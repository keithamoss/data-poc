"""A trial leaves nothing behind; a kept supply becomes a real arrival.

REQ-PIPE-103. Two routes through one command, and the difference is a
question asked before anything happens.

KEPT: the supply is filed as a real delivery with its own receipt
BEFORE any check runs, so recognition gives it a run id exactly as it
would a delivery that arrived on its own, and its staged table is
named for the receipt instant. Nothing is invented, so nothing has to
be renamed afterwards.

TRIAL: nothing is filed and nothing outlives the command. Keith's own
condition, 2026-09-27 - "a trial must write NOTHING to the database
that survives the end of its run" - which is stricter than a run was
already. A run discards its view schema and dbt's when it finishes
(REQ-PIPE-068), but staged tables are permanent BY DESIGN: staging
only ever grows, one physical table per arrival. That is right for a
supply that really arrived and exactly wrong for one nobody accepted.
"""
from __future__ import annotations

from qa_tools.common import supply_db, trial


def _database_state(conn) -> tuple[set[str], set[str]]:
    """What is in the database, EXCLUDING the carrier table.

    `staging._resolutions` is infrastructure - the table resolutions
    are recorded IN - not a supply anybody staged. It is created on
    first use, so a baseline taken before any run and compared after
    one would otherwise report it as something the trial left behind.
    A trial's ROWS in it are a different matter and are asserted on
    separately below.
    """
    staged = {r[0] for r in conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
        [supply_db.STAGING_SCHEMA]).fetchall()} - {"_resolutions"}
    schemas = set(supply_db.run_schemas(conn)) | set(supply_db.dbt_schemas(conn))
    return staged, schemas


class TestATrialIsNamedForWhatItIs:
    def test_a_trial_run_id_says_trial(self):
        run_id = trial.trial_run_id()
        assert run_id.startswith("trial_"), run_id

    def test_a_trial_run_id_carries_no_filename(self):
        """The stem existed so a human skimming committed history could
        see which file a run came from. A trial never reaches committed
        history, so it has nothing to carry."""
        run_id = trial.trial_run_id()
        assert "birth" not in run_id and "csv" not in run_id, run_id

    def test_two_trials_in_the_same_second_do_not_collide(self):
        """Sub-second precision replaces the stem. Second resolution was
        enough only while the filename carried the distinctness."""
        assert trial.trial_run_id() != trial.trial_run_id()

    def test_a_reference_trial_is_distinguishable(self):
        """Evidently compares this supply against a previous one, so a
        trial needs a second disposable run for the reference."""
        assert trial.trial_run_id(reference=True) != trial.trial_run_id()
        assert "ref" in trial.trial_run_id(reference=True)

    def test_a_trial_run_id_is_a_usable_schema_name(self):
        run_id = trial.trial_run_id()
        assert supply_db.run_schema(run_id) == supply_db.RUN_SCHEMA_PREFIX + run_id

    def test_a_trial_staged_table_fits_an_identifier(self):
        name = supply_db.staged_table("birth_registrations", trial.trial_run_id())
        assert len(name.encode()) <= 63, f"{name} is {len(name.encode())} bytes"


class TestATrialNeverTouchesSharedStaging:
    """THE GUARANTEE, and why it is a schema rather than a transaction.

    Keith asked the right question: "how are we safely preventing a
    trial from writing anything? wrapping the whole thing in a
    transaction that we rollback?" A transaction cannot do it, and
    that was MEASURED rather than assumed - work inside an open
    transaction is invisible to any other connection, and dbt, Soda,
    datacontract-cli and Evidently each open their own. Staging
    uncommitted would leave all four looking at an empty schema. dbt
    also creates its own models on its own connection, which our
    rollback could not reach.

    So a trial gets a SCHEMA OF ITS OWN and never writes into shared
    staging at all. It cannot leave a stray table among real supplies
    even in principle, and the tidy-up is DROP SCHEMA rather than a
    walk that can stop halfway.
    """

    def test_a_trials_staging_schema_is_its_own(self):
        run_id = trial.trial_run_id()
        assert supply_db.staging_schema_for(run_id) != supply_db.STAGING_SCHEMA
        assert supply_db.staging_schema_for(run_id).startswith("trial_")

    def test_a_kept_run_still_uses_shared_staging(self):
        """The other half: a supply that really arrived belongs in the
        history staging exists to keep."""
        assert supply_db.staging_schema_for("run_001") == supply_db.STAGING_SCHEMA

    def test_every_schema_a_trial_uses_is_identifiable_as_one(self):
        """A crash leaves something; it has to be something a sweep can
        recognise without being told."""
        run_id = trial.trial_run_id()
        for schema in (supply_db.staging_schema_for(run_id),
                       supply_db.run_schema(run_id),
                       supply_db.dbt_schema(run_id)):
            assert "trial_" in schema, schema

    def test_a_reference_trial_is_also_identifiable(self):
        """`trial_ref_...`, not `ref_trial_...`, so every trial schema
        starts the same way and one prefix finds them all."""
        run_id = trial.trial_run_id(reference=True)
        assert run_id.startswith("trial_ref_"), run_id
        assert supply_db.staging_schema_for(run_id).startswith("trial_")


