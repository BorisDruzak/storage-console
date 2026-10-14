"""A fixture observer must not compete for the collector's SQLite writer lock."""

import json
import os
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from windows_capture_diagnostics import activity_snapshot, readonly_observer, source_metadata

from collectors.common.outbox import Limits, Outbox


def test_status_observer_reads_while_producer_reserves_writer(tmp_path):
    box = Outbox(tmp_path / "outbox.sqlite3", uuid4(), Limits(busy_timeout_seconds=1))
    observer = readonly_observer(SimpleNamespace(outbox=box))
    before = box.path.read_bytes()
    with closing(sqlite3.connect(box.path, autocommit=True)) as writer:
        writer.execute("BEGIN IMMEDIATE")
        try:
            assert observer.status().pending_count == 0
        finally:
            writer.execute("ROLLBACK")
    assert before == box.path.read_bytes()


def test_source_diagnostics_exclude_identities_and_cursor_fingerprint():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    stamp = int(now.timestamp()*1000) - 2000
    fingerprint = "a"*64
    result = source_metadata({
        "cursor": f"ntfs-usn:continuous:{stamp}:{fingerprint}",
        "freshness_state": "HEALTHY", "freshness_reason": "CURRENT", "collector_count": 1,
        "hostname": "PRIVATE_IDENTITY", "id": "PRIVATE_IDENTITY", "token": "PRIVATE_SECRET",
    }, now)
    assert result == {
        "freshness_state": "HEALTHY", "freshness_reason": "CURRENT", "collector_count": 1,
        "cursor_class": "continuous", "proof_age_ms": 2000,
    }
    assert "PRIVATE" not in str(result) and fingerprint not in str(result)


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="PostgreSQL required")
def test_actual_activity_diagnostic_excludes_private_values(authenticated_setup, tmp_path):
    client, engine, collector, token, source = authenticated_setup
    response = client.get("/api/v1/activity", params={"source_id": str(source)})
    result = activity_snapshot(engine, source, response, SimpleNamespace(events=[]),
                               tmp_path / "private-marker.sqlite3", [], [])
    assert result["sampled_after_response"] is True and "diagnostic_error" not in result
    assert result["source"]["collector_count"] == 1 and result["quality"] == "UNAVAILABLE"
    encoded = json.dumps(result)
    assert all(value not in encoded
               for value in (str(source), str(collector), token, "private-marker"))
