from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from apps.api.body_limit import IngestBodyLimit


class ControlTransport:
    def __init__(self, app: ASGIApp) -> None:
        self.unbounded = app
        self.app = IngestBodyLimit(
            IngestBodyLimit(
                app, 16384, path_prefix="/api/v1/collectors", detail="CONTROL_TOO_LARGE"
            ),
            16384,
            path_prefix="/api/v1/sources",
            detail="CONTROL_TOO_LARGE",
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        roots = ("/api/v1/sources", "/api/v1/collectors")
        if scope["type"] != "http" or not any(
            scope["path"] == root or scope["path"].startswith(root + "/") for root in roots
        ):
            await self.unbounded(scope, receive, send)
            return

        async def no_store(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != b"cache-control"
                ]
                message = {**message, "headers": [*headers, (b"cache-control", b"no-store")]}
            await send(message)

        if scope["method"] in ("POST", "PATCH"):
            content_types = [
                value for key, value in scope["headers"] if key.lower() == b"content-type"
            ]
            if (
                len(content_types) != 1
                or content_types[0].split(b";", 1)[0].strip().lower() != b"application/json"
            ):
                await JSONResponse({"detail": "CONTROL_JSON_REQUIRED"}, status_code=415)(
                    scope, receive, no_store
                )
                return
        await self.app(scope, receive, no_store)
