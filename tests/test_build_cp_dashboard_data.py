"""Smoke test for pipeline/build_cp_dashboard_data.py's reshaping logic,
against a small fixture rather than a real (slow) qa_tools/cp/
orchestrate_cp.py run - the Child Protection counterpart to
tests/test_build_dashboard_data.py. Calls build_one_table() directly
(no results_cp.json file needed) since that's the actual per-table
reshaping function under test."""
from __future__ import annotations

import pytest

from pipeline import build_cp_dashboard_data as bcd

# ARRIVAL RECORDS, not manifest entries (REQ-GEN-043) - and row counts
# now sit in dataset_stats, MEASURED from the data that landed, rather
# than travelling with the run as something the generator declared.
FIXTURE_RUNS = [
    {
        "run_id": "cp_run_001", "run_index": 1, "delivery": "CP_20260101",
        "received_at": "2026-01-01T05:00:00+00:00",
    },
    {
        "run_id": "cp_run_002", "run_index": 2, "delivery": "cp-drop-9104",
        "received_at": "2026-04-01T20:00:00+00:00",
    },
]

FIXTURE_DATASET_STATS = {
    # earliest_extract values deliberately placed relative to CP's real
    # quarterly cadence (contract/child-protection-contract.yaml's
    # slaProperties: - Feb/May/Aug/Nov day 1, 09:00 AWST, 8h latency
    # grace) rather than each run's own run_date, so
    # test_arrival_status_is_genuinely_computed_from_real_cadence below
    # can tell a real onTime/late classification apart from a hardcoded
    # one - see that test's own docstring.
    "cp_run_001": {
        "row_counts": {"cp_notifications": 3},
        "value_counts": {"concern_type": [["Neglect", 2], ["Physical abuse", 1]]},
        "arrival": {"cp_notifications": {"earliest_extract": "2025-11-01T05:00:00+00:00"}},
        "check_aggregates": {},
    },
    "cp_run_002": {
        "row_counts": {"cp_notifications": 4},
        "value_counts": {"concern_type": [["Neglect", 3], ["Physical abuse", 1]]},
        "arrival": {"cp_notifications": {"earliest_extract": "2026-02-01T20:00:00+00:00"}},
        "check_aggregates": {},
    },
}


def _check(run_id, column_name, value, status="pass", **overrides):
    rec = {
        "column_name": column_name, "check_name": "dbt:accepted_values",
        "dimension": "validity", "label": "Invalid values",
        "run_id": run_id, "metric_value": value, "unit": "count",
        "warn_threshold": 0.0, "fail_threshold": 5.0, "status": status,
        "row_count_total": 3, "row_count_invalid": 0,
        "engine": "dbt-core 1.12 + dbt-duckdb",
        "check_id": f"data-asset-1.child-protection-family-support.child-protection.cp-notifications.{column_name}.accepted_values_dbt",
    }
    rec.update(overrides)
    return rec


FIXTURE_RESULTS = [
    _check("cp_run_001", "concern_type", 0),
    _check("cp_run_002", "concern_type", 1, status="warn", row_count_invalid=1),
]


def test_stats_by_run_carries_every_run_not_just_latest_and_previous():
    dataset = bcd.build_one_table("cp_notifications", FIXTURE_RESULTS, FIXTURE_RUNS, FIXTURE_DATASET_STATS, {})

    col = next(c for c in dataset["columns"] if c["name"] == "concern_type")
    by_run = col["stats"]["byRun"]

    assert set(by_run) == {"cp_run_001", "cp_run_002"}
    assert by_run["cp_run_001"] == {
        "total": 3, "invalid": 0, "valid": 3, "valueCounts": [["Neglect", 2], ["Physical abuse", 1]],
    }
    assert by_run["cp_run_002"] == {
        "total": 4, "invalid": 1, "valid": 3, "valueCounts": [["Neglect", 3], ["Physical abuse", 1]],
    }
    # current/previous stay exactly as before, unaffected by byRun
    assert col["stats"]["current"]["valueCounts"] == [["Neglect", 3], ["Physical abuse", 1]]


