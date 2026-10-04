from uuid import uuid4

import pytest
from sqlalchemy import insert

from packages.shared.auth.passwords import hash_password
from packages.shared.auth.providers import LocalProvider, credentials_valid
from packages.shared.models.security import roles, user_roles, users


@pytest.mark.parametrize(
    "enabled,provider,codes,success",
    [
        (True, "local", ["storage_admin"], True),
        (False, "local", ["storage_admin"], False),
        (True, "ldap", ["storage_admin"], False),
        (True, "local", ["viewer"], False),
        (True, "local", ["storage_admin", "unexpected"], False),
    ],
)
def test_local_accepts_only_enabled_explicit_break_glass_admin(
    ingest_setup, enabled, provider, codes, success
):
    _, engine, *_ = ingest_setup
    user = uuid4()
    password = "synthetic-long-password"
    with engine.begin() as connection:
        connection.execute(
            insert(users).values(
                id=user,
                username="emergency",
                auth_provider=provider,
                password_hash=hash_password(password),
                enabled=enabled,
            )
        )
        for code in codes:
            role = uuid4()
            connection.execute(insert(roles).values(id=role, code=code))
            connection.execute(insert(user_roles).values(user_id=user, role_id=role))
    auth = LocalProvider(engine)
    result = auth.authenticate("EMERGENCY", password)
    assert (result is not None) is success
    if result:
        assert result.subject == str(user)
        assert result.roles == frozenset({"storage_admin"})
        assert result.provider == "local"
    assert auth.authenticate("emergency", "wrong") is None
    assert auth.authenticate("unknown", password) is None
    assert auth.authenticate("emergency", "") is None
    assert auth.authenticate("emergency", "\ud800") is None


def test_unicode_account_names_supported_and_control_characters_rejected():
    assert credentials_valid("оператор", "synthetic-password")
    assert not credentials_valid("alice\x00", "synthetic-password")
    assert not credentials_valid(" alice", "synthetic-password")
