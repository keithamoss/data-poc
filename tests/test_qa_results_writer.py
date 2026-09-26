"""Tests for qa_tools/common/qa_results_writer.py - the committed
per-run raw-tool-output writer (plans/publishing-and-history.md Thread B,
Phase 1). Real requirement this covers: each write must land at the
documented path, carry the raw output byte-for-byte unmodified (never
reshaped/mutated), and separately record run_timestamp alongside it
rather than inside it.

REQ-PIPE-038 re-keyed the tree, so one call now writes several files:
the raw output to `_raw/<run_id>/<tool>.json` and each `verified`
record to the dataset it names. The path a call RETURNS is the raw one
- see tests/test_history_rekey.py for the fan-out itself, which is
that requirement's own subject rather than this module's."""
from __future__ import annotations

import json

from qa_tools.common.qa_results_writer import write_qa_result


def test_write_qa_result_lands_at_the_documented_path(tmp_path):
    out_path = write_qa_result("registry-services", "civil-registration", "run_01", "2026-01-01T00:00:00Z",
                                "dbt", {"some": "output"}, results_dir=tmp_path)

    assert out_path == (tmp_path / "registry-services" / "civil-registration"
                         / "_raw" / "run_01" / "dbt.json")
    assert out_path.exists()


def test_write_qa_result_preserves_raw_output_unmodified(tmp_path):
    raw = {"results": [{"status": "pass", "failures": 0}], "nested": {"a": [1, 2, 3]}}

    out_path = write_qa_result("agency", "dataset", "run_01", "2026-01-01T00:00:00Z", "soda", raw, results_dir=tmp_path)

    written = json.loads(out_path.read_text())
    assert written["raw_output"] == raw, "raw_output must be byte-for-byte what the tool produced, not reshaped"


def test_write_qa_result_records_run_timestamp_alongside_not_inside(tmp_path):
    raw = {"already": "has", "no": "timestamp field"}

    out_path = write_qa_result("agency", "dataset", "run_01", "2026-06-15T10:30:00Z", "evidently", raw, results_dir=tmp_path)

    written = json.loads(out_path.read_text())
    assert written["run_timestamp"] == "2026-06-15T10:30:00Z"
    assert written["raw_output"] == raw, "run_timestamp must never be spliced into the tool's own raw payload"


def test_write_qa_result_creates_parent_directories(tmp_path):
    out_path = write_qa_result("brand-new-agency", "brand-new-dataset", "run_99", "2026-01-01T00:00:00Z",
                                "dbt", {}, results_dir=tmp_path)

    assert out_path.parent.is_dir()


def test_write_qa_result_writes_verified_beside_raw_output(tmp_path):
    """Both are still written by one call - REQ-PIPE-038 separated
    WHERE they land, not whether the pair is recorded."""
    raw = {"results": [{"status": "fail", "failures": 0}]}  # e.g. dbt's own (buggy) count
    # the corrected record, naming the dataset it describes
    verified = [{"status": "fail", "metric_value": 7, "column_name": "sex",
                 "dataset_id": "birth-registrations"}]

    out_path = write_qa_result("registry-services", "civil-registration", "run_01",
                                "2026-01-01T00:00:00Z", "dbt", raw,
                                verified=verified, results_dir=tmp_path)

    written = json.loads(out_path.read_text())
    assert written["raw_output"] == raw, "raw_output must stay exactly what the tool produced, uncorrected"
    dataset_file = (tmp_path / "registry-services" / "civil-registration"
                     / "birth-registrations" / "run_01" / "dbt.json")
    assert json.loads(dataset_file.read_text())["verified"] == verified


def test_write_qa_result_with_no_verified_writes_no_dataset_file(tmp_path):
    """A tool that produced no record for any dataset writes only its
    raw output - not an empty file under each dataset, which would
    assert the tool ran there and found nothing."""
    out_path = write_qa_result("agency", "collection", "run_01", "2026-01-01T00:00:00Z", "dbt", {},
                                results_dir=tmp_path)

    assert [p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.json")] == [
        "agency/collection/_raw/run_01/dbt.json"]
    assert json.loads(out_path.read_text())["verified"] is None


def test_write_qa_result_stamps_run_by_alongside_run_timestamp(tmp_path):
    out_path = write_qa_result("agency", "dataset", "run_01", "2026-01-01T00:00:00Z", "dataset_stats", {},
                                run_by="keith@example.com", results_dir=tmp_path)

    written = json.loads(out_path.read_text())
    assert written["run_by"] == "keith@example.com"


def test_write_qa_result_defaults_run_by_to_none(tmp_path):
    out_path = write_qa_result("agency", "dataset", "run_01", "2026-01-01T00:00:00Z", "dbt", {},
                                results_dir=tmp_path)

    written = json.loads(out_path.read_text())
    assert written["run_by"] is None


def test_write_qa_result_overwrites_a_rerun_of_the_same_tool_and_run(tmp_path):
    write_qa_result("agency", "dataset", "run_01", "2026-01-01T00:00:00Z", "dbt", {"version": 1}, results_dir=tmp_path)
    out_path = write_qa_result("agency", "dataset", "run_01", "2026-01-02T00:00:00Z", "dbt", {"version": 2}, results_dir=tmp_path)

    written = json.loads(out_path.read_text())
    assert written["raw_output"] == {"version": 2}, \
        "re-running the same tool against the same run_id should overwrite, not duplicate/append"
