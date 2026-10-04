import asyncio
import json

import pytest
from starlette.responses import JSONResponse

from apps.api.source_control.transport import ControlTransport


def run_transport(path, body, headers, method="POST"):
    emitted, called = [], []
    chunks = iter([body[:10000], body[10000:]])

    async def app(scope, receive, send):
        called.append(True)
        await JSONResponse({"ok": True}, headers={"Cache-Control": "public"})(scope, receive, send)

    async def receive():
        chunk = next(chunks)
        return {"type": "http.request", "body": chunk, "more_body": len(chunk) == 10000}

    async def send(message):
        emitted.append(message)

    scope = {"type": "http", "path": path, "method": method, "headers": headers}
    asyncio.run(ControlTransport(app)(scope, receive, send))
    start = emitted[0]
    content = json.loads(b"".join(item.get("body", b"") for item in emitted[1:]))
    return start["status"], dict(start["headers"]), content, called


def test_transport_does_not_intercept_similarly_prefixed_noncontrol_routes():
    status, headers, _, called = run_transport(
        "/api/v1/sources-export", b" " * 20000, [], method="GET"
    )
    assert status == 200 and called
    assert headers[b"cache-control"] == b"public"


@pytest.mark.parametrize("length", [[], [(b"content-length", b"2")]])
def test_actual_chunked_body_limit_precedes_application_and_json_parsing(length):
    status, headers, content, called = run_transport(
        "/api/v1/sources",
        b"{" + b" " * 20000,
        [(b"content-type", b"application/json"), *length],
    )
    assert status == 413 and not called
    assert content == {"detail": "CONTROL_TOO_LARGE"}
    assert headers[b"cache-control"] == b"no-store"


def test_duplicate_content_type_is_denied_without_application_call():
    status, headers, content, called = run_transport(
        "/api/v1/collectors/synthetic/rotate-token",
        b"{}",
        [(b"content-type", b"application/json"), (b"content-type", b"application/json")],
    )
    assert status == 415 and not called
    assert content == {"detail": "CONTROL_JSON_REQUIRED"}
    assert headers[b"cache-control"] == b"no-store"


def test_allowed_body_overrides_cache_control_to_no_store():
    status, headers, _, called = run_transport(
        "/api/v1/sources", b"{}", [(b"content-type", b"application/json")]
    )
    assert status == 200 and called
    assert headers[b"cache-control"] == b"no-store"
