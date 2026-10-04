"""Owner & business entity resolution: name clustering with evidence.

Names cluster in three stages:
1. exact — identical normalized names collapse trivially;
2. blocked fuzzy — within (is_org, first_token) blocks, token_set_ratio
   edges at/above the AUTO threshold union clusters; the review band is
   queued, never merged;
3. phone boost (businesses only) — a shared normalized phone plus a
   moderately similar name is treated as auto evidence (two businesses
   rarely share a phone by accident; the name floor blocks franchises
   sharing a call center from collapsing).

Person-vs-organization matters: "JOHN SHEN" should never fuzzy-merge with
"SHEN JOHN LLC" on name similarity alone, so persons and orgs never share
a block.

Owner mentions come from permits (owner of record on the job) and PLUTO
(owner of record on the lot), restricted to properties the operational
data actually touches — clustering all 850K PLUTO owners would be wasted
work for buildings with no complaints, permits, or licenses.
"""

import hashlib
import logging
from collections import defaultdict

import duckdb
import pandas as pd
from rapidfuzz import fuzz

from entity_resolution.config import ERConfig
from entity_resolution.matcher import UnionFind
from normalization.io import PipelineRun, replace_table

logger = logging.getLogger(__name__)


def _entity_id(prefix: str, canonical_name: str, is_org: bool) -> str:
    return prefix + hashlib.sha1(f"{canonical_name}|{is_org}".encode()).hexdigest()[:10]


_LEGAL_SUFFIX_TOKENS = {"LLC", "INC", "CORP", "CO", "LTD", "LP", "LLP"}
_DIGIT_GUARD_CAP = 0.89   # inside the review band: queued, never auto-merged
_RULE_BOOST = 0.96        # confident rule-based match, above any sane AUTO


def name_similarity(a: str, b: str, is_org: bool) -> float:
    """Name similarity, tuned against eval/labeled_name_pairs.csv.

    Rules layered over fuzzy ratios (each earned by a measured failure):
    - digit guard: differing numeric tokens cap the score below AUTO —
      "PARKASH 2165 LLC" vs "PARKASH 2454 LLC" are per-building sibling
      LLCs, and "MARKET 2 CORP" vs "MARKET CORP" are sister companies;
    - legal-suffix rule: a diff of only LLC/INC/CORP/... tokens is not
      entity-distinguishing ("207 SHERMAN ASSOCIATES" ± "LLC");
    - person middle-initial rule: persons differing by one single-letter
      token are the same person with/without a middle initial;
    - subset guard: persons use token_sort only — token_set_ratio scores
      1.0 for subsets, which auto-merged "ANGEL" with "ANGEL CHU" and
      "LI HE DONG" with "LI LI" on real data. Orgs blend 50/50.
    """
    tokens_a, tokens_b = set(a.split()), set(b.split())
    digits_a = {t for t in tokens_a if t.isdigit()}
    digits_b = {t for t in tokens_b if t.isdigit()}

    sort = fuzz.token_sort_ratio(a, b) / 100.0
    score = sort if not is_org else 0.5 * sort + 0.5 * fuzz.token_set_ratio(a, b) / 100.0

    if digits_a != digits_b:
        return min(score, _DIGIT_GUARD_CAP)

    diff = tokens_a ^ tokens_b
    if diff and is_org:
        # Legal suffixes and articles are not entity-distinguishing.
        residual = diff - _LEGAL_SUFFIX_TOKENS - {"THE"}
        if not residual:
            return max(score, _RULE_BOOST)
        # Initials consolidation: "WELLS FARGO BANK N A" vs "... BANK NA",
        # "T F CORNERSTONE" vs "TF CORNERSTONE" — a tiny diff made of
        # ≤2-char fragments. Kept deliberately tight (≤3 tokens, ≤4 chars
        # total) so "B C D E REALTY" vs "B I H REALTY" stays out.
        if len(residual) <= 3 and all(len(t) <= 2 for t in residual) and sum(
            len(t) for t in residual
        ) <= 4:
            return max(score, _RULE_BOOST)
    if diff and not is_org and all(len(t) == 1 for t in diff):
        return max(score, _RULE_BOOST)
    return score