class TestATrialLeavesNothingBehind:
    def test_discarding_a_trial_removes_every_schema_it_used(self, supply_dsn):
        run_id = trial.trial_run_id()
        with supply_db.connect(label="test-trial") as conn:
            supply_db.ensure_schemas(conn)
            before_staged, before_schemas = _database_state(conn)
            for schema in (supply_db.staging_schema_for(run_id),
                           supply_db.run_schema(run_id),
                           supply_db.dbt_schema(run_id)):
                conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            conn.execute(
                f'CREATE TABLE "{supply_db.staging_schema_for(run_id)}".t (id integer)')

            trial.discard(conn, run_id)

            after_staged, after_schemas = _database_state(conn)
            assert not trial.schemas_of(conn, run_id), "a trial left a schema behind"
        assert after_staged == before_staged
        assert after_schemas == before_schemas

    def test_the_tidy_up_is_one_transaction(self, supply_dsn):
        """PostgreSQL has transactional DDL, which is what makes this a
        real guarantee rather than a walk that can stop halfway: either
        every schema the trial used goes, or none does and the next
        `mothman supply tidy` finds them all together."""
        import inspect

        source = inspect.getsource(trial.discard)
        assert "BEGIN" in source or "transaction" in source.lower(), \
            "the tidy-up drops schemas one statement at a time"

    def test_discarding_a_trial_that_staged_nothing_is_harmless(self, supply_dsn):
        """A trial that failed before staging still reaches its own
        tidy-up, and must not turn one failure into two."""
        with supply_db.connect(label="test-trial") as conn:
            supply_db.ensure_schemas(conn)
            trial.discard(conn, trial.trial_run_id())

    def test_discarding_a_trial_leaves_a_real_supply_alone(self, supply_dsn):
        """The property shared staging made impossible to guarantee."""
        with supply_db.connect(label="test-trial") as conn:
            supply_db.ensure_schemas(conn)
            real = supply_db.staged_table("birth_registrations", "2026-08-01T01:00:00+00:00")
            conn.execute(
                f'CREATE TABLE IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"."{real}" (id integer)')

            trial.discard(conn, trial.trial_run_id())

            staged, _ = _database_state(conn)
            assert real in staged, "discarding a trial touched shared staging"
            conn.execute(f'DROP TABLE "{supply_db.STAGING_SCHEMA}"."{real}"')

    def test_a_stale_trial_schema_is_findable_after_a_crash(self, supply_dsn):
        """The residual weakness, stated honestly: a kill -9 still
        leaves something. It has to be ONE identifiable thing that a
        sweep can clear, not rows scattered through shared staging."""
        run_id = trial.trial_run_id()
        with supply_db.connect(label="test-trial") as conn:
            supply_db.ensure_schemas(conn)
            conn.execute(
                f'CREATE SCHEMA IF NOT EXISTS "{supply_db.staging_schema_for(run_id)}"')

            assert trial.orphan_schemas(conn), "a crashed trial is invisible to the sweep"
            trial.discard(conn, run_id)
            assert not trial.orphan_schemas(conn)


