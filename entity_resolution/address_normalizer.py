"""Address normalization: messy municipal address strings → comparable parts.

Turns variants like ``"123 W. 42nd St Apt 4B"`` and ``"123 WEST 42 STREET
#4B"`` into one comparable representation:

    house_number="123", street_name="WEST 42", street_suffix="STREET",
    unit="4B", normalized_address="123 WEST 42 STREET",
    unit_address="123 WEST 42 STREET UNIT 4B"

Both property-level (``normalized_address``) and unit-level
(``unit_address``) forms are kept: building-level analytics must not split
one building into per-apartment entities, while unit-level lineage must not
be thrown away.

Parsing strategy: ``usaddress`` (a CRF model trained on US addresses) does
the heavy lifting for free-form strings; a deterministic rule layer then
canonicalizes what it produces (directionals, suffixes, ordinals). When
usaddress fails (RepeatedLabelError on garbage input) a regex fallback
extracts the leading house number and treats the rest as street text.
Results are memoized — municipal data repeats the same address thousands of
times, so the cache converts a per-row CRF call into a dict lookup.
"""

import re
from dataclasses import dataclass
from functools import lru_cache

import usaddress

# --- canonical vocabularies -------------------------------------------------

DIRECTIONALS = {
    "N": "NORTH", "S": "SOUTH", "E": "EAST", "W": "WEST",
    "NE": "NORTHEAST", "NW": "NORTHWEST", "SE": "SOUTHEAST", "SW": "SOUTHWEST",
    "NO": "NORTH", "SO": "SOUTH",
}

SUFFIXES = {
    "ST": "STREET", "STR": "STREET", "STREET": "STREET", "STREETS": "STREET",
    "AVE": "AVENUE", "AV": "AVENUE", "AVENUE": "AVENUE",
    "BLVD": "BOULEVARD", "BLV": "BOULEVARD", "BOULEVARD": "BOULEVARD",
    "RD": "ROAD", "ROAD": "ROAD",
    "PL": "PLACE", "PLACE": "PLACE",
    "DR": "DRIVE", "DRIVE": "DRIVE",
    "CT": "COURT", "COURT": "COURT",
    "LN": "LANE", "LANE": "LANE",
    "PKWY": "PARKWAY", "PKY": "PARKWAY", "PARKWAY": "PARKWAY",
    "TER": "TERRACE", "TERR": "TERRACE", "TERRACE": "TERRACE",
    "HWY": "HIGHWAY", "HIGHWAY": "HIGHWAY",
    "EXPY": "EXPRESSWAY", "EXPWY": "EXPRESSWAY", "EXPRESSWAY": "EXPRESSWAY",
    "SQ": "SQUARE", "SQUARE": "SQUARE",
    "CIR": "CIRCLE", "CIRCLE": "CIRCLE",
    "CRES": "CRESCENT", "CRESCENT": "CRESCENT",
    "WAY": "WAY",
    "PLZ": "PLAZA", "PLAZA": "PLAZA",
    "BCH": "BEACH", "BEACH": "BEACH",
    "CONC": "CONCOURSE", "CONCOURSE": "CONCOURSE",
    "WALK": "WALK",
    "ALY": "ALLEY", "ALLEY": "ALLEY",
    "BRG": "BRIDGE", "BRIDGE": "BRIDGE",
    "LOOP": "LOOP",
    "OVAL": "OVAL",
    "ROW": "ROW",
    "SLIP": "SLIP",
    "TPKE": "TURNPIKE", "TURNPIKE": "TURNPIKE",
}

BOROUGHS = {
    "MANHATTAN": "MANHATTAN", "MN": "MANHATTAN", "1": "MANHATTAN", "NEW YORK": "MANHATTAN",
    "BRONX": "BRONX", "THE BRONX": "BRONX", "BX": "BRONX", "2": "BRONX",
    "BROOKLYN": "BROOKLYN", "BK": "BROOKLYN", "KINGS": "BROOKLYN", "3": "BROOKLYN",
    "QUEENS": "QUEENS", "QN": "QUEENS", "QNS": "QUEENS", "4": "QUEENS",
    "STATEN ISLAND": "STATEN ISLAND", "SI": "STATEN ISLAND", "STATEN IS": "STATEN ISLAND",
    "RICHMOND": "STATEN ISLAND", "5": "STATEN ISLAND",
}

