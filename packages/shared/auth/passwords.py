import hashlib

from argon2 import PasswordHasher, extract_parameters
from argon2.exceptions import InvalidHashError, VerificationError
from argon2.low_level import Type

_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, type=Type.ID)


class PasswordPolicyError(ValueError):
    pass


def password_version(encoded: str) -> str:
    """Opaque, non-credential tag for detecting rotation after verification."""
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    try:
        size = len(password.encode("utf-8"))
    except UnicodeError:
        raise PasswordPolicyError("AUTH_PASSWORD_POLICY") from None
    if len(password) < 16 or size > 1024:
        raise PasswordPolicyError("AUTH_PASSWORD_POLICY")
    return _hasher.hash(password)


def verify_password(encoded: str, password: str) -> bool:
    try:
        if not password or len(password.encode("utf-8")) > 1024 or len(encoded) > 512:
            return False
        parameters = extract_parameters(encoded)
        # Bound work before native verification, even for damaged persisted hashes.
        if (
            parameters.type is not Type.ID
            or parameters.version != 19
            or not 1 <= parameters.time_cost <= 3
            or not 1 <= parameters.parallelism <= 4
            or not 16384 <= parameters.memory_cost <= 65536
            or not 16 <= parameters.salt_len <= 32
            or not 16 <= parameters.hash_len <= 64
        ):
            return False
        return _hasher.verify(encoded, password)
    except (InvalidHashError, VerificationError, UnicodeError):
        return False
