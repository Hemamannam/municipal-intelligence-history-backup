#!/usr/bin/env python3
"""Profile an ingested source and write a data-discovery report.

Reads the latest version of every record from ``raw.<source>``, computes
column-level statistics, hunts for primary-key candidates and data-quality
issues, and writes ``docs/profiling/<source>.md``.

Example:
    python scripts/profile_dataset.py --source nyc_311
"""

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd

from ingestion.config import get_settings
from ingestion.sources import SOURCES, get_source

# NYC bounding box (generous) for coordinate sanity checks.
NYC_LAT = (40.4, 41.0)
NYC_LON = (-74.3, -73.6)

STREET_SUFFIX_VARIANTS = {
    "STREET": {"ST", "STR", "STREET"},
    "AVENUE": {"AVE", "AV", "AVENUE"},
    "BOULEVARD": {"BLVD", "BLV", "BOULEVARD"},
    "ROAD": {"RD", "ROAD"},
    "PLACE": {"PL", "PLACE"},
    "DRIVE": {"DR", "DRIVE"},
    "COURT": {"CT", "COURT"},
    "LANE": {"LN", "LANE"},
    "PARKWAY": {"PKWY", "PARKWAY"},
}


def load_latest_records(db_path: str, source_key: str) -> pd.DataFrame:
    """Latest version of each record, payload exploded into columns."""
    conn = duckdb.connect(db_path, read_only=True)
    try:
        rows = conn.execute(
            f"""
            SELECT payload FROM (
                SELECT payload,
                       row_number() OVER (
                           PARTITION BY source_record_id
                           ORDER BY socrata_updated_at DESC NULLS LAST, ingested_at DESC
                       ) AS rn
                FROM raw.{source_key}
            ) WHERE rn = 1
            """
        ).fetchall()
        versions = conn.execute(f"SELECT count(*) FROM raw.{source_key}").fetchone()[0]
    finally:
        conn.close()
    payloads = [json.loads(r[0]) for r in rows]
    # Some sources nest objects (e.g. 311's `location` is a GeoJSON-ish dict);
    # flatten non-scalars to JSON strings so column ops work uniformly.
    for payload in payloads:
        for key, value in payload.items():
            if isinstance(value, (dict, list)):
                payload[key] = json.dumps(value, sort_keys=True)
    df = pd.DataFrame(payloads)
    df.attrs["raw_versions"] = versions
    return df


def _is_address_col(col: str) -> bool:
    return bool(re.search(r"address|street|house", col, re.I))


def profile(df: pd.DataFrame, source_key: str) -> dict:
    n = len(df)
    cols = list(df.columns)
    report: dict = {
        "source": source_key,
        "rows": n,
        "raw_versions": df.attrs.get("raw_versions", n),
        "columns": len(cols),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "column_stats": [],
        "pk_candidates": [],
        "issues": [],
        "date_ranges": {},
        "categoricals": {},
        "address_findings": [],
    }

    full_dupes = int(df.duplicated().sum())
    if full_dupes:
        report["issues"].append(f"{full_dupes:,} fully duplicated rows (all columns identical)")

    for col in cols:
        series = df[col]
        non_null = series.notna() & (series.astype(str).str.strip() != "")
        n_non_null = int(non_null.sum())
        null_pct = 100.0 * (n - n_non_null) / n if n else 0.0
        distinct = int(series[non_null].nunique())
        top = series[non_null].value_counts().head(3)
        report["column_stats"].append(
            {
                "column": col,
                "null_pct": round(null_pct, 1),
                "distinct": distinct,
                "top_values": [f"{v} ({c:,})" for v, c in top.items()],
            }
        )
        if n and n_non_null == n and distinct == n:
            report["pk_candidates"].append(col)
        if null_pct > 50:
            report["issues"].append(f"`{col}` is {null_pct:.0f}% null/blank")

        # Date columns: try parsing, record range, flag unparseable/future.
        if re.search(r"date|_dd$", col, re.I):
            parsed = pd.to_datetime(series[non_null], errors="coerce", format="mixed")
            bad = int(parsed.isna().sum())
            if n_non_null:
                report["date_ranges"][col] = {
                    "min": str(parsed.min()),
                    "max": str(parsed.max()),
                    "unparseable": bad,
                }
                if bad:
                    report["issues"].append(f"`{col}`: {bad:,} unparseable date values")
                future = int((parsed > pd.Timestamp.now() + pd.Timedelta(days=1)).sum())
                if future:
                    report["issues"].append(f"`{col}`: {future:,} values in the future")

        # Low-cardinality categoricals worth documenting.
        if 0 < distinct <= 30 and n_non_null > 0 and not re.search(r"date", col, re.I):
            report["categoricals"][col] = {
                str(v): int(c) for v, c in series[non_null].value_counts().head(10).items()
            }

    # Coordinate sanity.
    for lat_col, lon_col in (("latitude", "longitude"), ("gis_latitude", "gis_longitude")):
        if lat_col in df.columns and lon_col in df.columns:
            lat = pd.to_numeric(df[lat_col], errors="coerce")
            lon = pd.to_numeric(df[lon_col], errors="coerce")
            has_coords = lat.notna() & lon.notna()
            in_bounds = has_coords & lat.between(*NYC_LAT) & lon.between(*NYC_LON)
            missing = int((~has_coords).sum())
            out_of_bounds = int((has_coords & ~in_bounds).sum())
            if missing:
                report["issues"].append(
                    f"{missing:,} rows ({100 * missing / n:.1f}%) missing coordinates"
                )
            if out_of_bounds:
                report["issues"].append(
                    f"{out_of_bounds:,} rows with coordinates outside the NYC bounding box"
                )

    # Address heuristics: suffix abbreviation variants in street-ish columns.
    for col in cols:
        if not _is_address_col(col):
            continue
        values = df[col].dropna().astype(str).str.upper()
        if values.empty:
            continue
        last_tokens = values.str.strip().str.split().str[-1].value_counts()
        for canonical, variants in STREET_SUFFIX_VARIANTS.items():
            present = {v: int(last_tokens.get(v, 0)) for v in variants if last_tokens.get(v, 0) > 0}
            if len(present) > 1:
                report["address_findings"].append(
                    f"`{col}` mixes suffix spellings for {canonical}: "
                    + ", ".join(f"{k} ({v:,})" for k, v in sorted(present.items()))
                )
    return report


