# Architecture

All figures in this document were measured on this repository's local
build (see docs/benchmarks.json and docs/er-evaluation.md for the
regenerable versions). Nothing is estimated.

## 1. System overview

```
 NYC Open Data (Socrata SODA 2.1)
 311 · DOB NOW permits · DCWP licenses · PLUTO · HPD registrations+contacts
        │  keyset pagination (:id) · retries+backoff · column projection
        ▼
 raw.* (DuckDB)          append-only, versioned by :updated_at
 meta.ingest_runs        every run metered; meta.rejected_records = DLQ
        ▼
 clean.* (Python)        usaddress + rule normalizers; typed; flagged, not dropped
        ▼
 er.* (Python)           4-pass property resolution · name clustering ·
                         portfolio grouping · review queues · evidence
        ▼
 staging/intermediate/marts (dbt)   dims, facts, risk marts; 28+ data tests
        ▼
 Postgres (serving) ──> Metabase (2 dashboards, API-provisioned)

 Orchestration: Airflow (nightly DAG, retries, test-gated publish)
```

The warehouse is DuckDB; Postgres exists solely as the serving layer for
Metabase. Every layer is rebuildable from the layer below it; raw is the
only stateful truth.

## 2. Entity-resolution architecture

**Reference-anchored, not pairwise-symmetric.** PLUTO (one row per tax
lot, unique BBL) seeds the property universe; operational records resolve
*against* it in four passes: `bbl_exact` → `address_exact` → blocked
fuzzy scoring → deterministic standalone clustering. Measured on the
local build: 91.5% of mentions resolve deterministically by BBL (full build), which is
why the fuzzy path can afford to be conservative.

Why this shape:
- Matching N operational mentions against a canonical reference is
  O(N·k) with blocking, and — more importantly — *evaluable*: hiding the
  BBL from mentions that have one yields tens of thousands of labeled
  pairs for free (docs/er-evaluation.md).
- Fuzzy weights (street 0.55 / zip 0.15 / geo 0.15 / suffix 0.15) and
  thresholds (AUTO 0.90 / REVIEW 0.75) were tuned against that oracle,
  not copied from the spec. The review band is materialized
  (`er.review_queue`), never silently merged or dropped.
- Name matching learned its rules from measured failures: token_set_ratio
  alone auto-merged "ANGEL" with "ANGEL CHU" (subset scoring); sibling
  HDFC entities scored 0.93. Hence: persons use token_sort only, orgs a
  50/50 blend, a digit-token guard (per-building LLC families like
  "PARKASH 2165/2454" must never merge), legal-suffix/initials rules,
  and AUTO raised 0.92 → 0.95. Result on the audited pair set: 100%
  precision, 93.3% recall, the one false negative queued for review.
- Portfolio grouping is a separate entity layer (HPD registration
  evidence: shared corporate owner or owner mailing address), because the
  customer's "landlord" is an *operation*, not a legal entity. dim_owner
  stays legally precise; owner_groups carries the business reality.

## 3. Data-modeling strategy

Kimball-lite: canonical dims (`dim_property`, `dim_owner`,
`dim_business`), one incremental fact (`fct_complaints`), rollup marts
per consumer question, and — deliberately promoted to a first-class
model — `bridge_property_source`, the record-level lineage bridge.
Grain rules: staging = source grain (permits deduped, measured 15.04%
source duplication), intermediate = per-property rollups, marts = the
grain analysts ask questions at (property / owner / portfolio /
neighborhood).

## 4. Incremental processing

- **Ingestion**: watermark on Socrata's `:updated_at` (uniform across
  sources; catches in-place updates such as 311 status changes). The
  watermark derives from the raw data itself — no side state to corrupt.
- **Raw**: append-only versions keyed (record, :updated_at); reruns
  insert zero rows (verified live).
- **dbt**: `fct_complaints` is incremental (delete+insert on
  created_date). Entity IDs are deterministic (BBL-derived, or
  signature-hashed for standalones) precisely so incremental marts
  survive ER regeneration — the non-deterministic id bug was caught by a
  relationships test orphaning 1,120 rows, and is the reason this
  guarantee exists.
- **Normalization/ER**: full rebuilds by design at this scale (186s /
  ~36s measured at 3.9M raw rows). The scale lever is documented, not
  prematurely built.

## 5. Failure handling

