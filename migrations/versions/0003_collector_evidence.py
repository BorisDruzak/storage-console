"""Retain uncorrelated collector evidence and recovery observation ordering."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collector_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_node_id", sa.Uuid(), nullable=False),
        sa.Column("change_event_id", sa.Uuid(), nullable=True),
        sa.Column("source_event_id", sa.String(255), nullable=False),
        sa.Column("evidence_type", sa.String(32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_identity", sa.String(255)),
        sa.Column("client_identity", sa.String(255)),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["source_node_id"], ["source_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["change_event_id"], ["change_events.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_collector_event_confidence"),
    )
    op.create_index(
        "ix_collector_events_source_time", "collector_events", ["source_node_id", "occurred_at"]
    )
    op.add_column("acl_aces", sa.Column("ordinal", sa.Integer(), nullable=True))
    op.create_check_constraint("ck_ace_ordinal", "acl_aces", "ordinal >= 0")
    op.create_unique_constraint("uq_ace_ordinal", "acl_aces", ["snapshot_id", "ordinal"])
    for table, backfill in [
        ("vss_snapshots", "created_at"),
        ("backup_jobs", "COALESCE(finished_at, started_at)"),
        ("backup_snapshots", "created_at"),
    ]:
        op.add_column(table, sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True))
        op.execute(sa.text(f"UPDATE {table} SET observed_at = {backfill}"))
        op.alter_column(table, "observed_at", nullable=False)


def downgrade() -> None:
    op.drop_column("backup_snapshots", "observed_at")
    op.drop_constraint("uq_ace_ordinal", "acl_aces", type_="unique")
    op.drop_constraint("ck_ace_ordinal", "acl_aces", type_="check")
    op.drop_column("acl_aces", "ordinal")
    op.drop_column("backup_jobs", "observed_at")
    op.drop_column("vss_snapshots", "observed_at")
    op.drop_index("ix_collector_events_source_time", table_name="collector_events")
    op.drop_table("collector_events")
