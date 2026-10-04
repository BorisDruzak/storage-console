import os
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import SQLAlchemyError

from apps.api.auth import token_hash
from apps.api.ingest import accept
from apps.api.source_control import registry
from apps.api.user_auth.sessions import Actor
from packages.contracts.common import BatchEnvelope
from packages.contracts.heartbeat import HeartbeatRecord
from packages.contracts.sources import CreateCollector, CreateSource, SetCollectorEnabled
from packages.shared.models.core import collectors, source_nodes
from packages.shared.models.security import audit_log

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="PostgreSQL required")


@pytest.fixture
def control_setup(session_setup):
    _, engine, user, _ = session_setup
    return engine, Actor(user, "synthetic", frozenset({"storage_admin"}))


def register(engine, actor, source_type="FILESERVER"):
    return registry.register_source(
        engine,
        actor,
        CreateSource(source_type=source_type, hostname="synthetic", instance_id=str(uuid4())),
    )


def heartbeat(collector):
    now = datetime.now(UTC)
    return BatchEnvelope[HeartbeatRecord](
        collector_id=collector,
        batch_id=str(uuid4()),
        schema_version=1,
        sent_at=now,
        first_event_at=now,
        last_event_at=now,
        record_count=1,
        records=[HeartbeatRecord(occurred_at=now, version="test")],
    )


def test_registration_does_not_fabricate_health_and_audits_no_identity_values(control_setup):
    engine, actor = control_setup
    result = register(engine, actor)
    with engine.connect() as conn:
        stored = (
            conn.execute(select(source_nodes).where(source_nodes.c.id == result.id))
            .mappings()
            .one()
        )
        assert stored["instance_id"] == result.instance_id
        assert stored["last_success_at"] is None
        audit = (
            conn.execute(select(audit_log).where(audit_log.c.action == "source.register"))
            .mappings()
            .one()
        )
        assert audit["user_id"] == actor.id
        assert audit["resource_identity"] == str(result.id)
        assert audit["details"] == {}
        assert result.instance_id not in repr(audit)


def test_concurrent_natural_identity_registration_creates_one_source(control_setup):
    engine, actor = control_setup
    data = CreateSource(source_type="PVE", hostname="synthetic", instance_id=str(uuid4()))

    def create(_):
        try:
            return registry.register_source(engine, actor, data).id
        except registry.RegistryError as error:
            assert (error.status, error.detail) == (409, "SOURCE_IDENTITY_CONFLICT")
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(create, range(4)))
    assert sum(result is not None for result in outcomes) == 1
    with engine.connect() as conn:
        assert (
            conn.scalar(
                select(func.count())
                .select_from(source_nodes)
                .where(source_nodes.c.instance_id == data.instance_id)
            )
            == 1
        )
        assert (
            conn.scalar(
                select(func.count())
                .select_from(audit_log)
                .where(audit_log.c.action == "source.register")
            )
            == 1
        )


@pytest.mark.parametrize(
    "source_type,kind", [("FILESERVER", "WINDOWS"), ("PVE", "PVE"), ("PBS", "PBS")]
)
def test_enrollment_compatible_type_hash_only_and_list_without_credentials(
    control_setup, source_type, kind
):
    engine, actor = control_setup
    source = register(engine, actor, source_type)
    result = registry.enroll_collector(
        engine, actor, source.id, CreateCollector(collector_type=kind)
    )
    secret = result.token.get_secret_value()
    with engine.connect() as conn:
        row = conn.execute(select(collectors).where(collectors.c.id == result.id)).mappings().one()
        assert row["token_hash"] == token_hash(secret)
        assert secret not in repr(row)
        audit = (
            conn.execute(select(audit_log).where(audit_log.c.action == "collector.enroll"))
            .mappings()
            .one()
        )
        assert audit["details"] == {}
        assert secret not in repr(audit)
    listed = registry.list_collectors(engine, source.id, 50, 0)
    assert listed.total == 1
    assert listed.items[0].id == result.id
    assert "token" not in listed.items[0].model_dump()
    assert "token_hash" not in listed.items[0].model_dump()


def test_missing_source_and_type_mismatch_do_not_enroll(control_setup):
    engine, actor = control_setup
    with pytest.raises(registry.RegistryError) as missing:
        registry.enroll_collector(engine, actor, uuid4(), CreateCollector(collector_type="WINDOWS"))
    assert missing.value.status == 404
    source = register(engine, actor)
    with pytest.raises(registry.RegistryError) as mismatch:
        registry.enroll_collector(engine, actor, source.id, CreateCollector(collector_type="PBS"))
    assert mismatch.value.status == 409
    assert registry.list_collectors(engine, source.id, 50, 0).total == 0
    with pytest.raises(registry.RegistryError) as missing_list:
        registry.list_collectors(engine, uuid4(), 50, 0)
    assert missing_list.value.status == 404


