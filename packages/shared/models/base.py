from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Uuid, func

from packages.shared.database import metadata

__all__ = ["metadata", "identity", "reference", "timestamp"]


def identity() -> Column[UUID]:
    return Column("id", Uuid, primary_key=True, default=uuid4)


def reference(name: str, target: str, *, nullable: bool = False) -> Column[UUID]:
    return Column(name, Uuid, ForeignKey(target, ondelete="RESTRICT"), nullable=nullable)


def timestamp(name: str, *, nullable: bool = False, default_now: bool = False) -> Column[datetime]:
    return Column(
        name,
        DateTime(timezone=True),
        nullable=nullable,
        server_default=func.now() if default_now else None,
    )