- HTTP 429/5xx/connection errors: exponential backoff + jitter,
  Retry-After honored, bounded retries (unit-tested against a fake
  session).
- Schema change: per-source `critical_fields` contract checked on the
  first page of every run; a dropped column fails the run loudly.
- Malformed records: missing PKs and unparseable `:updated_at` land in
  `meta.rejected_records` with reasons — never silently dropped. Bad
  dates/coords/names in payloads are nulled and *flagged* in clean.*,
  keeping the record.
- Threshold misconfiguration: `ERConfig` validates AUTO > REVIEW and
  weight sums at load; the DAG's resolve task fails before touching data.
- dbt test failures gate the publish task in the DAG; the two known
  upstream oddities (permits issued before approval) are `warn` severity
  with a bounded error threshold — visible, tolerated, bounded.

## 6. Data quality

Measured at normalize time and stored with each run (meta.pipeline_runs):
address coverage 96.9% (311), BBL coverage 91.3% (311) / 100% (permits) /
62.4% (licenses), permit duplication 15.04%, plus 28 dbt tests on the
modeled layer. Placeholder identities discovered on real data
("UNAVAILABLE OWNER" aggregating 2,403 properties; 1–2 char name
fragments) are nulled by rule, each rule earned by an observed failure.

## 7. Scalability

Current build: 3.9M raw rows end-to-end on a laptop. The measured
bottlenecks and their levers:

| Stage | Measured | First lever at 10x | At 100M+ rows |
|---|---|---|---|
| Ingestion | 1.4K–9.6K rows/s measured (API- and column-width-bound) | app token; parallel keyset ranges | bulk CSV exports; direct feeds |
| Normalization | 3.9M rows / 186s | already cached+fast-pathed; polars or partitioned rebuild | incremental normalize on changed record ids |
| ER | ~36s all stages; 998K comparisons vs 26.5B naive (99.9962% reduction) | geo-grid second blocking pass | approximate-join engines (Splink-style), partition by borough |
| dbt | seconds | incremental marts | swap DuckDB → warehouse (BigQuery/Snowflake); models port as-is |
| Serving | Postgres copy of marts | — | keep: marts are small regardless of raw scale |

The single-writer DuckDB constraint is documented in the DAG (a pool
serializes writers); moving the warehouse to Postgres removes it without
touching model code.

## 8. Security considerations

All data is public municipal open data — no PII beyond what the city
itself publishes. Secrets (API tokens, DB passwords) live in `.env`
(gitignored) with documented local-only defaults; nothing is hardcoded.
The Metabase admin bootstrap password comes from the environment. For a
real deployment: read-only serving credentials, role-based dashboard
access (Metabase groups), and API tokens per environment.

## 9. Tradeoffs (the honest list)

- **DuckDB vs Postgres warehouse**: chose embedded speed and zero ops for
  local dev; accepted the single-writer constraint (visible in the DAG).
- **Batch vs streaming**: decision cadence is nightly/monthly; streaming
  would add cost with zero decision value.
- **Deterministic-first vs fuzzy-first ER**: NYC data has partial shared
  keys (BBL on 91% of 311 rows) — pretending otherwise would be
  malpractice. Fuzzy handles the measured remainder.
- **Precision over recall in auto-merges**: false merges are
  unrecoverable downstream (a landlord wrongly blamed); false splits sit
  in a review queue. Name AUTO at 0.95 costs recall (93.3% on labeled
  pairs) and we take that trade knowingly. Property fuzzy recall (68.5%
  blinded) is bounded by corner-lot frontages — measured, documented,
  and mostly moot given BBL coverage.
- **Rules vs learned ER model**: no honest training labels exist at
  bootstrap; rules are explainable to a city auditor. The eval harness
  is the on-ramp for a learned model later.
- **Full-rebuild normalize/ER vs incremental**: ~4 minutes buys total
  rerunnability; complexity deferred until data size demands it.

## 10. Future architecture at 100M+ records

Partition raw by source+month; incremental normalization keyed on raw
version ids; ER as partitioned reference-match (borough-sharded, geo-grid
blocking) with persisted match state and event-sourced merges/splits;
warehouse on Postgres/BigQuery with dbt unchanged; Airflow on
Kubernetes executor; the review queue grows a human UI (accept/reject
feeds back into labeled evaluation). The evaluation harness stays the
regression gate for any matcher change — that part is scale-independent.
