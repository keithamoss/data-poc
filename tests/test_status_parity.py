"""REQ-QAC-047 - the Python half of the shared status table.

There are two implementations of dataset status in this repo and there
have to be (qa_tools/common/dataset_status.py's own docstring explains
why). They drifted once already - plans/qa-pipeline.md item 74 - and the
drift rendered a check with 14 real violations GREEN.

Every case here comes from status-cases.json at the repo root, which
neither this suite nor tests-js/status-parity.test.js owns. That is the
point: a table either side could edit is a table either side can quietly
bend to whatever it already does.

The other half of this verification already exists and is NOT rebuilt
here - tests/test_dashboard_e2e.py's TestStatusMatchesEachToolsOwnVerdict
drives the real built dashboard over every committed result. It can only
ever cover statuses that appear in the history, and the status this
requirement was written for (per-check nodata) has no history at all yet.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_tools.common.dataset_status import (
    CHECK_STATUSES,
    DATASET_STATUSES,
    ORDERED_STATUSES,
    UNORDERED_STATUSES,
    UnknownStatusError,
    dashboard_status_of,
    is_retired,
    worst_of,
)

CASES_PATH = Path(__file__).resolve().parents[1] / "status-cases.json"
CASES = json.loads(CASES_PATH.read_text())


def _ids(cases):
    return [c["id"] for c in cases]


def _check_status(check: dict) -> str:
    return dashboard_status_of(
        check, "current", "current_status", check.get("warn"), check.get("fail")
    )


class TestTheVocabularyIsTheOneBothSidesAgreed:
    """The table declares the vocabulary; this module must not have its
    own. A status added to one implementation and not the other is the
    exact shape of item 74's drift, so the file is the single authority
    and both sides are held to it."""

    def test_the_ordering_matches_the_table_exactly(self):
        table = {k: v for k, v in CASES["vocabulary"]["ordered"].items()
                 if not k.startswith("_")}
        assert ORDERED_STATUSES == table

    def test_the_unorderable_statuses_match_the_table_exactly(self):
        table = {k for k in CASES["vocabulary"]["unordered"] if not k.startswith("_")}
        assert UNORDERED_STATUSES == table

    def test_no_status_is_both_orderable_and_not(self):
        assert not (set(ORDERED_STATUSES) & UNORDERED_STATUSES)

    def test_what_a_check_may_carry_matches_the_table(self):
        assert CHECK_STATUSES == set(CASES["vocabulary"]["by_level"]["check"])

    def test_what_a_dataset_may_carry_matches_the_table(self):
        assert DATASET_STATUSES == set(CASES["vocabulary"]["by_level"]["dataset"])

    def test_a_check_may_carry_strictly_less_than_a_dataset(self):
        """The scoping is only worth having if it is real. If the two
        levels ever accept the same set, the distinction has quietly
        collapsed and a dataset-level status on a check renders again."""
        assert CHECK_STATUSES < DATASET_STATUSES


class TestEveryCheckCase:
    @pytest.mark.parametrize("case", [c for c in CASES["check_cases"]
                                      if not c.get("expect_error")],
                             ids=_ids([c for c in CASES["check_cases"]
                                       if not c.get("expect_error")]))
    def test_it_returns_what_the_table_says(self, case):
        assert _check_status(case["check"]) == case["expect"], case["why"]

    @pytest.mark.parametrize("case", [c for c in CASES["check_cases"]
                                      if c.get("expect_error")],
                             ids=_ids([c for c in CASES["check_cases"]
                                       if c.get("expect_error")]))
    def test_it_fails_loudly_rather_than_guessing(self, case):
        with pytest.raises(UnknownStatusError):
            _check_status(case["check"])


class TestEveryRollupCase:
    @pytest.mark.parametrize("case", [c for c in CASES["rollup_cases"]
                                      if not c.get("expect_error")],
                             ids=_ids([c for c in CASES["rollup_cases"]
                                       if not c.get("expect_error")]))
    def test_it_returns_what_the_table_says(self, case):
        assert worst_of(case["statuses"]) == case["expect"], case["why"]

    @pytest.mark.parametrize("case", [c for c in CASES["rollup_cases"]
                                      if c.get("expect_error")],
                             ids=_ids([c for c in CASES["rollup_cases"]
                                       if c.get("expect_error")]))
    def test_it_refuses_rather_than_returning_green(self, case):
        with pytest.raises(UnknownStatusError):
            worst_of(case["statuses"])


class TestEveryRetiredCase:
    @pytest.mark.parametrize("case", CASES["retired_cases"],
                             ids=_ids(CASES["retired_cases"]))
    def test_the_filtering_rule_matches_the_table(self, case):
        assert is_retired(case["check"]) is case["expect_retired"], case["why"]


class TestTheErrorSaysEnoughToActOn:
    """A failure that does not name the value or where it was read from
    replaces a silent wrong answer with a loud useless one. The whole
    change in behaviour here is from silently-wrong to noisily-broken,
    and it is only worth it if the noise is diagnostic."""

    def test_it_names_the_status_it_did_not_recognise(self):
        with pytest.raises(UnknownStatusError, match="definitely-not-a-status"):
            _check_status({"current": 0, "warn": 5, "fail": 10,
                           "current_status": "definitely-not-a-status"})

    def test_it_names_where_the_status_was_read_from(self):
        with pytest.raises(UnknownStatusError, match="current_status"):
            _check_status({"current": 0, "warn": 5, "fail": 10,
                           "current_status": "definitely-not-a-status"})

    def test_a_rollup_failure_names_the_status_too(self):
        with pytest.raises(UnknownStatusError, match="exhausted"):
            worst_of(["green", "exhausted"])


class TestTheRealCommittedHistoryStillPasses:
    """Making an unrecognised status fatal is only safe if nothing in the
    real committed history carries one. Asserted rather than assumed -
    this is the change that turns a false green into a failed build, so
    the blast radius is worth measuring rather than trusting."""

    def test_every_recorded_status_in_the_built_reports_is_recognised(self):
        reports = Path(__file__).resolve().parents[1] / "reports"
        paths = [reports / "birth_registrations_dashboard.json",
                 reports / "child_protection_dashboard.json"]
        present = [p for p in paths if p.exists()]
        if not present:
            pytest.skip("dashboard JSON not built in this environment")
        known = set(ORDERED_STATUSES) | UNORDERED_STATUSES
        seen = set()
        for path in present:
            data = json.loads(path.read_text())
            for ds in data.get("datasets") or [data]:
                for col in ds.get("columns", []):
                    for ck in col.get("checks", []):
                        seen.add(ck.get("current_status"))
                        for h in ck.get("history", []):
                            seen.add(h.get("status"))
        unrecognised = {s for s in seen if s and s not in known}
        assert unrecognised == set(), (
            f"real committed results carry {unrecognised}, which both "
            "implementations would now refuse"
        )
