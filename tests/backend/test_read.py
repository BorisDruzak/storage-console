import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import insert, update

from packages.shared.models.core import collectors, source_nodes
from packages.shared.models.health import health_findings, health_policies, health_signals

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="PostgreSQL required")


def upload(client, collector, token, at):
    stamp = at.isoformat()
    payload = dict(
        collector_id=str(collector),
        batch_id=str(uuid4()),
        schema_version=1,
        sent_at=stamp,
        first_event_at=stamp,
        last_event_at=stamp,
        record_count=1,
        records=[dict(occurred_at=stamp, version="synthetic", cursor="42", lag_seconds=2)],
    )
    assert (
        client.post(
            "/api/v1/ingest/heartbeat", json=payload, headers={"Authorization": "Bearer " + token}
        ).status_code
        == 202
    )


def test_unseen_empty_and_missing_data_are_explicit_unknown(ingest_setup):
    client, _, _, _, source = ingest_setup
    overview = client.get("/api/v1/overview")
    assert overview.status_code == 200
    assert overview.json()["counts"]["volumes"] == 0
    assert overview.json()["overall_state"] == "UNKNOWN"
    assert overview.json()["freshness"]["state"] == "UNKNOWN"
    assert overview.json()["freshness"]["unknown_source_count"] == 1
    assert len(overview.json()["domains"]) == 10
    assert all(domain["state"] == "UNKNOWN" for domain in overview.json()["domains"])
    fresh = client.get(f"/api/v1/sources/{source}/freshness").json()
    assert fresh["state"] == "UNKNOWN"
    assert fresh["reason"] == "NEVER_SEEN"
    assert client.get(f"/api/v1/sources/{uuid4()}").status_code == 404
    assert client.get(f"/api/v1/sources/{uuid4()}/freshness").status_code == 404
    assert client.get("/api/v1/volumes").json()["items"] == []
    assert client.get("/api/v1/shares").json()["items"] == []
    assert all(
        d["state"] == "UNKNOWN" for d in client.get("/api/v1/health/domains").json()["domains"]
    )


@pytest.mark.parametrize(
    "age,expected",
    [(0, "HEALTHY"), (90, "OBSERVE"), (150, "WARNING"), (600, "CRITICAL"), (-60, "UNKNOWN")],
)
def test_source_event_age_controls_freshness_despite_recent_upload(ingest_setup, age, expected):
    client, _, collector, token, source = ingest_setup
    upload(client, collector, token, datetime.now(UTC) - timedelta(seconds=age))
    response = client.get(f"/api/v1/sources/{source}/freshness")
    assert response.status_code == 200
    fresh = response.json()
    assert fresh["state"] == expected
    assert fresh["cursor"] == "42"
    assert fresh["lag_seconds"] == 2
    assert fresh["last_event_at"].endswith("Z")
    # Collector transport freshness does not establish policy-evaluated domain health.
    assert all(
        d["state"] == "UNKNOWN" for d in client.get("/api/v1/health/domains").json()["domains"]
    )


def test_source_pagination_and_projection_exclude_credentials(ingest_setup):
    client, engine, _, _, _ = ingest_setup
    with engine.begin() as connection:
        for index in range(3):
            connection.execute(
                insert(source_nodes).values(
                    source_type="PBS", hostname=f"synthetic-{index}", instance_id=str(uuid4())
                )
            )
    first = client.get("/api/v1/sources?limit=2&offset=0").json()
    second = client.get("/api/v1/sources?limit=2&offset=2").json()
    assert first["total"] == second["total"] == 4
    assert len({s["id"] for s in first["items"] + second["items"]}) == 4
    assert "token_hash" not in str(first)
    for query in ["limit=0", "limit=101", "offset=-1", "offset=1000001"]:
        assert client.get("/api/v1/sources?" + query).status_code == 422


