"""Real PG/API/worker arrival ordering and sensitive read boundaries."""

import json
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select, text, update
from test_windows_audit_events import GEN, HOST, parse, xml
from test_windows_audit_streams import heartbeat

from apps.api.auth import token_hash
from apps.worker.processor import HANDLERS
from packages.contracts.audit import AuditHealth
from packages.shared.jobs import process_one
from packages.shared.models.audit import audit_candidates, audit_correlations, audit_evidence
from packages.shared.models.core import collectors
from packages.shared.models.security import roles


def csrf(client):
    return {
        "Origin": "https://storage.example.test",
        "X-CSRF-Token": client.cookies["__Host-storage_csrf"],
    }


@pytest.fixture
def setup(authenticated_setup):
    client, engine, usn, token, source = authenticated_setup
    audit, audit_token = uuid4(), secrets.token_urlsafe(32)
    with engine.begin() as conn:
        conn.execute(
            insert(collectors).values(
                id=audit,
                source_node_id=source,
                collector_type="AUDIT_WINDOWS",
                token_hash=token_hash(audit_token),
            )
        )
    return client, engine, usn, token, source, audit, audit_token


def post(client, domain, collector, token, records):
    times = [datetime.fromisoformat(r["occurred_at"]) for r in records]
    body = {
        "collector_id": str(collector),
        "batch_id": uuid4().hex,
        "schema_version": 1,
        "sent_at": datetime.now(UTC).isoformat(),
        "records": records,
    }
    if domain != "audit-events":
        body.update(
            first_event_at=min(times).isoformat(),
            last_event_at=max(times).isoformat(),
            record_count=len(records),
        )
    return client.post(
        "/api/v1/ingest/" + domain, json=body, headers={"Authorization": "Bearer " + token}
    )


def seed(
    setup, *, audit_first=False, late_alias=False, prior_identity=True, complete_coverage=True
):
    client, _, usn, usn_token, _, audit, audit_token = setup
    now = datetime.now(UTC) - (timedelta(hours=2) if late_alias else timedelta(seconds=30))
    before, after = now - timedelta(seconds=10), now + timedelta(seconds=10)
    records = [
        {
            "kind": "volume",
            "occurred_at": before.isoformat(),
            "unique_identity": "volume-a",
            "filesystem": "NTFS",
            "mount_aliases": ["C:\\"],
        },
        {
            "kind": "object",
            "occurred_at": before.isoformat(),
            "volume_identity": "volume-a",
            "file_id": "file-a",
            "object_type": "FILE",
            "name": "Отчёт.txt",
            "relative_path": "Pilot/Отчёт.txt",
            "link_count": 1,
        },
    ]
    response = post(client, "inventory", usn, usn_token, records if prior_identity else records[:1])
    assert response.status_code == 202
    if not late_alias:
        response = post(
            client, "inventory", usn, usn_token, [{**records[0], "occurred_at": after.isoformat()}]
        )
        assert response.status_code == 202
    for when in (before, after) if complete_coverage else (before,):
        hb = heartbeat(usn, when)["records"]
        response = post(client, "heartbeat", usn, usn_token, hb)
        assert response.status_code == 202
        health = AuditHealth(
            configured=True,
            state="HEALTHY",
            host_id=HOST,
            generation=GEN,
            boot_id="boot-a",
            last_collected_at=when,
            policy_verified=True,
            sacl_verified=True,
        )
        response = post(
            client,
            "heartbeat",
            audit,
            audit_token,
            [
                {
                    "occurred_at": when.isoformat(),
                    "version": "synthetic",
                    "audit": health.model_dump(mode="json"),
                }
            ],
        )
        assert response.status_code == 202
    access = parse(xml(AccessMask="0x10000")).model_copy(
        update={"occurred_at": now, "volume_id": "volume-a"}
    )
    logon = parse(xml(4624, record=8)).model_copy(update={"occurred_at": before})
    deletion = parse(xml(4660, record=11)).model_copy(
        update={
            "occurred_at": now + timedelta(milliseconds=500),
            "volume_id": "volume-a",
            "linked_record_ids": [10],
        }
    )
    audit_records = [
        {**e.model_dump(mode="json"), "digest": e.digest()} for e in (logon, access, deletion)
    ]
    change = {
        "occurred_at": (now + timedelta(seconds=1)).isoformat(),
        "volume_identity": "volume-a",
        "file_id": "file-a",
        "event_type": "DELETE",
        "old_relative_path": "Pilot/Отчёт.txt",
        "reason_mask": "0x200",
        "source_event_id": "ntfs-usn:" + "a" * 64,
    }
    operations = [
        ("audit-events", audit, audit_token, audit_records),
        ("changes", usn, usn_token, [change]),
    ]
    if not audit_first:
        operations.reverse()
    for domain, collector, token, body in operations:
        response = post(client, domain, collector, token, body)
        assert response.status_code == 202
    return access


