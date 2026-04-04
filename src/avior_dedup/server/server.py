from __future__ import annotations

import asyncio
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import uvicorn
import yaml
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from avior_dedup import config
from avior_dedup.cli import get_numbered_log_file
from avior_dedup.dedup.planner import build_move_plan, execute_move_plan
from avior_dedup.dedup.reporting import sort_and_finalize_log
from avior_dedup.dedup.scanner import find_duplicates
from avior_dedup.server.progress import JobCancelled, ProgressReporter
from avior_dedup.server.schemas import (
    ConfigUpdate,
    JobRequest,
    JobResult,
    JobStatus,
    ProgressSnapshot,
)
from avior_dedup.server.searchmove_routes import create_routes as create_searchmove_routes


@dataclass
class JobEntry:
    """In-memory state for a running or completed job."""
    status: JobStatus
    reporter: ProgressReporter


GIT_HASH = os.getenv("GIT_HASH", "dev")

app = FastAPI(title="avior-dedup API", version="0.1.0")

_jobs: dict[str, JobEntry] = {}
_executor = ThreadPoolExecutor(max_workers=4)

# Register Search & Move routes (shares job state and executor)
app.include_router(create_searchmove_routes(_jobs, _executor))


# ---------------------------------------------------------------------------
# Job runner (runs in thread pool)
# ---------------------------------------------------------------------------

def _run_job(job_id: str, req: JobRequest, reporter: ProgressReporter) -> None:
    """Execute the full dedup pipeline, pushing progress via reporter."""
    try:
        source_root = os.path.abspath(req.source.strip())
        target_root = os.path.abspath(req.target.strip())
        print(f"[avior-dedup] Job {job_id} starting: source={source_root!r}, target={target_root!r}")

        if not os.path.isdir(source_root):
            raise FileNotFoundError(f"Source directory does not exist: {source_root}")

        error_target = (
            os.path.abspath(req.error_target)
            if req.error_target
            else os.path.join(target_root, "errors")
        )
        novideo_target = (
            os.path.abspath(req.novideo_target)
            if req.novideo_target
            else os.path.join(target_root, "no_video")
        )

        os.makedirs(target_root, exist_ok=True)
        os.makedirs(error_target, exist_ok=True)
        os.makedirs(novideo_target, exist_ok=True)

        log_path = get_numbered_log_file(os.path.join(target_root, req.logname))
        log_handle = open(log_path, "w", encoding="utf-8")

        def log_fn(msg: str) -> None:
            log_handle.write(msg + "\n")

        # --- Phase: scanning ---
        reporter.update(phase="scanning", current_dir=None, dirs_completed=0, dirs_total=0, files_scanned=0)

        def scan_cb(current_dir: str, dirs_completed: int, dirs_total: int, files_scanned: int) -> None:
            if reporter.cancelled:
                raise JobCancelled
            reporter.update(
                phase="scanning",
                current_dir=current_dir,
                dirs_completed=dirs_completed,
                dirs_total=dirs_total,
                files_scanned=files_scanned,
            )

        groups, file_to_groupkey = find_duplicates(
            source_root,
            req.duptype,
            req.remove_episode_nos,
            req.semantic_prefixes,
            progress_cb=scan_cb,
        )

        reporter.update(phase="planning", groups_found=len(groups))

        # --- Phase: planning ---
        def plan_cb(current: int, total: int) -> None:
            if reporter.cancelled:
                raise JobCancelled
            reporter.update(phase="planning", files_planned=current, total_files_to_move=total)

        files_to_move, action_counter, size_counter = build_move_plan(
            groups=groups,
            target_root=target_root,
            error_target=error_target,
            novideo_target=novideo_target,
            max_errors_when_mc=req.max_errors_when_mc,
            duptype=req.duptype,
            file_to_groupkey=file_to_groupkey,
            log_fn=log_fn,
            progress_cb=plan_cb,
            max_duration_diff_longer=req.max_duration_diff_longer,
            max_duration_diff_shorter=req.max_duration_diff_shorter,
            selection_priorities=req.selection_priorities,
        )

        total_to_move = len(files_to_move)
        reporter.update(
            phase="executing",
            total_files_to_move=total_to_move,
            files_moved=0,
        )

        # --- Phase: executing ---
        def exec_cb(current: int, total: int) -> None:
            if reporter.cancelled:
                raise JobCancelled
            reporter.update(phase="executing", files_moved=current, total_files_to_move=total)

        execute_move_plan(
            files_to_move,
            source_root,
            req.mode,
            action_counter,
            log_fn,
            progress_cb=exec_cb,
            size_counter=size_counter,
        )

        log_handle.close()

        # Build a minimal args-like object for sort_and_finalize_log
        class _Args:
            mode = req.mode
            source = source_root
            target = target_root
            error_target = req.error_target
            novideo_target = req.novideo_target
            duptype = req.duptype
            max_errors_when_mc = req.max_errors_when_mc
            max_duration_diff_longer = req.max_duration_diff_longer
            max_duration_diff_shorter = req.max_duration_diff_shorter
            selection_priorities = req.selection_priorities
            semantic_prefixes = req.semantic_prefixes
            remove_episode_nos = req.remove_episode_nos

        sort_and_finalize_log(log_path, action_counter, _Args(), size_counter)

        scanned = reporter.snapshot.files_scanned
        print(f"[avior-dedup] Job {job_id} done: files_scanned={scanned}, groups={len(groups)}, actions={dict(action_counter)}")
        result = JobResult(
            files_scanned=scanned,
            groups_found=len(groups),
            action_counts=dict(action_counter),
            action_sizes=dict(size_counter),
            log_path=log_path,
        )
        _jobs[job_id].status = JobStatus(
            job_id=job_id,
            state="completed",
            progress=reporter.snapshot.model_copy(),
            result=result,
        )

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


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@app.get("/api/version")
async def get_version() -> dict[str, str]:
    """Return the current git commit hash."""
    return {"git_hash": GIT_HASH}