def test_domain_health_reads_fresh_policy_findings_and_demotes_stale_evidence(ingest_setup):
    client, engine, collector, token, source = ingest_setup
    upload(client, collector, token, datetime.now(UTC))
    signal, policy = uuid4(), uuid4()
    with engine.begin() as connection:
        connection.execute(
            insert(health_policies).values(
                id=policy,
                name="synthetic-capacity",
                domain="CAPACITY",
                policy_type="CAPACITY",
                parameters={},
            )
        )
        connection.execute(
            insert(health_signals).values(
                id=signal,
                source_node_id=source,
                domain="CAPACITY",
                signal_type="FREE_SPACE",
                measurement={},
                occurred_at=datetime.now(UTC),
            )
        )
        connection.execute(
            insert(health_findings).values(
                signal_id=signal,
                policy_id=policy,
                state="HEALTHY",
                cause_class="POLICY",
                fingerprint="a" * 64,
                evaluated_at=datetime.now(UTC),
            )
        )

    def capacity():
        return next(
            d
            for d in client.get("/api/v1/health/domains").json()["domains"]
            if d["domain"] == "CAPACITY"
        )

    assert capacity()["state"] == "HEALTHY"
    assert client.get("/api/v1/overview").json()["overall_state"] == "UNKNOWN"
    with engine.begin() as connection:
        connection.execute(
            update(health_signals)
            .where(health_signals.c.id == signal)
            .values(occurred_at=datetime.now(UTC) - timedelta(hours=1))
        )
    assert capacity()["state"] == "UNKNOWN"
    with engine.begin() as connection:
        connection.execute(update(collectors).values(enabled=False))
    assert client.get(f"/api/v1/sources/{source}/freshness").json()["state"] == "UNKNOWN"


def test_critical_domain_keeps_unknown_scope_coverage_visible(ingest_setup):
    client, engine, collector, token, source = ingest_setup
    upload(client, collector, token, datetime.now(UTC))
    policy = uuid4()
    with engine.begin() as connection:
        connection.execute(
            insert(health_policies).values(
                id=policy,
                name="synthetic-policy",
                domain="CAPACITY",
                policy_type="CAPACITY",
                parameters={},
            )
        )
        for index, (state, age) in enumerate([("HEALTHY", 3600), ("CRITICAL", 0)]):
            signal = uuid4()
            connection.execute(
                insert(health_signals).values(
                    id=signal,
                    source_node_id=source,
                    domain="CAPACITY",
                    signal_type="FREE_SPACE",
                    scope_identity=str(index),
                    measurement={},
                    occurred_at=datetime.now(UTC) - timedelta(seconds=age),
                )
            )
            connection.execute(
                insert(health_findings).values(
                    signal_id=signal,
                    policy_id=policy,
                    state=state,
                    cause_class="POLICY",
                    fingerprint=str(index) * 64,
                    evaluated_at=datetime.now(UTC),
                )
            )
    domain = next(
        d
        for d in client.get("/api/v1/health/domains").json()["domains"]
        if d["domain"] == "CAPACITY"
    )
    assert domain["state"] == "CRITICAL"
    assert domain["unknown_source_count"] == 1


def test_volume_share_serialization_filter_and_stale_quality(ingest_setup):
    from packages.shared.models.core import volumes

    client, engine, collector, token, source = ingest_setup
    stamp = datetime.now(UTC).isoformat()
    records = [
        dict(
            kind="volume",
            unique_identity="v",
            filesystem="NTFS",
            mount_aliases=["X:"],
            total_bytes=100,
            free_bytes=50,
        ),
        dict(
            kind="share", name="Отчёты", volume_identity="v", relative_path="Отдел", protocol="SMB"
        ),
    ]
    payload = dict(
        collector_id=str(collector),
        batch_id="inventory",
        schema_version=1,
        sent_at=stamp,
        first_event_at=stamp,
        last_event_at=stamp,
        record_count=2,
        records=[dict(occurred_at=stamp, **r) for r in records],
    )
    assert (
        client.post(
            "/api/v1/ingest/inventory", json=payload, headers={"Authorization": "Bearer " + token}
        ).status_code
        == 202
    )
    page = client.get(f"/api/v1/volumes?source_id={source}&limit=1").json()
    assert page["total"] == 1
    volume = page["items"][0]
    assert volume["mount_aliases"] == ["X:"]
    assert volume["quality"] == "COMPLETE"
    share = client.get(f"/api/v1/shares?source_id={source}").json()["items"][0]
    assert share["volume_id"] == volume["id"]
    assert share["name"] == "Отчёты"
    assert share["last_seen_at"].endswith("Z")
    with engine.begin() as connection:
        connection.execute(
            update(volumes).values(last_seen_at=datetime.now(UTC) - timedelta(hours=1))
        )
    assert client.get("/api/v1/volumes").json()["items"][0]["quality"] == "STALE"
    for route in ["volumes", "shares"]:
        assert client.get(f"/api/v1/{route}?source_id={uuid4()}").status_code == 404
        assert client.get(f"/api/v1/{route}?limit=101").status_code == 422


