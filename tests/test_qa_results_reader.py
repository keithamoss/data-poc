"""Tests for qa_tools/common/qa_results_reader.py - reading QA history
back into a flat results list, with no live tool access.

Still driven through `write_qa_result()` rather than by inserting
rows, so these exercise the exact shape the real writer produces -
which mattered when the history was files and matters more now that
it is a schema.

EVERY RUN HERE IS COMPLETED EXPLICITLY, and that is the behaviour
under test as much as the setup. REQ-PIPE-089 criterion 13 makes a
run observable only once it says it has finished, so a fixture that
writes results and stops is correctly invisible - which is what four
of these tests discovered when the reader moved.
"""
from __future__ import annotations

import pytest

from qa_tools.common import qa_store, supply_db
from qa_tools.common.qa_results_reader import list_run_ids, read_one, read_qa_results
from qa_tools.common.qa_results_writer import (
    finish_run, open_run, write_qa_result)


@pytest.fixture(autouse=True)
def clean_history(supply_dsn):
    """An empty QA history on this worker's own database.

    Per-test isolation used to come free from `tmp_path`; a worker's
    database is shared across the tests that run on it.
    """
    with supply_db.connect(label="test-qa-reader") as conn:
        qa_store.ensure_schema(conn)
        conn.execute(f'TRUNCATE "{qa_store.SCHEMA}".run CASCADE')
        yield conn


def _done(*run_ids):
    """Attribute each run and mark it finished.

    A real orchestrator calls `open_run` BEFORE its tools write and
    `finish_run` after; these fixtures call the pair together, which
    reaches the same state because registration coalesces and never
    touches the completion marker. Both halves are needed: criterion 6
    refuses to finish a run that cannot say who ran it, which is what
    these tests hit first when they tried to finish an anonymous one.
    """
    for run_id in run_ids:
        open_run("agency", "dataset", run_id, "2026-01-01T00:00:00+00:00",
                 "tests@example.gov.au")
        finish_run(run_id)


def test_read_one_returns_the_verified_list(tmp_path):
    """A real record round-trips EXACTLY.

    THE FULL KEY SET, not a convenient subset, because that is the
    claim. Counted across the whole committed corpus before writing
    this: every `verified` record carries the same twenty keys whatever
    their values, and a reader that drops the null ones or adds one the
    record never had has changed the shape - which
    `pipeline/build_dashboard_data.py` finds out about two transforms
    later, by indexing a key that is no longer there.

    `tool` is deliberately absent: it is a fact about the invocation,
    stored as a column because the write is keyed on it, and downstream
    derives it from `check_id`.
    """
    verified = [{
        "agency_id": "agency", "collection_id": "dataset", "dataset_id": "dataset",
        "check_id": "dbt:not_null", "check_name": "dbt:not_null",
        "column_name": "id", "dimension": "completeness", "label": "id is never null",
        "status": "pass", "metric_value": 0.0, "unit": "rows",
        "warn_threshold": 1.0, "fail_threshold": 5.0,
        "row_count_total": 100, "row_count_invalid": 0,
        "on_fail_action": "warn", "engine": "dbt-core",
        "failing_sample_keys": [],
        "run_id": "run_01", "run_timestamp": "2026-01-01T00:00:00+00:00",
    }]
    write_qa_result("agency", "dataset", "run_01", "2026-01-01T00:00:00+00:00", "dbt",
                     {"raw": True}, verified=[dict(verified[0])], results_dir=tmp_path)
    _done("run_01")

    assert read_one("agency", "dataset", "run_01", "dbt") == verified

def test_read_one_returns_empty_list_for_a_missing_file(tmp_path):
    assert read_one("agency", "dataset", "run_99", "dbt") == []


def test_read_qa_results_concatenates_every_run_and_tool_in_order(tmp_path):
    write_qa_result("agency", "dataset", "run_01", "2026-01-01T00:00:00Z", "dbt", {},
                     verified=[{"check_id": "dbt:a", "check_name": "dbt:a", "status": "pass"}], results_dir=tmp_path)
    write_qa_result("agency", "dataset", "run_01", "2026-01-01T00:00:00Z", "soda", {},
                     verified=[{"check_id": "soda:a", "check_name": "soda:a", "status": "pass"}], results_dir=tmp_path)
    write_qa_result("agency", "dataset", "run_02", "2026-01-02T00:00:00Z", "dbt", {},
                     verified=[{"check_id": "dbt:b", "check_name": "dbt:b", "status": "pass"}], results_dir=tmp_path)

    _done("run_01", "run_02")

    results = read_qa_results("agency", "dataset")

    assert [r["check_name"] for r in results] == ["dbt:a", "soda:a", "dbt:b"], \
        "run_01 (dbt then soda, matching TOOL_ORDER) before run_02, not file-listing order"


def test_read_qa_results_returns_empty_list_for_an_unknown_dataset(tmp_path):
    assert read_qa_results("no-such-agency", "no-such-dataset") == []


def test_list_run_ids_and_read_qa_results_sort_numerically_not_lexicographically(tmp_path):
    # Real bug, 2026-09-17: both functions used to sort run_id directory
    # names as plain strings, which is only correct as long as every
    # run number has the same digit width - "run_100" < "run_20" <
    # "run_3" lexicographically, wrong once BDM's real run count grew
    # past a fixed zero-padding width (see generator/generate_runs.py's
    # own comment on the same bug). Written deliberately out of numeric
    # order so a no-op "sort" couldn't accidentally still pass.
    write_qa_result("agency", "dataset", "run_100", "2026-04-10T00:00:00Z", "dbt", {},
                     verified=[{"check_id": "dbt:hundred", "check_name": "dbt:hundred", "status": "pass"}], results_dir=tmp_path)
    write_qa_result("agency", "dataset", "run_3", "2026-01-03T00:00:00Z", "dbt", {},
                     verified=[{"check_id": "dbt:three", "check_name": "dbt:three", "status": "pass"}], results_dir=tmp_path)
    write_qa_result("agency", "dataset", "run_20", "2026-01-20T00:00:00Z", "dbt", {},
                     verified=[{"check_id": "dbt:twenty", "check_name": "dbt:twenty", "status": "pass"}], results_dir=tmp_path)

    _done("run_100", "run_3", "run_20")

    assert list_run_ids("agency", "dataset") == ["run_3", "run_20", "run_100"]

    results = read_qa_results("agency", "dataset")
    assert [r["check_name"] for r in results] == ["dbt:three", "dbt:twenty", "dbt:hundred"]


def test_read_qa_results_skips_a_tool_with_no_committed_file_for_a_run(tmp_path):
    # e.g. a run that only has dbt/soda/datacontract committed, no evidently -
    # shouldn't error, just contribute nothing for that tool.
    write_qa_result("agency", "dataset", "run_01", "2026-01-01T00:00:00Z", "dbt", {},
                     verified=[{"check_id": "dbt:a", "check_name": "dbt:a", "status": "pass"}], results_dir=tmp_path)

    _done("run_01")

    results = read_qa_results("agency", "dataset")

    assert [r["check_name"] for r in results] == ["dbt:a"]
