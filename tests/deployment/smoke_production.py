"""Disposable production-topology acceptance; never a production DNS bypass."""

import json
import secrets
import socket
import ssl
import subprocess
import tempfile
from datetime import UTC, datetime
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, HTTPSHandler, ProxyHandler, Request, build_opener

from deploy.scripts import lifecycle
from deploy.scripts.backup import create_backup, restore_backup
from deploy.scripts.commands import ROOT, Compose, run
from deploy.scripts.environment import ConfigError, parse_environment


def authenticate_runtime(
    values: dict[str, str], compose: Compose, root: Path, password: str
) -> None:
    bootstrap = """import sys
from packages.shared.database import make_engine
from packages.shared.settings import Settings
from apps.api.user_auth.bootstrap import bootstrap_admin
bootstrap_admin(make_engine(Settings().database_url), 'synthetic-admin', sys.stdin.read())
"""
    result = subprocess.run(
        [*compose.base, "exec", "-T", "api", "python", "-c", bootstrap],
        input=password,
        env=compose.environment,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, "Synthetic local bootstrap failed"
    jar = CookieJar()
    client = build_opener(
        ProxyHandler({}),
        HTTPSHandler(context=ssl.create_default_context(cafile=root / "ca.pem")),
        HTTPCookieProcessor(jar),
    )
    origin = values["APP_ORIGIN"]

    def request(path: str, body: object | None = None, headers: dict[str, str] | None = None):
        data = None if body is None else json.dumps(body).encode()
        req = Request(
            origin + path,
            data=data,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        resolver = socket.getaddrinfo
        # Only the disposable test process maps this synthetic DNS name. TLS SNI,
        # hostname checking and chain validation still use storage.example.test.
        socket.getaddrinfo = lambda name, *args, **kwargs: resolver(
            "127.0.0.1" if name == "storage.example.test" else name, *args, **kwargs
        )
        try:
            try:
                response = client.open(req, timeout=10)
            except HTTPError as failure:
                response = failure
            with response:
                return response.status, response.headers, response.read(32769)
        finally:
            socket.getaddrinfo = resolver

    assert request("/")[0] == 200
    for path in ("/api/v1/overview", "/api/v1/auth/me"):
        assert request(path)[0] == 401
    login = {"provider": "local", "username": "synthetic-admin", "password": password}
    status, headers, body = request("/api/v1/auth/login", login, {"Origin": origin})
    assert status == 200 and headers["Cache-Control"] == "no-store"
    actor = json.loads(body)
    assert set(actor) == {"id", "username", "roles"} and actor["roles"] == ["storage_admin"]
    cookies = headers.get_all("Set-Cookie")
    assert len(cookies) == 2 and all(
        "Secure" in value and "SameSite=lax" in value and "Domain=" not in value
        for value in cookies
    )
    assert "HttpOnly" in next(
        value for value in cookies if value.startswith("__Host-storage_session=")
    )
    assert request("/api/v1/auth/me")[0] == 200
    assert request("/api/v1/overview")[0] == 200
    csrf = next(cookie.value for cookie in jar if cookie.name == "__Host-storage_csrf")
    assert request("/api/v1/auth/logout", {}, {"Origin": origin})[0] == 403
    assert (
        request(
            "/api/v1/auth/logout", {}, {"Origin": "https://evil.example.test", "X-CSRF-Token": csrf}
        )[0]
        == 403
    )
    assert request("/api/v1/auth/me")[0] == 200
    stamp = datetime.now(UTC).isoformat()
    heartbeat = {
        "collector_id": actor["id"],
        "batch_id": "synthetic-user-is-not-collector",
        "schema_version": 1,
        "sent_at": stamp,
        "first_event_at": stamp,
        "last_event_at": stamp,
        "record_count": 1,
        "records": [
            {"occurred_at": stamp, "version": "synthetic", "cursor": "1", "lag_seconds": 0}
        ],
    }
    assert request("/api/v1/ingest/heartbeat", heartbeat)[0] == 401
    assert request("/api/v1/auth/logout", {}, {"Origin": origin, "X-CSRF-Token": csrf})[0] == 204
    assert request("/api/v1/overview")[0] == 401 and request("/api/v1/auth/me")[0] == 401
    assert request("/api/v1/auth/login", login, {"Origin": "https://evil.example.test"})[0] == 403


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
            "-addext",
            "basicConstraints=critical,CA:TRUE",
            "-addext",
            "keyUsage=critical,keyCertSign,cRLSign",
            "-addext",
            "subjectKeyIdentifier=hash",
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
    extension.write_text(
        "subjectAltName=DNS:storage.example.test\n"
        "basicConstraints=critical,CA:FALSE\n"
        "keyUsage=critical,digitalSignature,keyEncipherment\n"
        "extendedKeyUsage=serverAuth\n"
        "subjectKeyIdentifier=hash\n"
        "authorityKeyIdentifier=keyid,issuer\n"
    )
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


def verify_directory_ca_permissions(values: dict[str, str], root: Path) -> None:
    provider_file = root / "directory-auth.json"
    provider_file.write_text(
        json.dumps(
            {
                "version": 1,
                "origin": values["APP_ORIGIN"],
                "local_enabled": False,
                "ldap": {
                    "hostname": "directory.example.test",
                    "base_dn": "DC=example,DC=test",
                    "bind_dn": "CN=synthetic-service,DC=example,DC=test",
                    "bind_password": secrets.token_urlsafe(32),
                    "ca_file": "/run/secrets/storage-console/directory-ca.pem",
                    "group_roles": {"CN=synthetic-viewers,DC=example,DC=test": ["viewer"]},
                },
            }
        )
    )
    provider_file.chmod(0o600)
    run(
        [
            "docker",
            "run",
            "--rm",
            "--user",
            "0",
            "--mount",
            f"type=bind,src={root},dst=/fixture",
            "postgres:16-alpine",
            "chown",
            "10001:10001",
            "/fixture/directory-auth.json",
        ],
        timeout=120,
    )
    configured = values | {"AUTH_CONFIG_FILE": str(provider_file)}
    # Fixture CA is operator-owned600: UID10001 must reject it before any writer stop.
    try:
        lifecycle.verify_auth_configuration(configured)
    except ConfigError:
        pass
    else:
        raise AssertionError("Unreadable directory CA was accepted")
    (root / "ca.pem").chmod(0o644)
    lifecycle.verify_auth_configuration(configured)
    print("Directory CA unreadable600 denial / public644 API UID10001 admission: PASS")


def browser_acceptance(values: dict[str, str], compose: Compose, root: Path, password: str) -> None:
    evidence = root / "browser-evidence"
    evidence.mkdir(mode=0o700)
    image = "storage-smoke-browser:" + values["APP_RELEASE"]
    run(
        ["docker", "build", "-f", "tests/deployment/browser.Dockerfile", "-t", image, "."],
        timeout=900,
    )
    bootstrap = """import sys
from packages.shared.database import make_engine
from packages.shared.settings import Settings
from apps.api.user_auth.bootstrap import bootstrap_admin
bootstrap_admin(make_engine(Settings().database_url), 'synthetic-browser-admin', sys.stdin.read())
"""
    result = subprocess.run(
        [*compose.base, "exec", "-T", "api", "python", "-c", bootstrap],
        input=password,
        env=compose.environment,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, "Synthetic browser bootstrap failed"
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "--network",
            "host",
            "--shm-size",
            "256m",
            "--mount",
            f"type=bind,src={root / 'ca.pem'},dst=/fixture/ca.pem,readonly",
            "--mount",
            f"type=bind,src={evidence},dst=/evidence",
            image,
        ],
        input=json.dumps(
            {
                "origin": values["APP_ORIGIN"],
                "username": "synthetic-browser-admin",
                "password": password,
            }
        ),
        text=True,
        capture_output=True,
        timeout=180,
    )
    if result.returncode != 0:
        stage = result.stdout.strip()
        if stage.startswith("BROWSER_AUTH_ACCEPTANCE_FAILED:") and len(stage) < 100:
            print(stage)
        raise AssertionError("Real browser authentication acceptance failed")
    print(result.stdout.strip())


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="storage-production-smoke-"))
    state, backups = root / "state", root / "backups"
    for directory in (state, state / "postgres", state / "diagnostics", backups):
        directory.mkdir(mode=0o700)
    setup_tls(root)
    password = secrets.token_urlsafe(32)
    (root / "auth.json").write_text(
        json.dumps(
            {"version": 1, "origin": "https://storage.example.test:18443", "local_enabled": True}
        )
    )
    (root / "auth.json").chmod(0o600)
    revision = run(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).strip()
    project = "storage-smoke-" + secrets.token_hex(4)
    values = parse_environment(
        "\n".join(
            [
                "STORAGE_HOSTNAME=storage.example.test",
                "APP_ORIGIN=https://storage.example.test:18443",
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
                "AUTH_CONFIG_FILE=" + str(root / "auth.json"),
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
                "chown 10001:10001 /fixture/auth.json",
            ],
            timeout=120,
        )
        compose.call("build", "--quiet", "api", "web", timeout=900)
        lifecycle.verify_images(values)
        lifecycle.verify_auth_configuration(values)
        verify_directory_ca_permissions(values, root)
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
        authenticate_runtime(values, compose, root, password)
        browser_acceptance(values, compose, root, password)

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
