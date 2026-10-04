#!/usr/bin/env python3
"""Publish marts + observability tables from DuckDB to Postgres.

DuckDB is the transformation engine; Postgres is the serving layer that
Metabase reads. Uses DuckDB's postgres extension so the copy is a single
SQL statement per table (no pandas round-trip).

Connection comes from PG_* env vars (see .env.example / docker-compose).
"""

import os
import sys

import duckdb

from ingestion.config import get_settings
from ingestion.logging_setup import configure_logging

PUBLISH = {
    "marts": [
        "dim_property", "dim_owner", "dim_business", "bridge_property_source",
        "fct_complaints", "mart_property_risk", "mart_landlord_performance",
        "mart_business_activity", "mart_neighborhood_operations",
    ],
    "meta": ["ingest_runs", "pipeline_runs", "rejected_records"],
    "er": ["review_queue", "owner_review_queue", "business_review_queue"],
}


def pg_dsn() -> str:
    host = os.environ.get("PG_HOST", "localhost")
    port = os.environ.get("PG_PORT", "5433")
    db = os.environ.get("PG_DB", "mip")
    user = os.environ.get("PG_USER", "mip")
    password = os.environ.get("PG_PASSWORD", "mip_local_dev")
    return f"host={host} port={port} dbname={db} user={user} password={password}"


def main() -> int:
    configure_logging()
    # NOT read_only: DuckDB propagates read-only mode to attached
    # databases, which would make the Postgres side unwritable.
    conn = duckdb.connect(str(get_settings().mip_duckdb_path))
    conn.execute("INSTALL postgres; LOAD postgres;")
    conn.execute(f"ATTACH '{pg_dsn()}' AS pg (TYPE postgres)")

    published = 0
    for schema, tables in PUBLISH.items():
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS pg.{schema}")
        for table in tables:
            exists = conn.execute(
                "SELECT count(*) FROM information_schema.tables"
                " WHERE table_schema = ? AND table_name = ?",
                [schema, table],
            ).fetchone()[0]
            if not exists:
                print(f"skip {schema}.{table} (not built locally)")
                continue
            conn.execute(f"DROP TABLE IF EXISTS pg.{schema}.{table}")
            conn.execute(
                f"CREATE TABLE pg.{schema}.{table} AS SELECT * FROM {schema}.{table}"
            )
            n = conn.execute(f"SELECT count(*) FROM pg.{schema}.{table}").fetchone()[0]
            print(f"published {schema}.{table}: {n:,} rows")
            published += 1
    conn.close()
    print(f"done: {published} tables")
    return 0


if __name__ == "__main__":
    sys.exit(main())
