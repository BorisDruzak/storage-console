import hashlib
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select

from packages.shared.models.core import collectors, filesystem_objects, object_path_history
from packages.shared.models.jobs import ingest_batches

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="PostgreSQL required")
START = datetime(2026, 1, 1, tzinfo=UTC)


def upload(setup, kind, records, second, batch_id=None, status=202):
    client, _, collector, token, _ = setup
    at = (START + timedelta(seconds=second)).isoformat()
    payload = dict(
        collector_id=str(collector),
        batch_id=batch_id or f"{kind}-{second}-{records[0].get('relative_path', 'event')}",
        schema_version=1,
        sent_at=at,
        first_event_at=at,
        last_event_at=at,
        record_count=len(records),
        records=[dict(occurred_at=at, **record) for record in records],
    )
    response = client.post(
        f"/api/v1/ingest/{kind}",
        json=payload,
        headers={"Authorization": "Bearer " + token},
    )
    assert response.status_code == status, response.json()
    return response.json()


def object_record(path, count=2, parent=None):
    return dict(
        kind="object",
        volume_identity="v",
        file_id="42",
        parent_file_id=parent,
        object_type="FILE",
        name=path.rsplit("/", 1)[-1],
        relative_path=path,
        link_count=count,
        size_bytes=10,
    )


def initial(setup):
    upload(setup, "inventory", [dict(kind="volume", unique_identity="v", filesystem="NTFS")], 0)


def paths(setup):
    with setup[1].connect() as connection:
        objects = connection.execute(select(filesystem_objects)).mappings().all()
        history = connection.execute(select(object_path_history)).mappings().all()
    assert len(objects) == 1
    active = {row["relative_path"] for row in history if row["valid_until_at"] is None}
    return objects[0], active, history


def change_record(event, old=None, new=None):
    return dict(
        volume_identity="v",
        file_id="42",
        event_type=event,
        old_relative_path=old,
        new_relative_path=new,
    )


def test_two_unchanged_scans_preserve_two_paths_without_interval_churn(ingest_setup):
    initial(ingest_setup)
    for second in (1, 2):
        upload(ingest_setup, "inventory", [object_record("a/x", parent="a")], second)
        upload(ingest_setup, "inventory", [object_record("b/x", parent="b")], second)
    obj, active, history = paths(ingest_setup)
    assert active == {"a/x", "b/x"}
    assert len(history) == 2
    assert obj["current_relative_path"] == "a/x"
    assert obj["parent_file_id"] == "a"


def test_delayed_independent_alias_survives_newer_object_metadata(ingest_setup):
    initial(ingest_setup)
    upload(ingest_setup, "inventory", [object_record("a/x")], 10)
    upload(ingest_setup, "inventory", [object_record("b/x")], 5)
    obj, active, _ = paths(ingest_setup)
    assert active == {"a/x", "b/x"}
    assert obj["last_seen_at"] == START + timedelta(seconds=10)
    assert obj["first_seen_at"] == START + timedelta(seconds=5)


def test_rename_one_preserves_other_alias_and_unknown_parent(ingest_setup):
    initial(ingest_setup)
    upload(ingest_setup, "inventory", [object_record("a/x", parent="a")], 1)
    upload(ingest_setup, "inventory", [object_record("b/x", parent="b")], 2)
    upload(ingest_setup, "changes", [change_record("RENAME", "a/x", "c/y")], 3)
    obj, active, history = paths(ingest_setup)
    assert active == {"b/x", "c/y"}
    assert len(history) == 3
    assert obj["current_relative_path"] == "b/x"
    assert obj["parent_file_id"] == "b"


def test_explicit_path_delete_does_not_delete_other_alias(ingest_setup):
    initial(ingest_setup)
    upload(ingest_setup, "inventory", [object_record("a/x")], 1)
    upload(ingest_setup, "inventory", [object_record("b/x")], 2)
    upload(ingest_setup, "changes", [change_record("DELETE", "b/x")], 3)
    obj, active, _ = paths(ingest_setup)
    assert active == {"a/x"}
    assert obj["deleted_at"] is None


