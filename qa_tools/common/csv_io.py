"""
Explicit, contract-driven null handling for every CSV this pipeline
reads - shared by pipeline/load.py, qa_tools/bdm/build_per_run_warehouses
.py, qa_tools/bdm/run_evidently_bdm.py, qa_tools/cp/build_cp_warehouses.py,
and qa_tools/cp/run_evidently_cp.py.

Built after a real bug (plans/qa-pipeline.md #17): pandas' and DuckDB's
default CSV readers each have their own hardcoded list of "these strings
mean null" (pandas: "", "N/A", "NA", "NULL", "NaN", "None", "n/a", "nan",
"null", and several numeric-looking variants; DuckDB's own list is
separate and not necessarily identical) - nothing in this codebase chose
that vocabulary, it's just whatever each library ships with, and an
injected dirty-data value ("N/A") silently colliding with it caused a
real, hard-to-spot bug. Keith's decision (2026-09-15): no more implicit
magic anywhere - every CSV read pins pandas'/DuckDB's own null-sniffing
off entirely, and only genuinely null (i.e. literal empty-field) or a
value a contract EXPLICITLY names for that column ever becomes NULL.

Where a column's null vocabulary comes from: an optional `nullValues`
list on that column's entry in the ODCS contract YAML (a project
convention, not a real ODCS property - like `classification`, ODCS's
Pydantic models accept arbitrary extra keys via `extra="allow"`, so this
doesn't break contract validity/lint). No column in either of this
project's contracts sets one today - every column's default null
vocabulary is "a literal empty field, nothing else" - but the mechanism
is real and ready the day a source system's own null convention
(a genuine "NULL" or "N/A" string a real upstream system writes,
as opposed to a source-format parsing accident) needs representing.
"""
from __future__ import annotations

import pandas as pd

from qa_tools.common import yaml_io

# DuckDB's own read_csv_auto/read_csv only ever sees an already-pandas-
# written intermediate CSV in this pipeline (every read_csv_auto call
# site reads a file pipeline/load.py or a build_*_warehouses.py module
# just wrote via pandas, never a raw generator CSV directly) - so by the
# time DuckDB reads it, every null has already been resolved down to a
# genuinely empty field by the pandas read below, and every non-null
# value is unambiguous literal text. A single explicit empty-string
# nullstr is therefore correct and sufficient there - never DuckDB's own
# default sniffing list, for the same "no implicit magic" reason.
DUCKDB_NULLSTR = ""


def load_null_values_by_column(contract_path: str) -> dict[str, dict[str, list[str]]]:
    """table name -> column name -> its contract-declared extra null
    vocabulary (never includes "" itself - that's always implicit,
    handled separately below). A table/column with no `nullValues` entry
    simply won't appear here; callers treat that as an empty list."""
    with open(contract_path) as f:
        contract = yaml_io.load(f)
    out: dict[str, dict[str, list[str]]] = {}
    for table in contract.get("schema", []):
        cols = {}
        for prop in table.get("properties", []):
            values = prop.get("nullValues")
            if values:
                cols[prop["name"]] = list(values)
        out[table["name"]] = cols
    return out


def read_csv_explicit_nulls(path: str, extra_null_values: dict[str, list[str]] | None = None,
                             **kwargs) -> pd.DataFrame:
    """pd.read_csv with pandas' own default null-sniffing turned off
    entirely (`keep_default_na=False`) and replaced with an explicit,
    per-column `na_values` map: every column defaults to "a literal
    empty field only" - `extra_null_values` (typically one table's slice
    of `load_null_values_by_column`'s result) adds column-specific extra
    sentinel strings on top, never a repo-wide default. Every column
    present in the file must appear in the na_values map or pandas gives
    it NO null treatment at all, not even blank fields - so this always
    peeks the header first to build a complete map, rather than trusting
    the caller to enumerate every column."""
    extra_null_values = extra_null_values or {}
    columns = list(pd.read_csv(path, nrows=0, **kwargs).columns)
    na_values = {col: [""] + extra_null_values.get(col, []) for col in columns}
    return pd.read_csv(path, keep_default_na=False, na_values=na_values, **kwargs)
