"""Portfolio grouping: HPD evidence → owner groups (synthetic warehouse)."""

import duckdb
import pandas as pd
import pytest

from entity_resolution.portfolio import build_owner_groups


@pytest.fixture
def conn(tmp_path):
    conn = duckdb.connect(str(tmp_path / "t.duckdb"))
    conn.execute("CREATE SCHEMA clean; CREATE SCHEMA er; CREATE SCHEMA meta;")
    yield conn
    conn.close()


def _seed(conn, registrations, contacts, properties):
    conn.register("_r", pd.DataFrame(registrations))
    conn.execute("CREATE TABLE clean.hpd_registrations AS SELECT * FROM _r")
    conn.register("_c", pd.DataFrame(contacts))
    conn.execute("CREATE TABLE clean.hpd_contacts AS SELECT * FROM _c")
    conn.register("_p", pd.DataFrame(properties))
    conn.execute("CREATE TABLE er.properties AS SELECT * FROM _p")


def test_llc_family_grouped_by_mailing_address(conn):
    # Two sibling LLCs (never name-mergeable) sharing one owner mailing
    # address, plus an unrelated third building.
    _seed(
        conn,
        registrations=[
            {"registration_id": "r1", "bbl": "2021650001"},
            {"registration_id": "r2", "bbl": "2024540001"},
            {"registration_id": "r3", "bbl": "3000010001"},
        ],
        contacts=[
            {"contact_id": "c1", "registration_id": "r1", "contact_type": "CorporateOwner",
             "corporation_name": "PARKASH 2165 LLC", "mailing_key": "9 W 31 ST|NEW YORK|NY|10001"},
            {"contact_id": "c2", "registration_id": "r2", "contact_type": "CorporateOwner",
             "corporation_name": "PARKASH 2454 LLC", "mailing_key": "9 W 31 ST|NEW YORK|NY|10001"},
            {"contact_id": "c3", "registration_id": "r3", "contact_type": "CorporateOwner",
             "corporation_name": "ZENITH HOLDINGS LLC", "mailing_key": "1 MAIN ST|BROOKLYN|NY|11201"},
        ],
        properties=[
            {"property_id": "P2021650001"}, {"property_id": "P2024540001"},
            {"property_id": "P3000010001"},
        ],
    )
    metrics = build_owner_groups(conn)

    groups = dict(
        conn.execute("SELECT property_id, group_id FROM er.property_owner_group").fetchall()
    )
    assert groups["P2021650001"] == groups["P2024540001"]  # LLC family united
    assert groups["P3000010001"] != groups["P2021650001"]
    assert metrics["multi_property_groups"] == 1

    evidence = conn.execute(
        "SELECT edge_type FROM er.owner_group_evidence"
    ).fetchall()
    assert ("mailing_address",) in evidence


def test_same_corporation_name_groups_without_shared_address(conn):
    _seed(
        conn,
        registrations=[
            {"registration_id": "r1", "bbl": "1000010001"},
            {"registration_id": "r2", "bbl": "1000020001"},
        ],
        contacts=[
            {"contact_id": "c1", "registration_id": "r1", "contact_type": "CorporateOwner",
             "corporation_name": "ACME PORTFOLIO LLC", "mailing_key": "A|X|NY|10001"},
            {"contact_id": "c2", "registration_id": "r2", "contact_type": "CorporateOwner",
             "corporation_name": "ACME PORTFOLIO LLC", "mailing_key": "B|Y|NY|10002"},
        ],
        properties=[{"property_id": "P1000010001"}, {"property_id": "P1000020001"}],
    )
    build_owner_groups(conn)
    groups = dict(
        conn.execute("SELECT property_id, group_id FROM er.property_owner_group").fetchall()
    )
    assert groups["P1000010001"] == groups["P1000020001"]


def test_agent_contacts_do_not_group(conn):
    # A registered agent's office must not fuse unrelated portfolios.
    _seed(
        conn,
        registrations=[
            {"registration_id": "r1", "bbl": "1000010001"},
            {"registration_id": "r2", "bbl": "1000020001"},
        ],
        contacts=[
            {"contact_id": "c1", "registration_id": "r1", "contact_type": "Agent",
             "corporation_name": None, "mailing_key": "AGENT OFFICE|NY|NY|10001"},
            {"contact_id": "c2", "registration_id": "r2", "contact_type": "Agent",
             "corporation_name": None, "mailing_key": "AGENT OFFICE|NY|NY|10001"},
        ],
        properties=[{"property_id": "P1000010001"}, {"property_id": "P1000020001"}],
    )
    metrics = build_owner_groups(conn)
    assert metrics["multi_property_groups"] == 0


def test_group_label_is_dominant_corporation(conn):
    _seed(
        conn,
        registrations=[
            {"registration_id": f"r{i}", "bbl": f"100000{i}001"} for i in range(1, 4)
        ],
        contacts=[
            {"contact_id": "c1", "registration_id": "r1", "contact_type": "CorporateOwner",
             "corporation_name": "BIG PORTFOLIO LLC", "mailing_key": "K|X|NY|10001"},
            {"contact_id": "c2", "registration_id": "r2", "contact_type": "CorporateOwner",
             "corporation_name": "BIG PORTFOLIO LLC", "mailing_key": "K|X|NY|10001"},
            {"contact_id": "c3", "registration_id": "r3", "contact_type": "CorporateOwner",
             "corporation_name": "SIDE LLC", "mailing_key": "K|X|NY|10001"},
        ],
        properties=[{"property_id": f"P100000{i}001"} for i in range(1, 4)],
    )
    build_owner_groups(conn)
    label = conn.execute(
        "SELECT group_label FROM er.owner_groups WHERE n_properties = 3"
    ).fetchone()[0]
    assert label == "BIG PORTFOLIO LLC"
