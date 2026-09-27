"""One write_qa_result() call fans out by rules, and this holds them.

WHY THIS EXISTS. One call becomes several recorded things by rules that
are not obvious - a record spanning datasets belongs to NONE of them, raw
output describes the invocation and is recorded once, the two
pseudo-tools describe a run rather than a dataset - and getting any of
them wrong is silent: the results are all still there, just attributed to
the wrong thing.

IT USED TO COMPARE TWO IMPLEMENTATIONS. While REQ-PIPE-089 was in
flight, write_qa_result() wrote both a committed file tree and the
database, and this module's job was to prove they produced the SAME
fan-out - which was the only honest basis for then deleting 924 files. It
said so itself: "when the file half goes, the assertions that read files
go with it and the rest stays." That is what happened, so what remains
asserts the rules directly rather than by agreement between two places.

WHAT THE COMPARISON WAS WORTH, recorded because it cannot be re-run: it
is what established that nothing was lost in the move, at a point when
both answers existed side by side. A later comparison would have had
nothing to compare against.
"""
from __future__ import annotations

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
def written(monkeypatch, supply_dsn):
    """One real `write_qa_result()` call, nothing stubbed.

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
        verified=[dict(r) for r in VERIFIED], run_by="keith@example.gov.au")

    with supply_db.connect(label="test-fanout") as conn:
        qa_store.complete_run(conn, RUN)
        yield conn


def _ids(records):
    return sorted(r["check_id"] for r in records)


def test_each_dataset_gets_its_own_records_and_no_others(written):
    conn = written
    assert _ids(qa_store.results_for_run(conn, RUN, dataset_id="births")) == [
        "births.id.not_null", "births.sex.accepted_values"]
    assert _ids(qa_store.results_for_run(conn, RUN, dataset_id="registrations")) == [
        "registrations.id.not_null"]


def test_the_spanning_record_is_in_neither_datasets_results(written):
    """Even though its own record NAMES `births` as its dataset. Which of
    the tables it spans got to own it was arbitrary, and the
    arbitrariness is the whole defect (REQ-QAC-037)."""
    conn = written
    for dataset in ("births", "registrations"):
        assert SPANNING not in _ids(qa_store.results_for_run(conn, RUN, dataset_id=dataset))


def test_the_spanning_record_is_in_the_cross_table_scope(written):
    assert _ids(qa_store.cross_table_results(written, RUN)) == [SPANNING]


def test_no_record_is_lost_or_duplicated_across_the_fan_out(written):
    """The whole point: every record the caller handed over is recorded
    exactly once, somewhere."""
    conn = written
    everywhere = sorted(
        _ids(qa_store.results_for_run(conn, RUN))
        + _ids(qa_store.cross_table_results(conn, RUN)))
    assert everywhere == sorted(r["check_id"] for r in VERIFIED)


def test_every_recorded_field_survives_the_round_trip(written):
    """Not just the ids. A verdict whose status or measurement changed on
    the way into a column would be a silently different history."""
    recorded = {r["check_id"]: r for r in qa_store.results_for_run(written, RUN)}
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
    the database says by holding it in a table of its own, keyed by the
    run and the tool rather than by a dataset."""
    assert qa_store.tool_output_for(written, RUN, "dbt") == RAW


def test_the_invocations_own_facts_come_from_the_call(written):
    """agency, collection and tool are what the caller said, not what a
    record happened to carry - they used to be encoded in a file PATH, and a
    record claiming a different agency must not be able to file itself
    under one."""
    row = qa_store.results_for_run(written, RUN)[0]
    assert (row["agency_id"], row["collection_id"], row["tool"]) == (AGENCY, COLLECTION, "dbt")


def test_a_second_write_of_the_same_tool_replaces_rather_than_doubles(written):
    """Re-running one tool is idempotent, which is what overwriting a
    file used to give for free and what a naive append would lose."""
    conn = written
    qa_results_writer.write_qa_result(
        AGENCY, COLLECTION, RUN, STAMP, "dbt", RAW,
        verified=[dict(r) for r in VERIFIED], run_by="keith@example.gov.au")
    qa_store.complete_run(conn, RUN)

    assert len(qa_store.results_for_run(conn, RUN)) == 3
    assert len(qa_store.cross_table_results(conn, RUN)) == 1
