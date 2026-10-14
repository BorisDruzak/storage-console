"""Test-only installed-worker trace; never record exception text or frame locals."""

import json
import math
import sqlite3

from collectors.windows.diagnostics import detail, valid_detail
from collectors.windows.inventory import CODES

_CODES = CODES | {
    "NETWORK", "TLS", "TIMEOUT", "RATE_LIMITED", "SERVER_ERROR", "INVALID_RECEIPT",
    "AUTH_REQUIRED", "HTTP_REJECTED", "REDIRECT", "STATE_INVALID", "RUNTIME_FAILED",
    "STATE_UNAVAILABLE",
}


def _enum(value, choices):
    return value if value is None or isinstance(value, str) and value in choices else "UNKNOWN"


def safe_failure(error):
    try:
        value = detail(error, "runtime")
        if valid_detail(value):
            return json.loads(value)
    except Exception:
        pass
    return {"diagnostic_error": "UNAVAILABLE"}


def outcome_metadata(domain, underlying, effective):
    def metadata(value):
        read = value.get if isinstance(value, dict) else lambda key: getattr(value, key, None)
        retry, duplicate = read("retry_after"), read("duplicate")
        return {"kind": _enum(read("kind"), {"accepted", "retry", "suspended", "quarantined"}),
                "code": _enum(read("code"), _CODES),
                "duplicate": duplicate if type(duplicate) is bool else None,
                "retry_after": retry if type(retry) in (int, float)
                and math.isfinite(retry) and 0 <= retry <= 300 else None}
    return {"domain": _enum(domain, {"heartbeat", "inventory", "changes"}),
            "underlying": metadata(underlying), "effective": metadata(effective)}


def runtime_snapshot(runtime, path, failures, outcomes=()):
    """One bounded read-only queue attempt; never emit IDs, bodies or exception text."""
    try:
        return _runtime_snapshot(runtime, path, failures, outcomes)
    except Exception:
        return {"diagnostic_error": "UNAVAILABLE"}


def _runtime_snapshot(runtime, path, failures, outcomes):
    events = [{"kind": _enum(event.kind, {"heartbeat", "inventory", "usn", "delivery"}),
               "code": _enum(event.code, _CODES)} for event in runtime.events[-24:]]
    safe_details = [value if valid_detail(json.dumps(value))
                    else {"diagnostic_error": "UNAVAILABLE"} for value in failures[-24:]]
    try:
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.1)
        try:
            connection.execute("PRAGMA query_only=ON")
            row = connection.execute(
                "SELECT coalesce(sum(state='pending'),0), "
                "coalesce(sum(state='quarantined'),0) FROM batches"
            ).fetchone()
            queue = {"pending": row[0], "quarantined": row[1]}
        finally:
            connection.close()
    except Exception:
        queue = {"diagnostic_error": "UNAVAILABLE"}
    safe_outcomes = [outcome_metadata(value.get("domain"), value.get("underlying", {}),
                                     value.get("effective", {}))
                     for value in list(outcomes)[-24:]]
    return {"events": events, "failures": safe_details,
            "outcomes": safe_outcomes, "queue": queue}


def trace_program(destination):
    return """
import json
import runpy
import sys
from collections import deque
from pathlib import Path

events = deque(maxlen=24)
modules = {
    'collectors.common.outbox', 'collectors.windows.producer',
    'collectors.windows.native', 'collectors.windows.inventory',
    'collectors.windows.security',
}

def trace(frame, event, argument):
    try:
        if frame.f_globals.get('__name__') not in modules:
            return None
        frame.f_trace_lines = False
        if event == 'exception':
            error = argument[1]
            name = type(error).__name__
            if name not in {'StopIteration', 'GeneratorExit'} and not (
                name == 'OutboxError' and getattr(error, 'code', None) == 'CAPACITY'
            ):
                item = {'type': name[:64], 'function': frame.f_code.co_name[:64],
                        'line': frame.f_lineno}
                for key in ('errno', 'winerror', 'sqlite_errorcode'):
                    value = getattr(error, key, None)
                    if type(value) is int and -(2**31) <= value < 2**32:
                        item[key] = value
                events.append(item)
    except Exception:
        pass
    return trace

sys.settrace(trace)
try:
    runpy.run_module('collectors.windows._capture_worker',
                     run_name='__main__', alter_sys=True)
finally:
    sys.settrace(None)
    try:
        Path(DESTINATION).write_text(json.dumps(list(events)), encoding='utf-8')
    except Exception:
        pass
""".replace("DESTINATION", json.dumps(str(destination)))


def read_trace(destination):
    try:
        if destination.stat().st_size > 8192:
            return {"diagnostic_error": "OVERSIZED"}
        return json.loads(destination.read_text(encoding="utf-8"))
    except Exception as error:
        return {"diagnostic_error": type(error).__name__}
