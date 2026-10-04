-- Complaints at analysis grain: one row per 311 service request,
-- carrying its resolved property (NULL when unresolvable).
select
    c.complaint_id,
    c.created_date,
    c.closed_date,
    date_diff('day', c.created_date, coalesce(c.closed_date, current_date)) as days_open,
    c.status,
    c.status = 'Closed' as is_closed,
    c.agency,
    c.complaint_type,
    c.complaint_type in (
        {% for t in var('emergency_complaint_types') %}'{{ t }}'{% if not loop.last %}, {% endif %}{% endfor %}
    ) as is_emergency,
    c.descriptor,
    c.location_type,
    c.channel,
    c.community_board,
    c.borough,
    c.zipcode,
    c.normalized_address,
    c.unit_address,
    c.bbl,
    c.latitude,
    c.longitude,
    m.property_id,
    m.match_method,
    m.match_score
from {{ source('clean', 'complaints') }} c
left join {{ source('er', 'map_complaints') }} m
    on m.source_record_id = c.complaint_id
