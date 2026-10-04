import json
import os

import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from packages.shared.auth.configuration import AuthConfigurationError
from packages.shared.settings import Settings

ORIGIN = "https://storage.example.test"


def test_unconfigured_runtime_aborts_before_readiness(ingest_setup):
    _, engine, *_ = ingest_setup
    with pytest.raises(AuthConfigurationError, match="^AUTH_CONFIG_INVALID$"):
        with TestClient(create_app(Settings(), engine)):
            pytest.fail("Runtime cannot start without explicit provider configuration")


@pytest.mark.skipif(os.name != "posix", reason="Private auth file is a POSIX runtime boundary")
def test_runtime_loads_private_provider_file(ingest_setup, tmp_path):
    _, engine, *_ = ingest_setup
    path = tmp_path / "auth.json"
    path.write_text(json.dumps({"version": 1, "origin": ORIGIN, "local_enabled": True}))
    path.chmod(0o600)
    app = create_app(Settings(app_origin=ORIGIN, auth_config_file=str(path)), engine)
    with TestClient(app, base_url=ORIGIN) as client:
        response = client.post(
            "/api/v1/auth/login",
            headers={"Origin": ORIGIN},
            json={"provider": "local", "username": "nonexistent", "password": "synthetic-password"},
        )
        assert response.status_code == 401 and response.json() == {"detail": "AUTH_FAILED"}
        assert app.state.user_auth.config.origin == ORIGIN


@pytest.mark.skipif(os.name != "posix", reason="Private auth file is a POSIX runtime boundary")
@pytest.mark.parametrize(
    "mode,contents",
    [
        (0o644, {}),
        (0o600, {"version": 1, "origin": "http://invalid.example.test", "local_enabled": True}),
    ],
)
def test_unsafe_runtime_auth_file_aborts_startup(ingest_setup, tmp_path, mode, contents):
    _, engine, *_ = ingest_setup
    path = tmp_path / "auth.json"
    path.write_text(json.dumps(contents))
    path.chmod(mode)
    app = create_app(Settings(app_origin=ORIGIN, auth_config_file=str(path)), engine)
    with pytest.raises(AuthConfigurationError, match="^AUTH_CONFIG_INVALID$"):
        with TestClient(app):
            pytest.fail("Unsafe provider configuration must never start")


def test_missing_requested_auth_file_aborts_startup(ingest_setup, tmp_path):
    _, engine, *_ = ingest_setup
    app = create_app(
        Settings(app_origin=ORIGIN, auth_config_file=str(tmp_path / "missing.json")), engine
    )
    with pytest.raises(AuthConfigurationError, match="^AUTH_CONFIG_INVALID$"):
        with TestClient(app):
            pytest.fail("Missing requested provider configuration must never start")


@pytest.mark.skipif(os.name != "posix", reason="Private auth file is a POSIX runtime boundary")
@pytest.mark.parametrize("origin", ["", "https://evil.example.test"])
def test_runtime_requires_origin_match_with_private_file(ingest_setup, tmp_path, origin):
    _, engine, *_ = ingest_setup
    path = tmp_path / "auth.json"
    path.write_text(json.dumps({"version": 1, "origin": ORIGIN, "local_enabled": True}))
    path.chmod(0o600)
    app = create_app(Settings(app_origin=origin, auth_config_file=str(path)), engine)
    with pytest.raises(AuthConfigurationError, match="^AUTH_CONFIG_INVALID$"):
        with TestClient(app):
            pytest.fail("Unmatched application origin must not start")