def test_rotation_and_disable_reject_old_token_even_for_committed_batch(control_setup):
    engine, actor = control_setup
    source = register(engine, actor)
    first = registry.enroll_collector(
        engine, actor, source.id, CreateCollector(collector_type="WINDOWS")
    )
    batch = heartbeat(first.id)
    old = first.token.get_secret_value()
    assert accept(engine, "heartbeat", batch, old).duplicate is False
    rotated = registry.rotate_collector(engine, actor, first.id)
    new = rotated.token.get_secret_value()
    assert new != old and rotated.id == first.id and rotated.source_node_id == source.id
    with pytest.raises(HTTPException) as rejected:
        accept(engine, "heartbeat", batch, old)
    assert rejected.value.status_code == 401
    assert accept(engine, "heartbeat", batch, new).duplicate is True
    disabled = registry.set_collector_enabled(
        engine, actor, first.id, SetCollectorEnabled(enabled=False)
    )
    assert disabled.enabled is False
    with pytest.raises(HTTPException) as rejected_disabled:
        accept(engine, "heartbeat", batch, new)
    assert rejected_disabled.value.status_code == 401
    again = registry.rotate_collector(engine, actor, first.id)
    assert again.enabled is False
    registry.set_collector_enabled(engine, actor, first.id, SetCollectorEnabled(enabled=True))
    with pytest.raises(HTTPException):
        accept(engine, "heartbeat", batch, new)
    assert accept(engine, "heartbeat", batch, again.token.get_secret_value()).duplicate is True
    with engine.connect() as conn:
        assert (
            conn.scalar(
                select(source_nodes.c.last_success_at).where(source_nodes.c.id == source.id)
            )
            is not None
        )
        details = conn.scalars(
            select(audit_log.c.details).where(audit_log.c.resource_identity == str(first.id))
        ).all()
        assert len(details) == 5 and all(value == {} for value in details)


def test_audit_failure_rolls_back_registration_and_rotation(control_setup):
    engine, actor = control_setup
    source = register(engine, actor)
    enrolled = registry.enroll_collector(
        engine, actor, source.id, CreateCollector(collector_type="WINDOWS")
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE audit_log ADD CONSTRAINT reject_controls "
                "CHECK (action NOT IN ('source.register','collector.rotate')) NOT VALID"
            )
        )
    with pytest.raises(SQLAlchemyError):
        registry.rotate_collector(engine, actor, enrolled.id)
    with pytest.raises(SQLAlchemyError):
        register(engine, actor)
    assert accept(
        engine, "heartbeat", heartbeat(enrolled.id), enrolled.token.get_secret_value()
    ).accepted
    with engine.connect() as conn:
        assert (
            conn.scalar(select(func.count()).select_from(source_nodes)) == 2
        )  # Fixture + registered source.


def test_missing_collector_mutations_are_not_successful(control_setup):
    engine, actor = control_setup
    for operation in (
        lambda: registry.rotate_collector(engine, actor, uuid4()),
        lambda: registry.set_collector_enabled(
            engine, actor, uuid4(), SetCollectorEnabled(enabled=False)
        ),
    ):
        with pytest.raises(registry.RegistryError) as missing:
            operation()
        assert missing.value.status == 404


def test_rotation_waits_for_admitted_ingest_then_revokes_old_token(control_setup):
    engine, actor = control_setup
    source = register(engine, actor)
    credential = registry.enroll_collector(
        engine, actor, source.id, CreateCollector(collector_type="WINDOWS")
    )
    old = credential.token.get_secret_value()
    batch = heartbeat(credential.id)
    admitted, release = threading.Event(), threading.Event()

    def hold_admitted(conn, cursor, statement, parameters, context, executemany):
        if threading.current_thread().name == "admitted-ingest" and "FOR UPDATE" in statement:
            admitted.set()
            assert release.wait(5), "Test never released collector admission lock"

    def ingest():
        threading.current_thread().name = "admitted-ingest"
        return accept(engine, "heartbeat", batch, old)

    event.listen(engine, "after_cursor_execute", hold_admitted)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending_ingest = pool.submit(ingest)
            assert admitted.wait(5)
            rotating = pool.submit(registry.rotate_collector, engine, actor, credential.id)
            try:
                with pytest.raises(TimeoutError):
                    rotating.result(timeout=0.1)
            finally:
                release.set()
            assert pending_ingest.result(timeout=5).accepted
            new = rotating.result(timeout=5)
    finally:
        release.set()
        event.remove(engine, "after_cursor_execute", hold_admitted)
    with pytest.raises(HTTPException) as rejected:
        accept(engine, "heartbeat", batch, old)
    assert rejected.value.status_code == 401
    assert accept(engine, "heartbeat", batch, new.token.get_secret_value()).duplicate


def test_concurrent_rotation_and_disable_cannot_implicitly_enable_collector(control_setup):
    engine, actor = control_setup
    source = register(engine, actor)
    credential = registry.enroll_collector(
        engine, actor, source.id, CreateCollector(collector_type="WINDOWS")
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        rotated = pool.submit(registry.rotate_collector, engine, actor, credential.id)
        disabled = pool.submit(
            registry.set_collector_enabled,
            engine,
            actor,
            credential.id,
            SetCollectorEnabled(enabled=False),
        )
        rotated.result(timeout=5)
        assert disabled.result(timeout=5).enabled is False
    assert registry.list_collectors(engine, source.id, 50, 0).items[0].enabled is False


def test_stable_collector_pagination_and_boundaries(control_setup):
    engine, actor = control_setup
    source = register(engine, actor)
    enrolled = [
        registry.enroll_collector(
            engine, actor, source.id, CreateCollector(collector_type="WINDOWS")
        )
        for _ in range(3)
    ]
    with engine.begin() as conn:
        conn.execute(
            collectors.update()
            .where(collectors.c.source_node_id == source.id)
            .values(created_at=datetime(2026, 1, 1, tzinfo=UTC))
        )
    first = registry.list_collectors(engine, source.id, 2, 0)
    second = registry.list_collectors(engine, source.id, 2, 2)
    assert first.total == second.total == 3
    assert [item.id for item in first.items + second.items] == sorted(item.id for item in enrolled)
    assert not registry.list_collectors(engine, source.id, 2, 3).items
    for limit, offset in ((0, 0), (101, 0), (True, 0), (1, -1), (1, 1000001), (1, True)):
        with pytest.raises(registry.RegistryError) as error:
            registry.list_collectors(engine, source.id, limit, offset)
        assert error.value.status == 422
