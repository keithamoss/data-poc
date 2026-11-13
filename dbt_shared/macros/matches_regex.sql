{#
Real dbt custom generic test - dbt-core ships no native regex/format test
(unlike accepted_values for a closed value set), and this project has no
dbt_utils dependency to borrow one from (see packages.yml's absence -
none exists). PostgreSQL's regexp_like() is used rather than regexp_matches(), and
the difference is not cosmetic: DuckDB's regexp_matches() returns a
BOOLEAN, while PostgreSQL's is a SET-RETURNING function, which it
refuses to allow in a WHERE clause ("set-returning functions are not
allowed in WHERE"). regexp_like() is the boolean one, available since
PostgreSQL 15 (REQ-PIPE-087).

The regex DIALECT changes with it, which is worth knowing before
writing a pattern: DuckDB uses RE2, PostgreSQL uses its own POSIX
engine. The patterns this project actually uses are plain character
classes and anchors, which both read identically - but RE2 and POSIX
differ on more elaborate constructs, so a new pattern needs checking
against PostgreSQL rather than against the Soda checks alone.

Excludes nulls the same way Soda's invalid_percent does - a null
value is a missing_count/not_null concern, not a format one, so a
separately-nullable column (registering_parent_1_name/_2_name) doesn't
get double-penalised by this test too.
#}

{% test matches_regex(model, column_name, pattern) %}

select *
from {{ model }}
where {{ column_name }} is not null
  and not regexp_like({{ column_name }}, '{{ pattern }}')

{% endtest %}
