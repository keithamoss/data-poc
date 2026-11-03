{# A thin generic test over the one set-member macro (REQ-QAC-297 criterion 1):
   missing members of a declared set, by key. See macros/set_member_violations.sql. #}
{% test missing_set_members(model, column_name, key_columns, member_setting) %}
{{ set_member_violations(model, column_name, key_columns, member_setting, 'missing') }}
{% endtest %}
