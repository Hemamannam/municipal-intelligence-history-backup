#!/usr/bin/env python3
"""Benchmark pipeline stages at the CURRENT local dataset size.

Times normalization, entity resolution, and dbt build against whatever is
in the warehouse right now, and records the dataset size alongside — so
docs/benchmarks.md only ever contains sizes that were actually run
(Phase 18 rule: no extrapolated numbers).

Ingestion throughput is taken from meta.ingest_runs (measured during real
API pulls) rather than re-fetching millions of rows on every benchmark.

Usage:
    python scripts/benchmark.py --label "full-sample"
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from ingestion.config import get_settings

RESULTS = Path("docs/benchmarks.json")


def _time(label: str, fn) -> tuple[float, object]:
    t0 = time.monotonic()
    out = fn()
    dt = time.monotonic() - t0
    print(f"  {label}: {dt:.1f}s")
    return round(dt, 2), out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()

    settings = get_settings()
    db_path = str(settings.mip_duckdb_path)

    conn = duckdb.connect(db_path, read_only=True)
    sizes = {
        t: conn.execute(f"SELECT count(*) FROM raw.{t}").fetchone()[0]
        for t in ("nyc_311", "dob_permits", "dca_licenses", "pluto", "hpd_registrations", "hpd_contacts")
    }
    ingest_rates = conn.execute(
        """
        SELECT source,
               sum(rows_received) AS rows,
               sum(epoch(finished_at) - epoch(started_at)) AS seconds
        FROM meta.ingest_runs
        WHERE status = 'success' AND rows_received > 0
        GROUP BY source
        """
    ).fetchall()
    conn.close()

    result = {
        "label": args.label,
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "raw_row_counts": sizes,
        "total_raw_rows": sum(sizes.values()),
        "ingest_throughput_rows_per_s": {
            src: round(rows / secs, 1) for src, rows, secs in ingest_rates if secs
        },
        "stages": {},
    }

    print(f"benchmarking at {result['total_raw_rows']:,} raw rows")

    from normalization.runner import run_all
    dt, _ = _time("normalize (all sources)", lambda: run_all(db_path))
    result["stages"]["normalize_s"] = dt

    import duckdb as _duck

    from entity_resolution.config import ERConfig
    from entity_resolution.matcher import match_properties
    from entity_resolution.name_matcher import resolve_businesses, resolve_owners

    cfg = ERConfig()
    wconn = _duck.connect(db_path)
    try:
        dt, metrics = _time("er: properties", lambda: match_properties(wconn, cfg))
        result["stages"]["er_properties_s"] = dt
        result["er_blocking"] = {
            "comparisons": metrics["comparisons"],
            "naive_comparisons": metrics["naive_comparisons"],
            "reduction_pct": metrics["reduction_pct"],
        }
        dt, _ = _time("er: owners", lambda: resolve_owners(wconn, cfg))
        result["stages"]["er_owners_s"] = dt
        dt, _ = _time("er: businesses", lambda: resolve_businesses(wconn, cfg))
        result["stages"]["er_businesses_s"] = dt
        try:
            from entity_resolution.portfolio import build_owner_groups

            dt, _ = _time("er: portfolios", lambda: build_owner_groups(wconn))
            result["stages"]["er_portfolios_s"] = dt
        except Exception as exc:  # HPD not ingested locally
            print(f"  er: portfolios skipped ({str(exc)[:80]})")
    finally:
        wconn.close()

    def dbt(cmd: str):
        return subprocess.run(
            ["../.venv/bin/dbt", cmd, "--profiles-dir", ".", "--full-refresh"]
            if cmd == "run" else ["../.venv/bin/dbt", cmd, "--profiles-dir", "."],
            cwd="dbt", capture_output=True, text=True,
            env={"PATH": "/usr/bin:/bin", "HOME": str(Path.home()),
                 "MIP_DUCKDB_PATH": str(Path(db_path).resolve())},
            check=True,
        )

    dt, _ = _time("dbt run (full refresh)", lambda: dbt("run"))
    result["stages"]["dbt_run_s"] = dt
    dt, _ = _time("dbt test", lambda: dbt("test"))
    result["stages"]["dbt_test_s"] = dt
    result["stages"]["pipeline_total_s"] = round(
        sum(v for v in result["stages"].values()), 2
    )

    history = json.loads(RESULTS.read_text()) if RESULTS.exists() else []
    history.append(result)
    RESULTS.write_text(json.dumps(history, indent=2))
    print(f"appended to {RESULTS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
