"""Ingestion pipeline: API → envelope validation → raw layer, fully metered.

Idempotency: reruns insert nothing new (version dedup in the loader), and
the incremental watermark is derived from the raw data itself, so a crashed
run resumes safely on the next execution.
"""

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime

from ingestion.config import Settings, get_settings
from ingestion.loaders.duckdb_loader import DuckDBLoader
from ingestion.schemas.envelope import RecordRejected, to_raw_record
from ingestion.socrata import SocrataClient
from ingestion.sources import get_source

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    run_id: str
    source: str
    mode: str
    rows_received: int
    rows_inserted: int
    rows_rejected: int
    duration_seconds: float
    watermark_after: datetime | None
    status: str


def ingest_source(
    source_key: str,
    *,
    settings: Settings | None = None,
    client: SocrataClient | None = None,
    loader: DuckDBLoader | None = None,
    max_records: int | None = None,
    incremental: bool = False,
) -> IngestResult:
    """Ingest one source. ``client``/``loader`` injectable for testing."""
    settings = settings or get_settings()
    source = get_source(source_key)
    owns_loader = loader is None
    loader = loader or DuckDBLoader(settings.mip_duckdb_path)
    client = client or SocrataClient(
        domain=settings.socrata_domain,
        app_token=settings.socrata_app_token,
        timeout=settings.request_timeout_seconds,
        max_retries=settings.max_retries,
        backoff_base=settings.backoff_base_seconds,
        backoff_cap=settings.backoff_cap_seconds,
    )
    max_records = max_records if max_records is not None else settings.mip_max_records

    where = source.sample_where
    mode = "sample"
    if incremental:
        watermark = loader.latest_updated_at(source_key)
        if watermark is not None:
            mode = "incremental"
            inc_clause = f":updated_at > '{watermark.isoformat()}'"
            where = f"({where}) AND ({inc_clause})" if where else inc_clause

    run_id = uuid.uuid4().hex[:12]
    loader.ensure_raw_table(source_key)
    loader.start_run(run_id, source_key, mode)
    logger.info(
        "ingest_started",
        extra={"run_id": run_id, "source": source_key, "mode": mode,
               "max_records": max_records, "where": where},
    )

    received = inserted = rejected = 0
    started = time.monotonic()
    contract_checked = False
    try:
        for page_num, page in enumerate(
            client.iter_pages(
                source.dataset_id,
                where=where,
                page_size=settings.mip_page_size,
                max_records=max_records,
                select_fields=source.select_fields,
            ),
            start=1,
        ):
            if not contract_checked and page and source.critical_fields:
                # Schema-change tripwire: sources rename/drop columns
                # without notice; absent keys must fail the run, not
                # silently null out downstream.
                present = set().union(*(row.keys() for row in page[:50]))
                missing = [f for f in source.critical_fields if f not in present]
                if missing:
                    raise RuntimeError(
                        f"source contract violation for '{source_key}': "
                        f"critical fields missing from API response: {missing}"
                    )
                contract_checked = True
            received += len(page)
            records = []
            for row in page:
                try:
                    records.append(to_raw_record(row, source))
                except RecordRejected as exc:
                    rejected += 1
                    loader.reject(source_key, run_id, exc.payload, exc.reason)
            inserted += loader.load_batch(source_key, records, run_id)
            logger.info(
                "page_loaded",
                extra={"run_id": run_id, "source": source_key, "page": page_num,
                       "received": received, "inserted": inserted, "rejected": rejected},
            )
    except Exception as exc:
        loader.finish_run(run_id, "failed", received, inserted, rejected, source_key, error=str(exc))
        logger.error("ingest_failed", extra={"run_id": run_id, "source": source_key, "error": str(exc)})
        if owns_loader:
            loader.close()
        raise

    duration = time.monotonic() - started
    loader.finish_run(run_id, "success", received, inserted, rejected, source_key)
    watermark_after = loader.latest_updated_at(source_key)
    total_raw = loader.raw_count(source_key)
    logger.info(
        "ingest_finished",
        extra={"run_id": run_id, "source": source_key, "mode": mode,
               "rows_received": received, "rows_inserted": inserted,
               "rows_rejected": rejected, "raw_total": total_raw,
               "duration_s": round(duration, 1)},
    )
    if owns_loader:
        loader.close()
    return IngestResult(
        run_id=run_id,
        source=source_key,
        mode=mode,
        rows_received=received,
        rows_inserted=inserted,
        rows_rejected=rejected,
        duration_seconds=duration,
        watermark_after=watermark_after,
        status="success",
    )
