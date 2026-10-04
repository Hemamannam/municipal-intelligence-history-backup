"""Entity-resolution evaluation — every number here is measured, never invented.

Two complementary evaluations:

1. **Property matching, BBL-oracle (large-scale, programmatic).**
   Mentions that carry a valid BBL known to PLUTO have ground truth: the
   lot they belong to. We *blind* the matcher (strip the BBL) and make it
   resolve those mentions by address alone, exactly as it would for
   BBL-less records. Prediction vs hidden BBL gives precision/recall on
   thousands of real, messy pairs — including natural hard negatives
   (same street, adjacent lots). "Building-level" correctness is also
   reported: predicting a different condo lot at the same street address
   is wrong at lot granularity but right at building granularity.

2. **Name matching (hand-audited, small-scale).**
   eval/labeled_name_pairs.csv holds pairs drawn overwhelmingly from real
   match evidence and review queues, labeled conservatively (ambiguous →
   nonmatch; the platform prefers false splits over false merges). The
   file is committed so every label is auditable.
"""

import csv
import random
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
from rapidfuzz import fuzz

from entity_resolution.candidate_generation import BlockingStats, build_block_index, iter_candidates
from entity_resolution.config import ERConfig
from entity_resolution.matcher import score_pair
from entity_resolution.name_matcher import name_similarity
from entity_resolution.owner_normalizer import normalize_name

LABELED_PAIRS = Path(__file__).parent / "eval" / "labeled_name_pairs.csv"


@dataclass
class Band:
    n: int = 0
    strict_correct: int = 0
    building_correct: int = 0

    def as_dict(self) -> dict:
        return {
            "n": self.n,
            "strict_correct": self.strict_correct,
            "building_correct": self.building_correct,
            "precision_strict": round(self.strict_correct / self.n, 4) if self.n else None,
            "precision_building": round(self.building_correct / self.n, 4) if self.n else None,
        }


@dataclass
class PropertyEval:
    eval_n: int = 0
    excluded_no_address: int = 0
    bands: dict = field(default_factory=dict)
    unmatched: int = 0

    def as_dict(self) -> dict:
        auto_bands = [b for m, b in self.bands.items() if m != "review"]
        tp = sum(b.strict_correct for b in auto_bands)
        fp = sum(b.n - b.strict_correct for b in auto_bands)
        return {
            "eval_n": self.eval_n,
            "excluded_no_address": self.excluded_no_address,
            "by_method": {m: b.as_dict() for m, b in self.bands.items()},
            "unmatched": self.unmatched,
            "precision_strict": round(tp / (tp + fp), 4) if tp + fp else None,
            "recall_strict": round(tp / self.eval_n, 4) if self.eval_n else None,
            "false_positive_rate": round(fp / self.eval_n, 4) if self.eval_n else None,
            "false_negative_rate": round(
                (self.eval_n - tp - fp) / self.eval_n, 4
            ) if self.eval_n else None,
        }


