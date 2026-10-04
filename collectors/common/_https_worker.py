"""Private isolated stdlib worker. No secrets in arguments, files or result output."""

from __future__ import annotations

import base64
import json
import os
import ssl
import sys
import threading
from datetime import UTC, datetime
from email.message import Message
from email.utils import parsedate_to_datetime
from http.client import HTTPException, HTTPMessage
from typing import IO
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: IO[bytes], code: int, msg: str, headers: HTTPMessage, newurl: str
    ) -> None:
        return None


def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def retry_after(value: str | None) -> float | None:
    if value is None or len(value) > 128:
        return None
    try:
        if value.isdecimal():
            return float(min(int(value), 300))
        stamp = parsedate_to_datetime(value)
        if stamp.tzinfo is None:
            return None
        return min(300.0, max(0.0, (stamp - datetime.now(UTC)).total_seconds()))
    except (ValueError, OverflowError, TypeError):
        return None


def outcome(
    kind: str, code: str | None = None, duplicate: bool | None = None, retry: float | None = None
) -> dict[str, object]:
    return {"kind": kind, "code": code, "duplicate": duplicate, "retry_after": retry}


def status_result(status: int, headers: Message[str, str]) -> dict[str, object]:
    if 300 <= status < 400:
        return outcome("quarantined", "REDIRECT")
    if status in (401, 403):
        return outcome("suspended", "AUTH_REQUIRED")
    if status == 429:
        return outcome("retry", "RATE_LIMITED", retry=retry_after(headers.get("Retry-After")))
    if status in (408, 425):
        return outcome("retry", "TIMEOUT")
    if 500 <= status <= 599:
        return outcome("retry", "SERVER_ERROR", retry=retry_after(headers.get("Retry-After")))
    if 400 <= status <= 499:
        return outcome("quarantined", "HTTP_REJECTED")
    return outcome("retry", "INVALID_RECEIPT")


def request(config: dict[str, object]) -> dict[str, object]:
    context = ssl.create_default_context(cadata=str(config["ca_data"]))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    opener = build_opener(ProxyHandler({}), NoRedirect(), HTTPSHandler(context=context))
    req = Request(
        str(config["url"]),
        data=base64.b64decode(str(config["body"]), validate=True),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": "Bearer " + str(config["token"]),
        },
        method="POST",
    )
    try:
        with opener.open(req, timeout=float(str(config["timeout"]))) as response:
            if response.status != 202:
                return status_result(response.status, response.headers)
            body = response.read(32769)
            if len(body) > 32768 or response.headers.get_content_type() != "application/json":
                return outcome("retry", "INVALID_RECEIPT")
            try:
                value = json.loads(body.decode("utf-8"), object_pairs_hook=unique)
            except (ValueError, UnicodeError):
                return outcome("retry", "INVALID_RECEIPT")
            if (
                not isinstance(value, dict)
                or set(value) != {"accepted", "duplicate"}
                or value["accepted"] is not True
                or type(value["duplicate"]) is not bool
            ):
                return outcome("retry", "INVALID_RECEIPT")
            return outcome("accepted", duplicate=value["duplicate"])
    except HTTPError as error:
        try:
            return status_result(error.code, error.headers)
        finally:
            error.close()
    except URLError as error:
        if isinstance(error.reason, ssl.SSLError):
            return outcome("retry", "TLS")
        return outcome("retry", "TIMEOUT" if isinstance(error.reason, TimeoutError) else "NETWORK")
    except ssl.SSLError:
        return outcome("retry", "TLS")
    except TimeoutError:
        return outcome("retry", "TIMEOUT")
    except (OSError, HTTPException):
        return outcome("retry", "NETWORK")


def main() -> None:
    timer: threading.Timer | None = None
    try:
        raw = sys.stdin.buffer.read(24 * 1024**2 + 1)
        if len(raw) > 24 * 1024**2:
            raise ValueError
        config = json.loads(raw)
        timer = threading.Timer(float(config["timeout"]), lambda: os._exit(70))
        timer.daemon = True
        timer.start()
        result = request(config)
    except Exception:
        result = outcome("retry", "NETWORK")
    finally:
        if timer is not None:
            timer.cancel()
    sys.stdout.write(json.dumps(result))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
