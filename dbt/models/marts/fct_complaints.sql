{{
    config(
        materialized='incremental',
        unique_key='complaint_id',
        incremental_strategy='delete+insert',
    )
}}
-- Complaint fact, incremental: only records created after the newest row
-- already in the table are reprocessed on a normal run (a full-refresh
-- rebuilds everything). delete+insert keeps reruns idempotent when a
-- window is re-read.
select
    complaint_id,
    property_id,
    created_date,
    closed_date,
    days_open,
    status,
    is_closed,
    is_emergency,
    agency,
    complaint_type,
    descriptor,
    borough,
    zipcode,
    latitude,
    longitude
from {{ ref('stg_311') }}
{% if is_incremental() %}
where created_date > (select coalesce(max(created_date), timestamp '1970-01-01') from {{ this }})
{% endif %}
