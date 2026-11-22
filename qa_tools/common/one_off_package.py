"""What a one-off's LOAD records about its package as a whole - the default
check layer's two facts no tool can see (REQ-QAC-441 criteria 2 and 3;
REQ-PIPE-442 criterion 4).

- A DECLARED TABLE THAT NEVER ARRIVED is a failing `table_arrived` result, in
  a run of its own for that dataset - named as its arrival's run would have
  been, at the load's receipt instant - because no arrival exists to hang it
  on, and its dataset then reads Fail rather than No data (REQ-DASH-436
  criterion 2). A declared table that did arrive passes the same check when
  its file is screened (qa_tools/common/file_checks.py).
- A FILE THE RECIPE DOES NOT DECLARE is never filed (hand_filing refuses a
  file no arrival pattern matches, architect A2) and is recorded as a failing
  `undeclared_file` result naming it. One result for the package, passing
  where every file is declared, recorded against the one-off's first counted
  dataset - SETTLED by Keith 2026-11-22 ('first dataset + home'): a file that
  belongs to no table has no dataset of its own, and the first counted one
  keeps the failure in the one-off's own status rather than in a derived
  product's, which no rollup counts; the page also names the file once on the
  one-off's home view (REQ-DASH-444).

QA CARRIES ON PAST BOTH (Keith 2026-11-21, round 2 Q7 (a)): these are
results, never a refusal of the package.

The results are the one-off's own file checks, defined in its check workspace
(qa_tools/common/one_off_checks.package_checks) from the kind's template, so
their words and definition fingerprints come from where every file check's
do.
"""
from __future__ import annotations

from dataclasses import dataclass

from asset_model import asset_time
from asset_model import file_check_definitions as defs


@dataclass(frozen=True)
class Findings:
    """What the package holds against what the recipe declares."""

    missing: tuple            # extraction_checks.Table, declared and not in the package
    undeclared: tuple[str, ...]   # file names in the package the recipe does not name
    present: tuple            # extraction_checks.Table, declared and in the package


def findings(package_files, tables, recipe_file: str) -> Findings:
    files = set(package_files) - {recipe_file}
    declared = {t.file for t in tables}
    return Findings(missing=tuple(t for t in tables if t.file not in files),
                    undeclared=tuple(sorted(files - declared)),
                    present=tuple(t for t in tables if t.file in files))


def run_id_for(table: str, received_at) -> str:
    """The run a declared table's arrival at `received_at` is - the spelling
    recognition gives it (asset_model/arrivals.py)."""
    return f"{table}__{asset_time.arrival_key(received_at)}"


def _record(conn, run_id: str, dataset_id: str, check: str, status: str, words: str, *,
            delivery: str, filename: str) -> None:
    from asset_model import hierarchy
    from qa_tools.common import qa_results_writer, qa_store, sample_data

    dataset = hierarchy.dataset(dataset_id)
    by_check = {d.check: d for d in defs.definitions()}
    definition = by_check[check]
    qa_store.ensure_schema(conn)
    qa_store.register_run_if_absent(conn, run_key=run_id, agency_id=dataset.agency_id,
                                    collection_id=dataset.collection_id,
                                    run_timestamp=asset_time.now().isoformat())
    qa_store.record_file_results(
        conn, run_id, [{"dataset_id": dataset_id, "check_id": defs.check_id_for(dataset, check),
                        "check_name": definition.name, "status": status, "dimension": None,
                        "engine": defs.TOOL, "finding": words,
                        "severity": definition.severity}],
        agency_id=dataset.agency_id, collection_id=dataset.collection_id,
        supply_state=sample_data.supply_state(dataset_id), load_attempt=None,
        delivery=delivery, filename=filename,
        fingerprints=qa_results_writer.fingerprints_for(run_id))


def _undeclared_words(f: Findings) -> tuple[str, str]:
    if f.undeclared:
        return "fail", (f"the supply holds {', '.join(f.undeclared)}, which the recipe does "
                        f"not declare - not filed and not checked")
    return "pass", "every file in the supply is one the recipe declares"


def home_of(tables):
    """The dataset the package's undeclared-file result is recorded against:
    the first counted one, else the first (SETTLED, module docstring)."""
    return next((t for t in tables if not t.derived), tables[0])


def record_missing(table, received_at, run_by: str, *, delivery: str | None,
                   undeclared: Findings | None = None) -> str:
    """A declared table that never arrived: a run of its own, opened and
    finished with its failing result - and the package's undeclared-file
    result where this dataset is its home - so it is visible like any run."""
    from asset_model import hierarchy
    from qa_tools.common import qa_results_writer, supply_db

    run_id = run_id_for(table.table, received_at)
    dataset = hierarchy.dataset(table.dataset_id)
    stamp = asset_time.now().isoformat()
    qa_results_writer.open_run(dataset.agency_id, dataset.collection_id, run_id, stamp,
                               run_by, dataset_id=table.dataset_id, delivery=delivery,
                               received_at=received_at.isoformat())
    try:
        with supply_db.connect(label="mothman:one-off-package") as conn:
            _record(conn, run_id, table.dataset_id, defs.TABLE_ARRIVED, "fail",
                    f"{table.file} is declared by the recipe and is not in the supply",
                    delivery=delivery or "", filename=table.file)
            if undeclared is not None:
                status, words = _undeclared_words(undeclared)
                _record(conn, run_id, table.dataset_id, defs.UNDECLARED_FILE, status, words,
                        delivery=delivery or "", filename=", ".join(undeclared.undeclared))
    except BaseException as exc:
        qa_results_writer.close_attempt(run_id, exc)
        raise
    qa_results_writer.finish_run(run_id)
    return run_id


def record_undeclared(f: Findings, run_id: str, dataset_id: str, *, delivery: str) -> str:
    """The package's undeclared-file result against an ARRIVED home dataset's
    run, written before that run is opened, as a file check's result is at
    staging. Returns its status."""
    from qa_tools.common import supply_db

    status, words = _undeclared_words(f)
    with supply_db.connect(label="mothman:one-off-package") as conn:
        _record(conn, run_id, dataset_id, defs.UNDECLARED_FILE, status, words,
                delivery=delivery, filename=", ".join(f.undeclared))
    return status