class TestARealTrialStagesAndVanishes:
    """The property the classes above assert about names, asserted
    instead about a trial that really loaded real rows through the real
    loader - which is where a naming mistake would actually show."""

    def _csv(self, bdm_delivery_dirs):
        """A REAL DELIVERED FILE, not the fixture's flat CSV - this is
        the shape an operator hands `mothman` and the shape the loader
        reads."""
        deliveries, _ = bdm_delivery_dirs
        return str(deliveries / "REF_20260101" / "birth_registrations_2026-01-01.csv")

    def test_a_real_trial_stages_into_its_own_schema_and_leaves_no_trace(
            self, supply_dsn, bdm_delivery_dirs, tmp_path):
        from qa_tools.bdm import build_per_run_warehouses

        run_id = trial.trial_run_id()
        with supply_db.connect(label="test-trial") as conn:
            supply_db.ensure_schemas(conn)
            before_staged, before_schemas = _database_state(conn)

        physical = build_per_run_warehouses.build_one(
            run_id, self._csv(bdm_delivery_dirs), "2026-01-01")
        assert physical, "the real loader staged nothing"

        with supply_db.connect(label="test-trial") as conn:
            # IT REALLY LOADED, through the real loader and the real
            # view schema - otherwise "nothing survived" would be true
            # of a trial that did nothing.
            own = supply_db.staging_schema_for(run_id)
            rows = conn.execute(
                f'SELECT count(*) FROM "{own}"."{physical}"').fetchone()[0]
            # Against the file's own row count rather than a literal,
            # so the fixture can change size without this going red
            # for a reason that has nothing to do with trials.
            with open(self._csv(bdm_delivery_dirs)) as handle:
                expected = sum(1 for _ in handle) - 1
            assert rows == expected, f"{rows} staged from a {expected}-row file"
            assert conn.execute(
                f'SELECT count(*) FROM "{supply_db.run_schema(run_id)}".'
                f'birth_registrations').fetchone()[0] == expected

            # AND SHARED STAGING NEVER SAW IT.
            mid_staged, _ = _database_state(conn)
            assert mid_staged == before_staged, \
                "a trial put a table in shared staging"

            trial.discard(conn, run_id)

            after_staged, after_schemas = _database_state(conn)
            assert after_staged == before_staged
            assert after_schemas == before_schemas
            assert not trial.schemas_of(conn, run_id)
            assert not trial.orphan_schemas(conn)

    def test_a_real_trials_load_records_go_with_it(
            self, supply_dsn, bdm_delivery_dirs, clean_load_log):
        """Criterion 6 names the load record explicitly. A trial's must
        not join the real ones - and must not simply be skipped either,
        because the record is the gate that decides which staged tables
        a run's views may resolve.

        THE MECHANISM CHANGED WITH REQ-PIPE-089 AND THE GUARANTEE GOT
        STRONGER. It used to be a scratch DIRECTORY outside the
        committed tree, removed by an rmtree after the schemas were
        dropped - two acts, and a crash between them left a
        half-discarded trial. It is now a column, and the delete runs
        inside the same transaction as the DROPs.
        """
        from qa_tools.bdm import build_per_run_warehouses
        from qa_tools.common import load_log

        run_id = trial.trial_run_id()
        before = len(load_log.records())

        physical = build_per_run_warehouses.build_one(
            run_id, self._csv(bdm_delivery_dirs), "2026-01-01")

        assert len(load_log.records()) == before, \
            "a trial's load record turned up among the real ones"
        mine = load_log.records(trial=run_id)
        assert any(r.physical == physical for r in mine), \
            "a trial wrote no load record, so its views resolved on a weaker rule"
        assert physical in load_log.loaded_tables(trial=run_id)
        assert physical not in load_log.loaded_tables(), \
            "a trial's staged table was readable outside the trial"

        with supply_db.connect(label="test-trial") as conn:
            trial.discard(conn, run_id)
        assert not load_log.records(trial=run_id), \
            "a discarded trial left its load records behind"
        assert len(load_log.records()) == before

    def test_a_kept_run_still_stages_into_shared_staging(
            self, supply_dsn, bdm_delivery_dirs):
        """The other half, and the one a mistake here would break
        silently: a real arrival must still land in the history staging
        exists to keep."""
        from qa_tools.bdm import build_per_run_warehouses

        physical = build_per_run_warehouses.build_one(
            "run_999", self._csv(bdm_delivery_dirs), "2099-03-03",
            received_at="2099-03-03T01:02:03+00:00")
        with supply_db.connect(label="test-trial") as conn:
            staged, _ = _database_state(conn)
            assert physical in staged
            conn.execute(
                f'DROP TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" CASCADE')
            supply_db.drop_run_schemas(conn, "run_999")


    def test_a_discarded_reference_run_is_not_left_as_a_crashed_run(
            self, supply_dsn, bdm_delivery_dirs):
        """post-build-review #118 D-C: staging screened the file and
        registered a qa.run for its file-check results; discarding the
        trial left that run - never completed - in the crashed-run list."""
        from qa_tools.bdm import build_per_run_warehouses
        from qa_tools.common import qa_store

        run_id = trial.trial_run_id(reference=True)
        build_per_run_warehouses.build_one(run_id, self._csv(bdm_delivery_dirs), "2026-01-01")
        with supply_db.connect(label="test-trial") as conn:
            trial.discard(conn, run_id)
            assert not conn.execute(
                f'SELECT 1 FROM "{qa_store.SCHEMA}".run WHERE run_key = ?', [run_id]).fetchall()
            assert not conn.execute(
                f'SELECT 1 FROM "{qa_store.SCHEMA}".check_result WHERE run_key = ?',
                [run_id]).fetchall()
            assert run_id not in qa_store.incomplete_runs(conn)

    def test_a_completed_trials_own_results_go_with_it(self, supply_dsn):
        """REQ-PIPE-103 criterion 6 - Keith, 2026-10-06 (post-build-review
        #120 Q6): discard KEPT a trial's own recorded checks on purpose, so a
        completed trial run and its results outlived it, visible to anything
        reading recorded results, while the terminal said nothing was
        recorded. The criterion wins: the run, its results and anything
        else recorded under it go in the same transaction."""
        from qa_tools.common import qa_store
        from qa_tools.common.qa_results_writer import finish_run, write_qa_result

        run_id = trial.trial_run_id()
        when = "2026-01-01T00:00:00+00:00"
        write_qa_result("civil-registration-agency", "civil-registration", run_id, when, "soda",
                        {"hasErrors": False},
                        [{"check_id": "x.y.civil-registration.birth-registrations.c.missing_soda",
                          "dataset_id": "birth-registrations", "run_id": run_id,
                          "status": "pass"}], run_by="trial:not-recorded")
        finish_run(run_id)
        with supply_db.connect(label="test-trial") as conn:
            conn.execute(f'INSERT INTO "{qa_store.SCHEMA}".census (trigger, run_key) '
                         "VALUES ('run', ?)", [run_id])
            trial.discard(conn, run_id)
            for table in ("run", "check_result", "census"):
                assert not conn.execute(
                    f'SELECT 1 FROM "{qa_store.SCHEMA}".{table} WHERE run_key = ?',
                    [run_id]).fetchall(), f"the trial's {table} rows outlived it"


