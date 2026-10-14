"""Private disk staging for a bounded, complete new-root ancestry observation."""

import json
import sqlite3
from collections.abc import Callable, Generator, Iterable, Iterator
from contextlib import closing, contextmanager
from pathlib import Path

from .scope_extension import ScopeNode


class ScopeStage:
    def __init__(
        self, path: Path, identity: str, *, max_nodes: int = 100000, max_bytes: int = 128 * 1024**2
    ) -> None:
        if type(max_nodes) is not int or not 1 <= max_nodes <= 100000:
            raise ValueError("SCOPE_CAPACITY")
        if type(max_bytes) is not int or not 1024 <= max_bytes <= 128 * 1024**2:
            raise ValueError("SCOPE_CAPACITY")
        if path.is_symlink() or (path.exists() and path.stat().st_nlink != 1):
            raise ValueError("SCOPE_STAGE_UNSAFE")
        self.path, self.identity = path, identity
        self.max_nodes, self.max_bytes = max_nodes, max_bytes
        with self._transaction() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS meta(id INTEGER PRIMARY KEY, identity TEXT)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS nodes(volume TEXT, file_id TEXT, body TEXT, "
                "PRIMARY KEY(volume,file_id))"
            )
            connection.execute("INSERT OR IGNORE INTO meta(id,identity) VALUES(1,?)", (identity,))
            if connection.execute("SELECT identity FROM meta WHERE id=1").fetchone()[0] != identity:
                raise ValueError("SCOPE_STAGE_CONFLICT")

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=2, autocommit=True)
        try:
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA cache_size=-2048")
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except sqlite3.IntegrityError:
            raise ValueError("SCOPE_IDENTITY_CONFLICT") from None
        except sqlite3.Error:
            raise ValueError("SCOPE_STAGE_UNAVAILABLE") from None
        finally:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            connection.close()

    def write_nodes(
        self, nodes: Iterable[ScopeNode], *, stopped: Callable[[], bool] = lambda: False
    ) -> None:
        with self._transaction() as connection:
            count, size = connection.execute(
                "SELECT count(*),coalesce(sum(length(CAST(body AS BLOB))),0) FROM nodes"
            ).fetchone()
            for node in nodes:
                if stopped():
                    raise ValueError("SCOPE_STOPPED")
                body = json.dumps(
                    {
                        "volume": node.volume,
                        "file_id": node.file_id,
                        "parent_id": node.parent_id,
                        "name": node.name,
                        "root": node.root,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                count += 1
                size += len(body.encode())
                if count > self.max_nodes or size > self.max_bytes:
                    raise ValueError("SCOPE_CAPACITY")
                connection.execute(
                    "INSERT INTO nodes(volume,file_id,body) VALUES(?,?,?)",
                    (
                        node.volume,
                        node.file_id,
                        body,
                    ),
                )

    def nodes(self) -> Generator[ScopeNode]:
        connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=2)
        try:
            cursor = connection.execute("SELECT body FROM nodes ORDER BY volume,file_id")
            while page := cursor.fetchmany(256):
                for (body,) in page:
                    yield ScopeNode(**json.loads(body))
        finally:
            connection.close()

    def contains(self, volume: str, identifier: str) -> bool:
        with self.read_view() as contains:
            return contains(volume, identifier)

    @contextmanager
    def read_view(self) -> Iterator[Callable[[str, str], bool]]:
        connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=2)
        try:
            connection.execute("PRAGMA cache_size=-2048")

            def contains(volume: str, identifier: str) -> bool:
                return (
                    connection.execute(
                        "SELECT 1 FROM nodes WHERE volume=? AND file_id=?", (volume, identifier)
                    ).fetchone()
                    is not None
                )

            yield contains
        finally:
            connection.close()

    def count(self) -> int:
        connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=2)
        with closing(connection):
            return int(connection.execute("SELECT count(*) FROM nodes").fetchone()[0])
