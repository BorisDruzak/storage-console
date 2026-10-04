from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class IngestBodyLimit:
    """Bound chunked bodies before JSON parsing, including absent/false Content-Length."""

    def __init__(
        self,
        app: ASGIApp,
        max_bytes: int,
        *,
        path_prefix: str = "/api/v1/ingest/",
        detail: str = "INGEST_TOO_LARGE",
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.path_prefix = path_prefix
        self.detail = detail

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(self.path_prefix):
            await self.app(scope, receive, send)
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.max_bytes:
                await JSONResponse({"detail": self.detail}, status_code=413)(
                    scope,
                    receive,
                    send,
                )
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