def evaluate_property_matching(
    conn: duckdb.DuckDBPyConnection,
    cfg: ERConfig | None = None,
    sample_size: int = 20_000,
    seed: int = 42,
) -> dict:
    """Blind the matcher to BBLs it could have used; score it against them."""
    cfg = cfg or ERConfig()
    reference = conn.execute(
        """
        SELECT bbl, house_number, street_name, street_suffix, borough, zipcode,
               normalized_address, latitude, longitude
        FROM clean.pluto_lots
        """
    ).fetchdf()
    reference = reference.astype(object).where(reference.notna(), None)
    ref_rows = reference.to_dict("records")
    ref_by_bbl = {r["bbl"]: r for r in ref_rows}
    ref_by_addr = {
        (r["borough"], r["normalized_address"]): r
        for r in ref_rows
        if r["borough"] and r["normalized_address"]
    }
    ref_index = build_block_index(ref_rows, ("borough", "house_number"))

    mentions = conn.execute(
        """
        SELECT * FROM er.property_mentions
        WHERE bbl IS NOT NULL
        """
    ).fetchdf()
    mentions = mentions.astype(object).where(mentions.notna(), None)
    eval_rows = [m for m in mentions.to_dict("records") if m["bbl"] in ref_by_bbl]
    random.Random(seed).shuffle(eval_rows)
    eval_rows = eval_rows[:sample_size]

    result = PropertyEval()
    result.bands = {
        "address_exact": Band(),
        "fuzzy_address": Band(),
        "review": Band(),
    }
    stats = BlockingStats(total_left=len(eval_rows), total_right=len(ref_rows))

    def _building_eq(pred: dict, truth: dict) -> bool:
        return (
            pred["borough"] == truth["borough"]
            and pred["normalized_address"] == truth["normalized_address"]
            and pred["normalized_address"] is not None
        )

    fuzzy_pending: list[dict] = []
    for m in eval_rows:
        truth = ref_by_bbl[m["bbl"]]
        if not m.get("normalized_address"):
            result.excluded_no_address += 1
            continue
        result.eval_n += 1
        blinded = dict(m, bbl=None)
        exact = ref_by_addr.get((blinded.get("borough"), blinded.get("normalized_address")))
        if exact is not None:
            band = result.bands["address_exact"]
            band.n += 1
            band.strict_correct += int(exact["bbl"] == truth["bbl"])
            band.building_correct += int(_building_eq(exact, truth))
        else:
            blinded["_truth"] = truth
            fuzzy_pending.append(blinded)

    matched_ids = set()
    candidate_iter = iter_candidates(
        fuzzy_pending, ref_index, ("borough", "house_number"), cfg.max_block_size, stats
    )
    for m, candidates in candidate_iter:
        truth = m["_truth"]
        best, best_total = None, -1.0
        for c in candidates:
            total = score_pair(m, c, cfg).weighted(cfg)
            if total > best_total:
                best, best_total = c, total
        if best is None:
            continue
        if best_total >= cfg.auto_match_threshold:
            band = result.bands["fuzzy_address"]
        elif best_total >= cfg.review_threshold:
            band = result.bands["review"]
        else:
            continue
        matched_ids.add(m["mention_id"])
        band.n += 1
        band.strict_correct += int(best["bbl"] == truth["bbl"])
        band.building_correct += int(_building_eq(best, truth))

    result.unmatched = len(fuzzy_pending) - len(matched_ids)
    out = result.as_dict()
    out["blocking"] = stats.summary()
    return out


def evaluate_name_matching(cfg: ERConfig | None = None, path: Path = LABELED_PAIRS) -> dict:
    """Score the name matcher against the audited labeled pairs."""
    cfg = cfg or ERConfig()
    with open(path) as f:
        pairs = list(csv.DictReader(f))

    def metrics(scorer) -> dict:
        tp = fp = tn = fn = review = 0
        errors = []
        for p in pairs:
            is_org = p["is_org"] == "1"
            # Mirror the production path: names are normalized before the
            # matcher ever sees them.
            a = normalize_name(p["name_a"]) or p["name_a"]
            b = normalize_name(p["name_b"]) or p["name_b"]
            score = scorer(a, b, is_org)
            predicted = score >= cfg.name_auto_threshold
            actual = p["label"] == "match"
            if cfg.name_review_threshold <= score < cfg.name_auto_threshold:
                review += 1
            if predicted and actual:
                tp += 1
            elif predicted and not actual:
                fp += 1
                errors.append(f"FP: {p['name_a']} ~ {p['name_b']} ({score:.2f})")
            elif not predicted and actual:
                fn += 1
                errors.append(f"FN: {p['name_a']} ~ {p['name_b']} ({score:.2f})")
            else:
                tn += 1
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision and recall and (precision + recall)
            else None
        )
        return {
            "n_pairs": len(pairs),
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "precision": round(precision, 4) if precision is not None else None,
            "recall": round(recall, 4) if recall is not None else None,
            "f1": round(f1, 4) if f1 is not None else None,
            "false_positive_rate": round(fp / (fp + tn), 4) if fp + tn else None,
            "in_review_band": review,
            "errors": errors,
        }

    return {
        "current_scorer": metrics(name_similarity),
        "token_set_only_baseline": metrics(lambda a, b, _o: fuzz.token_set_ratio(a, b) / 100.0),
    }
