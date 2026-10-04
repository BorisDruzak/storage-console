"""Preserve dated simultaneous paths without indexing unbounded path text."""

from hashlib import sha256
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None
PAGE_SIZE = 256


def _tables():
    metadata = sa.MetaData()
    objects = sa.Table("filesystem_objects", metadata, autoload_with=op.get_bind())
    history = sa.Table("object_path_history", metadata, autoload_with=op.get_bind())
    states = sa.Table("object_path_states", metadata, autoload_with=op.get_bind())
    return objects, history, states


def _merge(connection, states, *, target, path, seen, ended, active, name, parent):
    key = sha256(path.encode()).hexdigest()
    row = (
        connection.execute(
            sa.select(states).where(states.c.object_id == target, states.c.path_digest == key)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        connection.execute(
            sa.insert(states).values(
                id=uuid4(),
                object_id=target,
                path_digest=key,
                relative_path=path,
                seen_at=seen,
                ended_at=ended,
                event_ended_at=ended,
                active_history_id=active,
                name=name,
                parent_file_id=parent,
            )
        )
        return
    if row["relative_path"] != path:
        raise RuntimeError("PATH_DIGEST_CONFLICT")
    values = {}
    if seen is not None and (row["seen_at"] is None or seen >= row["seen_at"]):
        values.update(seen_at=seen, name=name, parent_file_id=parent)
    if ended is not None and (row["ended_at"] is None or ended > row["ended_at"]):
        values["ended_at"] = ended
        values["event_ended_at"] = ended
    if active is not None:
        if row["active_history_id"] is not None and row["active_history_id"] != active:
            raise RuntimeError("DUPLICATE_ACTIVE_PATH_HISTORY")
        values["active_history_id"] = active
    if values:
        connection.execute(sa.update(states).where(states.c.id == row["id"]).values(**values))


def _backfill():
    connection = op.get_bind()
    objects, history, states = _tables()
    # DELETE used whole-object semantics before this revision, even with a path.
    connection.execute(
        sa.text("""
        UPDATE filesystem_objects AS o
        SET last_deleted_at = GREATEST(o.deleted_at, (
            SELECT MAX(e.occurred_at)
            FROM change_events e JOIN volumes v ON v.id = o.volume_id
            WHERE e.source_node_id = v.source_node_id
              AND e.volume_identity = v.unique_identity AND e.file_id = o.file_id
              AND e.event_type = 'DELETE'
        ))
    """)
    )
    connection.execute(
        sa.text("""
        UPDATE object_path_history AS h SET valid_until_at = o.deleted_at
        FROM filesystem_objects o
        WHERE h.object_id = o.id AND h.valid_until_at IS NULL AND o.deleted_at IS NOT NULL
    """)
    )
    cursor = None
    while True:
        query = (
            sa.select(
                history,
                objects.c.current_relative_path,
                objects.c.current_name,
                objects.c.parent_file_id,
                objects.c.last_seen_at,
            )
            .join(objects, objects.c.id == history.c.object_id)
            .order_by(history.c.id)
            .limit(PAGE_SIZE)
        )
        if cursor is not None:
            query = query.where(history.c.id > cursor)
        rows = connection.execute(query).mappings().all()
        if not rows:
            break
        for row in rows:
            representative = row["relative_path"] == row["current_relative_path"]
            active = row["valid_until_at"] is None
            _merge(
                connection,
                states,
                target=row["object_id"],
                path=row["relative_path"],
                seen=row["last_seen_at"] if active and representative else row["valid_from_at"],
                ended=row["valid_until_at"],
                active=row["id"] if active else None,
                name=row["current_name"] if representative else None,
                parent=row["parent_file_id"] if representative else None,
            )
        cursor = rows[-1]["id"]
    cursor = None
    while True:
        query = sa.select(objects).order_by(objects.c.id).limit(PAGE_SIZE)
        if cursor is not None:
            query = query.where(objects.c.id > cursor)
        rows = connection.execute(query).mappings().all()
        if not rows:
            break
        for obj in rows:
            path = obj["current_relative_path"]
            key = sha256(path.encode()).hexdigest()
            state = (
                connection.execute(
                    sa.select(states).where(
                        states.c.object_id == obj["id"], states.c.path_digest == key
                    )
                )
                .mappings()
                .one_or_none()
            )
            if state is None:
                active = None
                if obj["deleted_at"] is None:
                    active = uuid4()
                    connection.execute(
                        sa.insert(history).values(
                            id=active,
                            object_id=obj["id"],
                            relative_path=path,
                            valid_from_at=obj["first_seen_at"],
                        )
                    )
                _merge(
                    connection,
                    states,
                    target=obj["id"],
                    path=path,
                    seen=obj["last_seen_at"],
                    ended=obj["deleted_at"],
                    active=active,
                    name=obj["current_name"],
                    parent=obj["parent_file_id"],
                )
            elif state["relative_path"] != path:
                raise RuntimeError("PATH_DIGEST_CONFLICT")
            connection.execute(
                sa.update(objects)
                .where(objects.c.id == obj["id"])
                .values(
                    sole_path_digest=key,
                    sole_path_at=obj["last_seen_at"],
                )
            )
        cursor = rows[-1]["id"]
    # A retained pre-inventory deletion may be newer than an otherwise open path.
    connection.execute(
        sa.text("""
        UPDATE object_path_history AS h SET valid_until_at = o.last_deleted_at
        FROM object_path_states s JOIN filesystem_objects o ON o.id = s.object_id
        WHERE h.id = s.active_history_id AND o.last_deleted_at >= s.seen_at
    """)
    )
    connection.execute(
        sa.text("""
        UPDATE object_path_states AS s
        SET active_history_id = NULL, ended_at = GREATEST(s.ended_at, o.last_deleted_at)
        FROM filesystem_objects o
        WHERE o.id = s.object_id AND o.last_deleted_at >= s.seen_at
    """)
    )
    connection.execute(
        sa.text("""
        UPDATE filesystem_objects SET deleted_at = last_deleted_at
        WHERE last_deleted_at >= last_seen_at
    """)
    )


def upgrade() -> None:
    op.add_column("filesystem_objects", sa.Column("link_count", sa.BigInteger()))
    for name in ("link_count_at", "sole_path_at", "last_deleted_at"):
        op.add_column("filesystem_objects", sa.Column(name, sa.DateTime(timezone=True)))
    op.add_column("filesystem_objects", sa.Column("sole_path_digest", sa.String(64)))
    op.add_column(
        "filesystem_objects",
        sa.Column(
            "multiple_paths_observed", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.create_check_constraint(
        "ck_object_link_count", "filesystem_objects", "link_count BETWEEN 1 AND 4294967295"
    )
    op.create_table(
        "object_path_states",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("object_id", sa.Uuid(), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("path_digest", sa.String(64), nullable=False),
        sa.Column("name", sa.Text()),
        sa.Column("parent_file_id", sa.String(255)),
        sa.Column("seen_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("event_ended_at", sa.DateTime(timezone=True)),
        sa.Column("active_history_id", sa.Uuid()),
        sa.ForeignKeyConstraint(["object_id"], ["filesystem_objects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["active_history_id"], ["object_path_history.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("object_id", "path_digest", name="uq_object_path_state"),
        sa.UniqueConstraint("active_history_id", name="uq_path_state_active_history"),
    )
    op.create_index(
        "ix_changes_object_identity_time",
        "change_events",
        ["source_node_id", "volume_identity", "file_id", "occurred_at"],
    )
    _backfill()


def downgrade() -> None:
    connection = op.get_bind()
    _, _, states = _tables()
    multiple = connection.scalar(
        sa.select(states.c.object_id)
        .where(states.c.active_history_id.is_not(None))
        .group_by(states.c.object_id)
        .having(sa.func.count() > 1)
        .limit(1)
    )
    if multiple is not None:
        raise RuntimeError("SIMULTANEOUS_PATHS_REQUIRE_COMPATIBLE_ROLLBACK")
    op.drop_index("ix_changes_object_identity_time", table_name="change_events")
    op.drop_table("object_path_states")
    op.drop_constraint("ck_object_link_count", "filesystem_objects", type_="check")
    for name in (
        "multiple_paths_observed",
        "last_deleted_at",
        "sole_path_at",
        "sole_path_digest",
        "link_count_at",
        "link_count",
    ):
        op.drop_column("filesystem_objects", name)
