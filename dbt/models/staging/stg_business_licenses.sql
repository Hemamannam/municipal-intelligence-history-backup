-- Licenses at analysis grain: NYC premises only (mailing-address rows have
-- no property to resolve to), carrying resolved property and business.
select
    l.license_id,
    l.business_unique_id,
    l.business_name,
    l.dba_trade_name,
    l.business_category,
    l.license_type,
    l.license_status,
    l.license_created,
    l.license_expires,
    l.license_expires < current_date as is_expired,
    l.contact_phone,
    l.borough,
    l.zipcode,
    l.normalized_address,
    l.bbl,
    l.latitude,
    l.longitude,
    mp.property_id,
    mp.match_method,
    mp.match_score,
    mb.business_id
from {{ source('clean', 'licenses') }} l
left join {{ source('er', 'map_licenses') }} mp
    on mp.source_record_id = l.license_id
left join {{ source('er', 'map_license_business') }} mb
    on mb.license_id = l.license_id
where l.is_nyc_premises
