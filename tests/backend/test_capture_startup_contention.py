"""Child startup must distinguish temporary queue contention from invalid state."""

from __future__ import annotations

import io
import sqlite3
import threading
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from collectors.common.outbox import Outbox, OutboxError
from collectors.windows import _capture_worker as worker
from collectors.windows.capture_process import CaptureProcess
from collectors.windows.configuration import RuntimeSettings
from collectors.windows.inventory import CaptureError
from collectors.windows.producer import CaptureReport


def _worker_harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    collector, binding = uuid4(), uuid4()
    box = Outbox(tmp_path / "outbox.sqlite3", collector)
    box.activate_credentials(binding)
    with closing(sqlite3.connect(box.path, autocommit=True)) as connection:
        connection.execute("UPDATE meta SET auth_suspended=1")
    settings = RuntimeSettings()
    request = worker._Request(
        state=str(tmp_path), collector_id=collector, credential_version=binding,
        roots=("C:\\synthetic",), settings=settings,
    )
    calls = []

    class State:
        root = tmp_path

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def validate_file(self, name):
            assert name == "outbox.sqlite3"

    def capture(opened, scope, observations, **kwargs):
        assert opened.credential_binding() == binding
        assert opened.auth_suspended()
        calls.append(1)
        return CaptureReport(0, 0, True, ())

    api = SimpleNamespace(
        bind=lambda *args: None,
        kernel=SimpleNamespace(GetStdHandle=lambda *args: 1, PeekNamedPipe=lambda *args: True),
    )
    monkeypatch.setattr(worker, "ProtectedState", State)
    monkeypatch.setattr(worker, "_api", lambda: api)
    monkeypatch.setattr(
        worker, "NativeInventory", lambda: SimpleNamespace(scan=lambda scope: iter(()))
    )
    monkeypatch.setattr(worker, "capture_inventory", capture)

    def run():
        output = io.BytesIO()
        with monkeypatch.context() as streams:
            streams.setattr(worker.sys, "stdin", SimpleNamespace(
                buffer=SimpleNamespace(raw=io.BytesIO(request.model_dump_json().encode() + b"\n"))
            ))
            streams.setattr(worker.sys, "stdout", SimpleNamespace(buffer=output))
            assert worker.main() == 0
        return CaptureProcess.decode(output.getvalue())

    return box, calls, run


def test_real_sqlite_startup_busy_unlocks_without_false_state_mismatch(tmp_path, monkeypatch):
    box, captures, run = _worker_harness(tmp_path, monkeypatch)
    box.limits = replace(box.limits, busy_timeout_seconds=1)
    ready, release, busy_seen = threading.Event(), threading.Event(), threading.Event()
    failures, busy_codes, attempts = [], [], []
    original = worker.Outbox

    def opened(*args, **kwargs):
        attempts.append(1)
        try:
            return original(*args, **kwargs)
        except OutboxError as error:
            if error.retryable:
                busy_codes.append(error.sqlite_errorcode)
                busy_seen.set()
                release.set()
            raise

    def writer():
        try:
            with closing(sqlite3.connect(box.path, autocommit=True)) as connection:
                connection.execute("BEGIN EXCLUSIVE")
                ready.set()
                assert release.wait(10)
                connection.execute("ROLLBACK")
        except Exception as error:
            failures.append(type(error).__name__)
            ready.set()

    monkeypatch.setattr(worker, "Outbox", opened)
    thread = threading.Thread(target=writer)
    thread.start()
    try:
        assert ready.wait(5) and not failures
        report = run()
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive() and not failures
    assert busy_seen.is_set() and busy_codes[0] == sqlite3.SQLITE_BUSY
    assert report.completed and not report.errors, report
    assert len(attempts) >= 2 and captures == [1]
    assert box.auth_suspended() and box.status().pending_count == 0
    assert box.checkpoint("windows:inventory").revision == 0


def _request(box, binding=None):
    return worker._Request(
        state=str(box.path.parent), collector_id=box.collector_id,
        credential_version=binding or box.credential_binding(),
        roots=("C:\\synthetic",), settings=RuntimeSettings(),
    )


def _state(box):
    return SimpleNamespace(root=box.path.parent, validate_file=Mock())


def test_real_binding_busy_is_revalidated_before_capture(tmp_path, monkeypatch):
    box, captures, run = _worker_harness(tmp_path, monkeypatch)
    arm, ready, release = threading.Event(), threading.Event(), threading.Event()
    failures, attempts, busy = [], [], []
    original = worker.Outbox

    def writer():
        try:
            assert arm.wait(5)
            with closing(sqlite3.connect(box.path, autocommit=True)) as connection:
                connection.execute("BEGIN EXCLUSIVE")
                ready.set()
                assert release.wait(10)
                connection.execute("ROLLBACK")
        except Exception as error:
            failures.append(type(error).__name__)
            ready.set()

    def opened(*args, **kwargs):
        current = original(*args, **kwargs)
        attempts.append(1)
        if len(attempts) == 1:
            binding = current.credential_binding

            def read():
                arm.set()
                assert ready.wait(5) and not failures
                try:
                    return binding()
                except OutboxError as error:
                    busy.append(error.sqlite_errorcode)
                    release.set()
                    raise

            current.credential_binding = read
        return current

    monkeypatch.setattr(worker, "Outbox", opened)
    thread = threading.Thread(target=writer)
    thread.start()
    try:
        report = run()
    finally:
        arm.set()
        release.set()
        thread.join(5)
    assert not thread.is_alive() and not failures
    assert busy == [sqlite3.SQLITE_BUSY]
    assert report.completed and not report.errors and captures == [1]
    assert len(attempts) >= 2 and box.auth_suspended()


