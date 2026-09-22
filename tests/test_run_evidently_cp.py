"""Regression test for a real bug fixed 2026-09-16: run_evidently_cp.py
wrote its qa_results/ output under its own table-scoped dataset id
(hierarchy.dataset_for_table("cp_notifications").dataset_id) instead of the
collection id (cp_common.COLLECTION_ID) every other CP tool writes
under - see that file's own comment on the fix, and
plans/publishing-and-history.md's Thread B entry for the restructuring
this was found during. Given correct inputs the code wrote its output
to the wrong location, a genuine logic bug (not the wiring-bug
exception - nothing about module/file resolution here, just the wrong
constant passed as an argument), so this stays as an automatic,
going-forward regression test per CLAUDE.md's convention."""
from __future__ import annotations

import pandas as pd

from qa_tools.common import hierarchy
from qa_tools.cp import cp_common, run_evidently_cp


def test_evaluate_evidently_cp_writes_under_the_collection_id_not_the_table_id(monkeypatch):
    reference = pd.DataFrame({"concern_type": ["neglect", "physical", "neglect", "emotional"]})
    current = pd.DataFrame({"concern_type": ["neglect", "physical", "neglect", "physical"]})
    monkeypatch.setattr(run_evidently_cp, "read_csv_explicit_nulls",
                         lambda path, null_values: reference if "cp_run_01" in path else current)

    captured = {}

    def fake_write_qa_result(agency, dataset, run_id, run_timestamp, tool, raw_output, verified=None, **kw):
        captured["dataset"] = dataset

    monkeypatch.setattr(run_evidently_cp, "write_qa_result", fake_write_qa_result)

    run_evidently_cp.evaluate_evidently_cp("cp_run_02", "2026-01-01T00:00:00Z", reference_run_id="cp_run_01")

    assert captured["dataset"] == cp_common.COLLECTION_ID
    assert captured["dataset"] != hierarchy.dataset_for_table("cp_notifications").dataset_id


def test_evaluate_evidently_cp_still_tags_its_own_result_with_the_table_dataset_id(monkeypatch):
    """The write-path fix must not touch the per-result "dataset_id"
    field itself - the dashboard still needs it for per-table grouping,
    only the file LOCATION changed."""
    reference = pd.DataFrame({"concern_type": ["neglect", "physical", "neglect", "emotional"]})
    current = pd.DataFrame({"concern_type": ["neglect", "physical", "neglect", "physical"]})
    monkeypatch.setattr(run_evidently_cp, "read_csv_explicit_nulls",
                         lambda path, null_values: reference if "cp_run_01" in path else current)
    monkeypatch.setattr(run_evidently_cp, "write_qa_result", lambda *a, **kw: None)

    results = run_evidently_cp.evaluate_evidently_cp("cp_run_02", "2026-01-01T00:00:00Z", reference_run_id="cp_run_01")

    assert results[0]["dataset_id"] == hierarchy.dataset_for_table("cp_notifications").dataset_id
