"""Windows rollback-journal deletion must not resemble a persistent unsafe file."""
import os
import sqlite3
import stat
import threading
import time
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from collectors.common.outbox import Outbox, OutboxError


@pytest.mark.skipif(os.name != "nt", reason="Windows deletion metadata")
@pytest.mark.parametrize("replacement", ["missing", "regular"])
def test_disappearing_journal_is_revalidated(tmp_path, monkeypatch, replacement):
    box = Outbox(tmp_path / "state" / "outbox.sqlite3", uuid4())
    journal = Path(str(box.path) + "-journal")
    journal.write_bytes(b"synthetic")
    original = Path.lstat
    calls = 0

    def metadata(path, *args, **kwargs):
        nonlocal calls
        if path == journal:
            calls += 1
            if calls == 1:
                return SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_nlink=0,
                                       st_file_attributes=32)
            if replacement == "missing":
                raise FileNotFoundError
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "is_symlink", lambda path: False)
    monkeypatch.setattr(Path, "is_junction", lambda path: False)
    monkeypatch.setattr(Path, "lstat", metadata)
    box._file()
    assert calls >= 2


@pytest.mark.skipif(os.name != "nt", reason="Windows deletion metadata")
@pytest.mark.parametrize("suffix", ["-journal", "-wal", "-shm", ""])
def test_persistent_zero_link_file_is_not_accepted(tmp_path, monkeypatch, suffix):
    box = Outbox(tmp_path / "state" / "outbox.sqlite3", uuid4())
    target = Path(str(box.path) + suffix)
    original = Path.lstat
    calls = 0

    def metadata(path, *args, **kwargs):
        nonlocal calls
        if path == target:
            calls += 1
            return SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_nlink=0,
                                   st_file_attributes=32)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "is_symlink", lambda path: False)
    monkeypatch.setattr(Path, "is_junction", lambda path: False)
    monkeypatch.setattr(Path, "lstat", metadata)
    with pytest.raises(OutboxError, match="UNSAFE_STATE"):
        box._file()
    assert calls <= 4


@pytest.mark.parametrize("suffix", ["-journal", "-wal", "-shm", ""])
def test_actual_hardlinks_remain_rejected(tmp_path, suffix):
    box = Outbox(tmp_path / "state" / "outbox.sqlite3", uuid4())
    target = Path(str(box.path) + suffix)
    if suffix:
        target.write_bytes(b"synthetic")
        target.chmod(0o600)
    os.link(target, tmp_path / "second-link")
    with pytest.raises(OutboxError, match="UNSAFE_STATE"):
        box._file()


@pytest.mark.parametrize("suffix", ["-journal", "-wal", "-shm"])
def test_sidecar_directory_is_rejected(tmp_path, suffix):
    box = Outbox(tmp_path / "state" / "outbox.sqlite3", uuid4())
    Path(str(box.path) + suffix).mkdir()
    with pytest.raises(OutboxError, match="UNSAFE_STATE"):
        box._file()


@pytest.mark.skipif(os.name != "nt", reason="Windows reparse metadata")
@pytest.mark.parametrize("nlink, attributes", [(2, 32), (1, 0x400)])
def test_journal_retry_rejects_unsafe_replacement(tmp_path, monkeypatch, nlink, attributes):
    box = Outbox(tmp_path / "state" / "outbox.sqlite3", uuid4())
    journal = Path(str(box.path) + "-journal")
    original = Path.lstat
    calls = 0

    def metadata(path, *args, **kwargs):
        nonlocal calls
        if path == journal:
            calls += 1
            return SimpleNamespace(st_mode=stat.S_IFREG | 0o600,
                                   st_nlink=0 if calls == 1 else nlink,
                                   st_file_attributes=32 if calls == 1 else attributes)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "is_symlink", lambda path: False)
    monkeypatch.setattr(Path, "is_junction", lambda path: False)
    monkeypatch.setattr(Path, "lstat", metadata)
    with pytest.raises(OutboxError, match="UNSAFE_STATE"):
        box._file()
    assert calls == 2


@pytest.mark.skipif(os.name != "nt", reason="Native Windows SQLite delete race")
def test_native_journal_commits_do_not_fail_validation(tmp_path):
    box = Outbox(tmp_path / "state" / "outbox.sqlite3", uuid4())
    with closing(sqlite3.connect(box.path)) as db:
        db.execute("CREATE TABLE synthetic_counter(value INTEGER)")
        db.execute("INSERT INTO synthetic_counter VALUES(0)")
        db.commit()
    stop = threading.Event()
    ready = threading.Event()
    validate_started = threading.Event()
    failures = []
    commits = []

    def writer():
        try:
            with closing(sqlite3.connect(box.path)) as db:
                for index in range(32):
                    if stop.is_set():
                        break
                    db.execute("UPDATE synthetic_counter SET value=value+1")
                    if index == 0:
                        # First validation observes a real open rollback journal;
                        # the writer cannot finish before validation begins.
                        ready.set()
                        if not validate_started.wait(5) or stop.is_set():
                            return
                    db.commit()
                    commits.append(1)
        except Exception as error:
            failures.append(type(error).__name__)

    thread = threading.Thread(target=writer)
    thread.start()
    validations = 0
    try:
        assert ready.wait(5), failures
        assert thread.is_alive() and not failures
        box._file()
        validations += 1
        validate_started.set()
        # Fixed native work, not a minimum disk-throughput claim. Continue
        # validating concurrently with commits until completion or guard expiry.
        deadline = time.monotonic() + 40
        while len(commits) < 32 and not failures and time.monotonic() < deadline:
            box._file()
            validations += 1
            time.sleep(0)
    finally:
        stop.set()
        validate_started.set()
        thread.join(5)
    assert not thread.is_alive()
    assert not failures
    assert len(commits) == 32 and validations > 0
    with closing(sqlite3.connect(box.path)) as db:
        assert db.execute("SELECT value FROM synthetic_counter").fetchone()[0] == 32
        assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
