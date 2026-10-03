from typing import Annotated, Literal

from pydantic import AwareDatetime, Field

from .common import Code, Identity, NonNegative32, Record


class VSSRecord(Record):
    kind: Literal["vss"] = "vss"
    volume_identity: Identity
    snapshot_identity: Identity
    created_at: AwareDatetime
    state: Literal["AVAILABLE", "UNAVAILABLE", "UNKNOWN"]


class BackupRecord(Record):
    kind: Literal["backup"] = "backup"
    job_identity: Identity
    workload_identity: Identity
    state: Literal["RUNNING", "COMPLETE", "FAILED", "UNKNOWN"]
    started_at: AwareDatetime
    finished_at: AwareDatetime | None = None
    snapshot_identity: Identity | None = None
    consistency: Literal["CRASH_CONSISTENT", "GUEST_AGENT", "VSS_QUIESCED", "UNKNOWN"] = "UNKNOWN"
    verification_state: Literal["COMPLETE", "FAILED", "UNKNOWN"] | None = None
    verified_at: AwareDatetime | None = None
    restore_test_state: Literal["COMPLETE", "FAILED", "UNKNOWN"] | None = None
    tested_at: AwareDatetime | None = None
    measured_rto_seconds: NonNegative32 | None = None
    error_code: Code | None = None


RecoveryRecord = Annotated[VSSRecord | BackupRecord, Field(discriminator="kind")]
