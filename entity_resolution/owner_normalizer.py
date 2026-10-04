"""Owner / business name normalization.

Turns naming variants into comparable keys:

    "ACME PROPERTY LLC" / "Acme Properties, L.L.C." → "ACME PROPERTIES LLC"-ish
    (exact equality is NOT the goal here — the matcher applies fuzzy
    similarity on top; this module just removes noise that would otherwise
    dominate the string distance: punctuation, legal-suffix spellings,
    case, whitespace)

    "RODRIGUEZ, JOSE R" (PLUTO) / first="JOSE" last="RODRIGUEZ" (permits)
    → "JOSE RODRIGUEZ" / "JOSE R RODRIGUEZ"

Also classifies a name as person vs organization — matching a person to an
LLC is a different (weaker) signal than LLC-to-LLC.
"""

import re
from functools import lru_cache

_PUNCT_RE = re.compile(r"[.,;:'\"/\\()&#!?*]")
_WS_RE = re.compile(r"\s+")

# Values that mean "no name" in municipal data.
_NULL_NAMES = {
    "", "N/A", "NA", "NONE", "UNKNOWN", "NOT APPLICABLE", "SAME", "OWNER",
    "TBD", "XX", "X", "-", "--", ".", "NULL", "NO NAME", "NOT AVAILABLE",
    # PLUTO placeholder that aggregated 2,403 unrelated properties under
    # one "owner" before this entry.
    "UNAVAILABLE OWNER", "UNAVAILABLE", "NAME UNAVAILABLE", "OWNER UNAVAILABLE",
}

# Legal-form token → canonical spelling. Applied token-wise after
# punctuation stripping, so "L.L.C." → "LLC" and "L L C" → "LLC".
_LEGAL_FORMS = {
    "LLC": "LLC", "L L C": "LLC", "LC": "LLC", "PLLC": "LLC",
    "INC": "INC", "INCORPORATED": "INC",
    "CORP": "CORP", "CORPORATION": "CORP",
    "CO": "CO", "COMPANY": "CO",
    "LTD": "LTD", "LIMITED": "LTD",
    "LP": "LP", "L P": "LP",
    "LLP": "LLP",
    "HDFC": "HDFC",  # Housing Development Fund Corporation — common in NYC
    "ASSOC": "ASSOCIATES", "ASSOCIATES": "ASSOCIATES", "ASSOCS": "ASSOCIATES",
    "MGMT": "MANAGEMENT", "MANAGEMENT": "MANAGEMENT", "MGT": "MANAGEMENT",
    "RLTY": "REALTY", "REALTY": "REALTY",
    "PROP": "PROPERTIES", "PROPS": "PROPERTIES", "PROPERTY": "PROPERTIES",
    "PROPERTIES": "PROPERTIES",
    "DEV": "DEVELOPMENT", "DEVELOPMENT": "DEVELOPMENT",
    "BLDG": "BUILDING", "BUILDING": "BUILDING", "BLDGS": "BUILDINGS",
    "APTS": "APARTMENTS", "APARTMENTS": "APARTMENTS",
    "GRP": "GROUP", "GROUP": "GROUP",
    # Street-word and NYC-specific expansions seen in org names.
    "HWY": "HIGHWAY", "PKWY": "PARKWAY", "BLVD": "BOULEVARD", "AVE": "AVENUE",
    "NYC": "NEW YORK CITY",
}

_ORG_MARKERS = {
    "LLC", "INC", "CORP", "CO", "LTD", "LP", "LLP", "HDFC", "TRUST",
    "ASSOCIATES", "MANAGEMENT", "REALTY", "PROPERTIES", "DEVELOPMENT",
    "GROUP", "PARTNERS", "HOLDINGS", "EQUITIES", "VENTURES", "ENTERPRISES",
    "CHURCH", "CITY", "AUTHORITY", "HOUSING", "CENTER", "HOSPITAL",
    "UNIVERSITY", "SCHOOL", "BANK", "FUND", "ESTATES", "ESTATE", "APARTMENTS",
    "CONDOMINIUM", "CONDO", "COOPERATIVE", "COOP", "OWNERS", "TENANTS",
}


@lru_cache(maxsize=200_000)
def normalize_name(raw: str | None) -> str | None:
    """Canonical comparable form of a person or organization name."""
    if raw is None:
        return None
    upper = str(raw).upper().strip()
    if upper in _NULL_NAMES:  # check before punctuation strip ("N/A")...
        return None
    text = _PUNCT_RE.sub(" ", upper)
    text = _WS_RE.sub(" ", text).strip()
    if text in _NULL_NAMES or text in {"N A", "NO NAME"}:  # ...and after
        return None
    # 1-2 character "names" are truncation garbage, not identities: a
    # single 'PR' owner name aggregated 8,021 unrelated properties before
    # this guard.
    if len(text) <= 2:
        return None
    # "LAST, FIRST" was flattened by punctuation strip; PLUTO-style commas
    # are handled by normalize_person_lastfirst before reaching here.
    tokens = [_LEGAL_FORMS.get(t, t) for t in text.split()]
    # Collapse single-letter legal spellings that survived: "L L C" case.
    joined = " ".join(tokens)
    joined = re.sub(r"\bL L C\b", "LLC", joined)
    joined = re.sub(r"\bL P\b", "LP", joined)
    return joined or None


def normalize_person_name(
    first: str | None, last: str | None, middle: str | None = None
) -> str | None:
    """Assemble 'FIRST [MIDDLE] LAST' from split fields.

    The middle part bypasses the short-garbage guard: a single-letter
    middle initial is legitimate in a way a single-letter *name* is not.
    """
    first_n, last_n = normalize_name(first), normalize_name(last)
    middle_n = None
    if middle:
        cleaned = _WS_RE.sub(" ", _PUNCT_RE.sub(" ", str(middle).upper())).strip()
        if cleaned and cleaned not in _NULL_NAMES and cleaned != "N A":
            middle_n = cleaned
    parts = [p for p in (first_n, middle_n, last_n) if p]
    return " ".join(parts) if parts else None


def normalize_person_lastfirst(raw: str | None) -> str | None:
    """PLUTO-style 'RODRIGUEZ, JOSE R' → 'JOSE R RODRIGUEZ'.

    Only reorders when there is exactly one comma and the result looks like
    a person (no org markers); otherwise falls through to normalize_name.
    """
    if raw is None or "," not in str(raw):
        return normalize_name(raw)
    left, right = str(raw).split(",", 1)
    reordered = f"{right.strip()} {left.strip()}"
    if is_organization(raw):
        return normalize_name(raw)
    return normalize_name(reordered)


@lru_cache(maxsize=200_000)
def is_organization(raw: str | None) -> bool:
    name = normalize_name(raw)
    if not name:
        return False
    tokens = set(name.split())
    if tokens & _ORG_MARKERS:
        return True
    return any(ch.isdigit() for ch in name)  # "123 MAIN ST LLC"-style holdcos


def normalize_phone(raw: str | None) -> str | None:
    """10-digit US phone or None."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10 or digits == "0" * 10:
        return None
    return digits