@app.post("/api/jobs", response_model=dict[str, str], status_code=201)
async def create_job(req: JobRequest) -> dict[str, str]:
    """Start a dedup job. Returns the job_id immediately."""
    loop = asyncio.get_running_loop()
    job_id = str(uuid.uuid4())
    reporter = ProgressReporter(loop)

    _jobs[job_id] = JobEntry(
        status=JobStatus(
            job_id=job_id,
            state="running",
            progress=ProgressSnapshot(),
        ),
        reporter=reporter,
    )

    loop.run_in_executor(_executor, _run_job, job_id, req, reporter)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}", response_model=JobStatus)
async def get_job(job_id: str) -> JobStatus:
    """Return current status of a job."""
    entry = _jobs.get(job_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Job not found")
    # Merge live progress into the stored status for running jobs
    if entry.status.state == "running":
        return JobStatus(
            job_id=job_id,
            state="running",
            progress=entry.reporter.snapshot.model_copy(),
        )
    return entry.status


@app.delete("/api/jobs/{job_id}", status_code=204)
async def cancel_job(job_id: str) -> None:
    """Signal a running job to cancel."""
    entry = _jobs.get(job_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Job not found")
    entry.reporter.cancelled = True


# ---------------------------------------------------------------------------
# Config endpoints
# ---------------------------------------------------------------------------

_VALID_CONFIG_NAMES = frozenset(config.config_files().keys())


@app.get("/api/config/{name}")
async def get_config(name: str) -> Any:
    """Return parsed YAML config by name."""
    if name not in _VALID_CONFIG_NAMES:
        raise HTTPException(status_code=404, detail=f"Unknown config '{name}'")
    filename = config.config_files()[name]
    path = config.config_dir() / filename
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@app.put("/api/config/{name}", status_code=204)
async def put_config(name: str, body: ConfigUpdate) -> None:
    """Overwrite a YAML config file and reload the in-memory cache."""
    if name not in _VALID_CONFIG_NAMES:
        raise HTTPException(status_code=404, detail=f"Unknown config '{name}'")
    filename = config.config_files()[name]
    path = config.config_dir() / filename
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(body.content, fh, allow_unicode=True)
    config.reload()


# ---------------------------------------------------------------------------
# WebSocket — live progress stream
# ---------------------------------------------------------------------------

@app.websocket("/api/ws/jobs/{job_id}")
async def ws_job_progress(websocket: WebSocket, job_id: str) -> None:
    """Stream ProgressSnapshot JSON at up to 10 msgs/sec (latest-wins throttle)."""
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
            # Pull all available snapshots; keep only the latest
            try:
                while True:
                    pending = queue.get_nowait()
            except asyncio.QueueEmpty:
                pass

            now = time.monotonic()
            if pending is not None and (now - last_sent) >= 0.1:
                await websocket.send_text(pending.model_dump_json())
                last_sent = now
                pending = None

            # Check if job finished
            if entry.status.state in ("completed", "failed", "cancelled") and queue.empty():
                # Send final status and close
                await websocket.send_text(entry.status.model_dump_json())
                break

            # Wait briefly for next update or yield control
            try:
                snapshot = await asyncio.wait_for(queue.get(), timeout=0.05)
                pending = snapshot
            except asyncio.TimeoutError:
                pass

    except WebSocketDisconnect:
        pass
    finally:
        entry.reporter.unsubscribe(queue)


# ---------------------------------------------------------------------------
# Static file serving (production frontend build)
# ---------------------------------------------------------------------------

_FRONTEND_DIST = Path(os.getenv("AVIOR_DEDUP_FRONTEND_DIST", ""))
if not _FRONTEND_DIST.is_dir():
    _FRONTEND_DIST = Path(__file__).parent.parent.parent.parent / "frontend" / "dist"
if _FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="static")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run() -> None:
    """Start the uvicorn server."""
    host = os.getenv("AVIOR_DEDUP_HOST", "0.0.0.0")
    port = int(os.getenv("AVIOR_DEDUP_PORT", "8642"))
    reload = os.getenv("AVIOR_DEDUP_RELOAD", "").lower() in ("1", "true", "yes")
    print(f"[avior-dedup] Starting server (commit: {GIT_HASH})")
    uvicorn.run("avior_dedup.server.server:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    run()
