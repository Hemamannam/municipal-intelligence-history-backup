"""Build clean.* tables from raw payloads (one builder per source).

Every builder is a full, idempotent rebuild (CREATE OR REPLACE from the
latest raw versions). At current volumes this costs seconds and keeps the
layer trivially rerunnable; switching to incremental normalization is a
documented scale lever, not a correctness requirement.

Data-quality stance: rows are cleaned, flagged, and *kept*. A complaint
with an unparseable address still counts as a complaint — it just can't
join to a property. Quality rates are measured and stored with the run.
"""

import logging
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

from entity_resolution.address_normalizer import (
    bbl_from_parts,
    from_free_text,
    from_parts,
    normalize_bbl,
    normalize_borough,
)
from entity_resolution.owner_normalizer import (
    is_organization,
    normalize_name,
    normalize_person_lastfirst,
    normalize_person_name,
    normalize_phone,
)
from normalization.io import PipelineRun, latest_payloads, replace_table

logger = logging.getLogger(__name__)

NYC_LAT = (40.4, 41.0)
NYC_LON = (-74.3, -73.6)


def _coords(lat_raw, lon_raw) -> tuple[float | None, float | None]:
    """Validated NYC coordinates or (None, None)."""
    try:
        lat, lon = float(lat_raw), float(lon_raw)
    except (TypeError, ValueError):
        return None, None
    if NYC_LAT[0] <= lat <= NYC_LAT[1] and NYC_LON[0] <= lon <= NYC_LON[1]:
        return lat, lon
    return None, None


