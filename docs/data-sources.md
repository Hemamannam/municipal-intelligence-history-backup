# Data sources — discovery notes

Verified live against the Socrata APIs on 2026-08-09.

## Selection

| Role | Dataset | ID | Why chosen |
|---|---|---|---|
| Complaints | NYC 311 Service Requests (2010–present) | `erm2-nwe9` | Clean PK (`unique_key`), incident address + borough + zip + lat/lon, `created_date` for windowing |
| Permits | DOB Permit Issuance | `ipu4-2q9a` | Owner **and** permittee names (owner ER fuel), block+lot → BBL, deliberately messy (see below) |
| Businesses | DCWP Legally Operating Businesses | `w7w3-xahh` | Legal name + DBA trade name (business ER fuel), address parts, license lifecycle dates |

All three are Socrata SODA 2.1 endpoints on `data.cityofnewyork.us`, which gives us
uniform system fields: `:id` (stable row id → keyset pagination) and `:updated_at`
(uniform incremental watermark that also captures in-place updates such as 311
status changes).

## The shared-identifier nuance (important, and honest)

These datasets *partially* share identifiers: `bbl` appears on some 311 rows,
DCWP rows carry `bin`/`bbl`, and permits carry `bin` + `block`+`lot` (BBL derivable).
Real municipal data is like this — a key exists but its coverage is incomplete,
inconsistently populated, and of uncertain reliability.

Design consequence: entity resolution treats BBL/BIN as a **high-precision
deterministic signal where present** (with coverage measured per source during
profiling), and address/name-based resolution carries the remainder. We will report
what fraction of matches each strategy contributed.

## Known messiness observed at first inspection

**311 (`erm2-nwe9`)**
- `incident_address` free text with abbreviated suffixes; separate `street_name` field
- `bbl`, coordinates, and zip present only on a subset of rows
- Address-less complaint types exist (e.g. intersection- or park-based)

**DOB Permit Issuance (`ipu4-2q9a`)**
- `filing_date` / `issuance_date` / `expiration_date` / `job_start_date` are
  **MM/DD/YYYY text**, while `dobrundate` is an ISO timestamp — two date regimes in one dataset
- Owner name split across `owner_s_first_name` / `owner_s_last_name` /
  `owner_s_business_name` (with literal `"N/A"` values); permittee similarly split
- No single obvious primary key; `permit_si_no` is the leading candidate —
  **must be confirmed by profiling before onboarding**
- Column names contain trailing underscores from source-system exports
  (`house__`, `job__`, `bin__`)

**DCWP Licenses (`w7w3-xahh`)**
- `business_name` vs `dba_trade_name` — same entity, two names
- `address_building` + `address_street_name` parts, plus borough naming that differs
  from 311's (e.g. "Manhattan" vs "MANHATTAN")
- License lifecycle fields (`license_status`, `lic_expir_dd`) suggest slowly-changing
  records → incremental via `:updated_at` matters here

## Dev sampling strategy

Each source config carries an optional `sample_where` (SoQL) bounding the local dev
sample to a recent window, plus a global `MIP_MAX_RECORDS` cap. Scaling up = widen
the window / raise the cap; no code changes.
