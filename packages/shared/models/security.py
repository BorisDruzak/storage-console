from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Index,
    Integer,
    String,
    Table,
    UniqueConstraint,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB

from .base import identity, metadata, reference, timestamp

users = Table(
    "users",
    metadata,
    identity(),
    Column("username", String(255), nullable=False, unique=True),
    Column("auth_provider", String(32), nullable=False),
    Column("provider_subject", String(255)),
    Column("password_hash", String(255)),
    Column("enabled", Boolean, nullable=False, server_default=true()),
    timestamp("created_at", default_now=True),
    UniqueConstraint("auth_provider", "provider_subject", name="uq_user_provider_subject"),
)
user_sessions = Table(
    "user_sessions",
    metadata,
    identity(),
    reference("user_id", "users.id"),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("csrf_hash", String(64), nullable=False),
    timestamp("created_at", default_now=True),
    timestamp("expires_at"),
    timestamp("last_used_at", default_now=True),
    timestamp("revoked_at", nullable=True),
    CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_session_token_hash"),
    CheckConstraint("csrf_hash ~ '^[0-9a-f]{64}$'", name="ck_session_csrf_hash"),
    CheckConstraint("expires_at > created_at", name="ck_session_expiry"),
    CheckConstraint("last_used_at >= created_at", name="ck_session_last_used"),
    Index("ix_user_sessions_user_expiry", "user_id", "expires_at"),
    Index("ix_user_sessions_expiry", "expires_at"),
)
login_rate_buckets = Table(
    "login_rate_buckets",
    metadata,
    Column("key", String(64), primary_key=True),
    timestamp("window_started_at"),
    Column("attempts", Integer, nullable=False),
    CheckConstraint("key ~ '^[0-9a-f]{64}$'", name="ck_login_rate_key"),
    CheckConstraint("attempts >= 0", name="ck_login_rate_attempts"),
)
roles = Table(
    "roles",
    metadata,
    identity(),
    Column("code", String(64), nullable=False, unique=True),
)
user_roles = Table(
    "user_roles",
    metadata,
    identity(),
    reference("user_id", "users.id"),
    reference("role_id", "roles.id"),
    UniqueConstraint("user_id", "role_id", name="uq_user_role"),
)
audit_log = Table(
    "audit_log",
    metadata,
    identity(),
    reference("user_id", "users.id", nullable=True),
    reference("collector_id", "collectors.id", nullable=True),
    Column("action", String(64), nullable=False),
    Column("resource_type", String(64), nullable=False),
    Column("resource_identity", String(255)),
    Column("result", String(32), nullable=False),
    timestamp("occurred_at", default_now=True),
    Column("details", JSONB, nullable=False),
)
