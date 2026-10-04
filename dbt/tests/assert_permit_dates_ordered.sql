-- Source-semantics check (warn severity: this is upstream data quality,
-- not a platform bug): a permit should not be issued before it was
-- approved. Violations are counted, surfaced, and tolerated up to a
-- small bound rather than silently ignored or hard-failing the build.
{{ config(severity='warn', warn_if='>0', error_if='>1000') }}
select permit_row_id, approved_date, issued_date
from {{ ref('stg_permits') }}
where issued_date is not null
  and approved_date is not null
  and issued_date < approved_date
