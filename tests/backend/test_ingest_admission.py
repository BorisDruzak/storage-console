"""Memory admission refuses overload before reading bodies or committing receipts."""

import asyncio
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import TimeoutError as PoolTimeout

from apps.api.body_limit import IngestBodyLimit
from packages.shared.models.jobs import ingest_batches


def scope(path="/api/v1/ingest/inventory", query=b""):
    return {
        "type": "http",
        "method": "POST",
        "path": path,
        "query_string": query,
        "headers": [],
        "http_version": "1.1",
    }


def test_overload_does_not_consume_body_and_heartbeat_has_two_reserved_slots():
    from apps.api.ingest_admission import IngestAdmission

    async def run():
        entered = asyncio.Queue()
        release = asyncio.Event()
        received = []

        async def downstream(request, receive, send):
            entered.put_nowait(request["path"])
            await release.wait()
            await send({"type": "http.response.start", "status": 202, "headers": []})

        async def receive():
            received.append(True)
            raise AssertionError("refused body was consumed")

        async def send(message):
            pass

        app = IngestAdmission(downstream)
        tasks = []
        try:
            for _ in range(2):
                tasks.append(asyncio.create_task(app(scope(), receive, send)))
                await asyncio.wait_for(entered.get(), 1)
            refused = []

            async def collect(message):
                refused.append(message)

            await asyncio.wait_for(app(scope(), receive, collect), 1)
            assert refused[0]["status"] == 503
            assert (b"retry-after", b"1") in refused[0]["headers"]
            for _ in range(2):
                tasks.append(
                    asyncio.create_task(app(scope("/api/v1/ingest/heartbeat"), receive, send))
                )
                assert await asyncio.wait_for(entered.get(), 1) == "/api/v1/ingest/heartbeat"
            refused.clear()
            await app(scope("/api/v1/ingest/heartbeat"), receive, collect)
            assert refused[0]["status"] == 503
            assert not received
        finally:
            release.set()
            await asyncio.gather(*tasks)

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["exception", "cancel", "disconnect", "oversize"])
def test_slots_are_released_after_failure(failure):
    from apps.api.ingest_admission import IngestAdmission

    async def run():
        entered = asyncio.Event()

        async def downstream(request, receive, send):
            if request["query_string"] == b"fail":
                entered.set()
                if failure == "exception":
                    raise OSError("synthetic failure")
                if failure == "cancel":
                    await asyncio.Event().wait()
            await send({"type": "http.response.start", "status": 202, "headers": []})

        async def receive():
            if failure == "disconnect":
                return {"type": "http.disconnect"}
            return {"type": "http.request", "body": b"x" * 17, "more_body": False}

        sent = []

        async def send(message):
            sent.append(message)

        target = (
            IngestBodyLimit(downstream, 16) if failure in {"disconnect", "oversize"} else downstream
        )
        app = IngestAdmission(target)
        for _ in range(3):
            entered.clear()
            task = asyncio.create_task(app(scope(query=b"fail"), receive, send))
            if failure == "cancel":
                await asyncio.wait_for(entered.wait(), 1)
                task.cancel()
            if failure in {"cancel", "exception"}:
                with pytest.raises(asyncio.CancelledError if failure == "cancel" else OSError):
                    await task
            else:
                await task

        async def empty():
            return {"type": "http.request", "body": b"", "more_body": False}

        sent.clear()
        await app(scope(), empty, send)
        assert sent[0]["status"] == 202

    asyncio.run(run())


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="PostgreSQL required")
def test_real_api_refusal_does_not_write_receipt_and_replay_is_accepted(ingest_setup, monkeypatch):
    from test_ingest import batch

    from apps.api import ingest

    client, engine, collector, token, _ = ingest_setup
    assert client.get("/health").status_code == 200
    entered = threading.Barrier(3)
    release = threading.Event()
    actual = ingest.accept

    def hold(*args):
        if args[1] == "inventory" and not release.is_set():
            entered.wait(timeout=5)
            assert release.wait(10)
        return actual(*args)

    monkeypatch.setattr(ingest, "accept", hold)
    headers = {"Authorization": "Bearer " + token}
    payloads = [
        batch(
            collector,
            [{"kind": "volume", "unique_identity": f"ntfs:synthetic-{n}", "filesystem": "NTFS"}],
            uuid4().hex,
        )
        for n in range(3)
    ]

    def upload(payload):
        return client.post("/api/v1/ingest/inventory", json=payload, headers=headers)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(upload, payloads[n]) for n in range(2)]
        try:
            entered.wait(timeout=5)
            denied = upload(payloads[2])
            assert denied.status_code == 503
            assert denied.headers["Retry-After"] == "1"
            with engine.connect() as connection:
                assert connection.scalar(select(func.count()).select_from(ingest_batches)) == 0
            pulse = client.post(
                "/api/v1/ingest/heartbeat",
                json=batch(collector, [{"version": "synthetic"}], uuid4().hex),
                headers=headers,
            )
            assert pulse.status_code == 202
        finally:
            release.set()
        assert [future.result().status_code for future in futures] == [202, 202]
    replay = upload(payloads[2])
    assert replay.status_code == 202 and replay.json()["duplicate"] is False
    assert upload(payloads[2]).json()["duplicate"] is True
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(ingest_batches)) == 4


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="PostgreSQL required")
def test_runtime_pool_bounds_total_connections_and_wait_time():
    from packages.shared.database import make_engine

    engine = make_engine(os.environ["TEST_DATABASE_URL"])
    connections = []
    try:
        connections = [engine.connect() for _ in range(10)]
        started = time.monotonic()
        with pytest.raises(PoolTimeout):
            engine.connect()
        assert time.monotonic() - started < 4
    finally:
        for connection in connections:
            connection.close()
        engine.dispose()


def test_cancelled_sync_handlers_keep_slots_until_worker_finishes():
    from fastapi import FastAPI

    from apps.api.ingest_admission import IngestAdmission

    async def run():
        endpoint = FastAPI()
        entered = asyncio.Queue()
        release = threading.Event()
        loop = asyncio.get_running_loop()

        @endpoint.post("/api/v1/ingest/inventory")
        def hold(payload: dict):
            loop.call_soon_threadsafe(entered.put_nowait, True)
            assert release.wait(5)
            return {"accepted": True}

        app = IngestAdmission(IngestBodyLimit(endpoint, 16))
        sent = []

        async def receive():
            return {"type": "http.request", "body": b"{}", "more_body": False}

        async def send(message):
            sent.append(message)

        request = scope()
        request["headers"] = [(b"content-type", b"application/json")]
        try:
            for _ in range(2):
                task = asyncio.create_task(app(request.copy(), receive, send))
                await asyncio.wait_for(entered.get(), 1)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            sent.clear()
            await asyncio.wait_for(app(request.copy(), receive, send), 1)
            assert sent[0]["status"] == 503
            assert entered.empty()
        finally:
            release.set()
            # Only owned downstream tasks are drained, never unrelated loop tasks.
            if hasattr(app, "pending"):
                await asyncio.gather(*tuple(app.pending))

        sent.clear()
        await app(request.copy(), receive, send)
        assert sent[0]["status"] == 200

    asyncio.run(run())
