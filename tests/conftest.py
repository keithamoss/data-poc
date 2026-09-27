"""Shared pytest fixtures for real-tool integration tests (Phase 6,
plans/publishing-and-history.md): qa_tools/{bdm,cp}/run_{dbt,soda,
datacontract,evidently}_*.py's actual output-PARSING logic had zero
test coverage before this - the one test that touches orchestrate_
bdm.py/orchestrate_cp.py (tests/test_orchestrate_reference_run.py)
deliberately monkeypatches every one of these functions out, correctly
for that test's own narrow purpose (checking reference-run forwarding),
but with the side effect that the real "turn this tool's actual output
into our check-result shape" logic was never exercised under pytest at
all - only a full, slow `./run_pipeline.sh` run ever called it.

These fixtures build small, REAL, session-scoped BDM/CP data (real
generator output, real per-run DuckDB warehouses, via this project's
own real loading code) once per test session, so every real-tool test
that uses them doesn't pay the cost of rebuilding from scratch - the
real per-tool invocations (dbt build/soda scan/datacontract-cli/
Evidently) still each pay their own real, unavoidable startup cost,
since genuinely testing "does this correctly parse the real tool's
real output" requires actually running the real tool."""
from __future__ import annotations

import os
from datetime import date

import pytest

# A DEVELOPER'S OWN .env, so `uv run pytest` needs no exports.
# At import time rather than in a fixture: the supply_dsn fixture
# below is autouse and reads the environment, and several test
# modules read it at import. Never overrides something already
# set, which is what keeps CI's own MOTHMAN_TEST_DSN authoritative
# - a .env that clobbered it would point the run at a database
# that does not exist there, and the failure would read as a code
# fault.
from qa_tools.common.local_env import load_local_env  # noqa: E402

load_local_env()

import fixture_ids
from generator.daily_batch import generate_daily_batch
from qa_tools.common import asset_time, delivery
from generator.dirty import apply_birth_registrations_presets


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """pytest-playwright's own launch-args fixture, extended with the
    same PLAYWRIGHT_CHROMIUM_PATH escape hatch dashboard/
    check_dashboard_renders.py already uses - some sandboxed dev
    environments pre-install a version-pinned Chromium at a fixed path
    that Playwright's own default channel/download lookup won't find.
    Unset everywhere else (a real contributor machine or CI runner,
    both of which run `uv run playwright install chromium` per
    pyproject.toml's dev dependency group), so this is a no-op there."""
    chromium_path = os.environ.get("PLAYWRIGHT_CHROMIUM_PATH")
    if not chromium_path:
        return browser_type_launch_args
    return {**browser_type_launch_args, "executable_path": chromium_path}

# Real, calibrated defect injection (generator/dirty.py's own "severity:
# 'amber' or 'red' - matches the warn/fail bands ... exactly" contract)
# plus a deliberately much smaller row count than the reference run -
# both real, deterministic ways to force at least one genuine fail/warn
# status out of each of the 4 real tools without hand-crafting fixture
# rows that don't reflect what the real generator actually produces.
_REF_RUN_ID = "pytest_bdm_ref"
_DIRTY_RUN_ID = "pytest_bdm_dirty"


