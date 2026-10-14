"""Admin-only current names with explicit provenance; native audit fields stay exact."""

from uuid import uuid4

import pytest
from sqlalchemy import update
from test_client_name_ingest import native_logon, observation
from test_client_name_ingest import post as client_post
from test_directory_contract import scope, user
from test_directory_ingest import post, wire
from test_source_control import headers, set_role

from packages.shared.models.core import collectors


@pytest.fixture
def setup(authenticated_setup):
    client, engine, collector, token, source = authenticated_setup
    with engine.begin() as conn:
        conn.execute(
            update(collectors)
            .where(collectors.c.id == collector)
            .values(collector_type="AUDIT_WINDOWS", directory_scope=scope())
        )
    return client, engine, collector, token, source


def search(setup):
    return setup[0].post(
        "/api/v1/audit/search", json={"source_id": str(setup[4])}, headers=headers(setup[0])
    )


def test_names_are_separate_and_partial_attempt_does_not_relabel_old_native(setup):
    native_logon(setup)
    record = user()
    record["account"] = "renamed-current"
    assert post(setup, wire(setup, records=[record])).status_code == 202
    assert client_post(setup, observation(setup)).status_code == 202
    result = search(setup)
    assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
    value = result.json()["items"][0]
    assert (
        value["evidence"]["account"] == "native-name" and value["evidence"]["workstation"] is None
    )
    assert value["account_observation"]["state"] == "CURRENT"
    assert value["account_observation"]["user"]["account"] == "renamed-current"
    assert value["account_observation"]["user"]["enabled"] is False
    assert value["client_observation"]["state"] == "CONFIRMED_CURRENT"
    assert value["client_observation"]["event_time_confirmed"] is False
    partial = wire(setup, records=[], complete=False, finished=False, total_records=None)
    assert post(setup, partial).status_code == 202
    value = search(setup).json()["items"][0]
    assert value["account_observation"]["state"] == "PARTIAL"
    assert value["account_observation"]["user"]["account"] == "renamed-current"
    assert value["evidence"]["account"] == "native-name"


@pytest.mark.parametrize("role", ["viewer", "analyst", "auditor", "storage_operator"])
def test_every_nonadmin_is_denied_names_and_directory_status(setup, role):
    set_role(setup[1], role)
    denied = setup[0].get(f"/api/v1/audit/sources/{setup[4]}/directory")
    assert denied.status_code == 403
    assert "domain_sid" not in denied.text
    assert search(setup).status_code == 403
    listing = setup[0].get(f"/api/v1/sources/{setup[4]}/collectors")
    assert listing.status_code == 200
    assert listing.json()["items"][0]["id"] == str(setup[2])
    assert "directory_scope" not in listing.text and "domain_sid" not in listing.text


def test_directory_status_is_not_healthy_without_complete_current_scope(setup):
    path = f"/api/v1/audit/sources/{setup[4]}/directory"
    assert setup[0].get(path).json()["state"] == "UNKNOWN"
    assert (
        post(
            setup,
            wire(setup, records=[], complete=False, error_code="LDAP_UNAVAILABLE", total_records=0),
        ).status_code
        == 202
    )
    assert setup[0].get(path).json()["state"] == "ERROR"
    assert post(setup, wire(setup, snapshot_id=uuid4())).status_code == 202
    result = setup[0].get(path)
    assert result.json()["state"] == "CURRENT" and result.json()["user_count"] == 1
    assert result.headers["cache-control"] == "no-store"


def test_latest_reads_bound_obsolete_collector_history(setup):
    from sqlalchemy import text

    old, current = uuid4(), uuid4()
    with setup[1].begin() as conn:
        conn.execute(
            text("CREATE TEMP TABLE directory_plan (LIKE directory_snapshots INCLUDING ALL)")
        )
        conn.execute(
            text("""
            INSERT INTO directory_plan
            (id,source_node_id,collector_id,dns_domain,domain_sid,observed_at,received_at,
             state,next_page,record_count,payload_bytes)
            SELECT gen_random_uuid(),:source,:old,'example.test','S-1-5-21-10-20-30',
                   now(),now(),'COMPLETE',1,0,500 FROM generate_series(1,10000)
        """),
            {"source": setup[4], "old": old},
        )
        conn.execute(text("ANALYZE directory_plan"))
        for state in ("", " AND state='COMPLETE'"):
            plan = conn.scalar(
                text(
                    """
                EXPLAIN (ANALYZE, FORMAT JSON) SELECT id FROM directory_plan
                WHERE source_node_id=:source AND collector_id=:current
                AND dns_domain='example.test' AND domain_sid='S-1-5-21-10-20-30'
            """
                    + state
                    + " ORDER BY observed_at DESC,id DESC LIMIT 1"
                ),
                {"source": setup[4], "current": current},
            )

            def nodes(node):
                yield node
                for child in node.get("Plans", []):
                    yield from nodes(child)

            visited = list(nodes(plan[0]["Plan"]))
            assert sum(n.get("Rows Removed by Filter", 0) for n in visited) == 0
            assert any("collector_id" in n.get("Index Cond", "") for n in visited)
        conn.execute(
            text("CREATE TEMP TABLE client_plan (LIKE client_name_observations INCLUDING ALL)")
        )
        conn.execute(
            text("""
            INSERT INTO client_plan
            (id,source_node_id,collector_id,receipt_id,dns_domain,domain_sid,client_ip_key,
             observed_at,expires_at,received_at,payload)
            SELECT gen_random_uuid(),:source,:old,gen_random_uuid(),'example.test',
                   'S-1-5-21-10-20-30','192.0.2.10',now(),now(),now(),'{}'::jsonb
            FROM generate_series(1,10000)
        """),
            {"source": setup[4], "old": old},
        )
        conn.execute(text("ANALYZE client_plan"))
        plan = conn.scalar(
            text("""
            EXPLAIN (ANALYZE, FORMAT JSON) SELECT id FROM client_plan
            WHERE source_node_id=:source AND collector_id=:current
            AND dns_domain='example.test' AND domain_sid='S-1-5-21-10-20-30'
            AND client_ip_key='192.0.2.10' ORDER BY observed_at DESC,id DESC LIMIT 1
        """),
            {"source": setup[4], "current": current},
        )
        visited = list(nodes(plan[0]["Plan"]))
        assert sum(n.get("Rows Removed by Filter", 0) for n in visited) == 0
        assert any("collector_id" in n.get("Index Cond", "") for n in visited)
