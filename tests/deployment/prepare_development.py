"""Create a fresh disposable HTTPS Compose fixture; never a default user account."""

import argparse
import json
import secrets
import sys
import tempfile
from pathlib import Path

from deploy.scripts.commands import run
from tests.deployment.smoke_production import setup_tls


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--http-port", type=int, default=8080)
    parser.add_argument("--https-port", type=int, default=8443)
    arguments = parser.parse_args()
    if (
        not all(1024 <= port <= 65535 for port in (arguments.http_port, arguments.https_port))
        or arguments.http_port == arguments.https_port
    ):
        raise ValueError("DEVELOPMENT_PORTS_INVALID")
    origin = f"https://storage.example.test:{arguments.https_port}"
    root = Path(tempfile.mkdtemp(prefix="storage-development-"))
    setup_tls(root)
    (root / "auth.json").write_text(
        json.dumps({"version": 1, "origin": origin, "local_enabled": True}) + "\n"
    )
    (root / "auth.json").chmod(0o600)
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
            "/fixture/auth.json",
        ],
        timeout=120,
    )
    environment = root / "development.env"
    environment.touch(mode=0o600)
    environment.write_text(
        "\n".join(
            [
                "POSTGRES_PASSWORD=" + secrets.token_hex(32),
                "STORAGE_HOSTNAME=storage.example.test",
                "APP_ORIGIN=" + origin,
                "AUTH_CONFIG_FILE=" + str(root / "auth.json"),
                "TLS_CERT_FILE=" + str(root / "cert.pem"),
                "TLS_KEY_FILE=" + str(root / "key.pem"),
                "TLS_CA_FILE=" + str(root / "ca.pem"),
                "WEB_PORT=" + str(arguments.http_port),
                "HTTPS_PORT=" + str(arguments.https_port),
            ]
        )
        + "\n"
    )
    print(environment)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("DEVELOPMENT_FIXTURE_FAILED", file=sys.stderr)
        raise SystemExit(1) from None
