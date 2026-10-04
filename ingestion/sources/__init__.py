"""Source registry."""

from ingestion.sources.base import SourceConfig
from ingestion.sources.dca_licenses import DCA_LICENSES
from ingestion.sources.dob_permits import DOB_PERMITS
from ingestion.sources.hpd_registrations import HPD_CONTACTS, HPD_REGISTRATIONS
from ingestion.sources.nyc_311 import NYC_311
from ingestion.sources.pluto import PLUTO

SOURCES: dict[str, SourceConfig] = {
    cfg.key: cfg
    for cfg in (NYC_311, DOB_PERMITS, DCA_LICENSES, PLUTO, HPD_REGISTRATIONS, HPD_CONTACTS)
}


def get_source(key: str) -> SourceConfig:
    try:
        return SOURCES[key]
    except KeyError:
        raise KeyError(f"unknown source '{key}'; available: {sorted(SOURCES)}") from None
