"""Property entity resolution: operational mentions → canonical properties.

Strategy (reference-anchored):

1. PLUTO tax lots seed the property universe — one property per valid BBL.
2. Deterministic pass: operational mentions carrying a valid BBL join
   directly (``bbl_exact``); a valid BBL absent from PLUTO seeds a
   standalone property (``bbl_standalone`` — PLUTO is an annual snapshot,
   new condos lag).
3. Deterministic pass 2: exact (borough, normalized_address) equality
   against the reference (``address_exact``).
4. Fuzzy pass: remaining mentions are blocked on (borough, house_number)
   and scored against reference candidates:
       score = w_street·street_sim + w_zip·zip_agree
             + w_geo·geo_proximity + w_suffix·suffix_agree
   score ≥ AUTO → matched; REVIEW ≤ score < AUTO → review queue;
   below → standalone property (never silently merged).
5. Leftover standalones sharing exact (borough, normalized_address) are
   unioned so the same unknown building isn't minted twice.

Every accepted or queued pair keeps its component scores and method — a
match must be explainable when a customer challenges it (Phase 14).
"""

import hashlib
import logging
import math
from dataclasses import dataclass

import duckdb
import pandas as pd
from rapidfuzz import fuzz

from entity_resolution.candidate_generation import BlockingStats, build_block_index, iter_candidates
from entity_resolution.config import ERConfig
from normalization.io import PipelineRun, replace_table

logger = logging.getLogger(__name__)


class UnionFind:
    def __init__(self):
        self.parent: dict = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:  # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


@dataclass
class ComponentScores:
    street: float
    zip: float
    geo: float
    suffix: float

    def weighted(self, cfg: ERConfig) -> float:
        return round(
            cfg.weight_street * self.street
            + cfg.weight_zip * self.zip
            + cfg.weight_geo * self.geo
            + cfg.weight_suffix * self.suffix,
            4,
        )


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def score_pair(mention: dict, candidate: dict, cfg: ERConfig) -> ComponentScores:
    """Component similarity between an operational mention and a candidate."""
    street = (
        fuzz.token_sort_ratio(mention.get("street_name") or "", candidate.get("street_name") or "")
        / 100.0
    )

    zip_a, zip_b = mention.get("zipcode"), candidate.get("zipcode")
    zip_score = 1.0 if (zip_a and zip_a == zip_b) else (0.5 if not zip_a or not zip_b else 0.0)

    lat_a, lon_a = mention.get("latitude"), mention.get("longitude")
    lat_b, lon_b = candidate.get("latitude"), candidate.get("longitude")
    if None in (lat_a, lon_a, lat_b, lon_b):
        geo = 0.5  # neutral: absence of coordinates is not evidence against
    else:
        dist = _haversine_m(lat_a, lon_a, lat_b, lon_b)
        span = cfg.geo_zero_credit_m - cfg.geo_full_credit_m
        geo = max(0.0, min(1.0, (cfg.geo_zero_credit_m - dist) / span))

    suf_a, suf_b = mention.get("street_suffix"), candidate.get("street_suffix")
    suffix = 1.0 if (suf_a == suf_b) else (0.5 if not suf_a or not suf_b else 0.0)

    return ComponentScores(street=round(street, 4), zip=zip_score, geo=round(geo, 4), suffix=suffix)


def _standalone_id(borough: str | None, normalized_address: str | None, fallback: str) -> str:
    basis = f"{borough}|{normalized_address}" if normalized_address else fallback
    return "PX" + hashlib.sha1(basis.encode()).hexdigest()[:10]


MENTIONS_SQL = """
CREATE OR REPLACE TABLE er.property_mentions AS
WITH unioned AS (
    SELECT 'complaints' AS source, house_number, street_name, street_suffix, borough,
           zipcode, bbl, normalized_address,
           avg(latitude) AS latitude, avg(longitude) AS longitude, count(*) AS n_records
    FROM clean.complaints
    WHERE normalized_address IS NOT NULL OR bbl IS NOT NULL
    GROUP BY ALL
    UNION ALL
    SELECT 'permits', house_number, street_name, street_suffix, borough,
           zipcode, bbl, normalized_address,
           avg(latitude), avg(longitude), count(*)
    FROM clean.permits
    WHERE dup_rank = 1 AND (normalized_address IS NOT NULL OR bbl IS NOT NULL)
    GROUP BY ALL
    UNION ALL
    SELECT 'licenses', house_number, street_name, street_suffix, borough,
           zipcode, bbl, normalized_address,
           avg(latitude), avg(longitude), count(*)
    FROM clean.licenses
    WHERE is_nyc_premises AND (normalized_address IS NOT NULL OR bbl IS NOT NULL)
    GROUP BY ALL
)
SELECT row_number() OVER () AS mention_id, *
FROM unioned
"""


