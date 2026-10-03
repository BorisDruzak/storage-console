from sqlalchemy import BigInteger, Boolean, Column, String, Table, Text, UniqueConstraint

from .base import identity, metadata, reference, timestamp

principals = Table(
    "principals",
    metadata,
    identity(),
    Column("identity_namespace", String(255), nullable=False),
    Column("sid", String(255), nullable=False),
    Column("account_name", String(255)),
    Column("principal_type", String(32), nullable=False),
    UniqueConstraint("identity_namespace", "sid", name="uq_principal_identity"),
)
ad_groups = Table(
    "ad_groups",
    metadata,
    identity(),
    reference("principal_id", "principals.id"),
    Column("scope", String(32), nullable=False),
    Column("category", String(32), nullable=False),
    UniqueConstraint("principal_id", name="uq_ad_group_principal"),
)
group_memberships = Table(
    "group_memberships",
    metadata,
    identity(),
    reference("group_id", "ad_groups.id"),
    reference("member_principal_id", "principals.id"),
    timestamp("observed_at"),
    UniqueConstraint("group_id", "member_principal_id", name="uq_group_membership"),
)
acl_templates = Table(
    "acl_templates",
    metadata,
    identity(),
    Column("name", String(128), nullable=False, unique=True),
    Column("scope_pattern", Text, nullable=False),
    Column("expected_owner_identity", String(255)),
    Column("inheritance_expected", Boolean, nullable=False),
    timestamp("created_at", default_now=True),
)
acl_snapshots = Table(
    "acl_snapshots",
    metadata,
    identity(),
    reference("source_node_id", "source_nodes.id"),
    reference("object_id", "filesystem_objects.id", nullable=True),
    Column("scope_identity", Text, nullable=False),
    Column("dacl_fingerprint", String(64), nullable=False),
    reference("owner_principal_id", "principals.id", nullable=True),
    Column("inheritance_enabled", Boolean, nullable=False),
    timestamp("observed_at"),
)
acl_aces = Table(
    "acl_aces",
    metadata,
    identity(),
    reference("snapshot_id", "acl_snapshots.id"),
    reference("principal_id", "principals.id", nullable=True),
    Column("unresolved_sid", String(255)),
    Column("ace_type", String(16), nullable=False),
    Column("access_mask", BigInteger, nullable=False),
    Column("inherited", Boolean, nullable=False),
    Column("inheritance_flags", String(64)),
)
acl_findings = Table(
    "acl_findings",
    metadata,
    identity(),
    reference("snapshot_id", "acl_snapshots.id"),
    reference("template_id", "acl_templates.id", nullable=True),
    Column("finding_type", String(64), nullable=False),
    Column("state", String(32), nullable=False),
    Column("reason_code", String(64), nullable=False),
    timestamp("evaluated_at"),
)
