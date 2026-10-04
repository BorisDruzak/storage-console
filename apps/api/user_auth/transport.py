from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from apps.api.body_limit import IngestBodyLimit


class AuthTransport:
    def __init__(self, app: ASGIApp) -> None:
        self.app = IngestBodyLimit(app, 16384, path_prefix="/api/v1/auth/", detail="AUTH_TOO_LARGE")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/api/v1/auth/"):
            await self.app(scope, receive, send)
            return

        async def no_store(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (k, v) for k, v in message.get("headers", []) if k.lower() != b"cache-control"
                ]
                message = {**message, "headers": [*headers, (b"cache-control", b"no-store")]}
            await send(message)

        if scope["path"] == "/api/v1/auth/login" and scope["method"] == "POST":
            content_types = [v for k, v in scope["headers"] if k.lower() == b"content-type"]
            if (
                len(content_types) != 1
                or content_types[0].split(b";", 1)[0].strip().lower() != b"application/json"
            ):
                await JSONResponse({"detail": "AUTH_JSON_REQUIRED"}, status_code=415)(
                    scope, receive, no_store
                )
                return
        await self.app(scope, receive, no_store)
