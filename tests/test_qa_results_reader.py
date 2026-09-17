"""Tests for qa_tools/common/qa_results_reader.py - the read side of
plans/publishing-and-history.md Thread B/Phase 2: reading committed
qa_results/ files' own `verified` field back into a flat results list,
with no live tool/DB access. Fixture-based, using write_qa_result()
itself to build the tmp_path tree so these tests exercise the exact
same on-disk shape the real writer produces."""
from __future__ import annotations

from qa_tools.common.qa_results_reader import list_run_ids, read_one, read_qa_results
from qa_tools.common.qa_results_writer import write_qa_result


def test_read_one_returns_the_verified_list(tmp_path):
    verified = [{"check_name": "dbt:not_null", "status": "pass"}]
    write_qa_result("agency", "dataset", "run_01", "2026-01-01T00:00:00Z", "dbt", {"raw": True},
                     verified=verified, results_dir=tmp_path)

    assert read_one("agency", "dataset", "run_01", "dbt", qa_results_dir=tmp_path) == verified


def test_read_one_returns_empty_list_for_a_missing_file(tmp_path):
    assert read_one("agency", "dataset", "run_99", "dbt", qa_results_dir=tmp_path) == []


def test_read_qa_results_concatenates_every_run_and_tool_in_order(tmp_path):
    write_qa_result("agency", "dataset", "run_01", "2026-01-01T00:00:00Z", "dbt", {},
                     verified=[{"check_name": "dbt:a"}], results_dir=tmp_path)
    write_qa_result("agency", "dataset", "run_01", "2026-01-01T00:00:00Z", "soda", {},
                     verified=[{"check_name": "soda:a"}], results_dir=tmp_path)
    write_qa_result("agency", "dataset", "run_02", "2026-01-02T00:00:00Z", "dbt", {},
                     verified=[{"check_name": "dbt:b"}], results_dir=tmp_path)

    results = read_qa_results("agency", "dataset", qa_results_dir=tmp_path)

    assert [r["check_name"] for r in results] == ["dbt:a", "soda:a", "dbt:b"], \
        "run_01 (dbt then soda, matching TOOL_ORDER) before run_02, not file-listing order"


def test_read_qa_results_returns_empty_list_for_an_unknown_dataset(tmp_path):
    assert read_qa_results("no-such-agency", "no-such-dataset", qa_results_dir=tmp_path) == []


def test_list_run_ids_and_read_qa_results_sort_numerically_not_lexicographically(tmp_path):
    # Real bug, 2026-09-17: both functions used to sort run_id directory
    # names as plain strings, which is only correct as long as every
    # run number has the same digit width - "run_100" < "run_20" <
    # "run_3" lexicographically, wrong once BDM's real run count grew
    # past a fixed zero-padding width (see generator/generate_runs.py's
    # own comment on the same bug). Written deliberately out of numeric
    # order so a no-op "sort" couldn't accidentally still pass.
    write_qa_result("agency", "dataset", "run_100", "2026-04-10T00:00:00Z", "dbt", {},
                     verified=[{"check_name": "dbt:hundred"}], results_dir=tmp_path)
    write_qa_result("agency", "dataset", "run_3", "2026-01-03T00:00:00Z", "dbt", {},
                     verified=[{"check_name": "dbt:three"}], results_dir=tmp_path)
    write_qa_result("agency", "dataset", "run_20", "2026-01-20T00:00:00Z", "dbt", {},
                     verified=[{"check_name": "dbt:twenty"}], results_dir=tmp_path)

    assert list_run_ids("agency", "dataset", qa_results_dir=tmp_path) == ["run_3", "run_20", "run_100"]

    results = read_qa_results("agency", "dataset", qa_results_dir=tmp_path)
    assert [r["check_name"] for r in results] == ["dbt:three", "dbt:twenty", "dbt:hundred"]


def test_read_qa_results_skips_a_tool_with_no_committed_file_for_a_run(tmp_path):
    # e.g. a run that only has dbt/soda/datacontract committed, no evidently -
    # shouldn't error, just contribute nothing for that tool.
    write_qa_result("agency", "dataset", "run_01", "2026-01-01T00:00:00Z", "dbt", {},
                     verified=[{"check_name": "dbt:a"}], results_dir=tmp_path)

    results = read_qa_results("agency", "dataset", qa_results_dir=tmp_path)

    assert [r["check_name"] for r in results] == ["dbt:a"]