def test_last_observed_alias_delete_does_not_invent_whole_object_deletion(ingest_setup):
    initial(ingest_setup)
    upload(ingest_setup, "inventory", [object_record("a/x")], 1)
    upload(ingest_setup, "changes", [change_record("DELETE", "a/x")], 10)
    obj, active, _ = paths(ingest_setup)
    assert active == set()
    assert obj["deleted_at"] is None


def test_old_whole_delete_is_not_reinstated_after_resurrection_and_alias_removal(ingest_setup):
    initial(ingest_setup)
    upload(ingest_setup, "inventory", [object_record("a/x")], 1)
    upload(ingest_setup, "changes", [change_record("DELETE")], 10)
    upload(ingest_setup, "inventory", [object_record("a/x")], 20)
    upload(ingest_setup, "changes", [change_record("DELETE", "a/x")], 30)
    obj, active, _ = paths(ingest_setup)
    assert active == set()
    assert obj["deleted_at"] is None


def test_count_one_proof_blocks_stale_alias_but_preserves_later_one(ingest_setup):
    initial(ingest_setup)
    upload(ingest_setup, "inventory", [object_record("a/x")], 1)
    upload(ingest_setup, "inventory", [object_record("b/x")], 12)
    upload(ingest_setup, "inventory", [object_record("a/x", count=1)], 10)
    upload(ingest_setup, "inventory", [object_record("c/x")], 8)
    _, active, _ = paths(ingest_setup)
    assert active == {"a/x", "b/x"}


def test_contradictory_explicit_single_link_proof_rolls_back(ingest_setup):
    initial(ingest_setup)
    upload(ingest_setup, "inventory", [object_record("a/x", count=1)], 1)
    result = upload(ingest_setup, "inventory", [object_record("b/x", count=1)], 1, status=409)
    assert result == {"detail": "SOLE_PATH_CONFLICT"}
    obj, active, history = paths(ingest_setup)
    assert active == {"a/x"}
    assert len(history) == 1
    assert obj["current_relative_path"] == "a/x"


def test_path_removal_watermark_survives_later_path_resurrection(ingest_setup):
    initial(ingest_setup)
    upload(ingest_setup, "inventory", [object_record("a/x")], 1)
    upload(ingest_setup, "changes", [change_record("DELETE", "a/x")], 10)
    upload(ingest_setup, "inventory", [object_record("a/x")], 20)
    upload(ingest_setup, "inventory", [object_record("a/x")], 9)
    upload(ingest_setup, "changes", [change_record("DELETE", "a/x")], 8)
    _, active, history = paths(ingest_setup)
    assert active == {"a/x"}
    assert len(history) == 2
    active_interval = next(row for row in history if row["valid_until_at"] is None)
    assert active_interval["valid_from_at"] == START + timedelta(seconds=20)


@pytest.mark.parametrize("removal", ["path", "whole", "sole"])
def test_late_removal_splits_history_without_losing_newer_positive_path(ingest_setup, removal):
    initial(ingest_setup)
    upload(ingest_setup, "inventory", [object_record("a/x")], 1)
    upload(ingest_setup, "inventory", [object_record("a/x")], 20)
    if removal == "sole":
        upload(ingest_setup, "inventory", [object_record("b/x", count=1)], 10)
    else:
        old = "a/x" if removal == "path" else None
        upload(ingest_setup, "changes", [change_record("DELETE", old)], 10)
    obj, active, history = paths(ingest_setup)
    assert "a/x" in active and obj["deleted_at"] is None
    intervals = sorted(
        (row["valid_from_at"], row["valid_until_at"])
        for row in history
        if row["relative_path"] == "a/x"
    )
    assert intervals == [
        (START + timedelta(seconds=1), START + timedelta(seconds=10)),
        (START + timedelta(seconds=20), None),
    ]
    # Older/replayed removals cannot split the supported post-removal interval again.
    upload(ingest_setup, "changes", [change_record("DELETE", "a/x")], 8)
    _, active_after, history_after = paths(ingest_setup)
    assert active_after == active and len(history_after) == len(history)


