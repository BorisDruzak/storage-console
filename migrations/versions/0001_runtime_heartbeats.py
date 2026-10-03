"""Foundation runtime heartbeat, no collector/domain data yet."""
import sqlalchemy as sa
from alembic import op

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'service_heartbeats',
        sa.Column('service', sa.String(64), primary_key=True),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('service_heartbeats')
