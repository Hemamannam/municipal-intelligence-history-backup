"""Runtime configuration, loaded from environment / .env.

All tunables live here rather than being hard-coded at call sites, so the
same code path serves a 50K-row laptop sample and a multi-million-row run.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings (see .env.example for documentation)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    socrata_app_token: str | None = None
    socrata_domain: str = "data.cityofnewyork.us"

    mip_duckdb_path: Path = Path("data/warehouse/mip.duckdb")
    mip_max_records: int = 50_000
    mip_page_size: int = 10_000

    request_timeout_seconds: float = 60.0
    max_retries: int = 5
    backoff_base_seconds: float = 2.0
    backoff_cap_seconds: float = 60.0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
