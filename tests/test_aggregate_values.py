"""Tests for pipeline/aggregate_values.py's shared "shape 2" aggregate
failing-value computation (module docstring - the check-detail panel's
distinct-invalid-values / numeric-range aggregate). Direct real DuckDB
queries against a small in-memory table, not a hand-mocked connection -
this module's whole job is the SQL it runs, so a real connection is the
only way to genuinely exercise it."""
from __future__ import annotations

from datetime import date

import duckdb

from pipeline.aggregate_values import _bin_dates, categorical_aggregate, numeric_date_aggregate


def _conn():
    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE t (id INTEGER, sex VARCHAR, date_of_birth DATE)
    """)
    conn.execute("""
        INSERT INTO t VALUES
            (1, 'M', '2020-01-01'),
            (2, 'F', '2020-01-02'),
            (3, 'X', '2020-01-05'),
            (4, 'X', '2020-01-05'),
            (5, NULL, '1899-01-01'),
            (6, 'M', '2020-01-10')
    """)
    return conn


def test_categorical_aggregate_counts_invalid_values():
    conn = _conn()
    result = categorical_aggregate(conn, "t", "sex", "sex NOT IN ('M','F') OR sex IS NULL", classification=None)

    assert result["type"] == "categorical"
    assert result["suppressed"] is False
    assert result["total_invalid"] == 3  # two 'X' + one NULL
    values_by_value = {v["value"]: v["count"] for v in result["values"]}
    assert values_by_value["X"] == 2
    assert values_by_value["(null)"] == 1


def test_categorical_aggregate_suppresses_classified_columns():
    conn = _conn()
    # SQL 3-valued logic: NULL NOT IN (...) is NULL, not TRUE, so this
    # condition (deliberately, unlike the other tests' own OR IS NULL)
    # only ever catches the two real 'X' rows, not the NULL one.
    result = categorical_aggregate(conn, "t", "sex", "sex NOT IN ('M','F')", classification="personal")

    assert result["suppressed"] is True
    assert result["values"] == []
    assert result["total_invalid"] == 2  # count itself is still safe to show


def test_categorical_aggregate_empty_when_nothing_invalid():
    conn = _conn()
    result = categorical_aggregate(conn, "t", "sex", "sex = 'does-not-exist'", classification=None)

    assert result["total_invalid"] == 0
    assert result["values"] == []


def test_numeric_date_aggregate_reports_min_max_and_histogram():
    conn = _conn()
    result = numeric_date_aggregate(
        conn, "t", "date_of_birth", "date_of_birth < DATE '1900-01-01'", classification=None
    )

    assert result["type"] == "numeric_date"
    assert result["total_invalid"] == 1
    assert result["min"] == "1899-01-01"
    assert result["max"] == "1899-01-01"
    assert result["histogram"] == [{"bucket": "1899-01-01", "count": 1}]  # lo == hi single-bucket path


def test_numeric_date_aggregate_bins_a_real_date_span():
    conn = _conn()
    result = numeric_date_aggregate(
        conn, "t", "date_of_birth", "1=1", classification=None, n_bins=3
    )

    assert result["total_invalid"] == 6
    # row 5's own date_of_birth (1899-01-01) is a real, genuine outlier in
    # this fixture (used elsewhere to test the invalid-date-range path) -
    # matching against it here confirms this isn't excluded/special-cased.
    assert result["min"] == "1899-01-01"
    assert result["max"] == "2020-01-10"
    assert sum(b["count"] for b in result["histogram"]) == 6
    assert len(result["histogram"]) <= 3


def test_numeric_date_aggregate_suppressed_skips_the_query():
    conn = _conn()
    result = numeric_date_aggregate(
        conn, "t", "date_of_birth", "1=1", classification="personal"
    )

    assert result["suppressed"] is True
    assert result["min"] is None
    assert result["values"] == []
    assert result["histogram"] == []


def test_numeric_date_aggregate_empty_when_nothing_invalid():
    conn = _conn()
    result = numeric_date_aggregate(conn, "t", "date_of_birth", "1=0", classification=None)

    assert result["total_invalid"] == 0
    assert result["min"] is None
    assert result["histogram"] == []


def test_bin_dates_same_day_collapses_to_one_bucket():
    d = date(2020, 1, 1)
    rows = [(d, 3), (d, 2)]

    out = _bin_dates(rows, d, d, n_bins=6)

    assert out == [{"bucket": d.isoformat(), "count": 5}]


def test_bin_dates_spreads_rows_across_bins_by_real_date_distance():
    lo, hi = date(2020, 1, 1), date(2020, 1, 10)
    rows = [(date(2020, 1, 1), 1), (date(2020, 1, 5), 2), (date(2020, 1, 10), 1)]

    out = _bin_dates(rows, lo, hi, n_bins=3)

    assert sum(b["count"] for b in out) == 4
    assert len(out) <= 3
