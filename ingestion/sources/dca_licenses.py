"""NYC DCWP (formerly DCA) Legally Operating Businesses.

https://data.cityofnewyork.us/Business/Legally-Operating-Businesses/w7w3-xahh

Active/renewable business licenses with business_name plus dba_trade_name
(name-variant fuel for business entity resolution), address parts, and
sometimes BIN/BBL.

PK verified server-side 2026-08: 69,884 distinct license_nbr across 69,885
rows — one collision in the source (the versioned raw layer stores both;
staging keeps the latest). Licenses are a slowly-changing population, so no
date sample window — the dataset is small enough to ingest whole.
"""

from ingestion.sources.base import SourceConfig

DCA_LICENSES = SourceConfig(
    key="dca_licenses",
    name="NYC DCWP Legally Operating Businesses",
    dataset_id="w7w3-xahh",
    pk_fields=("license_nbr",),
    sample_where=None,
    description=(
        "Business licenses with legal name, DBA/trade name, license category, "
        "premises address, and sometimes BIN/BBL."
    ),
)
