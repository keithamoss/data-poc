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
any check somebody was running right then, and the window it was the
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
    from qa_tools.bdm import orchestrate_bdm

    # NOTHING TO REDIRECT ON DISK (REQ-PIPE-102): run_single() stages
    # the file where it is rather than copying it into a raw
    # directory, so there is no longer one to point elsewhere.
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
    arrived = tmp_path / "lifecycle_arrival.csv"
    shutil.copy(candidates[0], arrived)

    with supply_db.connect(read_only=True, label="test-before") as conn:
        before = _schemas(conn)

    run_id = "lifecycle_run"
    orchestrate_bdm.run_single(
        run_id, str(arrived), "2026-01-02", BDM_REF_RUN_ID, run_by="test@example.com")

    with supply_db.connect(read_only=True, label="test-after") as conn:
        after = _schemas(conn)

    assert supply_db.run_schema(run_id) not in after, \
        "the run finished and left its view schema behind"
    assert supply_db.dbt_schema(run_id) not in after, \
        "the run finished and left dbt's schema behind"
    assert before - after == set(), \
        f"the run removed schemas that were not its own: {sorted(before - after)}"


def test_two_runs_over_the_same_files_do_not_share_a_staged_table(db):
    """Two runs with no receipt are two arrivals, whatever their names
    look like.

    THE IDS BELOW ARE HISTORICAL. `adhoc_`/`ref_` is the shape this
    project minted before REQ-PIPE-103 replaced it with a run id from
    recognition for a kept supply and `trial_<stamp>` for a trial.
    They are kept verbatim because they are what actually reproduced
    the bug, and because the rule they pin holds for any id, not just
    the two shapes we happen to mint today.

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


def test_a_long_run_id_still_fits_a_postgres_identifier(db):
    """Distinct is not enough - it has to fit.

    Making the run-id arrival segment lossless (so two runs with no
    receipt stop sharing a staged table) made it LONG, and the run
    ids of the day were long to begin with:
    `adhoc_birth_registrations_2026_09_20_20260927t041329z` produced
    a 74-byte table name against
    PostgreSQL's 63-byte limit. The loader's own guard caught it and
    refused rather than letting the name truncate into a collision,
    which is the right failure - but a real `mothman bdm qa --file`
    could not run at all.
    """
    from qa_tools.common import supply_db as db_mod

    long_id = "adhoc_birth_registrations_2026_09_20_20260927t041329z"
    name = db_mod.staged_table("birth_registrations", long_id)
    assert len(name.encode()) <= 63, f"{name} is {len(name.encode())} bytes"

    # AND STILL DISTINCT. Truncation alone would collide two runs of
    # the same dataset on the same day, which is the bug this segment
    # exists to prevent.
    sibling = db_mod.staged_table(
        "birth_registrations", "adhoc_birth_registrations_2026_09_20_20260927t041330z")
    assert name != sibling, "two long run ids collapsed to one staged table"


def test_a_short_run_id_is_left_readable(db):
    """The common case must not pay for the long one - `run_001` is a
    name a person reads in a table listing."""
    from qa_tools.common import supply_db as db_mod

    assert db_mod.staged_table("birth_registrations", "run_001") == \
        "birth_registrations__run_001"


def test_an_arrival_segment_never_contains_the_separator(db):
    """`__` separates the parts of a staged table name, so a segment
    containing one splits the name in the wrong place.

    Found by running the real hand-supplied path: the bounded segment was
    built as `<truncated>_<digest>`, the truncation ended on an
    underscore, and the result was
    `birth_registrations__adhoc_pytest_bdm_dirty__f5108854`.
    split_staged() then read the arrival as `adhoc_pytest_bdm_dirty`
    and the digest as an ORDINAL - so the run's views resolved
    nothing and dbt failed on a table that had just been staged.
    split_staged's own docstring states the invariant ("the arrival
    key and ordinal are digits"); nothing enforced it.
    """
    from qa_tools.common import supply_db as db_mod

    for run_id in ("adhoc_pytest_bdm_dirty_20260927t042417z",
                   "adhoc_birth_registrations_2026_09_20_20260927t041329z",
                   "run_001",
                   "a__deliberately__doubled__id"):
        segment = db_mod.arrival_segment(run_id)
        assert "__" not in segment, f"{run_id!r} -> {segment!r} contains the separator"
        physical = db_mod.staged_table("birth_registrations", run_id)
        parsed = db_mod.split_staged(physical)
        assert parsed is not None, f"{physical} does not parse as a staged table"
        assert parsed[1] == segment, \
            f"{physical} parsed its arrival as {parsed[1]!r}, not {segment!r}"
        assert parsed[2] == "", f"{physical} parsed a spurious ordinal {parsed[2]!r}"


class TestARunGivesBackItsDiskSpaceToo:
    """A real leak, found 2026-09-27 while auditing REQ-PIPE-087 for
    sign-off: 1.9 GB in `data/dbt_scratch/` across 80 DSN digests, one
    of them holding 101 per-run directories.

    THE REASONING WAS APPLIED TO HALF THE PROBLEM. REQ-PIPE-068 made a
    run's schemas self-discarding, and supply_db.drop_orphan_run_schemas'
    own docstring gives the reason in as many words - "a per-run thing
    that nothing deletes is just a leak with a tidier name". dbt's
    on-disk target/ is per-run by exactly the same mechanism
    (dbt_target_path(run_id), so two parallel workers cannot clobber
    each other's manifest.json), and nothing ever removed it.

    SAFE TO REMOVE AT THIS POINT because dbt's artefacts are read
    DURING evaluation - run_results.json and manifest.json are parsed
    by evaluate_dbt_*() - and this tidy-up runs in _run_one's finally,
    after the results are already recorded.
    """

    def _target(self, run_id):
        from qa_tools.common import supply_db as db_mod
        return db_mod.dbt_target_path(run_id)

    @pytest.mark.parametrize("module_name", ["bdm", "cp"])
    def test_a_finished_run_removes_its_own_dbt_target_directory(self, db, module_name):
        import importlib

        orchestrate = importlib.import_module(
            f"qa_tools.{module_name}.orchestrate_{module_name}")
        run_id = f"leak_probe_{module_name}"
        target = self._target(run_id)
        target.mkdir(parents=True, exist_ok=True)
        (target / "run_results.json").write_text("{}")
        assert target.is_dir(), "test precondition - the directory must exist to be removed"

        orchestrate._discard_this_runs_schemas(run_id)

        assert not target.exists(), (
            f"{target} survived the run's own tidy-up - a per-run directory "
            f"nothing deletes is a leak with a tidier name")

    def test_removing_it_never_fails_a_finished_run(self, db):
        """The results are already recorded by the time this happens, so
        a tidy-up that cannot complete is a thing to report and move
        past - the same rule the schema half already follows."""
        from qa_tools.bdm import orchestrate_bdm

        # A run that never created one: the ordinary case for a run that
        # failed before dbt, and it must not turn one failure into two.
        orchestrate_bdm._discard_this_runs_schemas("leak_probe_never_existed")
