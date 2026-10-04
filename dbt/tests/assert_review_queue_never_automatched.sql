-- Internal invariant: nothing in the review queue may also appear as an
-- auto-accepted match for the same mention.
select q.mention_id
from {{ source('er', 'review_queue') }} q
join {{ source('er', 'property_matches') }} m
  on m.mention_id = q.mention_id
where m.match_method = 'fuzzy_address'