@pytest.fixture(scope="session")
def bdm_raw_dir(tmp_path_factory):
    """A tiny (relative to real production volume), real data/raw/-
    shaped directory: two runs, a clean reference (600 rows - comfortably
    clear of the real Soda row_count check's own 500-row warn floor,
    contract/bdm-birth-registrations-soda-checks.yml - a fixture much
    smaller than that would trip a real check for being implausibly
    small, exactly the kind of thing that check exists to catch) and a
    red-severity dirty run with a real defect injection AND a much
    smaller row count (20 rows, a ~97% drop off the reference - well
    past both that same row_count floor AND evidently's own 25%
    row-count-growth fail threshold) - real generator output, not
    hand-crafted rows."""
    raw_dir = tmp_path_factory.mktemp("bdm_raw")

    ref_df = generate_daily_batch(date(2026, 1, 1), seed=90001, n_rows=600)
    ref_df.to_csv(raw_dir / f"{_REF_RUN_ID}.csv", index=False)

    dirty_df = generate_daily_batch(date(2026, 1, 2), seed=90002, n_rows=20)
    dirty_df = apply_birth_registrations_presets(dirty_df, severity="red", seed=90003, previous_row_count=600)
    dirty_df.to_csv(raw_dir / f"{_DIRTY_RUN_ID}.csv", index=False)

    # AND AS REAL DELIVERIES (REQ-GEN-043) - the shape the pipeline
    # actually reads now. Two arrivals, arbitrary supplier-shaped names,
    # filenames matching the real arrivalPattern, receipts OUTSIDE the
    # deliveries. The flat CSVs above stay because several tests want
    # a plain file to hand `mothman bdm qa --file`, which is what an
    # operator really has; nothing reads a manifest from them.
    deliveries = raw_dir / "deliveries"
    receipts = raw_dir / "receipts"
    for run_id, name, when, df in (
            (_REF_RUN_ID, "REF_20260101", "2026-01-01T06:00:00+00:00", ref_df),
            (_DIRTY_RUN_ID, "drop-9002", "2026-01-02T06:00:00+00:00", dirty_df)):
        delivery.write_delivery(
            name, {f"birth_registrations_{when[:10]}.csv": df.to_csv(index=False)},
            received_at=asset_time.parse_instant(when, run_id),
            deliveries_dir=deliveries, receipts_dir=receipts)

    return str(raw_dir)


@pytest.fixture(scope="session")
def bdm_delivery_dirs(bdm_raw_dir):
    """(deliveries_dir, receipts_dir) for the fixture above."""
    from pathlib import Path
    return Path(bdm_raw_dir) / "deliveries", Path(bdm_raw_dir) / "receipts"


#: The PostgreSQL the SUITE connects to. Points at a server somebody else
#: is running - a dev container, a CI service container, or a local
#: install - never one this suite starts (REQ-TEST-095 criterion 1). A
#: suite that starts its own server tests a server nobody deploys.
TEST_DSN_ENV = "MOTHMAN_TEST_DSN"


@pytest.fixture(scope="session", autouse=True)
def supply_dsn(worker_id):
    """ONE SUPPLY DATABASE PER TEST WORKER, in a real PostgreSQL.

    WHY A WHOLE DATABASE rather than a schema set per worker: the code
    under test creates and drops SCHEMAS as its ordinary business -
    staging, rejected, one per period, one per run - so a worker confined
    to a schema would have to have every one of those names rewritten,
    and the thing being tested would no longer be the thing that runs.
    A database is the boundary that needs no cooperation from the code.

    IT FAILS RATHER THAN SKIPS when there is nowhere to connect
    (criterion 2). A skip is how a suite quietly stops testing: the run
    goes green, the count drops, and nobody reads the count. This is the
    same reasoning as the never-silently-skip rule the arrival pin in
    tests/test_asset_time_semantics.py carries.

    Dropped and recreated at session start rather than cleaned up at the
    end, which is deliberate: a crashed run leaves its database behind to
    look at, and the next run does not care what it finds.
    """
    import os

    import psycopg

    admin = os.environ.get(TEST_DSN_ENV)
    if not admin:
        raise pytest.UsageError(
            f"{TEST_DSN_ENV} is not set. This suite needs a real PostgreSQL to "
            f"connect to and deliberately does not start one - see README's "
            f"Development section. A dev container and CI each supply it; "
            f"locally, point it at your own server, e.g. "
            f"{TEST_DSN_ENV}=postgresql://user:pass@localhost:5432/postgres")

    name = f"mothman_test_{worker_id}"
    with psycopg.connect(admin, autocommit=True) as conn:
        # FORCE, because a leftover connection from a crashed run would
        # otherwise block the drop and fail the whole session with an
        # error about something the person did not do.
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{name}"')
        # REAP CONNECTIONS A QA TOOL LEAVES IDLE IN A TRANSACTION, which
        # is a real thing that happens rather than a precaution. Found
        # 2026-09-27: a datacontract-cli SQL rule left its connection
        # open after `test()` returned, holding a read lock on a staged
        # table, and the next load's DROP TABLE blocked behind it until
        # the whole run was killed. supply_db sets a lock_timeout so that
        # now fails loudly instead of hanging - this removes the cause as
        # well as the symptom, so the suite does not spend its time
        # proving the timeout works.
        #
        # ON THE DATABASE, not on our own connections: the leaking
        # connection is the TOOL'S, opened by its own driver, so nothing
        # we set on a connection we opened would reach it. A production
        # deployment wants this too, set by whoever administers the
        # database rather than by the application.
        conn.execute(
            f'ALTER DATABASE "{name}" SET idle_in_transaction_session_timeout = \'15s\'')

    info = psycopg.conninfo.conninfo_to_dict(admin)
    info["dbname"] = name
    dsn = psycopg.conninfo.make_conninfo(**info)

    # BEFORE ANY SODA SCAN CAN RUN, and this import is the whole point
    # of the line rather than a stylistic one. Soda builds a singleton
    # EnvHelper whose constructor reloads this repo's `.env` OVER the
    # process environment, which would undo the redirection below and
    # send every test after a Soda test on this worker at the
    # developer's real database. Importing soda_common defuses that
    # once - see its own _defuse_sodas_dotenv_reload(). Doing it here
    # makes the isolation guaranteed rather than dependent on which
    # module a worker happens to import first.
    from qa_tools.common import soda_common, supply_db  # noqa: F401

    before = os.environ.get(supply_db.SUPPLY_DSN_ENV)
    # THE DEPLOYMENT'S OWN DATABASE, remembered before this fixture
    # points everything at the worker's. One fixture genuinely needs
    # it: tests/test_dashboard_e2e.py builds the real dashboard, whose
    # input is recorded QA history - a shared, read-only corpus that
    # used to arrive with the checkout as committed files and is a
    # populated database since REQ-PIPE-089. A worker's database is
    # empty by design, so building from it produces an empty dashboard.
    globals()["DEPLOYMENT_SUPPLY_DSN"] = before
    os.environ[supply_db.SUPPLY_DSN_ENV] = dsn
    yield dsn
    if before is None:
        os.environ.pop(supply_db.SUPPLY_DSN_ENV, None)
    else:
        os.environ[supply_db.SUPPLY_DSN_ENV] = before