BOROUGH_CODES = {"MANHATTAN": "1", "BRONX": "2", "BROOKLYN": "3", "QUEENS": "4", "STATEN ISLAND": "5"}

_ORDINAL_RE = re.compile(r"\b(\d+)(?:ST|ND|RD|TH)\b")
_UNIT_LABELS = {"APT", "APARTMENT", "UNIT", "STE", "SUITE", "RM", "ROOM", "FL", "FLOOR", "#", "PH"}
_HOUSE_RE = re.compile(r"^\s*(\d+[A-Z]?(?:-\d+[A-Z]?)?)\s+(.*)$")
_PUNCT_RE = re.compile(r"[.,;:'\"()]")
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class NormalizedAddress:
    house_number: str | None = None
    street_name: str | None = None       # canonicalized, without suffix: "WEST 42"
    street_suffix: str | None = None     # canonical: "STREET"
    unit: str | None = None
    borough: str | None = None
    zipcode: str | None = None

    @property
    def full_street(self) -> str | None:
        """Street with suffix: 'WEST 42 STREET'."""
        if not self.street_name:
            return None
        return f"{self.street_name} {self.street_suffix}" if self.street_suffix else self.street_name

    @property
    def normalized_address(self) -> str | None:
        """Property-level address: '123 WEST 42 STREET' (no unit)."""
        street = self.full_street
        if not street:
            return None
        return f"{self.house_number} {street}" if self.house_number else street

    @property
    def unit_address(self) -> str | None:
        """Unit-level address; equals normalized_address when no unit."""
        base = self.normalized_address
        if base and self.unit:
            return f"{base} UNIT {self.unit}"
        return base


def normalize_borough(value: str | None) -> str | None:
    if not value:
        return None
    return BOROUGHS.get(_WS_RE.sub(" ", str(value).strip().upper()))


def normalize_zip(value: str | None) -> str | None:
    if not value:
        return None
    match = re.match(r"^\s*(\d{5})(?:-\d{4})?\s*$", str(value))
    if not match or match.group(1) == "00000":
        return None
    return match.group(1)


