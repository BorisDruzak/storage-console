"""Disposable GitHub Windows runner only: PostgreSQL for native SCM acceptance."""

import os
import secrets
import subprocess
import sys
from pathlib import Path

import psycopg
from psycopg import sql
from sqlalchemy import URL


def main() -> None:
    if os.name != "nt" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("DISPOSABLE_WINDOWS_RUNNER_REQUIRED")
    # Runner image provides a stopped/disabled PostgreSQL >=16 service. Its
    # documented bootstrap account is disposable; create our own random account.
    command = (
        "$ErrorActionPreference='Stop'; "
        "$svc=Get-Service 'postgresql-x64-*'; "
        "if (@($svc).Count -ne 1) {throw 'DISPOSABLE_POSTGRES_REQUIRED'}; "
    )
    if "--stop" in sys.argv:
        command += "Stop-Service $svc.Name; Set-Service $svc.Name -StartupType Disabled"
    else:
        command += "Set-Service $svc.Name -StartupType Manual; Start-Service $svc.Name"
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, timeout=60,
    )
    if result.returncode:
        raise RuntimeError("DISPOSABLE_POSTGRES_SERVICE_FAILED")
    if "--stop" in sys.argv:
        return
    name, password = "storage_console_scm_test", secrets.token_urlsafe(32)
    with psycopg.connect(dbname="postgres", user="postgres", password="root",
                         host="127.0.0.1", connect_timeout=5, autocommit=True) as connection:
        if connection.info.server_version < 160000:
            raise RuntimeError("POSTGRES_16_REQUIRED")
        connection.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
            sql.Identifier(name), sql.Literal(password),
        ))
        connection.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(
            sql.Identifier(name), sql.Identifier(name),
        ))
    url = URL.create(
        "postgresql+psycopg", username=name, password=password,
        host="127.0.0.1", port=5432, database=name,
    ).render_as_string(hide_password=False)
    print("::add-mask::" + password, flush=True)
    print("::add-mask::" + url, flush=True)
    with Path(os.environ["GITHUB_ENV"]).open("a", encoding="utf-8") as stream:
        stream.write("TEST_DATABASE_URL=" + url + "\n")
    print("Disposable PostgreSQL ready; isolated native acceptance enabled")


if __name__ == "__main__":
    main()
