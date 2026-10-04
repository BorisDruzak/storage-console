"""Disposable production-topology acceptance; never a production DNS bypass."""

import os
import secrets
import subprocess
import tempfile
from pathlib import Path

from deploy.scripts import lifecycle
from deploy.scripts.backup import create_backup, restore_backup
from deploy.scripts.commands import ROOT, Compose, run
from deploy.scripts.environment import parse_environment


def setup_tls(root: Path) -> None:
    common = ["openssl", "req", "-newkey", "rsa:2048", "-nodes"]
    run(
        [
            *common,
            "-x509",
            "-days",
            "30",
            "-subj",
            "/CN=Synthetic Smoke CA",
            "-keyout",
            str(root / "ca.key"),
            "-out",
            str(root / "ca.pem"),
        ]
    )
    run(
        [
            *common,
            "-subj",
            "/CN=storage.example.test",
            "-keyout",
            str(root / "key.pem"),
            "-out",
            str(root / "leaf.csr"),
        ]
    )
    extension = root / "extensions.cnf"
    extension.write_text("subjectAltName=DNS:storage.example.test\n")
    run(
        [
            "openssl",
            "x509",
            "-req",
            "-in",
            str(root / "leaf.csr"),
            "-CA",
            str(root / "ca.pem"),
            "-CAkey",
            str(root / "ca.key"),
            "-CAcreateserial",
            "-days",
            "30",
            "-extfile",
            str(extension),
            "-out",
            str(root / "cert.pem"),
        ]
    )
    for file in root.iterdir():
        if file.is_file():
            file.chmod(0o600)


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="storage-production-smoke-"))
    state, backups = root / "state", root / "backups"
    for directory in (state, state / "postgres", state / "diagnostics", backups):
        directory.mkdir(mode=0o700)
    setup_tls(root)
    password = secrets.token_hex(16)
    hashed = subprocess.run(
        ["openssl", "passwd", "-6", "-stdin"],
        input=password,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    (root / "users.htpasswd").write_text("operator:" + hashed + "\n")
    (root / "users.htpasswd").chmod(0o640)
    revision = run(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).strip()
    project = "storage-smoke-" + secrets.token_hex(4)
    values = parse_environment(
        "\n".join(
            [
                "STORAGE_HOSTNAME=storage.example.test",
                "PROJECT_NAME=" + project,
                "APP_RELEASE=" + revision,
                "API_IMAGE=storage-smoke-api:" + revision,
                "WEB_IMAGE=storage-smoke-web:" + revision,
                "POSTGRES_DB=storage_smoke",
                "POSTGRES_USER=storage_smoke",
                "POSTGRES_PASSWORD=" + secrets.token_hex(32),
                "STATE_DIR=" + str(state),
                "BACKUP_DIR=" + str(backups),
                "TLS_CERT_FILE=" + str(root / "cert.pem"),
                "TLS_KEY_FILE=" + str(root / "key.pem"),
                "TLS_CA_FILE=" + str(root / "ca.pem"),
                "AUTH_FILE=" + str(root / "users.htpasswd"),
                "HTTP_BIND=127.0.0.1",
                "HTTP_PORT=18083",
                "HTTPS_BIND=127.0.0.1",
                "HTTPS_PORT=18443",
            ]
        )
    )
    compose = Compose(values)
    try:
        run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "-v",
                str(root) + ":/fixture",
                "postgres:16-alpine",
                "sh",
                "-c",
                "chown 70:70 /fixture/state/postgres; "
                "chown 10001:10001 /fixture/state/diagnostics; "
                f"chown {os.getuid()}:101 /fixture/users.htpasswd",
            ],
            timeout=120,
        )
        compose.call("build", "--quiet", "api", "web", timeout=900)
        lifecycle.verify_images(values)
        compose.call("up", "-d", "--wait", "--wait-timeout", "180", timeout=240)
        original_run = lifecycle.run

        def synthetic_client(args: list[str], **kwargs: object) -> str:
            if args[0] == "curl":
                args = [
                    *args,
                    "--noproxy",
                    "*",
                    "--resolve",
                    "storage.example.test:18083:127.0.0.1",
                    "--resolve",
                    "storage.example.test:18443:127.0.0.1",
                ]
            return original_run(args, **kwargs)  # type: ignore[arg-type]

        # Only this disposable test client resolves the synthetic hostname locally.
        # Production preflight/lifecycle code is unchanged.
        lifecycle.run = synthetic_client
        lifecycle.healthcheck(values, compose)
        config = (
            f'user = "operator:{password}"\n'
            f'cacert = "{root / "ca.pem"}"\n'
            'resolve = "storage.example.test:18443:127.0.0.1"\n'
            'noproxy = "*"\n'
        )
        for route in ("/", "/api/v1/overview"):
            result = subprocess.run(
                [
                    "curl",
                    "--config",
                    "-",
                    "--silent",
                    "--show-error",
                    "--fail",
                    "--max-time",
                    "10",
                    "https://storage.example.test:18443" + route,
                ],
                input=config,
                text=True,
                capture_output=True,
                check=False,
            )
            assert result.returncode == 0, "Authenticated HTTPS failed"

        def sql(statement: str) -> str:
            return compose.call(
                "exec",
                "-T",
                "postgres",
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-At",
                "-U",
                "storage_smoke",
                "-d",
                "storage_smoke",
                "-c",
                statement,
            ).strip()

        # Only disposable smoke owns this table; production migrations are unchanged.
        sql(
            "create table synthetic_backup_marker (value text); "
            "insert into synthetic_backup_marker values ('before-backup')"
        )
        with lifecycle.deployment_lock(values):
            archive = create_backup(values, compose)
            sql("update synthetic_backup_marker set value='after-backup'")
            restore_backup(values, compose, archive, project + "/storage_smoke")
            assert sql("select value from synthetic_backup_marker") == "before-backup"
            compose.call(
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "migrate",
                "alembic",
                "downgrade",
                "0002",
                timeout=180,
            )
            older_archive = create_backup(values, compose)
            compose.call(
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "migrate",
                "alembic",
                "upgrade",
                "head",
                timeout=180,
            )
            restore_backup(values, compose, older_archive, project + "/storage_smoke")
            assert sql("select version_num from alembic_version") == "0002"
            assert sql("select to_regclass('public.collector_events')") == ""
            compose.call(
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "migrate",
                "alembic",
                "upgrade",
                "head",
                timeout=180,
            )
        compose.call(
            "up",
            "-d",
            "--no-deps",
            "--wait",
            "--wait-timeout",
            "180",
            "api",
            "worker",
            "web",
            timeout=240,
        )
        lifecycle.healthcheck(values, compose)
        print("Production topology/strict TLS/auth/backup/restore: PASS")
    finally:
        compose.call("down", timeout=90)
        # No database dumps/certificates are uploaded as CI artifacts.
        # A private temporary fixture remains until the disposable runner is removed.


if __name__ == "__main__":
    main()
