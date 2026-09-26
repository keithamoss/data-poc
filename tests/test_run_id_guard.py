"""qa_tools/common/run_id_guard.py - a recognition change must never
quietly re-key committed QA history (REQ-PIPE-057 criterion 19).

The failure this exists for is invisible from the change that causes
it: a delivery that starts being skipped shifts every later run down
one, and every committed path under qa_results/ is keyed by that
number. Nothing in the recognition change mentions qa_results/ at all.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from qa_tools.common import run_id_guard, tables_read


@dataclass
class _Arrival:
    run_id: str
    delivery_name: str


def _history(tmp_path, runs: dict[str, str]):
    # The `_raw` scope, where REQ-PIPE-038 put dataset_stats - it
    # describes a RUN, and the collection's other children are datasets.
    base = tmp_path / "ag" / "col" / tables_read.RAW_SCOPE
    for run_id, delivery_name in runs.items():
        run_dir = base / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "dataset_stats.json").write_text(json.dumps(
            {"raw_output": {"arrival_record": {"run_id": run_id, "delivery": delivery_name}}}))
    return tmp_path


class TestItPassesWhenNothingMoved:
    def test_the_same_deliveries_in_the_same_order_are_fine(self, tmp_path):
        _history(tmp_path, {"run_001": "a", "run_002": "b"})
        run_id_guard.check("ag", "col", [_Arrival("run_001", "a"), _Arrival("run_002", "b")],
                            results_dir=tmp_path)

    def test_a_new_arrival_on_the_end_is_the_ordinary_case(self, tmp_path):
        _history(tmp_path, {"run_001": "a"})
        run_id_guard.check("ag", "col", [_Arrival("run_001", "a"), _Arrival("run_002", "b")],
                            results_dir=tmp_path)

    def test_no_committed_history_is_not_a_failure(self, tmp_path):
        """A first run has nothing to disagree with."""
        run_id_guard.check("ag", "col", [_Arrival("run_001", "a")], results_dir=tmp_path)


class TestItFailsWhenAnIdChangesMeaning:
    def test_a_skipped_delivery_shifting_the_rest_is_caught(self, tmp_path):
        """The real shape: 'a' stops being recognised, so run_001 now
        means what run_002 meant and everything slides."""
        _history(tmp_path, {"run_001": "a", "run_002": "b", "run_003": "c"})
        shifted = [_Arrival("run_001", "b"), _Arrival("run_002", "c")]
        with pytest.raises(run_id_guard.RunIdWouldChangeError) as exc:
            run_id_guard.check("ag", "col", shifted, results_dir=tmp_path)
        message = str(exc.value)
        assert "run_001" in message and "run_002" in message and "run_003" in message

    def test_it_names_the_old_and_the_new_delivery(self, tmp_path):
        """"History would be re-keyed" sends somebody diffing directory
        listings; naming both ends is what makes it actionable."""
        _history(tmp_path, {"run_001": "monday-drop"})
        with pytest.raises(run_id_guard.RunIdWouldChangeError) as exc:
            run_id_guard.check("ag", "col", [_Arrival("run_001", "tuesday-drop")],
                                results_dir=tmp_path)
        assert "monday-drop" in str(exc.value) and "tuesday-drop" in str(exc.value)

    def test_a_run_that_would_vanish_is_caught_too(self, tmp_path):
        _history(tmp_path, {"run_001": "a", "run_002": "b"})
        with pytest.raises(run_id_guard.RunIdWouldChangeError, match="no longer exist"):
            run_id_guard.check("ag", "col", [_Arrival("run_001", "a")], results_dir=tmp_path)


class TestItDoesNotGuessAtProvenance:
    def test_a_run_with_no_recorded_arrival_is_skipped(self, tmp_path):
        """An unknown provenance cannot be compared against anything,
        and inventing one is how a guard starts reporting confidently
        on nothing."""
        base = tmp_path / "ag" / "col" / tables_read.RAW_SCOPE / "run_001"
        base.mkdir(parents=True)
        (base / "dataset_stats.json").write_text(json.dumps({"raw_output": {}}))
        assert run_id_guard.committed_deliveries("ag", "col", tmp_path) == {}

    def test_unreadable_history_is_skipped_rather_than_fatal(self, tmp_path):
        base = tmp_path / "ag" / "col" / tables_read.RAW_SCOPE / "run_001"
        base.mkdir(parents=True)
        (base / "dataset_stats.json").write_text("{not json")
        assert run_id_guard.committed_deliveries("ag", "col", tmp_path) == {}


class TestAgainstTheRealCommittedHistory:
    def test_todays_recognition_still_agrees_with_what_is_committed(self):
        """The check that matters: REQ-PIPE-057 changed recognition
        twice over, and this asserts neither change moved a real run
        id. Every delivery in this PoC has a receipt and none spans
        collections, which is WHY it holds - stated here so a future
        failure reads as "that stopped being true" rather than as a
        mystery."""
        from qa_tools.common import arrivals

        for agency, collection, prefix in (
                ("registry-services", "civil-registration", "run_"),
                ("child-protection-family-support", "child-protection", "cp_run_")):
            found = arrivals.arrivals_for(collection, prefix)
            if not found:
                pytest.skip("no deliveries on disk - a freshly-cloned checkout")
            run_id_guard.check(agency, collection, found)
