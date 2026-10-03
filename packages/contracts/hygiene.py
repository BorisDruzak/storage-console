from typing import Annotated, Literal

from pydantic import AwareDatetime, Field

from .common import Contract, NonNegative, NonNegative32, Quality, Record
from .inventory import Path


class PathSample(Contract):
    relative_path: Path
    path_length: NonNegative32
    bucket: Literal["240+", "260+", "320+", "400+", "500+"]


class LargeFileSample(Contract):
    relative_path: Path
    size_bytes: NonNegative
    last_write_at: AwareDatetime


class TempStats(Contract):
    classification: Literal["ACTIVE", "RECENT", "STALE"]
    file_count: NonNegative
    total_bytes: NonNegative


class HygieneRecord(Record):
    scope_identity: Path
    quality: Quality
    file_count: NonNegative
    directory_count: NonNegative
    total_bytes: NonNegative
    zero_byte_count: NonNegative
    long_paths: Annotated[list[PathSample], Field(max_length=1000)] = []
    large_files: Annotated[list[LargeFileSample], Field(max_length=1000)] = []
    temp_artifacts: Annotated[list[TempStats], Field(max_length=3)] = []
