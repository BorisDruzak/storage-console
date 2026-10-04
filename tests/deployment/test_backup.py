import json
import os
from pathlib import Path

import pytest

from deploy.scripts.environment import ConfigError


def values(tmp_path):
    directory = tmp_path / "backups"
    directory.mkdir(mode=0o700)
    return {
        "BACKUP_DIR": str(directory),
        "PROJECT_NAME": "synthetic-project",
        "POSTGRES_DB": "synthetic_database",
        "POSTGRES_USER": "synthetic_user",
        "APP_RELEASE": "a" * 40,
    }


def test_backup_is_atomic_private_and_verified(tmp_path, monkeypatch):
    from deploy.scripts import backup

    config = values(tmp_path)

    def dump(compose, target):
        target.write_bytes(b"PGDMP synthetic consistent snapshot")
        if os.name == "posix":
            assert target.stat().st_mode & 0o777 == 0o600

    monkeypatch.setattr(backup, "dump_database", dump)
    monkeypatch.setattr(backup, "check_archive", lambda *args: None)
    archive = backup.create_backup(config, object())
    assert backup.validate_backup(config, archive) == archive / "database.dump"
    assert json.loads((archive / "manifest.json").read_text())["release"] == "a" * 40
    assert not list(Path(config["BACKUP_DIR"]).glob(".partial-*"))
    if os.name == "posix":
        assert archive.stat().st_mode & 0o777 == 0o700
        assert (archive / "manifest.json").stat().st_mode & 0o777 == 0o600


def test_failed_backup_is_never_promoted(tmp_path, monkeypatch):
    from deploy.scripts import backup

    config = values(tmp_path)

    def failed_dump(compose, target):
        target.write_bytes(b"PGDMP truncated")
        raise ConfigError("synthetic disk full")

    monkeypatch.setattr(backup, "dump_database", failed_dump)
    with pytest.raises(ConfigError):
        backup.create_backup(config, object())
    assert not list(Path(config["BACKUP_DIR"]).iterdir())


@pytest.mark.parametrize("damage", ["checksum", "project", "database", "symlink"])
def test_restore_rejects_wrong_or_corrupt_backup_before_stopping_writers(
    tmp_path, monkeypatch, damage
):
    from deploy.scripts import backup

    config = values(tmp_path)
    monkeypatch.setattr(backup, "dump_database", lambda c, p: p.write_bytes(b"PGDMP synthetic"))
    monkeypatch.setattr(backup, "check_archive", lambda *args: None)
    archive = backup.create_backup(config, object())
    if damage == "checksum":
        (archive / "database.dump").write_bytes(b"PGDMP truncated")
    elif damage == "symlink":
        if os.name != "posix":
            pytest.skip("POSIX symlink check")
        link = tmp_path / "archive-link"
        link.symlink_to(archive, target_is_directory=True)
        archive = link
    else:
        config["PROJECT_NAME" if damage == "project" else "POSTGRES_DB"] = "different"
    with pytest.raises(ConfigError):
        backup.restore_backup(
            config, object(), archive, config["PROJECT_NAME"] + "/" + config["POSTGRES_DB"]
        )


def test_restore_requires_explicit_target_and_preserves_safety_copy(tmp_path, monkeypatch):
    from deploy.scripts import backup

    config = values(tmp_path)
    events = []
    monkeypatch.setattr(backup, "dump_database", lambda c, p: p.write_bytes(b"PGDMP synthetic"))
    monkeypatch.setattr(backup, "check_archive", lambda *args: events.append("check"))
    archive = backup.create_backup(config, object())

    class Compose:
        def call(self, *args, **kwargs):
            events.append(args)

    monkeypatch.setattr(backup, "restore_database", lambda *args: events.append("restore"))
    with pytest.raises(ConfigError):
        backup.restore_backup(config, Compose(), archive, "wrong-target")
    events.clear()
    backup.restore_backup(config, Compose(), archive, "synthetic-project/synthetic_database")
    assert events[0] == "check"
    assert events[1] == ("stop", "web", "api", "worker")
    assert events[-1] == "restore"
    assert len(list(Path(config["BACKUP_DIR"]).iterdir())) == 2


def test_failed_safety_backup_prevents_restore(tmp_path, monkeypatch):
    from deploy.scripts import backup

    config = values(tmp_path)
    monkeypatch.setattr(backup, "dump_database", lambda c, p: p.write_bytes(b"PGDMP synthetic"))
    monkeypatch.setattr(backup, "check_archive", lambda *args: None)
    archive = backup.create_backup(config, object())
    events = []

    class Compose:
        def call(self, *args, **kwargs):
            events.append(args)

    def failure(*args):
        raise ConfigError("synthetic safety copy failure")

    monkeypatch.setattr(backup, "create_backup", failure)
    monkeypatch.setattr(backup, "restore_database", lambda *args: events.append("restore"))
    with pytest.raises(ConfigError):
        backup.restore_backup(config, Compose(), archive, "synthetic-project/synthetic_database")
    assert events == [("stop", "web", "api", "worker")]


def test_restore_replaces_managed_schema_in_one_transaction(tmp_path, monkeypatch):
    from deploy.scripts import backup

    commands = []

    class Compose:
        values = {"POSTGRES_USER": "synthetic_user", "POSTGRES_DB": "synthetic_database"}

    def command(compose, args, *, source=None, target=None):
        commands.append(args)
        if target:
            target.write_bytes(b"CREATE TABLE public.old_release_table (id int);\n")
        if args[0] == "psql":
            script = source.read_text()
            assert script.index("DROP SCHEMA") < script.index("CREATE SCHEMA")
            assert script.index("CREATE SCHEMA") < script.index("CREATE TABLE")
            assert "--single-transaction" in args
            assert "ON_ERROR_STOP=1" in args

    dump = tmp_path / "database.dump"
    dump.write_bytes(b"PGDMP synthetic")
    monkeypatch.setattr(backup, "postgres_command", command)
    backup.restore_database(Compose(), dump)
    assert commands[-1][0] == "psql"
    assert not list(tmp_path.glob(".restore-*"))
