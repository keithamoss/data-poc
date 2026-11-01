{# A thin generic test over the one set-member macro (REQ-QAC-297 criterion 1):
   unexpected members of a declared set, by key. See macros/set_member_violations.sql. #}
{% test unexpected_set_members(model, column_name, key_columns, member_setting) %}
{{ set_member_violations(model, column_name, key_columns, member_setting, 'unexpected') }}
{% endtest %}