def drain(engine):
    for _ in range(100):
        if not process_one(engine, HANDLERS):
            return
    pytest.fail("bounded fixture jobs did not drain")


@pytest.mark.parametrize("audit_first", [True, False])
def test_hourly_alias_witness_revisits_old_delete_and_duplicate_is_inert(setup, audit_first):
    from packages.shared.models.jobs import jobs

    access = seed(setup, audit_first=audit_first, late_alias=True)
    client, engine, usn, token, _, _, _ = setup
    drain(engine)
    with engine.connect() as conn:
        assert conn.execute(select(audit_correlations.c["class"])).scalar_one() == "UNKNOWN"
    response = post(
        client,
        "inventory",
        usn,
        token,
        [
            {
                "kind": "volume",
                "occurred_at": (access.occurred_at + timedelta(hours=1)).isoformat(),
                "unique_identity": "volume-a",
                "filesystem": "NTFS",
                "mount_aliases": ["C:\\"],
            }
        ],
    )
    assert response.status_code == 202
    drain(engine)
    with engine.connect() as conn:
        verdict = conn.execute(select(audit_correlations)).mappings().one()
        count = conn.scalar(select(func.count()).select_from(jobs))
    assert verdict["class"] == "CORRELATED_HIGH"
    assert verdict["actor"]["sid"] == access.sid
    replay = client.post(
        "/api/v1/ingest/inventory",
        json=json.loads(response.request.content),
        headers={"Authorization": "Bearer " + token},
    )
    assert replay.status_code == 202 and replay.json()["duplicate"] is True
    drain(engine)
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(jobs)) == count
        assert conn.scalar(select(func.count()).select_from(audit_correlations)) == 1


@pytest.mark.parametrize("missing", ["identity", "coverage"])
def test_late_alias_does_not_substitute_for_identity_or_coverage(setup, missing):
    access = seed(
        setup,
        late_alias=True,
        prior_identity=missing != "identity",
        complete_coverage=missing != "coverage",
    )
    client, engine, usn, token, _, _, _ = setup
    drain(engine)
    response = post(
        client,
        "inventory",
        usn,
        token,
        [
            {
                "kind": "volume",
                "unique_identity": "volume-a",
                "filesystem": "NTFS",
                "mount_aliases": ["C:\\"],
                "occurred_at": (access.occurred_at + timedelta(hours=1)).isoformat(),
            }
        ],
    )
    assert response.status_code == 202
    drain(engine)
    with engine.connect() as conn:
        verdict = conn.execute(select(audit_correlations)).mappings().one()
    assert verdict["class"] == "ACCESS_OBSERVED" and verdict["actor"] is None
    assert verdict["reason"] == (
        "PATH_TIME_ONLY" if missing == "identity" else "INTERVAL_COVERAGE_UNKNOWN"
    )


