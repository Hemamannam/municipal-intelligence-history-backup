# Interview guide

How to talk about this project, from 30 seconds to a deep dive. Every
number quoted here is measured in this repo (er-evaluation.md,
benchmarks.json) — if you re-run with different data, update the numbers.

## 30-second version

> I built a municipal data platform that unifies six NYC datasets — 311
> complaints, DOB permits, business licenses, tax lots, and HPD
> registrations — into canonical properties, owners, and portfolios,
> despite there being no reliable shared key. It's Python + dbt + Airflow
> + DuckDB with a Metabase front end, and the interesting part is the
> entity resolution: reference-anchored matching with blocking, measured
> at 98.7% precision on 20K blind-evaluated pairs, with every match
> explainable down to component scores. It answers questions no single
> dataset can, like "which landlords generate the most complaints per
> unit while pulling repeated renovation permits."

## 2-minute version

Add these beats:

- **The messy-data reality**: the "shared key" (BBL) exists on 91% of
  311 rows, 100% of permits, 62% of licenses — so the design uses it
  deterministically where present and falls back to normalized-address
  fuzzy matching, rather than pretending the data is keyless or clean.
- **Evaluation before tuning**: I blinded the matcher to BBLs it could
  have used and scored it against them — 20K labeled pairs for free.
  Name matching has a hand-audited, committed CSV of labeled pairs.
  Tuning was driven by measured failures (the token_set subset bug, the
  sibling-LLC merges), not vibes.
- **The customer iteration**: after delivery, the "customer" pointed out
  per-building LLCs hide portfolios. The fix wasn't looser matching — it
  was a new evidence source (HPD registrations: shared owner mailing
  addresses), a separate entity layer, and a new mart. Legal entities
  stay precise; portfolios sit on top.
- **Production shape**: nightly Airflow DAG, idempotent everything,
  dead-letter queue, schema-change tripwires, dbt tests gating publish,
  pipeline-health dashboard.

## 5-minute deep dive — suggested walk

1. Data discovery findings that shaped design (permits: no natural key,
   15% duplicate rows, two date regimes; PLUTO decimal BBLs; borough
   spelled four ways).
2. Raw layer contract: append-only versions on `:updated_at`, DLQ,
   run metadata. Show a rerun inserting 0 rows.
3. Address normalization: "123 W. 42nd St Apt 4B" ≡ "123 WEST 42 STREET
   #4B"; property-level vs unit-level both kept; CRF fast-path story
   (2ms → 2µs for simple addresses; 1.35M rows in 34s).
4. ER passes + blocking math: 998K comparisons vs 26.5B naive.
5. The evaluation harness and what it caught. Show the labeled CSV.
6. The LLC portfolio iteration end-to-end.
7. Lineage: pick a property in Metabase, walk `bridge_property_source`
   back to raw records and the runs that ingested them.

## Questions you should expect, with strong answers

**Why fuzzy matching at all — and why so little of it?**
Because the data earns it: BBL covers ~91.5% of property mentions
deterministically. Fuzzy exists for the measured remainder, and it's
deliberately conservative because a false merge (two buildings blended)
poisons every downstream aggregate. The 2,689 ambiguous pairs go to a
review queue, not into the data.

**How did you measure whether entity resolution worked?**
Two ways. Properties: BBL-oracle — hide the key, resolve by address,
score against the hidden key. 20,000 real mentions: 98.7% precision,
72.5% recall, 0.95% FPR, plus a building-level precision figure because
condo lots share addresses. Names: a committed, auditable CSV of labeled
pairs (mostly real pairs from the match evidence), conservative labels:
100% precision / 93.3% recall after rule fixes. I can also tell you what
the eval *caught*: token_set_ratio scoring 1.0 on token subsets —
'ANGEL' vs 'ANGEL CHU' was auto-merging.

**Why not machine learning?**
No honest labels at bootstrap, and the customer needs every ranking
explainable to a non-technical audience — "these matched because street
similarity 0.96, same zip, 12m apart" survives an audit; embeddings
don't. The eval harness is exactly the infrastructure you'd need to
justify graduating to a learned model (Splink/dedupe-style) later — I'd
argue that's the right order.

**What happens when two buildings have similar addresses?**
Blocking only compares candidates sharing (borough, house_number), so
"123 Main St" never meets "125 Main St". Within a block, the weighted
score has to clear 0.90 with zip and geo agreement contributing; the
0.75–0.90 band is quarantined for review. The measured failure mode is
the opposite: corner buildings with two legitimate frontages depress
*recall* (72.5% blinded), which BBL coverage mostly moots — and I can
show the block-cap experiment proving the cap isn't the limiter
(+0.26pp recall for 2x comparisons at cap 2000).

**How do you prevent incorrect entity merges?**
Layers: conservative thresholds (auto 0.95 names / 0.90 property),
digit-token guard (sibling LLCs), person/org block separation, review
queues for the gray band, deterministic evidence rows for every merge,
and dbt tests asserting the invariants (auto matches above threshold;
review pairs never auto-matched). And when a merge is challenged:
`bridge_property_source` walks it back to raw records.

**What happens when a source changes its schema?**
Every source declares `critical_fields`; ingestion checks them against
the first page of every run and fails loudly with the missing list. Less
critical drift lands as NULLs that the normalize-time quality metrics
(stored per run) make visible. Raw is schemaless JSON on purpose — the
payload survives even when the contract breaks.

**Why Airflow?** Because the thing being orchestrated is a nightly
dependency chain with retries, gating, and human-visible history — the
exact shape Airflow is boring and good at, and boring is a feature in
government. The DAG is honest about the single-writer warehouse (an
explicit pool) rather than faking parallelism.

**Why dbt?** Tests-as-code on the modeled layer (28 checks including
custom ER invariants), documented lineage, and warehouse portability —
the models don't change if DuckDB becomes BigQuery.

**Why DuckDB?** Millions of rows on a laptop with zero ops, SQL-first
transforms, and a clean publish step to Postgres for serving. The
single-writer constraint is real and documented; it's the first thing a
production deployment swaps.

**How would this scale to 100 million records?**
See architecture.md §7/§10 — the levers per stage are already listed,
and the honest answer starts with "the marts stay small; raw and ER are
what scale." Partition raw, make normalization incremental on version
ids, shard ER by borough with a geo-grid second block, move the
warehouse. The evaluation harness is the piece that doesn't change —
it's the regression gate for any matcher rewrite.

**How would you deploy this for an actual city?**
Postgres/RDS warehouse, Airflow on managed K8s, read-only Metabase with
SSO groups, secrets in a vault, plus two human loops: a review-queue UI
for the gray-band matches, and a data-steward sign-off on matcher
version bumps (the eval report is the sign-off artifact).

**What was the hardest engineering problem?**
Entity identity that survives reruns. The ugly version: standalone
property IDs derived from row_number() changed across ER runs and
orphaned 1,120 rows in an incremental fact — caught by a dbt
relationships test. The fix (signature-hashed deterministic IDs) sounds
trivial; knowing you need it is the difference between a demo and a
pipeline.

**What customer requirement changed during implementation?**
"Group by landlord" became "landlord names are meaningless, group by the
operation behind the LLCs" — see customer_requests/. The architecture
absorbed it as a new evidence source + a new entity layer in about a
day's work, *because* source onboarding and ER layering were built to be
cheap. That's the FDE muscle the project is designed to demonstrate.
