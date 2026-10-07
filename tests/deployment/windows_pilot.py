"""Installed Windows CLI against a fresh disposable central stack, private stdin only.

Input: origin (https://localhost:port), userOrigin (disposable canonical origin),
CA path, installed CLI path, username/password.
Output: synthetic source ID and counts for browser/DB acceptance; no private metadata.
"""

import json
import os
import ssl
import subprocess
import sys
import tempfile
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, HTTPSHandler, ProxyHandler, Request, build_opener
from uuid import uuid4


def main() -> None:
    config = json.load(sys.stdin)
    origin = config["origin"]
    if os.name != "nt" or urlsplit(origin).hostname != "localhost":
        raise ValueError("DISPOSABLE_WINDOWS_LOCALHOST_REQUIRED")
    jar = CookieJar()
    client = build_opener(
        ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context(cafile=config["ca"])),
        HTTPCookieProcessor(jar),
    )

    def request(path: str, body: object | None = None) -> dict[str, object]:
        csrf = next(
            (cookie.value for cookie in jar if cookie.name == "__Host-storage_csrf"), "",
        ) or ""
        with client.open(Request(
            origin + path, data=None if body is None else json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json", "Origin": config["userOrigin"],
                "X-CSRF-Token": csrf,
            },
        ), timeout=15) as response:
            return json.loads(response.read())  # type: ignore[no-any-return]

    request("/api/v1/auth/login", {
        "provider": "local", "username": config["username"], "password": config["password"],
    })
    source = request("/api/v1/sources", {
        "source_type": "FILESERVER", "hostname": "synthetic-live-fileserver",
        "instance_id": str(uuid4()),
    })
    source_id = str(source["id"])
    credential = request(f"/api/v1/sources/{source_id}/collectors", {"collector_type": "WINDOWS"})
    token = str(credential["token"])
    assert request(f"/api/v1/sources/{source_id}")["freshness"]["state"] == "UNKNOWN"  # type: ignore[index]
    with tempfile.TemporaryDirectory(prefix="storage-windows-pilot-") as temporary:
        root = Path(temporary)
        data, state = root / "data", root / "state"
        data.mkdir()
        for index in range(3):
            (data / f"synthetic-{index}.txt").write_text("fixture", encoding="utf-8")

        def command(*args: str, key: str | None = None) -> None:
            result = subprocess.run(
                [config["cli"], *args, "--state", str(state)], input=key,
                capture_output=True, timeout=120, text=True, encoding="utf-8",
                env=dict(os.environ, PYTHONUTF8="1"), cwd=root,
            )
            assert token not in result.stdout + result.stderr
            assert result.returncode == 0, "INSTALLED_CLI_COMMAND_FAILED"

        command("activate", "--collector-id", str(credential["id"]), "--origin", origin,
                "--ca", config["ca"], "--root", str(data), "--key-stdin", key=token + "\n")
        command("status")
        for _ in range(2):
            command("inventory-once", "--scan-seconds", "30", "--settle-seconds", "30")
        command("status")
        assert token not in (state / "config.json").read_text()
    counts = request("/api/v1/overview")["counts"]
    assert counts["sources"] == 1 and counts["volumes"] == 1  # type: ignore[index]
    assert counts["filesystem_objects"] == 4  # type: ignore[index]
    print(json.dumps({"sourceId": source_id, "expectedObjects": 4, "replay": "PASS"}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("WINDOWS_PILOT_ACCEPTANCE_FAILED", file=sys.stderr)
        raise SystemExit(1) from None
