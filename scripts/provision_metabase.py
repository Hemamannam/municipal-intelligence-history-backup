#!/usr/bin/env python3
"""Provision Metabase end-to-end via its REST API (idempotent).

Creates: admin user (first run), the Postgres data source, and two
dashboards — "City Operations Overview" (7 panels, borough/ZIP filters)
and "Pipeline Health" (observability). Cards are prefixed "[MIP]" and
recreated on each run, so the script is safe to re-run after publishes.

Requires: docker compose up postgres metabase; scripts/publish_postgres.py.
"""

import os
import sys
import time
import uuid

import requests

BASE = os.environ.get("METABASE_URL", "http://localhost:3000")
ADMIN_EMAIL = os.environ.get("METABASE_ADMIN_EMAIL", "admin@mip.local")
ADMIN_PASSWORD = os.environ.get("METABASE_ADMIN_PASSWORD", "MipLocal-Dev1")
PG = {
    "host": "postgres",  # metabase reaches postgres via the compose network
    "port": 5432,
    "dbname": os.environ.get("PG_DB", "mip"),
    "user": os.environ.get("PG_USER", "mip"),
    "password": os.environ.get("PG_PASSWORD", "mip_local_dev"),
}

BOROUGH_TAG = {
    "id": str(uuid.uuid4()), "name": "borough", "display-name": "Borough", "type": "text"
}
ZIP_TAG = {"id": str(uuid.uuid4()), "name": "zip", "display-name": "ZIP", "type": "text"}


def wait_healthy(timeout: int = 180) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(f"{BASE}/api/health", timeout=5).json().get("status") == "ok":
                return
        except requests.RequestException:
            pass
        time.sleep(3)
    raise RuntimeError("Metabase did not become healthy in time")


