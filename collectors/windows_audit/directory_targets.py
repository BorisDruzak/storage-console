"""Only selected Security witnesses with an acknowledged Audit batch become targets."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from .store import Cipher


def read_targets(path: Path, cipher: Cipher) -> list[str]:
    if not path.exists():
        return []
    with closing(sqlite3.connect(path.absolute().as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        row = db.execute("SELECT checkpoint FROM state WHERE id=1").fetchone()
        if row is None or row[0] is None:
            return []
        checkpoint = json.loads(cipher.unprotect(row[0]))
        targets = checkpoint["cache"].get("directory_targets", {})
        if not isinstance(targets, dict) or len(targets) > 512:
            raise ValueError("DIRECTORY_LIMIT")
        batches = {value["batch"] for value in targets.values()}
        if not batches:
            return []
        placeholders = ",".join("?" for _ in batches)
        pending = {
            row[0]
            for row in db.execute(
                "SELECT id FROM queue WHERE id IN (" + placeholders + ")", tuple(batches)
            )
        }
        return [value["ip"] for value in targets.values() if value["batch"] not in pending]
