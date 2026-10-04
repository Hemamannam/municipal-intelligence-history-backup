# Change request: "landlord names aren't reliable"

## The request (two weeks after the first delivery)

> "We realized landlord names aren't reliable because buildings are often
> owned through separate LLCs. PARKASH 2165 LLC and PARKASH 2454 LLC are
> obviously the same operation. Can we group properties using mailing
> address and management-company information?"

## Why the existing architecture couldn't answer it

Our own entity resolution had *correctly* kept those LLCs separate — they
are distinct legal entities, and our labeled evaluation explicitly marks
sibling per-building LLCs as non-matches (merging them by name similarity
would also merge unrelated "SUNSET 63 LLC"/"SUNSET REALTY ASSOCIATES LLC").
The customer wasn't asking for looser name matching; they were asking for
a **different entity**: the operating portfolio behind the LLCs. That
needs evidence no amount of fuzzy matching can extract from a name.

## What we did instead

NYC already collects the needed evidence: **HPD Multiple Dwelling
Registrations** list, for every registered building, its corporate owner,
officers, and their **business mailing addresses**. Two buildings whose
registrations share an owner mailing address (or corporate-owner name)
are managed together — the city's own paperwork says so.

Architecture change (clean, because source onboarding was built cheap):

1. Two new source configs (`hpd_registrations`, `hpd_contacts`) — reuse
   the entire ingestion framework (keyset pagination, versioned raw, DLQ).
2. One new normalization builder (BBL assembly + mailing-address
   normalization through the same address normalizer).
3. A new ER stage (`entity_resolution/portfolio.py`): union-find over
   properties, edges = shared corporate-owner name OR shared owner/officer
   mailing address. Registered agents excluded (their office "manages"
   thousands of unrelated buildings); mailing keys touching >200
   registrations are skipped and counted as service companies.
4. A new mart (`mart_portfolio_performance`) at group grain; the original
   owner-level mart is kept — the department wanted both views.

`dim_owner` is untouched: legal entities remain legal entities. The
portfolio group is a separate, evidence-backed layer on top — which is
exactly what makes the ranked list defensible when a landlord pushes back.

## Results (measured on the local build)

See solution.md for the numbers generated from this repository's data,
including group counts and the largest portfolios found.
