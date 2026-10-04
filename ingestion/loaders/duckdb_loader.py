"""DuckDB warehouse loader.

Raw layer contract:
- ``raw.<source>`` is an append-only versioned log: one row per
  (source_record_id, socrata_updated_at). Reruns never duplicate a version;
  updated source records append a new version. Staging selects the latest
  version per record.
- ``meta.ingest_runs`` records every pipeline execution.
- ``meta.rejected_records`` is the dead-letter table — nothing is silently
  dropped.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd

from ingestion.schemas.envelope import RawRecord

logger = logging.getLogger(__name__)

_EPOCH = "TIMESTAMP '1970-01-01'"


def _utc_naive(dt: datetime | None) -> datetime | None:
    """Normalize to naive UTC before storage.

    Warehouse convention: every TIMESTAMP column holds naive UTC. DuckDB
    converts tz-aware values to the *session's local* timezone on insert
    into TIMESTAMP columns, which would make the warehouse's contents
    depend on the machine it ran on.
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


class DuckDBLoader:
    def __init__(self, db_path: Path | str):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = duckdb.connect(str(db_path))
        self._init_meta()

    def close(self) -> None:
        self.conn.close()

    # -- schema ------------------------------------------------------------

    def _init_meta(self) -> None:
        self.conn.execute("CREATE SCHEMA IF NOT EXISTS raw")
        self.conn.execute("CREATE SCHEMA IF NOT EXISTS meta")
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meta.ingest_runs (
                run_id VARCHAR PRIMARY KEY,
                source VARCHAR NOT NULL,
                mode VARCHAR NOT NULL,
                started_at TIMESTAMP NOT NULL,
                finished_at TIMESTAMP,
                status VARCHAR NOT NULL,
                rows_received BIGINT NOT NULL DEFAULT 0,
                rows_inserted BIGINT NOT NULL DEFAULT 0,
                rows_rejected BIGINT NOT NULL DEFAULT 0,
                watermark_before TIMESTAMP,
                watermark_after TIMESTAMP,
                error VARCHAR
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meta.rejected_records (
                source VARCHAR NOT NULL,
                run_id VARCHAR NOT NULL,
                payload JSON NOT NULL,
                reason VARCHAR NOT NULL,
                rejected_at TIMESTAMP NOT NULL DEFAULT now()
            )
            """
        )

    def ensure_raw_table(self, source_key: str) -> None:
        self.conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS raw.{source_key} (
                source_record_id VARCHAR NOT NULL,
                socrata_row_id VARCHAR,
                socrata_updated_at TIMESTAMP,
                payload JSON NOT NULL,
                run_id VARCHAR NOT NULL,
                ingested_at TIMESTAMP NOT NULL DEFAULT now()
            )
            """
        )

    # -- loading -----------------------------------------------------------

    def load_batch(self, source_key: str, records: list[RawRecord], run_id: str) -> int:
        """Insert record versions not already present. Returns rows inserted."""
        if not records:
            return 0
        self.ensure_raw_table(source_key)
        batch = pd.DataFrame(
            {
                "source_record_id": [r.source_record_id for r in records],
                "socrata_row_id": [r.socrata_row_id for r in records],
                "socrata_updated_at": [_utc_naive(r.socrata_updated_at) for r in records],
                "payload": [json.dumps(r.payload) for r in records],
            }
        )
        # A record may legitimately appear twice within one run (rare, but
        # possible across incremental windows); keep one row per version.
        batch = batch.drop_duplicates(subset=["source_record_id", "socrata_updated_at"], keep="last")
        self.conn.register("_batch", batch)
        inserted = self.conn.execute(
            f"""
            INSERT INTO raw.{source_key}
                (source_record_id, socrata_row_id, socrata_updated_at, payload, run_id)
            SELECT b.source_record_id, b.socrata_row_id, b.socrata_updated_at, b.payload, ?
            FROM _batch b
            WHERE NOT EXISTS (
                SELECT 1 FROM raw.{source_key} r
                WHERE r.source_record_id = b.source_record_id
                  AND coalesce(r.socrata_updated_at, {_EPOCH})
                      = coalesce(b.socrata_updated_at, {_EPOCH})
            )
            """,
            [run_id],
        ).fetchone()[0]
        self.conn.unregister("_batch")
        return int(inserted)

    def reject(self, source_key: str, run_id: str, payload: dict, reason: str) -> None:
        self.conn.execute(
            "INSERT INTO meta.rejected_records (source, run_id, payload, reason) VALUES (?, ?, ?, ?)",
            [source_key, run_id, json.dumps(payload, default=str), reason],
        )

    # -- run metadata --------------------------------------------------------

    def start_run(self, run_id: str, source_key: str, mode: str) -> None:
        self.conn.execute(
            """
            INSERT INTO meta.ingest_runs (run_id, source, mode, started_at, status, watermark_before)
            VALUES (?, ?, ?, ?, 'running', ?)
            """,
            [
                run_id,
                source_key,
                mode,
                _utc_naive(datetime.now(UTC)),
                self.latest_updated_at(source_key),
            ],
        )

    def finish_run(
        self,
        run_id: str,
        status: str,
        rows_received: int,
        rows_inserted: int,
        rows_rejected: int,
        source_key: str,
        error: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE meta.ingest_runs
            SET finished_at = ?, status = ?, rows_received = ?, rows_inserted = ?,
                rows_rejected = ?, watermark_after = ?, error = ?
            WHERE run_id = ?
            """,
            [
                _utc_naive(datetime.now(UTC)),
                status,
                rows_received,
                rows_inserted,
                rows_rejected,
                self.latest_updated_at(source_key),
                error,
                run_id,
            ],
        )

    # -- queries -------------------------------------------------------------

    def latest_updated_at(self, source_key: str) -> datetime | None:
        """Incremental watermark, derived from the data itself (no side state)."""
        if not self._raw_table_exists(source_key):
            return None
        row = self.conn.execute(f"SELECT max(socrata_updated_at) FROM raw.{source_key}").fetchone()
        return row[0]

    def raw_count(self, source_key: str) -> int:
        if not self._raw_table_exists(source_key):
            return 0
        return self.conn.execute(f"SELECT count(*) FROM raw.{source_key}").fetchone()[0]

    def _raw_table_exists(self, source_key: str) -> bool:
        row = self.conn.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='raw' AND table_name=?",
            [source_key],
        ).fetchone()
        return row[0] > 0
