"""Entity-resolution configuration.

All weights/thresholds live here (env-overridable, ``ER_`` prefix), and the
model VALIDATES itself: an AUTO threshold at or below REVIEW would silently
auto-accept everything in the review band — a real misconfiguration class
(Phase 16), so it fails fast at load time instead.

The default weights were tuned against the BBL-oracle evaluation
(entity_resolution/evaluator.py); see docs for the measured tradeoff.
"""

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ERConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ER_", env_file=".env", extra="ignore")

    # -- property matching (address-based, against the PLUTO-seeded reference)
    auto_match_threshold: float = 0.90
    review_threshold: float = 0.75

    weight_street: float = 0.55
    weight_zip: float = 0.15
    weight_geo: float = 0.15
    weight_suffix: float = 0.15

    geo_full_credit_m: float = 30.0     # distance considered "same building"
    geo_zero_credit_m: float = 250.0    # distance considered unrelated

    # -- name (owner/business) matching
    # 0.95 (up from an initial 0.92) after labeled-pair evaluation showed
    # 0.92 admits false merges like sibling HDFC entities scoring 0.93.
    name_auto_threshold: float = 0.95
    name_review_threshold: float = 0.85

    # -- blocking safety valves
    max_block_size: int = 200           # skip+log pathological blocks
    max_candidates_per_mention: int = 25

    @model_validator(mode="after")
    def _sane(self) -> "ERConfig":
        if self.auto_match_threshold <= self.review_threshold:
            raise ValueError(
                f"AUTO_MATCH_THRESHOLD ({self.auto_match_threshold}) must exceed "
                f"REVIEW_THRESHOLD ({self.review_threshold}) — otherwise the review "
                "band silently auto-matches."
            )
        if self.name_auto_threshold <= self.name_review_threshold:
            raise ValueError("ER_NAME_AUTO_THRESHOLD must exceed ER_NAME_REVIEW_THRESHOLD")
        total = self.weight_street + self.weight_zip + self.weight_geo + self.weight_suffix
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"property score weights must sum to 1.0 (got {total})")
        return self
