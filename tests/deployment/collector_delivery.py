"""Disposable real HTTPS ingest and crash probe; no credentials in arguments or logs."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import uvicorn
from starlette.types import ASGIApp

from collectors.common.delivery import Delivery
from collectors.common.outbox import Claim, Outbox
from collectors.common.transport import DeliveryOutcome, Transport


def setup_tls(root: Path) -> None:
    executable = shutil.which("openssl")
    if executable is None and os.name == "nt":
        candidate = Path("C:/Program Files/Git/usr/bin/openssl.exe")
        executable = str(candidate) if candidate.is_file() else None
    if executable is None:
        raise RuntimeError("NATIVE_TLS_EXECUTABLE_REQUIRED")
    root.mkdir(mode=0o700)
    extensions = root / "extensions.cnf"
    extensions.write_text(
        "subjectAltName=DNS:localhost\nbasicConstraints=critical,CA:FALSE\n"
        "keyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n"
        "subjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n",
        encoding="ascii",
    )
    common = [executable, "req", "-newkey", "rsa:2048", "-nodes"]
    commands = [
        [
            *common,
            "-x509",
            "-days",
            "2",
            "-subj",
            "/CN=Synthetic Delivery CA",
            "-addext",
            "basicConstraints=critical,CA:TRUE",
            "-addext",
            "keyUsage=critical,keyCertSign,cRLSign",
            "-addext",
            "subjectKeyIdentifier=hash",
            "-keyout",
            str(root / "ca.key"),
            "-out",
            str(root / "ca.pem"),
        ],
        [
            *common,
            "-subj",
            "/CN=localhost",
            "-keyout",
            str(root / "key.pem"),
            "-out",
            str(root / "leaf.csr"),
        ],
        [
            executable,
            "x509",
            "-req",
            "-in",
            str(root / "leaf.csr"),
            "-CA",
            str(root / "ca.pem"),
            "-CAkey",
            str(root / "ca.key"),
            "-CAcreateserial",
            "-days",
            "2",
            "-extfile",
            str(extensions),
            "-out",
            str(root / "cert.pem"),
        ],
    ]
    for command in commands:
        try:
            subprocess.run(
                command,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
            )
        except (OSError, subprocess.SubprocessError):
            raise RuntimeError("NATIVE_TLS_FIXTURE_FAILED") from None
    for file in root.iterdir():
        file.chmod(0o600)


@contextmanager
def serving_ingest(app: ASGIApp, root: Path) -> Iterator[tuple[str, Path]]:
    setup_tls(root)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    origin = "https://localhost:" + str(listener.getsockname()[1])
    config = uvicorn.Config(
        app,
        loop="asyncio",
        access_log=False,
        log_config=None,
        ssl_keyfile=str(root / "key.pem"),
        ssl_certfile=str(root / "cert.pem"),
        timeout_graceful_shutdown=2,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        if not server.started:
            raise RuntimeError("NATIVE_INGEST_START_FAILED")
        yield origin, root / "ca.pem"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()
        if thread.is_alive():
            raise RuntimeError("NATIVE_INGEST_STOP_FAILED")


def crash_after_accept() -> None:
    try:
        raw = sys.stdin.buffer.read(256 * 1024 + 1)
        if len(raw) > 256 * 1024:
            raise ValueError
        config = json.loads(raw)
        identity = UUID(config["collector_id"])
        box = Outbox(Path(config["outbox"]), identity)
        transport = Transport(
            config["origin"], Path(config["ca"]), config["token"], collector_id=identity
        )

        class CrashSender:
            collector_id = identity

            def send(self, claim: Claim) -> DeliveryOutcome:
                receipt = transport.send(claim)
                if receipt.kind == "accepted" and receipt.duplicate is False:
                    # Real server commit succeeded; simulate client death before local ACK.
                    os._exit(29)
                return receipt

        Delivery(box, CrashSender(), clock=lambda: datetime.now(UTC)).run_once()
    except Exception:
        os._exit(28)
    os._exit(28)


if __name__ == "__main__":
    if sys.argv[1:] != ["--crash-after-accept"]:
        raise SystemExit(28)
    crash_after_accept()
