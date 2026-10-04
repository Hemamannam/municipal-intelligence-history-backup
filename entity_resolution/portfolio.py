"""Portfolio grouping: which properties are managed together?

Built for the customer's follow-up requirement (customer_requests/):
per-building LLCs make owner names unreliable for portfolio analysis —
"PARKASH 2165 LLC" and "PARKASH 2454 LLC" are different legal entities and
different `dim_owner` rows, yet one operation manages both buildings.

HPD registration data resolves this the way the city itself does:
1. Registrations attach to properties via BBL (deterministic — our
   property IDs are BBL-derived, so the join is exact).
2. Two properties belong to the same PORTFOLIO GROUP when their
   registrations share:
     - the same corporate-owner name (edge: ``corp_name``), or
     - the same owner/officer business MAILING ADDRESS
       (edge: ``mailing_address``; Agent contacts are excluded — a
       registered agent's office manages thousands of unrelated
       buildings).
3. Mailing-address keys touching more than ``max_group_fanout``
   registrations are skipped and counted: those are service companies,
   not landlords (measured, logged, never silent).

Output preserves evidence per edge so a grouped pair can always be
explained (Phase 14).
"""

import hashlib
import logging

import duckdb
import pandas as pd

from entity_resolution.matcher import UnionFind
from normalization.io import PipelineRun, replace_table

logger = logging.getLogger(__name__)

# Contact types that represent the ownership/management side.
OWNER_CONTACT_TYPES = (
    "CorporateOwner", "IndividualOwner", "HeadOfficer", "Officer", "JointOwner",
    "SiteManager",
)
# Mailing-address edges are restricted to *owners*: measured on the full
# build, officer/manager mailing addresses (shared professional offices)
# chained transitively into a 5,931-property mega-group spanning 3,782
# distinct owner names. Owner-only edges keep the LLC-family signal
# without fusing portfolios through their shared management offices.
MAILING_EDGE_TYPES = ("CorporateOwner", "IndividualOwner", "JointOwner")
MAX_GROUP_FANOUT = 200          # corp-name keys
MAX_MAILING_FANOUT = 100        # mailing keys (service offices sit above this)


PROPERTY_CONTACTS_SQL = f"""
    SELECT
        'P' || r.bbl AS property_id,
        c.contact_type,
        c.corporation_name,
        c.mailing_key
    FROM clean.hpd_registrations r
    JOIN clean.hpd_contacts c ON c.registration_id = r.registration_id
    JOIN er.properties p ON p.property_id = 'P' || r.bbl
    WHERE r.bbl IS NOT NULL
      AND c.contact_type IN {OWNER_CONTACT_TYPES}
"""


def build_owner_groups(conn: duckdb.DuckDBPyConnection) -> dict:
    with PipelineRun(conn, "er.owner_groups") as run:
        rows = conn.execute(PROPERTY_CONTACTS_SQL).fetchdf()
        rows = rows.astype(object).where(pd.notna(rows), None)

        uf = UnionFind()
        evidence: list[dict] = []
        skipped_keys = 0

        for kind, column in (("corp_name", "corporation_name"), ("mailing_address", "mailing_key")):
            if kind == "mailing_address":
                pool = rows[rows["contact_type"].isin(MAILING_EDGE_TYPES)]
                fanout_cap = MAX_MAILING_FANOUT
            else:
                pool = rows
                fanout_cap = MAX_GROUP_FANOUT
            groups = (
                pool.dropna(subset=[column])
                .groupby(column)["property_id"]
                .unique()
            )
            for key, props in groups.items():
                props = sorted(set(props))
                if len(props) < 2:
                    continue
                if len(props) > fanout_cap:
                    skipped_keys += 1
                    logger.warning(
                        "portfolio_key_skipped",
                        extra={"edge": kind, "key": str(key)[:60], "fanout": len(props)},
                    )
                    continue
                anchor = props[0]
                for other in props[1:]:
                    uf.union(anchor, other)
                    evidence.append(
                        {"property_a": anchor, "property_b": other,
                         "edge_type": kind, "edge_key": str(key)[:120]}
                    )

        all_props = sorted(set(rows["property_id"].dropna())) if len(rows) else []
        assignments = []
        roots: dict[str, str] = {}
        for prop in all_props:
            root = uf.find(prop)
            if root not in roots:
                roots[root] = "G" + hashlib.sha1(root.encode()).hexdigest()[:10]
            assignments.append({"property_id": prop, "group_id": roots[root]})
        assign_df = pd.DataFrame(assignments, columns=["property_id", "group_id"])

        # Group label: most common corporation name inside the group.
        labeled = rows.dropna(subset=["corporation_name"]).merge(assign_df, on="property_id")
        if len(labeled):
            labels = (
                labeled.groupby("group_id")["corporation_name"]
                .agg(lambda s: s.value_counts().idxmax())
                .rename("group_label")
                .reset_index()
            )
        else:
            labels = pd.DataFrame(columns=["group_id", "group_label"])
        groups_df = (
            assign_df.groupby("group_id").size().rename("n_properties").reset_index()
            .merge(labels, on="group_id", how="left")
            if len(assign_df)
            else pd.DataFrame(columns=["group_id", "n_properties", "group_label"])
        )

        replace_table(conn, "er", "property_owner_group", assign_df)
        replace_table(conn, "er", "owner_groups", groups_df)
        replace_table(
            conn, "er", "owner_group_evidence",
            pd.DataFrame(evidence, columns=["property_a", "property_b", "edge_type", "edge_key"]),
        )

        run.records_processed = len(assign_df)
        run.metrics = {
            "properties_with_hpd": len(all_props),
            "groups": len(groups_df),
            "multi_property_groups": int((groups_df["n_properties"] > 1).sum()),
            "largest_group": int(groups_df["n_properties"].max()) if len(groups_df) else 0,
            "evidence_edges": len(evidence),
            "high_fanout_keys_skipped": skipped_keys,
        }
        logger.info("owner_groups_done", extra=run.metrics)
        return run.metrics
