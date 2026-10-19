"""The shared dashboard builder (pipeline/build_dashboard_data.py, one for
every collection since REQ-DASH-244) on a Child Protection table, against a
small fixture rather than a real (slow) orchestrator run. Calls
build_one_table() directly (no results file needed) since that's the
actual per-table reshaping function under test. These were the tests of
pipeline/build_cp_dashboard_data.py, which that requirement deleted."""
from __future__ import annotations

import pytest

from pipeline import build_dashboard_data as bcd
from qa_tools import collections
from qa_tools.common import hierarchy

_CP = collections.by_id("child-protection")


def _table(table, *args):
    return bcd.build_one_table(_CP, hierarchy.dataset_for_table(table), *args)

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
    "cp_run_001": {
        "row_counts": {"cp_notifications": 3},
        "value_counts": {"concern_type": [["Neglect", 2], ["Physical abuse", 1]]},
        "check_aggregates": {},
    },
    "cp_run_002": {
        "row_counts": {"cp_notifications": 4},
        "value_counts": {"concern_type": [["Neglect", 3], ["Physical abuse", 1]]},
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
    dataset = _table("cp_notifications", FIXTURE_RESULTS, FIXTURE_RUNS, FIXTURE_DATASET_STATS, {})

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


def test_each_dataset_shows_its_own_runs():
    """One file is one arrival (REQ-PIPE-105), so a delivery is six runs
    and each belongs to one table. Without this every Child Protection
    page listed all 108 runs as its own arrival history."""
    manifest = [{"run_id": "cp_clients__1"}, {"run_id": "cp_placements__1"},
                {"run_id": "cp_clients__2"}, {"run_id": "cp_run_001"}]
    assert [m["run_id"] for m in bcd.own_runs(manifest, "cp_clients")] == [
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
        table = _table("cp_notifications", self._results(pseudo), FIXTURE_RUNS,
                                    FIXTURE_DATASET_STATS, {})
        cards = [c for col in table["columns"] for c in col["checks"] if c.get("check_id") == _XT]

        assert len(cards) == 1, "one check, one card - the can't-run run must not open a second"
        by_run = {h["run_id"]: h for h in cards[0]["history"]}
        assert by_run["cp_run_002"]["status"] == "red"
        assert by_run["cp_run_002"]["not_evaluated"] == "cp_case_workers is held"
        assert by_run["cp_run_001"]["not_evaluated"] is None


class TestACheckATheToolCouldNotEvaluateSaysWhy:
    """The road-testing sweep's #7 (Keith, 2026-10-06): a real tool's check
    that it could not evaluate - Soda leaving it out of its results - is
    recorded red with a reason, and the card shows that reason."""

    def test_the_reason_reaches_the_card(self):
        failed = _check("cp_run_002", "assigned_worker_id", None, status="error", check_id=_XT,
                        check_name="relationships_cp_notifications_assigned_worker_id",
                        not_evaluated_reason="Soda could not evaluate it - needs Soda Cloud")
        real = _check("cp_run_001", "assigned_worker_id", 0, check_id=_XT,
                      check_name="relationships_cp_notifications_assigned_worker_id")
        table = _table("cp_notifications", [real, failed], FIXTURE_RUNS,
                                    FIXTURE_DATASET_STATS, {})
        card = next(c for col in table["columns"] for c in col["checks"]
                    if c.get("check_id") == _XT)
        by_run = {h["run_id"]: h for h in card["history"]}
        assert by_run["cp_run_002"]["status"] == "red"
        assert by_run["cp_run_002"]["not_evaluated"] == \
            "Soda could not evaluate it - needs Soda Cloud"


class TestTwoChecksThatShareANameStayTwoCards:
    """post-build-review #88 (found 2026-10-04 overnight, by the full
    suite). cp-clients' cross-table section carries checks DECLARED by
    other datasets that read it - cp-investigations' and cp-placements'
    `cp_client_id.relationships_dbt` among them. The builder keyed a
    section's cards by (engine, check_name), so those two different
    checks merged into ONE card: cp-placements' verdicts drawn on
    cp-investigations' check. Silent wrong information. A check's
    identity is its check_id, so cards are keyed by it, and where two
    pooled checks share a column and tail their URL key names the
    dataset that declares each."""

    _INV = ("data-asset-1.child-protection-family-support.child-protection."
            "cp-investigations.cp_client_id.relationships_dbt")
    _PLA = ("data-asset-1.child-protection-family-support.child-protection."
            "cp-placements.cp_client_id.relationships_dbt")

    def _cards(self, monkeypatch):
        monkeypatch.setattr(bcd, "_cross_table_check_ids", lambda: {self._INV, self._PLA})
        results = [
            _check("cp_run_001", "cp_client_id", 0, check_id=self._INV,
                   check_name="relationships_cp_investigations_cp_client_id"),
            _check("cp_run_001", "cp_client_id", 3, status="fail", check_id=self._PLA,
                   check_name="relationships_cp_investigations_cp_client_id"),
        ]
        table = _table("cp_clients", results, FIXTURE_RUNS,
                                    FIXTURE_DATASET_STATS, {})
        return [c for col in table["columns"] if col.get("scope") == "cross-table"
                for c in col["checks"]]

    def test_each_check_keeps_its_own_card_and_verdicts(self, monkeypatch):
        cards = {c["check_id"]: c for c in self._cards(monkeypatch)}
        assert set(cards) == {self._INV, self._PLA}
        assert cards[self._PLA]["history"][0]["value"] == 3
        assert cards[self._INV]["history"][0]["value"] == 0

    def test_their_keys_differ_and_name_the_declaring_dataset(self, monkeypatch):
        keys = {c["check_id"]: c["key"] for c in self._cards(monkeypatch)}
        assert len(set(keys.values())) == 2
        assert "cp-placements" in keys[self._PLA]


class TestACrossTableResultFromAnotherTablesRunReachesThePage:
    """post-build-review #253, Keith's call 2026-10-19 (option a): a page
    shows each check's newest result whichever run recorded it, as the
    promotion gate already reads it. TS-80's re-check of the Client
    Register re-ran Notifications' "Client reference" under cp-clients'
    own run; Notifications' page left that result out and read red for
    three months after the gate had promoted on it."""

    _REF = ("data-asset-1.child-protection-family-support.child-protection."
            "cp-notifications.cp_client_id.relationships_dbt")
    _OWN = "cp_notifications__202011010820000800"
    _RECHECK = "cp_clients__202011010830000800__1__r1"
    _RUNS = [
        {"run_id": _OWN, "run_index": 1, "delivery": "Data Extract 01 Nov 2020",
         "received_at": "2020-11-01T08:20:00+08:00"},
        {"run_id": _RECHECK, "run_index": 2, "delivery": "Data Extract 01 Nov 2020",
         "received_at": "2020-11-01T08:30:00+08:00"},
    ]
    _STATS = {_OWN: {"row_counts": {"cp_notifications": 987}, "value_counts": {},
                     "check_aggregates": {}}}

    def _card(self):
        results = [
            _check(self._OWN, "cp_client_id", 40, status="fail", check_id=self._REF,
                   check_name="dbt:relationships", run_timestamp="2020-11-01T08:20:00+08:00"),
            _check(self._RECHECK, "cp_client_id", 0, check_id=self._REF,
                   check_name="dbt:relationships", run_timestamp="2020-11-02T11:00:00+08:00"),
        ]
        table = bcd.build_one_table(
            _CP, hierarchy.dataset_for_table("cp_notifications"), results,
            bcd.own_runs(self._RUNS, "cp_notifications"), self._STATS, {},
            all_runs=self._RUNS)
        return next(c for col in table["columns"] for c in col["checks"]
                    if c.get("check_id") == self._REF)

    def test_the_result_is_in_the_checks_history_saying_where_and_when_it_was_recorded(self):
        by_run = {h["run_id"]: h for h in self._card()["history"]}
        assert set(by_run) == {self._OWN, self._RECHECK}
        assert by_run[self._RECHECK]["recorded_by"] == "cp-clients"
        assert by_run[self._RECHECK]["recorded_at"] == "2020-11-02T11:00:00+08:00"
        assert by_run[self._OWN]["recorded_by"] is None
        assert by_run[self._OWN]["recorded_at"] == "2020-11-01T08:20:00+08:00"
        # Criterion 7: only a re-check run is said to be one.
        assert by_run[self._RECHECK]["recorded_in"] == "re-check"
        assert by_run[self._OWN]["recorded_in"] is None

    def test_the_newest_result_is_the_current_one(self):
        card = self._card()
        assert card["current_status"] == "green"
        assert card["current"] == 0
        assert card["history"][-1]["run_id"] == self._RECHECK

    def test_the_card_names_the_tables_the_check_is_between(self):
        assert self._card()["between"] == {"declared_on": "cp-notifications",
                                           "reads": ["cp-clients"]}
