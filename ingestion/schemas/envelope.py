"""Raw-record envelope: the minimal contract a record must satisfy at ingest.

Deliberately light validation here — a record only needs an identity and a
parseable version timestamp to enter the raw layer. Semantic validation
(dates, coordinates, addresses) happens in staging, where failures are
visible and testable rather than causing data loss at the door.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ingestion.sources.base import SourceConfig


class RecordRejected(Exception):
    """Record cannot enter the raw layer; carries the reason for the DLQ."""

    def __init__(self, reason: str, payload: dict):
        super().__init__(reason)
        self.reason = reason
        self.payload = payload


class RawRecord(BaseModel):
    source_record_id: str = Field(min_length=1)
    socrata_row_id: str | None = None
    socrata_updated_at: datetime | None = None
    payload: dict[str, Any]


def to_raw_record(row: dict, source: SourceConfig) -> RawRecord:
    """Build the envelope for one API row.

    Raises RecordRejected when the source primary key is missing/blank or
    the version timestamp is unparseable.
    """
    try:
        record_id = source.build_record_id(row)
    except ValueError as exc:
        raise RecordRejected(str(exc), row) from None

    raw_updated = row.get(":updated_at")
    updated_at: datetime | None = None
    if raw_updated:
        try:
            updated_at = datetime.fromisoformat(str(raw_updated).replace("Z", "+00:00"))
        except ValueError:
            raise RecordRejected(f"unparseable :updated_at '{raw_updated}'", row) from None

    payload = {k: v for k, v in row.items() if not k.startswith(":")}
    return RawRecord(
        source_record_id=record_id,
        socrata_row_id=row.get(":id"),
        socrata_updated_at=updated_at,
        payload=payload,
    )
