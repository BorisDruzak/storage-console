from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from .common import Identity, Record


class EvidenceRecord(Record):
    source_event_id: Identity
    evidence_type: Literal["WINDOWS_4663", "WINDOWS_4660", "WINDOWS_5145", "COLLECTOR"]
    change_event_id: UUID | None = None
    actor_identity: Identity | None = None
    client_identity: Identity | None = None
    confidence: Annotated[float, Field(ge=0, le=1)]