def test_source_lag_is_not_hidden_by_fresh_heartbeat(ingest_setup):
    client, engine, collector, token, source = ingest_setup
    upload(client, collector, token, datetime.now(UTC))
    from packages.shared.models.core import collector_heartbeats

    with engine.begin() as connection:
        connection.execute(update(collector_heartbeats).values(lag_seconds=600))
    assert client.get(f"/api/v1/sources/{source}/freshness").json()["state"] == "CRITICAL"


def test_fresh_envelope_cannot_disguise_stale_records(ingest_setup):
    client, _, collector, token, source = ingest_setup
    now = datetime.now(UTC).isoformat()
    old = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    payload = dict(
        collector_id=str(collector),
        batch_id="inflated-window",
        schema_version=1,
        sent_at=now,
        first_event_at=old,
        last_event_at=now,
        record_count=1,
        records=[dict(occurred_at=old, version="synthetic", lag_seconds=0)],
    )
    response = client.post(
        "/api/v1/ingest/heartbeat", json=payload, headers={"Authorization": "Bearer " + token}
    )
    assert response.status_code == 422
    assert client.get(f"/api/v1/sources/{source}/freshness").json()["state"] == "UNKNOWN"


@pytest.mark.parametrize(
    "mode,expected", [("unseen", "UNKNOWN"), ("stale", "CRITICAL"), ("lag", "CRITICAL")]
)
def test_fresh_collector_does_not_mask_another_enabled_collector(ingest_setup, mode, expected):
    import hashlib

    from packages.shared.models.core import collector_heartbeats

    client, engine, collector, token, source = ingest_setup
    other, other_token = uuid4(), uuid4().hex
    with engine.begin() as connection:
        connection.execute(
            insert(collectors).values(
                id=other,
                source_node_id=source,
                collector_type="SYNTHETIC",
                token_hash=hashlib.sha256(("collector:" + other_token).encode()).hexdigest(),
            )
        )
    if mode != "unseen":
        age = 600 if mode == "stale" else 0
        upload(client, other, other_token, datetime.now(UTC) - timedelta(seconds=age))
        if mode == "lag":
            with engine.begin() as connection:
                connection.execute(
                    update(collector_heartbeats)
                    .where(collector_heartbeats.c.collector_id == other)
                    .values(lag_seconds=600)
                )
    upload(client, collector, token, datetime.now(UTC))
    data = client.get(f"/api/v1/sources/{source}/freshness").json()
    assert data["state"] == expected
    assert data["collector_count"] == 2
    assert data["bottleneck_collector_id"] == str(other)


def test_overview_freshness_includes_sources_outside_first_page(ingest_setup):
    client, engine, collector, token, _ = ingest_setup
    upload(client, collector, token, datetime.now(UTC))
    with engine.begin() as connection:
        for index in range(55):
            connection.execute(
                insert(source_nodes).values(
                    source_type="PBS",
                    hostname=f"synthetic-extra-{index}",
                    instance_id=str(uuid4()),
                )
            )
    summary = client.get("/api/v1/overview").json()["freshness"]
    assert summary["source_count"] == 56
    assert summary["current_source_count"] == 1
    assert summary["unknown_source_count"] == 55
    assert summary["stale_source_count"] == 0
    assert summary["state"] == "UNKNOWN"


@pytest.mark.parametrize(
    "age,state", [(0, "HEALTHY"), (90, "OBSERVE"), (150, "WARNING"), (600, "CRITICAL")]
)
def test_overview_source_freshness_is_independent_from_operational_health(ingest_setup, age, state):
    client, _, collector, token, _ = ingest_setup
    upload(client, collector, token, datetime.now(UTC) - timedelta(seconds=age))
    data = client.get("/api/v1/overview").json()
    assert data["overall_state"] == "UNKNOWN"
    assert data["freshness"]["state"] == state
    assert data["freshness"]["stale_source_count"] == int(age > 0)


