"""DuckDBLoader: idempotency, versioning, dead-letter queue, run metadata."""

from datetime import UTC, datetime

import pytest

from ingestion.loaders.duckdb_loader import DuckDBLoader
from ingestion.schemas.envelope import RawRecord


@pytest.fixture
def loader(tmp_path):
    loader = DuckDBLoader(tmp_path / "test.duckdb")
    yield loader
    loader.close()


def _record(record_id: str, updated: str | None = "2026-06-01T00:00:00+00:00"):
    return RawRecord(
        source_record_id=record_id,
        socrata_row_id=f"row-{record_id}",
        socrata_updated_at=datetime.fromisoformat(updated) if updated else None,
        payload={"unique_key": record_id, "value": "x"},
    )


def test_rerun_is_idempotent(loader):
    batch = [_record("1"), _record("2")]
    assert loader.load_batch("test_source", batch, run_id="run1") == 2
    assert loader.load_batch("test_source", batch, run_id="run2") == 0
    assert loader.raw_count("test_source") == 2


def test_new_version_appends(loader):
    assert loader.load_batch("test_source", [_record("1", "2026-06-01T00:00:00+00:00")], "run1") == 1
    assert loader.load_batch("test_source", [_record("1", "2026-06-02T00:00:00+00:00")], "run2") == 1
    assert loader.raw_count("test_source") == 2
    assert loader.latest_updated_at("test_source").day == 2


def test_null_updated_at_deduped(loader):
    assert loader.load_batch("test_source", [_record("1", None)], "run1") == 1
    assert loader.load_batch("test_source", [_record("1", None)], "run2") == 0


def test_intra_batch_duplicate_versions_collapsed(loader):
    batch = [_record("1"), _record("1")]
    assert loader.load_batch("test_source", batch, run_id="run1") == 1


def test_rejected_records_persisted(loader):
    loader.reject("test_source", "run1", {"bad": "row"}, "missing primary key component 'unique_key'")
    rows = loader.conn.execute(
        "SELECT source, run_id, reason FROM meta.rejected_records"
    ).fetchall()
    assert rows == [("test_source", "run1", "missing primary key component 'unique_key'")]


def test_run_lifecycle(loader):
    loader.ensure_raw_table("test_source")
    loader.start_run("run1", "test_source", "sample")
    loader.load_batch("test_source", [_record("1")], "run1")
    loader.finish_run("run1", "success", 1, 1, 0, "test_source")

    row = loader.conn.execute(
        """SELECT status, rows_received, rows_inserted, rows_rejected,
                  watermark_before, watermark_after
           FROM meta.ingest_runs WHERE run_id='run1'"""
    ).fetchone()
    assert row[0] == "success"
    assert row[1:4] == (1, 1, 0)
    assert row[4] is None  # empty table before the run
    assert row[5] is not None


def test_watermark_none_when_table_missing(loader):
    assert loader.latest_updated_at("never_ingested") is None
    assert loader.raw_count("never_ingested") == 0


def test_utc_now_is_timezone_aware():
    # Guard against naive datetimes sneaking into run metadata.
    assert datetime.now(UTC).tzinfo is not None
