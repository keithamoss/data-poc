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

from qa_tools.common.dataset_status import (  # noqa: I001
    rollup_statuses,
    CHECK_STATUSES,
    dashboard_status,
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


class TestTheWordsAreTheOnesBothSidesAgreed:
    """REQ-DASH-359 NFR 1, REQ-TEST-360 criterion 1: the terminal's words for
    each status are status-cases.json's vocabulary.labels block, exactly -
    the page's copy is held to the same block by tests-js/
    status-parity.test.js, so the two cannot drift apart."""

    def _table(self):
        labels = CASES["vocabulary"]["labels"]
        return {k: v for k, v in labels.items() if not k.startswith("_")}

    def test_the_words_match_the_table_exactly(self):
        from qa_tools.common.dataset_status import STATUS_WORDS

        assert self._table(), "the labels block is empty"
        assert STATUS_WORDS == self._table()

    def test_every_status_any_level_may_carry_has_words(self):
        """Every level's statuses - a left-out row's notchecked included
        (REQ-DASH-299 criterion 17) - and nothing else."""
        levels = {k: v for k, v in CASES["vocabulary"]["by_level"].items() if not k.startswith("_")}
        assert set(self._table()) == set().union(*levels.values())

    @pytest.mark.parametrize("form", ["label", "verb", "count"])
    def test_status_words_gives_each_form(self, form):
        from qa_tools.common.dataset_status import status_words

        for value, words in self._table().items():
            assert status_words(value, form) == words[form]

    @pytest.mark.parametrize("value", ["purple", "", None, "Fail", "pass"])
    def test_a_status_it_has_no_word_for_is_refused(self, value):
        from qa_tools.common.dataset_status import status_words

        with pytest.raises(UnknownStatusError):
            status_words(value)

    def test_no_word_is_a_colour(self):
        import re

        for words in self._table().values():
            for said in words.values():
                assert not re.search(r"\b(green|amber|red)\b", said, re.I), said


class TestEveryLevelCase:
    """REQ-DASH-299 criterion 17: notchecked is a left-out row's alone - a
    check result or a dataset tile carrying it is refused, naming it."""

    _ALLOWED = {"check": None, "dataset": "DATASET_STATUSES", "left_out": "LEFT_OUT_STATUSES"}

    def _allowed(self, level):
        from qa_tools.common import dataset_status

        name = self._ALLOWED[level]
        return None if name is None else getattr(dataset_status, name)

    def test_the_left_out_level_matches_the_table(self):
        from qa_tools.common.dataset_status import LEFT_OUT_STATUSES

        assert LEFT_OUT_STATUSES == set(CASES["vocabulary"]["by_level"]["left_out"])

    @pytest.mark.parametrize("case", CASES["level_cases"]["cases"],
                             ids=_ids(CASES["level_cases"]["cases"]))
    def test_it_returns_or_refuses_what_the_table_says(self, case):
        from qa_tools.common.dataset_status import recognised_status

        allowed = self._allowed(case["level"])
        if case.get("expect_error"):
            with pytest.raises(UnknownStatusError, match=case["status"]):
                recognised_status(case["status"], case["level"], allowed)
        else:
            assert recognised_status(case["status"], case["level"], allowed) == case["expect"]


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


class TestEveryDatasetRollupCase:
    """The FILTERING rollup, as opposed to the ordering one above.

    Added 2026-09-25 with `inactive` (post-build-review #4). This side
    had no equivalent at all - `dataset_status()` called `worst_of()`
    directly, so the first check carrying a status with no verdict
    would have raised inside the GitHub Issues automation.
    """

    @pytest.mark.parametrize("case", CASES["dataset_rollup_cases"]["cases"],
                             ids=_ids(CASES["dataset_rollup_cases"]["cases"]))
    def test_it_returns_what_the_table_says(self, case):
        assert rollup_statuses(case["statuses"]) == case["expect"], case["why"]


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


class TestTheRealRecordedHistoryStillPasses:
    """Making an unrecognised status fatal is only safe if nothing in the
    real history carries one. Asserted rather than assumed - this is the
    change that turns a false green into a failed build, so the blast
    radius is worth measuring rather than trusting.

    Read from the RECORDED history rather than from `reports/*.json`, and
    that is a correction rather than a preference. The first version read
    the built dashboard JSON, which is a REGENERATED artifact: in a
    parallel run tests/test_dashboard_e2e.py's build fixture rewrites
    those same files, and this test failed intermittently against one
    mid-rewrite. That hazard is already documented (plans/tooling.md #10)
    and this walked straight into it. The recorded history is also the
    truer subject - it is the permanent record, and `reports/` is a view
    of it.

    IT USED TO GLOB A COMMITTED TREE, at a depth that had to be kept in
    step with REQ-PIPE-038's own re-keying. REQ-PIPE-089 made the history
    rows, so there is no depth to get wrong - but the guard that existed
    because of it stays, because the failure it prevents is unchanged: a
    query that finds nothing makes every assertion below pass.
    """

    def _recorded_tool_verdicts(self, conn) -> set[str]:
        from qa_tools.common import qa_store

        return {row[0] for row in conn.execute(
            f'SELECT DISTINCT status FROM "{qa_store.SCHEMA}".check_result_visible').fetchall()}

    def test_the_history_is_actually_there_to_check(self, deployment_history):
        """Without this, an empty result makes every assertion below pass
        by finding nothing - which is the same shape of false green this
        whole requirement is about."""
        from qa_tools.common import supply_db

        with supply_db.connect(label="test-status-parity") as conn:
            assert self._recorded_tool_verdicts(conn), "no recorded QA history found"

    def test_every_recorded_tool_verdict_maps_to_a_known_status(self, deployment_history):
        from qa_tools.common import supply_db

        with supply_db.connect(label="test-status-parity") as conn:
            verdicts = self._recorded_tool_verdicts(conn)
        unmapped = {v for v in verdicts if v and dashboard_status(v) is None}
        assert unmapped == set(), (
            f"recorded history carries tool verdicts {unmapped} that map "
            "to no dashboard status"
        )

    def test_every_status_the_history_maps_to_is_one_a_check_may_carry(self, deployment_history):
        from qa_tools.common import supply_db

        with supply_db.connect(label="test-status-parity") as conn:
            verdicts = self._recorded_tool_verdicts(conn)
        mapped = {dashboard_status(v) for v in verdicts if v}
        assert mapped <= CHECK_STATUSES, (
            f"recorded history maps to {mapped - CHECK_STATUSES}, which "
            "both implementations would now refuse on a check"
        )
