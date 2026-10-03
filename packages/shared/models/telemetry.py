from sqlalchemy import CheckConstraint, Column, Float, Index, Integer, String, Table, Text

from .base import identity, metadata, reference, timestamp


def metric_table(name: str) -> Table:
    return Table(
        name,
        metadata,
        identity(),
        reference("source_node_id", "source_nodes.id"),
        Column("metric_name", String(128), nullable=False),
        Column("scope_identity", String(255), nullable=False, server_default="source"),
        timestamp("occurred_at"),
        Column("value", Float, nullable=False),
        Column("unit", String(32), nullable=False),
        Column("quality", String(16), nullable=False, server_default="COMPLETE"),
        Column("sample_count", Integer, nullable=False, server_default="1"),
        CheckConstraint("sample_count > 0", name=f"ck_{name}_sample_count"),
        Index(f"ix_{name}_source_metric_time", "source_node_id", "metric_name", "occurred_at"),
    )


metric_samples_1m = metric_table("metric_samples_1m")
metric_samples_1h = metric_table("metric_samples_1h")
metric_samples_1d = metric_table("metric_samples_1d")
diagnostic_bundles = Table(
    "diagnostic_bundles",
    metadata,
    identity(),
    reference("source_node_id", "source_nodes.id"),
    Column("trigger_type", String(64), nullable=False),
    timestamp("triggered_at"),
    timestamp("first_event_at"),
    timestamp("last_event_at"),
    Column("storage_reference", Text),
    Column("sha256", String(64)),
    Column("status", String(32), nullable=False),
    CheckConstraint("last_event_at >= first_event_at", name="ck_diagnostic_range"),
)
