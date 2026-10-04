{# Generic tests kept dependency-free (no dbt_utils needed offline). #}

{% test within_range(model, column_name, min_value, max_value) %}
select {{ column_name }}
from {{ model }}
where {{ column_name }} is not null
  and ({{ column_name }} < {{ min_value }} or {{ column_name }} > {{ max_value }})
{% endtest %}

{% test not_in_future(model, column_name, grace_days=1) %}
select {{ column_name }}
from {{ model }}
where {{ column_name }} is not null
  and {{ column_name }} > current_date + interval '{{ grace_days }}' day
{% endtest %}
