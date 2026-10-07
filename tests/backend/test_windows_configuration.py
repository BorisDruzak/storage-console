import json
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_collector_outbox import heartbeat
from test_collector_transport import authorities as authorities

from collectors.common.outbox import Outbox
from collectors.windows import configuration
from collectors.windows.errors import SecurityError
from collectors.windows.inventory import Scope
from collectors.windows.security import ProtectedState


@pytest.mark.skipif(os.name != "nt", reason="Native protected configuration")
def test_oversized_config_is_rejected_before_any_activation(tmp_path, authorities):
    roots = tuple(
        "C:\\synthetic-" + str(index) + "\\" + "\\".join(["x" * 250] * 63) for index in range(10)
    )
    with ProtectedState(tmp_path / "state", create=True) as state:
        collector = uuid4()
        with pytest.raises(SecurityError, match="^CONFIG_INVALID$"):
            configuration.activate(
                state,
                collector,
                "https://localhost",
                Scope(roots),
                "a" * 43,
                (authorities[0] / "ca.pem").read_bytes(),
            )
        assert not (state.root / "config.json").exists()
        assert not (state.root / "outbox.sqlite3").exists()


@pytest.mark.parametrize(
    "settings",
    [
        {"heartbeat_seconds": 0},
        {"heartbeat_seconds": True},
        {"poll_seconds": 0},
        {"transport_seconds": 16},
        {"stop_seconds": 15},
        {"batch_records": 513},
        {"retained_batches": 32},
        {"reserve_bytes": 512 * 1024**2},
        {"unknown": 1},
    ],
)
def test_settings_reject_unsafe_or_ambiguous_bounds(settings):
    with pytest.raises((ValidationError, SecurityError)):
        configuration.RuntimeSettings(**settings)


def test_stop_budget_accounts_for_several_database_transactions():
    with pytest.raises(ValidationError):
        configuration.RuntimeSettings(busy_seconds=5, stop_seconds=30)
    assert configuration.RuntimeSettings(busy_seconds=1).stop_seconds == 30


@pytest.mark.skipif(os.name != "nt", reason="Native protected configuration")
def test_activation_restart_revocation_and_explicit_new_version(tmp_path, authorities):
    collector = uuid4()
    scope = Scope((str(tmp_path),))
    token = "a" * 43
    with ProtectedState(tmp_path / "state", create=True) as state:
        config = configuration.activate(
            state,
            collector,
            "https://localhost",
            scope,
            token,
            (authorities[0] / "ca.pem").read_bytes(),
        )
        assert token.encode() not in state.read("config.json", 131072)
        assert token not in repr(config) and str(tmp_path) not in repr(config)
        loaded = configuration.load(state)
        assert loaded.config.credential_version == config.credential_version
        loaded.outbox.enqueue("heartbeat", heartbeat(collector), "stream", 0, {})
        claim = loaded.outbox.claim(datetime.now(UTC))
        assert claim is not None and loaded.outbox.suspend_auth(claim)
    with ProtectedState(tmp_path / "state") as state:
        loaded = configuration.load(state)
        assert loaded.outbox.auth_suspended()
        updated = configuration.activate(
            state,
            collector,
            "https://localhost",
            scope,
            "b" * 43,
            (authorities[0] / "ca.pem").read_bytes(),
        )
        assert updated.credential_version != config.credential_version
        assert not configuration.load(state).outbox.auth_suspended()


@pytest.mark.skipif(os.name != "nt", reason="Native protected configuration")
def test_config_replacement_crash_fails_closed_without_resuming_old_credentials(
    tmp_path,
    authorities,
    monkeypatch,
):
    with ProtectedState(tmp_path / "state", create=True) as state:
        collector = uuid4()
        ca = (authorities[0] / "ca.pem").read_bytes()
        scope = Scope((str(tmp_path),))
        configuration.activate(state, collector, "https://localhost", scope, "a" * 43, ca)
        original = state.write

        def crash(name, value):
            if name == "config.json":
                raise SecurityError("STATE_INVALID")
            original(name, value)

        monkeypatch.setattr(state, "write", crash)
        with pytest.raises(SecurityError, match="^STATE_INVALID$"):
            configuration.activate(state, collector, "https://localhost", scope, "b" * 43, ca)
        monkeypatch.setattr(state, "write", original)
        with pytest.raises(SecurityError, match="^CREDENTIAL_MISMATCH$"):
            configuration.load(state)
        assert Outbox(state.root / "outbox.sqlite3", collector).status().pending_count == 0


@pytest.mark.skipif(os.name != "nt", reason="Native protected configuration")
def test_invalid_config_duplicate_keys_and_changed_scope_are_fixed_code_failures(
    tmp_path, authorities
):
    with ProtectedState(tmp_path / "state", create=True) as state:
        collector = uuid4()
        scope = Scope((str(tmp_path),))
        configuration.activate(
            state,
            collector,
            "https://localhost",
            scope,
            "a" * 43,
            (authorities[0] / "ca.pem").read_bytes(),
        )
        original = state.read("config.json", 131072)
        corrupted = json.loads(original)
        corrupted["private_unexpected"] = "synthetic-secret"
        state.write("config.json", json.dumps(corrupted).encode())
        with pytest.raises(SecurityError, match="^CONFIG_INVALID$"):
            configuration.load(state)
        state.write("config.json", b'{"version":1,"version":1}')
        with pytest.raises(SecurityError, match="^CONFIG_INVALID$"):
            configuration.load(state)
        state.write("config.json", original)
        with pytest.raises(SecurityError, match="^SCOPE_CHANGED$"):
            configuration.activate(
                state,
                collector,
                "https://localhost",
                Scope((str(tmp_path / "different"),)),
                "b" * 43,
                (authorities[0] / "ca.pem").read_bytes(),
            )
