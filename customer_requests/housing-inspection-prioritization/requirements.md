# Customer request: inspection prioritization for the Housing Department

## The request (verbatim)

> "The Housing Department wants to identify landlords with unusually high
> complaint levels before conducting inspections. Can the platform give us
> a ranked list we could actually defend if a landlord pushes back?"

## Questions we asked, and the answers that shaped the build

| Question | Answer | Consequence |
|---|---|---|
| High complaint levels *relative to what*? | "A big landlord will always have more complaints." | Normalize by residential units → needed PLUTO (`unitsres`); absolute counts rejected as the primary metric. |
| Do all complaint types count equally? | "A heat outage is not a noise complaint." | Emergency-type weighting (heat/water/gas/electric/elevator/structural). |
| What does "defensible" mean to you? | "If we knock on a door, we must be able to say why." | Full lineage: score → properties → source records → match evidence. Every match keeps method + component scores. |
| Is this an accusation system? | "No — it's triage. Inspectors have limited hours." | Framed and documented as an *operational prioritization score*, explicitly not a wrongdoing claim. |
| How fresh must it be? | "Monthly board meeting; nightly is plenty." | Nightly Airflow schedule; no streaming complexity. |

## Ambiguities we resolved (and how)

- **"Landlord" is not a field in any dataset.** Permits carry an owner of
  record per job; PLUTO carries an owner per lot; neither is complete.
  Decision: canonical owners from both, clustered with conservative
  name matching (false split preferred over false merge), evidence kept.
- **Small-denominator noise.** A 2-unit building with 3 complaints would
  top any per-unit ranking. Decision: scoring pool requires ≥10 units and
  ≥3 complaints in 12m; owners outside the pool are listed but unscored.
- **City agencies dominate raw rankings** (NYCHA, Parks). They are real
  results, not bugs — left in, with a documented filter (`owner_is_org`,
  name patterns) the department can apply per meeting.

## Assumptions (stated, not hidden)

1. 311 complaint volume is an imperfect proxy for building condition
   (reporting rates vary by neighborhood; the score compares within-peer
   percentiles to soften this, but the bias is documented).
2. PLUTO `unitsres` is the best available unit count; it lags new
   construction by up to a year.
3. The 180-day complaint sample window bounds trend analysis; production
   would backfill several years.

## Technical decisions & tradeoffs

- **Score = weighted percentile blend** (40% complaints/unit, 20%
  emergency share, 15% open share, 15% trend, 10% permit churn), not a
  learned model: the department must be able to explain every ranking to
  a non-technical audience, and there is no labeled "bad landlord" ground
  truth to train against honestly.
- **Peer-pool percentiles, not absolute thresholds**: complaint levels
  drift seasonally; percentiles keep the list stable in size.
- **Nightly batch over streaming**: the decision cadence is monthly.

## Delivery plan

1. Canonical owners + unit counts (ER + PLUTO) — done in platform core.
2. `mart_landlord_performance` with documented score — dbt.
3. Ranked dashboard panel + drill-down lineage query — Metabase.
4. This document + solution.md as the paper trail.

## The follow-up that changed the architecture

Delivered rankings immediately surfaced the next problem — see
[llc-portfolio-grouping.md](llc-portfolio-grouping.md): per-building LLCs
fragment portfolios, so the "top landlords" list under-ranked the largest
operations. That request added HPD registrations as a source and a
portfolio-grouping stage to entity resolution.
