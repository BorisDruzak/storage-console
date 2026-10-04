import os
import socket
from pathlib import Path

import pytest

from deploy.scripts.environment import ConfigError, load_environment, parse_environment
from deploy.scripts.preflight import check_machine, check_ports


def valid_text():
    return "\n".join(
        [
            "STORAGE_HOSTNAME=storage.example.test",
            "APP_RELEASE=" + "a" * 40,
            "API_IMAGE=storage-api:" + "a" * 40,
            "WEB_IMAGE=storage-web:" + "a" * 40,
            "POSTGRES_USER=storage_console",
            "POSTGRES_DB=storage_console",
            "POSTGRES_PASSWORD=" + "b" * 64,
            "STATE_DIR=/var/lib/storage-control-plane",
            "BACKUP_DIR=/var/backups/storage-control-plane",
            "TLS_CERT_FILE=/etc/storage-control-plane/fullchain.pem",
            "TLS_KEY_FILE=/etc/storage-control-plane/privkey.pem",
            "TLS_CA_FILE=/etc/storage-control-plane/ca.pem",
            "AUTH_FILE=/etc/storage-control-plane/users.htpasswd",
        ]
    )


def test_configuration_keeps_values_as_data_and_supplies_defaults():
    data = parse_environment(valid_text())
    assert data["HTTPS_PORT"] == "443"
    assert data["PROJECT_NAME"] == "storage-control-plane"
    assert data["POSTGRES_PASSWORD"] == "b" * 64


@pytest.mark.parametrize(
    "extra",
    [
        "UNKNOWN_OPTION=value",
        "STORAGE_HOSTNAME=bad;hostname",
        "HTTPS_PORT=70000",
        "HTTP_BIND=hostname.example.test",
        "APP_RELEASE=main",
        "POSTGRES_PASSWORD=$(touch /tmp/should-not-execute)",
        "TLS_KEY_FILE=relative/key.pem",
        "STATE_DIR=/",
        "export SENTRY_DSN=ignored",
        "SENTRY_DSN=value\x00hidden",
        "SENTRY_DSN=https://secret@[invalid",
    ],
)
def test_bad_configuration_is_rejected_without_echoing_values(extra):
    key = extra.partition("=")[0]
    lines = valid_text().splitlines()
    if any(line.startswith(key + "=") for line in lines):
        lines = [extra if line.startswith(key + "=") else line for line in lines]
    else:
        lines.append(extra)
    with pytest.raises(ConfigError) as failure:
        parse_environment("\n".join(lines))
    assert extra not in str(failure.value)
    assert "b" * 64 not in str(failure.value)


def test_duplicate_key_is_rejected_even_if_equal():
    with pytest.raises(ConfigError):
        parse_environment(valid_text() + "\nPOSTGRES_DB=storage_console")


@pytest.mark.skipif(os.name != "posix", reason="Production POSIX file permissions")
def test_environment_requires_private_regular_file(tmp_path):
    path = tmp_path / "production.env"
    path.write_text(valid_text())
    path.chmod(0o644)
    with pytest.raises(ConfigError):
        load_environment(path)
    path.chmod(0o600)
    assert load_environment(path)["STORAGE_HOSTNAME"] == "storage.example.test"
    link = tmp_path / "linked.env"
    link.symlink_to(path)
    with pytest.raises(ConfigError):
        load_environment(link)


@pytest.mark.parametrize(
    "os_version,cpu,memory,disk,ntp",
    [
        ("22.04", 4, 16, 30, True),
        ("24.04", 1, 16, 30, True),
        ("24.04", 4, 4, 30, True),
        ("24.04", 4, 16, 1, True),
        ("24.04", 4, 16, 30, False),
    ],
)
def test_machine_preflight_rejects_unsuitable_host(os_version, cpu, memory, disk, ntp):
    with pytest.raises(ConfigError):
        check_machine(
            {"ID": "ubuntu", "VERSION_ID": os_version},
            cpu,
            memory * 1024**3,
            disk * 1024**3,
            ntp,
        )


def test_recommended_machine_accepts_usable_memory_after_kernel_reservation():
    check_machine({"ID": "ubuntu", "VERSION_ID": "24.04"}, 4, 15 * 1024**3, 30 * 1024**3, True)


def test_occupied_port_is_allowed_only_for_current_project():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        with pytest.raises(ConfigError):
            check_ports([("127.0.0.1", port)], set())
        check_ports([("127.0.0.1", port)], {("127.0.0.1", port)})


def test_paths_with_spaces_are_preserved_as_data():
    text = valid_text().replace(
        "STATE_DIR=/var/lib/storage-control-plane", "STATE_DIR=/var/lib/storage console"
    )
    assert Path(parse_environment(text)["STATE_DIR"]).name == "storage console"


def test_failed_migration_keeps_api_and_worker_stopped(monkeypatch):
    import contextlib

    from deploy.scripts import lifecycle

    calls = []

    class FakeCompose:
        def call(self, *args, **kwargs):
            calls.append(args)
            if args[0] == "run":
                raise ConfigError("synthetic migration failure")
            return ""

    monkeypatch.setattr(lifecycle, "preflight", lambda *args: None)
    monkeypatch.setattr(lifecycle, "verify_images", lambda *args: None)
    monkeypatch.setattr(lifecycle, "verify_source", lambda *args: None)
    monkeypatch.setattr(lifecycle, "deployment_lock", lambda *args: contextlib.nullcontext())
    with pytest.raises(ConfigError):
        lifecycle.deploy(parse_environment(valid_text()), FakeCompose())
    assert ("stop", "web", "api", "worker") in calls
    migration = next(i for i, call in enumerate(calls) if call[0] == "run")
    stop = next(i for i, call in enumerate(calls) if call[0] == "stop")
    assert stop < migration
    assert not any(call[0] == "up" and "api" in call for call in calls)


@pytest.mark.parametrize("content", ["", "operator:plaintext", "operator:{PLAIN}password"])
def test_operator_gateway_rejects_empty_or_unhashed_credentials(tmp_path, content):
    from deploy.scripts.preflight import check_auth

    path = tmp_path / "users.htpasswd"
    path.write_text(content)
    with pytest.raises(ConfigError):
        check_auth(path)


@pytest.mark.parametrize("wrong_identity", ["image", "revision", None])
def test_healthcheck_verifies_running_release_identity(monkeypatch, wrong_identity):
    from deploy.scripts import lifecycle

    class HealthyCompose:
        def services(self):
            return [
                {"Service": name, "ID": name, "State": "running", "Health": "healthy"}
                for name in ("postgres", "api", "worker", "web")
            ]

    def synthetic_run(args, **kwargs):
        if args[0] == "docker":
            if args[1] == "image":
                return "sha256:expected-image"
            image = "sha256:old-image" if wrong_identity == "image" else "sha256:expected-image"
            revision = "c" * 40 if wrong_identity == "revision" else values["APP_RELEASE"]
            return image + " " + revision
        if "--fail" in args:
            return '{"status":"ok"}'
        if "-w" in args:
            return "401"
        return "HTTP/1.1 308 Permanent Redirect\nLocation: https://storage.example.test/\n"

    monkeypatch.setattr(lifecycle, "run", synthetic_run)
    values = parse_environment(valid_text())
    if wrong_identity:
        with pytest.raises(ConfigError):
            lifecycle.healthcheck(values, HealthyCompose())
    else:
        lifecycle.healthcheck(values, HealthyCompose())