def test_alias_reconciliation_pages_retry_without_touching_other_source_or_volume(setup):
    from packages.shared.audit.engine import process
    from packages.shared.models.activity import change_events
    from packages.shared.models.core import source_nodes
    from packages.shared.models.jobs import jobs

    access = seed(setup, late_alias=True)
    client, engine, usn, token, source, _, _ = setup
    drain(engine)
    other = uuid4()
    with engine.begin() as conn:
        conn.execute(
            insert(source_nodes).values(
                id=other,
                source_type="FILESERVER",
                hostname="other.example.test",
                instance_id="other",
            )
        )
        conn.execute(
            insert(change_events),
            [
                dict(
                    source_node_id=source if i < 66 else other,
                    volume_identity="volume-a" if i != 65 else "volume-b",
                    file_id="noise-" + str(i),
                    event_type="WRITE",
                    new_relative_path="Noise/" + str(i),
                    occurred_at=access.occurred_at + timedelta(seconds=45),
                )
                for i in range(67)
            ],
        )
    response = post(
        client,
        "inventory",
        usn,
        token,
        [
            {
                "kind": "volume",
                "unique_identity": "volume-a",
                "filesystem": "NTFS",
                "mount_aliases": ["C:\\"],
                "occurred_at": (access.occurred_at + timedelta(hours=1)).isoformat(),
            }
        ],
    )
    assert response.status_code == 202
    drain(engine)
    with engine.begin() as conn:
        pages = (
            conn.execute(
                select(jobs)
                .where(
                    jobs.c.payload["alias_window"].astext.is_not(None),
                )
                .order_by(jobs.c.created_at)
            )
            .mappings()
            .all()
        )
        assert len(pages) == 3
        assert all(p["status"] == "COMPLETE" for p in pages)
        process(conn, pages[0])
        assert conn.scalar(select(func.count()).select_from(audit_correlations)) == 66
        scoped = conn.execute(
            select(change_events.c.source_node_id, change_events.c.volume_identity).join(
                audit_correlations, audit_correlations.c.change_event_id == change_events.c.id
            )
        ).all()
        assert all(s == source and v == "volume-a" for s, v in scoped)
        assert (
            conn.scalar(
                select(func.count())
                .select_from(jobs)
                .where(
                    jobs.c.payload["alias_window"].astext.is_not(None),
                )
            )
            == 3
        )


@pytest.mark.parametrize("kind", ["equal", "older", "object", "heartbeat", "rejected"])
def test_only_applied_forward_volume_witness_enqueues_alias_window(setup, kind):
    from packages.shared.models.core import volumes
    from packages.shared.models.jobs import ingest_batches, jobs

    access = seed(setup, late_alias=True)
    client, engine, usn, token, _, _, _ = setup
    before = access.occurred_at - timedelta(seconds=10)
    with engine.connect() as conn:
        previous = conn.scalar(select(volumes.c.last_seen_at))
        receipts = conn.scalar(select(func.count()).select_from(ingest_batches))
    volume = {
        "kind": "volume",
        "unique_identity": "volume-a",
        "filesystem": "NTFS",
        "mount_aliases": ["C:\\"],
        "occurred_at": before.isoformat(),
    }
    if kind in ("equal", "older"):
        volume["occurred_at"] = (
            before - timedelta(seconds=1 if kind == "older" else 0)
        ).isoformat()
        response = post(client, "inventory", usn, token, [volume])
    elif kind == "heartbeat":
        response = post(client, "heartbeat", usn, token, heartbeat(usn, before)["records"])
    else:
        obj = {
            "kind": "object",
            "volume_identity": "volume-a",
            "file_id": "file-a",
            "object_type": "FILE",
            "name": "Отчёт.txt",
            "relative_path": "Pilot/Отчёт.txt",
            "occurred_at": before.isoformat(),
        }
        if kind == "rejected":
            volume["occurred_at"] = (access.occurred_at + timedelta(hours=1)).isoformat()
            obj["volume_identity"] = "unregistered-volume"
            response = post(client, "inventory", usn, token, [volume, obj])
        else:
            response = post(client, "inventory", usn, token, [obj])
    assert response.status_code == (409 if kind == "rejected" else 202)
    with engine.connect() as conn:
        assert not conn.scalar(
            select(func.count())
            .select_from(jobs)
            .where(
                jobs.c.payload["alias_window"].astext.is_not(None),
            )
        )
        assert conn.scalar(select(volumes.c.last_seen_at)) == previous
        if kind == "rejected":
            assert conn.scalar(select(func.count()).select_from(ingest_batches)) == receipts


