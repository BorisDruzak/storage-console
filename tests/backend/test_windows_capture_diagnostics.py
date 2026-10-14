"""Late root errors must survive ordinary probes without leaking their text."""

import json
import subprocess
import sys
from contextlib import closing
from types import SimpleNamespace

from windows_capture_diagnostics import trace_program


def test_root_error_survives_probe_noise_without_changing_worker_output(tmp_path):
    destination = tmp_path / "codes.json"
    # Exercise real interpreter exception events and a real SQLite error. The
    # synthetic module models handled sidecar probes, not an installed worker.
    prefix = """
import runpy
import sqlite3
import sys
scope = {'__name__': 'collectors.common.outbox', 'sqlite3': sqlite3, 'sys': sys}
exec('''def probe():
    for _ in range(100):
        try:
            raise FileNotFoundError(2, 'synthetic-private-error-text')
        except FileNotFoundError:
            pass
    try:
        sqlite3.connect(':memory:').execute('synthetic_private_sql')
    except sqlite3.Error:
        pass
    sys.stdout.buffer.write(b'unchanged')
''', scope)
runpy.run_module = lambda *args, **kwargs: scope['probe']()
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", prefix + trace_program(destination)],
        capture_output=True, timeout=10, cwd=tmp_path,
    )
    assert result.returncode == 0 and result.stdout == b"unchanged" and not result.stderr
    raw = destination.read_bytes()
    events = json.loads(raw)
    assert len(raw) <= 8192 and 1 <= len(events) <= 24
    assert any(event.get("sqlite_errorcode") == 1 for event in events)
    assert all(set(event) <= {
        "type", "function", "line", "errno", "winerror", "sqlite_errorcode",
    } for event in events)
    assert b"synthetic-private-error-text" not in raw and b"synthetic_private_sql" not in raw


def test_runtime_snapshot_is_bounded_and_excludes_private_values(tmp_path):
    import sqlite3

    from windows_capture_diagnostics import outcome_metadata, runtime_snapshot, safe_failure

    from collectors.common.transport import DeliveryOutcome
    from collectors.windows.diagnostics import RuntimeFailure
    from collectors.windows.runtime import RuntimeEvent

    path = tmp_path / "synthetic-private-path.sqlite3"
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE batches(state TEXT, body BLOB)")
        connection.executemany("INSERT INTO batches VALUES (?, ?)", [
            ("pending", b"synthetic-private-body"), ("quarantined", b"private-token"),
        ])
        connection.commit()
    events = [RuntimeEvent("heartbeat", "USN_BOOTSTRAP", 1, 1)] * 100
    events.append(RuntimeEvent("synthetic-private-kind", "synthetic-private-code"))
    failure = safe_failure(RuntimeFailure(
        "STATE_INVALID", OSError("synthetic-private-error"), "delivery",
    ))
    outcome = outcome_metadata("changes", DeliveryOutcome("accepted", duplicate=True),
                               DeliveryOutcome("retry", code="NETWORK"))
    result = runtime_snapshot(SimpleNamespace(events=events), path, [failure], [outcome] * 100)
    raw = json.dumps(result)
    assert "synthetic-private" not in raw and "private-token" not in raw
    assert len(result["events"]) == len(result["outcomes"]) == 24
    assert result["queue"] == {"pending": 1, "quarantined": 1}
    assert result["failures"][0]["stage"] == "delivery"
    assert result["outcomes"][-1]["underlying"]["kind"] == "accepted"
    assert result["outcomes"][-1]["effective"]["code"] == "NETWORK"


def test_runtime_snapshot_unavailable_does_not_create_state_or_leak_error(tmp_path):
    from windows_capture_diagnostics import runtime_snapshot

    path = tmp_path / "missing-private-state.sqlite3"
    result = runtime_snapshot(SimpleNamespace(events=[]), path, [{"password": "private-token"}],
                              [{"body": "private-token"}])
    assert not path.exists()
    assert result["queue"] == {"diagnostic_error": "UNAVAILABLE"}
    assert result["failures"] == [{"diagnostic_error": "UNAVAILABLE"}]
    assert "private-token" not in json.dumps(result)
    assert runtime_snapshot(SimpleNamespace(events=[object()]), path, []) == {
        "diagnostic_error": "UNAVAILABLE",
    }
