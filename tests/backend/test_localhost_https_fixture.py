"""The native HTTPS fixture must serve both localhost address families."""

from __future__ import annotations

import errno
import socket
import ssl
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import urlsplit

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from tests.deployment import collector_delivery
from tests.deployment.collector_delivery import _loopback_listeners, serving_ingest


async def _accepted(request: Request) -> Response:
    return Response(status_code=204)


@pytest.mark.parametrize("address", ["127.0.0.1", "::1"])
def test_verified_localhost_tls_on_each_loopback(tmp_path: Path, address: str) -> None:
    if address == "::1":
        try:
            with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as probe:
                probe.bind(("::1", 0))
        except OSError as exc:
            if exc.errno in {errno.EAFNOSUPPORT, errno.EPROTONOSUPPORT, errno.EADDRNOTAVAIL}:
                pytest.skip("Kernel does not provide IPv6 loopback")
            raise
    app = Starlette(routes=[Route("/", _accepted)])
    with serving_ingest(app, tmp_path / "tls") as (origin, ca):
        assert urlsplit(origin).hostname == "localhost"
        port = urlsplit(origin).port
        assert port is not None
        context = ssl.create_default_context(cafile=str(ca))
        with socket.create_connection((address, port), timeout=5) as connection:
            with context.wrap_socket(connection, server_hostname="localhost") as secure:
                assert secure.getpeercert()
                secure.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
                assert secure.recv(4096).startswith(b"HTTP/1.1 204")


def _assert_closed(sockets: list[socket.socket]) -> None:
    assert sockets
    for owned in sockets:
        assert owned.fileno() == -1


@pytest.mark.parametrize(
    ("stage", "error", "fallback"),
    [
        ("create", errno.EAFNOSUPPORT, True),
        ("option", errno.ENOPROTOOPT, True),
        ("bind", errno.EADDRNOTAVAIL, True),
        ("bind", errno.EADDRINUSE, False),
        ("create", errno.EMFILE, False),
        ("bind", errno.EACCES, False),
    ],
)
def test_listener_failures_are_fenced_and_owned_sockets_closed(
    monkeypatch: pytest.MonkeyPatch, stage: str, error: int, fallback: bool
) -> None:
    real_socket = socket.socket
    owned: list[socket.socket] = []

    def create(family: int, kind: int) -> socket.socket | Mock:
        if family == socket.AF_INET6 and stage == "create":
            raise OSError(error, "Synthetic socket failure")
        connection = real_socket(family, kind)
        owned.append(connection)
        if family == socket.AF_INET6:
            proxy = Mock(wraps=connection)
            method = proxy.setsockopt if stage == "option" else proxy.bind
            method.side_effect = OSError(error, "Synthetic socket failure")
            return proxy
        return connection

    monkeypatch.setattr(collector_delivery.socket, "socket", create)
    if fallback:
        with _loopback_listeners() as listeners:
            assert len(listeners) == 1
            assert listeners[0].getsockname()[0] == "127.0.0.1"
    else:
        with pytest.raises(OSError) as raised, _loopback_listeners():
            pytest.fail("Unexpected errors must prevent server startup")
        assert raised.value.errno == error
    _assert_closed(owned)


@pytest.mark.parametrize("failure", ["body", "thread_start", "server_start"])
def test_ingest_closes_listeners_after_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    owned: list[socket.socket] = []

    @contextmanager
    def capture() -> Iterator[list[socket.socket]]:
        with _loopback_listeners() as listeners:
            owned.extend(listeners)
            addresses = [listener.getsockname() for listener in listeners]
            assert {address[0] for address in addresses} <= {"127.0.0.1", "::1"}
            assert len({address[1] for address in addresses}) == 1
            yield listeners

    monkeypatch.setattr(collector_delivery, "_loopback_listeners", capture)
    if failure == "thread_start":
        monkeypatch.setattr(
            collector_delivery.threading.Thread, "start", Mock(side_effect=RuntimeError("probe"))
        )
    elif failure == "server_start":
        monkeypatch.setattr(collector_delivery.uvicorn.Server, "run", Mock(return_value=None))
    with pytest.raises(RuntimeError), serving_ingest(Starlette(), tmp_path / "tls"):
        assert failure == "body"
        raise RuntimeError("Synthetic context body failure")
    _assert_closed(owned)
