-- Internal invariant (error severity): any fuzzy match that was
-- auto-accepted must score at/above the configured AUTO threshold.
-- A violation means the matcher and its config have drifted apart.
select mention_id, match_method, match_score
from {{ source('er', 'property_matches') }}
where match_method = 'fuzzy_address'
  and match_score < {{ var('er_auto_match_threshold') }}
