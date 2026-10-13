"""Strict resume, gap latch and independent SCM identity contracts."""

from uuid import UUID

import pytest
from test_windows_audit_events import module, xml
from test_windows_audit_store import store


class Reader:
    def __init__(self, rows):
        self.rows = iter(rows)

    def next(self):
        return next(self.rows, None)


def runtime(tmp_path, rows, **kwargs):
    return module("runtime").Capture(
        store(tmp_path),
        Reader(rows),
        module("scope").AuditScope({r"C:\Pilot": "volume-a"}),
        host_id=UUID(int=1),
        boot_id="boot-a",
        generation=UUID(int=2),
        **kwargs,
    )


def test_filtered_record_id_jumps_do_not_create_gap(tmp_path):
    capture = runtime(tmp_path, [(xml(record=10), "b10"), (xml(record=500), "b500")])
    assert capture.step() == "accepted" and capture.step() == "accepted"
    assert capture.store.gap() is None and capture.store.checkpoint()[0] == "b500"


def test_log_clear_stops_before_advancing_and_never_auto_rebaselines(tmp_path):
    capture = runtime(
        tmp_path,
        [
            (xml(record=10), "b10"),
            (xml(1102, record=1, provider="{fc65ddd8-d6ef-4962-83d5-6e5cfe9ce148}"), "clear"),
        ],
    )
    capture.step()
    assert capture.step() == "gap"
    assert capture.store.gap() == "AUDIT_LOG_CLEARED"
    assert capture.store.checkpoint()[0] == "b10"
    assert capture.step() == "gap"


def test_store_failure_restores_local_caches_before_retry(tmp_path):
    capture = runtime(tmp_path, [(xml(record=10), "b10")])
    commit = capture.store.commit

    def failed(*args):
        raise module("store").AuditStoreError("AUDIT_BACKPRESSURE")

    capture.store.commit = failed
    with pytest.raises(module("store").AuditStoreError):
        capture.step()
    assert capture.selector.snapshot()["accesses"] == []
    capture.store.commit = commit
    assert capture.step() == "accepted"
    assert capture.store.checkpoint()[0] == "b10"


def test_strict_stale_native_error_is_durable_gap(tmp_path):
    capture = runtime(tmp_path, [])

    def stale():
        raise module("native").EventLogError(15011)

    capture.reader.next = stale
    assert capture.step() == "gap"
    assert capture.store.gap() == "AUDIT_BOOKMARK_STALE"


def test_service_command_is_independent_and_cannot_target_old_usn_name():
    spec = module("scm").AuditServiceSpec(r"C:\Protected\python.exe", r"C:\AuditState")
    assert spec.name == "SosnadminStorageAudit"
    assert "collectors.windows_audit.service" in spec.command
    assert "collectors.windows.service" not in spec.command
    with pytest.raises(ValueError, match="AUDIT_SERVICE_NAME_INVALID"):
        module("scm").AuditServiceSpec(
            r"C:\Protected\python.exe", r"C:\AuditState", "SosnadminStorageCollector"
        )


def test_native_subscription_contract_never_uses_future_only_resume():
    assert module("native").RESUME_FLAGS == 0x10003
    assert module("native").INITIAL_FLAGS == 0x10002


def test_reboot_refuses_to_assign_current_boot_to_old_events(tmp_path):
    capture = runtime(tmp_path, [(xml(record=10), "b10")])
    capture.step()
    changed = module("runtime").Capture(
        capture.store,
        Reader([]),
        capture.selector.scope,
        host_id=UUID(int=1),
        boot_id="boot-b",
        generation=UUID(int=2),
    )
    assert changed.step() == "gap" and changed.store.gap() == "AUDIT_BOOT_CHANGED"


def test_generation_or_host_change_cannot_relabel_queued_evidence(tmp_path):
    capture = runtime(tmp_path, [(xml(record=10), "b10")])
    capture.step()
    changed = module("runtime").Capture(
        capture.store,
        Reader([]),
        capture.selector.scope,
        host_id=UUID(int=3),
        boot_id="boot-a",
        generation=UUID(int=4),
    )
    assert changed.step() == "gap"