def match_properties(conn: duckdb.DuckDBPyConnection, cfg: ERConfig | None = None) -> dict:
    """Run the full property-resolution pass. Returns summary metrics."""
    cfg = cfg or ERConfig()
    conn.execute("CREATE SCHEMA IF NOT EXISTS er")

    with PipelineRun(conn, "er.properties") as run:
        conn.execute(MENTIONS_SQL)
        mentions = conn.execute("SELECT * FROM er.property_mentions").fetchdf()
        reference = conn.execute(
            """
            SELECT bbl, house_number, street_name, street_suffix, borough, zipcode,
                   normalized_address, latitude, longitude
            FROM clean.pluto_lots
            """
        ).fetchdf()

        # NULL → None (not NaN: NaN is truthy and poisons `if bbl` guards).
        mentions = mentions.astype(object).where(pd.notna(mentions), None)
        reference = reference.astype(object).where(pd.notna(reference), None)
        mention_rows = mentions.to_dict("records")
        ref_rows = reference.to_dict("records")
        ref_by_bbl = {r["bbl"]: r for r in ref_rows}
        ref_by_addr = {
            (r["borough"], r["normalized_address"]): r
            for r in ref_rows
            if r["borough"] and r["normalized_address"]
        }

        matches: list[dict] = []
        review: list[dict] = []
        unresolved: list[dict] = []

        # -- pass 1: deterministic BBL ------------------------------------
        no_bbl: list[dict] = []
        for m in mention_rows:
            bbl = m.get("bbl")
            if bbl and bbl in ref_by_bbl:
                matches.append(_match_row(m, "P" + bbl, "bbl_exact", 1.0, None))
            elif bbl:
                matches.append(_match_row(m, "P" + bbl, "bbl_standalone", 1.0, None))
            else:
                no_bbl.append(m)

        # -- pass 2: deterministic exact address --------------------------
        still_unmatched: list[dict] = []
        for m in no_bbl:
            key = (m.get("borough"), m.get("normalized_address"))
            candidate = ref_by_addr.get(key)
            if candidate is not None and key[0] and key[1]:
                matches.append(_match_row(m, "P" + candidate["bbl"], "address_exact", 1.0, None))
            else:
                still_unmatched.append(m)

        # -- pass 3: blocked fuzzy against reference ----------------------
        stats = BlockingStats(total_left=len(still_unmatched), total_right=len(ref_rows))
        block_key = ("borough", "house_number")
        ref_index = build_block_index(ref_rows, block_key)
        fuzzy_resolved_ids = set()
        candidate_iter = iter_candidates(still_unmatched, ref_index, block_key, cfg.max_block_size, stats)
        for m, candidates in candidate_iter:
            best, best_scores, best_total = None, None, -1.0
            for c in candidates:
                scores = score_pair(m, c, cfg)
                total = scores.weighted(cfg)
                if total > best_total:
                    best, best_scores, best_total = c, scores, total
            if best is None:
                continue
            if best_total >= cfg.auto_match_threshold:
                matches.append(_match_row(m, "P" + best["bbl"], "fuzzy_address", best_total, best_scores))
                fuzzy_resolved_ids.add(m["mention_id"])
            elif best_total >= cfg.review_threshold:
                review.append(
                    _match_row(m, "P" + best["bbl"], "fuzzy_address", best_total, best_scores)
                )

        unresolved = [m for m in still_unmatched if m["mention_id"] not in fuzzy_resolved_ids]

        # -- pass 4: cluster standalones by exact address ------------------
        # IDs must be DETERMINISTIC across runs: incremental marts retain
        # property_ids between ER regenerations, so an id derived from
        # row_number() would orphan them (observed: 1,120 orphans in
        # fct_complaints). Address-less mentions hash their full signature.
        for m in unresolved:
            if m.get("normalized_address"):
                basis = f"{m.get('borough')}|{m['normalized_address']}"
            else:
                basis = "|".join(
                    str(m.get(f))
                    for f in ("source", "house_number", "street_name", "street_suffix",
                              "borough", "zipcode")
                )
            pid = _standalone_id(m.get("borough"), m.get("normalized_address"), basis)
            matches.append(_match_row(m, pid, "standalone", 0.0, None))

        match_df = pd.DataFrame(matches)
        replace_table(conn, "er", "property_matches", match_df)
        replace_table(
            conn, "er", "review_queue",
            pd.DataFrame(review) if review else pd.DataFrame(columns=match_df.columns),
        )
        _materialize_properties(conn)
        _materialize_record_maps(conn)

        decided = len(match_df)
        run.records_processed = decided
        run.metrics = {
            "mentions": len(mention_rows),
            "bbl_exact": int((match_df["match_method"] == "bbl_exact").sum()),
            "bbl_standalone": int((match_df["match_method"] == "bbl_standalone").sum()),
            "address_exact": int((match_df["match_method"] == "address_exact").sum()),
            "fuzzy_auto": int((match_df["match_method"] == "fuzzy_address").sum()),
            "review_queue": len(review),
            "standalone": int((match_df["match_method"] == "standalone").sum()),
            "match_rate_pct": round(
                100.0 * float((match_df["match_method"] != "standalone").mean()), 2
            ),
            **stats.summary(),
        }
        logger.info("property_er_done", extra=run.metrics)
        return run.metrics


