"""Bound resident ingest bodies without creating a waiting-request queue."""

import asyncio
from threading import BoundedSemaphore, Lock

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from apps.api.body_limit import BODY_READY


class IngestAdmission:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        # Also safe when the same application is exercised by multiple event loops.
        self.heavy = BoundedSemaphore(2)
        self.heartbeats = BoundedSemaphore(2)
        self.pending: set[asyncio.Task[None]] = set()
        self.lock = Lock()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/api/v1/ingest/"):
            await self.app(scope, receive, send)
            return
        slots = self.heartbeats if scope["path"] == "/api/v1/ingest/heartbeat" else self.heavy
        if not slots.acquire(blocking=False):
            await JSONResponse(
                {"detail": "INGEST_BUSY"},
                status_code=503,
                headers={"Retry-After": "1", "Cache-Control": "no-store"},
            )(scope, receive, send)
            return
        scope.pop(BODY_READY, None)

        async def downstream() -> None:
            await self.app(scope, receive, send)

        task = asyncio.create_task(downstream())
        with self.lock:
            self.pending.add(task)

        def completed(finished: asyncio.Task[None]) -> None:
            with self.lock:
                self.pending.discard(finished)
            slots.release()
            # A disconnected parent may no longer await the downstream exception.
            if not finished.cancelled():
                finished.exception()

        task.add_done_callback(completed)
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            if not scope.get(BODY_READY, False):
                task.cancel()
            # Fully buffered requests can own a non-cancellable threadpool worker.
            # Keep that bounded child alive and release only when it finishes.
            raise
