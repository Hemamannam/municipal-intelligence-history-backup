-- Permits at analysis grain: source duplicates (measured ~15%) removed via
-- dup_rank; every kept permit carries its resolved property.
select
    p.permit_row_id,
    p.job_filing_number,
    p.work_permit,
    p.permit_status,
    p.filing_reason,
    p.work_type,
    p.job_description,
    p.estimated_job_cost,
    p.issued_date,
    p.approved_date,
    p.expired_date,
    p.borough,
    p.zipcode,
    p.normalized_address,
    p.bin,
    p.bbl,
    p.owner_name,
    p.owner_is_org,
    p.applicant_business_name,
    p.applicant_person_name,
    m.property_id,
    m.match_method,
    m.match_score
from {{ source('clean', 'permits') }} p
left join {{ source('er', 'map_permits') }} m
    on m.source_record_id = p.permit_row_id
where p.dup_rank = 1
