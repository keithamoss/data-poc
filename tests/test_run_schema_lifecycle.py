"""A run's own schemas go when that run is done, not in a later sweep.

KEITH'S QUESTION, 2026-09-27, on seeing a pipeline print "discarded 54
per-run view schema(s)" at the end: shouldn't they be discarded when the
run is done, rather than separately later?

THE ANSWER IS YES, AND THE REASON THEY WERE NOT IS A DEAD ONE. The
orchestrators swept every run schema after the whole fan-out had
finished, and the comment said why: "dropping a schema is a WRITE,
DuckDB gives a writer an exclusive lock over the whole database, and a
worker that tidied up after itself would lock out every other worker
still reading." True of DuckDB, and DuckDB stopped being the warehouse
in REQ-PIPE-087. PostgreSQL locks the objects being dropped, not the
database, so a run dropping its own schema does not touch a sibling's.

WHY IT IS WORTH FIXING RATHER THAN LEAVING. A blanket sweep cannot tell
a schema left by an interrupted run from one belonging to a run that is
happening right now in another process - so the tidy-up was a hazard to
any concurrent ad-hoc check, and the window it was live for was the
whole length of the batch. Discarding per run removes both: nothing
sweeps what it did not create, and a schema exists for exactly as long
as the run that reads through it.

THE SWEEP DOES NOT GO AWAY, it stops being automatic - `mothman supply
tidy` is where a genuine orphan gets cleared, by someone who knows
nothing else is running.
"""
from __future__ import annotations

import pytest

from qa_tools.common import supply_db


@pytest.fixture
def db(supply_dsn):
    with supply_db.connect(label="test-schema-lifecycle") as conn:
        supply_db.ensure_schemas(conn)
        yield conn


def _schemas(conn) -> set[str]:
    return set(supply_db.run_schemas(conn)) | set(supply_db.dbt_schemas(conn))


def test_dropping_one_run_leaves_every_other_run_alone(db):
    """The property the blanket sweep could not offer."""
    for run_id in ("lifecycle_a", "lifecycle_b"):
        db.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.run_schema(run_id)}"')
        db.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.dbt_schema(run_id)}"')

    supply_db.drop_run_schemas(db, "lifecycle_a")

    remaining = _schemas(db)
    assert supply_db.run_schema("lifecycle_a") not in remaining
    assert supply_db.dbt_schema("lifecycle_a") not in remaining
    assert supply_db.run_schema("lifecycle_b") in remaining, \
        "dropping one run's schemas took another run's with it"
    assert supply_db.dbt_schema("lifecycle_b") in remaining

    supply_db.drop_run_schemas(db, "lifecycle_b")


def test_dbts_store_failures_audit_schema_goes_too(db):
    """dbt makes TWO schemas per run, not one.

    Found by running the real pipeline rather than by reading the code:
    `--store-failures` writes each failing test's offending rows into
    an audit relation, and dbt puts that in a schema of its own named
    `<target_schema>_dbt_test__audit`. The first version of the per-run
    discard dropped only `dbt_<run_id>` and left eighteen audit schemas
    sitting in the database - which the blanket sweep it replaced had
    been quietly clearing all along.
    """
    run_id = "lifecycle_audit"
    audit = supply_db.dbt_schema(run_id) + "_dbt_test__audit"
    db.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.run_schema(run_id)}"')
    db.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.dbt_schema(run_id)}"')
    db.execute(f'CREATE SCHEMA IF NOT EXISTS "{audit}"')

    supply_db.drop_run_schemas(db, run_id)

    assert audit not in _schemas(db), "dbt's audit schema outlived the run that made it"


def test_a_similarly_named_run_is_not_collateral(db):
    """The prefix test has to be exact-or-followed-by-underscore.
    `run_001` must not take `run_0011` with it, which a bare
    startswith() would."""
    db.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.dbt_schema("lifecycle_9")}"')
    db.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.dbt_schema("lifecycle_99")}"')

    supply_db.drop_run_schemas(db, "lifecycle_9")

    remaining = _schemas(db)
    assert supply_db.dbt_schema("lifecycle_9") not in remaining
    assert supply_db.dbt_schema("lifecycle_99") in remaining, \
        "dropping one run took a longer-named run's schema with it"
    supply_db.drop_run_schemas(db, "lifecycle_99")


