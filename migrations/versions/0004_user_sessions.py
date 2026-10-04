"""Persist revocable sessions and login rate limits.

Downgrade invalidates sessions and removes user disabling. Canonical role data
is preserved so existing assignments are not silently deleted.
"""

from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import insert

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true())
    )
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_used_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_session_token_hash"),
        sa.CheckConstraint("csrf_hash ~ '^[0-9a-f]{64}$'", name="ck_session_csrf_hash"),
        sa.CheckConstraint("expires_at > created_at", name="ck_session_expiry"),
        sa.CheckConstraint("last_used_at >= created_at", name="ck_session_last_used"),
    )
    op.create_index("ix_user_sessions_user_expiry", "user_sessions", ["user_id", "expires_at"])
    op.create_index("ix_user_sessions_expiry", "user_sessions", ["expires_at"])
    op.create_table(
        "login_rate_buckets",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.CheckConstraint("key ~ '^[0-9a-f]{64}$'", name="ck_login_rate_key"),
        sa.CheckConstraint("attempts >= 0", name="ck_login_rate_attempts"),
    )
    roles = sa.table("roles", sa.column("id", sa.Uuid()), sa.column("code", sa.String()))
    for code in ("storage_admin", "storage_operator", "auditor", "analyst", "viewer"):
        op.execute(
            insert(roles)
            .values(id=uuid5(NAMESPACE_URL, f"urn:storage-console:role:{code}"), code=code)
            .on_conflict_do_nothing(index_elements=["code"])
        )


def downgrade() -> None:
    op.drop_table("login_rate_buckets")
    op.drop_index("ix_user_sessions_expiry", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_expiry", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_column("users", "enabled")
