"""Tests for qa_tools/common/dataset_status.py - the worst-of-every-
real-check rollup used by the ticketing MVP (item 76, plans/qa-
pipeline.md), mirroring the dashboard's own client-side worstOf()/
checkStatus(). Fixture-based dataset dicts, matching the real shape
pipeline/build_dashboard_data.py/build_cp_dashboard_data.py produce."""
from __future__ import annotations

from qa_tools.common.dataset_status import dataset_status, status_for_value


def _check(current, warn, fail, retired_as_of=None):
    return {"current": current, "warn": warn, "fail": fail, "retired_as_of": retired_as_of}


def _dataset(*columns_of_checks):
    return {"columns": [{"checks": list(checks)} for checks in columns_of_checks]}


def test_status_for_value_green_amber_red_bands():
    assert status_for_value(0, warn=1, fail=2) == "green"
    assert status_for_value(1.5, warn=1, fail=2) == "amber"
    assert status_for_value(3, warn=1, fail=2) == "red"


def test_all_green_checks_gives_a_green_dataset():
    d = _dataset([_check(0, 1, 2)], [_check(0.5, 1, 2)])
    assert dataset_status(d) == "green"


def test_worst_single_check_across_any_column_wins():
    d = _dataset([_check(0, 1, 2)], [_check(3, 1, 2)])  # one red check, buried in the second column
    assert dataset_status(d) == "red"


def test_amber_beats_green_but_loses_to_red():
    d = _dataset([_check(1.5, 1, 2)], [_check(0, 1, 2)])
    assert dataset_status(d) == "amber"


def test_a_retired_check_never_contributes_even_if_its_own_value_is_red():
    d = _dataset([_check(3, 1, 2, retired_as_of="2026-09-18")])
    assert dataset_status(d) == "green"


def test_dataset_with_no_columns_is_green():
    assert dataset_status({"columns": []}) == "green"


def test_column_with_no_checks_is_green():
    assert dataset_status({"columns": [{"checks": []}]}) == "green"
