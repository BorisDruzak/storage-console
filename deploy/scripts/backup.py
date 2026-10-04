"""Private, atomic PostgreSQL archives and explicit maintenance restoration."""

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from deploy.scripts.commands import Compose
from deploy.scripts.environment import ConfigError, load_environment
from deploy.scripts.lifecycle import deployment_lock


def private_path(path: Path, mode: int, *, directory: bool = False) -> None:
    info = path.lstat()
    correct_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not correct_type or (
        os.name == "posix"
        and (stat.S_IMODE(info.st_mode) != mode or info.st_uid not in {0, os.geteuid()})
    ):
        raise ConfigError("Backup должен находиться в приватном обычном файле/каталоге")


def postgres_command(
    compose: Compose, args: list[str], *, source: Path | None = None, target: Path | None = None
) -> None:
    with source.open("rb") if source else open(os.devnull, "rb") as incoming:
        with target.open("wb") if target else open(os.devnull, "wb") as outgoing:
            try:
                result = subprocess.run(
                    [*compose.base, "exec", "-T", "postgres", *args],
                    env=compose.environment,
                    stdin=incoming,
                    stdout=outgoing,
                    stderr=subprocess.DEVNULL,
                    timeout=900,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                raise ConfigError(
                    "PostgreSQL backup/restore недоступен или превысил время"
                ) from None
            if result.returncode:
                raise ConfigError("PostgreSQL backup/restore завершился с ошибкой")
            if target:
                outgoing.flush()
                os.fsync(outgoing.fileno())


def dump_database(compose: Compose, target: Path) -> None:
    postgres_command(
        compose,
        [
            "pg_dump",
            "--format=custom",
            "--schema=public",
            "--no-owner",
            "--no-acl",
            "--username",
            compose.values["POSTGRES_USER"],
            "--dbname",
            compose.values["POSTGRES_DB"],
        ],
        target=target,
    )


def check_archive(compose: Compose, dump: Path) -> None:
    postgres_command(compose, ["pg_restore", "--list"], source=dump)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def sync_directory(path: Path) -> None:
    if os.name == "posix":
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def create_backup(values: dict[str, str], compose: Compose) -> Path:
    root = Path(values["BACKUP_DIR"])
    private_path(root, 0o700, directory=True)
    temporary = Path(tempfile.mkdtemp(prefix=".partial-", dir=root))
    try:
        dump = temporary / "database.dump"
        with dump.open("xb"):
            pass
        dump.chmod(0o600)
        dump_database(compose, dump)
        check_archive(compose, dump)
        manifest = {
            "format": 1,
            "project": values["PROJECT_NAME"],
            "database": values["POSTGRES_DB"],
            "release": values["APP_RELEASE"],
            "sha256": digest(dump),
            "bytes": dump.stat().st_size,
        }
        metadata = temporary / "manifest.json"
        with metadata.open("x", encoding="utf-8") as stream:
            metadata.chmod(0o600)
            json.dump(manifest, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        destination = root / ("backup-" + uuid.uuid4().hex)
        sync_directory(temporary)
        temporary.rename(destination)
        sync_directory(root)
        return destination
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def validate_backup(values: dict[str, str], archive: Path) -> Path:
    root = Path(values["BACKUP_DIR"])
    private_path(root, 0o700, directory=True)
    if not archive.is_absolute() or archive.parent != root:
        raise ConfigError("Backup должен быть непосредственным каталогом BACKUP_DIR")
    private_path(archive, 0o700, directory=True)
    metadata, dump = archive / "manifest.json", archive / "database.dump"
    private_path(metadata, 0o600)
    private_path(dump, 0o600)
    if metadata.stat().st_size > 4096:
        raise ConfigError("Недопустимый manifest backup")
    manifest = json.loads(metadata.read_text(encoding="utf-8"))
    if (
        not isinstance(manifest, dict)
        or manifest.get("format") != 1
        or manifest.get("project") != values["PROJECT_NAME"]
        or manifest.get("database") != values["POSTGRES_DB"]
        or manifest.get("bytes") != dump.stat().st_size
        or manifest.get("sha256") != digest(dump)
    ):
        raise ConfigError("Проект/БД или контрольная сумма backup не совпадает")
    return dump


def restore_database(compose: Compose, dump: Path) -> None:
    temporary = Path(tempfile.mkdtemp(prefix=".restore-", dir=dump.parent))
    try:
        rendered, transaction = temporary / "archive.sql", temporary / "transaction.sql"
        for path in (rendered, transaction):
            path.touch(mode=0o600, exist_ok=False)
        # Render completely before touching the DB: truncated archives/disk-full fail closed.
        postgres_command(
            compose,
            [
                "pg_restore",
                "--file=-",
                "--schema=public",
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-acl",
                "--exit-on-error",
            ],
            source=dump,
            target=rendered,
        )
        with transaction.open("wb") as output, rendered.open("rb") as incoming:
            # The application owns the entire public schema. Newer migration objects must
            # disappear together with restored Alembic history, inside the same transaction.
            output.write(b"DROP SCHEMA IF EXISTS public CASCADE;\nCREATE SCHEMA public;\n")
            shutil.copyfileobj(incoming, output)
        postgres_command(
            compose,
            [
                "psql",
                "-X",
                "--single-transaction",
                "-v",
                "ON_ERROR_STOP=1",
                "--username",
                compose.values["POSTGRES_USER"],
                "--dbname",
                compose.values["POSTGRES_DB"],
            ],
            source=transaction,
        )
    finally:
        shutil.rmtree(temporary)


def restore_backup(
    values: dict[str, str], compose: Compose, archive: Path, confirmation: str
) -> None:
    if confirmation != values["PROJECT_NAME"] + "/" + values["POSTGRES_DB"]:
        raise ConfigError("Restore требует --confirm PROJECT_NAME/POSTGRES_DB")
    dump = validate_backup(values, archive)
    check_archive(compose, dump)
    compose.call("stop", "web", "api", "worker", timeout=60)
    safety = create_backup(values, compose)
    print("Backup перед restore сохранён:", safety, flush=True)
    restore_database(compose, dump)
    print("Restore выполнен; Web/API/worker остановлены. Проверьте совместимость release.")


def main() -> int:
    try:
        if len(sys.argv) < 3 or sys.argv[1] not in {"backup", "restore"}:
            raise ConfigError(
                "Использование: backup ENV либо restore ENV ARCHIVE --confirm PROJECT/DB"
            )
        values = load_environment(Path(sys.argv[2]))
        compose = Compose(values)
        if sys.argv[1] == "backup" and len(sys.argv) == 3:
            with deployment_lock(values):
                print("Backup сохранён:", create_backup(values, compose))
        elif sys.argv[1] == "restore" and len(sys.argv) == 6 and sys.argv[4] == "--confirm":
            with deployment_lock(values):
                restore_backup(values, compose, Path(sys.argv[3]), sys.argv[5])
        else:
            raise ConfigError("Недопустимые аргументы backup/restore")
        return 0
    except (ConfigError, ValueError, KeyError, TypeError, OSError):
        error = sys.exception()
        print(
            str(error) if isinstance(error, ConfigError) else "Ошибка backup/restore",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
