"""Own queue -> strict real HTTPS -> real PostgreSQL, including lost ACK."""

import json
from uuid import uuid4

from sqlalchemy import func, insert, select, update
from test_windows_audit_events import parse, xml
from test_windows_audit_store import Cipher

from collectors.common.transport import DeliveryOutcome, Transport
from collectors.windows_audit.delivery import Delivery
from collectors.windows_audit.store import AuditStore
from packages.shared.models.audit import audit_evidence
from packages.shared.models.core import collectors, volumes
from tests.deployment.collector_delivery import serving_ingest


def test_own_retained_bytes_actual_https_pg_lost_ack(authenticated_setup, tmp_path):
    client, engine, collector, token, source = authenticated_setup
    with engine.begin() as conn:
        conn.execute(
            update(collectors)
            .where(collectors.c.id == collector)
            .values(collector_type="AUDIT_WINDOWS")
        )
        conn.execute(
            insert(volumes).values(
                source_node_id=source, unique_identity="volume-a", filesystem="NTFS"
            )
        )
    with serving_ingest(client.app, tmp_path / "tls") as (origin, ca):
        transport = Transport(origin, ca, token, timeout=5, collector_id=collector)
        store = AuditStore(tmp_path / "audit.sqlite3", collector, Cipher())
        event = parse(xml()).model_copy(update={"volume_id": "volume-a"})
        body = json.dumps(
            {
                "collector_id": str(collector),
                "batch_id": uuid4().hex,
                "schema_version": 1,
                "sent_at": event.occurred_at.isoformat(),
                "records": [{**event.model_dump(mode="json"), "digest": event.digest()}],
            }
        ).encode()
        store.commit("synthetic bookmark", {}, body)

        class LostAck:
            def __init__(self):
                self.first = True
                self.bodies = []
                self.duplicate = False

            def send(self, claim):
                self.bodies.append(claim.body)
                outcome = transport.send(claim)
                assert outcome.kind == "accepted"
                if self.first:
                    self.first = False
                    return DeliveryOutcome("retry", "NETWORK")
                self.duplicate = outcome.duplicate
                return outcome

        sender = LostAck()
        Delivery(store, sender).step(now=1000)
        assert store.peek() is not None
        # New delivery object proves retained state/retry after restart.
        Delivery(store, sender).step(now=2000)
        assert store.peek() is None and sender.duplicate is True and sender.bodies == [body, body]
        with engine.connect() as conn:
            assert conn.scalar(select(func.count()).select_from(audit_evidence)) == 1
