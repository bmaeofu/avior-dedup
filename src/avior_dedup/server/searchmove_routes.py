"""API router for Search & Move jobs."""

from __future__ import annotations

import asyncio
import os
import uuid

from fastapi import APIRouter, HTTPException

from avior_dedup.searchmove.models import ActivityMode
from avior_dedup.searchmove.runner import run_search_move_job
from avior_dedup.server.progress import JobCancelled, ProgressReporter
from avior_dedup.server.schemas import (
    JobStatus,
    ProgressSnapshot,
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


def _run_searchmove_job(
    job_id: str,
    req: SearchMoveRequest,
    reporter: ProgressReporter,
    jobs: dict,
) -> None:
    """Execute a search-move job in a thread pool worker."""
    try:
        source = os.path.abspath(req.source.strip())
        dest = os.path.abspath(req.dest.strip())
        mode = _MODE_MAP[req.mode]

        if not os.path.exists(source):
            raise FileNotFoundError(f"Source does not exist: {source}")

        os.makedirs(dest, exist_ok=True)
        log_path = os.path.join(dest, req.logname)
        log_handle = open(log_path, "w", encoding="utf-8")

        def log_fn(msg: str) -> None:
            log_handle.write(msg + "\n")

        def progress_cb(**kw: object) -> None:
            if reporter.cancelled:
                raise JobCancelled
            reporter.update(**kw)

        def cancel_check() -> bool:
            return reporter.cancelled

        output_path = os.path.join(dest, "results.txt")

        result = run_search_move_job(
            source=source,
            dest=dest,
            mode=mode,
            extensions=req.extensions,
            search_expressions=req.search_expressions,
            recursive=req.recursive,
            progress_cb=progress_cb,
            log_fn=log_fn,
            cancel_check=cancel_check,
            output_path=output_path,
        )

        log_handle.close()

        sm_result = SearchMoveResult(
            files_scanned=result.files_scanned,
            files_matched=result.files_matched,
            action_counts=result.action_counts,
            log_path=log_path,
        )
        jobs[job_id].status = JobStatus(
            job_id=job_id,
            state="completed",
            progress=reporter.snapshot.model_copy(),
            result=sm_result,
        )

    except JobCancelled:
        jobs[job_id].status = JobStatus(
            job_id=job_id,
            state="cancelled",
            progress=reporter.snapshot.model_copy(),
        )
    except Exception as exc:  # noqa: BLE001
        jobs[job_id].status = JobStatus(
            job_id=job_id,
            state="failed",
            progress=reporter.snapshot.model_copy(),
            error=str(exc),
        )


def create_routes(jobs: dict, executor) -> APIRouter:
    """Build the router with access to shared job state and executor."""

    @router.post("/jobs", response_model=dict[str, str], status_code=201)
    async def create_searchmove_job(req: SearchMoveRequest) -> dict[str, str]:
        """Start a search-move job. Returns the job_id immediately."""
        loop = asyncio.get_running_loop()
        job_id = str(uuid.uuid4())
        reporter = ProgressReporter(loop)

        from avior_dedup.server.server import JobEntry

        jobs[job_id] = JobEntry(
            status=JobStatus(
                job_id=job_id,
                state="running",
                progress=ProgressSnapshot(),
            ),
            reporter=reporter,
        )

        loop.run_in_executor(executor, _run_searchmove_job, job_id, req, reporter, jobs)
        return {"job_id": job_id}

    @router.get("/jobs/{job_id}", response_model=JobStatus)
    async def get_searchmove_job(job_id: str) -> JobStatus:
        """Return current status of a search-move job."""
        entry = jobs.get(job_id)
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
        entry = jobs.get(job_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="Job not found")
        entry.reporter.cancelled = True

    return router