@pytest.mark.parametrize("audit_first", [True, False])
def test_both_arrival_orders_high_delete_and_late_second_sid_ambiguous(setup, audit_first):
    access = seed(setup, audit_first=audit_first)
    client, engine, _, _, _, audit, token = setup
    drain(engine)
    with engine.connect() as conn:
        verdict = conn.execute(select(audit_correlations)).mappings().one()
        change_id = verdict["change_event_id"]
        original_count = conn.scalar(select(func.count()).select_from(audit_candidates))
    assert verdict["class"] == "CORRELATED_HIGH" and verdict["actor"]["account"] == "UserA"
    response = client.get(f"/api/v1/audit/changes/{change_id}")
    assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
    assert len(response.json()["candidates"]) == 3 and response.json()["actor"]["client_ip"] is None
    second = access.model_copy(
        update={
            "account": "UserB",
            "sid": "S-1-5-21-100-200-300-1002",
            "logon_id": 258,
            "record_id": 12,
        }
    )
    response = post(
        client,
        "audit-events",
        audit,
        token,
        [{**second.model_dump(mode="json"), "digest": second.digest()}],
    )
    assert response.status_code == 202
    drain(engine)
    result = client.get(f"/api/v1/audit/changes/{change_id}").json()
    assert result["classification"] == "AMBIGUOUS" and result["actor"] is None
    assert len(result["candidates"]) == original_count + 1
    # Byte-identical evidence remains untouched and reruns do not duplicate links.
    drain(engine)
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(audit_evidence)) == 4


def test_csrf_post_sensitive_filters_and_audit_not_allowed_usn(setup):
    client, _, _, _, source, audit, token = setup
    seed(setup)
    response = client.post("/api/v1/audit/search", json={"account": "UserA"}, headers=csrf(client))
    assert response.status_code == 200 and len(response.json()["items"]) == 3
    assert "UserA" not in str(response.request.url)
    assert client.post("/api/v1/audit/search", json={"account": "UserA"}).status_code == 403
    response = post(
        client,
        "changes",
        audit,
        token,
        [
            {
                "occurred_at": datetime.now(UTC).isoformat(),
                "volume_identity": "volume-a",
                "file_id": "fake",
                "event_type": "WRITE",
            }
        ],
    )
    assert response.status_code == 403
    assert client.get(f"/api/v1/audit/sources/{source}").status_code == 200


@pytest.mark.parametrize("role", ["viewer", "analyst", "storage_operator", "auditor"])
def test_direct_sensitive_reads_403_for_all_non_admin_roles(authenticated_setup, role):
    client, engine, _, _, source = authenticated_setup
    with engine.begin() as conn:
        conn.execute(update(roles).values(code=role))
    for path in (
        "/api/v1/activity",
        f"/api/v1/audit/sources/{source}",
        f"/api/v1/audit/changes/{uuid4()}",
        f"/api/v1/audit/changes/{uuid4()}/coverage",
    ):
        response = client.get(path)
        assert response.status_code == 403 and response.json() == {"detail": "AUTH_FORBIDDEN"}
    response = client.post("/api/v1/audit/search", json={"account": "UserA"}, headers=csrf(client))
    assert response.status_code == 403
    assert client.get("/api/v1/overview").status_code == 200
    client.cookies.clear()
    assert client.get(f"/api/v1/audit/sources/{source}").status_code == 401


def test_unconfigured_audit_does_not_change_usn_health(setup):
    client, engine, usn, token, source, audit, audit_token = setup
    now = datetime.now(UTC)
    response = post(client, "heartbeat", usn, token, heartbeat(usn, now)["records"])
    assert response.status_code == 202
    health = AuditHealth(configured=False, state="NOT_CONFIGURED", host_id=HOST)
    response = post(
        client,
        "heartbeat",
        audit,
        audit_token,
        [
            {
                "occurred_at": now.isoformat(),
                "version": "synthetic",
                "audit": health.model_dump(mode="json"),
            }
        ],
    )
    assert response.status_code == 202
    assert client.get(f"/api/v1/audit/sources/{source}").json()["state"] == "NOT_CONFIGURED"
    assert client.get("/api/v1/activity").json()["continuity"] == "CONTINUOUS_SINCE_BASELINE"