def render_markdown(report: dict, source_name: str, pk_fields: tuple[str, ...]) -> str:
    lines = [
        f"# Data profile: {source_name}",
        "",
        f"- Generated: {report['generated_at']} (from local raw layer, latest record versions)",
        f"- Rows (distinct records): **{report['rows']:,}**"
        f" — raw versions stored: {report['raw_versions']:,}",
        f"- Columns: **{report['columns']}**",
        f"- Configured primary key: `{' + '.join(pk_fields)}`",
        "",
        "## Primary-key candidates (unique + never null in sample)",
        "",
    ]
    if report["pk_candidates"]:
        lines += [f"- `{c}`" for c in report["pk_candidates"]]
    else:
        lines.append("- none found — a composite key is required")
    lines += ["", "## Potential data-quality issues", ""]
    lines += [f"- {issue}" for issue in report["issues"]] or ["- none detected"]
    if report["address_findings"]:
        lines += ["", "## Address inconsistencies (entity-resolution fuel)", ""]
        lines += [f"- {f}" for f in report["address_findings"]]
    if report["date_ranges"]:
        lines += ["", "## Date ranges", "", "| column | min | max | unparseable |", "|---|---|---|---|"]
        for col, r in report["date_ranges"].items():
            lines.append(f"| `{col}` | {r['min']} | {r['max']} | {r['unparseable']:,} |")
    if report["categoricals"]:
        lines += ["", "## Categorical columns (top values)", ""]
        for col, counts in report["categoricals"].items():
            top = ", ".join(f"{k} ({v:,})" for k, v in list(counts.items())[:6])
            lines.append(f"- `{col}`: {top}")
    lines += [
        "",
        "## Column statistics",
        "",
        "| column | null % | distinct | top values |",
        "|---|---:|---:|---|",
    ]
    for cs in report["column_stats"]:
        top = "; ".join(str(t)[:60] for t in cs["top_values"])
        lines.append(f"| `{cs['column']}` | {cs['null_pct']} | {cs['distinct']:,} | {top} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, choices=sorted(SOURCES))
    parser.add_argument("--out-dir", default="docs/profiling")
    args = parser.parse_args()

    settings = get_settings()
    source = get_source(args.source)
    df = load_latest_records(str(settings.mip_duckdb_path), args.source)
    if df.empty:
        print(f"No data in raw.{args.source} — run ingestion first.", file=sys.stderr)
        return 1

    report = profile(df, args.source)
    out_path = Path(args.out_dir) / f"{args.source}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_markdown(report, source.name, source.pk_fields))

    print(f"Profiled {report['rows']:,} records ({report['columns']} columns) -> {out_path}")
    print(f"PK candidates: {report['pk_candidates'] or 'NONE'}")
    print(f"Issues found: {len(report['issues'])}")
    for issue in report["issues"][:12]:
        print(f"  - {issue}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