def test_the_suppliers_own_timestamp_no_longer_decides_punctuality():
    """REQ-PIPE-080 criterion 4 - the Child Protection half, and the
    counterpart of test_build_dashboard_data.py's own. See that one
    for the full account of why this test now asserts the opposite of
    what it used to.

    In short: it proved that FIXTURE_DATASET_STATS' `earliest_extract`
    values, placed inside and outside each cycle's grace window, drove
    arrivalStatus to onTime and late. They did - and that value comes
    from inside the supplier's own file, so the supplier was deciding
    whether they were late. The verdict is now read from the recorded
    filing, so moving those timestamps must change nothing."""
    import json

    moved = json.loads(json.dumps(FIXTURE_DATASET_STATS))
    for run in moved.values():
        run["arrival"]["cp_notifications"]["earliest_extract"] = "2026-02-01T23:59:00+00:00"

    before = bcd.build_one_table("cp_notifications", FIXTURE_RESULTS, FIXTURE_RUNS,
                                  FIXTURE_DATASET_STATS, {})
    after = bcd.build_one_table("cp_notifications", FIXTURE_RESULTS, FIXTURE_RUNS, moved, {})

    assert ({r: v["arrivalStatus"] for r, v in before["arrivalByRun"].items()}
            == {r: v["arrivalStatus"] for r, v in after["arrivalByRun"].items()}), (
        "the supplier's own extract timestamp still moves the verdict")


def test_each_dataset_shows_its_own_runs():
    """One file is one arrival (REQ-PIPE-105), so a delivery is six runs
    and each belongs to one table. Without this every Child Protection
    page listed all 108 runs as its own arrival history."""
    from pipeline import build_cp_dashboard_data as b

    manifest = [{"run_id": "cp_clients__1"}, {"run_id": "cp_placements__1"},
                {"run_id": "cp_clients__2"}, {"run_id": "cp_run_001"}]
    assert [m["run_id"] for m in b.own_runs(manifest, "cp_clients")] == [
        "cp_clients__1", "cp_clients__2", "cp_run_001"]


_XT = ("data-asset-1.child-protection-family-support.child-protection."
       "cp-notifications.assigned_worker_id.relationships_dbt")


class TestACheckThatCouldNotRunStaysOnItsOwnCard:
    """post-build-review #77, gap 1 (Keith signed the fix 2026-10-04).

    A run whose cross-table check could not be evaluated records it
    under a pseudo-tool (`unrunnable`/`held`) with its own check_name,
    so keying by (engine, check_name) alone would open a SECOND card for
    the same check. It has to land on the real check's card, as that
    run's red, carrying the reason - so a reader sees "this run could
    not be evaluated, and why", never a pass and never a vanished run.
    """

    def _results(self, pseudo):
        real = _check("cp_run_001", "assigned_worker_id", 0, check_id=_XT,
                      check_name="relationships_cp_notifications_assigned_worker_id")
        return [real, pseudo]

    @pytest.mark.parametrize("reason_key", ["unrunnable_reason", "held_reason"])
    def test_it_joins_the_real_checks_card_as_a_red_run_with_its_reason(self, reason_key):
        pseudo = _check("cp_run_002", "cp_case_workers", None, status="fail", check_id=_XT,
                        check_name="Every notification's worker exists",
                        label="Not evaluated", **{reason_key: "cp_case_workers is held"})
        table = bcd.build_one_table("cp_notifications", self._results(pseudo), FIXTURE_RUNS,
                                    FIXTURE_DATASET_STATS, {})
        cards = [c for col in table["columns"] for c in col["checks"] if c.get("check_id") == _XT]

        assert len(cards) == 1, "one check, one card - the can't-run run must not open a second"
        by_run = {h["run_id"]: h for h in cards[0]["history"]}
        assert by_run["cp_run_002"]["status"] == "red"
        assert by_run["cp_run_002"]["not_evaluated"] == "cp_case_workers is held"
        assert by_run["cp_run_001"]["not_evaluated"] is None
