-- Q9 (lineage demo): for one canonical property, show every source record
-- that resolved to it, how it matched, and the pipeline runs involved.
-- Swap :property_id for any id from dim_property.
with target as (
    select property_id
    from marts.mart_property_risk
    order by complaints_12m desc
    limit 1
)
select
    b.source_system,
    b.source_record_id,
    b.match_method,
    b.match_score,
    p.canonical_address,
    p.bbl
from marts.bridge_property_source b
join marts.dim_property p using (property_id)
where b.property_id = (select property_id from target)
order by b.source_system, b.source_record_id
limit 50;
