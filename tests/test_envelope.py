"""Raw-record envelope validation."""

import pytest

from ingestion.schemas.envelope import RecordRejected, to_raw_record


def test_happy_path(source):
    row = {
        ":id": "row-abc",
        ":updated_at": "2026-06-01T12:30:00.000Z",
        "unique_key": "12345",
        "complaint_type": "HEAT/HOT WATER",
    }
    record = to_raw_record(row, source)
    assert record.source_record_id == "12345"
    assert record.socrata_row_id == "row-abc"
    assert record.socrata_updated_at is not None
    assert record.socrata_updated_at.year == 2026
    # System fields are stripped from the preserved payload.
    assert ":id" not in record.payload
    assert record.payload["complaint_type"] == "HEAT/HOT WATER"


def test_missing_pk_rejected(source):
    with pytest.raises(RecordRejected, match="unique_key"):
        to_raw_record({":id": "row-abc", "unique_key": "  "}, source)


def test_composite_pk_joined(composite_source):
    record = to_raw_record({"job": "340733647", "seq": "01"}, composite_source)
    assert record.source_record_id == "340733647|01"


def test_composite_pk_partial_rejected(composite_source):
    with pytest.raises(RecordRejected, match="seq"):
        to_raw_record({"job": "340733647"}, composite_source)


def test_unparseable_updated_at_rejected(source):
    with pytest.raises(RecordRejected, match="unparseable"):
        to_raw_record({"unique_key": "1", ":updated_at": "not-a-date"}, source)


def test_missing_updated_at_allowed(source):
    record = to_raw_record({"unique_key": "1"}, source)
    assert record.socrata_updated_at is None


def test_no_natural_key_falls_back_to_row_id():
    from ingestion.sources.base import SourceConfig

    cfg = SourceConfig(key="k", name="n", dataset_id="d", pk_fields=())
    record = to_raw_record({":id": "row-xyz", "field": "v"}, cfg)
    assert record.source_record_id == "row-xyz"

    with pytest.raises(RecordRejected, match=":id"):
        to_raw_record({"field": "v"}, cfg)
