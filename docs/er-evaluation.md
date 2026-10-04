# Entity-resolution evaluation

Generated 2026-08-10T17:33:40+00:00 by `scripts/evaluate_er.py` — all numbers measured on this
repo's local warehouse; regenerate after any matcher change.

## 1. Property matching — BBL-oracle evaluation

Mentions carrying a PLUTO-known BBL have ground truth. The matcher is
**blinded** (BBL stripped) and must resolve them by address alone; the
prediction is scored against the hidden BBL. *Strict* = exact tax lot;
*building* = same borough + street address (condo lots share buildings).

- Evaluation sample: **20,000** mentions (requested 20,000; 0 excluded lacking any address)
- Auto-match precision (strict lot): **98.7%**
- Auto-match recall (strict lot): **72.5%**
- False positive rate: **0.95%**
- False negative rate: **26.58%**

| method | n | strict precision | building precision |
|---|---:|---:|---:|
| address_exact | 14,457 | 99.1% | 99.3% |
| fuzzy_address | 226 | 71.2% | 71.2% |
| review | 681 | 17.3% | 17.3% |
| unmatched (false negatives) | 4,636 | — | — |

Blocking during evaluation: 238,201 comparisons vs 17,172,040,000 naive (99.9986% reduction).

## 2. Name matching — audited labeled pairs

Pairs in `entity_resolution/eval/labeled_name_pairs.csv` are drawn mostly
from real match evidence / review queues and labeled conservatively
(ambiguous → nonmatch; false splits are recoverable, false merges are not).

- Labeled pairs: **45**
- Thresholds: auto ≥ 0.95, review ≥ 0.85

| scorer | precision | recall | F1 | FPR | in review band |
|---|---:|---:|---:|---:|---:|
| current (sort/blend) | 100.0% | 93.3% | 96.5% | 0.0% | 16 |
| token_set_ratio only (baseline) | 48.1% | 86.7% | 61.9% | 46.7% | 16 |

The baseline row is why the scorer changed: pure token_set_ratio scores
1.0 for token-subset pairs ('ANGEL' vs 'ANGEL CHU'), silently merging
distinct people. Persons now use token_sort only; orgs blend 50/50.

### Current-scorer disagreements with labels

- FN: BROOKFIELD PROPERTIES OP BY CBRE ~ BROOKFIELD PROPERTIES OPERATED BY CBRE (0.93)

## Caveats

- The BBL oracle covers mentions that *have* BBLs; addresses on BBL-less
  records may be systematically messier. Treat the precision figure as an
  upper-bound estimate for that subpopulation.
- Name labels are conservative; some 'nonmatch' pairs may be true matches
  (recall is understated rather than precision overstated).