def test_older_boot_events_are_filtered_and_not_given_current_session(tmp_path):
    from datetime import UTC, datetime

    capture = runtime(
        tmp_path, [(xml(record=10), "b10")], boot_started_at=datetime(2026, 10, 13, 1, tzinfo=UTC)
    )
    assert capture.step() == "filtered" and capture.store.peek() is None


def test_scope_guard_prevents_reparse_escape_without_claiming_historical_identity():
    scope = module("scope").AuditScope({r"C:\Pilot": "volume-a"}, guard=lambda path: False)
    from test_windows_audit_events import parse

    assert scope.select(parse(xml())) is None


def test_configuration_and_dpapi_chunking_contract():
    config = module("configuration")
    assert config.AuditConfig.model_fields["token"].repr is False
    assert config.QUEUE_NAME == "audit.sqlite3"
    assert config.CONFIG_NAME == "audit-config.dpapi"


def test_independent_scm_host_and_cli_modules_exist():
    assert callable(module("service").dispatch)
    assert callable(module("cli").entrypoint)


def test_long_cyrillic_cache_cannot_pin_bookmark_in_crash_loop(tmp_path):
    rows = [
        (
            xml(
                record=i,
                ObjectName="C:\\Pilot\\" + "Ж" * 16000,
                ProcessName="C:\\Synthetic\\" + "Я" * 16000,
            ),
            f"b{i}",
        )
        for i in range(1, 70)
    ]
    capture = runtime(tmp_path, rows)
    for _ in rows:
        capture.step()
    assert capture.store.checkpoint()[0] == "b69"


def test_native_leaf_guard_only_allows_genuine_missing_file():
    native = module("native")
    assert native.safe_leaf_attributes(0xFFFFFFFF, 2)
    assert not native.safe_leaf_attributes(0xFFFFFFFF, 5)
    assert not native.safe_leaf_attributes(0xFFFFFFFF, 32)
    assert not native.safe_leaf_attributes(0x400, 0)


def test_native_bounds_diagnostics_contract():
    assert callable(module("native").SecurityReader.bounds)


def test_queue_delivery_identity_matches_envelope_batch_id(tmp_path):
    import json

    capture = runtime(tmp_path, [(xml(record=10), "b10")])
    capture.step()
    queue_id, body = capture.store.peek()
    assert queue_id == json.loads(body)["batch_id"]


def test_explicit_initial_baseline_has_native_anchor_and_current_boot_session_bootstrap():
    native = module("native")
    assert callable(native.latest_baseline)
    assert callable(native.recent_session_xml)


def test_audit_registration_has_distinct_display_name_from_existing_usn():
    from contextlib import contextmanager
    from types import SimpleNamespace

    scm = module("scm")
    assert hasattr(scm, "AuditBackend"), "Audit must not reuse the USN display-name registration"
    calls = []

    @contextmanager
    def manager(access):
        yield 1

    def create(*args):
        calls.append(args)
        return 10

    backend = scm.AuditBackend.__new__(scm.AuditBackend)
    backend._manager = manager
    backend.api = SimpleNamespace(
        CreateServiceW=create,
        ChangeServiceConfig2W=lambda *args: True,
        CloseServiceHandle=lambda *args: True,
    )
    spec = scm.AuditServiceSpec(r"C:\Protected\python.exe", r"C:\AuditState")
    backend.create(spec)
    assert calls[0][2] != "Storage Console Collector"
    assert "Audit" in calls[0][2]


def test_scalar_evt_variant_count_is_undefined_and_not_an_array_flag():
    native = module("native")
    assert native.decode_uint64(123, 10, 0xFFFFFFFF) == 123
    with pytest.raises(native.EventLogError):
        native.decode_uint64(123, 0x80 | 10, 1)


