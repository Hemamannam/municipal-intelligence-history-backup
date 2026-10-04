import pytest

from ingestion.sources.base import SourceConfig


@pytest.fixture
def source() -> SourceConfig:
    return SourceConfig(
        key="test_source",
        name="Test Source",
        dataset_id="abcd-1234",
        pk_fields=("unique_key",),
    )


@pytest.fixture
def composite_source() -> SourceConfig:
    return SourceConfig(
        key="test_composite",
        name="Composite PK Source",
        dataset_id="efgh-5678",
        pk_fields=("job", "seq"),
    )
