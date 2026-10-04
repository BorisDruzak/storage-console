import hashlib
import os
import re
import shutil
import socket
import stat
from pathlib import Path

from deploy.scripts.commands import Compose, run
from deploy.scripts.environment import ConfigError


def check_machine(release: dict[str, str], cpu: int, memory: int, disk: int, ntp: bool) -> None:
    if release.get("ID") != "ubuntu" or release.get("VERSION_ID") != "24.04":
        raise ConfigError("Требуется Ubuntu24.04 LTS")
    if cpu < 4 or memory < 15 * 1024**3 or disk < 20 * 1024**3:
        raise ConfigError("Недостаточно ресурсов: требуются4 CPU,16GiB RAM и20GiB свободного места")
    if not ntp:
        raise ConfigError("Системное время не синхронизировано через NTP")


def check_ports(bindings: list[tuple[str, int]], owned: set[tuple[str, int]]) -> None:
    if len(set(bindings)) != len(bindings):
        raise ConfigError("HTTP и HTTPS используют один адрес/порт")
    for binding in bindings:
        with socket.socket() as probe:
            try:
                probe.bind(binding)
            except OSError:
                if binding not in owned:
                    raise ConfigError("Порт занят другим сервисом или адрес недоступен") from None


def check_file(path: Path, *, private: bool = False) -> None:
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or not os.access(path, os.R_OK):
            raise ConfigError("TLS/auth файл отсутствует, является ссылкой или недоступен")
        mode = stat.S_IMODE(info.st_mode)
        if private and mode != 0o600:
            raise ConfigError("Закрытый TLS-ключ должен иметь права0600")
    except OSError:
        raise ConfigError("TLS/auth файл недоступен") from None


def check_auth_file(path: Path) -> None:
    try:
        info = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != 10001
            or info.st_nlink != 1
            or not 1 <= info.st_size <= 32768
        ):
            raise ConfigError("Provider JSON должен быть обычным файлом0600 UID10001 до32KiB")
    except OSError:
        raise ConfigError("Provider JSON недоступен") from None


def check_tls(values: dict[str, str]) -> None:
    for key in ("TLS_CERT_FILE", "TLS_KEY_FILE", "TLS_CA_FILE"):
        check_file(Path(values[key]), private=key == "TLS_KEY_FILE")
    check_auth_file(Path(values["AUTH_CONFIG_FILE"]))
    if values.get("DIRECTORY_CA_FILE"):
        check_file(Path(values["DIRECTORY_CA_FILE"]))
    run(["openssl", "x509", "-in", values["TLS_CERT_FILE"], "-checkend", "604800", "-noout"])
    run(
        [
            "openssl",
            "verify",
            "-verify_hostname",
            values["STORAGE_HOSTNAME"],
            "-CAfile",
            values["TLS_CA_FILE"],
            "-untrusted",
            values["TLS_CERT_FILE"],
            values["TLS_CERT_FILE"],
        ]
    )
    certificate = run(["openssl", "x509", "-in", values["TLS_CERT_FILE"], "-pubkey", "-noout"])
    key = run(["openssl", "pkey", "-in", values["TLS_KEY_FILE"], "-pubout"])
    if hashlib.sha256(certificate.encode()).digest() != hashlib.sha256(key.encode()).digest():
        raise ConfigError("TLS-сертификат и ключ не совпадают")


def check_dns(values: dict[str, str]) -> None:
    answers = run(["getent", "ahostsv4", values["STORAGE_HOSTNAME"]], timeout=5)
    addresses = {line.split()[0] for line in answers.splitlines() if line.split()}
    local = set(run(["hostname", "-I"]).split()) | {"127.0.0.1"}
    if not addresses or not addresses & local:
        raise ConfigError("DNS hostname не указывает на эту ВМ")


def preflight(values: dict[str, str], compose: Compose) -> None:
    release = dict(
        line.split("=", 1)
        for line in Path("/etc/os-release").read_text().splitlines()
        if "=" in line
    )
    release = {key: value.strip('"') for key, value in release.items()}
    memory = next(
        int(line.split()[1]) * 1024
        for line in Path("/proc/meminfo").read_text().splitlines()
        if line.startswith("MemTotal:")
    )
    state = Path(values["STATE_DIR"])
    if not state.is_dir() or state.is_symlink():
        raise ConfigError("Подготовьте постоянный STATE_DIR согласно runbook")
    check_machine(
        release,
        os.cpu_count() or 0,
        memory,
        shutil.disk_usage(state).free,
        run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"]).strip() == "yes",
    )
    for directory in (state, state / "postgres", state / "diagnostics", Path(values["BACKUP_DIR"])):
        if not directory.is_dir() or directory.is_symlink():
            raise ConfigError("Постоянный каталог отсутствует или является ссылкой")
        if stat.S_IMODE(directory.stat().st_mode) & 0o022:
            raise ConfigError("Постоянные каталоги не должны быть доступны для записи группе/всем")
    if (state / "diagnostics").stat().st_uid != 10001:
        raise ConfigError("Каталог diagnostics должен принадлежать UID10001")
    version = run(["docker", "compose", "version", "--short"]).strip()
    match = re.match(r"v?(\d+)\.(\d+)", version)
    if not match or tuple(map(int, match.groups())) < (2, 20):
        raise ConfigError("Требуется Docker Compose>=2.20")
    run(["docker", "info", "--format", "{{.ServerVersion}}"])
    compose.call("config", "--quiet")
    check_dns(values)
    check_tls(values)
    bindings = [(values[key + "_BIND"], int(values[key + "_PORT"])) for key in ("HTTP", "HTTPS")]
    check_ports(bindings, compose.owned_ports())