class TestATrialIsNeverSilentlyCheckedAgainstPromotedData:
    """A latent false green, found by Keith asking the right question
    (2026-09-27): "how do the trial schemas work with cross-table
    checks and the whole overlay staging on top of the period's
    schema?"

    CROSS-TABLE CHECKS WERE ALREADY FINE - they read the run's own
    view schema, and a trial's views point at its own staging, so all
    six tables resolve exactly as they would for a real run.

    THE PERIOD OVERLAY WAS NOT. period_schema.create_overlay_views()
    builds a run's views as "this arrival's staged tables, falling
    back to the period's promoted version for anything this arrival
    did not carry", and it read `staging` as a hard-coded constant. A
    trial's tables are not there, so every one of them would take the
    fall-through and the trial would report on the last promoted data
    while appearing to check the operator's file. Nothing calls that
    function yet; this pins the behaviour so that wiring it up cannot
    reintroduce the bug.
    """

    def test_the_overlay_reads_a_trials_own_staging_schema(self, supply_dsn):
        from qa_tools.common import period_schema

        run_id = trial.trial_run_id()
        staging = supply_db.staging_schema_for(run_id)
        with supply_db.connect(label="test-trial") as conn:
            supply_db.ensure_schemas(conn)
            supply_db.ensure_staging(conn, run_id)
            period = period_schema.ensure_period_schema(conn, "2099-Q1")
            physical = "cp_clients__trialoverlay"
            # THE TRIAL'S OWN TABLE, in its own schema, with a value
            # that could only have come from there...
            conn.execute(f'CREATE TABLE "{staging}"."{physical}" (id integer)')
            conn.execute(f'INSERT INTO "{staging}"."{physical}" VALUES (1)')
            # ...and a DIFFERENT, already-promoted table of the same
            # logical name, which is what the bug would have read.
            conn.execute(f'CREATE TABLE "{period}"."cp_clients__promoted" (id integer)')
            conn.execute(f'INSERT INTO "{period}"."cp_clients__promoted" VALUES (2), (3)')

            period_schema.create_overlay_views(
                conn, run_id, "2099-Q1",
                staged={"cp_clients": [physical]},
                promoted={"cp_clients": ["cp_clients__promoted"]})

            rows = conn.execute(
                f'SELECT id FROM "{supply_db.run_schema(run_id)}".cp_clients'
            ).fetchall()
            assert [r[0] for r in rows] == [1], (
                "the trial's view resolved to the PROMOTED table - it would "
                "have reported on data the operator never supplied")

            trial.discard(conn, run_id)
            conn.execute(f'DROP SCHEMA IF EXISTS "{period}" CASCADE')