@pytest.mark.parametrize(
    ("code", "sqlite_code"),
    [("UNSAFE_STATE", None), ("SCHEMA_UNSUPPORTED", None),
     ("IDENTITY_CONFLICT", None), ("STATE_UNAVAILABLE", sqlite3.SQLITE_CORRUPT)],
)
def test_hard_startup_errors_fail_without_retry_or_capture(
    tmp_path, monkeypatch, code, sqlite_code
):
    _, captures, run = _worker_harness(tmp_path, monkeypatch)
    opened = Mock(side_effect=OutboxError(code, sqlite_errorcode=sqlite_code))
    monkeypatch.setattr(worker, "Outbox", opened)
    report = run()
    assert report.errors == ("STATE_MISMATCH",) and not report.completed
    assert opened.call_count == 1 and not captures
    assert not any(t.name == "capture-control" for t in threading.enumerate())


def test_binding_mismatch_does_not_retry_or_change_auth(tmp_path, monkeypatch):
    box, _, _ = _worker_harness(tmp_path, monkeypatch)
    opened = Mock(wraps=Outbox)
    monkeypatch.setattr(worker, "Outbox", opened)
    state = _state(box)
    with pytest.raises(CaptureError, match="STATE_MISMATCH"):
        worker._open_outbox(state, _request(box, uuid4()), threading.Event())
    assert opened.call_count == 1 and state.validate_file.call_count == 1
    assert box.auth_suspended() and box.status().pending_count == 0


@pytest.mark.parametrize("stage", ["constructor", "binding"])
def test_control_stops_before_capture_even_during_startup(tmp_path, monkeypatch, stage):
    _, captures, run = _worker_harness(tmp_path, monkeypatch)
    entered, control_seen = threading.Event(), threading.Event()
    original = worker.Outbox

    def peek(*args):
        if entered.is_set():
            control_seen.set()
            return False  # Real control() treats pipe EOF as STOP.
        return True

    worker._api().kernel.PeekNamedPipe = peek

    def stopped():
        entered.set()
        assert control_seen.wait(5), "control thread was not started before initialization"

    def opened(*args, **kwargs):
        if stage == "constructor":
            stopped()
        current = original(*args, **kwargs)
        read = current.credential_binding

        def binding():
            assert stage == "binding", "binding must not run after constructor STOP"
            stopped()
            return read()

        current.credential_binding = binding
        return current

    monkeypatch.setattr(worker, "Outbox", opened)
    report = run()
    assert control_seen.is_set() and report.errors == ("STOPPED",) and not captures
    assert not any(t.name == "capture-control" for t in threading.enumerate())


def test_busy_retry_uses_cancellable_wait(tmp_path, monkeypatch):
    box, _, _ = _worker_harness(tmp_path, monkeypatch)
    request = _request(box)
    stop = threading.Event()
    waits = []

    def cancel(seconds):
        waits.append(seconds)
        stop.set()
        return True

    stop.wait = cancel
    opened = Mock(side_effect=OutboxError("STATE_UNAVAILABLE", sqlite_errorcode=5))
    monkeypatch.setattr(worker, "Outbox", opened)
    with pytest.raises(CaptureError, match="STOPPED"):
        worker._open_outbox(_state(box), request, stop)
    assert opened.call_count == 1 and len(waits) == 1 and 0 < waits[0] <= 1


def test_expired_budget_does_not_start_another_attempt(tmp_path, monkeypatch):
    box, _, _ = _worker_harness(tmp_path, monkeypatch)
    request = _request(box)
    ticks = iter([0, 0, 31])
    monkeypatch.setattr(worker, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    opened = Mock(side_effect=OutboxError("STATE_UNAVAILABLE", sqlite_errorcode=5))
    monkeypatch.setattr(worker, "Outbox", opened)
    stop = threading.Event()
    stop.wait = Mock(side_effect=AssertionError("no wait after expiry"))
    with pytest.raises(OutboxError) as caught:
        worker._open_outbox(_state(box), request, stop)
    assert caught.value.retryable and opened.call_count == 1


def test_expired_constructor_budget_does_not_read_binding(tmp_path, monkeypatch):
    box, _, _ = _worker_harness(tmp_path, monkeypatch)
    request = _request(box)
    ticks = iter([0, 0, 31, 31])
    monkeypatch.setattr(worker, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    binding = Mock(side_effect=AssertionError("no binding after expiry"))
    monkeypatch.setattr(worker, "Outbox", Mock(return_value=SimpleNamespace(
        credential_binding=binding
    )))
    with pytest.raises(OutboxError) as caught:
        worker._open_outbox(_state(box), request, threading.Event())
    assert caught.value.retryable
    binding.assert_not_called()
