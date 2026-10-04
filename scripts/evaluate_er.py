#!/usr/bin/env python3
"""CLI: run ER evaluation and write docs/er-evaluation.md with measured metrics."""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from entity_resolution.config import ERConfig
from entity_resolution.evaluator import evaluate_name_matching, evaluate_property_matching
from ingestion.config import get_settings
from ingestion.logging_setup import configure_logging


def render(prop: dict, names: dict, cfg: ERConfig, sample_size: int) -> str:
    ts = datetime.now(UTC).isoformat(timespec="seconds")
    cur, base = names["current_scorer"], names["token_set_only_baseline"]
    lines = [
        "# Entity-resolution evaluation",
        "",
        f"Generated {ts} by `scripts/evaluate_er.py` — all numbers measured on this",
        "repo's local warehouse; regenerate after any matcher change.",
        "",
        "## 1. Property matching — BBL-oracle evaluation",
        "",
        "Mentions carrying a PLUTO-known BBL have ground truth. The matcher is",
        "**blinded** (BBL stripped) and must resolve them by address alone; the",
        "prediction is scored against the hidden BBL. *Strict* = exact tax lot;",
        "*building* = same borough + street address (condo lots share buildings).",
        "",
        f"- Evaluation sample: **{prop['eval_n']:,}** mentions"
        f" (requested {sample_size:,}; {prop['excluded_no_address']:,} excluded lacking any address)",
        f"- Auto-match precision (strict lot): **{prop['precision_strict']:.1%}**",
        f"- Auto-match recall (strict lot): **{prop['recall_strict']:.1%}**",
        f"- False positive rate: **{prop['false_positive_rate']:.2%}**",
        f"- False negative rate: **{prop['false_negative_rate']:.2%}**",
        "",
        "| method | n | strict precision | building precision |",
        "|---|---:|---:|---:|",
    ]
    for method, band in prop["by_method"].items():
        if band["n"]:
            lines.append(
                f"| {method} | {band['n']:,} | {band['precision_strict']:.1%}"
                f" | {band['precision_building']:.1%} |"
            )
    lines += [
        f"| unmatched (false negatives) | {prop['unmatched']:,} | — | — |",
        "",
        f"Blocking during evaluation: {prop['blocking']['comparisons']:,} comparisons vs "
        f"{prop['blocking']['naive_comparisons']:,} naive "
        f"({prop['blocking']['reduction_pct']:.4f}% reduction).",
        "",
        "## 2. Name matching — audited labeled pairs",
        "",
        "Pairs in `entity_resolution/eval/labeled_name_pairs.csv` are drawn mostly",
        "from real match evidence / review queues and labeled conservatively",
        "(ambiguous → nonmatch; false splits are recoverable, false merges are not).",
        "",
        f"- Labeled pairs: **{cur['n_pairs']}**",
        f"- Thresholds: auto ≥ {cfg.name_auto_threshold}, review ≥ {cfg.name_review_threshold}",
        "",
        "| scorer | precision | recall | F1 | FPR | in review band |",
        "|---|---:|---:|---:|---:|---:|",
        _name_row("current (sort/blend)", cur),
        _name_row("token_set_ratio only (baseline)", base),
        "",
        "The baseline row is why the scorer changed: pure token_set_ratio scores",
        "1.0 for token-subset pairs ('ANGEL' vs 'ANGEL CHU'), silently merging",
        "distinct people. Persons now use token_sort only; orgs blend 50/50.",
        "",
        "### Current-scorer disagreements with labels",
        "",
    ]
    lines += [f"- {e}" for e in cur["errors"]] or ["- none"]
    lines += [
        "",
        "## Caveats",
        "",
        "- The BBL oracle covers mentions that *have* BBLs; addresses on BBL-less",
        "  records may be systematically messier. Treat the precision figure as an",
        "  upper-bound estimate for that subpopulation.",
        "- Name labels are conservative; some 'nonmatch' pairs may be true matches",
        "  (recall is understated rather than precision overstated).",
        "",
    ]
    return "\n".join(lines)


def _name_row(label: str, m: dict) -> str:
    def pct(v):
        return f"{v:.1%}" if v is not None else "—"

    return (
        f"| {label} | {pct(m['precision'])} | {pct(m['recall'])} | {pct(m['f1'])}"
        f" | {pct(m['false_positive_rate'])} | {m['in_review_band']} |"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-size", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="docs/er-evaluation.md")
    args = parser.parse_args()

    configure_logging()
    cfg = ERConfig()
    conn = duckdb.connect(str(get_settings().mip_duckdb_path), read_only=True)
    try:
        prop = evaluate_property_matching(conn, cfg, sample_size=args.sample_size, seed=args.seed)
        names = evaluate_name_matching(cfg)
    finally:
        conn.close()

    Path(args.out).write_text(render(prop, names, cfg, args.sample_size))
    print(json.dumps({"property": {k: v for k, v in prop.items() if k != "by_method"}}, indent=2))
    print(json.dumps({"names_current": names["current_scorer"]}, indent=2, default=str))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
