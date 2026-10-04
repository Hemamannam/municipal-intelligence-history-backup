#!/usr/bin/env python3
"""CLI: ingest one source into the local warehouse.

Examples:
    python scripts/ingest.py --source nyc_311
    python scripts/ingest.py --source nyc_311 --max-records 5000
    python scripts/ingest.py --source nyc_311 --incremental
"""

import argparse
import sys

from ingestion.logging_setup import configure_logging
from ingestion.pipeline import ingest_source
from ingestion.sources import SOURCES


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, choices=sorted(SOURCES))
    parser.add_argument("--max-records", type=int, default=None,
                        help="Override MIP_MAX_RECORDS for this run.")
    parser.add_argument("--incremental", action="store_true",
                        help="Only fetch records updated since the stored watermark.")
    args = parser.parse_args()

    configure_logging()
    result = ingest_source(
        args.source, max_records=args.max_records, incremental=args.incremental
    )
    print(
        f"\n[{result.status}] run={result.run_id} source={result.source} mode={result.mode}\n"
        f"  received={result.rows_received:,} inserted={result.rows_inserted:,} "
        f"rejected={result.rows_rejected:,} in {result.duration_seconds:.1f}s\n"
        f"  watermark={result.watermark_after}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