def get_session() -> str:
    props = requests.get(f"{BASE}/api/session/properties", timeout=10).json()
    token = props.get("setup-token")
    if token:
        resp = requests.post(
            f"{BASE}/api/setup",
            json={
                "token": token,
                "user": {
                    "first_name": "MIP", "last_name": "Admin",
                    "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD,
                },
                "prefs": {"site_name": "Municipal Intelligence", "allow_tracking": False},
            },
            timeout=30,
        )
        # Metabase can keep advertising a stale setup-token after setup
        # has completed; fall through to a normal login in that case.
        if resp.status_code < 400:
            return resp.json()["id"]
    resp = requests.post(
        f"{BASE}/api/session",
        json={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


class MB:
    def __init__(self, session_id: str):
        self.headers = {"X-Metabase-Session": session_id}

    def req(self, method: str, path: str, **kwargs):
        resp = requests.request(
            method, f"{BASE}{path}", headers=self.headers, timeout=60, **kwargs
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"{method} {path} -> {resp.status_code}: {resp.text[:300]}")
        return resp.json() if resp.text else None

    def ensure_database(self) -> int:
        for db in self.req("GET", "/api/database")["data"]:
            if db["name"] == "MIP Warehouse":
                return db["id"]
        db = self.req(
            "POST", "/api/database",
            json={"engine": "postgres", "name": "MIP Warehouse",
                  "details": {**PG, "ssl": False}},
        )
        return db["id"]

    def delete_existing(self) -> None:
        for card in self.req("GET", "/api/card"):
            if card["name"].startswith("[MIP]"):
                self.req("DELETE", f"/api/card/{card['id']}")
        for dash in self.req("GET", "/api/dashboard"):
            if dash["name"].startswith("[MIP]"):
                self.req("DELETE", f"/api/dashboard/{dash['id']}")

    def card(self, name: str, db_id: int, sql: str, display: str = "table",
             tags: dict | None = None, viz: dict | None = None) -> int:
        payload = {
            "name": f"[MIP] {name}",
            "display": display,
            "visualization_settings": viz or {},
            "dataset_query": {
                "type": "native",
                "database": db_id,
                "native": {"query": sql, "template-tags": tags or {}},
            },
        }
        return self.req("POST", "/api/card", json=payload)["id"]

    def dashboard(self, name: str, dashcards: list, parameters: list | None = None) -> int:
        dash = self.req("POST", "/api/dashboard", json={"name": f"[MIP] {name}"})
        self.req(
            "PUT", f"/api/dashboard/{dash['id']}",
            json={"dashcards": dashcards, "parameters": parameters or []},
        )
        return dash["id"]


def overview_cards(mb: MB, db: int) -> list:
    """Build the City Operations Overview cards; returns dashcards layout."""
    borough_filter = "[[WHERE borough = {{borough}}]]"
    scalar = [
        ("Resolved properties", "select count(*) from marts.dim_property"),
        ("Complaints (12m)",
         "select count(*) from marts.fct_complaints"
         " where created_date >= current_date - interval '365 day'"),
        ("Canonical owners", "select count(*) from marts.dim_owner"),
        ("Canonical businesses", "select count(*) from marts.dim_business"),
    ]
    cards = [mb.card(n, db, q, display="scalar") for n, q in scalar]

    match_quality = mb.card(
        "Entity match confidence", db,
        "select match_method, count(*) as records from marts.bridge_property_source"
        " group by 1 order by 2 desc",
        display="bar",
        viz={"graph.dimensions": ["match_method"], "graph.metrics": ["records"]},
    )
    by_borough = mb.card(
        "Complaints by borough (12m)", db,
        "select borough, count(*) as complaints from marts.fct_complaints"
        " where created_date >= current_date - interval '365 day'"
        " and borough is not null group by 1 order by 2 desc",
        display="bar",
        viz={"graph.dimensions": ["borough"], "graph.metrics": ["complaints"]},
    )
    top_landlords = mb.card(
        "Top landlords by complaints per unit (12m)", db,
        "select canonical_owner_name, n_properties, total_units_res, complaints_12m,"
        " round(complaints_per_unit_12m::numeric, 2) as complaints_per_unit,"
        " operational_risk_score"
        " from marts.mart_landlord_performance where in_scoring_pool"
        " order by complaints_per_unit_12m desc limit 15",
    )
    risk_properties = mb.card(
        "Highest-priority properties", db,
        "select canonical_address, borough, zipcode, units_res, complaints_12m,"
        " complaints_open, permits_12m, round(complaints_per_unit_12m::numeric,2) as cpu"
        f" from marts.mart_property_risk {borough_filter}"
        " order by complaints_12m desc limit 15",
        tags={"borough": BOROUGH_TAG},
    )
    construction = mb.card(
        "Construction vs complaints by neighborhood", db,
        # Postgres sorts NULLs first under DESC (DuckDB: last), so filter them
        # out explicitly; the units floor drops PO-box/out-of-city ZIPs.
        "select zipcode, borough, complaints_per_1k_units_12m,"
        " permits_per_1k_properties_12m from (select * from"
        " marts.mart_neighborhood_operations"
        " where complaints_per_1k_units_12m is not null and units_res >= 500) n"
        f" {borough_filter} order by complaints_per_1k_units_12m desc",
        display="scatter",
        tags={"borough": BOROUGH_TAG},
        viz={"graph.dimensions": ["permits_per_1k_properties_12m"],
             "graph.metrics": ["complaints_per_1k_units_12m"]},
    )

    def dc(card_id, row, col, sx, sy, with_borough=False):
        entry = {"id": -card_id, "card_id": card_id, "row": row, "col": col,
                 "size_x": sx, "size_y": sy, "parameter_mappings": []}
        if with_borough:
            entry["parameter_mappings"] = [{
                "parameter_id": "boroughp", "card_id": card_id,
                "target": ["variable", ["template-tag", "borough"]],
            }]
        return entry

    return [
        dc(cards[0], 0, 0, 6, 3), dc(cards[1], 0, 6, 6, 3),
        dc(cards[2], 0, 12, 6, 3), dc(cards[3], 0, 18, 6, 3),
        dc(match_quality, 3, 0, 12, 6), dc(by_borough, 3, 12, 12, 6),
        dc(top_landlords, 9, 0, 24, 7),
        dc(risk_properties, 16, 0, 24, 7, with_borough=True),
        dc(construction, 23, 0, 24, 8, with_borough=True),
    ]


def health_cards(mb: MB, db: int) -> list:
    ingest = mb.card(
        "Ingest runs (recent)", db,
        "select source, mode, status, rows_received, rows_inserted, rows_rejected,"
        " started_at, finished_at from meta.ingest_runs order by started_at desc limit 20",
    )
    pipeline = mb.card(
        "Pipeline runs (recent)", db,
        "select pipeline_name, status, records_processed, records_failed,"
        " duration_seconds, started_at, metrics from meta.pipeline_runs"
        " order by started_at desc limit 20",
    )
    rejected = mb.card(
        "Dead-letter records", db,
        "select count(*) as rejected_records from meta.rejected_records",
        display="scalar",
    )
    review = mb.card(
        "Review queues", db,
        "select 'property' as queue, count(*) as pairs from er.review_queue"
        " union all select 'owner', count(*) from er.owner_review_queue"
        " union all select 'business', count(*) from er.business_review_queue",
        display="bar",
        viz={"graph.dimensions": ["queue"], "graph.metrics": ["pairs"]},
    )
    freshness = mb.card(
        "Source freshness", db,
        "select source, max(finished_at) as last_success from meta.ingest_runs"
        " where status = 'success' group by 1",
    )
    return [
        {"id": -ingest, "card_id": ingest, "row": 0, "col": 0, "size_x": 24, "size_y": 6},
        {"id": -pipeline, "card_id": pipeline, "row": 6, "col": 0, "size_x": 24, "size_y": 6},
        {"id": -rejected, "card_id": rejected, "row": 12, "col": 0, "size_x": 6, "size_y": 4},
        {"id": -review, "card_id": review, "row": 12, "col": 6, "size_x": 9, "size_y": 4},
        {"id": -freshness, "card_id": freshness, "row": 12, "col": 15, "size_x": 9, "size_y": 4},
    ]


def main() -> int:
    wait_healthy()
    mb = MB(get_session())
    db = mb.ensure_database()
    mb.delete_existing()

    overview = mb.dashboard(
        "City Operations Overview",
        overview_cards(mb, db),
        parameters=[{
            "id": "boroughp", "name": "Borough", "slug": "borough", "type": "string/=",
        }],
    )
    health = mb.dashboard("Pipeline Health", health_cards(mb, db))
    print(f"dashboards ready: {BASE}/dashboard/{overview} and {BASE}/dashboard/{health}")
    print(f"login: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
