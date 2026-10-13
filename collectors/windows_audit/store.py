"""Independent encrypted SQLite queue and atomic native bookmark/cache checkpoint."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid4


class Cipher(Protocol):
    def protect(self, value: bytes) -> bytes: ...
    def unprotect(self, value: bytes) -> bytes: ...


class AuditStoreError(Exception):
    """Fixed code only; never include SQL, XML, paths or credentials."""


class AuditStore:
    def __init__(
        self,
        path: Path,
        collector_id: UUID,
        cipher: Cipher,
        *,
        max_bytes: int = 64 * 1024**2,
        max_batches: int = 1024,
    ) -> None:
        if not 128 <= max_bytes <= 512 * 1024**2 or not 1 <= max_batches <= 10000:
            raise AuditStoreError("AUDIT_LIMITS_INVALID")
        if path.is_symlink() or (path.exists() and path.stat().st_nlink != 1):
            raise AuditStoreError("AUDIT_STATE_UNSAFE")
        self.path, self.collector_id, self.cipher = path, collector_id, cipher
        self.max_bytes, self.max_batches = max_bytes, max_batches
        with self._transaction() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), "
                "collector TEXT NOT NULL, checkpoint BLOB, gap TEXT)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS queue (seq INTEGER PRIMARY KEY AUTOINCREMENT, "
                "id TEXT UNIQUE NOT NULL, body BLOB NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS delivery (id INTEGER PRIMARY KEY CHECK(id=1), "
                "payload BLOB NOT NULL)"
            )
            db.execute(
                "INSERT OR IGNORE INTO state(id,collector) VALUES(1,?)", (str(collector_id),)
            )
            if db.execute("SELECT collector FROM state WHERE id=1").fetchone()[0] != str(
                collector_id
            ):
                raise AuditStoreError("AUDIT_IDENTITY_CONFLICT")

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=2)
        try:
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except sqlite3.Error:
            db.rollback()
            raise AuditStoreError("AUDIT_STORE_FAILED") from None
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def checkpoint(self) -> tuple[str | None, dict[str, Any]]:
        with self._transaction() as db:
            row = db.execute("SELECT checkpoint FROM state WHERE id=1").fetchone()
        if not row[0]:
            return None, {}
        value = json.loads(self.cipher.unprotect(row[0]))
        return value["bookmark"], value["cache"]

    def commit(self, bookmark: str, cache: dict[str, Any], body: bytes | None) -> str | None:
        checkpoint = json.dumps(
            {"bookmark": bookmark, "cache": cache}, separators=(",", ":")
        ).encode()
        if len(checkpoint) > 4 * 1024**2 or len(bookmark) > 16384:
            raise AuditStoreError("AUDIT_CACHE_INVALID")
        encrypted = self.cipher.protect(body) if body is not None else None
        encoded = self.cipher.protect(checkpoint)
        batch_id = uuid4().hex if body is not None else None
        if body is not None:
            try:
                envelope = json.loads(body)
                if isinstance(envelope, dict) and "batch_id" in envelope:
                    batch_id = str(UUID(envelope["batch_id"])).replace("-", "")
                    if str(envelope.get("collector_id")) != str(self.collector_id):
                        raise AuditStoreError("AUDIT_IDENTITY_CONFLICT")
            except (ValueError, TypeError, UnicodeError):
                # Store also supports opaque owned test receipts; capture always uses an envelope.
                pass
        with self._transaction() as db:
            if db.execute("SELECT gap FROM state WHERE id=1").fetchone()[0]:
                raise AuditStoreError("AUDIT_GAP")
            count, size = db.execute(
                "SELECT count(*),coalesce(sum(length(body)),0) FROM queue"
            ).fetchone()
            if encrypted is not None:
                if count >= self.max_batches or size + len(encrypted) > self.max_bytes:
                    raise AuditStoreError("AUDIT_BACKPRESSURE")
                db.execute("INSERT INTO queue(id,body) VALUES(?,?)", (batch_id, encrypted))
            db.execute("UPDATE state SET checkpoint=? WHERE id=1", (encoded,))
        return batch_id

    def peek(self) -> tuple[str, bytes] | None:
        with self._transaction() as db:
            row = db.execute("SELECT id,body FROM queue ORDER BY seq LIMIT 1").fetchone()
        return (row[0], self.cipher.unprotect(row[1])) if row else None

    def acknowledge(self, batch_id: str) -> None:
        with self._transaction() as db:
            # Only the current oldest batch can be acknowledged.
            db.execute(
                "DELETE FROM queue WHERE id=? AND seq=(SELECT min(seq) FROM queue)", (batch_id,)
            )

    def gap(self) -> str | None:
        with self._transaction() as db:
            result: str | None = db.execute("SELECT gap FROM state WHERE id=1").fetchone()[0]
            return result

    def latch_gap(self, code: str) -> None:
        if code not in {
            "AUDIT_LOG_CLEARED",
            "AUDIT_BOOKMARK_STALE",
            "AUDIT_BOOT_CHANGED",
            "AUDIT_CONFIGURATION_CHANGED",
        }:
            raise AuditStoreError("AUDIT_GAP_CODE_INVALID")
        with self._transaction() as db:
            db.execute("UPDATE state SET gap=coalesce(gap,?) WHERE id=1", (code,))

    def status(self) -> dict[str, int | str | None]:
        with self._transaction() as db:
            count, size = db.execute(
                "SELECT count(*),coalesce(sum(length(body)),0) FROM queue"
            ).fetchone()
            gap = db.execute("SELECT gap FROM state WHERE id=1").fetchone()[0]
        return {"backlog": count, "encrypted_bytes": size, "gap": gap}

    def delivery_state(self) -> dict[str, Any]:
        with self._transaction() as db:
            row = db.execute("SELECT payload FROM delivery WHERE id=1").fetchone()
        return json.loads(self.cipher.unprotect(row[0])) if row else {}

    def save_delivery(self, value: dict[str, Any]) -> None:
        encoded = self.cipher.protect(json.dumps(value, separators=(",", ":")).encode())
        with self._transaction() as db:
            db.execute(
                "INSERT INTO delivery(id,payload) VALUES(1,?) "
                "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (encoded,),
            )
