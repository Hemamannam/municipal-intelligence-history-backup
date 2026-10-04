"""Address normalization: the spec's canonical example plus NYC edge cases."""

import pytest

from entity_resolution.address_normalizer import (
    bbl_from_parts,
    from_free_text,
    from_parts,
    normalize_bbl,
    normalize_borough,
    normalize_street,
    normalize_zip,
    parse_free_address,
)


class TestSpecExample:
    """'123 W. 42nd St Apt 4B' and '123 WEST 42 STREET #4B' must converge."""

    def test_variant_one(self):
        a = parse_free_address("123 W. 42nd St Apt 4B")
        assert a.house_number == "123"
        assert a.street_name == "WEST 42"
        assert a.street_suffix == "STREET"
        assert a.unit == "4B"
        assert a.normalized_address == "123 WEST 42 STREET"
        assert a.unit_address == "123 WEST 42 STREET UNIT 4B"

    def test_variant_two_converges(self):
        b = parse_free_address("123 WEST 42 STREET #4B")
        assert b.normalized_address == "123 WEST 42 STREET"
        assert b.unit == "4B"
        assert (
            parse_free_address("123 W. 42nd St Apt 4B").unit_address == b.unit_address
        )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("761 CLARENCE AVENUE", "761 CLARENCE AVENUE"),
        ("761 Clarence Ave.", "761 CLARENCE AVENUE"),
        ("20 CLINTON ST", "20 CLINTON STREET"),
        ("2109 BLACKROCK AVE", "2109 BLACKROCK AVENUE"),
        ("78-15 PARSONS BLVD", "78-15 PARSONS BOULEVARD"),  # Queens hyphenated
        ("1465 WASHINGTON AVENUE", "1465 WASHINGTON AVENUE"),
        ("100 E 42ND ST", "100 EAST 42 STREET"),
        ("305 GRAND CONCOURSE", "305 GRAND CONCOURSE"),
        ("1 CENTRE ST FL 9", "1 CENTRE STREET"),
    ],
)
def test_property_level_normalization(raw, expected):
    assert parse_free_address(raw).normalized_address == expected


def test_unit_not_blindly_removed():
    a = parse_free_address("350 5TH AVE STE 4100")
    assert a.normalized_address == "350 5 AVENUE"  # property level
    assert a.unit == "4100"  # unit preserved separately
    assert "4100" in a.unit_address


def test_garbage_and_empty():
    assert parse_free_address(None).normalized_address is None
    assert parse_free_address("   ").normalized_address is None
    assert parse_free_address("N/A").house_number is None


def test_from_parts_with_split_fields():
    a = from_parts("60", "BAY 34 ST", "BROOKLYN", "11214")
    assert a.normalized_address == "60 BAY 34 STREET"
    assert a.borough == "BROOKLYN"
    assert a.zipcode == "11214"


def test_from_free_text_trusted_fields_override():
    a = from_free_text("123 MAIN ST", borough="Bronx", zipcode="10465-1234")
    assert a.borough == "BRONX"
    assert a.zipcode == "10465"


class TestBorough:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("BROOKLYN", "BROOKLYN"), ("Manhattan", "MANHATTAN"), ("BX", "BRONX"),
            ("QN", "QUEENS"), ("SI", "STATEN ISLAND"), ("Staten Island", "STATEN ISLAND"),
            ("NEW YORK", "MANHATTAN"), ("3", "BROOKLYN"), ("Unspecified", None), (None, None),
        ],
    )
    def test_mapping(self, raw, expected):
        assert normalize_borough(raw) == expected


class TestZipAndBbl:
    def test_zip(self):
        assert normalize_zip("11226") == "11226"
        assert normalize_zip("11226-3402") == "11226"
        assert normalize_zip("1122") is None
        assert normalize_zip("00000") is None

    def test_bbl_plain_and_pluto_decimal(self):
        assert normalize_bbl("1003507501") == "1003507501"
        assert normalize_bbl("2054800111.00000000") == "2054800111"
        assert normalize_bbl("54800111") is None       # too short
        assert normalize_bbl("6054800111") is None     # borough 6 doesn't exist
        assert normalize_bbl("1000000000") is None     # placeholder block/lot
        assert normalize_bbl(None) is None

    def test_bbl_from_parts(self):
        assert bbl_from_parts("QUEENS", "5198", "21") == "4051980021"
        assert bbl_from_parts("BROOKLYN", "06861", "00067") == "3068610067"
        assert bbl_from_parts("NOWHERE", "1", "1") is None
        assert bbl_from_parts("QUEENS", "0", "21") is None


def test_normalize_street_only():
    assert normalize_street("W 42nd St.") == ("WEST 42", "STREET")
    assert normalize_street("GRAND CONCOURSE") == ("GRAND", "CONCOURSE")
    assert normalize_street(None) == (None, None)


def test_cache_behavior_same_object():
    # lru_cache means repeated municipal addresses cost a dict lookup.
    assert parse_free_address("123 MAIN ST") is parse_free_address("123 MAIN ST")
