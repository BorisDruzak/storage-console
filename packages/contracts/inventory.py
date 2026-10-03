from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .common import Identity, NonNegative, Record

Path = Annotated[str, Field(min_length=1, max_length=32767)]


class VolumeRecord(Record):
    kind: Literal["volume"] = "volume"
    unique_identity: Identity
    filesystem: Annotated[str, Field(min_length=1, max_length=32)]
    label: Identity | None = None
    mount_aliases: Annotated[list[Path], Field(max_length=128)] = []
    total_bytes: NonNegative | None = None
    free_bytes: NonNegative | None = None

    @model_validator(mode="after")
    def validate_capacity(self) -> Self:
        if self.total_bytes is not None and self.free_bytes is not None:
            if self.free_bytes > self.total_bytes:
                raise ValueError("Free capacity exceeds total capacity")
        if len(set(self.mount_aliases)) != len(self.mount_aliases):
            raise ValueError("Duplicate mount aliases")
        return self


class ShareRecord(Record):
    kind: Literal["share"] = "share"
    name: Identity
    volume_identity: Identity | None = None
    relative_path: Path
    protocol: Literal["SMB", "NFS"]


class FileObjectRecord(Record):
    kind: Literal["object"] = "object"
    volume_identity: Identity
    file_id: Identity
    parent_file_id: Identity | None = None
    object_type: Literal["FILE", "DIRECTORY"]
    name: Path
    relative_path: Path
    size_bytes: NonNegative | None = None


InventoryRecord = Annotated[
    VolumeRecord | ShareRecord | FileObjectRecord, Field(discriminator="kind")
]
