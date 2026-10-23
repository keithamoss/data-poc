"""A supply's status from the newest result of every check that READ it -
one function (REQ-PIPE-121 NFR 4, shared with REQ-DASH-126 and the status
REQ-PIPE-130 criterion 11 records at promotion).

WHICH RESULTS ARE ABOUT A SUPPLY is results_about's answer, the one
function the promotion gate, the dashboard build (pipeline.red_promoted)
and carried.decide all read (REQ-PIPE-279 criterion 21) - from what each
RESULT recorded reading, never from whose run it was nor from a run's
record of physical names.

NEWEST IS THE LATER-OPENED RUN (REQ-PIPE-279 criterion 9; Keith, K1 = A):
qa.run.run_seq, the order runs were opened for evaluation. It replaced the
asset's timeline - a decision's effective time, a supply's receipt - which
named an earlier-opened run newest whenever a decision was recorded after
the fact, though only the later run had seen it.

READ-ONLY, and only recorded QA results - never a supply row. So it is
safe on the dashboard build's path as well as the gate's.
"""
from __future__ import annotations

from qa_tools.common import qa_store, supply_db


def results_about(conn, dataset_id: str, supply: str) -> list[dict]:
    """Every completed, agreed result about `supply` of `dataset_id`, oldest
    first by run_seq and then as each run recorded them - so the last
    result per check is the newest.

    A RESULT IS ABOUT A SUPPLY BY WHAT IT RECORDED, in one of five states:

      its run's own   a single-table result recorded under a run whose
                      qa.run.supply_id is this supply - such a result reads
                      only its run's own supply (criterion 3), so the run's
                      supply is its supply
      its file        a file check's, whose recorded delivery and file are
                      one of this supply's files (supply_files.resolve): a
                      pair's arrival run is shared by both its supplies, and
                      which file each one IS is settled later
                      (post-build-review #262 D2). A supply never filed has
                      no recorded file, so its run's own rule applies
      READ            a cross-table result whose qa.check_read for this
                      dataset's table names this supply - a contested
                      table's included, read as the supply it fell through to
      HELD            the supply was deliberately not read: NOT about it
      ABSENT          nothing of the table was read: about no supply of it
                      (K2 = A - it shows only where its check is declared)
      NO-SUPPLY       a sample's or a trial's table: about no supply at all

    Only the first two are about the supply, and that is the whole rule.
    The run-level qa.tables_read is not consulted: it says what a RUN read,
    and matching it by physical name was a guess about each result.

    TIE-BREAK: none is needed. run_seq is unique per run; within a run, the
    order the run recorded its results (qa.check_result.id), exactly as one
    run's own reader reads them.
    """
    from qa_tools.common import hierarchy
    from qa_tools.common import qa_results_reader as reader

    from qa_tools.common import supply_files

    table = hierarchy.dataset(dataset_id).table
    s = qa_store.SCHEMA
    own = "(r.dataset_id = ? AND r.supply_id = ?)"
    found = supply_files.resolve(conn, dataset_id, supply)
    if found is not None and found.delivery is not None:
        files = ([found.filename] if found.filename
                 else supply_files.files_in_order(conn, dataset_id, found.delivery)
                 if len(found.own) > 1 else [])
        by_file = "(c.dataset_id = ? AND c.delivery = ? AND c.filename = ANY(?))"
        by_file_params = [dataset_id, found.delivery, files]
    else:
        by_file, by_file_params = own, [dataset_id, supply]
    cursor = conn.execute(
        f'SELECT c.* FROM "{s}".check_result_visible c '
        f'JOIN "{s}".run_visible r ON r.run_key = c.run_key '
        "WHERE c.supply_state = ? AND ("
        f"(c.scope NOT IN (?, ?) AND {own}) "
        f"OR (c.scope = ? AND {by_file}) "
        f'OR EXISTS (SELECT 1 FROM "{s}".check_read k WHERE k.check_result_id = c.id '
        "AND k.logical_table = ? AND k.state = ? AND k.supply_id = ?)) "
        "ORDER BY r.run_seq, c.id",
        [qa_store.AGREED, qa_store.CROSS_TABLE_SCOPE, qa_store.FILE_SCOPE, dataset_id, supply,
         qa_store.FILE_SCOPE, *by_file_params, table, qa_store.READ, supply])
    return reader.records_from(cursor.description, cursor.fetchall())


def latest_results(conn, dataset_id: str, supply: str) -> list[dict]:
    """The newest recorded result per check about this supply
    (results_about), the later-opened run's where two recorded one.
    Includes other datasets' results; status() keeps only what contributes
    to this dataset."""
    latest: dict[str, dict] = {}
    for record in results_about(conn, dataset_id, supply):
        latest[record["check_id"]] = record
    return list(latest.values())


def status(conn: supply_db.SupplyConnection, dataset_id: str, supply: str, *,
           reads: dict[str, list[str]] | None = None) -> str | None:
    """green/amber/red (or a quiet status) from the newest result of every
    check contributing to this dataset that read this supply; None where
    nothing did."""
    from qa_tools.common import promotion

    reads = reads if reads is not None else promotion._declared_reads()
    return promotion.status_of(dataset_id, latest_results(conn, dataset_id, supply),
                               reads=reads)
