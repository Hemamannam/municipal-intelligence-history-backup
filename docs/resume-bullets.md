# Resume bullets (all figures measured in this repo)

Primary three (Forward Deployed Engineer framing):

- Built a Python/dbt/Airflow municipal-data platform unifying 6 NYC open
  datasets (3.9M records — 311 complaints, DOB permits, business
  licenses, PLUTO tax lots, HPD registrations) into canonical property,
  owner, and portfolio entities despite the absence of a reliable shared
  identifier, with record-level lineage from every dashboard number back
  to its source rows.

- Engineered address and owner entity resolution combining deterministic
  keys, blocking, and fuzzy scoring — 478K property mentions resolved at
  98.7% precision (blind-evaluated on 20,000 labeled pairs) while
  blocking cut candidate comparisons 99.996% (998K vs 26.5B naive);
  built the evaluation harness that caught and fixed real false-merge
  bugs before they reached analysts.

- Automated nightly ingestion, normalization, dbt transformations
  (17 models, 28 data-quality tests), and Metabase analytics behind a
  test-gated publish, enabling cross-dataset products such as
  complaints-per-unit landlord rankings and an LLC-portfolio grouping
  requested mid-project by the customer — delivered by onboarding a new
  evidence source (HPD) in under a day on the existing framework.

Shorter variants (pick per resume space):

- Unified 6 NYC municipal datasets (3.9M records) into canonical
  properties/owners via blocking + deterministic + fuzzy entity
  resolution: 98.7% precision on 20K blind-evaluated pairs, 99.996%
  comparison reduction, full match-evidence lineage.

- Shipped an end-to-end data platform (Python, dbt, Airflow, DuckDB,
  Postgres, Metabase, Docker) with measured evaluation, dead-letter
  handling, schema-change tripwires, and a documented 0–100 operational
  risk score over an 11K-owner peer pool.

Notes for honest use:
- "3.9M records" = raw rows ingested locally (3,897,961; 3,880,769
  distinct records). If asked: 311 is a 180-day contiguous sample plus a
  January block; the architecture supports full backfill.
- Name-matcher metrics (100% precision / 93.3% recall) are on a 45-pair
  audited set — cite the property numbers (n=20,000) as the headline.
- The risk score is an operational prioritization signal; never describe
  it as detecting wrongdoing.
