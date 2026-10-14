"""Overload must be refused through real TLS before a paused upload completes."""

import json
import socket
import ssl
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from deploy.scripts.commands import Compose


def verify_overload(values: dict[str, str], compose: Compose, root: Path) -> None:
    def sql(statement: str) -> str:
        return compose.call(
            "exec", "-T", "postgres", "psql", "-At", "-v", "ON_ERROR_STOP=1",
            "-U", values["POSTGRES_USER"], "-d", values["POSTGRES_DB"], "-c", statement,
        ).strip()

    def await_count(statement: str, expected: int) -> None:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if int(sql(statement)) >= expected:
                return
            time.sleep(0.05)
        raise AssertionError("Synthetic lock/ingest handlers did not enter")

    context = ssl.create_default_context(cafile=root / "ca.pem")

    def connect() -> ssl.SSLSocket:
        return context.wrap_socket(
            socket.create_connection(("127.0.0.1", int(values["HTTPS_PORT"])), timeout=5),
            server_hostname="storage.example.test",
        )

    stamp = datetime.now(UTC).isoformat()
    payload = json.dumps({
        "collector_id": str(uuid4()), "batch_id": uuid4().hex, "schema_version": 1,
        "sent_at": stamp, "first_event_at": stamp, "last_event_at": stamp, "record_count": 1,
        "records": [{"occurred_at": stamp, "kind": "volume", "unique_identity": "ntfs:synthetic",
                     "filesystem": "NTFS"}],
    }).encode()

    def headers(length: bytes) -> bytes:
        return (b"POST /api/v1/ingest/inventory HTTP/1.1\r\n"
                b"Host: storage.example.test\r\nContent-Type: application/json\r\n"
                b"Authorization: Bearer synthetic-collector-token-only-for-fixture\r\n"
                b"Connection: close\r\n"
                + length + b"\r\n\r\n")

    def status(connection: ssl.SSLSocket) -> tuple[int, bytes]:
        reply = bytearray()
        while b"\r\n\r\n" not in reply and len(reply) < 8192:
            chunk = connection.recv(1024)
            assert chunk, "Gateway closed before sending headers"
            reply.extend(chunk)
        return int(reply.split(b" ", 2)[1]), bytes(reply).lower()

    def held_upload() -> int:
        with connect() as connection:
            connection.sendall(headers(b"Content-Length: " + str(len(payload)).encode()) + payload)
            return status(connection)[0]

    # Only this disposable Compose project's synthetic database is locked.
    lock = subprocess.Popen(
        [*compose.base, "exec", "-T", "postgres", "psql", "-At", "-v", "ON_ERROR_STOP=1",
         "-U", values["POSTGRES_USER"], "-d", values["POSTGRES_DB"]],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=compose.environment,
    )
    assert lock.stdin is not None
    try:
        lock.stdin.write(b"BEGIN; LOCK TABLE collectors IN ACCESS EXCLUSIVE MODE;\n")
        lock.stdin.flush()
        await_count("SELECT count(*) FROM pg_locks WHERE relation='collectors'::regclass "
                    "AND mode='AccessExclusiveLock' AND granted", 1)
        with ThreadPoolExecutor(max_workers=2) as pool:
            uploads = [pool.submit(held_upload) for _ in range(2)]
            try:
                await_count("SELECT count(*) FROM pg_stat_activity WHERE wait_event='relation' "
                            "AND query LIKE '%FROM collectors%'", 2)
                for declaration, partial in (
                    (b"Content-Length: 16777216", b"{"),
                    (b"Transfer-Encoding: chunked", b"1\r\n{\r\n"),
                ):
                    with connect() as connection:
                        connection.sendall(headers(declaration) + partial)
                        code, reply = status(connection)
                        assert code == 503 and b"retry-after: 1" in reply
                assert sql("SELECT count(*) FROM ingest_batches") == "0"
            finally:
                lock.stdin.write(b"ROLLBACK;\n\\q\n")
                lock.stdin.flush()
            assert [upload.result() for upload in uploads] == [401, 401]
        assert lock.wait(timeout=10) == 0
        print("Strict HTTPS paused length/chunked uploads refused before buffering: PASS")
    finally:
        if lock.poll() is None:
            lock.stdin.close()  # EOF also rolls back the owned transaction.
            lock.wait(timeout=10)
        if lock.stdout is not None:
            lock.stdout.close()
        if lock.stderr is not None:
            lock.stderr.close()
