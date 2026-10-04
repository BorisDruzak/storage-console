"""Verified, deadline-bounded HTTPS delivery; secrets use child stdin only."""

import base64
import ipaddress
import json
import math
import re
import ssl
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from .outbox import Claim

_WORKER_PATH = Path(__file__).with_name("_https_worker.py").absolute()
_ROUTES = {
    "heartbeat": "heartbeat",
    "inventory": "inventory",
    "changes": "changes",
    "telemetry": "telemetry",
    "events": "events",
    "acl": "acl",
    "recovery": "recovery",
    "hygiene": "hygiene",
    "diagnostics": "diagnostic-bundles",
}
_RETRY_CODES = frozenset(
    {"NETWORK", "TLS", "TIMEOUT", "RATE_LIMITED", "SERVER_ERROR", "INVALID_RECEIPT"}
)
Kind = Literal["accepted", "retry", "suspended", "quarantined"]


class TransportError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class DeliveryOutcome:
    kind: Kind
    code: str | None = None
    duplicate: bool | None = None
    retry_after: float | None = None


def valid_outcome(value: DeliveryOutcome) -> bool:
    if not isinstance(value, DeliveryOutcome):
        return False
    if value.retry_after is not None and (
        type(value.retry_after) not in (int, float)
        or not math.isfinite(value.retry_after)
        or not 0 <= value.retry_after <= 300
    ):
        return False
    if value.kind == "accepted":
        return type(value.duplicate) is bool and value.code is None and value.retry_after is None
    if value.duplicate is not None:
        return False
    return (
        (value.kind == "retry" and value.code in _RETRY_CODES)
        or (value.kind == "suspended" and value.code == "AUTH_REQUIRED")
        or (value.kind == "quarantined" and value.code in {"HTTP_REJECTED", "REDIRECT"})
    )


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


class Transport:
    def __init__(
        self, origin: str, ca: Path, token: str, timeout: float = 15, *, collector_id: UUID
    ) -> None:
        try:
            if (
                not isinstance(origin, str)
                or not origin.isascii()
                or any(ord(char) < 33 or ord(char) == 127 for char in origin)
                or "?" in origin
                or "#" in origin
            ):
                raise ValueError
            parsed = urlsplit(origin)
            hostname = parsed.hostname or ""
            if (
                parsed.scheme != "https"
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in ("", "/")
                or not 1 <= (parsed.port or 443) <= 65535
                or parsed.port == 0
                or len(hostname) > 253
                or (hostname != "localhost" and "." not in hostname)
                or not all(
                    re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                    for label in hostname.split(".")
                )
            ):
                raise ValueError
            try:
                ipaddress.ip_address(hostname)
            except ValueError:
                pass
            else:
                raise ValueError
            if not isinstance(token, str) or re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is None:
                raise ValueError
            if (
                not isinstance(collector_id, UUID)
                or type(timeout) not in (int, float)
                or not math.isfinite(timeout)
                or not 0 < timeout <= 15
            ):
                raise ValueError
            with Path(ca).open("rb") as file:
                data = file.read(128 * 1024 + 1)
            if len(data) > 128 * 1024 or b"PRIVATE KEY" in data:
                raise ValueError
            ca_data = data.decode("ascii")
            context = ssl.create_default_context(cadata=ca_data)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.check_hostname = True
            context.verify_mode = ssl.CERT_REQUIRED
        except (ValueError, TypeError, OSError, UnicodeError):
            raise TransportError("INVALID_CONFIG") from None
        self.origin = "https://" + hostname + (":" + str(parsed.port) if parsed.port else "")
        self.collector_id = collector_id
        self._token = token
        self._ca_data = ca_data
        self._timeout = float(timeout)

    def send(self, claim: Claim) -> DeliveryOutcome:
        try:
            if (
                claim.domain not in _ROUTES
                or not isinstance(claim.body, bytes)
                or (not 0 < len(claim.body) <= 16 * 1024**2)
            ):
                raise ValueError
            body = json.loads(claim.body, object_pairs_hook=_unique)
            if (
                not isinstance(body, dict)
                or UUID(body["collector_id"]) != self.collector_id
                or body["batch_id"] != claim.batch_id
            ):
                raise ValueError
        except (ValueError, TypeError, KeyError, AttributeError):
            return DeliveryOutcome("quarantined", code="HTTP_REJECTED")
        payload = json.dumps(
            {
                "url": self.origin + "/api/v1/ingest/" + _ROUTES[claim.domain],
                "ca_data": self._ca_data,
                "token": self._token,
                "timeout": self._timeout,
                "body": base64.b64encode(claim.body).decode("ascii"),
            }
        ).encode()
        process: subprocess.Popen[bytes] | None = None
        started = time.monotonic()
        try:
            process = subprocess.Popen(
                [sys.executable, "-I", str(_WORKER_PATH)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            remaining = self._timeout - (time.monotonic() - started)
            output, _ = process.communicate(payload, timeout=max(0.001, remaining))
            if process.returncode == 70:
                return DeliveryOutcome("retry", code="TIMEOUT")
            if process.returncode != 0 or len(output) > 2048:
                return DeliveryOutcome("retry", code="NETWORK")
            value = json.loads(output, object_pairs_hook=_unique)
            if not isinstance(value, dict) or set(value) != {
                "kind",
                "code",
                "duplicate",
                "retry_after",
            }:
                raise ValueError
            if value["kind"] not in ("accepted", "retry", "suspended", "quarantined"):
                raise ValueError
            result = DeliveryOutcome(**value)
            return result if valid_outcome(result) else DeliveryOutcome("retry", code="NETWORK")
        except subprocess.TimeoutExpired:
            if process is not None:
                process.kill()
                process.communicate()
            return DeliveryOutcome("retry", code="TIMEOUT")
        except (OSError, ValueError, TypeError):
            return DeliveryOutcome("retry", code="NETWORK")
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate()