def test_whole_delete_resurrection_retains_negative_watermark(ingest_setup):
    initial(ingest_setup)
    upload(ingest_setup, "inventory", [object_record("a/x")], 1)
    upload(ingest_setup, "changes", [change_record("DELETE")], 10)
    _, active, _ = paths(ingest_setup)
    assert active == set()
    upload(ingest_setup, "inventory", [object_record("a/x")], 20)
    upload(ingest_setup, "inventory", [object_record("b/x")], 9)
    obj, active, history = paths(ingest_setup)
    assert active == {"a/x"}
    assert obj["deleted_at"] is None
    assert len(history) == 2


def test_legacy_unknown_count_does_not_erase_known_aliases(ingest_setup):
    initial(ingest_setup)
    upload(ingest_setup, "inventory", [object_record("a/x")], 1)
    upload(ingest_setup, "inventory", [object_record("b/x")], 2)
    upload(ingest_setup, "inventory", [object_record("a/x", count=None)], 3)
    _, active, history = paths(ingest_setup)
    assert active == {"a/x", "b/x"}
    assert len(history) == 2


@pytest.mark.parametrize("event, expected", [("DELETE", set()), ("RENAME", {"b/x"})])
def test_change_before_first_inventory_hydrates_dated_paths(ingest_setup, event, expected):
    initial(ingest_setup)
    record = change_record(
        event, "a/x" if event == "RENAME" else None, "b/x" if event == "RENAME" else None
    )
    upload(ingest_setup, "changes", [record], 10)
    upload(ingest_setup, "inventory", [object_record("a/x")], 5)
    obj, active, _ = paths(ingest_setup)
    assert active == expected
    assert obj["last_seen_at"] == START + timedelta(seconds=10)


def test_equal_time_delete_wins_over_replayed_positive_evidence(ingest_setup):
    initial(ingest_setup)
    upload(ingest_setup, "inventory", [object_record("a/x")], 1)
    upload(ingest_setup, "changes", [change_record("DELETE", "a/x")], 10)
    upload(ingest_setup, "inventory", [object_record("a/x")], 10)
    _, active, _ = paths(ingest_setup)
    assert active == set()


def test_legacy_same_time_path_replacement_remains_accepted(ingest_setup):
    initial(ingest_setup)
    upload(ingest_setup, "inventory", [object_record("a/x", count=None)], 1)
    upload(ingest_setup, "inventory", [object_record("b/x", count=None)], 1)
    _, active, _ = paths(ingest_setup)
    assert active == {"b/x"}


def test_legacy_equal_time_cycle_preserves_last_path_but_explicit_delete_wins(ingest_setup):
    initial(ingest_setup)
    for n, path in enumerate(("a/x", "b/x", "a/x")):
        upload(ingest_setup, "inventory", [object_record(path, count=None)], 1, f"cycle-{n}")
    _, active, _ = paths(ingest_setup)
    assert active == {"a/x"}
    upload(ingest_setup, "changes", [change_record("DELETE", "a/x")], 2)
    upload(ingest_setup, "inventory", [object_record("a/x", count=None)], 2, "after-delete")
    _, active, _ = paths(ingest_setup)
    assert active == set()


def test_stale_legacy_inventory_after_rename_keeps_single_path_semantics(ingest_setup):
    initial(ingest_setup)
    upload(ingest_setup, "inventory", [object_record("a/x", count=None)], 1)
    upload(ingest_setup, "changes", [change_record("RENAME", "a/x", "b/x")], 10)
    upload(ingest_setup, "inventory", [object_record("c/x", count=None)], 5)
    _, active, _ = paths(ingest_setup)
    assert active == {"b/x"}


