"""End-to-end pipeline test against a fake API and a real (temp) DuckDB."""

import pytest

from ingestion.config import Settings
from ingestion.loaders.duckdb_loader import DuckDBLoader
from ingestion.pipeline import ingest_source


class FakeClient:
    """Stands in for SocrataClient; yields canned pages."""

    def __init__(self, pages):
        self.pages = pages
        self.requested_wheres: list = []

    def iter_pages(self, dataset_id, where=None, page_size=None, max_records=None, select_fields=None):
        self.requested_wheres.append(where)
        yielded = 0
        for page in self.pages:
            if max_records is not None:
                page = page[: max_records - yielded]
            if not page:
                return
            yielded += len(page)
            yield page


def _row(i: int, updated="2026-06-01T00:00:00.000Z", **overrides):
    row = {
        ":id": f"row-{i:06d}",
        ":updated_at": updated,
        "unique_key": str(i),
        "complaint_type": "NOISE",
    }
    row.update(overrides)
    return row


@pytest.fixture
def settings(tmp_path):
    return Settings(
        mip_duckdb_path=tmp_path / "wh.duckdb",
        mip_max_records=100,
        mip_page_size=10,
        _env_file=None,
    )


def test_pipeline_end_to_end(settings, monkeypatch):
    monkeypatch.setattr("ingestion.pipeline.get_source", lambda key: _test_source())
    good = [_row(i) for i in range(5)]
    bad = [_row(99, unique_key="")]  # missing PK -> dead letter
    client = FakeClient([good[:3], good[3:] + bad])

    result = ingest_source("test_source", settings=settings, client=client)

    assert result.status == "success"
    assert result.rows_received == 6
    assert result.rows_inserted == 5
    assert result.rows_rejected == 1

    loader = DuckDBLoader(settings.mip_duckdb_path)
    try:
        assert loader.raw_count("test_source") == 5
        run = loader.conn.execute(
            "SELECT status, rows_received, rows_inserted, rows_rejected FROM meta.ingest_runs"
        ).fetchone()
        assert run == ("success", 6, 5, 1)
        rejected = loader.conn.execute("SELECT count(*) FROM meta.rejected_records").fetchone()[0]
        assert rejected == 1
    finally:
        loader.close()


def test_pipeline_rerun_inserts_nothing(settings, monkeypatch):
    monkeypatch.setattr("ingestion.pipeline.get_source", lambda key: _test_source())
    pages = [[_row(i) for i in range(4)]]

    first = ingest_source("test_source", settings=settings, client=FakeClient(pages))
    second = ingest_source("test_source", settings=settings, client=FakeClient(pages))

    assert first.rows_inserted == 4
    assert second.rows_inserted == 0
    assert second.rows_received == 4


def test_incremental_adds_updated_at_clause(settings, monkeypatch):
    monkeypatch.setattr("ingestion.pipeline.get_source", lambda key: _test_source())
    ingest_source(
        "test_source", settings=settings, client=FakeClient([[_row(1)]])
    )
    client = FakeClient([[]])
    ingest_source("test_source", settings=settings, client=client, incremental=True)

    assert len(client.requested_wheres) == 1
    assert ":updated_at >" in client.requested_wheres[0]


def _test_source():
    from ingestion.sources.base import SourceConfig

    return SourceConfig(
        key="test_source",
        name="Test Source",
        dataset_id="abcd-1234",
        pk_fields=("unique_key",),
    )
