"""Bound audit alias reconciliation reads without rewriting change history."""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_changes_source_volume_time_id",
        "change_events",
        ["source_node_id", "volume_identity", "occurred_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_changes_source_volume_time_id", table_name="change_events")
