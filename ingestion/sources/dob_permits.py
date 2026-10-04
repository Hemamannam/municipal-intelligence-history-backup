"""NYC DOB NOW: Build — Approved Permits.

https://data.cityofnewyork.us/Housing-Development/DOB-NOW-Build-Approved-Permits/rbx6-tga4

Chosen over the classic DOB Permit Issuance dataset (ipu4-2q9a) after live
verification (2026-08): BIS wound down as DOB NOW took over, leaving only
~15K permits issued 2025-2026 in the classic dataset vs ~174K here. This
dataset has proper timestamp columns, owner_business_name + owner_name,
applicant (contractor) names, BIN/BBL, and estimated job costs.

Verified messiness (kept on purpose — it drives the DLQ and staging-dedup
story):
- No unique natural key: ~15% of rows are duplicates even on
  (job_filing_number, work_permit, sequence_number, issued_date) —
  identity falls back to Socrata ``:id``; staging dedupes and measures.
- Garbage rows exist (a record with job_filing_number "Permit is no").
- ``dobrundate``-style refresh applies here too: server-side sampling must
  filter on ``issued_date``, not update timestamps.
"""

from ingestion.sources.base import SourceConfig

DOB_PERMITS = SourceConfig(
    key="dob_permits",
    name="NYC DOB NOW Approved Permits",
    dataset_id="rbx6-tga4",
    pk_fields=(),  # no reliable natural key — see module docstring
    sample_where="issued_date >= '2025-08-01T00:00:00'",
    description=(
        "Approved construction permits from DOB NOW with owner and applicant "
        "names, house/street/borough/zip, BIN/BBL, work type, and estimated "
        "job costs — key fuel for property and owner entity resolution."
    ),
)
