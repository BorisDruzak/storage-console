from sqlalchemy import Column, String, Table, UniqueConstraint
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
    timestamp("created_at", default_now=True),
    UniqueConstraint("auth_provider", "provider_subject", name="uq_user_provider_subject"),
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
