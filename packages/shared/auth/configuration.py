"""Private provider configuration. Validation errors never contain input values."""

import ipaddress
import json
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from urllib.parse import urlsplit

ROLES = frozenset({"storage_admin", "storage_operator", "auditor", "analyst", "viewer"})
_MAX_BYTES = 32768


class AuthConfigurationError(ValueError):
    def __init__(self) -> None:
        super().__init__("AUTH_CONFIG_INVALID")


@dataclass(frozen=True)
class DirectoryConfig:
    hostname: str
    base_dn: str
    bind_dn: str
    bind_password: str = field(repr=False)
    ca_file: str
    group_roles: Mapping[str, frozenset[str]]
    timeout_seconds: int = 5


@dataclass(frozen=True)
class AuthConfig:
    origin: str
    local_enabled: bool
    ldap: DirectoryConfig | None = None


def _text(value: object, limit: int) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise AuthConfigurationError()
    try:
        if len(value.encode("utf-8")) > limit:
            raise AuthConfigurationError()
    except UnicodeError:
        raise AuthConfigurationError() from None
    return value


def _hostname(value: object) -> str:
    name = _text(value, 253).lower()
    try:
        ipaddress.ip_address(name)
    except ValueError:
        pass
    else:
        raise AuthConfigurationError()
    labels = name.split(".")
    if len(labels) < 2 or any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels
    ):
        raise AuthConfigurationError()
    return name


def _object(value: object, required: set[str], optional: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise AuthConfigurationError()
    if not required <= value.keys() or value.keys() - required - optional:
        raise AuthConfigurationError()
    return dict(value)


def _origin(value: object) -> str:
    origin = _text(value, 300)
    try:
        url = urlsplit(origin)
        host = _hostname(url.hostname)
        port = url.port
        if (
            url.scheme != "https"
            or url.username is not None
            or url.password is not None
            or url.path
            or url.query
            or url.fragment
            or port is not None
            and not 1 <= port <= 65535
        ):
            raise AuthConfigurationError()
        canonical = f"https://{host}" + (f":{port}" if port is not None and port != 443 else "")
        if origin != canonical:
            raise AuthConfigurationError()
        return canonical
    except ValueError:
        raise AuthConfigurationError() from None


def _directory(value: object) -> DirectoryConfig:
    data = _object(
        value,
        {"hostname", "base_dn", "bind_dn", "bind_password", "ca_file", "group_roles"},
        {"timeout_seconds"},
    )
    ca_file = _text(data["ca_file"], 1024)
    ca_path = PurePosixPath(ca_file)
    if not ca_path.is_absolute() or ".." in ca_path.parts or "\n" in ca_file:
        raise AuthConfigurationError()
    timeout = data.get("timeout_seconds", 5)
    if type(timeout) is not int or not 1 <= timeout <= 10:
        raise AuthConfigurationError()
    groups = data["group_roles"]
    if not isinstance(groups, dict) or not 1 <= len(groups) <= 32:
        raise AuthConfigurationError()
    mapping: dict[str, frozenset[str]] = {}
    for dn, roles in groups.items():
        key = _text(dn, 2048).casefold()
        if (
            key in mapping
            or "=" not in key
            or not isinstance(roles, list)
            or not 1 <= len(roles) <= 5
        ):
            raise AuthConfigurationError()
        if any(not isinstance(role, str) or role not in ROLES for role in roles):
            raise AuthConfigurationError()
        mapping[key] = frozenset(roles)
    base_dn = _text(data["base_dn"], 2048)
    bind_dn = _text(data["bind_dn"], 2048)
    if "=" not in base_dn or "=" not in bind_dn:
        raise AuthConfigurationError()
    return DirectoryConfig(
        _hostname(data["hostname"]),
        base_dn,
        bind_dn,
        _text(data["bind_password"], 1024),
        ca_file,
        MappingProxyType(mapping),
        timeout,
    )


def parse_auth_config(value: object) -> AuthConfig:
    data = _object(value, {"version", "origin", "local_enabled"}, {"ldap"})
    if type(data["version"]) is not int or data["version"] != 1:
        raise AuthConfigurationError()
    local_enabled = data["local_enabled"]
    if not isinstance(local_enabled, bool):
        raise AuthConfigurationError()
    directory = _directory(data["ldap"]) if "ldap" in data else None
    if not local_enabled and directory is None:
        raise AuthConfigurationError()
    return AuthConfig(_origin(data["origin"]), local_enabled, directory)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise AuthConfigurationError()
        result[key] = value
    return result


def load_auth_config(path: Path) -> AuthConfig:
    if os.name != "posix" or not path.is_absolute():
        raise AuthConfigurationError()
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as source:
            info = os.fstat(source.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != os.geteuid()
                or info.st_nlink != 1
                or info.st_size > _MAX_BYTES
            ):
                raise AuthConfigurationError()
            contents = source.read(_MAX_BYTES + 1)
            if len(contents) > _MAX_BYTES:
                raise AuthConfigurationError()
        return parse_auth_config(
            json.loads(contents.decode("utf-8"), object_pairs_hook=_unique_object)
        )
    except (OSError, UnicodeError, ValueError, RecursionError):
        raise AuthConfigurationError() from None