class TestASingleTableRunRecordsAllSixTablesItRead:
    """A defect this requirement's own change introduced, found by
    Keith asking what "borrows the other five tables" actually means
    (2026-09-27).

    Child Protection's dbt models reference all six tables, so a
    one-table supply reads five more from the run it borrowed them
    from. The run's SCHEMA gets all six views - that part worked - but
    the RESOLUTION RECORD only ever carried what was staged, so a
    single-table run recorded that it had read one table while
    actually reading six. That record is what `tables_read` publishes
    as "what this run read", and the question it answers is asked
    years later by an audit, so under-reporting it is not cosmetic.
    """

    def test_borrowing_a_table_records_that_the_run_read_it(self, supply_dsn):
        earlier = "cp_run_900"
        later = trial.trial_run_id()
        with supply_db.connect(label="test-trial") as conn:
            supply_db.ensure_schemas(conn)
            # An earlier run that really did read two tables.
            for logical in ("cp_clients", "cp_carers"):
                physical = f"{logical}__900"
                conn.execute(
                    f'CREATE TABLE IF NOT EXISTS "{supply_db.STAGING_SCHEMA}".'
                    f'"{physical}" (id integer)')
            supply_db.record_resolution(conn, supply_db.Resolution(
                run_id=earlier, schema=supply_db.run_schema(earlier),
                resolved={"cp_clients": "cp_clients__900",
                          "cp_carers": "cp_carers__900"}))

            # A later run that staged ONE of them and must borrow the
            # other - exactly the partial-resupply shape.
            staging = supply_db.ensure_staging(conn, later)
            mine = f"cp_clients__{supply_db.arrival_segment(later)}"
            conn.execute(f'CREATE TABLE "{staging}"."{mine}" (id integer)')
            res = supply_db.create_run_views(
                conn, later, {"cp_clients": [mine], "cp_carers": []},
                source_schema=staging)
            supply_db.record_resolution(conn, res)
            assert res.absent == ["cp_carers"], res.absent

            supply_db.borrow_views(conn, later, earlier, ["cp_carers"])

            recorded = supply_db.resolution_for(conn, later)
            assert set(recorded.resolved) == {"cp_clients", "cp_carers"}, (
                "the run reads six tables and recorded fewer - `tables_read` "
                f"would under-report: {recorded.resolved}")
            assert recorded.resolved["cp_carers"] == "cp_carers__900", \
                "the borrowed table must be recorded as the version really read"
            assert "cp_carers" not in recorded.absent

            trial.discard(conn, later)
            for logical in ("cp_clients", "cp_carers"):
                conn.execute(
                    f'DROP TABLE IF EXISTS "{supply_db.STAGING_SCHEMA}".'
                    f'"{logical}__900" CASCADE')
            conn.execute(
                f'DELETE FROM "{supply_db.STAGING_SCHEMA}"._resolutions '
                f"WHERE run_id = '{earlier}'")

