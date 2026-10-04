# Solution: inspection prioritization — what was built, why, and results

All numbers measured on this repository's build (3.90M raw rows across
six sources; regenerate via `make evaluate` / `scripts/benchmark.py`).

## What was built

1. **Canonical entities with lineage.** 478,774 property mentions
   resolved to canonical properties at a 93.6% match rate — 91.5% via
   deterministic BBL, the rest via exact/fuzzy address matching with
   component-score evidence. 2,689 ambiguous pairs sit in a review queue
   rather than in the data. Blinded evaluation on 20,000 real pairs:
   **98.7% precision**, 72.5% recall, 0.95% false-positive rate.
2. **The denominator the question needed.** No operational dataset has
   residential unit counts, so PLUTO was onboarded as the property spine
   (`unitsres` per BBL) — "complaints per unit" became computable.
3. **`mart_landlord_performance`** — owner rollups plus the 0–100
   operational risk score (40% complaints/unit, 20% emergency share,
   15% open share, 15% trend, 10% permit churn), percent-ranked within
   a peer pool of **11,000+ owners** (≥10 units, ≥3 complaints/12m).
   Documented as a *prioritization* score, not a wrongdoing claim.
4. **Dashboards** (Metabase, API-provisioned): City Operations Overview
   (ranked landlords, priority properties with borough filter, match
   confidence) and Pipeline Health (runs, dead letters, review queues,
   freshness).

## Why these choices

- Percentile blend over a learned model: explainable to a board, no
  honest training labels exist, and the evaluation harness is in place
  to justify graduating to ML later.
- Peer-pool gating (≥10 units, ≥3 complaints): kills small-denominator
  noise (a 2-unit building with 3 complaints would otherwise top the
  list).
- Review queues over forced decisions: an inspector knocking on the
  wrong door costs more than a deferred match.

## The change request, delivered

"LLC names hide portfolios" → HPD registrations onboarded (927K rows in
two sources), portfolio grouping added as a separate evidence-backed
entity layer:

- 101,070 properties carry HPD registrations; **7,752 multi-property
  portfolio groups** were formed from 47,338 evidence edges (shared
  corporate owner, or shared *owner* mailing address — registered agents
  excluded).
- The first run exposed a transitive-closure failure: officer/manager
  office addresses chained a **5,931-property mega-group spanning 3,782
  owner names**. Fix: mailing edges restricted to owner-type contacts
  with a tighter fanout cap. Largest group after the fix: **266
  properties** — plausible for NYC's largest operators, and every group
  is walkable back to its evidence rows.
- Result mart: `mart_portfolio_performance`. Top portfolios by 12-month
  complaints now surface per-building LLC families as single operations
  (e.g. a 187-building group at ~7,155 units, 0.95 complaints/unit)
  that the owner-level view scattered across dozens of rows.

## Limitations (told to the customer, not buried)

- 311 volume is a reporting-rate proxy, not an inspection finding;
  neighborhood reporting bias is real. Percentile ranking softens but
  does not remove it.
- The complaint sample covers ~180 days contiguously; trend components
  use 90-day windows and are sensitive to seasonality until a
  multi-year backfill lands.
- Unit counts lag new construction (PLUTO is annual).
- City agencies (NYCHA, Parks) legitimately top raw rankings; the
  dashboard documents the filter rather than silently excluding them.
