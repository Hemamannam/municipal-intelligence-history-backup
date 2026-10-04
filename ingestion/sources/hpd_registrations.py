"""HPD Multiple Dwelling Registrations + Registration Contacts.

Added in response to the Housing Department's follow-up requirement (see
customer_requests/): per-building LLCs hide portfolios, so properties must
be groupable by owner mailing address and management-company information.
HPD registrations are the city's own answer — every registered multiple
dwelling lists its corporate owner, officers, and their business addresses.

- Registrations (tesw-yqqr, ~203K): building ↔ registration id, with
  boro/block/lot → BBL (joins straight onto our property spine).
- Contacts (feu5-w2e2, ~782K): per registration: CorporateOwner /
  HeadOfficer / Agent / etc., corporation name, business mailing address.
"""

from ingestion.sources.base import SourceConfig

HPD_REGISTRATIONS = SourceConfig(
    key="hpd_registrations",
    name="NYC HPD Multiple Dwelling Registrations",
    dataset_id="tesw-yqqr",
    pk_fields=("registrationid",),
    select_fields=(
        "registrationid", "buildingid", "boro", "housenumber", "streetname",
        "zip", "block", "lot", "bin", "lastregistrationdate", "registrationenddate",
    ),
    critical_fields=("registrationid", "boro", "block", "lot"),
    description="Registered multiple dwellings; boro/block/lot → BBL property join.",
)

HPD_CONTACTS = SourceConfig(
    key="hpd_contacts",
    name="NYC HPD Registration Contacts",
    dataset_id="feu5-w2e2",
    pk_fields=("registrationcontactid",),
    select_fields=(
        "registrationcontactid", "registrationid", "type", "contactdescription",
        "corporationname", "firstname", "lastname",
        "businesshousenumber", "businessstreetname", "businessapartment",
        "businesscity", "businessstate", "businesszip",
    ),
    critical_fields=("registrationcontactid", "registrationid", "type"),
    description="Owner/officer/agent contacts per registration, with mailing addresses.",
)
