{#
THE SHARED PACKAGE'S TESTS, NAMED AS THIS PROJECT'S OWN (REQ-QAC-368
criterion 2). The macro and generic tests live once, in the local package
dbt_shared/ (packages.yml). dbt resolves an UNQUALIFIED generic test - the
`- matches_regex:` a schema file names - in the root project and dbt's own
namespace only, never in an installed package, and a package's macro called
from here sees the root project's names, not its own. So each is forwarded
here, by name, to the package; a schema file keeps naming it as it always has,
so no check's definition changes (its config hash reads the package's SQL -
validate_check_lifecycle.dbt_definitions).

FORWARDING ONLY: every line of logic is the package's. The whitespace
control (`-%}`, `{%-`) keeps the compiled SQL byte-identical to the SQL the
package's macro renders. A test or macro added to dbt_shared/ that a schema
file names is added here too.
#}
{% test matches_regex(model, column_name, pattern) -%}
{{ dbt_shared.test_matches_regex(model, column_name, pattern) }}
{%- endtest %}

{% test missing_set_members(model, column_name, key_columns, member_setting) -%}
{{ dbt_shared.test_missing_set_members(model, column_name, key_columns, member_setting) }}
{%- endtest %}

{% test unexpected_set_members(model, column_name, key_columns, member_setting) -%}
{{ dbt_shared.test_unexpected_set_members(model, column_name, key_columns, member_setting) }}
{%- endtest %}

{% test duplicated_set_members(model, column_name, key_columns, member_setting) -%}
{{ dbt_shared.test_duplicated_set_members(model, column_name, key_columns, member_setting) }}
{%- endtest %}

{% macro set_member_violations(model, column_name, key_columns, member_setting, kind) -%}
{{ dbt_shared.set_member_violations(model, column_name, key_columns, member_setting, kind) }}
{%- endmacro %}
