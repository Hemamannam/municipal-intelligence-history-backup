"""SocrataClient: keyset pagination, max_records bounding, retry behavior."""

import pytest

from ingestion.socrata import SocrataClient, SocrataError


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, headers=None, text=""):
        self.status_code = status_code
        self._json = json_data if json_data is not None else []
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._json


class FakeSession:
    """Returns queued responses; records the params of every request."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []
        self.headers: dict = {}

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params})
        return self.responses.pop(0)


def _rows(start, count):
    return [{":id": f"row-{i:06d}", ":updated_at": "2026-01-01T00:00:00.000Z", "unique_key": str(i)}
            for i in range(start, start + count)]


def make_client(session, **kwargs):
    defaults = dict(domain="example.com", backoff_base=0.0, backoff_cap=0.0, sleep=lambda s: None)
    defaults.update(kwargs)
    return SocrataClient(session=session, **defaults)


def test_keyset_pagination_advances_and_terminates():
    session = FakeSession([
        FakeResponse(json_data=_rows(0, 3)),
        FakeResponse(json_data=_rows(3, 2)),  # short page -> stop
    ])
    client = make_client(session)
    pages = list(client.iter_pages("abcd-1234", page_size=3))

    assert [len(p) for p in pages] == [3, 2]
    # First call has no keyset clause; second continues after the last id.
    assert "$where" not in session.calls[0]["params"]
    assert ":id > 'row-000002'" in session.calls[1]["params"]["$where"]
    assert session.calls[0]["params"]["$order"] == ":id"


def test_where_clause_combined_with_keyset():
    session = FakeSession([
        FakeResponse(json_data=_rows(0, 2)),
        FakeResponse(json_data=[]),
    ])
    client = make_client(session)
    list(client.iter_pages("abcd-1234", where="created_date >= '2026-01-01'", page_size=2))

    assert session.calls[0]["params"]["$where"] == "(created_date >= '2026-01-01')"
    second = session.calls[1]["params"]["$where"]
    assert "created_date" in second and ":id > 'row-000001'" in second


def test_max_records_caps_fetch():
    session = FakeSession([
        FakeResponse(json_data=_rows(0, 3)),
        FakeResponse(json_data=_rows(3, 2)),
    ])
    client = make_client(session)
    pages = list(client.iter_pages("abcd-1234", page_size=3, max_records=5))

    total = sum(len(p) for p in pages)
    assert total == 5
    # Final page requests only the remaining 2 records.
    assert session.calls[1]["params"]["$limit"] == 2


def test_retries_on_429_then_succeeds():
    sleeps = []
    session = FakeSession([
        FakeResponse(status_code=429, headers={"Retry-After": "0"}),
        FakeResponse(status_code=503),
        FakeResponse(json_data=_rows(0, 1)),
    ])
    client = make_client(session, sleep=sleeps.append)
    pages = list(client.iter_pages("abcd-1234", page_size=5))

    assert sum(len(p) for p in pages) == 1
    assert len(sleeps) == 2  # slept before each retry


def test_non_retryable_status_raises_immediately():
    session = FakeSession([FakeResponse(status_code=400, text="bad soql")])
    client = make_client(session)
    with pytest.raises(SocrataError, match="HTTP 400"):
        list(client.iter_pages("abcd-1234"))
    assert len(session.calls) == 1


def test_retries_exhausted_raises():
    session = FakeSession([FakeResponse(status_code=503)] * 3)
    client = make_client(session, max_retries=2)
    with pytest.raises(SocrataError, match="retries exhausted"):
        list(client.iter_pages("abcd-1234"))
    assert len(session.calls) == 3
