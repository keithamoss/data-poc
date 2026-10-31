"""Run inside a copy built by tests/thirty_linked_datasets.py (REQ-TEST-339):
generate the six fake collections, then replay them as ONE receipt-ordered
stream through cli.pipeline._run_stream - the function `mothman pipeline run`
calls for collections sharing a calendar - against the database
MOTHMAN_SUPPLY_DSN names.

THE ONE THING ADDED is a stopwatch: orchestrate.run_one, which the stream's
per-arrival steps look up at call time, is wrapped to record how long each
QA run took (criterion 4). The run itself is unchanged. The timings are
written to the path given as the only argument.

Invoked as `python tests/thirty_linked_run.py <out.json>` with the copy as
the working directory, so every import resolves to the copy's own files.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))


def main(out: str) -> None:
    from cli import pipeline
    from qa_tools import collections
    from qa_tools.tools import orchestrate

    import thirty_linked_datasets as fixture

    timings: list[dict] = []
    real = orchestrate.run_one

    def timed(collection_id, entry, *args, **kwargs):
        start = time.perf_counter()
        try:
            return real(collection_id, entry, *args, **kwargs)
        finally:
            timings.append({"collection": collection_id, "run_id": entry["run_id"],
                            "seconds": round(time.perf_counter() - start, 2)})

    orchestrate.run_one = timed
    ids = [c["id"] for c in fixture.sources()] + [fixture.PRODUCT["collection"]]
    start = time.perf_counter()
    try:
        pipeline._run_stream([collections.by_id(i) for i in ids], sequential=False)
    finally:
        evidence = {"runs": timings, "stream_seconds": round(time.perf_counter() - start, 1)}
        Path(out).write_text(json.dumps(evidence))
    evidence |= recorded(fixture)
    Path(out).write_text(json.dumps(evidence))


def recorded(fixture) -> dict:
    """What the run RECORDED, read back after it: each run's resolved reads
    (qa.tables_read - logical table, physical table, supply, and whether it
    came from staging or the period), what each tool was asked for, the runs
    a decision caused, and the supply each linked dataset's period held when
    the linkage product was checked and holds now."""
    from qa_tools.common import decision_log, qa_store, supply_db

    s = qa_store.SCHEMA
    out: dict = {"tables_read": {}, "asked": {}, "held_at_linkage": {}, "held_now": {}}
    with supply_db.connect(read_only=True, label="mothman:t339-evidence") as conn:
        runs = conn.execute(
            f'SELECT run_key, collection_id, scope, period, reads_table, caused_by_decision, '
            f'run_timestamp FROM "{s}".run ORDER BY run_seq').fetchall()
        out["recorded_runs"] = [dict(zip(("run_key", "collection", "scope", "period",
                                          "reads_table", "caused_by_decision", "run_timestamp"),
                                         r)) for r in runs]
        linkage = [r for r in out["recorded_runs"] if r["collection"] == fixture.PRODUCT["collection"]]
        for r in linkage:
            out["tables_read"][r["run_key"]] = [dict(zip(("logical", "physical", "supply", "source"), x))
                                                for x in conn.execute(
                f'SELECT logical_table, physical_table, supply, source FROM "{s}".tables_read '
                "WHERE run_key = ? ORDER BY logical_table", [r["run_key"]]).fetchall()]
            out["asked"][r["run_key"]] = {tool: sorted(c for (c,) in conn.execute(
                f'SELECT check_id FROM "{s}".asked_check WHERE run_key = ? AND tool = ?',
                [r["run_key"], tool]).fetchall()) for tool in ("soda", "dbt", "datacontract")}
        first = next(r for r in linkage if r["scope"] == "arrival")
        for d in fixture.linked():
            out["held_at_linkage"][d["id"]] = decision_log.promoted_into(
                conn, d["id"], fixture.PERIOD, first["run_timestamp"])
            out["held_now"][d["id"]] = decision_log.promoted_into(conn, d["id"], fixture.PERIOD)
    return out


if __name__ == "__main__":
    sys.path.insert(1, str(Path(__file__).resolve().parent))
    main(sys.argv[1])