@pytest.fixture(scope="session", autouse=True)
def _committed_history_is_off_limits(tmp_path_factory):
    """No test writes into this repo's committed history trees.

    AUTOUSE AND SESSION-SCOPED ON PURPOSE. The trees here - the
    processing log, the delivery log, the in-flight observations - are
    written several frames below whatever a test actually called, by
    real production code paths that take a directory argument nobody
    at the test's level passes. So a test cannot opt in reliably; it
    has to be opted in for.

    THIS IS NOT PRECAUTIONARY. Both halves of it have already happened
    in this repo. `mothman pipeline run` once cleared the whole
    delivery log at its top, and the suite - which invokes that command
    with the real work stubbed - deleted sixty committed records on the
    next gate run. And the processing log, one day old, had 109
    test-run records in it out of 259, each one a table name that only
    ever existed inside a temporary directory.

    The prune half is the worse of the two and is still live without
    this: six tests invoke `pipeline run` without redirecting the
    delivery log, and the prune removes every record for a delivery
    not on disk. On this machine `data/deliveries/` exists so nothing
    is pruned; on a freshly-cloned CI runner there is no `data/` at
    all, so the correct answer to "which deliveries are present" is
    NONE and all sixty records go. Exactly the shape CLAUDE.md records
    for gitignored trees, in the opposite direction.

    Patches the module constants rather than the environment, so a test
    that redirects one of these itself still overrides this and still
    restores to a temporary directory rather than to the real tree.
    """
    from qa_tools.common import in_flight_log

    root = tmp_path_factory.mktemp("committed_history")
    # NEITHER load_log NOR delivery_log NOR filing is here any more:
    # REQ-PIPE-089 moved the first two into the database and
    # REQ-PIPE-104 the third, so there is no committed tree of any of
    # them left to guard. Isolation comes from each worker having its own
    # database, which is stronger than a redirected directory - a test
    # cannot reach the real one at all, rather than being pointed away
    # from it.
    guarded = [(in_flight_log, "OBSERVATIONS_DIR", "observations")]
    before = [(module, name, getattr(module, name)) for module, name, _ in guarded]
    for module, name, folder in guarded:
        setattr(module, name, root / folder)
    yield root
    for module, name, value in before:
        setattr(module, name, value)


