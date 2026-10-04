"""NYC 311 Service Requests (2010–present).

https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2010-to-Present/erm2-nwe9

~41M rows total. The dev sample is bounded to a recent window: recent
complaints are what the analytics care about, and the window is one config
value away from a full backfill.
"""

from ingestion.sources.base import SourceConfig

NYC_311 = SourceConfig(
    key="nyc_311",
    name="NYC 311 Service Requests",
    dataset_id="erm2-nwe9",
    pk_fields=("unique_key",),
    # 180 days of contiguous coverage: trend analytics (90d vs prior 90d)
    # need both windows fully populated. NOTE keyset pagination fills the
    # window oldest-first — max_records must cover the whole window
    # (~8.2K complaints/day citywide → ~1.5M for 180 days) or the sample
    # silently truncates to the window's early months.
    sample_where="created_date >= '2026-02-09T00:00:00'",
    description=(
        "Service complaints (heat, noise, plumbing, ...) with incident address, "
        "borough, coordinates, and sometimes BBL. Primary key: unique_key. "
        "Incremental via :updated_at (captures status changes, not just inserts)."
    ),
)
