"""Warehouse IO shared by normalization and entity resolution."""

import json
import time
import uuid
from datetime import UTC, datetime

import duckdb
import pandas as pd


def latest_payloads(conn: duckdb.DuckDBPyConnection, source_key: str) -> list[dict]:
    """Latest version of every raw record's payload, with its record id."""
    rows = conn.execute(
        f"""
        SELECT source_record_id, payload FROM (
            SELECT source_record_id, payload,
                   row_number() OVER (
                       PARTITION BY source_record_id
                       ORDER BY socrata_updated_at DESC NULLS LAST, ingested_at DESC
                   ) AS rn
            FROM raw.{source_key}
        ) WHERE rn = 1
        """
    ).fetchall()
    out = []
    for record_id, payload in rows:
        data = json.loads(payload)
        data["_source_record_id"] = record_id
        out.append(data)
    return out


def replace_table(conn: duckdb.DuckDBPyConnection, schema: str, name: str, df: pd.DataFrame) -> int:
    """Idempotently materialize a DataFrame as ``schema.name``."""
    conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    conn.register("_stage_df", df)
    conn.execute(f"CREATE OR REPLACE TABLE {schema}.{name} AS SELECT * FROM _stage_df")
    conn.unregister("_stage_df")
    return len(df)


class PipelineRun:
    """Context manager recording a step into meta.pipeline_runs (Phase 13)."""

    DDL = """
        CREATE TABLE IF NOT EXISTS meta.pipeline_runs (
            run_id VARCHAR PRIMARY KEY,
            pipeline_name VARCHAR NOT NULL,
            started_at TIMESTAMP NOT NULL,
            finished_at TIMESTAMP,
            status VARCHAR NOT NULL,
            records_processed BIGINT DEFAULT 0,
            records_failed BIGINT DEFAULT 0,
            duration_seconds DOUBLE,
            metrics JSON,
            error VARCHAR
        )
    """

    def __init__(self, conn: duckdb.DuckDBPyConnection, pipeline_name: str):
        self.conn = conn
        self.pipeline_name = pipeline_name
        self.run_id = uuid.uuid4().hex[:12]
        self.records_processed = 0
        self.records_failed = 0
        self.metrics: dict = {}

    def __enter__(self) -> "PipelineRun":
        self.conn.execute("CREATE SCHEMA IF NOT EXISTS meta")
        self.conn.execute(self.DDL)
        self._t0 = time.monotonic()
        self.conn.execute(
            "INSERT INTO meta.pipeline_runs (run_id, pipeline_name, started_at, status)"
            " VALUES (?, ?, ?, 'running')",
            [self.run_id, self.pipeline_name, datetime.now(UTC).replace(tzinfo=None)],
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        status = "failed" if exc_type else "success"
        self.conn.execute(
            """
            UPDATE meta.pipeline_runs
            SET finished_at = ?, status = ?, records_processed = ?, records_failed = ?,
                duration_seconds = ?, metrics = ?, error = ?
            WHERE run_id = ?
            """,
            [
                datetime.now(UTC).replace(tzinfo=None),
                status,
                self.records_processed,
                self.records_failed,
                round(time.monotonic() - self._t0, 2),
                json.dumps(self.metrics),
                str(exc) if exc else None,
                self.run_id,
            ],
        )
