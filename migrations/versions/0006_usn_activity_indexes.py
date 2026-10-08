"""Bound Activity time queries and deduplicate canonical USN event identities."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_changes_time_id", "change_events", ["occurred_at", "id"])
    op.create_index("ix_changes_source_type_time_id", "change_events",
                    ["source_node_id", "event_type", "occurred_at", "id"])
    # Existing non-USN event semantics are unaffected. Conflicting pre-existing
    # USN identities fail migration instead of silently discarding evidence.
    op.create_index("uq_changes_usn_source_event", "change_events",
                    ["source_node_id", "source_event_id"], unique=True,
                    postgresql_where=sa.text("source_event_id LIKE 'ntfs-usn:%'"))


def downgrade():
    op.drop_index("uq_changes_usn_source_event", table_name="change_events")
    op.drop_index("ix_changes_source_type_time_id", table_name="change_events")
    op.drop_index("ix_changes_time_id", table_name="change_events")
