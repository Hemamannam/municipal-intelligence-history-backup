"""NYC PLUTO (Primary Land Use Tax Lot Output) — enrichment source.

https://data.cityofnewyork.us/City-Government/Primary-Land-Use-Tax-Lot-Output-PLUTO-/64uk-42ks

Why this source exists in the platform: the three operational datasets
contain **no residential unit counts**, which the customer's headline
question ("complaints per residential unit by landlord") requires. PLUTO is
the city's canonical tax-lot table: one row per lot with ``unitsres``,
``ownername``, year built, building class, and coordinates.

Verified quirks (2026-08):
- ``bbl`` arrives as a decimal string ("2054800111.00000000") — normalized
  in staging to the canonical 10-digit form
- ``borough`` uses codes (BX/BK/MN/QN/SI), unlike every other source
- ``ownername`` is "LAST, FIRST" for individuals — name-normalization fuel

~857K rows, refreshed roughly annually; column projection keeps the fetch
manageable (~90 columns exist, we use 11).
"""

from ingestion.sources.base import SourceConfig

PLUTO = SourceConfig(
    key="pluto",
    name="NYC PLUTO tax lots",
    dataset_id="64uk-42ks",
    pk_fields=("bbl",),
    sample_where=None,
    select_fields=(
        "bbl",
        "address",
        "borough",
        "zipcode",
        "unitsres",
        "unitstotal",
        "ownername",
        "yearbuilt",
        "bldgclass",
        "latitude",
        "longitude",
    ),
    description=(
        "Canonical tax-lot reference: residential/total units, owner of "
        "record, year built, building class per BBL. Enrichment backbone "
        "for canonical properties."
    ),
)
