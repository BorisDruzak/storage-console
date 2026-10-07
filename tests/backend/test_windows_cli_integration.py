import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_windows_cli_native import installed_cli as installed_cli
from test_windows_runtime_native import installed_python as installed_python

from packages.shared.models.core import collector_heartbeats, filesystem_objects, volumes
from tests.deployment.collector_delivery import serving_ingest

pytestmark = [
    pytest.mark.skipif(os.name != "nt", reason="Installed Windows pilot CLI"),
    pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Disposable PostgreSQL required"),
]


def test_installed_cli_management_native_inventory_strict_https_postgres_and_replay(
    authenticated_setup, tmp_path, installed_cli,
):
    client, engine, *_ = authenticated_setup
    origin = "https://storage.example.test"
    headers = {"Origin": origin, "X-CSRF-Token": client.cookies.get("__Host-storage_csrf")}
    source = client.post("/api/v1/sources", headers=headers, json={
        "source_type": "FILESERVER", "hostname": "synthetic-cli-fileserver",
        "instance_id": str(uuid4()),
    })
    assert source.status_code == 201
    source_id = source.json()["id"]
    credential = client.post(
        f"/api/v1/sources/{source_id}/collectors", headers=headers,
        json={"collector_type": "WINDOWS"},
    )
    assert credential.status_code == 201
    identity, token = credential.json()["id"], credential.json()["token"]
    assert client.get(f"/api/v1/sources/{source_id}").json()["freshness"]["state"] == "UNKNOWN"
    data = tmp_path / "data"
    data.mkdir()
    for index in range(3):
        (data / f"synthetic-{index}.txt").write_text("fixture", encoding="utf-8")
    state = tmp_path / "state"
    cli = installed_cli
    assert cli.is_file()

    def command(*args, key=None):
        result = subprocess.run(
            [str(cli), *args, "--state", str(state)], input=key, text=True,
            encoding="utf-8", env=dict(os.environ, PYTHONUTF8="1"),
            capture_output=True, timeout=90, cwd=tmp_path,
        )
        assert token not in result.stdout + result.stderr
        assert str(data) not in result.stdout + result.stderr
        assert result.returncode == 0, "INSTALLED_CLI_FAILED: " + result.stdout + result.stderr
        return result.stdout

    with serving_ingest(client.app, tmp_path / "tls") as (https_origin, ca):
        command("activate", "--collector-id", identity, "--origin", https_origin,
                "--ca", str(ca), "--root", str(data), "--key-stdin", key=token + "\n")
        assert token not in (state / "config.json").read_text()
        before = (state / "outbox.sqlite3").read_bytes()
        assert "В очереди: 0" in command("status")
        assert before == (state / "outbox.sqlite3").read_bytes()
        for _ in range(2):
            assert "Инвентаризация завершена" in command("inventory-once")
        assert "completed=True" in command("status")
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(volumes)) == 1
        assert connection.scalar(select(func.count()).select_from(filesystem_objects)) == 4
        assert connection.scalar(select(func.count()).select_from(collector_heartbeats)) == 2
    assert client.get(f"/api/v1/sources/{source_id}").json()["freshness"]["state"] == "HEALTHY"
    assert client.get("/api/v1/overview").json()["counts"]["filesystem_objects"] == 4
    volume = client.get(f"/api/v1/volumes?source_id={source_id}").json()["items"][0]
    assert volume["filesystem"] == "NTFS" and volume["unique_identity"].startswith("volume:")
    assert client.get(f"/api/v1/shares?source_id={source_id}").json()["total"] == 0
    assert Path(cli).name == "storage-collector.exe"
    assert json.loads((state / "config.json").read_bytes())["encrypted_token"] != token
