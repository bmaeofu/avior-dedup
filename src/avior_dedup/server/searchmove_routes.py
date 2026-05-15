"""API router for Search & Move jobs.

Has its own job storage and WebSocket endpoint so it runs independently
from the dedup module.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from avior_dedup.cli import get_numbered_log_file
from avior_dedup.searchmove.models import ActivityMode
from avior_dedup.searchmove.runner import run_search_move_job
from avior_dedup.searchmove.mover import clear_directory_file_index_cache
from avior_dedup.server.progress import JobCancelled, ProgressReporter
from avior_dedup.permissions import ensure_output_permissions
from avior_dedup.server.schemas import (
    JobStatus,
    ProgressSnapshot,
    SearchMoveMatchEntry,
    SearchMoveRequest,
    SearchMoveResult,
)

router = APIRouter(prefix="/api/searchmove", tags=["searchmove"])

_MODE_MAP: dict[str, ActivityMode] = {
    "copy": ActivityMode.COPY,
    "move": ActivityMode.MOVE,
    "delete": ActivityMode.DELETE,
    "test": ActivityMode.TEST,
}


@dataclass
class _SmJobEntry:
    """In-memory state for a running or completed search-move job."""
    status: JobStatus
    reporter: ProgressReporter


_jobs: dict[str, _SmJobEntry] = {}
_executor = ThreadPoolExecutor(max_workers=4)


def _get_searchmove_output_paths(dest: str, logname: str) -> tuple[str, str]:
    """Choose non-conflicting output file paths for a Search & Move job."""
    log_path = get_numbered_log_file(os.path.join(dest, logname))
    output_path = get_numbered_log_file(os.path.join(dest, "results.txt"))
    return log_path, output_path


# ---------------------------------------------------------------------------
# Job runner (runs in thread pool)
# ---------------------------------------------------------------------------

def _run_searchmove_job(
    job_id: str,
    req: SearchMoveRequest,
    reporter: ProgressReporter,
) -> None:
    """Execute a search-move job in a thread pool worker."""
    try:
        source = os.path.abspath(req.source.strip())
        dest = os.path.abspath(req.dest.strip())
        mode = _MODE_MAP[req.mode]

        if not os.path.exists(source):
            raise FileNotFoundError(f"Source does not exist: {source}")

        os.makedirs(dest, exist_ok=True)
        ensure_output_permissions(dest, is_dir=True)

        log_path, output_path = _get_searchmove_output_paths(dest, req.logname)

        ensure_output_permissions(log_path, is_dir=False)
        ensure_output_permissions(output_path, is_dir=False)
        log_handle = open(log_path, "w", encoding="utf-8")

        # Write header with all job parameters for easier debugging and audit.
        try:
            log_handle.write(f"Job ID:\t{job_id}\n")
            log_handle.write(f"Timestamp:\t{time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            log_handle.write(f"Source:\t{source}\n")
            log_handle.write(f"Dest:\t{dest}\n")
            log_handle.write(f"Mode:\t{req.mode}\n")
            log_handle.write(f"Extensions:\t{','.join(req.extensions or [])}\n")
            log_handle.write(f"Recursive:\t{req.recursive}\n")
            log_handle.write(f"Preserve_Dirs:\t{getattr(req, 'preserve_dirs', False)}\n")
            log_handle.write(f"Ignored_Directories:\t{','.join(req.ignored_directories or [])}\n")
            log_handle.write(f"Search_Expressions:\t{','.join(req.search_expressions or [])}\n")
            log_handle.write(f"Output_File:\t{output_path}\n")
            log_handle.write("---\n")
        except Exception:
            # Defensive: do not fail job start because of logging
            pass

        def log_fn(msg: str) -> None:
            """Write log lines but skip lines that indicate an existing destination.

            Per-user request, avoid listing siblings that were not actually moved
            due to the destination already existing. Other log lines are kept.
            """
            try:
                # If this looks like a per-file record with tab-separated fields,
                # skip entries that report destination existence.
                if "\t" in msg:
                    parts = msg.split("\t")
                    status = parts[-1].strip().lower()
                    if "destination already exists" in status or status == "already exists":
                        return
            except Exception:
                # Defensive: on any parse error, fall back to writing the line.
                pass

            log_handle.write(msg + "\n")

        def progress_cb(**kw: object) -> None:
            if reporter.cancelled:
                raise JobCancelled
            reporter.update(**kw)

        def cancel_check() -> bool:
            return reporter.cancelled

        result = run_search_move_job(
            source=source,
            dest=dest,
            mode=mode,
            ignored_directories=req.ignored_directories,
            extensions=req.extensions,
            search_expressions=req.search_expressions,
            recursive=req.recursive,
            preserve_dirs=getattr(req, 'preserve_dirs', False),
            progress_cb=progress_cb,
            log_fn=log_fn,
            cancel_check=cancel_check,
            output_path=output_path,
            log_path=log_path,
        )

        sm_result = SearchMoveResult(
            files_scanned=result.files_scanned,
            files_matched=result.files_matched,
            action_counts=result.action_counts,
            matches=[
                SearchMoveMatchEntry(
                    file_path=m.file_path,
                    matched_expression=m.matched_expression,
                    found_values=m.found_values,
                )
                for m in result.matches
            ],
            log_path=log_path,
        )
        # Append a concise statistics summary to the log for quick inspection.
        try:
            log_handle.write("--- STATS ---\n")
            log_handle.write(f"SCAN_SECONDS\t{result.scan_seconds:.3f}\n")
            log_handle.write(f"SEARCH_SECONDS\t{result.search_seconds:.3f}\n")
            log_handle.write(f"EXECUTE_SECONDS\t{result.execute_seconds:.3f}\n")
            log_handle.write(f"TOTAL_SECONDS\t{result.total_seconds:.3f}\n")
            log_handle.write(f"Files_Scanned:\t{result.files_scanned}\n")
            log_handle.write(f"Files_Matched:\t{result.files_matched}\n")
            log_handle.write(f"Action_Counts:\t{result.action_counts}\n")
            # Also expand action counts into individual lines for easier grepping.
            for k, v in (result.action_counts or {}).items():
                log_handle.write(f"Action_{k}:\t{v}\n")
                # Do not include Log_Path in the STATS section
            log_handle.write("--- END STATS ---\n")
        except Exception:
            pass
        _jobs[job_id].status = JobStatus(
            job_id=job_id,
            state="completed",
            progress=reporter.snapshot.model_copy(),
            result=sm_result,
        )
        log_handle.close()

    except JobCancelled:
        _jobs[job_id].status = JobStatus(
            job_id=job_id,
            state="cancelled",
            progress=reporter.snapshot.model_copy(),
        )
    except Exception as exc:  # noqa: BLE001
        _jobs[job_id].status = JobStatus(
            job_id=job_id,
            state="failed",
            progress=reporter.snapshot.model_copy(),
            error=str(exc),
        )
    finally:
        if "log_handle" in locals() and not log_handle.closed:
            log_handle.close()
        # Invalidate directory file index cache to avoid stale entries across jobs.
        try:
            clear_directory_file_index_cache()
        except Exception:
            # Defensive: do not allow cache-clear errors to interfere with cleanup
            pass


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@router.post("/jobs", response_model=dict[str, str], status_code=201)
async def create_searchmove_job(req: SearchMoveRequest) -> dict[str, str]:
    """Start a search-move job. Returns the job_id immediately."""
    loop = asyncio.get_running_loop()
    job_id = str(uuid.uuid4())
    reporter = ProgressReporter(loop)

    _jobs[job_id] = _SmJobEntry(
        status=JobStatus(
            job_id=job_id,
            state="running",
            progress=ProgressSnapshot(),
        ),
        reporter=reporter,
    )

    loop.run_in_executor(_executor, _run_searchmove_job, job_id, req, reporter)
    return {"job_id": job_id}


@router.get("/jobs/{job_id}", response_model=JobStatus)
async def get_searchmove_job(job_id: str) -> JobStatus:
    """Return current status of a search-move job."""
    entry = _jobs.get(job_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if entry.status.state == "running":
        return JobStatus(
            job_id=job_id,
            state="running",
            progress=entry.reporter.snapshot.model_copy(),
        )
    return entry.status


@router.delete("/jobs/{job_id}", status_code=204)
async def cancel_searchmove_job(job_id: str) -> None:
    """Signal a running search-move job to cancel."""
    entry = _jobs.get(job_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Job not found")
    entry.reporter.cancelled = True


# ---------------------------------------------------------------------------
# WebSocket — live progress stream
# ---------------------------------------------------------------------------

@router.websocket("/ws/jobs/{job_id}")
async def ws_searchmove_progress(websocket: WebSocket, job_id: str) -> None:
    """Stream ProgressSnapshot JSON at up to 10 msgs/sec."""
    entry = _jobs.get(job_id)
    if entry is None:
        await websocket.close(code=4004)
        return

    await websocket.accept()
    queue = entry.reporter.subscribe()

    try:
        last_sent = 0.0
        pending: ProgressSnapshot | None = None

        while True:
            try:
                while True:
                    pending = queue.get_nowait()
            except asyncio.QueueEmpty:
                pass

            now = time.monotonic()
            min_interval = 0.0 if (pending is not None and pending.phase == "executing") else 0.1
            if pending is not None and (now - last_sent) >= min_interval:
                await websocket.send_text(pending.model_dump_json())
                last_sent = now
                pending = None

            if entry.status.state in ("completed", "failed", "cancelled") and queue.empty():
                await websocket.send_text(entry.status.model_dump_json())
                break

            try:
                snapshot = await asyncio.wait_for(queue.get(), timeout=0.05)
                pending = snapshot
            except asyncio.TimeoutError:
                pass

    except WebSocketDisconnect:
        pass
    finally:
        entry.reporter.unsubscribe(queue)
