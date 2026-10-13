"""Frozen additive audit schema; existing USN/path history remains untouched."""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

DDL = (
    """CREATE TABLE windows_audit_evidence (
	id UUID NOT NULL,
	source_node_id UUID NOT NULL,
	audit_collector_id UUID NOT NULL,
	host_id UUID NOT NULL,
	generation UUID NOT NULL,
	channel VARCHAR(32) NOT NULL,
	record_id BIGINT NOT NULL,
	event_id INTEGER NOT NULL,
	occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
	volume_id VARCHAR(255),
	path_key VARCHAR(64),
	sid VARCHAR(255),
	logon_id VARCHAR(20),
	payload JSONB NOT NULL,
	digest VARCHAR(64) NOT NULL,
	first_received_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
        CONSTRAINT uq_audit_event_identity UNIQUE (source_node_id, host_id, channel,
generation, record_id),
	FOREIGN KEY(source_node_id) REFERENCES source_nodes (id) ON DELETE RESTRICT,
	FOREIGN KEY(audit_collector_id) REFERENCES collectors (id) ON DELETE RESTRICT
)""",
    """CREATE INDEX ix_audit_source_logon_time ON windows_audit_evidence (source_node_id, logon_id,
occurred_at)""",
    """CREATE INDEX ix_audit_source_sid_time ON windows_audit_evidence (source_node_id, sid,
occurred_at)""",
    """CREATE INDEX ix_audit_source_time ON windows_audit_evidence (source_node_id, occurred_at)""",
    """CREATE INDEX ix_audit_source_volume_path_time ON windows_audit_evidence (source_node_id,
volume_id, path_key, occurred_at)""",
    """CREATE TABLE windows_audit_streams (
	collector_id UUID NOT NULL,
	host_id UUID,
	health JSONB NOT NULL,
	reported_at TIMESTAMP WITH TIME ZONE,
	accepted_at TIMESTAMP WITH TIME ZONE,
	CONSTRAINT uq_audit_stream_collector UNIQUE (collector_id),
	FOREIGN KEY(collector_id) REFERENCES collectors (id) ON DELETE RESTRICT
)""",
    """CREATE TABLE windows_audit_correlations (
	change_event_id UUID NOT NULL,
	rule_version VARCHAR(64) NOT NULL,
	class VARCHAR(32) NOT NULL,
	reason VARCHAR(64) NOT NULL,
	actor JSONB,
	evaluated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT uq_audit_correlation_change UNIQUE (change_event_id),
	FOREIGN KEY(change_event_id) REFERENCES change_events (id) ON DELETE RESTRICT
)""",
    """CREATE TABLE windows_audit_candidates (
	id UUID NOT NULL,
	change_event_id UUID NOT NULL,
	audit_evidence_id UUID NOT NULL,
	rule_version VARCHAR(64) NOT NULL,
	method VARCHAR(64) NOT NULL,
	class VARCHAR(32) NOT NULL,
	reason VARCHAR(64) NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_audit_candidate UNIQUE (change_event_id, audit_evidence_id, rule_version),
	FOREIGN KEY(change_event_id) REFERENCES change_events (id) ON DELETE RESTRICT,
	FOREIGN KEY(audit_evidence_id) REFERENCES windows_audit_evidence (id) ON DELETE RESTRICT
)""",
    """CREATE INDEX ix_audit_candidate_evidence ON windows_audit_candidates (audit_evidence_id)""",
    """CREATE TABLE windows_audit_identity_observations (
	id UUID NOT NULL,
	source_node_id UUID NOT NULL,
	collector_id UUID NOT NULL,
	receipt_id UUID NOT NULL,
	volume_id VARCHAR(255) NOT NULL,
	file_id VARCHAR(255) NOT NULL,
	path_key VARCHAR(64) NOT NULL,
	payload JSONB NOT NULL,
	occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(source_node_id) REFERENCES source_nodes (id) ON DELETE RESTRICT,
	FOREIGN KEY(collector_id) REFERENCES collectors (id) ON DELETE RESTRICT,
	FOREIGN KEY(receipt_id) REFERENCES ingest_batches (id) ON DELETE RESTRICT
)""",
    """CREATE INDEX ix_audit_identity_file_time ON windows_audit_identity_observations
(source_node_id, volume_id, file_id, occurred_at)""",
    """CREATE INDEX ix_audit_identity_path_time ON windows_audit_identity_observations
(source_node_id, volume_id, path_key, occurred_at)""",
    """CREATE TABLE windows_audit_health_observations (
	id UUID NOT NULL,
	collector_id UUID NOT NULL,
	receipt_id UUID NOT NULL,
	occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
	payload JSONB NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(collector_id) REFERENCES collectors (id) ON DELETE RESTRICT,
	FOREIGN KEY(receipt_id) REFERENCES ingest_batches (id) ON DELETE RESTRICT
)""",
    """CREATE INDEX ix_audit_health_collector_time ON windows_audit_health_observations
(collector_id, occurred_at)""",
)

IMMUTABLE = (
    "windows_audit_evidence",
    "windows_audit_identity_observations",
    "windows_audit_health_observations",
)
TABLES = (
    "windows_audit_health_observations",
    "windows_audit_identity_observations",
    "windows_audit_candidates",
    "windows_audit_correlations",
    "windows_audit_streams",
    "windows_audit_evidence",
)


def upgrade():
    for statement in DDL:
        op.execute(statement)
    op.execute("""CREATE FUNCTION reject_audit_evidence_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'AUDIT_EVIDENCE_IMMUTABLE';
        END $$""")
    for table in IMMUTABLE:
        op.execute(
            f"CREATE TRIGGER immutable_audit_row BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_audit_evidence_mutation()"
        )
        op.execute(
            f"CREATE TRIGGER immutable_audit_truncate BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION reject_audit_evidence_mutation()"
        )


def downgrade():
    for table in TABLES:
        op.drop_table(table)
    op.execute("DROP FUNCTION reject_audit_evidence_mutation()")
