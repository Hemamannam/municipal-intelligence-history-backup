-- Business activity joined to property complaint context: where do
-- licensed businesses operate amid heavy complaint volume?
select
    b.business_id,
    b.canonical_business_name,
    b.n_licenses,
    count(distinct l.property_id) as n_locations,
    count(*) filter (where l.license_status = 'Active') as active_licenses,
    min(l.license_created) as first_licensed,
    max(l.license_expires) as latest_expiry,
    string_agg(distinct l.business_category, ', ') as categories,
    sum(coalesce(c.complaints_12m, 0)) as location_complaints_12m,
    sum(coalesce(c.complaints_total, 0)) as location_complaints_total
from {{ ref('dim_business') }} b
join {{ ref('stg_business_licenses') }} l using (business_id)
left join {{ ref('int_property_complaints') }} c on c.property_id = l.property_id
group by b.business_id, b.canonical_business_name, b.n_licenses
