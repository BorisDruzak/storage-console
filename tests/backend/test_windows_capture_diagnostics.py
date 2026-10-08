"""Late root errors must survive ordinary probes without leaking their text."""

import json
import subprocess
import sys

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
