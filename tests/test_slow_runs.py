"""Which whole-supply runs were slow (REQ-PIPE-412 criterion 7).

pipeline/slow_runs.marks is the one rule, called by the dashboard build over a
dataset's run times; the last test drives the build itself, so a dataset whose
runs are all slow is shown to keep its status at the layer that emits it."""
from __future__ import annotations

import pytest

from pipeline import slow_runs

pytestmark = pytest.mark.asset("quarterly")


def _runs(*times, scope="arrival"):
    """One run per run time, ranked in order; None is a run with no run time
    (a failed try's run)."""
    return [{"run_id": f"r{i}", "rank": i, "scope": scope, "run_time_ms": t}
            for i, t in enumerate(times, start=1)]


def _by_id(marked):
    return {m["run_id"]: m for m in marked}


class TestTheRule:

    def test_exactly_twice_the_median_is_not_slow(self):
        got = _by_id(slow_runs.marks(_runs(100, 100, 100, 200)))
        assert got["r4"]["slow"] is False

    def test_just_over_twice_is_slow_with_its_median_and_count(self):
        got = _by_id(slow_runs.marks(_runs(100, 100, 100, 201)))
        assert got["r4"]["slow"] is True
        assert (got["r4"]["median_ms"], got["r4"]["judged_against"]) == (100, 3)

    def test_an_even_baseline_uses_the_mean_of_its_two_middle_values(self):
        # Median of 100, 100, 300, 300 is 200: 400 is not slow, 401 is.
        assert _by_id(slow_runs.marks(_runs(100, 300, 100, 300, 400)))["r5"]["slow"] is False
        got = _by_id(slow_runs.marks(_runs(100, 300, 100, 300, 401)))["r5"]
        assert got["slow"] is True and got["median_ms"] == 200

    def test_the_first_three_are_too_few_and_the_fourth_is_judged(self):
        got = slow_runs.marks(_runs(100, 900, 100, 100))
        assert [m["too_few"] for m in got] == [True, True, True, False]
        assert [m["slow"] for m in got[:3]] == [None, None, None]
        assert got[3]["slow"] is False

    def test_the_22nd_is_judged_against_runs_2_to_21_only(self):
        # Run 1 is huge; were it in the window, the median would not move -
        # so make runs 2-21 all 100 and run 1 small instead: 201 is slow only
        # against runs 2-21.
        times = [1] + [100] * 20 + [201]
        got = slow_runs.marks(_runs(*times))[-1]
        assert got["judged_against"] == slow_runs.WINDOW == 20
        assert got["slow"] is True and got["median_ms"] == 100

    def test_a_readers_only_run_is_neither_marked_nor_counted(self):
        runs = _runs(100, 100, 100)
        runs.append({"run_id": "readers", "rank": 4, "scope": "readers", "run_time_ms": 10_000})
        runs.append({"run_id": "r5", "rank": 5, "scope": "full", "run_time_ms": 150})
        got = _by_id(slow_runs.marks(runs))
        assert got["readers"]["slow"] is None and not got["readers"]["too_few"]
        assert got["r5"]["judged_against"] == 3 and got["r5"]["slow"] is False

    def test_a_failed_try_is_not_counted(self):
        got = slow_runs.marks(_runs(100, None, 100, 100, 201))
        assert got[1]["slow"] is None
        assert got[4]["slow"] is True and got[4]["judged_against"] == 3

    def test_a_runs_mark_does_not_change_after_a_much_slower_later_run(self):
        before = slow_runs.marks(_runs(100, 100, 100, 150))
        after = slow_runs.marks(_runs(100, 100, 100, 150, 100_000))
        assert before[3]["slow"] is after[3]["slow"] is False
        assert after[4]["slow"] is True

    def test_the_median_is_emitted_only_where_it_is_shown(self):
        got = slow_runs.marks(_runs(100, 100, 100, 120, 130, 140))
        assert ["median_ms" in m for m in got] == [False, False, False, False, False, True]


class TestItIsNeverAStatus:
    """Criterion 6 at the build: a dataset whose runs are all slow keeps its
    statuses exactly as it has them with no run times at all."""

    def test_a_dataset_whose_runs_are_all_slow_keeps_its_status(self, monkeypatch):
        from pipeline import build_dashboard_data as bdd

        facts = {f"r{i}": {"dataset_id": "cp-clients", "scope": "arrival",
                           "supply_id": f"cp-clients@{i}", "rank": i,
                           "cause": f"arrival:r{i}", "run_time_ms": 10 ** i,
                           "ended_at": None, "not_checked": False}
                 for i in range(1, 9)}
        marked = bdd.run_times("cp-clients", facts)
        assert sum(1 for m in marked if m["slow"]) >= 4
        assert all("status" not in m and "current_status" not in m for m in marked)
        quiet = {k: {**f, "run_time_ms": None} for k, f in facts.items()}
        assert [m["slow"] for m in bdd.run_times("cp-clients", quiet)] == [None] * 8
