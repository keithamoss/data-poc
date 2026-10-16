"""dbt beside the other three tools (REQ-TEST-116 criterion 3).

dbt is a SUBPROCESS, so it can run while Soda, datacontract-cli and
Evidently - all in-process, and never written to share an interpreter -
run one after another in the foreground. plans/performance.md #5
measured the payoff: dbt ~5s and datacontract-cli ~6s dominate a ~11s
run, so overlapping them takes a run to ~6s.
"""
from __future__ import annotations

import ast
import inspect
import time

import pytest

from qa_tools.common import parallel_orchestrate as po


def test_both_halves_run_and_come_back_in_order():
    assert po.beside(lambda: "dbt", lambda: "rest") == ("dbt", "rest")


def test_they_actually_overlap():
    started = time.monotonic()
    po.beside(lambda: time.sleep(0.4), lambda: time.sleep(0.4))
    assert time.monotonic() - started < 0.7


def test_sequential_runs_one_then_the_other():
    seen = []
    po.beside(lambda: seen.append("dbt"), lambda: seen.append("rest"), concurrent=False)
    assert seen == ["dbt", "rest"]


def test_a_background_failure_is_raised_even_when_the_foreground_succeeds():
    def boom():
        raise RuntimeError("dbt failed")
    with pytest.raises(RuntimeError, match="dbt failed"):
        po.beside(boom, lambda: "rest")


def test_the_background_failure_wins_when_both_fail():
    """The order the tools would have failed in when run one after the
    other - dbt first - so a report does not depend on timing."""
    def dbt():
        time.sleep(0.1)
        raise RuntimeError("dbt failed")

    def rest():
        raise ValueError("soda failed")
    with pytest.raises(RuntimeError, match="dbt failed"):
        po.beside(dbt, rest)


def test_a_foreground_failure_waits_for_the_background_to_finish():
    """Nothing is left running behind a raised exception."""
    finished = []

    def dbt():
        time.sleep(0.2)
        finished.append(True)

    def rest():
        raise ValueError("soda failed")
    with pytest.raises(ValueError):
        po.beside(dbt, rest)
    assert finished == [True]


@pytest.mark.parametrize("module", ["qa_tools.bdm.orchestrate_bdm", "qa_tools.cp.orchestrate_cp"])
def test_each_orchestrator_runs_dbt_beside_the_rest(module):
    mod = __import__(module, fromlist=["_run_one_inner"])
    tree = ast.parse(inspect.getsource(mod._run_one_inner))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "beside"]
    assert calls, f"{module} still runs its four tools strictly one after another"
