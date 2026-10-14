"""Large approved scope must not turn directory width into resident path memory."""

import json
import stat
import threading
import tracemalloc
from contextlib import nullcontext
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from test_collector_transport import authorities as authorities


@pytest.mark.parametrize("reject_first", [True, False])
def test_wide_directory_checks_first_child_without_loading_remaining_paths(
    monkeypatch, reject_first
):
    from collectors.windows_audit import readiness

    yielded = 0
    closed = 0

    class Entry:
        def __init__(self, index):
            self.path = f"synthetic-root/file-{index}"

        def stat(self, *, follow_symlinks):
            assert follow_symlinks is False
            return SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0)

        def is_symlink(self):
            return False

        def is_dir(self, *, follow_symlinks):
            assert follow_symlinks is False
            return False

    class Children:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.close()

        def close(self):
            nonlocal closed
            closed += 1

        def __iter__(self):
            return self

        def __next__(self):
            nonlocal yielded
            if yielded == 52000:
                raise StopIteration
            yielded += 1
            return Entry(yielded)

    monkeypatch.setattr(readiness.os, "scandir", lambda _: Children())
    tracemalloc.start()
    try:
        result = readiness.scope_covered(
            "synthetic-root", ["sid"],
            lambda path, *_: path == "synthetic-root" or not reject_first,
            limit=100000,
        )
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert result is not reject_first
    assert yielded == (1 if reject_first else 52000)
    assert closed == 1
    assert peak < 4 * 1024**2


def test_explicit_large_scope_handles_real_unicode_descendants(tmp_path):
    from collectors.windows_audit.readiness import scope_covered

    for index in range(300):
        (tmp_path / f"Синтетический-отчёт-{index}").touch()
    assert not scope_covered(str(tmp_path), ["sid"], lambda *_: True)
    assert scope_covered(str(tmp_path), ["sid"], lambda *_: True, limit=1000)


def test_timeout_and_cancellation_do_not_verify_partial_tree(tmp_path):
    from collectors.windows_audit.readiness import scope_covered

    (tmp_path / "child").touch()
    clock = iter((0.0, 0.0, 31.0))
    assert not scope_covered(
        str(tmp_path), ["sid"], lambda *_: True, clock=lambda: next(clock), max_seconds=30
    )
    assert not scope_covered(str(tmp_path), ["sid"], lambda *_: True, stopped=lambda: True)


def test_deep_tree_is_rejected_before_opening_unbounded_handles(tmp_path):
    from collectors.windows_audit.readiness import scope_covered

    cursor = tmp_path
    for _ in range(5):
        cursor = cursor / "d"
        cursor.mkdir()
    assert not scope_covered(str(tmp_path), ["sid"], lambda *_: True, max_depth=3)
    assert scope_covered(str(tmp_path), ["sid"], lambda *_: True, max_depth=8)


@pytest.mark.parametrize(
    "limit,depth,seconds",
    [(True, 128, 30), (100001, 128, 30), (256, 0, 30), (256, 128, float("nan"))],
)
def test_invalid_resource_budgets_fail_closed(tmp_path, limit, depth, seconds):
    from collectors.windows_audit.readiness import scope_covered

    assert not scope_covered(
        str(tmp_path), ["sid"], lambda *_: True, limit=limit, max_depth=depth, max_seconds=seconds
    )


def test_operator_large_scope_configuration_is_validated_without_secret_leak(authorities):
    from pydantic import ValidationError

    from collectors.windows_audit.configuration import AuditConfig

    data = {
        "collector_id": "00000000-0000-0000-0000-000000000001",
        "host_id": "00000000-0000-0000-0000-000000000002",
        "source_id": "00000000-0000-0000-0000-000000000003",
        "generation": "00000000-0000-0000-0000-000000000004",
        "roots": {r"D:\Synthetic\Department": "synthetic-volume"},
        "origin": "https://synthetic.example.test",
        "ca_file": str(authorities[0] / "ca.pem"),
        "token": "a" * 43,
        "readiness_max_objects": 100000,
    }
    config = AuditConfig.model_validate(data)
    assert config.readiness_max_objects == 100000
    default = AuditConfig.model_validate(
        {k: v for k, v in data.items() if k != "readiness_max_objects"}
    )
    assert default.readiness_max_objects == 256
    for value in (True, 0, 100001, "100000"):
        with pytest.raises(ValidationError) as error:
            AuditConfig.model_validate({**data, "readiness_max_objects": value})
        assert data["token"] not in str(error.value)


