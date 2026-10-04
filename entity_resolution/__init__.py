"""Entity resolution: normalization, blocking, matching, evaluation.

The pipeline turns messy per-source records into canonical properties,
owners, and businesses:

    normalize (this package's *_normalizer modules, applied by
    normalization.runner) → candidate_generation (blocking) → matcher
    (deterministic + fuzzy scoring with explainable evidence) → clusters →
    canonical entities (materialized by dbt) → evaluator (measured metrics).
"""
