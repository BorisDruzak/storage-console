import pytest


def test_local_admin_password_hash_is_argon2id_and_salted():
    from packages.shared.auth.passwords import hash_password, verify_password

    password = "synthetic-admin-passphrase-for-tests"
    first, second = hash_password(password), hash_password(password)
    assert first.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert first != second
    assert password not in first
    assert verify_password(first, password)
    assert not verify_password(first, "synthetic-wrong-passphrase")


@pytest.mark.parametrize("password", ["", "short", "a" * 1025, "я" * 513, "\ud800" * 20])
def test_bootstrap_rejects_short_or_oversized_password_without_echo(password):
    from packages.shared.auth.passwords import PasswordPolicyError, hash_password

    with pytest.raises(PasswordPolicyError) as error:
        hash_password(password)
    assert str(error.value) == "AUTH_PASSWORD_POLICY"


@pytest.mark.parametrize(
    "encoded",
    ["", "plaintext", "$argon2id$malformed", "$argon2id$v=19$m=999999999,t=3,p=4$bad$bad"],
)
def test_malformed_or_unbounded_hash_fails_closed(encoded):
    from packages.shared.auth.passwords import verify_password

    assert not verify_password(encoded, "synthetic-admin-passphrase-for-tests")


def test_unencodable_candidate_fails_without_verification_exception():
    from packages.shared.auth.passwords import verify_password

    assert not verify_password("$argon2id$malformed", "\ud800")
