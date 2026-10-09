"""Bounded exception metadata; never serialize messages, locals or absolute paths."""

import json
import re

from .errors import SecurityError

_NAME = re.compile(r"[A-Za-z_][A-Za-z_0-9.]{0,95}\Z")
_TYPES = {"Exception", "RuntimeError", "ValueError", "TypeError", "OSError",
          "PermissionError", "FileNotFoundError", "MemoryError", "TimeoutError",
          "OperationalError", "DatabaseError", "IntegrityError", "ProgrammingError",
          "OutboxError", "CaptureError", "SecurityError"}
_STAGES = {"prepare", "runtime", "delivery", "heartbeat", "inventory", "usn", "cleanup"}


def detail(error: Exception, stage: str) -> str:
    if isinstance(error, RuntimeFailure):
        return error.detail
    frames = []
    trace = error.__traceback__
    while trace is not None:
        module = trace.tb_frame.f_globals.get("__name__", "")
        function = trace.tb_frame.f_code.co_name
        if (isinstance(module, str) and module.startswith("collectors.")
                and _NAME.fullmatch(module) and _NAME.fullmatch(function)):
            frames.append({"module": module, "function": function, "line": trace.tb_lineno})
        trace = trace.tb_next
    code = getattr(error, "sqlite_errorcode", None)
    safe_code = code if type(code) is int and 0 <= code <= 65535 else None
    name = type(error).__name__
    return json.dumps({"version": 1, "stage": stage if stage in _STAGES else "runtime",
                       "exception": name if name in _TYPES else "Exception",
                       "sqlite_errorcode": safe_code,
                       "frames": frames[-12:]}, separators=(",", ":"))


def valid_detail(value: str) -> bool:
    if len(value) > 8192:
        return False
    try:
        data = json.loads(value)
        if (set(data) != {"version", "stage", "exception", "sqlite_errorcode", "frames"}
                or data["version"] != 1 or data["stage"] not in _STAGES
                or data["exception"] not in _TYPES
                or (data["sqlite_errorcode"] is not None
                    and (type(data["sqlite_errorcode"]) is not int
                         or not 0 <= data["sqlite_errorcode"] <= 65535))
                or not isinstance(data["frames"], list) or len(data["frames"]) > 12):
            return False
        return all(set(frame) == {"module", "function", "line"}
                   and isinstance(frame["module"], str)
                   and frame["module"].startswith("collectors.")
                   and _NAME.fullmatch(frame["module"])
                   and isinstance(frame["function"], str) and _NAME.fullmatch(frame["function"])
                   and type(frame["line"]) is int and 0 < frame["line"] <= 100000
                   for frame in data["frames"])
    except (ValueError, TypeError, KeyError):
        return False


class RuntimeFailure(SecurityError):
    def __init__(self, code: str, error: Exception, stage: str) -> None:
        super().__init__(code)
        self.detail = detail(error, stage)
