"""Frozen additive directory schema; native evidence is never rewritten."""

import ipaddress

from alembic import op
from sqlalchemy import text

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

DDL = (
    """CREATE TABLE directory_snapshots (
id UUID NOT NULL,
source_node_id UUID NOT NULL,
collector_id UUID NOT NULL,
dns_domain VARCHAR(253) NOT NULL,
domain_sid VARCHAR(64) NOT NULL,
observed_at TIMESTAMP WITH TIME ZONE NOT NULL,
received_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
state VARCHAR(16) NOT NULL,
next_page INTEGER NOT NULL,
record_count INTEGER NOT NULL,
payload_bytes BIGINT NOT NULL,
error_code VARCHAR(64),
PRIMARY KEY (id),
CONSTRAINT ck_directory_snapshot_state CHECK (state IN ('COLLECTING','COMPLETE','ERROR')),
CONSTRAINT ck_directory_snapshot_bounds CHECK (next_page BETWEEN 1 AND 512 AND record_count
BETWEEN 0 AND 100000 AND payload_bytes BETWEEN 1 AND 33554432),
FOREIGN KEY(source_node_id) REFERENCES source_nodes (id) ON DELETE RESTRICT,
FOREIGN KEY(collector_id) REFERENCES collectors (id) ON DELETE RESTRICT
)""",
    """CREATE INDEX ix_directory_complete ON directory_snapshots
(source_node_id, collector_id, dns_domain, domain_sid, state, observed_at, id)""",
    """CREATE INDEX ix_directory_latest ON directory_snapshots
(source_node_id, collector_id, dns_domain, domain_sid, observed_at, id)""",
    """CREATE TABLE directory_pages (
snapshot_id UUID NOT NULL,
receipt_id UUID NOT NULL,
page_index INTEGER NOT NULL,
record_count INTEGER NOT NULL,
payload_sha256 VARCHAR(64) NOT NULL,
CONSTRAINT uq_directory_page UNIQUE (snapshot_id, page_index),
CONSTRAINT uq_directory_page_receipt UNIQUE (receipt_id),
FOREIGN KEY(snapshot_id) REFERENCES directory_snapshots (id) ON DELETE RESTRICT,
FOREIGN KEY(receipt_id) REFERENCES ingest_batches (id) ON DELETE RESTRICT
)""",
    """CREATE TABLE directory_user_observations (
snapshot_id UUID NOT NULL,
sid VARCHAR(64) NOT NULL,
object_guid UUID NOT NULL,
payload JSONB NOT NULL,
CONSTRAINT uq_directory_user_sid UNIQUE (snapshot_id, sid),
CONSTRAINT uq_directory_user_guid UNIQUE (snapshot_id, object_guid),
FOREIGN KEY(snapshot_id) REFERENCES directory_snapshots (id) ON DELETE RESTRICT
)""",
    """CREATE TABLE client_name_observations (
id UUID NOT NULL,
source_node_id UUID NOT NULL,
collector_id UUID NOT NULL,
receipt_id UUID NOT NULL,
dns_domain VARCHAR(253) NOT NULL,
domain_sid VARCHAR(64) NOT NULL,
client_ip_key VARCHAR(45) NOT NULL,
observed_at TIMESTAMP WITH TIME ZONE NOT NULL,
expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
received_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
payload JSONB NOT NULL,
PRIMARY KEY (id),
CONSTRAINT uq_client_name_receipt UNIQUE (receipt_id),
FOREIGN KEY(source_node_id) REFERENCES source_nodes (id) ON DELETE RESTRICT,
FOREIGN KEY(collector_id) REFERENCES collectors (id) ON DELETE RESTRICT,
FOREIGN KEY(receipt_id) REFERENCES ingest_batches (id) ON DELETE RESTRICT
)""",
    """CREATE INDEX ix_client_name_latest ON client_name_observations
(source_node_id, collector_id, dns_domain, domain_sid, client_ip_key, observed_at, id)""",
    """CREATE TABLE audit_client_ip_observations (
audit_evidence_id UUID NOT NULL,
source_node_id UUID NOT NULL,
client_ip_key VARCHAR(45) NOT NULL,
CONSTRAINT uq_audit_client_ip_evidence UNIQUE (audit_evidence_id),
FOREIGN KEY(audit_evidence_id) REFERENCES windows_audit_evidence (id) ON DELETE RESTRICT,
FOREIGN KEY(source_node_id) REFERENCES source_nodes (id) ON DELETE RESTRICT
)""",
    """CREATE INDEX ix_audit_client_ip_source ON audit_client_ip_observations (source_node_id,
client_ip_key)""",
)
IMMUTABLE = (
    "directory_pages",
    "directory_user_observations",
    "client_name_observations",
    "audit_client_ip_observations",
)


