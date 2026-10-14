"""Own bounded encrypted directory queue, independent of Security bookmark/delivery."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any
from uuid import UUID

from collectors.common.outbox import Claim
from collectors.common.transport import DeliveryOutcome, valid_outcome
from packages.contracts.directory import ClientNameObservation, DirectoryPage

from .store import Cipher


class DirectoryStoreError(Exception):
    pass


class DirectoryStore:
    def __init__(
        self,
        path: Path,
        collector_id: UUID,
        cipher: Cipher,
        *,
        max_bytes: int = 64 * 1024**2,
        max_batches: int = 1024,
    ) -> None:
        if not 8192 <= max_bytes <= 64 * 1024**2 or not 2 <= max_batches <= 1024:
            raise DirectoryStoreError("DIRECTORY_LIMIT")
        if path.is_symlink() or path.exists() and path.stat().st_nlink != 1:
            raise DirectoryStoreError("DIRECTORY_STATE_UNSAFE")
        self.path, self.collector_id, self.cipher = path, collector_id, cipher
        self.max_bytes, self.max_batches = max_bytes, max_batches
        with self._transaction() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS identity (id INTEGER PRIMARY KEY CHECK(id=1), "
                "collector TEXT NOT NULL, payload BLOB)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS queue (seq INTEGER PRIMARY KEY AUTOINCREMENT, "
                "batch TEXT UNIQUE NOT NULL, domain TEXT NOT NULL, body BLOB NOT NULL)"
            )
            db.execute(
                "INSERT OR IGNORE INTO identity(id,collector) VALUES(1,?)", (str(collector_id),)
            )
            if db.execute("SELECT collector FROM identity WHERE id=1").fetchone()[0] != str(
                collector_id
            ):
                raise DirectoryStoreError("DIRECTORY_IDENTITY_CONFLICT")

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.path, timeout=2)) as db:
            try:
                db.execute("PRAGMA journal_mode=DELETE")
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
                yield db
                db.commit()
            except sqlite3.Error:
                db.rollback()
                raise DirectoryStoreError("DIRECTORY_STORE_FAILED") from None
            except BaseException:
                db.rollback()
                raise

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        with closing(
            sqlite3.connect(self.path.absolute().as_uri() + "?mode=ro", uri=True, timeout=2)
        ) as db:
            try:
                db.execute("PRAGMA query_only=ON")
                yield db
            except sqlite3.Error:
                raise DirectoryStoreError("DIRECTORY_STORE_FAILED") from None

    def enqueue(
        self,
        domain: str,
        value: DirectoryPage | ClientNameObservation,
        *,
        terminal_error: bool = False,
    ) -> None:
        if (
            value.collector_id != self.collector_id
            or domain == "directory"
            and not isinstance(value, DirectoryPage)
            or domain == "client-names"
            and not isinstance(value, ClientNameObservation)
            or domain not in {"directory", "client-names"}
        ):
            raise DirectoryStoreError("DIRECTORY_IDENTITY_CONFLICT")
        if terminal_error and not (
            isinstance(value, DirectoryPage)
            and value.finished
            and not value.complete
            and value.error_code
        ):
            raise DirectoryStoreError("DIRECTORY_TERMINAL_INVALID")
        raw = value.model_dump_json().encode()
        if len(raw) > 4 * 1024**2:
            raise DirectoryStoreError("DIRECTORY_LIMIT")
        encrypted = self.cipher.protect(raw)
        with self._transaction() as db:
            count, size = db.execute(
                "SELECT count(*),coalesce(sum(length(body)),0) FROM queue"
            ).fetchone()
            reserve = 0 if terminal_error else 4096
            if (
                count >= self.max_batches - (not terminal_error)
                or size + len(encrypted) > self.max_bytes - reserve
            ):
                raise DirectoryStoreError("DIRECTORY_LIMIT")
            db.execute(
                "INSERT INTO queue(batch,domain,body) VALUES(?,?,?)",
                (value.batch_id, domain, encrypted),
            )

    def delivery_state(self) -> dict[str, Any]:
        with self._read() as db:
            value = db.execute("SELECT payload FROM identity WHERE id=1").fetchone()[0]
        return json.loads(self.cipher.unprotect(value)) if value else {}

    def save_state(self, value: dict[str, Any]) -> None:
        raw = json.dumps(value, separators=(",", ":")).encode()
        if len(raw) > 48000:
            raise DirectoryStoreError("DIRECTORY_LIMIT")
        with self._transaction() as db:
            db.execute("UPDATE identity SET payload=? WHERE id=1", (self.cipher.protect(raw),))

    def peek(self) -> Claim | None:
        with self._read() as db:
            row = db.execute("SELECT batch,domain,body FROM queue ORDER BY seq LIMIT 1").fetchone()
        if row is None:
            return None
        return Claim(row[0], row[1], self.cipher.unprotect(row[2]), "directory", 0)

    def status(self) -> dict[str, int]:
        with self._read() as db:
            count, size = db.execute(
                "SELECT count(*),coalesce(sum(length(body)),0) FROM queue"
            ).fetchone()
        return {"backlog": count, "encrypted_bytes": size}

    def record_outcome(self, outcome: DeliveryOutcome, *, now: float) -> None:
        if not valid_outcome(outcome):
            outcome = DeliveryOutcome("retry", code="INVALID_RECEIPT")
        state = self.delivery_state()
        if outcome.kind == "accepted":
            with self._transaction() as db:
                db.execute("DELETE FROM queue WHERE seq=(SELECT min(seq) FROM queue)")
            state.update(next_attempt=0, attempts=0, error_code=None)
        else:
            attempts = min(state.get("attempts", 0) + 1, 10)
            state.update(
                attempts=attempts,
                error_code=outcome.code,
                next_attempt=now + max(outcome.retry_after or 0, min(300, 2**attempts)),
                suspended=outcome.kind == "suspended",
                quarantine=outcome.kind == "quarantined",
            )
        self.save_state(state)
