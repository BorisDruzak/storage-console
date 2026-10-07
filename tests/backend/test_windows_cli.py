import importlib
import io
import signal
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from collectors.common.outbox import Outbox, OutboxError
from collectors.common.transport import DeliveryOutcome
from collectors.windows.configuration import RuntimeSettings
from collectors.windows.inventory import Observation, Scope
from collectors.windows.producer import CaptureReport, capture_inventory
from packages.contracts.inventory import VolumeRecord


@pytest.fixture
def cli():
    return importlib.import_module("collectors.windows.cli")


@pytest.fixture
def loaded(tmp_path):
    collector = uuid4()
    box = Outbox(tmp_path / "state" / "outbox.sqlite3", collector)
    config = SimpleNamespace(settings=RuntimeSettings(poll_seconds=0.05), collector_id=collector)

    class Sender:
        collector_id = collector

        def send(self, claim):
            return DeliveryOutcome("accepted", duplicate=False)

    return SimpleNamespace(config=config, outbox=box, transport=Sender())


def inventory(loaded):
    return capture_inventory(
        loaded.outbox,
        Scope(("C:\\synthetic",)),
        iter([Observation(record=VolumeRecord(
            occurred_at=datetime.now(UTC), unique_identity="synthetic-volume", filesystem="NTFS"
        ))]),
    )


def test_argument_errors_never_echo_supplied_secret(cli, capsys):
    secret = "private-not-a-cli-argument"
    assert cli.main(["activate", "--token", secret]) == 2
    assert secret not in str(capsys.readouterr())


def test_bad_platform_is_safe(cli, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_windows", lambda: False)
    assert cli.main(["status"]) == 1
    assert "PLATFORM_UNSUPPORTED" in capsys.readouterr().err


def test_key_stdin_is_bounded_and_prompt_fails_closed(cli, monkeypatch):
    key = "a" * 43
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(key + "\n"))
    assert cli._key(True) == key
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(key + "x\n"))
    with pytest.raises(cli.SecurityError):
        cli._key(True)
    def unsafe(prompt):
        import warnings
        warnings.warn("unsafe", cli.getpass.GetPassWarning, stacklevel=2)
    monkeypatch.setattr(cli.getpass, "getpass", unsafe)
    with pytest.raises(cli.SecurityError):
        cli._key(False)


def test_once_delivers_inventory_and_heartbeat(cli, loaded):
    report = inventory(loaded)
    class Capture:
        def poll(self):
            return report
        def stop(self, grace):
            pytest.fail("Completed capture must not be stopped")
    result = cli.inventory_once(loaded, capture_factory=Capture)
    assert result.complete and result.pending == 0 and result.errors == ()
    assert result.records == 1 and result.delivered == 2
    assert loaded.outbox.checkpoint("windows:heartbeat").revision == 1


def test_once_partial_is_not_success_even_when_delivered(cli, loaded):
    inventory(loaded)
    class Capture:
        def poll(self):
            return CaptureReport(1, 1, False, ("ACCESS_DENIED",))
    result = cli.inventory_once(loaded, capture_factory=Capture)
    assert not result.complete and result.pending == 0
    assert result.errors == ("ACCESS_DENIED",)


def test_once_pending_and_stalled_capture_have_bounded_exit(cli, loaded):
    class Capture:
        stopped = False
        def poll(self):
            return None
        def stop(self, grace):
            self.stopped = True
            return CaptureReport(0, 0, False, ("STOPPED",))
    capture = Capture()
    tick = iter([0, 2, 4, 6, 8, 10, 12, 14, 16, 18])
    result = cli.inventory_once(
        loaded, capture_factory=lambda: capture, scan_seconds=1, settle_seconds=1,
        monotonic=lambda: next(tick),
    )
    assert capture.stopped and not result.complete and "SCAN_TIMEOUT" in result.errors


def test_status_outbox_read_only_does_not_create_or_migrate(tmp_path):
    path = tmp_path / "state" / "outbox.sqlite3"
    identity = uuid4()
    Outbox(path, identity)
    before = path.read_bytes()
    readonly = Outbox(path, identity, read_only=True)
    assert readonly.status().pending_count == 0
    assert not readonly.auth_suspended()
    assert readonly.checkpoint("windows:inventory").revision == 0
    assert before == path.read_bytes()
    with pytest.raises(OutboxError):
        Outbox(path.parent / "absent.sqlite3", identity, read_only=True)
    assert not (path.parent / "absent.sqlite3").exists()


def test_status_only_prints_safe_checkpoints(cli, loaded, capsys):
    inventory(loaded)
    loaded.config.origin = "https://storage.example.test"
    loaded.config.roots = ("C:\\synthetic",)
    loaded.config.scope = Scope(loaded.config.roots)
    cli.print_status(loaded.config, loaded.outbox)
    output = capsys.readouterr().out
    assert "storage.example.test" in output and "Корней scope: 1" in output
    assert "C:\\synthetic" not in output
    assert "scope" not in output.split("Inventory checkpoint:")[-1]


def test_scope_rejects_drive_root_and_state_overlap(cli, tmp_path):
    for root, state in [("C:\\", "C:\\state"), ("C:\\synthetic", "C:\\synthetic\\state")]:
        with pytest.raises(cli.CaptureError):
            cli._scope(root, state)


def test_once_auth_suspension_cannot_report_success(cli, loaded):
    report = inventory(loaded)
    class Capture:
        def poll(self):
            return report
    loaded.transport.send = lambda claim: DeliveryOutcome("suspended", code="AUTH_REQUIRED")
    result = cli.inventory_once(loaded, capture_factory=Capture)
    assert not result.complete and "AUTH_REQUIRED" in result.errors
    assert result.pending > 0 and result.delivered == 0


def test_ctrl_c_reaches_runtime_stop_and_restores_handler(cli, monkeypatch, loaded, capsys):
    previous = signal.getsignal(signal.SIGINT)
    stopped = []
    class State:
        def __init__(self, *args):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            stopped.append("state-closed")
    class Runtime:
        events = ()
        def __init__(self, value):
            assert value is loaded
        def run(self, stop):
            signal.getsignal(signal.SIGINT)(signal.SIGINT, None)
            assert stop.is_set()
            stopped.append("runtime-stopped")
    monkeypatch.setattr(cli, "_windows", lambda: True)
    monkeypatch.setattr(cli, "ProtectedState", State)
    monkeypatch.setattr(cli, "load", lambda state: loaded)
    monkeypatch.setattr(cli, "Runtime", Runtime)
    assert cli.main(["run"]) == 130
    assert stopped == ["runtime-stopped", "state-closed"]
    assert signal.getsignal(signal.SIGINT) is previous
    assert "Runtime остановлен" in capsys.readouterr().out