@pytest.fixture
def real_committed_history(_committed_history_is_off_limits):
    """Opt one test back on to the REAL committed trees, for READING.

    The guard above is about writes and deletes, and redirecting
    everything also hides the trees from the handful of tests whose
    whole point is the real corpus - REQ-PIPE-058's collision gate, for
    one, which reads the committed delivery log precisely so it can run
    in CI without touching data/.

    Deliberately not autouse and deliberately named: a test that wants
    the real tree has to say so, which is the difference between an
    exception and a hole.
    """
    from qa_tools.common import delivery_log, in_flight_log

    root = delivery_log.ROOT
    restore = [(in_flight_log, "OBSERVATIONS_DIR", in_flight_log.OBSERVATIONS_DIR)]
    in_flight_log.OBSERVATIONS_DIR = root / "observations" / "in_flight"
    yield root
    for module, name, value in restore:
        setattr(module, name, value)


@pytest.fixture
def deployment_history(supply_dsn, monkeypatch):
    """Read the DEPLOYMENT'S recorded QA history, not this worker's.

    A handful of tests exist to check this repo's own real corpus -
    "a real run has a recorded sex distribution", "BDM's run windows
    are sorted and open-ended". That corpus used to arrive with the
    checkout as committed `qa_results/` files, so every worker saw it
    for free; REQ-PIPE-089 made it a database and a worker's is empty
    by design.

    READ-ONLY BY CONVENTION AND BY WHAT THESE TESTS DO - they assert on
    a corpus, they do not build one. A test that WRITES must use its own
    worker database, which is what every other test here gets.

    It needs that database populated, which is
    `mothman pipeline bootstrap` - see CLAUDE.md's setup section.
    """
    dsn = globals().get("DEPLOYMENT_SUPPLY_DSN")
    if not dsn:
        pytest.skip("no deployment database configured (MOTHMAN_SUPPLY_DSN)")
    monkeypatch.setenv(supply_db_module().SUPPLY_DSN_ENV, dsn)
    return dsn


def supply_db_module():
    from qa_tools.common import supply_db
    return supply_db


@pytest.fixture
def clean_qa_history(supply_dsn):
    """An empty QA history for one test (REQ-PIPE-089).

    Per-test isolation used to come free from `tmp_path`, because each
    test wrote its own little `qa_results/` tree. The history is a
    schema now and a worker's database outlives any one test, so a
    test reusing a run id - `run_1` is popular - sees whatever an
    earlier test recorded under it.

    Yields the connection, so a test that needs to mark a run complete
    or look at a row directly has one to hand.
    """
    from qa_tools.common import qa_store, supply_db

    with supply_db.connect(label="test-clean-qa-history") as conn:
        qa_store.ensure_schema(conn)
        conn.execute(f'TRUNCATE "{qa_store.SCHEMA}".run CASCADE')
        yield conn


@pytest.fixture
def finish_runs():
    """Attribute runs and mark them finished, so their results are
    observable (criterion 13).

    A helper rather than something automatic: a run becoming observable
    is a real event with a real precondition - it has to say who ran
    it - and a fixture that quietly completed every run would remove
    the thing several tests are about.
    """
    from qa_tools.common.qa_results_writer import finish_run, open_run

    def _finish(*run_ids, agency="a", collection="b",
                when="2026-01-01T00:00:00+00:00", run_by="tests@example.gov.au"):
        for run_id in run_ids:
            open_run(agency, collection, run_id, when, run_by)
            finish_run(run_id)

    return _finish


@pytest.fixture
def clean_delivery_log(supply_dsn):
    """An empty delivery log for one test (REQ-PIPE-089 criterion 16).

    Same reasoning as `clean_load_log` below, and the same deliberate
    non-autouse: a test asserting on the WHOLE log has to empty it
    first, and the staging fixtures legitimately leave records behind.
    """
    from qa_tools.common import qa_store, supply_db

    with supply_db.connect(label="test-clean-delivery-log") as conn:
        qa_store.ensure_schema(conn)
        conn.execute(f'TRUNCATE "{qa_store.SCHEMA}".delivery CASCADE')
        yield conn


