"""Nightly municipal-intelligence pipeline.

    ingest_311 ─┐
    ingest_permits ─┤
    ingest_licenses ─┼─> normalize ─> resolve_entities ─> dbt_run ─> dbt_test ─> publish
    ingest_pluto ───┘

Design notes:
- Each ingest task is incremental (``:updated_at`` watermark) and
  idempotent (versioned raw dedup) — a retried or re-run task never
  duplicates data.
- Ingests are declared parallel, but the pool serializes them: DuckDB is
  single-writer, and honesty in the DAG beats fake parallelism. (With a
  Postgres warehouse backend the pool constraint simply disappears.)
- dbt_test gates publish: a red data-quality suite stops the marts from
  reaching analysts, and the failed task carries the test output.
"""

from datetime import datetime, timedelta

from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

from airflow import DAG

MIP = "/opt/mip"
DBT = f"cd {MIP}/dbt && dbt {{}} --profiles-dir . --project-dir ."

default_args = {
    "owner": "data-platform",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
}


def _ingest(source_key: str, **_context) -> dict:
    from ingestion.logging_setup import configure_logging
    from ingestion.pipeline import ingest_source

    configure_logging()
    result = ingest_source(source_key, incremental=True)
    return result.__dict__


def _normalize(**_context) -> list:
    from ingestion.config import get_settings
    from ingestion.logging_setup import configure_logging
    from normalization.runner import run_all

    configure_logging()
    return run_all(get_settings().mip_duckdb_path)


def _resolve(**_context) -> dict:
    import duckdb

    from entity_resolution.config import ERConfig
    from entity_resolution.matcher import match_properties
    from entity_resolution.name_matcher import resolve_businesses, resolve_owners
    from entity_resolution.portfolio import build_owner_groups
    from ingestion.config import get_settings
    from ingestion.logging_setup import configure_logging

    configure_logging()
    cfg = ERConfig()  # fails fast on threshold misconfiguration
    conn = duckdb.connect(str(get_settings().mip_duckdb_path))
    try:
        return {
            "properties": match_properties(conn, cfg),
            "owners": resolve_owners(conn, cfg),
            "businesses": resolve_businesses(conn, cfg),
            "portfolios": build_owner_groups(conn),
        }
    finally:
        conn.close()


with DAG(
    dag_id="municipal_intelligence",
    description="311 + permits + licenses + PLUTO -> canonical entities -> marts -> Metabase",
    schedule="0 5 * * *",  # nightly, after NYC Open Data's own refreshes
    start_date=datetime(2026, 8, 1),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["municipal-intelligence"],
) as dag:
    ingest_tasks = [
        PythonOperator(
            task_id=f"ingest_{key}",
            python_callable=_ingest,
            op_kwargs={"source_key": key},
            pool="duckdb_writer",  # single-writer warehouse
        )
        for key in ("nyc_311", "dob_permits", "dca_licenses", "pluto",
                    "hpd_registrations", "hpd_contacts")
    ]

    normalize = PythonOperator(
        task_id="normalize",
        python_callable=_normalize,
        pool="duckdb_writer",
        execution_timeout=timedelta(minutes=30),
    )

    resolve_entities = PythonOperator(
        task_id="resolve_entities",
        python_callable=_resolve,
        pool="duckdb_writer",
        execution_timeout=timedelta(minutes=30),
    )

    dbt_run = BashOperator(task_id="dbt_run", bash_command=DBT.format("run"), pool="duckdb_writer")
    dbt_test = BashOperator(task_id="dbt_test", bash_command=DBT.format("test"), pool="duckdb_writer")

    publish = BashOperator(
        task_id="publish_postgres",
        bash_command=f"cd {MIP} && python scripts/publish_postgres.py",
        pool="duckdb_writer",
    )

    ingest_tasks >> normalize >> resolve_entities >> dbt_run >> dbt_test >> publish
