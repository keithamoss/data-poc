"""Tests for the small pure-function/edge-branch gaps in qa_tools/common/
{dbt,soda,datacontract,evidently}_common.py that the real-tool integration
tests (tests/test_run_*_{bdm,cp}.py) don't happen to exercise - each of
those tools' own "happy path" already runs for real via those tests; what's
missing is the failure/no-match/empty branches, which don't need a real
tool invocation to test since these are plain functions over plain data."""
from __future__ import annotations

import duckdb

from qa_tools.common.datacontract_common import check_id_from_quality_definition
from qa_tools.common.dbt_common import failing_sample_keys_direct, failing_sample_keys_via_values
from qa_tools.common.evidently_common import status_for_psi
from qa_tools.common.soda_common import check_id_from_resource_attributes


def test_check_id_from_quality_definition_none_when_no_definition():
    assert check_id_from_quality_definition(None) is None
    assert check_id_from_quality_definition("") is None


def test_check_id_from_quality_definition_none_when_no_check_id_property():
    quality_definition = "customProperties:\n  - property: other\n    value: x\n"
    assert check_id_from_quality_definition(quality_definition) is None


def test_check_id_from_quality_definition_finds_the_real_property():
    quality_definition = "customProperties:\n  - property: check_id\n    value: my.real.check\n"
    assert check_id_from_quality_definition(quality_definition) == "my.real.check"


def test_check_id_from_resource_attributes_none_when_no_match():
    assert check_id_from_resource_attributes({}) is None
    assert check_id_from_resource_attributes({"resourceAttributes": [{"name": "other", "value": "x"}]}) is None


def test_check_id_from_resource_attributes_finds_the_real_attribute():
    check = {"resourceAttributes": [{"name": "check_id", "value": "my.real.check"}]}
    assert check_id_from_resource_attributes(check) == "my.real.check"


def test_status_for_psi_below_warn_threshold_is_pass():
    assert status_for_psi(0.01, is_reference=False) == "pass"


def test_status_for_psi_reference_run_is_always_pass_regardless_of_value():
    assert status_for_psi(0.9, is_reference=True) == "pass"


def test_failing_sample_keys_direct_returns_empty_on_a_real_query_error():
    conn = duckdb.connect(":memory:")
    # relation_name doesn't exist - a real DuckDB error, not a mock
    assert failing_sample_keys_direct(conn, "no_such_table", "id") == []


def test_failing_sample_keys_direct_returns_real_pk_values():
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE audit (id INTEGER)")
    conn.execute("INSERT INTO audit VALUES (1), (2), (NULL)")
    assert failing_sample_keys_direct(conn, "audit", "id") == ["1", "2"]


def test_failing_sample_keys_via_values_returns_empty_on_a_real_query_error():
    conn = duckdb.connect(":memory:")
    assert failing_sample_keys_via_values(conn, "no_such_table", "v", "no_such_model", "col", "id") == []


def test_failing_sample_keys_via_values_resolves_real_rows():
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE model (id INTEGER, sex VARCHAR)")
    conn.execute("INSERT INTO model VALUES (1, 'X'), (2, 'M')")
    conn.execute("CREATE TABLE audit (sex VARCHAR)")
    conn.execute("INSERT INTO audit VALUES ('X')")
    assert failing_sample_keys_via_values(conn, "audit", "sex", "model", "sex", "id") == ["1"]
