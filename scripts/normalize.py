#!/usr/bin/env python3
"""CLI: build clean.* tables from raw payloads.

Examples:
    python scripts/normalize.py                 # all sources with raw data
    python scripts/normalize.py --only permits complaints
"""

import argparse
import sys

from ingestion.config import get_settings
from ingestion.logging_setup import configure_logging
from normalization.runner import BUILDERS, run_all


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", choices=sorted(BUILDERS), default=None)
    args = parser.parse_args()

    configure_logging()
    results = run_all(get_settings().mip_duckdb_path, only=args.only)
    for r in results:
        extras = {k: v for k, v in r.items() if k not in ("table", "rows")}
        print(f"{r['table']}: {r['rows']:,} rows  {extras}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