def cluster_names(
    names: list[tuple[str, bool, int]],  # (normalized_name, is_org, weight)
    cfg: ERConfig,
    extra_edges: list[tuple[str, str, float, str]] | None = None,
) -> tuple[dict[str, str], list[dict], list[dict]]:
    """Cluster normalized names.

    Returns (name → cluster_root), match-evidence rows, review-queue rows.
    ``extra_edges`` lets callers inject non-name evidence (e.g. shared
    phones) as (name_a, name_b, score, method).
    """
    uf = UnionFind()
    evidence: list[dict] = []
    review: list[dict] = []

    seen: dict[tuple[str, bool], int] = {}
    for name, is_org, weight in names:
        seen[(name, is_org)] = seen.get((name, is_org), 0) + weight
        uf.find((name, is_org))

    blocks: dict[tuple[bool, str], list[str]] = defaultdict(list)
    for name, is_org in seen:
        first = name.split()[0] if name.split() else ""
        blocks[(is_org, first)].append(name)

    oversize = 0
    for (is_org, _first), members in blocks.items():
        if len(members) > cfg.max_block_size:
            oversize += 1
            logger.warning(
                "name_block_skipped", extra={"first_token": _first, "size": len(members)}
            )
            continue
        members = sorted(members)
        for i, a in enumerate(members):
            for b in members[i + 1 :]:
                score = name_similarity(a, b, is_org)
                if score >= cfg.name_auto_threshold:
                    uf.union((a, is_org), (b, is_org))
                    evidence.append(
                        {"name_a": a, "name_b": b, "is_org": is_org, "score": round(score, 4),
                         "method": "name_fuzzy", "decision": "auto"}
                    )
                elif score >= cfg.name_review_threshold:
                    review.append(
                        {"name_a": a, "name_b": b, "is_org": is_org, "score": round(score, 4),
                         "method": "name_fuzzy", "decision": "review"}
                    )

    for a, b, score, method in extra_edges or []:
        for is_org in (True, False):
            if (a, is_org) in seen and (b, is_org) in seen:
                uf.union((a, is_org), (b, is_org))
                evidence.append(
                    {"name_a": a, "name_b": b, "is_org": is_org, "score": round(score, 4),
                     "method": method, "decision": "auto"}
                )

    # canonical representative = heaviest variant in each cluster
    cluster_members: dict[tuple, list[tuple[str, bool]]] = defaultdict(list)
    for key in seen:
        cluster_members[uf.find(key)].append(key)
    assignment: dict[tuple[str, bool], str] = {}
    for members in cluster_members.values():
        canonical = max(members, key=lambda k: (seen[k], -len(k[0])))
        for member in members:
            assignment[member] = canonical[0]

    if oversize:
        logger.warning("name_blocks_skipped_total", extra={"count": oversize})
    return (
        {f"{name}|{int(is_org)}": canonical for (name, is_org), canonical in assignment.items()},
        evidence,
        review,
    )


OWNER_MENTIONS_SQL = """
    WITH permit_owners AS (
        SELECT p.owner_name AS name, p.owner_is_org AS is_org,
               m.property_id, count(*) AS n_records, 'permits' AS source
        FROM clean.permits p
        JOIN er.map_permits m ON m.source_record_id = p.permit_row_id
        WHERE p.dup_rank = 1 AND p.owner_name IS NOT NULL
        GROUP BY ALL
    ),
    pluto_owners AS (
        SELECT pr.pluto_owner_name AS name, pr.pluto_owner_is_org AS is_org,
               pr.property_id, greatest(pr.n_source_records, 1) AS n_records, 'pluto' AS source
        FROM er.properties pr
        WHERE pr.pluto_owner_name IS NOT NULL AND pr.in_pluto
    )
    SELECT * FROM permit_owners UNION ALL SELECT * FROM pluto_owners
"""


