"""Strict operator configuration: data, never shell code or dotenv expansion."""

import ipaddress
import os
import re
import stat
from pathlib import Path
from urllib.parse import urlsplit

DEFAULTS = {
    "PROJECT_NAME": "storage-control-plane",
    "POSTGRES_USER": "storage_console",
    "POSTGRES_DB": "storage_console",
    "HTTP_BIND": "0.0.0.0",
    "HTTPS_BIND": "0.0.0.0",
    "HTTP_PORT": "80",
    "HTTPS_PORT": "443",
    "SENTRY_DSN": "",
}
REQUIRED = {
    "STORAGE_HOSTNAME",
    "APP_RELEASE",
    "API_IMAGE",
    "WEB_IMAGE",
    "POSTGRES_PASSWORD",
    "STATE_DIR",
    "BACKUP_DIR",
    "TLS_CERT_FILE",
    "TLS_KEY_FILE",
    "TLS_CA_FILE",
    "AUTH_FILE",
}
PATHS = {"STATE_DIR", "BACKUP_DIR", "TLS_CERT_FILE", "TLS_KEY_FILE", "TLS_CA_FILE", "AUTH_FILE"}


class ConfigError(Exception):
    """Safe operator diagnostic which never includes configuration values."""


def parse_environment(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or key not in REQUIRED | DEFAULTS.keys() or key in values:
            raise ConfigError("Недопустимый или повторяющийся параметр конфигурации")
        if len(value) > 2048 or any(ord(char) < 32 or char in "$`" for char in value):
            raise ConfigError("Недопустимые символы в конфигурации")
        if value != value.strip() or "CHANGE_ME" in value:
            raise ConfigError("Не заполнен параметр конфигурации")
        values[key] = value
    if REQUIRED - values.keys() or any(not values[key] for key in REQUIRED):
        raise ConfigError("Отсутствует обязательный параметр конфигурации")
    result = DEFAULTS | values
    hostname = result["STORAGE_HOSTNAME"]
    if (
        len(hostname) > 253
        or "." not in hostname
        or any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in hostname.split(".")
        )
    ):
        raise ConfigError("STORAGE_HOSTNAME должен быть DNS-именем")
    if not re.fullmatch(r"[a-f0-9]{40}", result["APP_RELEASE"]):
        raise ConfigError("APP_RELEASE должен содержать полный Git SHA")
    for key in ("API_IMAGE", "WEB_IMAGE"):
        image = result[key]
        if not re.fullmatch(r"[a-z0-9][a-z0-9./:_@-]{0,255}", image) or not (
            image.endswith(":" + result["APP_RELEASE"])
            or re.search(r"@sha256:[a-f0-9]{64}$", image)
        ):
            raise ConfigError("Образы должны иметь release-тег или неизменяемый digest")
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", result["PROJECT_NAME"]):
        raise ConfigError("Недопустимый PROJECT_NAME")
    for key in ("POSTGRES_USER", "POSTGRES_DB"):
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", result[key]):
            raise ConfigError("Недопустимый идентификатор PostgreSQL")
    if not re.fullmatch(r"[a-f0-9]{64}", result["POSTGRES_PASSWORD"]):
        raise ConfigError("POSTGRES_PASSWORD должен быть случайным hex-значением из 64 символов")
    for key in ("HTTP_PORT", "HTTPS_PORT"):
        if not result[key].isdigit() or not 1 <= int(result[key]) <= 65535:
            raise ConfigError("Недопустимый порт")
    for key in ("HTTP_BIND", "HTTPS_BIND"):
        try:
            ipaddress.IPv4Address(result[key])
        except ValueError:
            raise ConfigError("Адрес bind должен быть IPv4") from None
    for key in PATHS:
        path = Path(result[key])
        # Pure POSIX syntax also makes configuration tests portable on Windows.
        if not result[key].startswith("/") or result[key] == "/" or ".." in path.parts:
            raise ConfigError("Пути должны быть абсолютными и не содержать родительских переходов")
    if result["STATE_DIR"] == result["BACKUP_DIR"]:
        raise ConfigError("Каталоги данных и резервных копий должны различаться")
    if result["SENTRY_DSN"]:
        try:
            parsed = urlsplit(result["SENTRY_DSN"])
        except ValueError:
            raise ConfigError("Недопустимый SENTRY_DSN") from None
        if parsed.scheme != "https" or not parsed.hostname:
            raise ConfigError("SENTRY_DSN должен использовать HTTPS")
    return result


def load_environment(path: Path) -> dict[str, str]:
    if not path.is_absolute():
        raise ConfigError("Укажите абсолютный путь к production.env")
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
                raise ConfigError("production.env должен быть обычным файлом с правами0600")
            if hasattr(os, "geteuid") and info.st_uid not in {0, os.geteuid()}:
                raise ConfigError("Неподходящий владелец production.env")
            text = stream.read(65537)
            if len(text) > 65536:
                raise ConfigError("production.env превышает допустимый размер")
    except (OSError, UnicodeError):
        raise ConfigError("Не удалось безопасно прочитать production.env") from None
    return parse_environment(text)