@pytest.fixture
def clean_load_log(supply_dsn):
    """An empty load log for one test (REQ-PIPE-089).

    Until the load record moved into the database each test got this
    free, from its own temporary directory. A worker's database is
    shared across the tests that run on it, so a test asserting on the
    WHOLE log - "these are the only records" - has to empty it first or
    it is asserting about whatever ran before it. Exactly the leakage
    that made three assertions in tests/test_qa_store.py fail on rows
    an earlier test left behind.

    DELIBERATELY NOT AUTOUSE, for a reason rather than restraint: the
    module-scoped staging fixtures below write load records, and those
    records are the gate that makes their staged tables readable. A
    blanket truncate between tests would leave the tables staged and
    invisible, which is a far more confusing failure than the one it
    would prevent.
    """
    from qa_tools.common import qa_store, supply_db

    with supply_db.connect(label="test-clean-load-log") as conn:
        qa_store.ensure_schema(conn)
        conn.execute(f'TRUNCATE "{qa_store.SCHEMA}".load_outcome')
        yield conn


@pytest.fixture(scope="module")
def bdm_duckdb_dir(supply_dsn, bdm_raw_dir):
    """bdm_raw_dir's same two runs, staged into this worker's supply
    database via the real build_all() - the exact loading code path the
    real pipeline uses, not a hand-rolled copy of it.

    PER MODULE, NOT PER SESSION, since 2026-09-27. What this fixture
    guarantees is not just "the rows are staged" but "this run has a
    view schema to read them through", and a QA run now DISCARDS its
    own view schema when it finishes (REQ-PIPE-068 criterion 1, which
    always said "once the run completes" - the sweep-at-the-end it
    replaced never actually met it). So one module calling run_single()
    used to leave the next module on the same xdist worker with staged
    tables and no views. Re-staging is cheap here - two arrivals, 620
    rows - and buys back an invariant every reader of this fixture
    assumes.

    Named for the directory it used to return, and returning the
    database path instead. The name is left alone on purpose: every
    test that depends on it depends on the DATA being staged, not on
    the path, and renaming it across a dozen files would be churn that
    hid the one real change in the diff.
    """
    from pathlib import Path

    from qa_tools.bdm.build_per_run_warehouses import build_all

    build_all(deliveries_dir=Path(bdm_raw_dir) / "deliveries",
               receipts_dir=Path(bdm_raw_dir) / "receipts")
    return supply_dsn


# The run_ids recognition will assign these two deliveries - see
# tests/fixture_ids.py. The flat data/cp_raw/<run_id>/ copy below has to
# be named for them because qa_tools/cp/run_datacontract_cp.py and
# run_evidently_cp.py still read their CSVs from that path, exactly as
# the real generator writes it. That coupling is real and outlives this
# fixture; it is logged as a follow-up rather than papered over here.
_CP_REF_RUN_ID = fixture_ids.CP_REF_RUN_ID
_CP_DIRTY_RUN_ID = fixture_ids.CP_DIRTY_RUN_ID


