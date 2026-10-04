"""Transactional capture checkpoints and retained immutable ingest batches."""

import json
import math
import os
import sqlite3
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, TypeAdapter, ValidationError

from packages.contracts.acl import ACLRecord
from packages.contracts.changes import ChangeRecord
from packages.contracts.common import BatchEnvelope
from packages.contracts.diagnostics import DiagnosticRecord
from packages.contracts.events import EvidenceRecord
from packages.contracts.heartbeat import HeartbeatRecord
from packages.contracts.hygiene import HygieneRecord
from packages.contracts.inventory import InventoryRecord
from packages.contracts.recovery import RecoveryRecord
from packages.contracts.telemetry import TelemetryRecord

_ADAPTERS: dict[str, TypeAdapter[BaseModel]] = {
    "heartbeat": TypeAdapter(BatchEnvelope[HeartbeatRecord]),
    "inventory": TypeAdapter(BatchEnvelope[InventoryRecord]),
    "changes": TypeAdapter(BatchEnvelope[ChangeRecord]),
    "telemetry": TypeAdapter(BatchEnvelope[TelemetryRecord]),
    "events": TypeAdapter(BatchEnvelope[EvidenceRecord]),
    "acl": TypeAdapter(BatchEnvelope[ACLRecord]),
    "recovery": TypeAdapter(BatchEnvelope[RecoveryRecord]),
    "hygiene": TypeAdapter(BatchEnvelope[HygieneRecord]),
    "diagnostics": TypeAdapter(BatchEnvelope[DiagnosticRecord]),
}
_DELIVERY_CODES = frozenset(
    {
        "NETWORK",
        "TLS",
        "TIMEOUT",
        "RATE_LIMITED",
        "SERVER_ERROR",
        "INVALID_RECEIPT",
        "AUTH_REQUIRED",
        "HTTP_REJECTED",
        "REDIRECT",
    }
)
_APPLICATION_ID = 0x53434F42
_SCHEMA = (
    "CREATE TABLE meta(collector_id TEXT NOT NULL, "
    "auth_suspended INTEGER NOT NULL DEFAULT 0 CHECK(auth_suspended IN (0,1)), "
    "credential_generation INTEGER NOT NULL DEFAULT 0 CHECK(credential_generation>=0), "
    "credential_binding TEXT)",
    "CREATE TABLE checkpoints(stream TEXT PRIMARY KEY, revision INTEGER NOT NULL, "
    "value TEXT NOT NULL)",
    "CREATE TABLE batches(seq INTEGER PRIMARY KEY AUTOINCREMENT, batch_id TEXT UNIQUE NOT NULL, "
    "domain TEXT NOT NULL, stream TEXT NOT NULL, body BLOB NOT NULL, digest TEXT NOT NULL, "
    "revision INTEGER NOT NULL, checkpoint TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending', "
    "lease_id TEXT, lease_until REAL, next_attempt REAL NOT NULL DEFAULT 0, "
    "attempts INTEGER NOT NULL DEFAULT 0, error_code TEXT)",
    "CREATE INDEX batch_stream_order ON batches(stream, seq)",
    "CREATE TABLE receipts(seq INTEGER PRIMARY KEY AUTOINCREMENT, batch_id TEXT UNIQUE NOT NULL, "
    "domain TEXT NOT NULL, stream TEXT NOT NULL, digest TEXT NOT NULL, revision INTEGER NOT NULL, "
    "checkpoint TEXT NOT NULL)",
)