def test_100k_indexed_bounded_candidate_plan(ingest_setup):
    from packages.shared.audit.engine import candidate_query
    from packages.shared.audit.keys import path_key

    _, engine, collector, _, source = ingest_setup
    now = datetime.now(UTC)
    with engine.begin() as conn:
        # Synthetic normalized rows, no Windows/production evidence or credentials.
        conn.execute(
            text("""INSERT INTO windows_audit_evidence
          (id,source_node_id,audit_collector_id,host_id,generation,channel,record_id,event_id,
           occurred_at,volume_id,path_key,payload,digest)
          SELECT gen_random_uuid(),:source,:collector,:host,:generation,'Security',i,4663,
                 :now - i * interval '1 second','volume-a',:key,'{}'::jsonb,repeat('a',64)
          FROM generate_series(1,100000) i"""),
            {
                "source": source,
                "collector": collector,
                "host": HOST,
                "generation": GEN,
                "now": now,
                "key": path_key(r"C:\Pilot\Отчёт.txt"),
            },
        )
        conn.execute(text("ANALYZE windows_audit_evidence"))
        query = candidate_query(source, "volume-a", [r"C:\Pilot\Отчёт.txt"], now)
        compiled = query.compile(dialect=engine.dialect, compile_kwargs={"literal_binds": True})
        plan = conn.execute(
            text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + str(compiled))
        ).scalar_one()
    encoded = json.dumps(plan)
    assert (
        "ix_audit_source_volume_path_time" in encoded or "ix_audit_source_time" in encoded
    ) and "Seq Scan" not in encoded
    assert plan[0]["Plan"]["Actual Rows"] <= 65


def test_100k_alias_pages_bound_reads_with_other_sources_volumes_and_old_rows(ingest_setup):
    from packages.shared.audit.engine import PAGE, alias_window_query
    from packages.shared.models.activity import change_events
    from packages.shared.models.core import source_nodes

    _, engine, _, _, source = ingest_setup
    other, now = uuid4(), datetime.now(UTC)
    with engine.begin() as conn:
        conn.execute(
            insert(source_nodes).values(
                id=other,
                source_type="FILESERVER",
                hostname="other.example.test",
                instance_id="other",
            )
        )
        conn.execute(
            text("""INSERT INTO change_events
          (id,source_node_id,volume_identity,event_type,occurred_at,file_id)
          SELECT gen_random_uuid(),
            CASE WHEN i BETWEEN 20066 AND 40000 THEN :other ELSE :source END,
            CASE WHEN i BETWEEN 66 AND 20065 THEN 'volume-b' ELSE 'volume-a' END,
            'WRITE', CASE WHEN i>40000 THEN :now - interval '2 hours' ELSE :now END,
            'synthetic-' || i::text FROM generate_series(1,100000) i"""),
            {"source": source, "other": other, "now": now},
        )
        conn.execute(text("ANALYZE change_events"))
        ids = (
            conn.execute(
                select(change_events.c.id)
                .where(
                    change_events.c.source_node_id == source,
                    change_events.c.volume_identity == "volume-a",
                    change_events.c.occurred_at == now,
                )
                .order_by(change_events.c.id)
            )
            .scalars()
            .all()
        )
        assert len(ids) == 65
        seen = []
        for offset in (0, PAGE, PAGE * 2):
            query = alias_window_query(
                source,
                "volume-a",
                now - timedelta(hours=1),
                now + timedelta(seconds=1),
                after_at=now if offset else None,
                after=ids[offset - 1] if offset else None,
            )
            compiled = query.compile(dialect=engine.dialect, compile_kwargs={"literal_binds": True})
            plan = conn.execute(
                text(
                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + str(compiled),
                )
            ).scalar_one()[0]["Plan"]

            def nodes(p):
                return [p] + [n for child in p.get("Plans", []) for n in nodes(child)]

            assert all(n["Node Type"] != "Seq Scan" for n in nodes(plan))
            assert max(n.get("Rows Removed by Filter", 0) for n in nodes(plan)) <= 65, json.dumps(
                plan
            )
            assert plan["Shared Hit Blocks"] + plan.get("Shared Read Blocks", 0) <= 128, json.dumps(
                plan
            )
            assert plan["Actual Rows"] <= PAGE + 1
            seen.extend(row["id"] for row in conn.execute(query).mappings().all()[:PAGE])
        assert seen == ids


def test_recent_heartbeat_with_lagging_usn_cursor_cannot_close_historical_window(setup):
    from packages.shared.models.audit import audit_health_observations

    seed(setup)
    _, engine, usn, *_ = setup
    with engine.begin() as conn:
        row = (
            conn.execute(
                select(audit_health_observations)
                .where(audit_health_observations.c.collector_id == usn)
                .order_by(audit_health_observations.c.occurred_at.desc())
                .limit(1)
            )
            .mappings()
            .one()
        )
        payload = dict(row["payload"])
        payload["cursor"] = (
            f"ntfs-usn:continuous:{int((row['occurred_at'].timestamp() - 14) * 1000)}:" + "a" * 64
        )
        conn.execute(
            update(audit_health_observations)
            .where(audit_health_observations.c.id == row["id"])
            .values(payload=payload)
        )
    drain(engine)
    with engine.connect() as conn:
        verdict = conn.execute(select(audit_correlations)).mappings().one()
    assert verdict["class"] != "CORRELATED_HIGH" and verdict["actor"] is None


