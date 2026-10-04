"""Source configuration model.

Each public dataset is described declaratively; connectors share one code
path (client + loader + pipeline) parameterized by these configs.
"""

from pydantic import BaseModel


class SourceConfig(BaseModel, frozen=True):
    key: str
    """Registry key; also the raw table name (``raw.<key>``)."""

    name: str
    dataset_id: str
    """Socrata dataset identifier (the 4x4 id in the API URL)."""

    pk_fields: tuple[str, ...]
    """Payload field(s) forming the source primary key. Composite keys are
    joined with ``|`` to build ``source_record_id``. Verified by profiling
    before a source is onboarded.

    Empty tuple = the source has no reliable natural key (verified against
    the API, e.g. DOB NOW permits contain ~15% duplicate rows even on the
    full natural key); identity falls back to Socrata's stable ``:id`` and
    business-key dedup happens in staging, where the rate is measured."""

    sample_where: str | None = None
    """SoQL filter bounding the local dev sample (e.g. a recent date window).
    Widen or remove to scale up; ``max_records`` still applies either way."""

    select_fields: tuple[str, ...] | None = None
    """Optional column projection. For wide datasets (PLUTO has ~90 columns)
    fetching only what the platform uses cuts transfer size massively."""

    critical_fields: tuple[str, ...] = ()
    """Fields downstream layers depend on. If a source SCHEMA CHANGE removes
    one, ingestion detects it on the first page and fails loudly instead of
    letting NULLs flow silently into staging (Phase 16)."""

    description: str = ""

    def build_record_id(self, row: dict) -> str:
        """Derive the stable source record id from a payload row.

        Raises ValueError if any key component is missing/blank — callers
        route such rows to the rejected-records table.
        """
        if not self.pk_fields:
            row_id = str(row.get(":id") or "").strip()
            if not row_id:
                raise ValueError("missing ':id' system field (no natural key configured)")
            return row_id
        parts = []
        for field in self.pk_fields:
            value = str(row.get(field) or "").strip()
            if not value:
                raise ValueError(f"missing primary key component '{field}'")
            parts.append(value)
        return "|".join(parts)