def test_dropping_a_run_that_has_no_schemas_is_harmless(db):
    """A run that failed before staging anything still reaches the
    tidy-up, so it must not turn one failure into two."""
    assert supply_db.drop_run_schemas(db, "lifecycle_never_existed") == []


def test_a_finished_run_leaves_no_schema_behind(monkeypatch, tmp_path, bdm_raw_dir, bdm_duckdb_dir):
    """The real thing, through the real single-arrival entry point."""
    import shutil
    from pathlib import Path

    from fixture_ids import BDM_REF_RUN_ID
    from qa_tools.bdm import build_per_run_warehouses, orchestrate_bdm

    raw = tmp_path / "raw"
    raw.mkdir()
    monkeypatch.setattr(build_per_run_warehouses, "RAW_DIR", str(raw))
    monkeypatch.setattr(orchestrate_bdm, "write_qa_result", lambda *a, **k: None)
    for module_name in ("run_dbt_bdm", "run_soda_bdm", "run_datacontract_bdm", "run_evidently_bdm"):
        module = __import__(f"qa_tools.bdm.{module_name}", fromlist=[module_name])
        monkeypatch.setattr(module, "write_qa_result", lambda *a, **k: None)

    # ANY of the fixture's flat CSVs, found rather than named. The
    # names under bdm_raw_dir are the generator's own, not the run ids
    # recognition assigns, and a test that skips when it guesses wrong
    # is a test that quietly stops checking - which is the one thing
    # this suite is not allowed to do.
    candidates = sorted(Path(bdm_raw_dir).glob("*.csv"))
    assert candidates, f"the bdm_raw_dir fixture wrote no CSV at all: {bdm_raw_dir}"
    arrived = raw / "lifecycle_arrival.csv"
    shutil.copy(candidates[0], arrived)

    with supply_db.connect(read_only=True, label="test-before") as conn:
        before = _schemas(conn)

    run_id = "lifecycle_run"
    orchestrate_bdm.run_single(
        run_id, str(arrived), "2026-01-02", BDM_REF_RUN_ID, "", run_by="test@example.com")

    with supply_db.connect(read_only=True, label="test-after") as conn:
        after = _schemas(conn)

    assert supply_db.run_schema(run_id) not in after, \
        "the run finished and left its view schema behind"
    assert supply_db.dbt_schema(run_id) not in after, \
        "the run finished and left dbt's schema behind"
    assert before - after == set(), \
        f"the run removed schemas that were not its own: {sorted(before - after)}"


def test_two_runs_over_the_same_files_do_not_share_a_staged_table(db):
    """Two ad-hoc runs are two arrivals, whatever their names look like.

    THE BUG, found 2026-09-27 and pre-existing rather than introduced:
    a run staged with no receipt falls back to its RUN ID as the
    arrival, and `arrival_key()` keeps only the digits - which is
    correct for the instant it was written for and lossy for a run id.
    `adhoc_cp_run_001_20260927t030150` and
    `ref_cp_run_001_20260927t030150` both reduce to
    `00120260927030150`, so the two runs claimed one physical table.

    WHY THAT IS WORSE THAN A COLLIDING NAME. Re-loading a staged table
    does `DROP TABLE ... CASCADE`, which takes any view depending on
    it - so staging the second run silently destroyed the first run's
    views. It stayed hidden while the drift check read a CSV instead;
    removing that fallback (REQ-PIPE-102) is what surfaced it.
    """
    from qa_tools.common import supply_db as db_mod

    a = db_mod.staged_table("cp_notifications", "adhoc_cp_run_001_20260927t030150")
    b = db_mod.staged_table("cp_notifications", "ref_cp_run_001_20260927t030150")
    assert a != b, (
        "two differently-named runs over the same files resolved to one staged "
        f"table ({a}) - the second load would CASCADE away the first's views")


def test_a_real_receipt_instant_still_names_the_table_exactly_as_before(db):
    """The other half, and the reason the fix is where it is: a real
    arrival's physical name must not change, because committed history
    records it."""
    from qa_tools.common import supply_db as db_mod

    assert db_mod.staged_table("cp_clients", "2026-08-01T01:00:00+00:00") == \
        "cp_clients__202608010100000000"