def _ts(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _num(value) -> float | None:
    try:
        return float(str(value).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return None


def _int(value) -> int | None:
    number = _num(value)
    return int(number) if number is not None else None


def _addr_fields(addr) -> dict:
    return {
        "house_number": addr.house_number,
        "street_name": addr.street_name,
        "street_suffix": addr.street_suffix,
        "unit": addr.unit,
        "borough": addr.borough,
        "zipcode": addr.zipcode,
        "normalized_address": addr.normalized_address,
        "unit_address": addr.unit_address,
    }


# --- builders ---------------------------------------------------------------


def build_complaints(conn: duckdb.DuckDBPyConnection) -> dict:
    with PipelineRun(conn, "normalize.complaints") as run:
        rows = []
        for p in latest_payloads(conn, "nyc_311"):
            addr = from_free_text(p.get("incident_address"), p.get("borough"), p.get("incident_zip"))
            lat, lon = _coords(p.get("latitude"), p.get("longitude"))
            rows.append(
                {
                    "complaint_id": p["unique_key"],
                    "source_record_id": p["_source_record_id"],
                    "created_date": _ts(p.get("created_date")),
                    "closed_date": _ts(p.get("closed_date")),
                    "status": p.get("status"),
                    "agency": p.get("agency"),
                    "complaint_type": p.get("complaint_type"),
                    "descriptor": p.get("descriptor"),
                    "location_type": p.get("location_type"),
                    "channel": p.get("open_data_channel_type"),
                    "community_board": p.get("community_board"),
                    **_addr_fields(addr),
                    "bbl": normalize_bbl(p.get("bbl")),
                    "latitude": lat,
                    "longitude": lon,
                }
            )
        df = pd.DataFrame(rows)
        run.records_processed = replace_table(conn, "clean", "complaints", df)
        run.metrics = {
            "pct_with_address": round(100.0 * float(df["normalized_address"].notna().mean()), 2),
            "pct_with_bbl": round(100.0 * float(df["bbl"].notna().mean()), 2),
            "pct_with_coords": round(100.0 * float(df["latitude"].notna().mean()), 2),
        }
        return {"table": "clean.complaints", "rows": len(df), **run.metrics}


def build_permits(conn: duckdb.DuckDBPyConnection) -> dict:
    with PipelineRun(conn, "normalize.permits") as run:
        rows = []
        for p in latest_payloads(conn, "dob_permits"):
            addr = from_parts(
                p.get("house_no"), p.get("street_name"), p.get("borough"), p.get("zip_code")
            )
            lat, lon = _coords(p.get("latitude"), p.get("longitude"))
            owner_business = normalize_name(p.get("owner_business_name"))
            owner_person = normalize_person_lastfirst(p.get("owner_name"))
            owner = owner_business or owner_person
            rows.append(
                {
                    "permit_row_id": p["_source_record_id"],
                    "job_filing_number": (p.get("job_filing_number") or "").strip() or None,
                    "work_permit": (p.get("work_permit") or "").strip() or None,
                    "sequence_number": (p.get("sequence_number") or "").strip() or None,
                    "permit_status": p.get("permit_status"),
                    "filing_reason": p.get("filing_reason"),
                    "work_type": p.get("work_type"),
                    "job_description": p.get("job_description"),
                    "estimated_job_cost": _num(p.get("estimated_job_costs")),
                    "issued_date": _ts(p.get("issued_date")),
                    "approved_date": _ts(p.get("approved_date")),
                    "expired_date": _ts(p.get("expired_date")),
                    **_addr_fields(addr),
                    "bin": (p.get("bin") or "").strip() or None,
                    "bbl": normalize_bbl(p.get("bbl"))
                    or bbl_from_parts(p.get("borough"), p.get("block"), p.get("lot")),
                    "owner_name": owner,
                    "owner_is_org": is_organization(p.get("owner_business_name") or p.get("owner_name")),
                    "owner_business_name": owner_business,
                    "owner_person_name": owner_person,
                    "applicant_business_name": normalize_name(p.get("applicant_business_name")),
                    "applicant_person_name": normalize_person_name(
                        p.get("applicant_first_name"), p.get("applicant_last_name")
                    ),
                    "latitude": lat,
                    "longitude": lon,
                }
            )
        df = pd.DataFrame(rows)
        # The source has no reliable natural key and ~15% duplicated rows;
        # rank duplicates on the business key so staging can take rank 1.
        # NULL issued_date groups are ranked too (deterministic via row id).
        df["dup_rank"] = (
            df.sort_values("permit_row_id")
            .groupby(
                [
                    df["job_filing_number"].fillna(""),
                    df["work_permit"].fillna(""),
                    df["sequence_number"].fillna(""),
                    df["issued_date"].astype(str),
                ],
                dropna=False,
            )
            .cumcount()
            + 1
        )
        run.records_processed = replace_table(conn, "clean", "permits", df)
        run.metrics = {
            "duplicate_rate_pct": round(100.0 * float((df["dup_rank"] > 1).mean()), 2),
            "pct_with_address": round(100.0 * float(df["normalized_address"].notna().mean()), 2),
            "pct_with_bbl": round(100.0 * float(df["bbl"].notna().mean()), 2),
            "pct_with_owner": round(100.0 * float(df["owner_name"].notna().mean()), 2),
        }
        return {"table": "clean.permits", "rows": len(df), **run.metrics}


def build_licenses(conn: duckdb.DuckDBPyConnection) -> dict:
    with PipelineRun(conn, "normalize.licenses") as run:
        rows = []
        for p in latest_payloads(conn, "dca_licenses"):
            addr = from_parts(
                p.get("address_building"),
                p.get("address_street_name"),
                p.get("address_borough"),
                p.get("address_zip"),
            )
            lat, lon = _coords(p.get("latitude"), p.get("longitude"))
            rows.append(
                {
                    "license_id": p["_source_record_id"],
                    "business_unique_id": p.get("business_unique_id"),
                    "business_name": normalize_name(p.get("business_name")),
                    "dba_trade_name": normalize_name(p.get("dba_trade_name")),
                    "business_category": p.get("business_category"),
                    "license_type": p.get("license_type"),
                    "license_status": p.get("license_status"),
                    "license_created": _ts(p.get("license_creation_date")),
                    "license_expires": _ts(p.get("lic_expir_dd")),
                    "contact_phone": normalize_phone(p.get("contact_phone")),
                    **_addr_fields(addr),
                    "address_city": (p.get("address_city") or "").strip().upper() or None,
                    "address_state": (p.get("address_state") or "").strip().upper() or None,
                    "is_nyc_premises": normalize_borough(p.get("address_borough")) is not None,
                    "bin": (p.get("bin") or "").strip() or None,
                    "bbl": normalize_bbl(p.get("bbl")),
                    "latitude": lat,
                    "longitude": lon,
                }
            )
        df = pd.DataFrame(rows)
        run.records_processed = replace_table(conn, "clean", "licenses", df)
        run.metrics = {
            "pct_nyc_premises": round(100.0 * float(df["is_nyc_premises"].mean()), 2),
            "pct_with_bbl": round(100.0 * float(df["bbl"].notna().mean()), 2),
            "pct_with_address": round(100.0 * float(df["normalized_address"].notna().mean()), 2),
        }
        return {"table": "clean.licenses", "rows": len(df), **run.metrics}


def build_pluto(conn: duckdb.DuckDBPyConnection) -> dict:
    with PipelineRun(conn, "normalize.pluto") as run:
        rows, bad_bbl = [], 0
        for p in latest_payloads(conn, "pluto"):
            bbl = normalize_bbl(p.get("bbl"))
            if bbl is None:
                bad_bbl += 1
                continue
            addr = from_free_text(p.get("address"), p.get("borough"), p.get("zipcode"))
            lat, lon = _coords(p.get("latitude"), p.get("longitude"))
            owner_raw = p.get("ownername")
            rows.append(
                {
                    "bbl": bbl,
                    "source_record_id": p["_source_record_id"],
                    **_addr_fields(addr),
                    "units_res": _int(p.get("unitsres")),
                    "units_total": _int(p.get("unitstotal")),
                    "owner_name": normalize_person_lastfirst(owner_raw),
                    "owner_is_org": is_organization(owner_raw),
                    "year_built": _int(p.get("yearbuilt")),
                    "bldg_class": p.get("bldgclass"),
                    "latitude": lat,
                    "longitude": lon,
                }
            )
        df = pd.DataFrame(rows).drop_duplicates(subset=["bbl"], keep="first")
        run.records_processed = replace_table(conn, "clean", "pluto_lots", df)
        run.records_failed = bad_bbl
        run.metrics = {
            "invalid_bbl_rows": bad_bbl,
            "pct_with_owner": round(100.0 * float(df["owner_name"].notna().mean()), 2),
            "pct_with_address": round(100.0 * float(df["normalized_address"].notna().mean()), 2),
        }
        return {"table": "clean.pluto_lots", "rows": len(df), **run.metrics}


def build_hpd(conn: duckdb.DuckDBPyConnection) -> dict:
    """HPD registrations + contacts (portfolio-grouping fuel)."""
    with PipelineRun(conn, "normalize.hpd") as run:
        regs = []
        for p in latest_payloads(conn, "hpd_registrations"):
            regs.append(
                {
                    "registration_id": p["_source_record_id"],
                    "building_id": p.get("buildingid"),
                    "bbl": bbl_from_parts(p.get("boro"), p.get("block"), p.get("lot")),
                    "bin": (p.get("bin") or "").strip() or None,
                    "borough": normalize_borough(p.get("boro")),
                    "last_registration_date": _ts(p.get("lastregistrationdate")),
                    "registration_end_date": _ts(p.get("registrationenddate")),
                }
            )
        regs_df = pd.DataFrame(regs)

        contacts = []
        for p in latest_payloads(conn, "hpd_contacts"):
            mailing = from_parts(
                p.get("businesshousenumber"), p.get("businessstreetname"),
                None, p.get("businesszip"),
            )
            city = (p.get("businesscity") or "").strip().upper() or None
            state = (p.get("businessstate") or "").strip().upper() or None
            mailing_key = (
                f"{mailing.normalized_address}|{city}|{state}|{mailing.zipcode}"
                if mailing.normalized_address and (mailing.zipcode or city)
                else None
            )
            contacts.append(
                {
                    "contact_id": p["_source_record_id"],
                    "registration_id": (p.get("registrationid") or "").strip() or None,
                    "contact_type": p.get("type"),
                    "corporation_name": normalize_name(p.get("corporationname")),
                    "person_name": normalize_person_name(p.get("firstname"), p.get("lastname")),
                    "mailing_address": mailing.normalized_address,
                    "mailing_city": city,
                    "mailing_state": state,
                    "mailing_zip": mailing.zipcode,
                    "mailing_key": mailing_key,
                }
            )
        contacts_df = pd.DataFrame(contacts)

        n = replace_table(conn, "clean", "hpd_registrations", regs_df)
        n += replace_table(conn, "clean", "hpd_contacts", contacts_df)
        run.records_processed = n
        run.metrics = {
            "registrations": len(regs_df),
            "contacts": len(contacts_df),
            "pct_regs_with_bbl": round(100.0 * float(regs_df["bbl"].notna().mean()), 2),
            "pct_contacts_with_mailing_key": round(
                100.0 * float(contacts_df["mailing_key"].notna().mean()), 2
            ),
        }
        return {"table": "clean.hpd_*", "rows": n, **run.metrics}


BUILDERS = {
    "complaints": build_complaints,
    "permits": build_permits,
    "licenses": build_licenses,
    "pluto": build_pluto,
    "hpd": build_hpd,
}


def run_all(db_path: Path | str, only: list[str] | None = None) -> list[dict]:
    conn = duckdb.connect(str(db_path))
    results = []
    try:
        for name, builder in BUILDERS.items():
            if only and name not in only:
                continue
            try:
                result = builder(conn)
            except duckdb.CatalogException as exc:
                # Source not ingested locally yet — skip loudly, not fatally.
                logger.warning("normalize_skipped", extra={"builder": name, "reason": str(exc)})
                continue
            logger.info("normalized", extra=result)
            results.append(result)
    finally:
        conn.close()
    return results