def resolve_owners(conn: duckdb.DuckDBPyConnection, cfg: ERConfig | None = None) -> dict:
    cfg = cfg or ERConfig()
    with PipelineRun(conn, "er.owners") as run:
        mentions = conn.execute(OWNER_MENTIONS_SQL).fetchdf()
        weights = (
            mentions.groupby(["name", "is_org"])["n_records"].sum().reset_index()
        )
        names = [(r["name"], bool(r["is_org"]), int(r["n_records"])) for _, r in weights.iterrows()]
        assignment, evidence, review = cluster_names(names, cfg)

        mentions["canonical_name"] = [
            assignment[f"{n}|{int(o)}"] for n, o in zip(mentions["name"], mentions["is_org"], strict=True)
        ]
        mentions["owner_id"] = [
            _entity_id("O", c, bool(o))
            for c, o in zip(mentions["canonical_name"], mentions["is_org"], strict=True)
        ]

        owners = (
            mentions.groupby(["owner_id", "canonical_name", "is_org"])
            .agg(n_name_variants=("name", "nunique"), n_properties=("property_id", "nunique"),
                 n_records=("n_records", "sum"))
            .reset_index()
            .rename(columns={"canonical_name": "canonical_owner_name", "is_org": "owner_is_org"})
        )
        prop_owners = (
            mentions.groupby(["property_id", "owner_id", "source"])["n_records"].sum().reset_index()
            .rename(columns={"source": "relation", "n_records": "evidence_records"})
        )
        name_map = mentions[["name", "is_org", "owner_id"]].drop_duplicates()

        replace_table(conn, "er", "owners", owners)
        replace_table(conn, "er", "map_property_owners", prop_owners)
        replace_table(conn, "er", "owner_name_map", name_map)
        replace_table(conn, "er", "owner_matches",
                      pd.DataFrame(evidence) if evidence else _empty_evidence())
        replace_table(conn, "er", "owner_review_queue",
                      pd.DataFrame(review) if review else _empty_evidence())

        run.records_processed = len(mentions)
        run.metrics = {
            "distinct_names": len(names),
            "owners": len(owners),
            "merge_rate_pct": round(100.0 * (1 - len(owners) / max(len(names), 1)), 2),
            "fuzzy_edges": len(evidence),
            "review_pairs": len(review),
        }
        logger.info("owner_er_done", extra=run.metrics)
        return run.metrics


def resolve_businesses(conn: duckdb.DuckDBPyConnection, cfg: ERConfig | None = None) -> dict:
    cfg = cfg or ERConfig()
    with PipelineRun(conn, "er.businesses") as run:
        rows = conn.execute(
            """
            SELECT license_id, business_name, dba_trade_name, contact_phone
            FROM clean.licenses WHERE business_name IS NOT NULL
            """
        ).fetchdf()

        weights: dict[str, int] = defaultdict(int)
        for _, r in rows.iterrows():
            weights[r["business_name"]] += 1
        names = [(n, True, w) for n, w in weights.items()]

        # Phone evidence: same phone + moderately similar name → same business.
        phone_edges: list[tuple[str, str, float, str]] = []
        by_phone = rows.dropna(subset=["contact_phone"]).groupby("contact_phone")["business_name"].unique()
        for _phone, group in by_phone.items():
            group = sorted(set(group))
            if len(group) > 10:  # shared call centers / registered agents
                continue
            for i, a in enumerate(group):
                for b in group[i + 1 :]:
                    sim = name_similarity(a, b, is_org=True)
                    if 0.80 <= sim < cfg.name_auto_threshold:
                        phone_edges.append((a, b, round(sim, 4), "phone+name"))

        assignment, evidence, review = cluster_names(names, cfg, extra_edges=phone_edges)

        rows["canonical_name"] = [assignment[f"{n}|1"] for n in rows["business_name"]]
        rows["business_id"] = [_entity_id("B", c, True) for c in rows["canonical_name"]]

        businesses = (
            rows.groupby(["business_id", "canonical_name"])
            .agg(n_licenses=("license_id", "nunique"), n_name_variants=("business_name", "nunique"))
            .reset_index()
            .rename(columns={"canonical_name": "canonical_business_name"})
        )
        replace_table(conn, "er", "businesses", businesses)
        replace_table(conn, "er", "map_license_business",
                      rows[["license_id", "business_id"]].drop_duplicates())
        replace_table(conn, "er", "business_matches",
                      pd.DataFrame(evidence) if evidence else _empty_evidence())
        replace_table(conn, "er", "business_review_queue",
                      pd.DataFrame(review) if review else _empty_evidence())

        run.records_processed = len(rows)
        run.metrics = {
            "distinct_names": len(names),
            "businesses": len(businesses),
            "merge_rate_pct": round(100.0 * (1 - len(businesses) / max(len(names), 1)), 2),
            "phone_edges": len(phone_edges),
            "review_pairs": len(review),
        }
        logger.info("business_er_done", extra=run.metrics)
        return run.metrics


def _empty_evidence() -> pd.DataFrame:
    return pd.DataFrame(columns=["name_a", "name_b", "is_org", "score", "method", "decision"])