def normalize_bbl(value: str | float | None) -> str | None:
    """Canonical 10-digit BBL (borough 1-5, block 5, lot 4).

    Accepts PLUTO's decimal strings ('2054800111.00000000') and plain forms.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "." in text:
        text = text.split(".", 1)[0]
    if not re.fullmatch(r"\d{10}", text):
        return None
    if text[0] not in "12345" or text.endswith("000000000"):
        return None
    return text


def bbl_from_parts(borough: str | None, block: str | None, lot: str | None) -> str | None:
    """Assemble a BBL from borough name + block + lot strings."""
    code = BOROUGH_CODES.get(normalize_borough(borough) or "")
    try:
        block_i, lot_i = int(str(block)), int(str(lot))
    except (TypeError, ValueError):
        return None
    if not code or block_i <= 0 or lot_i <= 0:
        return None
    return f"{code}{block_i:05d}{lot_i:04d}"


def _canonicalize_street_tokens(tokens: list[str]) -> tuple[str | None, str | None]:
    """Expand directionals, strip ordinals, split off a trailing suffix."""
    out: list[str] = []
    for i, token in enumerate(tokens):
        token = _ORDINAL_RE.sub(r"\1", token)
        # Expand a directional only at the start, or immediately before the
        # end (e.g. 'AVENUE W' stays: a lone trailing W after a suffix is a
        # street letter, not a direction — handled by position check).
        if token in DIRECTIONALS and i == 0 and len(tokens) > 1:
            token = DIRECTIONALS[token]
        out.append(token)
    suffix = None
    if len(out) >= 2 and out[-1] in SUFFIXES:
        suffix = SUFFIXES[out[-1]]
        out = out[:-1]
    name = " ".join(out).strip() or None
    return name, suffix


def _clean(text: str) -> str:
    text = _PUNCT_RE.sub(" ", text.upper())
    text = text.replace("#", " # ")
    return _WS_RE.sub(" ", text).strip()


def _extract_unit(tokens: list[str]) -> tuple[list[str], str | None]:
    """Pull 'APT 4B' / '# 4B' / 'UNIT 4B' off a token list."""
    for i, token in enumerate(tokens):
        if token in _UNIT_LABELS and i + 1 < len(tokens):
            return tokens[:i], " ".join(tokens[i + 1 :]) or None
        if token in _UNIT_LABELS and i + 1 == len(tokens):
            return tokens[:i], None
    return tokens, None


# Fast-path eligibility: "<house> <street tokens>" with no unit markers or
# digits-with-letters oddities. Municipal data is dominated by this shape;
# the CRF (usaddress) costs ~2ms/call, the regex path ~2µs — a 1000x
# difference that matters at PLUTO's 850K mostly-unique addresses.
_SIMPLE_RE = re.compile(r"^(\d+[A-Z]?(?:-\d+[A-Z]?)?) ([A-Z0-9 ]+)$")


@lru_cache(maxsize=200_000)
def parse_free_address(text: str | None) -> NormalizedAddress:
    """Parse a free-form address string ('123 W. 42nd St Apt 4B')."""
    if not text or not str(text).strip():
        return NormalizedAddress()
    cleaned = _clean(str(text))
    if not cleaned:
        return NormalizedAddress()

    simple = _SIMPLE_RE.match(cleaned)
    if simple and not (set(simple.group(2).split()) & _UNIT_LABELS):
        name, suffix = _canonicalize_street_tokens(simple.group(2).split())
        return NormalizedAddress(house_number=simple.group(1), street_name=name, street_suffix=suffix)

    house = unit = zipcode = None
    street_tokens: list[str] = []
    try:
        tagged, _ = usaddress.tag(cleaned)
        house = tagged.get("AddressNumber")
        unit = tagged.get("OccupancyIdentifier")
        zipcode = normalize_zip(tagged.get("ZipCode"))
        street_parts = [
            tagged.get("StreetNamePreDirectional"),
            tagged.get("StreetNamePreType"),
            tagged.get("StreetName"),
            tagged.get("StreetNamePostType"),
            tagged.get("StreetNamePostDirectional"),
        ]
        street_tokens = " ".join(p for p in street_parts if p).split()
    except (usaddress.RepeatedLabelError, UnicodeEncodeError):
        pass

    if not street_tokens:  # fallback: leading house number + rest
        match = _HOUSE_RE.match(cleaned)
        rest = cleaned
        if match:
            house, rest = match.group(1), match.group(2)
        tokens, unit = _extract_unit(rest.split())
        street_tokens = tokens
    else:
        street_tokens, extracted_unit = _extract_unit(street_tokens)
        unit = unit or extracted_unit

    name, suffix = _canonicalize_street_tokens(street_tokens)
    if unit:
        unit = unit.replace("#", "").strip() or None
    return NormalizedAddress(
        house_number=house, street_name=name, street_suffix=suffix,
        unit=unit, zipcode=zipcode,
    )


@lru_cache(maxsize=200_000)
def normalize_street(text: str | None) -> tuple[str | None, str | None]:
    """Normalize an already-isolated street string → (name, suffix)."""
    if not text or not str(text).strip():
        return None, None
    tokens, _ = _extract_unit(_clean(str(text)).split())
    return _canonicalize_street_tokens(tokens)


def from_parts(
    house_number: str | None,
    street: str | None,
    borough: str | None = None,
    zipcode: str | None = None,
    unit: str | None = None,
) -> NormalizedAddress:
    """Build a NormalizedAddress from pre-split source fields."""
    name, suffix = normalize_street(street)
    house = str(house_number).strip().upper() if house_number and str(house_number).strip() else None
    return NormalizedAddress(
        house_number=house,
        street_name=name,
        street_suffix=suffix,
        unit=str(unit).strip().upper() if unit and str(unit).strip() else None,
        borough=normalize_borough(borough),
        zipcode=normalize_zip(zipcode),
    )


def from_free_text(
    text: str | None,
    borough: str | None = None,
    zipcode: str | None = None,
) -> NormalizedAddress:
    """Parse free text, then overlay trusted borough/zip fields if given."""
    parsed = parse_free_address(text)
    return NormalizedAddress(
        house_number=parsed.house_number,
        street_name=parsed.street_name,
        street_suffix=parsed.street_suffix,
        unit=parsed.unit,
        borough=normalize_borough(borough) or parsed.borough,
        zipcode=normalize_zip(zipcode) or parsed.zipcode,
    )
