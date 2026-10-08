"""Test-only installed-worker trace; never record exception text or frame locals."""

import json


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
