# Benchmarks

All numbers below were **measured on this repository's local build**
(Apple-silicon laptop, DuckDB warehouse, unauthenticated Socrata API).
Raw stage timings live in [benchmarks.json](benchmarks.json) (appended by
`scripts/benchmark.py`); ingest figures come from `meta.ingest_runs`.
Per the project rule, only dataset sizes actually run are reported —
nothing is extrapolated.

## Dataset sizes measured

Two scales were exercised end-to-end during development:

| build | raw rows | 311 | permits | licenses | PLUTO | HPD |
|---|---:|---:|---:|---:|---:|---:|
| mid build | ~1.35M | 252K | 174K | 70K | 859K | — |
| full build | **3.90M** | 1.87M | 174K | 70K | 859K | 927K |

## Ingestion (live API, largest single pull per source)

| source | rows pulled | seconds | rows/s |
|---|---:|---:|---:|
| NYC 311 (44 cols) | 1,600,000 | 1,178 | 1,359 |
| PLUTO (11 projected cols) | 858,602 | 137 | 6,252 |
| HPD contacts (13 projected cols) | 782,024 | 82 | 9,574 |
| HPD registrations | 203,236 | 36 | 5,632 |
| DOB NOW permits | 173,679 | 49 | 3,555 |
| DCWP licenses | 69,885 | 7 | 9,512 |

Throughput is API-bound and column-width-bound: PLUTO's ~90 columns were
projected down to 11, turning an estimated ~40-minute pull into 2.3
minutes. Rates vary with API load; an app token raises rate limits.

## Pipeline stages (full build, 3.9M raw rows)

| stage | seconds |
|---|---:|
| Normalization (all 6 sources, full rebuild) | 185.6 |
| ER: property resolution (478,774 mentions) | 12.1 |
| ER: owner clustering (163K distinct names) | 16.3 |
| ER: business clustering (57K names) | 4.1 |
| ER: portfolio grouping (101K HPD-registered properties) | 3.7 |
| dbt run (17 models, full refresh) | 4.5 |
| dbt test (28 tests) | 1.8 |
| **Total transform pipeline** | **228.1** |

At the mid build (1.35M rows) normalization measured 33.8s and property
ER 12.4s — normalization scales roughly linearly with row count (the
per-row Python cost dominates); ER cost tracks *mention* count, which
grows sublinearly because repeated addresses collapse into one mention.

## Why blocking matters (measured, not theoretical)

Property ER at full scale compared **998,330** candidate pairs. The naive
cross product (478,774 mentions × 858,602 reference lots — every mention
against every lot) is **26,505,902,342** comparisons. Blocking on
(borough, house_number) removed **99.9962%** of the work. At ~1µs per
scored pair, naive would take ~7 hours; blocked takes ~1 second of
scoring inside the 12.1s stage. Oversized blocks are capped (200
candidates) and counted: 3,474 skips at full scale, and a measured
cap-raise experiment (200→2000) bought only +0.26pp recall for ~2x
comparisons — documented in docs/er-evaluation.md.

## Known bottleneck & next optimization

Normalization (185.6s) is the slowest transform stage: per-row Python
over 3.9M payloads. The measured fast path (regex short-circuit before
the usaddress CRF) already cut it ~50x vs CRF-everything; the next lever
is incremental normalization (only re-normalize raw versions newer than
the last run), which the versioned raw layer already supports.