def _match_row(mention: dict, property_id: str, method: str, score: float, scores) -> dict:
    return {
        "mention_id": mention["mention_id"],
        "source": mention["source"],
        "property_id": property_id,
        "match_method": method,
        "match_score": score,
        "street_score": scores.street if scores else None,
        "zip_score": scores.zip if scores else None,
        "geo_score": scores.geo if scores else None,
        "suffix_score": scores.suffix if scores else None,
        "mention_address": mention.get("normalized_address"),
        "mention_borough": mention.get("borough"),
        "mention_zip": mention.get("zipcode"),
        "mention_bbl": mention.get("bbl"),
        "n_records": mention.get("n_records"),
    }


def _materialize_properties(conn: duckdb.DuckDBPyConnection) -> None:
    """Canonical dim-ready property table: PLUTO attributes where anchored,
    mention-derived attributes for standalones."""
    conn.execute(
        """
        CREATE OR REPLACE TABLE er.properties AS
        WITH matched AS (
            SELECT property_id,
                   any_value(mention_bbl) AS mention_bbl,
                   any_value(mention_address) AS mention_address,
                   any_value(mention_borough) AS mention_borough,
                   any_value(mention_zip) AS mention_zip,
                   sum(n_records) AS n_source_records,
                   count(*) AS n_mentions
            FROM er.property_matches
            GROUP BY property_id
        )
        SELECT
            m.property_id,
            coalesce(p.bbl, m.mention_bbl) AS bbl,
            coalesce(p.normalized_address, m.mention_address) AS canonical_address,
            coalesce(p.house_number,
                     regexp_extract(m.mention_address, '^([0-9][0-9A-Z-]*)', 1)) AS house_number,
            coalesce(p.street_name, NULL) AS street_name,
            coalesce(p.borough, m.mention_borough) AS borough,
            coalesce(p.zipcode, m.mention_zip) AS zipcode,
            p.latitude, p.longitude,
            p.units_res, p.units_total,
            p.owner_name AS pluto_owner_name,
            p.owner_is_org AS pluto_owner_is_org,
            p.year_built, p.bldg_class,
            (p.bbl IS NOT NULL) AS in_pluto,
            m.n_mentions, m.n_source_records,
            now() AS created_at
        FROM matched m
        LEFT JOIN clean.pluto_lots p ON p.bbl = replace(m.property_id, 'P', '')
        """
    )


def _materialize_record_maps(conn: duckdb.DuckDBPyConnection) -> None:
    """Record-level lineage: every clean record → its property, with evidence."""
    specs = {
        "complaints": ("clean.complaints", "complaint_id",
                       "WHERE c.normalized_address IS NOT NULL OR c.bbl IS NOT NULL"),
        "permits": ("clean.permits", "permit_row_id",
                    "WHERE c.dup_rank = 1 AND (c.normalized_address IS NOT NULL OR c.bbl IS NOT NULL)"),
        "licenses": ("clean.licenses", "license_id",
                     "WHERE c.is_nyc_premises AND (c.normalized_address IS NOT NULL OR c.bbl IS NOT NULL)"),
    }
    for source, (table, pk, where) in specs.items():
        conn.execute(
            f"""
            CREATE OR REPLACE TABLE er.map_{source} AS
            SELECT c.{pk} AS source_record_id,
                   pm.property_id, pm.match_method, pm.match_score
            FROM {table} c
            JOIN er.property_mentions m
              ON m.source = '{source}'
             AND m.house_number IS NOT DISTINCT FROM c.house_number
             AND m.street_name IS NOT DISTINCT FROM c.street_name
             AND m.street_suffix IS NOT DISTINCT FROM c.street_suffix
             AND m.borough IS NOT DISTINCT FROM c.borough
             AND m.zipcode IS NOT DISTINCT FROM c.zipcode
             AND m.bbl IS NOT DISTINCT FROM c.bbl
            JOIN er.property_matches pm ON pm.mention_id = m.mention_id
            {where}
            """
        )
