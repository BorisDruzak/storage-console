import json
import os
from pathlib import Path

import pytest

from packages.shared.auth.configuration import (
    AuthConfigurationError,
    load_auth_config,
    parse_auth_config,
)


def directory_config():
    return {
        "version": 1,
        "origin": "https://storage.example.test",
        "local_enabled": True,
        "ldap": {
            "hostname": "ad.example.test",
            "base_dn": "DC=example,DC=test",
            "bind_dn": "CN=reader,DC=example,DC=test",
            "bind_password": "synthetic-service-secret",
            "ca_file": "/run/secrets/directory-ca.pem",
            "group_roles": {"CN=readers,DC=example,DC=test": ["viewer"]},
        },
    }


def test_valid_configuration_has_bounded_timeouts_and_redacts_password():
    config = parse_auth_config(directory_config())
    assert config.origin == "https://storage.example.test"
    assert config.ldap is not None
    assert config.ldap.timeout_seconds == 5
    assert config.ldap.group_roles["cn=readers,dc=example,dc=test"] == frozenset({"viewer"})
    assert "synthetic-service-secret" not in repr(config)


@pytest.mark.parametrize(
    "origin",
    [
        "http://storage.example.test",
        "https://user:secret@x.test",
        "https://storage.example.test/path",
        "https://storage.example.test?x=1",
        "https://storage.example.test#x",
        "https://192.0.2.1",
        "https://x.test:0",
    ],
)
def test_unsafe_origins_rejected(origin):
    with pytest.raises(AuthConfigurationError, match="^AUTH_CONFIG_INVALID$"):
        parse_auth_config(directory_config() | {"origin": origin})


@pytest.mark.parametrize(
    "patch",
    [
        {"hostname": "ldap://ad.example.test"},
        {"hostname": "192.0.2.1"},
        {"ca_file": "relative.pem"},
        {"timeout_seconds": 0},
        {"timeout_seconds": 11},
        {"timeout_seconds": True},
        {"bind_password": ""},
        {"bind_password": "\ud800"},
        {"group_roles": {}},
        {"group_roles": {"CN=group,DC=test": ["Domain Admins"]}},
        {"group_roles": {"CN=group,DC=test": []}},
        {"allow_insecure": True},
    ],
)
def test_unsafe_directory_configuration_rejected_without_secret(patch):
    data = directory_config()
    data["ldap"] |= patch
    with pytest.raises(AuthConfigurationError) as caught:
        parse_auth_config(data)
    assert str(caught.value) == "AUTH_CONFIG_INVALID"
    assert "synthetic-service-secret" not in str(caught.value)


def test_local_provider_requires_explicit_boolean_and_at_least_one_provider():
    with pytest.raises(AuthConfigurationError):
        parse_auth_config(
            {"version": 1, "origin": "https://storage.example.test", "local_enabled": "true"}
        )
    with pytest.raises(AuthConfigurationError):
        parse_auth_config(
            {"version": 1, "origin": "https://storage.example.test", "local_enabled": False}
        )


@pytest.mark.skipif(os.name != "posix", reason="Production private file ownership is POSIX")
def test_private_file_modes_links_duplicates_and_size_fail_closed(tmp_path):
    path = tmp_path / "auth.json"
    path.write_text(json.dumps(directory_config()), encoding="utf-8")
    path.chmod(0o600)
    assert load_auth_config(path).local_enabled is True
    path.chmod(0o644)
    with pytest.raises(AuthConfigurationError):
        load_auth_config(path)
    path.chmod(0o600)
    link = tmp_path / "link.json"
    link.symlink_to(path)
    with pytest.raises(AuthConfigurationError):
        load_auth_config(link)
    hard_link = tmp_path / "hard.json"
    os.link(path, hard_link)
    with pytest.raises(AuthConfigurationError):
        load_auth_config(path)
    hard_link.unlink()
    path.write_text('{"version":1,"version":1}', encoding="utf-8")
    with pytest.raises(AuthConfigurationError):
        load_auth_config(path)
    path.write_bytes(b" " * 32769)
    with pytest.raises(AuthConfigurationError):
        load_auth_config(path)
    with pytest.raises(AuthConfigurationError):
        load_auth_config(Path("relative.json"))
