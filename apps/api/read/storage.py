from datetime import datetime
from typing import cast

from sqlalchemy.engine import RowMapping

from packages.contracts.common import Quality
from packages.contracts.read import Share, Volume


def quality(at: datetime, now: datetime, cadence: int) -> Quality:
    if at > now:
        return "UNAVAILABLE"
    return "COMPLETE" if (now - at).total_seconds() <= cadence else "STALE"


def volume(row: RowMapping, now: datetime, aliases: list[str], stale_seconds: int) -> Volume:
    result_quality = quality(row["last_seen_at"], now, stale_seconds)
    if result_quality == "COMPLETE" and (row["total_bytes"] is None or row["free_bytes"] is None):
        result_quality = "PARTIAL"
    return Volume.model_validate(
        dict(
            **{
                key: row[key]
                for key in Volume.model_fields
                if key not in {"mount_aliases", "quality"}
            },
            mount_aliases=list(aliases),
            quality=result_quality,
        )
    )


def share(row: RowMapping, now: datetime, stale_seconds: int) -> Share:
    values = {key: row[key] for key in Share.model_fields if key != "quality"}
    values["quality"] = cast(
        str, quality(row["last_seen_at"], now, stale_seconds)
    )
    return Share.model_validate(values)
