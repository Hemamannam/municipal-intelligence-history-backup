"""Owner/business name normalization: the spec's LLC example and NYC realities."""

import pytest

from entity_resolution.owner_normalizer import (
    is_organization,
    normalize_name,
    normalize_person_lastfirst,
    normalize_person_name,
    normalize_phone,
)


def test_spec_llc_example_converges():
    a = normalize_name("ACME PROPERTY LLC")
    b = normalize_name("ACME PROPERTIES, L.L.C.")
    assert a == b == "ACME PROPERTIES LLC"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Gem Financial Services, Inc.", "GEM FINANCIAL SERVICES INC"),
        ("HENRYSMITH PROPERTY MGMT", "HENRYSMITH PROPERTIES MANAGEMENT"),
        ("  Flushing   Hospital  Medical Center ", "FLUSHING HOSPITAL MEDICAL CENTER"),
        ("123 MAIN STREET REALTY CORP.", "123 MAIN STREET REALTY CORP"),
        ("N/A", None),
        ("NOT APPLICABLE", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_name(raw, expected):
    assert normalize_name(raw) == expected


def test_person_name_assembly():
    assert normalize_person_name("JOHN", "SHEN") == "JOHN SHEN"
    assert normalize_person_name("Iris", "Lee", middle="M") == "IRIS M LEE"
    assert normalize_person_name(None, None) is None
    assert normalize_person_name("N/A", "N/A") is None


def test_pluto_lastfirst_reordering():
    assert normalize_person_lastfirst("RODRIGUEZ, JOSE R") == "JOSE R RODRIGUEZ"
    assert normalize_person_lastfirst("STEWART, RAYMOND") == "RAYMOND STEWART"
    # Orgs with commas must NOT be reordered.
    assert normalize_person_lastfirst("ACME PROPERTIES, L.L.C.") == "ACME PROPERTIES LLC"
    assert normalize_person_lastfirst("NEIL PAPPAS") == "NEIL PAPPAS"


class TestOrgClassification:
    @pytest.mark.parametrize(
        "name",
        [
            "ACME PROPERTIES LLC", "GEM FINANCIAL SERVICES, INC.",
            "FLUSHING HOSPITAL MEDICAL CENTER", "NYC HOUSING AUTHORITY",
            "745 E 168 HDFC", "123 MAIN ST LLC",
        ],
    )
    def test_orgs(self, name):
        assert is_organization(name) is True

    @pytest.mark.parametrize("name", ["JOSE R RODRIGUEZ", "IRIS LEE", None, "N/A"])
    def test_non_orgs(self, name):
        assert is_organization(name) is False


def test_normalize_phone():
    assert normalize_phone("7182371166") == "7182371166"
    assert normalize_phone("(718) 237-1166") == "7182371166"
    assert normalize_phone("1-718-237-1166") == "7182371166"
    assert normalize_phone("123") is None
    assert normalize_phone("0000000000") is None
    assert normalize_phone(None) is None