def test_background_probe_does_not_block_status_and_closes_on_stop():
    from collectors.windows_audit.readiness_worker import ReadinessWorker

    entered = threading.Event()
    cancelled = threading.Event()

    def probe(stopped):
        entered.set()
        while not stopped():
            cancelled.wait(0.001)
        cancelled.set()
        return True, True, 52000

    with ReadinessWorker(probe) as worker:
        assert entered.wait(1)
        snapshot = worker.snapshot()
        assert snapshot["sacl_verified"] is False
        assert snapshot["readiness_complete"] is False
    assert cancelled.wait(1)
    assert not worker.snapshot()["sacl_verified"]


def test_background_completed_proof_expires_from_scan_start():
    from collectors.windows_audit.readiness_worker import ReadinessWorker

    finished = threading.Event()
    clock = [0.0]

    def probe(_):
        clock[0] = 25.0
        finished.set()
        return True, True, 52000

    with ReadinessWorker(probe, clock=lambda: clock[0]) as worker:
        assert finished.wait(1)
        assert worker.wait_initial(1)
        snapshot = worker.snapshot()
        assert snapshot["sacl_verified"]
        assert snapshot["readiness_objects"] == 52000
        assert snapshot["readiness_duration_seconds"] == 25
        clock[0] = 61.0
        expired = worker.snapshot()
        assert expired["sacl_verified"] is False
        assert expired["readiness_stale"] is True


def test_probe_exception_never_exposes_path_or_reuses_old_positive_proof():
    from collectors.windows_audit.readiness_worker import ReadinessWorker

    def denied(_):
        raise PermissionError("synthetic-private-path-and-account")

    with ReadinessWorker(denied) as worker:
        assert worker.wait_initial(1)
        snapshot = worker.snapshot()
        assert snapshot["policy_verified"] is False
        assert snapshot["sacl_verified"] is False
        assert snapshot["readiness_error"] == "AUDIT_READINESS_UNAVAILABLE"
        assert "synthetic-private" not in str(snapshot)


def test_native_probe_accepts_exact_total_budget_and_distinguishes_incomplete(
    tmp_path, monkeypatch
):
    from collectors.windows_audit import readiness
    from collectors.windows_audit.readiness_worker import native_probe

    (tmp_path / "child").touch()
    monkeypatch.setattr(
        readiness,
        "Native",
        lambda: SimpleNamespace(
            privilege=nullcontext,
            policy=lambda: True,
            sacl_entry=lambda *_: True,
        ),
    )
    assert native_probe([str(tmp_path)], ["sid"], 2)(lambda: False) == (True, True, 2)
    with pytest.raises(ValueError, match="AUDIT_READINESS_INCOMPLETE"):
        native_probe([str(tmp_path)], ["sid"], 1)(lambda: False)


def test_capture_never_reports_healthy_after_background_proof_expires(tmp_path, monkeypatch):
    from collectors.windows_audit import configuration, native, runtime
    from collectors.windows_audit.readiness_worker import ReadinessWorker

    class Cipher:
        def protect(self, value):
            return value

        def unprotect(self, value):
            return value

    stop = threading.Event()
    clock = [0.0]

    class Reader:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def bounds(self):
            return {"oldest_record_id": 1, "newest_record_id": 1}

        def next(self):
            clock[0] = 61.0
            stop.set()
            return None

    monkeypatch.setattr(configuration, "MachineCipher", Cipher)
    monkeypatch.setattr(native, "SecurityReader", Reader)
    monkeypatch.setattr(native, "boot_epoch", lambda: ("synthetic-boot", datetime.now(UTC)))
    monkeypatch.setattr(runtime.time, "monotonic", lambda: clock[0])
    state = SimpleNamespace(
        root=tmp_path, write=lambda name, data: (tmp_path / name).write_bytes(data)
    )
    config = SimpleNamespace(
        configured=True, mode="deliver", collector_id=UUID(int=1), host_id=UUID(int=2),
        generation=UUID(int=3), roots={r"D:\Synthetic": "volume"}, audit_sids=["sid"],
        initial_baseline=True, readiness_max_objects=100000,
    )
    with ReadinessWorker(lambda _: (True, True, 52000), clock=lambda: clock[0]) as worker:
        assert worker.wait_initial(1)
        runtime._capture(state, config, stop, verifier=worker)
    status = json.loads((tmp_path / "audit-status.json").read_bytes())
    assert status["health"] == "OBSERVE"
    assert status["sacl_verified"] is False
    assert status["readiness_stale"] is True
    assert status["gap"] is None