class OutboxError(Exception):
    """Fixed code only: never include SQL, paths, payloads or underlying exception text."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Limits:
    max_retained_batches: int = 1024
    max_retained_bytes: int = 512 * 1024 * 1024
    max_body_bytes: int = 16 * 1024 * 1024
    max_checkpoint_bytes: int = 16 * 1024
    max_receipts: int = 4096
    lease_seconds: int = 60
    busy_timeout_seconds: int = 5
    heartbeat_reserve_batches: int = 0
    heartbeat_reserve_bytes: int = 0

    def __post_init__(self) -> None:
        bounds = (
            (self.max_retained_batches, 1, 100000),
            (self.max_retained_bytes, 1, 8 * 1024**3),
            (self.max_body_bytes, 1, 16 * 1024**2),
            (self.max_checkpoint_bytes, 1, 16 * 1024),
            (self.max_receipts, 1, 100000),
            (self.lease_seconds, 30, 3600),
            (self.busy_timeout_seconds, 1, 30),
            (self.heartbeat_reserve_batches, 0, self.max_retained_batches - 1),
            (self.heartbeat_reserve_bytes, 0, self.max_retained_bytes - 1),
        )
        if any(type(value) is not int or not low <= value <= high for value, low, high in bounds):
            raise OutboxError("INVALID_LIMITS")
        if self.max_body_bytes > self.max_retained_bytes:
            raise OutboxError("INVALID_LIMITS")


@dataclass(frozen=True)
class Checkpoint:
    revision: int
    value: object


@dataclass(frozen=True)
class Claim:
    batch_id: str
    domain: str
    body: bytes
    lease_id: str
    attempts: int
    credential_generation: int = 0


@dataclass(frozen=True)
class Status:
    pending_count: int
    quarantined_count: int
    retained_bytes: int


def _stream(value: str) -> None:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 255
        or any(ord(character) < 32 or 0xD800 <= ord(character) <= 0xDFFF for character in value)
    ):
        raise OutboxError("INVALID_CHECKPOINT")


def _time(value: datetime) -> float:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise OutboxError("INVALID_TIME")
    result = value.timestamp()
    if not math.isfinite(result):
        raise OutboxError("INVALID_TIME")
    return result


class Outbox:
    def __init__(self, path: Path, collector_id: UUID, limits: Limits | None = None) -> None:
        if not isinstance(collector_id, UUID):
            raise OutboxError("INVALID_BATCH")
        self.path = Path(os.path.abspath(path))
        self.collector_id = collector_id
        self.limits = limits if limits is not None else Limits()
        self._prepare()
        with self._transaction(initializing=True) as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            application = db.execute("PRAGMA application_id").fetchone()[0]
            tables = {
                row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if version == 0 and application == 0 and not tables:
                for statement in _SCHEMA:
                    db.execute(statement)
                db.execute("INSERT INTO meta(collector_id) VALUES (?)", (str(collector_id),))
                db.execute(f"PRAGMA application_id={_APPLICATION_ID}")
                db.execute("PRAGMA user_version=3")
            elif (
                version not in (1, 2, 3)
                or application != _APPLICATION_ID
                or tables != {"meta", "checkpoints", "batches", "receipts", "sqlite_sequence"}
            ):
                raise OutboxError("SCHEMA_UNSUPPORTED")
            identity = db.execute("SELECT collector_id FROM meta").fetchall()
            if len(identity) != 1 or identity[0][0] != str(collector_id):
                raise OutboxError("IDENTITY_CONFLICT")
            if version == 1:
                db.execute(
                    "ALTER TABLE meta ADD COLUMN auth_suspended INTEGER NOT NULL "
                    "DEFAULT 0 CHECK(auth_suspended IN (0,1))"
                )
                db.execute(
                    "ALTER TABLE meta ADD COLUMN credential_generation INTEGER NOT NULL "
                    "DEFAULT 0 CHECK(credential_generation>=0)"
                )
            if version in (1, 2):
                db.execute("ALTER TABLE meta ADD COLUMN credential_binding TEXT")
                db.execute("PRAGMA user_version=3")
            self._binding(db)

    def _prepare(self) -> None:
        try:
            self._links()
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self._links()
            if os.name == "posix":
                info = self.path.parent.stat()
                if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
                    raise OutboxError("UNSAFE_STATE")
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(fd)
            self._file()
        except OSError:
            raise OutboxError("UNSAFE_STATE") from None

    def _links(self) -> None:
        for component in (self.path, *self.path.parents):
            if component.is_symlink() or component.is_junction():
                raise OutboxError("UNSAFE_STATE")

    def _file(self) -> None:
        self._links()
        if os.name == "posix":
            parent = self.path.parent.stat()
            if parent.st_uid != os.geteuid() or stat.S_IMODE(parent.st_mode) != 0o700:
                raise OutboxError("UNSAFE_STATE")
        info = self.path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise OutboxError("UNSAFE_STATE")
        if os.name == "posix" and (
            info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise OutboxError("UNSAFE_STATE")
        for suffix in ("-journal", "-wal", "-shm"):
            sidecar = Path(str(self.path) + suffix)
            if sidecar.is_symlink() or sidecar.is_junction():
                raise OutboxError("UNSAFE_STATE")
            try:
                info = sidecar.lstat()
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise OutboxError("UNSAFE_STATE")
            if os.name == "posix" and (
                info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600
            ):
                raise OutboxError("UNSAFE_STATE")

    def _connect(self) -> sqlite3.Connection:
        self._file()
        db = sqlite3.connect(self.path, timeout=self.limits.busy_timeout_seconds, autocommit=True)
        db.row_factory = sqlite3.Row
        return db

    @contextmanager
    def _transaction(self, *, initializing: bool = False) -> Iterator[sqlite3.Connection]:
        db: sqlite3.Connection | None = None
        try:
            db = self._connect()
            db.execute("PRAGMA synchronous=FULL")
            # Refuse WAL state instead of switching journal modes or deleting sidecars.
            if db.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
                raise OutboxError("SCHEMA_UNSUPPORTED")
            db.execute("BEGIN IMMEDIATE")
            if not initializing:
                if (
                    db.execute("PRAGMA user_version").fetchone()[0] != 3
                    or db.execute("PRAGMA application_id").fetchone()[0] != _APPLICATION_ID
                ):
                    raise OutboxError("SCHEMA_UNSUPPORTED")
                identity = db.execute("SELECT collector_id FROM meta").fetchall()
                if len(identity) != 1 or identity[0][0] != str(self.collector_id):
                    raise OutboxError("IDENTITY_CONFLICT")
            yield db
            db.execute("COMMIT")
        except (sqlite3.Error, OSError):
            raise OutboxError("STATE_UNAVAILABLE") from None
        finally:
            if db is not None:
                try:
                    try:
                        if db.in_transaction:
                            db.execute("ROLLBACK")
                    finally:
                        db.close()
                except sqlite3.Error:
                    raise OutboxError("STATE_UNAVAILABLE") from None

    def checkpoint(self, stream: str) -> Checkpoint:
        _stream(stream)
        with self._transaction() as db:
            row = db.execute(
                "SELECT revision, value FROM checkpoints WHERE stream=?", (stream,)
            ).fetchone()
            try:
                return Checkpoint(row[0], json.loads(row[1])) if row else Checkpoint(0, None)
            except (ValueError, TypeError):
                raise OutboxError("STATE_UNAVAILABLE") from None

    def enqueue(
        self, domain: str, batch: BaseModel, stream: str, expected_revision: int, checkpoint: object
    ) -> str:
        _stream(stream)
        if type(expected_revision) is not int or not 0 <= expected_revision < 2**63 - 1:
            raise OutboxError("INVALID_CHECKPOINT")
        try:
            value = json.dumps(
                checkpoint,
                allow_nan=False,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            if len(value.encode("utf-8")) > self.limits.max_checkpoint_bytes:
                raise OutboxError("INVALID_CHECKPOINT")
        except (ValueError, TypeError, RecursionError, UnicodeError):
            raise OutboxError("INVALID_CHECKPOINT") from None
        try:
            if domain not in _ADAPTERS or not isinstance(batch, BaseModel):
                raise OutboxError("INVALID_BATCH")
            body = batch.model_dump_json().encode("utf-8")
            if len(body) > self.limits.max_body_bytes:
                raise OutboxError("INVALID_BATCH")
            # JSON validation also checks model_copy/model_construct mutations.
            validated = _ADAPTERS[domain].validate_json(body)
            fields = validated.model_dump()
            if fields["collector_id"] != self.collector_id:
                raise OutboxError("INVALID_BATCH")
            batch_id = fields["batch_id"]
            if not isinstance(batch_id, str):
                raise OutboxError("INVALID_BATCH")
        except (ValidationError, ValueError, TypeError, UnicodeError):
            raise OutboxError("INVALID_BATCH") from None
        digest = sha256(body).hexdigest()
        with self._transaction() as db:
            previous = db.execute(
                "SELECT domain, stream, digest, revision, checkpoint FROM batches WHERE batch_id=?",
                (batch_id,),
            ).fetchone()
            if previous is None:
                previous = db.execute(
                    "SELECT domain, stream, digest, revision, checkpoint "
                    "FROM receipts WHERE batch_id=?",
                    (batch_id,),
                ).fetchone()
            if previous is not None:
                if tuple(previous) != (domain, stream, digest, expected_revision, value):
                    raise OutboxError("BATCH_CONFLICT")
                return batch_id
            current = db.execute(
                "SELECT revision FROM checkpoints WHERE stream=?", (stream,)
            ).fetchone()
            if (current[0] if current else 0) != expected_revision:
                raise OutboxError("CHECKPOINT_CONFLICT")
            count, size, data_count, data_size = db.execute(
                "SELECT count(*), coalesce(sum(length(body)),0), "
                "coalesce(sum(CASE WHEN domain!='heartbeat' THEN 1 ELSE 0 END),0), "
                "coalesce(sum(CASE WHEN domain!='heartbeat' THEN length(body) ELSE 0 END),0) "
                "FROM batches"
            ).fetchone()
            if count >= self.limits.max_retained_batches or (
                size + len(body) > self.limits.max_retained_bytes
            ):
                raise OutboxError("CAPACITY")
            if domain != "heartbeat" and (
                data_count
                >= self.limits.max_retained_batches - self.limits.heartbeat_reserve_batches
                or data_size + len(body)
                > self.limits.max_retained_bytes - self.limits.heartbeat_reserve_bytes
            ):
                raise OutboxError("CAPACITY")
            db.execute(
                "INSERT INTO batches(batch_id,domain,stream,body,digest,revision,checkpoint) "
                "VALUES (?,?,?,?,?,?,?)",
                (batch_id, domain, stream, body, digest, expected_revision, value),
            )
            db.execute(
                "INSERT INTO checkpoints(stream,revision,value) VALUES (?,?,?) "
                "ON CONFLICT(stream) DO UPDATE SET revision=excluded.revision, "
                "value=excluded.value",
                (stream, expected_revision + 1, value),
            )
            self._receipt(db, batch_id, domain, stream, digest, expected_revision, value)
            return batch_id

    def _receipt(
        self,
        db: sqlite3.Connection,
        batch_id: str,
        domain: str,
        stream: str,
        digest: str,
        revision: int,
        checkpoint: str,
    ) -> None:
        db.execute(
            "INSERT OR IGNORE INTO receipts(batch_id,domain,stream,digest,revision,checkpoint) "
            "VALUES (?,?,?,?,?,?)",
            (batch_id, domain, stream, digest, revision, checkpoint),
        )
        db.execute(
            "DELETE FROM receipts WHERE seq IN (SELECT seq FROM receipts ORDER BY seq DESC "
            "LIMIT -1 OFFSET ?)",
            (self.limits.max_receipts,),
        )

    def claim(
        self, now: datetime, *, heartbeat_priority: Literal["normal", "first", "last"] = "normal"
    ) -> Claim | None:
        if heartbeat_priority not in ("normal", "first", "last"):
            raise OutboxError("INVALID_PRIORITY")
        ordering = {
            "normal": "b.seq",
            "first": "CASE WHEN b.domain='heartbeat' THEN 0 ELSE 1 END, b.seq",
            "last": "CASE WHEN b.domain='heartbeat' THEN 1 ELSE 0 END, b.seq",
        }[heartbeat_priority]
        stamp = _time(now)
        with self._transaction() as db:
            suspended, generation = self._auth(db)
            if suspended:
                return None
            row = db.execute(
                "SELECT b.* FROM batches b WHERE state='pending' AND next_attempt<=? "
                "AND (lease_id IS NULL OR lease_until<=?) "
                "AND NOT EXISTS(SELECT 1 FROM batches earlier "
                "WHERE earlier.stream=b.stream AND earlier.seq<b.seq) ORDER BY "
                + ordering
                + " LIMIT 1",
                (stamp, stamp),
            ).fetchone()
            if row is None:
                return None
            if not isinstance(row["body"], bytes) or (
                sha256(row["body"]).hexdigest() != row["digest"]
            ):
                raise OutboxError("STATE_UNAVAILABLE")
            lease = str(uuid4())
            db.execute(
                "UPDATE batches SET lease_id=?, lease_until=? WHERE seq=?",
                (lease, stamp + self.limits.lease_seconds, row["seq"]),
            )
            return Claim(
                row["batch_id"], row["domain"], row["body"], lease, row["attempts"], generation
            )

    def _auth(self, db: sqlite3.Connection) -> tuple[bool, int]:
        row = db.execute("SELECT auth_suspended,credential_generation FROM meta").fetchone()
        if (
            row is None
            or type(row[0]) is not int
            or row[0] not in (0, 1)
            or (type(row[1]) is not int or not 0 <= row[1] <= 2**63 - 1)
        ):
            raise OutboxError("STATE_UNAVAILABLE")
        return bool(row[0]), row[1]

    def auth_suspended(self) -> bool:
        with self._transaction() as db:
            return self._auth(db)[0]

    def credential_generation(self) -> int:
        with self._transaction() as db:
            return self._auth(db)[1]

    def _binding(self, db: sqlite3.Connection) -> UUID | None:
        row = db.execute("SELECT credential_binding FROM meta").fetchone()
        if row is None:
            raise OutboxError("STATE_UNAVAILABLE")
        if row[0] is None:
            return None
        try:
            binding = UUID(row[0])
            if str(binding) != row[0]:
                raise ValueError
            return binding
        except (ValueError, TypeError, AttributeError):
            raise OutboxError("STATE_UNAVAILABLE") from None

    def credential_binding(self) -> UUID | None:
        with self._transaction() as db:
            return self._binding(db)

    def activate_credentials(self, binding: UUID) -> int:
        if not isinstance(binding, UUID):
            raise OutboxError("INVALID_CREDENTIALS")
        with self._transaction() as db:
            generation = self._auth(db)[1]
            # Replaying the same config transition cannot undo credential revocation.
            if self._binding(db) == binding:
                return generation
            if generation == 2**63 - 1:
                raise OutboxError("STATE_UNAVAILABLE")
            db.execute(
                "UPDATE meta SET auth_suspended=0,credential_generation=?,credential_binding=?",
                (generation + 1, str(binding)),
            )
            db.execute("UPDATE batches SET lease_id=NULL,lease_until=NULL")
            return generation + 1

    def resume_auth(self) -> int:
        with self._transaction() as db:
            if self._binding(db) is not None:
                raise OutboxError("CREDENTIAL_BOUND")
            generation = self._auth(db)[1]
            if generation == 2**63 - 1:
                raise OutboxError("STATE_UNAVAILABLE")
            db.execute(
                "UPDATE meta SET auth_suspended=0,credential_generation=?", (generation + 1,)
            )
            return generation + 1

    def suspend_auth(self, claim: Claim) -> bool:
        with self._transaction() as db:
            if self._auth(db)[1] != claim.credential_generation:
                return False
            result = db.execute(
                "UPDATE batches SET lease_id=NULL,lease_until=NULL,next_attempt=0, "
                "attempts=min(attempts+1,2147483647),error_code='AUTH_REQUIRED' "
                "WHERE batch_id=? AND lease_id=?",
                (claim.batch_id, claim.lease_id),
            )
            if result.rowcount != 1:
                return False
            db.execute("UPDATE meta SET auth_suspended=1")
            return True

    def acknowledge(self, claim: Claim) -> bool:
        with self._transaction() as db:
            if self._auth(db)[1] != claim.credential_generation:
                return False
            row = db.execute(
                "SELECT * FROM batches WHERE batch_id=? AND lease_id=?",
                (claim.batch_id, claim.lease_id),
            ).fetchone()
            if row is None:
                return False
            self._receipt(
                db,
                row["batch_id"],
                row["domain"],
                row["stream"],
                row["digest"],
                row["revision"],
                row["checkpoint"],
            )
            db.execute("DELETE FROM batches WHERE seq=?", (row["seq"],))
            return True

    def retry(self, claim: Claim, code: str, next_attempt: datetime) -> bool:
        return self._finish(claim, code, "pending", _time(next_attempt))

    def quarantine(self, claim: Claim, code: str) -> bool:
        return self._finish(claim, code, "quarantined", 0)

    def _finish(self, claim: Claim, code: str, state: str, stamp: float) -> bool:
        if code not in _DELIVERY_CODES:
            raise OutboxError("INVALID_CODE")
        with self._transaction() as db:
            if self._auth(db)[1] != claim.credential_generation:
                return False
            result = db.execute(
                "UPDATE batches SET state=?, lease_id=NULL, lease_until=NULL, "
                "next_attempt=?, attempts=min(attempts+1,2147483647), error_code=? "
                "WHERE batch_id=? AND lease_id=?",
                (state, stamp, code, claim.batch_id, claim.lease_id),
            )
            return result.rowcount == 1

    def status(self) -> Status:
        with self._transaction() as db:
            row = db.execute(
                "SELECT coalesce(sum(state='pending'),0), "
                "coalesce(sum(state='quarantined'),0),coalesce(sum(length(body)),0) "
                "FROM batches"
            ).fetchone()
            return Status(row[0], row[1], row[2])
