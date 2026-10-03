from typing import Annotated

from pydantic import Field

from .common import Identity, Quality, Record


class TelemetryRecord(Record):
    metric_name: Annotated[str, Field(min_length=1, max_length=128)]
    scope_identity: Identity = "source"
    value: float
    unit: Annotated[str, Field(min_length=1, max_length=32)]
    quality: Quality = "COMPLETE"