def test_native_read_failure_preserves_numeric_code_without_exception_message():
    from collectors.windows.diagnostics import valid_detail

    native = module("native")
    error = native.EventLogError(15016)
    error.args = ("synthetic confidential event content",)
    failure = native.AuditReadFailure(error)
    assert failure.code == "AUDIT_READ_FAILED"
    assert failure.native_code == 15016
    assert valid_detail(failure.detail)
    assert "confidential" not in failure.detail
    for code in (-1, True, 2**32):
        assert native.AuditReadFailure(native.EventLogError(code)).native_code is None


@pytest.mark.parametrize("error", [259, 4317])
def test_empty_pull_subscription_resets_before_drain_without_crashing(monkeypatch, error):
    import ctypes
    from types import SimpleNamespace

    native = module("native")
    calls = []
    reader = native.SecurityReader.__new__(native.SecurityReader)
    reader.subscription, reader.signal, reader._draining = 100, 101, False
    reader.kernel = SimpleNamespace(
        WaitForSingleObject=lambda handle, timeout: 0,
        ResetEvent=lambda handle: calls.append(("reset", handle)) or True,
    )
    reader.api = SimpleNamespace(EvtNext=lambda *args: calls.append(("next", 100)) or False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: error, raising=False)
    assert reader.next() is None
    assert calls == [("reset", 101), ("next", 100)]


def test_unsignalled_pull_subscription_does_not_call_evt_next():
    from types import SimpleNamespace

    reader = module("native").SecurityReader.__new__(module("native").SecurityReader)
    reader.subscription, reader.signal, reader._draining = 100, 101, False
    reader.kernel = SimpleNamespace(WaitForSingleObject=lambda handle, timeout: 258)
    reader.api = SimpleNamespace()
    assert reader.next() is None


@pytest.mark.parametrize("error,returned", [(6, 0), (15011, 0), (4317, 1)])
def test_invalid_or_stale_pull_subscription_is_not_an_empty_result(monkeypatch, error, returned):
    import ctypes
    from types import SimpleNamespace

    native = module("native")
    reader = native.SecurityReader.__new__(native.SecurityReader)
    reader.subscription, reader.signal, reader._draining = 100, 101, False
    reader.kernel = SimpleNamespace(
        WaitForSingleObject=lambda handle, timeout: 0, ResetEvent=lambda handle: True
    )

    def failed(*args):
        ctypes.cast(args[-1], ctypes.POINTER(native.D)).contents.value = returned
        return False

    reader.api = SimpleNamespace(EvtNext=failed)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: error, raising=False)
    with pytest.raises(native.EventLogError) as caught:
        reader.next()
    assert caught.value.code == error


def test_subscription_arrival_during_empty_probe_keeps_wakeup(monkeypatch):
    import ctypes
    from types import SimpleNamespace

    native = module("native")
    reader = native.SecurityReader.__new__(native.SecurityReader)
    reader.subscription, reader.signal, reader._draining = 100, 101, False
    signal, probes = [True], []

    def reset(handle):
        signal[0] = False
        return True

    def next_event(*args):
        probes.append(1)
        # Publisher arrives immediately after the zero-result snapshot.
        signal[0] = True
        return False

    reader.kernel = SimpleNamespace(
        WaitForSingleObject=lambda *args: 0 if signal[0] else 258, ResetEvent=reset
    )
    reader.api = SimpleNamespace(EvtNext=next_event)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 259, raising=False)
    assert reader.next() is None and reader.next() is None
    assert len(probes) == 2, "PUBLISHED_EVENT_WAKEUP_WAS_LOST"


def test_evt_timeout_is_pending_and_does_not_advance_coverage(monkeypatch, tmp_path):
    import ctypes
    from types import SimpleNamespace

    native = module("native")
    reader = native.SecurityReader.__new__(native.SecurityReader)
    reader.subscription, reader.signal, reader._draining = 100, 101, False
    reader.kernel = SimpleNamespace(
        WaitForSingleObject=lambda *args: 0, ResetEvent=lambda handle: True
    )
    reader.api = SimpleNamespace(EvtNext=lambda *args: False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 1460, raising=False)
    capture = runtime(tmp_path, [])
    capture.reader = reader
    before = capture.store.checkpoint()
    assert capture.step() == "pending"
    assert capture.store.checkpoint() == before
