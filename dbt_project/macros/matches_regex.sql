{#
Real dbt custom generic test - dbt-core ships no native regex/format test
(unlike accepted_values for a closed value set), and this project has no
dbt_utils dependency to borrow one from (see packages.yml's absence -
none exists). DuckDB's regexp_matches() is the same RE2 engine Soda's own
`valid regex` checks compile down to (see bdm-birth-registrations-soda-
checks.yml's header comment on RE2's lack of lookahead support), so this
mirrors those checks exactly rather than introducing a different regex
dialect. Excludes nulls the same way Soda's invalid_percent does - a null
value is a missing_count/not_null concern, not a format one, so a
separately-nullable column (registering_parent_1_name/_2_name) doesn't
get double-penalised by this test too.
#}

{% test matches_regex(model, column_name, pattern) %}

select *
from {{ model }}
where {{ column_name }} is not null
  and not regexp_matches({{ column_name }}, '{{ pattern }}')

{% endtest %}
