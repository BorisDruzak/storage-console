from uuid import uuid4

import pytest
from sqlalchemy import insert, select, update

from apps.api.user_auth.bootstrap import BootstrapError, bootstrap_admin, main
from apps.api.user_auth.identities import bind_subject
from apps.api.user_auth.sessions import SessionStore
from packages.shared.auth.providers import LocalProvider
from packages.shared.models.security import audit_log, users


def test_bootstrap_create_rotate_and_revoke_all_previous_sessions(ingest_setup):
    _, engine, *_ = ingest_setup
    first, second = "synthetic-first-password", "synthetic-second-password"
    user = bootstrap_admin(engine, "EMERGENCY", first)
    provider, store = LocalProvider(engine), SessionStore(engine)
    subject = provider.authenticate("emergency", first)
    assert subject.subject == str(user)
    assert bind_subject(engine, subject) == user
    assert store.issue(user) is None
    old = store.issue(user, credential_tag=subject.credential_tag)
    assert bootstrap_admin(engine, "emergency", second) == user
    assert store.resolve(old.token) is None
    assert store.issue(user, credential_tag=subject.credential_tag) is None
    assert bind_subject(engine, subject) is None
    assert provider.authenticate("emergency", first) is None
    fresh = provider.authenticate("emergency", second)
    assert store.issue(user, credential_tag=fresh.credential_tag) is not None
    with engine.connect() as connection:
        row = connection.execute(select(users).where(users.c.id == user)).one()
        assert row.password_hash.startswith("$argon2id$")
        assert first not in str(row) and second not in str(row)
        assert [
            action
            for action in connection.scalars(select(audit_log.c.action))
            if "bootstrap" in action
        ] == ["auth.bootstrap_create", "auth.bootstrap_rotate"]


def test_rotation_preserves_disabled_status_and_rejects_directory_collision(ingest_setup):
    _, engine, *_ = ingest_setup
    user = bootstrap_admin(engine, "emergency", "synthetic-long-password")
    with engine.begin() as connection:
        connection.execute(update(users).where(users.c.id == user).values(enabled=False))
        connection.execute(
            insert(users).values(id=uuid4(), username="directory", auth_provider="ldap")
        )
    bootstrap_admin(engine, "emergency", "synthetic-new-password")
    with engine.connect() as connection:
        assert connection.scalar(select(users.c.enabled).where(users.c.id == user)) is False
    with pytest.raises(BootstrapError, match="^AUTH_BOOTSTRAP_FAILED$"):
        bootstrap_admin(engine, "directory", "synthetic-new-password")


def test_cli_requires_terminal_and_privileged_runtime_without_reading_password(monkeypatch, capsys):
    monkeypatch.setattr("apps.api.user_auth.bootstrap._interactive_operator", lambda: False)
    monkeypatch.setattr(
        "apps.api.user_auth.bootstrap.getpass", lambda *a: pytest.fail("password read")
    )
    assert main(["--username", "emergency"]) == 1
    assert capsys.readouterr().err.strip() == "AUTH_BOOTSTRAP_INTERACTIVE_OPERATOR_REQUIRED"


def test_cli_password_confirmation_failure_does_not_open_database(monkeypatch, capsys):
    monkeypatch.setattr("apps.api.user_auth.bootstrap._interactive_operator", lambda: True)
    passwords = iter(["synthetic-long-password", "different-long-password"])
    monkeypatch.setattr("apps.api.user_auth.bootstrap.getpass", lambda *a: next(passwords))
    monkeypatch.setattr(
        "apps.api.user_auth.bootstrap.make_engine", lambda *a: pytest.fail("database opened")
    )
    assert main(["--username", "emergency"]) == 1
    output = capsys.readouterr()
    assert output.err.strip() == "AUTH_BOOTSTRAP_FAILED"
    assert "synthetic" not in output.err


def test_cli_argument_errors_never_echo_accidentally_supplied_password(capsys):
    with pytest.raises(SystemExit) as caught:
        main(["--username", "emergency", "--password", "synthetic-secret"])
    assert caught.value.code == 2
    assert "synthetic-secret" not in capsys.readouterr().err


def test_cli_success_uses_hidden_confirmation_and_generic_result(ingest_setup, monkeypatch, capsys):
    _, engine, *_ = ingest_setup
    monkeypatch.setattr("apps.api.user_auth.bootstrap._interactive_operator", lambda: True)
    monkeypatch.setattr(
        "apps.api.user_auth.bootstrap.getpass", lambda *a: "synthetic-very-long-password"
    )
    monkeypatch.setattr("apps.api.user_auth.bootstrap.make_engine", lambda *a: engine)
    assert main(["--username", "emergency"]) == 0
    output = capsys.readouterr()
    assert output.out.strip() == "AUTH_BOOTSTRAPPED" and output.err == ""
    assert (
        LocalProvider(engine).authenticate("emergency", "synthetic-very-long-password") is not None
    )


def test_cli_configuration_error_is_value_free_without_opening_database(monkeypatch, capsys):
    monkeypatch.setattr("apps.api.user_auth.bootstrap._interactive_operator", lambda: True)
    monkeypatch.setattr(
        "apps.api.user_auth.bootstrap.getpass", lambda *a: "synthetic-long-password"
    )

    def invalid_config():
        raise ValueError("synthetic-config-secret")

    monkeypatch.setattr("apps.api.user_auth.bootstrap.Settings", invalid_config)
    monkeypatch.setattr(
        "apps.api.user_auth.bootstrap.make_engine", lambda *a: pytest.fail("database opened")
    )
    assert main(["--username", "emergency"]) == 1
    assert capsys.readouterr().err.strip() == "AUTH_BOOTSTRAP_FAILED"