def test_pre_upgrade_usn_receipt_replays_after_additive_audit_contract(authenticated_setup):
    from hashlib import sha256

    from packages.contracts.common import BatchEnvelope
    from packages.contracts.heartbeat import HeartbeatRecord
    from packages.shared.models.jobs import ingest_batches

    client, engine, usn, token, _ = authenticated_setup
    body = heartbeat(usn, datetime.now(UTC))
    response = client.post(
        "/api/v1/ingest/heartbeat", json=body, headers={"Authorization": "Bearer " + token}
    )
    assert response.status_code == 202
    normalized = BatchEnvelope[HeartbeatRecord].model_validate(body).model_dump(mode="json")
    for record in normalized["records"]:
        record.pop("audit", None)  # The published pre-B HeartbeatRecord has no audit property.
    digest = sha256(
        json.dumps(
            {"kind": "heartbeat", "batch": normalized},
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    with engine.begin() as conn:
        conn.execute(
            update(ingest_batches)
            .where(ingest_batches.c.collector_id == usn)
            .values(payload_sha256=digest)
        )
    response = client.post(
        "/api/v1/ingest/heartbeat", json=body, headers={"Authorization": "Bearer " + token}
    )
    assert response.status_code == 202 and response.json()["duplicate"] is True


def test_later_read_cannot_lend_identity_to_earlier_delete_chain(setup):
    from packages.shared.models.audit import audit_identity_observations

    access = seed(setup)
    client, engine, _, _, _, audit, token = setup
    with engine.begin() as conn:
        conn.execute(
            update(audit_identity_observations).values(
                occurred_at=access.occurred_at + timedelta(milliseconds=250)
            )
        )
    read = access.model_copy(
        update={
            "record_id": 12,
            "access_mask": 1,
            "occurred_at": access.occurred_at + timedelta(milliseconds=500),
        }
    )
    response = post(
        client,
        "audit-events",
        audit,
        token,
        [{**read.model_dump(mode="json"), "digest": read.digest()}],
    )
    assert response.status_code == 202
    drain(engine)
    with engine.connect() as conn:
        verdict = conn.execute(select(audit_correlations)).mappings().one()
    assert verdict["class"] != "CORRELATED_HIGH" and verdict["actor"] is None


@pytest.mark.parametrize("hazard", ["metadata", "same_time_conflict", "retired_collector"])
def test_prior_identity_cannot_survive_uncertain_lineage(setup, hazard):
    from packages.shared.models.activity import change_events
    from packages.shared.models.audit import audit_identity_observations

    access = seed(setup)
    _, engine, usn, _, _, _, _ = setup
    with engine.begin() as conn:
        if hazard == "metadata":
            change = dict(conn.execute(select(change_events)).mappings().one())
            change.update(
                id=uuid4(),
                event_type="METADATA_CHANGE",
                occurred_at=access.occurred_at - timedelta(seconds=1),
                source_event_id="ntfs-usn:" + "b" * 64,
            )
            conn.execute(insert(change_events).values(**change))
        elif hazard == "same_time_conflict":
            witness = dict(conn.execute(select(audit_identity_observations)).mappings().one())
            conn.execute(insert(audit_identity_observations).values(**(witness | {"id": uuid4()})))
            witness.update(id=uuid4(), payload=witness["payload"] | {"link_count": 2})
            conn.execute(insert(audit_identity_observations).values(**witness))
        else:
            conn.execute(update(collectors).where(collectors.c.id == usn).values(enabled=False))
            conn.execute(
                insert(collectors).values(
                    id=uuid4(),
                    source_node_id=setup[4],
                    collector_type="WINDOWS",
                    token_hash=token_hash(secrets.token_urlsafe(32)),
                )
            )
    drain(engine)
    with engine.connect() as conn:
        verdict = (
            conn.execute(
                select(audit_correlations)
                .join(change_events, change_events.c.id == audit_correlations.c.change_event_id)
                .where(change_events.c.event_type == "DELETE")
            )
            .mappings()
            .one()
        )
    assert verdict["class"] != "CORRELATED_HIGH" and verdict["actor"] is None


def test_late_metadata_receipt_retracts_high_across_prior_identity_window(setup):
    access = seed(setup)
    client, engine, usn, token, _, _, _ = setup
    drain(engine)
    with engine.connect() as conn:
        assert conn.execute(select(audit_correlations.c["class"])).scalar_one() == "CORRELATED_HIGH"
    response = post(
        client,
        "changes",
        usn,
        token,
        [
            {
                "occurred_at": (access.occurred_at - timedelta(seconds=5)).isoformat(),
                "event_type": "METADATA_CHANGE",
                "volume_identity": "volume-a",
                "file_id": "file-a",
                "new_relative_path": "Pilot/Отчёт.txt",
                "reason_mask": "0x10000",
                "source_event_id": "ntfs-usn:" + "b" * 64,
            }
        ],
    )
    assert response.status_code == 202
    drain(engine)
    with engine.connect() as conn:
        from packages.shared.models.activity import change_events

        verdict = (
            conn.execute(
                select(audit_correlations)
                .join(change_events, change_events.c.id == audit_correlations.c.change_event_id)
                .where(change_events.c.event_type == "DELETE")
            )
            .mappings()
            .one()
        )
    assert verdict["class"] != "CORRELATED_HIGH" and verdict["actor"] is None


@pytest.mark.parametrize(
    "collected,expected", [(None, "UNKNOWN"), (-7200, "STALE"), (3600, "UNKNOWN")]
)
def test_fresh_delivery_cannot_mark_stalled_capture_healthy(setup, collected, expected):
    client, _, _, _, source, audit, token = setup
    now = datetime.now(UTC)
    health = AuditHealth(
        configured=True,
        state="HEALTHY",
        host_id=HOST,
        policy_verified=True,
        sacl_verified=True,
        last_collected_at=now + timedelta(seconds=collected) if collected is not None else None,
    )
    response = post(
        client,
        "heartbeat",
        audit,
        token,
        [
            {
                "occurred_at": now.isoformat(),
                "version": "synthetic",
                "audit": health.model_dump(mode="json"),
            }
        ],
    )
    assert response.status_code == 202
    assert client.get(f"/api/v1/audit/sources/{source}").json()["state"] == expected


def test_receipt_workers_serialize_before_any_correlation_read(setup, monkeypatch):
    import threading

    from packages.shared.audit import engine as matcher
    from packages.shared.jobs import lock_key
    from packages.shared.models.jobs import ingest_batches

    access = seed(setup)
    client, engine, _, _, source, audit, token = setup
    entered, release = threading.Event(), threading.Event()
    original = matcher.decide
    failures = []

    def paused(*args, **kwargs):
        verdict = original(*args, **kwargs)
        if threading.current_thread().name == "audit-old":
            entered.set()
            assert release.wait(10), "fixture worker was not released"
        return verdict

    monkeypatch.setattr(matcher, "decide", paused)
    with engine.connect() as conn:
        receipt = conn.scalar(select(ingest_batches.c.id).where(ingest_batches.c.kind == "changes"))

    def older():
        try:
            with engine.begin() as conn:
                matcher.process(conn, {"payload": {"receipt_id": str(receipt)}})
        except Exception as error:
            failures.append(type(error).__name__)

    thread = threading.Thread(target=older, name="audit-old")
    thread.start()
    try:
        assert entered.wait(10)
        # A different receipt must not read old candidates while this source is owned.
        with engine.begin() as conn:
            assert (
                conn.scalar(
                    select(func.pg_try_advisory_xact_lock(lock_key("audit-source:" + str(source))))
                )
                is False
            )
        second = access.model_copy(
            update={
                "account": "UserB",
                "sid": "S-1-5-21-100-200-300-1002",
                "logon_id": 258,
                "record_id": 12,
            }
        )
        response = post(
            client,
            "audit-events",
            audit,
            token,
            [{**second.model_dump(mode="json"), "digest": second.digest()}],
        )
        assert response.status_code == 202
    finally:
        release.set()
        thread.join(10)
    assert not thread.is_alive() and not failures
    drain(engine)
    with engine.connect() as conn:
        verdict = conn.execute(select(audit_correlations)).mappings().one()
    assert verdict["class"] == "AMBIGUOUS" and verdict["actor"] is None