def test_pre_upgrade_receipt_replays_and_meaningful_count_change_conflicts(ingest_setup):
    from test_path_alias_contracts import OLD_BATCH, OLD_RECORD, digest

    client, engine, collector, token, _ = ingest_setup
    old = dict(OLD_BATCH, collector_id=str(collector))
    with engine.begin() as connection:
        connection.execute(
            insert(ingest_batches).values(
                collector_id=collector,
                batch_id=old["batch_id"],
                schema_version=1,
                kind="inventory",
                payload_sha256=digest(old),
                record_count=1,
                sent_at=START,
                first_event_at=START,
                last_event_at=START,
                processed_at=START,
            )
        )
    response = client.post(
        "/api/v1/ingest/inventory", json=old, headers={"Authorization": "Bearer " + token}
    )
    assert response.status_code == 202
    assert response.json()["duplicate"] is True
    changed = dict(old, records=[dict(OLD_RECORD, link_count=2)])
    response = client.post(
        "/api/v1/ingest/inventory", json=changed, headers={"Authorization": "Bearer " + token}
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "BATCH_ID_CONFLICT"}
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(ingest_batches)) == 1
        assert connection.scalar(select(func.count()).select_from(filesystem_objects)) == 0


def test_full_length_unicode_path_uses_bounded_digest_index(ingest_setup):
    initial(ingest_setup)
    long_path = "界" * 32765 + "/x"
    upload(ingest_setup, "inventory", [object_record(long_path)], 1, "long-first")
    upload(ingest_setup, "inventory", [object_record("b/x")], 2)
    upload(ingest_setup, "inventory", [object_record(long_path)], 3, "long-again")
    _, active, history = paths(ingest_setup)
    assert active == {long_path, "b/x"}
    assert len(history) == 2


def test_digest_collision_rolls_back_metadata_and_receipt(ingest_setup, monkeypatch):
    from packages.shared.ingest import paths as path_helpers

    monkeypatch.setattr(path_helpers, "digest", lambda _: "a" * 64)
    initial(ingest_setup)
    upload(ingest_setup, "inventory", [object_record("a/x")], 1)
    conflict = object_record("b/x")
    conflict["size_bytes"] = 99
    result = upload(ingest_setup, "inventory", [conflict], 2, status=409)
    assert result == {"detail": "PATH_DIGEST_CONFLICT"}
    obj, active, history = paths(ingest_setup)
    assert obj["size_bytes"] == 10
    assert obj["last_seen_at"] == START + timedelta(seconds=1)
    assert active == {"a/x"}
    assert len(history) == 1
    with ingest_setup[1].connect() as connection:
        assert connection.scalar(select(func.count()).select_from(ingest_batches)) == 2


def test_two_collectors_on_one_source_preserve_simultaneous_aliases(ingest_setup):
    initial(ingest_setup)
    client, engine, _, _, source = ingest_setup
    collector, token = uuid4(), secrets.token_urlsafe(32)
    with engine.begin() as connection:
        connection.execute(
            insert(collectors).values(
                id=collector,
                source_node_id=source,
                collector_type="WINDOWS",
                token_hash=hashlib.sha256(("collector:" + token).encode()).hexdigest(),
            )
        )
    second = (client, engine, collector, token, source)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(upload, setup, "inventory", [object_record(path)], 1)
            for setup, path in [(ingest_setup, "a/x"), (second, "b/x")]
        ]
        for future in futures:
            future.result()
    _, active, history = paths(ingest_setup)
    assert active == {"a/x", "b/x"}
    assert len(history) == 2


def test_first_inventory_hydrates_all_event_keyset_pages(ingest_setup):
    from packages.shared.models.activity import change_events

    initial(ingest_setup)
    source = ingest_setup[4]
    events = [
        dict(
            source_node_id=source,
            volume_identity="v",
            file_id="42",
            event_type="WRITE",
            occurred_at=START + timedelta(seconds=n),
            old_relative_path=None,
            new_relative_path=None,
        )
        for n in range(1, 514)
    ]
    events[-1].update(event_type="RENAME", old_relative_path="a/x", new_relative_path="b/x")
    with ingest_setup[1].begin() as connection:
        connection.execute(insert(change_events), events)
    upload(ingest_setup, "inventory", [object_record("a/x")], 0)
    obj, active, _ = paths(ingest_setup)
    assert obj["last_seen_at"] == START + timedelta(seconds=513)
    assert active == {"b/x"}
