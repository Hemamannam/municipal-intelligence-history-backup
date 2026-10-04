-- Canonical business dimension (license legal names + DBA clustering).
select
    business_id,
    canonical_business_name,
    n_licenses,
    n_name_variants
from {{ source('er', 'businesses') }}