def test_overall_critical_does_not_hide_unknown_domains(ingest_setup):
    client, engine, collector, token, source = ingest_setup
    upload(client, collector, token, datetime.now(UTC))
    signal, policy = uuid4(), uuid4()
    with engine.begin() as connection:
        connection.execute(
            insert(health_policies).values(
                id=policy,
                name="synthetic",
                domain="CAPACITY",
                policy_type="CAPACITY",
                parameters={},
            )
        )
        connection.execute(
            insert(health_signals).values(
                id=signal,
                source_node_id=source,
                domain="CAPACITY",
                signal_type="FREE_SPACE",
                measurement={},
                occurred_at=datetime.now(UTC),
            )
        )
        connection.execute(
            insert(health_findings).values(
                signal_id=signal,
                policy_id=policy,
                state="CRITICAL",
                cause_class="POLICY",
                fingerprint="c" * 64,
                evaluated_at=datetime.now(UTC),
            )
        )
    data = client.get("/api/v1/overview").json()
    assert data["overall_state"] == "CRITICAL"
    assert any(domain["state"] == "UNKNOWN" for domain in data["domains"])


def test_all_read_responses_publish_bounded_validity_and_disable_http_cache(ingest_setup):
    client, _, _, _, source = ingest_setup
    paths = [
        "/overview",
        "/health/domains",
        "/sources",
        f"/sources/{source}",
        f"/sources/{source}/freshness",
        "/volumes",
        "/shares",
    ]
    for path in paths:
        response = client.get("/api/v1" + path)
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        assert 0 <= int(response.headers["X-Evidence-Valid-For-Ms"]) <= 35000


def test_read_validity_expires_before_source_freshness_changes(ingest_setup):
    client, _, collector, token, source = ingest_setup
    upload(client, collector, token, datetime.now(UTC) - timedelta(seconds=58))
    for path in [
        "/overview",
        "/health/domains",
        "/sources",
        f"/sources/{source}",
        f"/sources/{source}/freshness",
    ]:
        response = client.get("/api/v1" + path)
        assert 0 < int(response.headers["X-Evidence-Valid-For-Ms"]) <= 2000


def test_domain_validity_expires_before_policy_evidence_becomes_unknown(ingest_setup):
    client, engine, collector, token, source = ingest_setup
    upload(client, collector, token, datetime.now(UTC))
    signal, policy = uuid4(), uuid4()
    old = datetime.now(UTC) - timedelta(seconds=58)
    with engine.begin() as connection:
        connection.execute(
            insert(health_policies).values(
                id=policy,
                name="synthetic",
                domain="CAPACITY",
                policy_type="CAPACITY",
                parameters={},
            )
        )
        connection.execute(
            insert(health_signals).values(
                id=signal,
                source_node_id=source,
                domain="CAPACITY",
                signal_type="FREE_SPACE",
                measurement={},
                occurred_at=old,
            )
        )
        connection.execute(
            insert(health_findings).values(
                signal_id=signal,
                policy_id=policy,
                state="HEALTHY",
                cause_class="POLICY",
                fingerprint="d" * 64,
                evaluated_at=old,
            )
        )
    for path in ["/overview", "/health/domains"]:
        response = client.get("/api/v1" + path)
        assert 0 < int(response.headers["X-Evidence-Valid-For-Ms"]) <= 2000


def test_validity_accounts_for_collectors_masked_by_fixed_reported_lag(ingest_setup):
    import hashlib

    from packages.shared.models.core import collector_heartbeats

    client, engine, collector, token, source = ingest_setup
    other, other_token = uuid4(), uuid4().hex
    with engine.begin() as connection:
        connection.execute(
            insert(collectors).values(
                id=other,
                source_node_id=source,
                collector_type="SYNTHETIC",
                token_hash=hashlib.sha256(("collector:" + other_token).encode()).hexdigest(),
            )
        )
    upload(client, other, other_token, datetime.now(UTC) - timedelta(seconds=58))
    upload(client, collector, token, datetime.now(UTC))
    with engine.begin() as connection:
        connection.execute(
            update(collector_heartbeats)
            .where(collector_heartbeats.c.collector_id == collector)
            .values(lag_seconds=60)
        )
    response = client.get(f"/api/v1/sources/{source}")
    assert response.json()["freshness"]["bottleneck_collector_id"] == str(collector)
    assert 0 < int(response.headers["X-Evidence-Valid-For-Ms"]) <= 2000
