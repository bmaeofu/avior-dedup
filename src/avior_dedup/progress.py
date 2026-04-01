from __future__ import annotations

import asyncio
from typing import Any

from avior_dedup.schemas import ProgressSnapshot


class JobCancelled(Exception):
    """Raised when a job's cancelled flag is set."""


class ProgressReporter:
    """Thread-safe progress reporter that fans out updates to WebSocket listeners.

    The reporter is created on the asyncio event loop thread, but ``update()``
    is called from a worker thread via ``run_in_executor``.  All queue puts are
    therefore dispatched back to the event loop via ``loop.call_soon_threadsafe``.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self.snapshot = ProgressSnapshot()
        self.cancelled: bool = False
        self._listeners: list[asyncio.Queue[ProgressSnapshot]] = []

    # ------------------------------------------------------------------
    # Listener management (called from the event loop thread)
    # ------------------------------------------------------------------

    def subscribe(self) -> asyncio.Queue[ProgressSnapshot]:
        """Register a new listener queue and return it."""
        q: asyncio.Queue[ProgressSnapshot] = asyncio.Queue()
        self._listeners.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[ProgressSnapshot]) -> None:
        """Remove a listener queue."""
        try:
            self._listeners.remove(q)
        except ValueError:
            pass

    # ------------------------------------------------------------------
    # Update (safe to call from any thread)
    # ------------------------------------------------------------------

    def update(self, **kwargs: Any) -> None:
        """Update snapshot fields and push to all listener queues.

        This method is thread-safe — it schedules the actual queue puts on the
        event loop so that asyncio coroutines can await them normally.
        """
        for key, value in kwargs.items():
            setattr(self.snapshot, key, value)

        snapshot_copy = self.snapshot.model_copy()

        def _push() -> None:
            for q in list(self._listeners):
                try:
                    q.put_nowait(snapshot_copy)
                except asyncio.QueueFull:
                    pass

        self._loop.call_soon_threadsafe(_push)
