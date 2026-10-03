from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

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
    snapshot_created_at: AwareDatetime | None = None
    consistency: Literal["CRASH_CONSISTENT", "GUEST_AGENT", "VSS_QUIESCED", "UNKNOWN"] = "UNKNOWN"
    verification_state: Literal["COMPLETE", "FAILED", "UNKNOWN"] | None = None
    verified_at: AwareDatetime | None = None
    restore_test_state: Literal["COMPLETE", "FAILED", "UNKNOWN"] | None = None
    tested_at: AwareDatetime | None = None
    measured_rto_seconds: NonNegative32 | None = None
    error_code: Code | None = None

    @model_validator(mode="after")
    def consistent_evidence(self) -> Self:
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("Backup finishes before it starts")
        if self.state in {"COMPLETE", "FAILED"} and self.finished_at is None:
            raise ValueError("Terminal backup requires finish time")
        if (self.snapshot_identity is None) != (self.snapshot_created_at is None):
            raise ValueError("Snapshot requires identity and creation time")
        evidence = (
            self.verification_state,
            self.verified_at,
            self.restore_test_state,
            self.tested_at,
            self.measured_rto_seconds,
        )
        if self.snapshot_identity is None and (
            any(v is not None for v in evidence) or self.consistency != "UNKNOWN"
        ):
            raise ValueError("Recovery evidence requires a snapshot")
        for state, time in [
            (self.verification_state, self.verified_at),
            (self.restore_test_state, self.tested_at),
        ]:
            if (state is None) != (time is None):
                raise ValueError("Evidence requires state and observation time")
            if time is not None and self.snapshot_created_at is not None:
                if time < self.snapshot_created_at:
                    raise ValueError("Evidence predates snapshot")
        if self.measured_rto_seconds is not None and self.tested_at is None:
            raise ValueError("Measured RTO requires restore test evidence")
        for time in [
            self.started_at,
            self.finished_at,
            self.snapshot_created_at,
            self.verified_at,
            self.tested_at,
        ]:
            if time is not None and time > self.occurred_at:
                raise ValueError("Evidence occurs after its observation")
        return self


RecoveryRecord = Annotated[VSSRecord | BackupRecord, Field(discriminator="kind")]