@pytest.fixture(scope="session")
def cp_raw_dir(tmp_path_factory):
    """A tiny, real data/cp_raw/-shaped directory: two collection
    snapshots (a clean reference and a red-severity dirty one), built
    from a small (not real 70k-row production scale, kept fast for a
    test fixture - real generation confirmed <1s at this size) but
    genuinely real population via the actual synthetic_data_generator.
    population/child_protection generators and generator.dirty's real
    apply_cp_*_presets() injectors - the exact same generation
    functions generator/generate_cp_runs.py's own main() calls, at a
    smaller scale, not a hand-rolled copy of CP's real cross-table
    structure."""
    from generator import dirty as dirty_mod
    from generator.generate_cp_runs import _add_extract_timestamp
    from synthetic_data_generator.child_protection import generate_child_protection_collection
    from synthetic_data_generator.population import generate_population

    raw_dir = tmp_path_factory.mktemp("cp_raw")
    tables_list = ["cp_clients", "cp_notifications", "cp_investigations", "cp_placements", "cp_carers", "cp_case_workers"]

    # 45000 (not the real 70k production scale) is the smallest population
    # that clears every real Soda row_count warn floor for cp_clients (300),
    # cp_notifications (600) and cp_carers (150) - contract/child-protection-
    # soda-checks.yml - so the "clean" reference run really is clean, not
    # just short of the fail threshold.
    pop = generate_population(45000, seed=91001)
    base_tables = generate_child_protection_collection(pop, seed=91002, n_case_workers=15)

    def _write_run(run_id: str, run_date: str, tables: dict, delivery_name: str):
        """One arrival: the six CP tables landing together as ONE
        delivery (REQ-GEN-043), plus a flat per-run folder several
        tests hand to `mothman cp qa --folder`, which is the shape an
        operator really has."""
        run_dir = raw_dir / run_id
        run_dir.mkdir()
        files = {}
        for name in tables_list:
            df = _add_extract_timestamp(tables[name], date.fromisoformat(run_date), None, seed=91003)
            cols = [c for c in df.columns if not c.startswith("_")]
            df[cols].to_csv(run_dir / f"{name}.csv", index=False)
            files[f"{name}.csv"] = df[cols].to_csv(index=False)
        delivery.write_delivery(
            delivery_name, files,
            received_at=asset_time.parse_instant(f"{run_date}T06:00:00+00:00", run_id),
            deliveries_dir=raw_dir / "deliveries", receipts_dir=raw_dir / "receipts")

    _write_run(_CP_REF_RUN_ID, "2026-01-01", base_tables, "CP_20260101")

    dirty_tables = {name: base_tables[name].copy() for name in tables_list}
    dirty_tables["cp_notifications"] = dirty_mod.apply_cp_notifications_presets(
        dirty_tables["cp_notifications"], base_tables["cp_clients"], base_tables["cp_case_workers"],
        "red", seed=91101)
    dirty_tables["cp_placements"] = dirty_mod.apply_cp_placements_presets(
        dirty_tables["cp_placements"], dirty_tables["cp_carers"], base_tables["cp_clients"],
        "red", seed=91102)
    dirty_tables["cp_investigations"] = dirty_mod.apply_cp_investigations_presets(
        dirty_tables["cp_investigations"], dirty_tables["cp_clients"], base_tables["cp_notifications"],
        base_tables["cp_case_workers"], "red", seed=91103)
    dirty_tables["cp_clients"] = dirty_mod.apply_cp_clients_presets(dirty_tables["cp_clients"], "red", seed=91104)
    dirty_tables["cp_carers"] = dirty_mod.apply_cp_carers_presets(dirty_tables["cp_carers"], "red", seed=91105)
    dirty_tables["cp_case_workers"] = dirty_mod.apply_cp_case_workers_presets(dirty_tables["cp_case_workers"], "red", seed=91106)
    _write_run(_CP_DIRTY_RUN_ID, "2026-04-01", dirty_tables, "cp-drop-9104")

    return str(raw_dir)


@pytest.fixture(scope="session")
def cp_delivery_dirs(cp_raw_dir):
    """(deliveries_dir, receipts_dir) for the fixture above."""
    from pathlib import Path
    return Path(cp_raw_dir) / "deliveries", Path(cp_raw_dir) / "receipts"


@pytest.fixture(scope="module")
def cp_duckdb_dir(supply_dsn, cp_raw_dir):
    """cp_raw_dir's same two runs, staged into this worker's supply
    database via the real build_all(). Shares one database with the BDM
    fixture above, which is the point rather than a compromise - the
    whole asset has one, and the two collections' tables have always
    been distinct.

    PER MODULE for the same reason as the BDM fixture - see its own
    note on run_single() discarding the view schema it read through.
    The expensive half (generating a 45,000-person population) stays
    session-scoped in cp_raw_dir; only the staging repeats.

    See the BDM fixture for why the name still says `dir`.
    """
    from pathlib import Path

    from qa_tools.cp.build_cp_warehouses import build_all

    # deliveries_dir/receipts_dir passed EXPLICITLY. Without them
    # build_all() recognises arrivals from the real data/deliveries/
    # tree (REQ-GEN-043) - a real leak this fixture hit for exactly one
    # run, building 18 real CP warehouses into a pytest tmp dir while
    # the fixture's own two sat unread.
    build_all(
               deliveries_dir=Path(cp_raw_dir) / "deliveries",
               receipts_dir=Path(cp_raw_dir) / "receipts")
    return supply_dsn
