"""Tests for qa_tools/common/csv_io.py - the explicit, contract-driven null
handling every real CSV read in this pipeline goes through (see that
module's own docstring, and plans/qa-pipeline.md #17/#18 for the "N/A"
bug this replaces). The core guarantee under test: nothing gets treated
as null except a genuinely empty field, or a value a contract explicitly
names for that column - never pandas'/DuckDB's own default null-sniffing
list (which independently swallows things like "N/A"/"NULL"/"NaN")."""
from __future__ import annotations

import textwrap

import pytest

from qa_tools.common.csv_io import load_null_values_by_column, read_csv_explicit_nulls

# Every string pandas' own default na_values list would otherwise treat as
# null - the whole point is that NONE of these should be swallowed unless a
# column explicitly opts in.
PANDAS_DEFAULT_NA_STRINGS = ["N/A", "NA", "NULL", "NaN", "None", "n/a", "nan", "null", "#N/A"]


@pytest.fixture
def _patch_read_csv(monkeypatch, tmp_path):
    """read_csv_explicit_nulls takes a path, not a buffer - writes each
    test's CSV text to a real temp file rather than reworking the
    function to also accept file-like objects, since every real caller
    always passes a path."""
    def _write(csv_text: str) -> str:
        p = tmp_path / "test.csv"
        p.write_text(textwrap.dedent(csv_text))
        return str(p)
    return _write


def test_default_na_strings_are_preserved_as_literal_text(_patch_read_csv):
    path = _patch_read_csv("a,b\n" + "\n".join(f"{s},x" for s in PANDAS_DEFAULT_NA_STRINGS))
    df = read_csv_explicit_nulls(path)
    assert df["a"].tolist() == PANDAS_DEFAULT_NA_STRINGS
    assert df["a"].isna().sum() == 0


def test_a_genuinely_blank_field_still_becomes_null(_patch_read_csv):
    path = _patch_read_csv("a,b\n,x\nfoo,\n")
    df = read_csv_explicit_nulls(path)
    assert df["a"].isna().tolist() == [True, False]
    assert df["b"].isna().tolist() == [False, True]


def test_contract_specified_extra_null_value_applies_only_to_its_own_column(_patch_read_csv):
    path = _patch_read_csv("a,b\nTBD,TBD\n")
    df = read_csv_explicit_nulls(path, extra_null_values={"a": ["TBD"]})
    assert df["a"].isna().tolist() == [True]
    assert df["b"].tolist() == ["TBD"]  # not opted in for column b - stays literal text


def test_load_null_values_by_column_parses_a_real_contract_shape(tmp_path):
    contract = tmp_path / "contract.yaml"
    contract.write_text(textwrap.dedent("""
        schema:
          - name: table_one
            properties:
              - name: col_a
                nullValues: ["TBD", "Unknown"]
              - name: col_b
          - name: table_two
            properties:
              - name: col_c
                nullValues: ["N/A"]
    """))
    result = load_null_values_by_column(str(contract))
    assert result == {
        "table_one": {"col_a": ["TBD", "Unknown"]},
        "table_two": {"col_c": ["N/A"]},
    }
