{#
THE SET-MEMBER RULE, ONCE (REQ-QAC-297 criterion 1): for every key, exactly
one row for each member of a declared set. One macro, called by three thin
generic tests in tests/generic/ - missing, duplicated and unexpected set
members - so that each is its own check (dbt_check_id_lookup keys on
(model, column, test)), and none carries SQL of its own.

GENERIC. It names no set and no dataset: `key_columns` are the record's
identifier columns, `column_name` the member column, and `member_setting` the
name of the list setting holding the declared set. The set in force for the
run's period is read from the run's own view schema through source() - the
list_setting_members relation qa_tools/common/list_setting_members.py builds
with the period's views (criterion 3), keyed by the model's table and the
setting's name. Members are compared as text, whatever the column's type.

One failing row per violation (criteria 5 to 7), carrying the key columns and
the member, so a failing pair names its record and its member (criterion 8):
  missing     a key present in the table lacks a row for a member in force
  duplicated  a key has more than one row for the same member
  unexpected  a row's member is outside the set in force, or none
#}
{% macro set_member_violations(model, column_name, key_columns, member_setting, kind) %}
{%- set table_name = model.identifier[4:] if model.identifier.startswith('stg_') else model.identifier -%}
with members as (
    select member
    from {{ source('raw', 'list_setting_members') }}
    where table_name = '{{ table_name }}' and setting = '{{ member_setting }}'
)
{%- if kind == 'missing' %},
records as (
    select distinct {% for k in key_columns %}{{ k }}{{ ", " if not loop.last }}{% endfor %}
    from {{ model }}
)
select {% for k in key_columns %}r.{{ k }}, {% endfor %}m.member as {{ column_name }}
from records r
cross join members m
where not exists (
    select 1 from {{ model }} t
    where {% for k in key_columns %}t.{{ k }} is not distinct from r.{{ k }} and {% endfor -%}
          cast(t.{{ column_name }} as text) = m.member
)
{%- elif kind == 'duplicated' %}
select {% for k in key_columns %}{{ k }}, {% endfor %}cast({{ column_name }} as text) as {{ column_name }}
from {{ model }}
where cast({{ column_name }} as text) in (select member from members)
group by {% for k in key_columns %}{{ k }}, {% endfor %}cast({{ column_name }} as text)
having count(*) > 1
{%- elif kind == 'unexpected' %}
select {% for k in key_columns %}{{ k }}, {% endfor %}cast({{ column_name }} as text) as {{ column_name }}
from {{ model }}
where {{ column_name }} is null
   or cast({{ column_name }} as text) not in (select member from members)
{%- else %}
{{ exceptions.raise_compiler_error("set_member_violations: kind must be missing, duplicated or unexpected, not " ~ kind) }}
{%- endif %}
{% endmacro %}
