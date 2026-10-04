-- Lineage bridge: every source record → its canonical property, with the
-- method and score that connected them (Phase 14: when a customer
-- challenges a merge, this is the audit trail).
select 'nyc_311' as source_system, source_record_id, property_id, match_method, match_score
from {{ source('er', 'map_complaints') }}
union all
select 'dob_permits', source_record_id, property_id, match_method, match_score
from {{ source('er', 'map_permits') }}
union all
select 'dca_licenses', source_record_id, property_id, match_method, match_score
from {{ source('er', 'map_licenses') }}
