"""The file tree and the database get the SAME fan-out (REQ-PIPE-089).

WHY THIS EXISTS RATHER THAN A LATER COMPARISON. Phase 6 of this
requirement deletes 924 committed files, and the only honest basis for
doing that is having shown the database already holds what they hold.
The fan-out is where that could go wrong: one `write_qa_result()` call
becomes several files by rules that are not obvious - a record spanning
datasets belongs to none of them, raw output describes the invocation
and is recorded once, the two pseudo-tools describe a run rather than a
dataset - and re-implementing those rules for the database would be two
things to keep in step.

So there is one implementation, and this holds it to producing the same
answer on both sides. When the file half goes, the assertions that read
files go with it and the rest stays.
"""
from __future__ import annotations

import json

import pytest

from qa_tools.common import qa_results_writer, qa_store, supply_db

AGENCY = "registry-services"
COLLECTION = "civil-registration"
RUN = "fanout_run_01"
STAMP = "2026-09-27T10:00:00+08:00"

#: Two datasets' own records plus one that spans them, which is the
#: shape that makes the fan-out non-trivial.
VERIFIED = [
    {"check_id": "births.id.not_null", "check_name": "id not null",
     "dataset_id": "births", "status": "pass", "metric_value": 0.0},
    {"check_id": "births.sex.accepted_values", "check_name": "sex accepted",
     "dataset_id": "births", "status": "fail", "metric_value": 7.0},
    {"check_id": "registrations.id.not_null", "check_name": "id not null",
     "dataset_id": "registrations", "status": "pass", "metric_value": 0.0},
    {"check_id": "cross.births_vs_registrations", "check_name": "every birth registered",
     "dataset_id": "births", "status": "warn", "metric_value": 3.0},
]
SPANNING = "cross.births_vs_registrations"
RAW = {"results": [{"unique_id": "test.x", "status": "fail", "failures": 0}]}


@pytest.fixture
def written(tmp_path, monkeypatch, supply_dsn):
    """One real `write_qa_result()` call, both halves, nothing stubbed.

    The declared cross-table map is the one thing patched - it is
    normally parsed from the real check definitions, and pinning it
    keeps this test about the fan-out rather than about which of the
    257 real checks currently spans tables.
    """
    monkeypatch.setattr(qa_results_writer, "_declared_reads_tables",
                        lambda: {SPANNING: ["births", "registrations"]})
    with supply_db.connect(label="test-fanout") as conn:
        qa_store.ensure_schema(conn)
        conn.execute(f'TRUNCATE "{qa_store.SCHEMA}".run CASCADE')

    qa_results_writer.write_qa_result(
        AGENCY, COLLECTION, RUN, STAMP, "dbt", RAW,
        verified=[dict(r) for r in VERIFIED], run_by="keith@example.gov.au",
        results_dir=tmp_path)

    with supply_db.connect(label="test-fanout") as conn:
        qa_store.complete_run(conn, RUN)
        yield tmp_path, conn


def _from_files(root, scope):
    path = root / AGENCY / COLLECTION / scope / RUN / "dbt.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())["verified"] or []


def _ids(records):
    return sorted(r["check_id"] for r in records)


def test_each_datasets_own_records_match(written):
    root, conn = written
    for dataset in ("births", "registrations"):
        assert _ids(_from_files(root, dataset)) == \
            _ids(qa_store.results_for_run(conn, RUN, dataset_id=dataset)), \
            f"the tree and the database disagree about {dataset}'s own records"


def test_the_spanning_record_is_in_neither_datasets_results(written):
    root, conn = written
    for dataset in ("births", "registrations"):
        assert SPANNING not in _ids(_from_files(root, dataset))
        assert SPANNING not in _ids(qa_store.results_for_run(conn, RUN, dataset_id=dataset))


def test_the_spanning_record_is_in_the_cross_table_scope_on_both_sides(written):
    root, conn = written
    assert _ids(_from_files(root, "_cross-table")) == [SPANNING]
    assert _ids(qa_store.cross_table_results(conn, RUN)) == [SPANNING]


def test_no_record_is_lost_or_duplicated_across_the_fan_out(written):
    """The whole point: every record the caller handed over is recorded
    exactly once, somewhere, on both sides."""
    root, conn = written
    from_files = sorted(
        _ids(_from_files(root, "births")) + _ids(_from_files(root, "registrations"))
        + _ids(_from_files(root, "_cross-table")))
    from_db = sorted(
        _ids(qa_store.results_for_run(conn, RUN))
        + _ids(qa_store.cross_table_results(conn, RUN)))

    assert from_files == sorted(r["check_id"] for r in VERIFIED)
    assert from_db == from_files


def test_every_recorded_field_survives_the_round_trip(written):
    """Not just the ids. A verdict whose status or measurement changed on
    the way into a column would be a silently different history."""
    _, conn = written
    recorded = {r["check_id"]: r for r in qa_store.results_for_run(conn, RUN)}
    for original in VERIFIED:
        if original["check_id"] == SPANNING:
            continue
        row = recorded[original["check_id"]]
        assert row["status"] == original["status"]
        assert row["metric_value"] == original["metric_value"]
        assert row["check_name"] == original["check_name"]
        assert row["dataset_id"] == original["dataset_id"]


def test_raw_output_is_recorded_once_and_unmodified(written):
    """It describes the INVOCATION, so it belongs to no dataset - which
    the tree says with a `_raw` directory and the database says with a
    table of its own."""
    root, conn = written
    on_disk = json.loads(
        (root / AGENCY / COLLECTION / "_raw" / RUN / "dbt.json").read_text())
    assert on_disk["raw_output"] == RAW
    assert qa_store.tool_output_for(conn, RUN, "dbt") == RAW


def test_the_invocations_own_facts_come_from_the_call(written):
    """agency, collection and tool are what the caller said, not what a
    record happened to carry - the tree encoded them in the PATH, and a
    record claiming a different agency must not be able to file itself
    under one."""
    _, conn = written
    row = qa_store.results_for_run(conn, RUN)[0]
    assert (row["agency_id"], row["collection_id"], row["tool"]) == (AGENCY, COLLECTION, "dbt")


def test_a_second_write_of_the_same_tool_replaces_rather_than_doubles(written):
    """Re-running one tool is idempotent, which is what overwriting a
    file gave and what a naive append would lose."""
    root, conn = written
    qa_results_writer.write_qa_result(
        AGENCY, COLLECTION, RUN, STAMP, "dbt", RAW,
        verified=[dict(r) for r in VERIFIED], run_by="keith@example.gov.au",
        results_dir=root)
    qa_store.complete_run(conn, RUN)

    assert len(qa_store.results_for_run(conn, RUN)) == 3
    assert len(qa_store.cross_table_results(conn, RUN)) == 1
