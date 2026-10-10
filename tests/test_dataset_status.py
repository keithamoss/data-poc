"""Tests for qa_tools/common/dataset_status.py - the worst-of-every-
real-check rollup used by the ticketing MVP (item 76, plans/qa-
pipeline.md), mirroring the dashboard's own client-side worstOf()/
checkStatus(). Fixture-based dataset dicts, matching the real shape
pipeline/build_dashboard_data.py/build_cp_dashboard_data.py produce."""
from __future__ import annotations

from qa_tools.common.dataset_status import dataset_status, status_by_run, status_for_value


def _check(current, warn, fail, retired_as_of=None):
    return {"current": current, "warn": warn, "fail": fail, "retired_as_of": retired_as_of}


def _dataset(*columns_of_checks):
    return {"columns": [{"checks": list(checks)} for checks in columns_of_checks]}


def _history_check(warn, fail, *history, retired_as_of=None):
    return {"warn": warn, "fail": fail, "retired_as_of": retired_as_of,
            "history": [{"run_id": run_id, "value": value} for run_id, value in history]}


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


class TestStatusByRun:
    def test_worst_check_per_run_id_wins(self):
        d = {"columns": [
            {"checks": [_history_check(1, 2, ("run_1", 0), ("run_2", 3))]},
            {"checks": [_history_check(1, 2, ("run_1", 1.5), ("run_2", 0))]},
        ]}
        assert status_by_run(d) == {"run_1": "amber", "run_2": "red"}

    def test_an_all_green_run_is_absent_not_explicitly_recorded(self):
        """A real, faithfully-mirrored quirk of the dashboard's own
        client-side datasetStatusByRun() - see status_by_run()'s own
        docstring. Callers must treat a missing run_id as green."""
        d = {"columns": [{"checks": [_history_check(1, 2, ("run_1", 0))]}]}
        assert status_by_run(d) == {}
        assert status_by_run(d).get("run_1", "green") == "green"

    def test_retired_checks_still_contribute_unlike_dataset_status(self):
        """Deliberately different from dataset_status()'s own filtering -
        mirrors the dashboard's own client-side datasetStatusByRun()
        exactly, which never excludes retired checks either (that
        function's own real behavior, this Python port's job is to
        match it, not "fix" it)."""
        d = {"columns": [{"checks": [_history_check(1, 2, ("run_1", 3), retired_as_of="2026-09-18")]}]}
        assert status_by_run(d) == {"run_1": "red"}

    def test_no_history_anywhere_returns_an_empty_map(self):
        assert status_by_run({"columns": [{"checks": [_history_check(1, 2)]}]}) == {}


# --- plans/qa-pipeline.md item 74's own follow-up (2026-09-19) ---------
#
# This module is the PYTHON MIRROR of the dashboard's own client-side
# status logic, and item 74's fix changed that logic in two ways without
# updating the mirror: a warn/fail threshold may now legitimately be
# None ("this check has no bound of that kind", e.g. the ODCS rowCount
# rule's two-sided mustBeBetween range), and every check/history entry
# now carries its own real tool verdict, which is authoritative.
#
# Caught by CI - the FIRST run of ticket-sync.yml after its own dead
# branch pin was fixed (plans/publishing-and-history.md #7) died with a
# real `TypeError: '>' not supported between instances of 'int' and
# 'NoneType'` on real committed data. Worth recording as the concrete
# argument for that pin fix: this regression existed for exactly as long
# as CI wasn't running, and was found within seconds of it running again.

def test_status_for_value_treats_a_null_bound_as_absent_not_zero():
    """A None threshold means the check has no bound of that kind, so it
    can never be crossed. Reading it as 0 is what item 74 fixed in the
    dashboard; this mirror has to agree or the two disagree silently."""
    assert status_for_value(1939, warn=None, fail=None) == "green"
    assert status_for_value(7, warn=5, fail=None) == "amber"
    assert status_for_value(3, warn=5, fail=None) == "green"
    # a real zero-tolerance violation count still reads red
    assert status_for_value(14, warn=None, fail=0) == "red"
    assert status_for_value(0, warn=None, fail=0) == "green"


def test_dataset_status_prefers_each_checks_real_tool_verdict():
    d = _dataset([{**_check(1939, None, None), "current_status": "green"}])
    assert dataset_status(d) == "green"
    # and a real failure is still red even where thresholds say nothing
    d = _dataset([{**_check(0, None, None), "current_status": "red"}])
    assert dataset_status(d) == "red"


def test_dataset_status_does_not_crash_on_a_null_threshold():
    """The exact real CI failure: a rowCount check with both bounds
    None and no verdict recorded reached `value > fail` and raised."""
    assert dataset_status(_dataset([_check(1939, None, None)])) == "green"


def test_status_by_run_prefers_each_history_entrys_real_verdict():
    ck = _history_check(None, None, ("run_01", 1939), ("run_02", 2119))
    for h, status in zip(ck["history"], ("green", "red")):
        h["status"] = status
    assert status_by_run({"columns": [{"checks": [ck]}]}) == {"run_02": "red"}


def test_status_by_run_does_not_crash_on_a_null_threshold():
    ck = _history_check(None, None, ("run_01", 1939))
    assert status_by_run({"columns": [{"checks": [ck]}]}) == {}