def upgrade():
    op.execute("ALTER TABLE collectors ADD COLUMN directory_scope JSONB")
    for statement in DDL:
        op.execute(statement)
    # Populate a separate derived index in bounded pages. Original payloads,
    # digests and immutable triggers remain untouched throughout the migration.
    connection = op.get_bind()
    cursor = None
    while True:
        rows = (
            connection.execute(
                text("""SELECT id, source_node_id, payload->>'client_ip' AS ip
            FROM windows_audit_evidence WHERE event_id=4624
            AND (CAST(:cursor AS uuid) IS NULL OR id > CAST(:cursor AS uuid))
            ORDER BY id LIMIT 256"""),
                {"cursor": cursor},
            )
            .mappings()
            .all()
        )
        if not rows:
            break
        for row in rows:
            try:
                value = row["ip"]
                if not isinstance(value, str) or "%" in value or len(value) > 45:
                    continue
                address = ipaddress.ip_address(value)
                if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
                    address = address.ipv4_mapped
            except ValueError:
                continue
            connection.execute(
                text("""INSERT INTO audit_client_ip_observations
                (audit_evidence_id, source_node_id, client_ip_key) VALUES (:id,:source,:ip)"""),
                {"id": row["id"], "source": row["source_node_id"], "ip": str(address)},
            )
        cursor = str(rows[-1]["id"])
    for table in IMMUTABLE + ("directory_snapshots",):
        for operation, level in (("DELETE", "ROW"), ("TRUNCATE", "STATEMENT")):
            op.execute(
                f"CREATE TRIGGER immutable_directory_{operation.lower()} BEFORE "
                f"{operation} ON {table} FOR EACH {level} "
                "EXECUTE FUNCTION reject_audit_evidence_mutation()"
            )
        if table in IMMUTABLE:
            op.execute(
                f"CREATE TRIGGER immutable_directory_update BEFORE UPDATE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION reject_audit_evidence_mutation()"
            )
    op.execute("""CREATE FUNCTION guard_directory_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.state <> 'COLLECTING' OR
               ROW(NEW.id,NEW.source_node_id,NEW.collector_id,NEW.dns_domain,NEW.domain_sid,
                   NEW.observed_at,NEW.received_at) IS DISTINCT FROM
               ROW(OLD.id,OLD.source_node_id,OLD.collector_id,OLD.dns_domain,OLD.domain_sid,
                   OLD.observed_at,OLD.received_at) OR
               NEW.next_page <> OLD.next_page+1 OR NEW.record_count < OLD.record_count OR
               NEW.payload_bytes <= OLD.payload_bytes THEN
                RAISE EXCEPTION 'DIRECTORY_OBSERVATION_IMMUTABLE';
            END IF;
            RETURN NEW;
        END $$""")
    op.execute("""CREATE TRIGGER directory_snapshot_progress BEFORE UPDATE ON directory_snapshots
                  FOR EACH ROW EXECUTE FUNCTION guard_directory_snapshot()""")


def downgrade():
    for table in (
        "audit_client_ip_observations",
        "client_name_observations",
        "directory_user_observations",
        "directory_pages",
        "directory_snapshots",
    ):
        op.drop_table(table)
    op.execute("DROP FUNCTION guard_directory_snapshot()")
    op.drop_column("collectors", "directory_scope")
