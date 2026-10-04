#!/usr/bin/env python3
"""CLI: run entity resolution (properties, then owners, then businesses).

Example:
    python scripts/resolve_entities.py
    python scripts/resolve_entities.py --only properties
"""

import argparse
import sys

import duckdb

from entity_resolution.config import ERConfig
from entity_resolution.matcher import match_properties
from entity_resolution.name_matcher import resolve_businesses, resolve_owners
from entity_resolution.portfolio import build_owner_groups
from ingestion.config import get_settings
from ingestion.logging_setup import configure_logging

STEPS = ("properties", "owners", "businesses", "portfolios")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", choices=STEPS, default=None)
    args = parser.parse_args()

    configure_logging()
    cfg = ERConfig()  # validates thresholds/weights at load (fail fast)
    conn = duckdb.connect(str(get_settings().mip_duckdb_path))
    try:
        selected = args.only or STEPS
        if "properties" in selected:
            print("properties:", match_properties(conn, cfg))
        if "owners" in selected:
            print("owners:", resolve_owners(conn, cfg))
        if "businesses" in selected:
            print("businesses:", resolve_businesses(conn, cfg))
        if "portfolios" in selected:
            try:
                print("portfolios:", build_owner_groups(conn))
            except Exception as exc:  # HPD sources are optional locally
                print(f"portfolios: skipped ({str(exc)[:80]})")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
