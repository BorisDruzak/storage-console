"""Blocked capture retains evidence while continuing to publish fresh diagnostics."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from collectors.windows_audit import configuration, native, runtime
from collectors.windows_audit.store import AuditStore


class Cipher:
    def protect(self, value):
        return value

    def unprotect(self, value):
        return value


@pytest.mark.parametrize("configured,gap", [(True, False), (True, True), (False, False)])
@pytest.mark.parametrize("later_healthy", [False, True])
def test_blocked_capture_refreshes_status_without_opening_subscription(
    tmp_path, monkeypatch, configured, gap, later_healthy
):
    monkeypatch.setattr(configuration, "MachineCipher", Cipher)
    writes = []

    class Stop:
        stopped = False
        waits = 0

        def is_set(self):
            return self.stopped

        def wait(self, timeout=None):
            self.waits += 1
            self.stopped = timeout is None or self.waits >= 3
            return self.stopped

    class Verifier:
        calls = 0

        def snapshot(self):
            self.calls += 1
            return {
                "policy_verified": True,
                "sacl_verified": later_healthy and self.calls > 1,
                "readiness_complete": True, "readiness_stale": False,
                "readiness_age_seconds": float(self.calls),
                "readiness_checked_at": datetime.now(UTC).isoformat(),
            }

    def forbidden(*_args, **_kwargs):
        pytest.fail("Blocked capture must not open a Security subscription")

    monkeypatch.setattr(native, "SecurityReader", forbidden)
    store = AuditStore(tmp_path / "audit.sqlite3", UUID(int=1), Cipher())
    if gap:
        store.latch_gap("AUDIT_CONFIGURATION_CHANGED")
    checkpoint = store.checkpoint()
    config = SimpleNamespace(
        configured=configured, mode="deliver", collector_id=UUID(int=1),
        roots={r"D:\Synthetic": "volume"}, audit_sids=["synthetic"],
    )
    state = SimpleNamespace(
        root=tmp_path, write=lambda name, value: writes.append(json.loads(value))
    )
    runtime._capture(state, config, Stop(), verifier=Verifier())
    assert len(writes) >= 2
    assert writes[-1]["readiness_age_seconds"] > writes[0]["readiness_age_seconds"]
    assert all(row["health"] == ("GAP" if gap else "NOT_CONFIGURED") for row in writes)
    assert store.checkpoint() == checkpoint
    assert store.gap() == ("AUDIT_CONFIGURATION_CHANGED" if gap else None)
