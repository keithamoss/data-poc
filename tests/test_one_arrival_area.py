"""A Child Protection supply lives in two places, not three (REQ-PIPE-102).

WHAT THIS REPLACED. Staging copied every delivered CP CSV into
`data/cp_raw/<run_id>/<table>.csv`, and the generator wrote each run
there as well as writing a real delivery. Both existed because
run_datacontract_cp.py and run_evidently_cp.py used to read those CSVs
off disk; REQ-QAC-088 pointed both at the warehouse and the reason went
with it. Birth Registrations never had the copy.

THE LINE THIS KEEPS. `data/deliveries/` stays - it is where a
supplier's files land, the thing the database is a copy OF. What goes
is the third copy nobody was reading.
"""
from __future__ import annotations

import psycopg
import pytest

import generator_isolation
from staging_support import stage_cp

_supply_files = generator_isolation.supply_files_under_data


def test_staging_writes_no_second_copy_of_the_file_it_was_given(tmp_path, supply_dsn):
    """Criterion 1, behaviourally. Stage a CSV from a directory of its
    own and assert no new supply file appears anywhere under data/."""

    source_dir = tmp_path / "delivery"
    source_dir.mkdir()
    csv = source_dir / "cp_case_workers.csv"
    csv.write_text("worker_id,full_name,office,_extract_timestamp\n"
                    "W1,A Worker,Perth,2026-01-01T00:00:00+00:00\n")

    before = _supply_files()
    stage_cp(
        "one_area_run", "cp_case_workers", str(csv), dataset_id="cp-case-workers")

    # The loader's own scratch CSV is written and removed inside the
    # call, so anything left is a copy that outlived it.
    new = _supply_files() - before
    assert not new, f"staging left a copy of the supply under data/: {sorted(str(p) for p in new)}"


def test_a_bdm_single_arrival_is_staged_from_where_it_is(tmp_path, supply_dsn, monkeypatch):
    """The Birth Registrations counterpart, through the real
    single-arrival entry point. run_single() used to copy every arriving
    file into data/raw/<run_id>.csv before staging it; the file it was
    handed is where it stays.

    The four tools are stubbed out - they are not what this is about,
    and they run in test_orchestrate_single_run.py - but staging is the
    real stage_table(), against this worker's own database.
    """
    from qa_tools.bdm import orchestrate_bdm
    from qa_tools.common import supply_db, trial

    staged_from = []
    from qa_tools.tools import stage

    real_stage_table = stage.stage_table

    def recording_stage_table(collection_id, run_id, table, csv_path, *args, **kwargs):
        staged_from.append(csv_path)
        return real_stage_table(collection_id, run_id, table, csv_path, *args, **kwargs)

    monkeypatch.setattr(stage, "stage_table", recording_stage_table)
    monkeypatch.setattr(orchestrate_bdm, "_run_one", lambda *a, **k: [])

    arrived = tmp_path / "incoming.csv"
    arrived.write_text("registration_id,child_family_name\nBR0001,SMITH\n")

    run_id = trial.trial_run_id()
    before = _supply_files()
    try:
        orchestrate_bdm.run_single(run_id, str(arrived), "2026-01-02",
                                   reference_run_id=None, run_by="test@example.com")
    finally:
        with supply_db.connect(label="test-one-arrival-area") as conn:
            trial.discard(conn, run_id)

    assert staged_from == [str(arrived)], \
        f"run_single() staged {staged_from}, not the file it was handed"
    new = _supply_files() - before
    assert not new, f"run_single() left a copy of the arrival under data/: {sorted(map(str, new))}"
    assert arrived.exists(), "the file handed in should be left alone, not moved"


class _UnreachableWarehouse:
    """A connection whose every data read fails the way a lost server
    does. Setting the search path succeeds, so the failure lands on the
    read itself - where a fallback would have to catch it."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, *args, **kwargs):
        if sql.lstrip().upper().startswith("SET "):
            return self
        raise psycopg.OperationalError("server closed the connection unexpectedly")


@pytest.mark.parametrize("compute", ["bdm", "cp"])
def test_a_warehouse_failure_fails_the_drift_check_rather_than_producing_a_number(
        compute, monkeypatch):
    """Criterion 4. A bare `except` that reads a CSV turns a database
    failure into a plausible-looking number, which is the shape this
    project argues against everywhere else. So when the warehouse read
    fails, the drift check raises; it does not return a result."""
    from qa_tools.common import supply_db
    from qa_tools.tools import run_evidently

    monkeypatch.setattr(supply_db, "connect", lambda *a, **k: _UnreachableWarehouse())
    # Recording is stubbed so that the only database read left in the
    # path is the warehouse read under test - otherwise a fallback could
    # hide behind the writer's own failure to connect.
    recorded = []
    monkeypatch.setattr(run_evidently, "write_qa_result",
                        lambda *a, **k: recorded.append(k))
    with pytest.raises(psycopg.OperationalError):
        run_evidently.evaluate(
            {"bdm": "civil-registration", "cp": "child-protection"}[compute],
            "drift_failure_run", "2026-01-02T00:00:00+08:00", reference_run_id=None)
    assert recorded == [], "a drift result was recorded from a failed warehouse read"