def test_operator_lower_object_budget_cannot_use_unbounded_default_probe(tmp_path, monkeypatch):
    from collectors.windows_audit import readiness, runtime

    (tmp_path / "child").touch()
    class NativeFixture:
        def privilege(self):
            return nullcontext()

        def policy(self):
            return True

        def sacl_entry(self, *_):
            return True

        def sacl(self, root, sids):
            return readiness.scope_covered(root, sids, self.sacl_entry)

    monkeypatch.setattr(readiness, "Native", NativeFixture)
    results = []

    def consuming_runtime(_state, config, _stop, *, verifier=None):
        if verifier is None:
            results.append(readiness.readiness(list(config.roots), config.audit_sids)[1])
        else:
            assert verifier.wait_initial(1)
            results.append(verifier.snapshot()["sacl_verified"])

    monkeypatch.setattr(runtime, "_run_capture", consuming_runtime)
    config = SimpleNamespace(
        mode="deliver", roots={str(tmp_path): "volume"}, audit_sids=["sid"],
        readiness_max_objects=1,
    )
    runtime.run_capture(None, config, threading.Event())
    assert results == [False]


def test_default_budget_also_uses_asynchronous_expiring_readiness(monkeypatch):
    from collectors.windows_audit import runtime
    worker = object()
    monkeypatch.setattr(runtime, "ReadinessWorker", lambda probe: nullcontext(worker))
    monkeypatch.setattr(runtime, "native_probe", lambda *args: object())
    seen = []
    monkeypatch.setattr(runtime, "_run_capture", lambda *args, verifier=None: seen.append(verifier))
    runtime.run_capture(None, SimpleNamespace(
        mode="deliver", roots={r"D:\Synthetic": "volume"}, audit_sids=["sid"],
        readiness_max_objects=256,
    ), threading.Event())
    assert seen == [worker]


@pytest.mark.parametrize("duration,expected_wait", [(0, 30), (22, 8), (29.5, 0.5)])
def test_probe_period_includes_scan_duration(duration, expected_wait):
    from collectors.windows_audit.readiness_worker import ReadinessWorker

    at = [0.0]
    waits = []

    class Stop:
        def is_set(self):
            return bool(waits)

        def wait(self, timeout):
            waits.append(timeout)
            return True

    def probe(_):
        at[0] += duration
        return True, True, 1

    worker = ReadinessWorker(probe, clock=lambda: at[0])
    worker._stop = Stop()
    worker._run()
    assert waits == [expected_wait]


def test_consecutive_complete_probes_keep_previous_proof_fresh_until_publish():
    from collectors.windows_audit.readiness_worker import ReadinessWorker

    at = [0.0]
    calls = []
    waits = []
    intervening = []

    class Stop:
        def is_set(self):
            return len(waits) == 2

        def wait(self, timeout):
            waits.append(timeout)
            at[0] += timeout
            return self.is_set()

    def probe(_):
        at[0] += 22
        if calls:
            intervening.append(worker.snapshot())
        calls.append(True)
        return True, True, 1

    worker = ReadinessWorker(probe, clock=lambda: at[0])
    worker._stop = Stop()
    worker._run()
    assert len(intervening) == 1
    assert intervening[0]["policy_verified"] and intervening[0]["sacl_verified"]
    assert not intervening[0]["readiness_stale"]
    assert intervening[0]["readiness_age_seconds"] <= 60


def test_failed_probe_keeps_backoff_instead_of_repeating_a_full_failed_scan():
    from collectors.windows_audit.readiness_worker import ReadinessWorker

    at = [0.0]
    waits = []

    class Stop:
        def is_set(self):
            return bool(waits)

        def wait(self, timeout):
            waits.append(timeout)
            return True

    def probe(_):
        at[0] += 30
        raise ValueError("AUDIT_READINESS_INCOMPLETE")

    worker = ReadinessWorker(probe, clock=lambda: at[0])
    worker._stop = Stop()
    worker._run()
    assert waits == [30]
