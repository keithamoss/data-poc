"""A parallel bootstrap records the same history as a sequential one
(REQ-TEST-116 criterion 4, "kept as a test").

WHAT IS RUN. The real generators write the real corpus into a temporary
tree; it is cut down to a few deliveries; then `bootstrap()` itself runs
twice over it, each into an empty database of its own - once with
`sequential=True` (the reference: collections one after the other,
tools one after the other) and once as it runs by default (collections in
spawned processes, dbt beside the other three tools). Nothing in the
bootstrap is mocked except generation, which happens once, up front, so
both modes read byte-identical input.

WHAT IS COMPARED: see equiv_support.snapshot() - every row of every qa
table, every supply table's contents, the schema list - with the
clock-stamped columns and surrogate ids it names, and nothing else, left
out. Validated first against the two FULL bootstraps of 2026-10-03
(7,210 check results, 84 decisions, 151 supply tables): identical under
this comparison too, so the exclusions are sufficient rather than
convenient.

WHY A REDUCED CORPUS IS STILL THE THING. What the parallel mode can break
is (a) two collections writing to one database at once - the delivery
log, schema migrations, the qa tables, period schemas - and (b) dbt's
results being recorded beside the other tools'. Both happen on the first
arrival of each collection. What the reduced corpus gives up is length:
the within-collection chain is sequential in both modes by construction
(criterion 2), so a longer one adds minutes without adding a way for the
two modes to differ.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

import psycopg
import pytest

import equiv_support

#: ON DEMAND ONLY (Keith, 2026-10-04): about 3-4 minutes of two real
#: bootstraps, so it is deselected from every ordinary run - CI included -
#: and run when the bootstrap's parallelism is touched:
#:     uv run pytest --run-on-demand tests/test_bootstrap_equivalence.py
pytestmark = pytest.mark.on_demand

#: The cut-down corpus, by the generator's own run ids - chosen so each
#: kind of record the two modes could disagree on is present at least once
#: (TestTheCorpusIsWorthComparing holds it to that):
#:
#: Birth Registrations - two clean daily supplies (promoted), the first
#: RED one (fails checks, so is filed and not promoted) and a supply
#: received days later, which files LATE into the oldest slot nothing has
#: promoted into - a filing that reads the decision log, which is what
#: makes the chain a chain.
#:
#: Child Protection - its first quarterly delivery, six files and so six
#: arrivals into six datasets, all promoted into ONE period schema: the
#: shared-write case at its most concentrated. Then ONE file of its
#: second delivery: case workers are not due that quarter, so promotion
#: is WITHHELD - a decision that is not a promotion. Trimmed to that one
#: file because each file is a whole run, and the other five add a minute
#: without adding a kind of record.
KEEP = {"birth-registrations": ("run_001", "run_002", "run_009", "run_017"),
        "cp-clients": ("cp_run_001", "cp_run_002")}
#: Deliveries kept only in part: run id -> the files kept.
KEEP_ONLY_FILES = {"cp_run_002": {"cp_case_workers.csv"}}

ADMIN_DSN_ENV = "MOTHMAN_TEST_DSN"


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    """The real generators' output, cut down to KEEP's deliveries.

    Generated through tests/generator_isolation.redirect, the same
    redirection the generator tests use, so nothing under data/ is
    touched; the scenario map (committed configuration) is not
    rewritten, which is the one step of cli's generate_synthetic_data()
    left out.
    """
    import generator_isolation
    from generator import generate_cp_runs, generate_runs

    root = tmp_path_factory.mktemp("equiv_corpus")
    for module in (generate_runs, generate_cp_runs):
        undo = generator_isolation.redirect(module, root)
        try:
            module.main()
        finally:
            undo()

    bookkeeping = json.loads((root / "generator_bookkeeping.json").read_text())
    delivery_of = {entry["run_id"]: entry["delivery"]
                   for dataset, run_ids in KEEP.items()
                   for entry in bookkeeping[dataset] if entry["run_id"] in run_ids}
    assert len(delivery_of) == sum(len(v) for v in KEEP.values()), \
        "a KEEP run id no longer names a generated delivery - the generator changed"
    keep = set(delivery_of.values())
    for tree in ("deliveries", "receipts"):
        for d in (root / tree).iterdir():
            if d.name not in keep:
                shutil.rmtree(d)
    for run_id, files in KEEP_ONLY_FILES.items():
        name = delivery_of[run_id]
        present = {p.name for p in (root / "deliveries" / name).iterdir()}
        assert files <= present, f"{name} no longer carries {files - present}"
        for f in present - files:
            (root / "deliveries" / name / f).unlink()
            # Its receipt too: a file with no receipt reads as IN FLIGHT,
            # and a receipt with no file as something else again.
            (root / "receipts" / name / f"{f}.json").unlink()
    assert sorted(p.name for p in (root / "deliveries").iterdir()) == sorted(keep)
    return root


def _fresh_database(name: str) -> str:
    admin = os.environ[ADMIN_DSN_ENV]
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{name}"')
        conn.execute(f'ALTER DATABASE "{name}" '
                     "SET idle_in_transaction_session_timeout = '15s'")
    info = psycopg.conninfo.conninfo_to_dict(admin)
    info["dbname"] = name
    return psycopg.conninfo.make_conninfo(**info)


def _drop_database(name: str) -> None:
    with psycopg.connect(os.environ[ADMIN_DSN_ENV], autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def _real_tree_listing():
    from qa_tools.common import delivery
    tree = Path(delivery.DELIVERIES_DIR)
    return sorted(p.name for p in tree.iterdir()) if tree.exists() else None


def _bootstrap_into(corpus: Path, db_name: str, *, sequential: bool) -> tuple[dict, dict]:
    """One real bootstrap of `corpus` into a new database; its snapshot."""
    from cli import bdm, cp
    from qa_tools.common import bootstrap as boot

    mp = pytest.MonkeyPatch()
    original = equiv_support.apply_redirects(corpus)
    dsn = _fresh_database(db_name)
    scratch = None
    try:
        mp.setenv("MOTHMAN_SUPPLY_DSN", dsn)
        # Taken only once the DSN is this test's own - computed any earlier
        # it would name the REAL database's scratch, and the teardown below
        # would delete that.
        from qa_tools.common import supply_db
        scratch = supply_db.scratch_dir()
        mp.setenv(equiv_support.CORPUS_ENV, str(corpus))
        # A GitHub Actions runner sets this, and with it set the
        # orchestrators reconcile real GitHub Issues after every run.
        mp.delenv("GITHUB_REPOSITORY", raising=False)
        # Generated once, by the corpus fixture - both modes read it as is.
        mp.setattr(bdm, "generate_synthetic_data", lambda: None)
        mp.setattr(cp, "generate_synthetic_data", lambda: None)
        # BOTH MODES through the same wrapper - see its docstring.
        mp.setattr(boot, "_run_collection", equiv_support.redirected_run_collection)
        # bootstrap() sets this per process from `sequential`; put it back.
        from qa_tools.common import parallel_orchestrate
        mp.setattr(parallel_orchestrate, "TOOLS_CONCURRENTLY",
                   parallel_orchestrate.TOOLS_CONCURRENTLY)

        result = boot.bootstrap(force=True, sequential=sequential)
        assert result.populated
        return equiv_support.snapshot(dsn), result.timings
    finally:
        # dbt's per-database scratch, keyed by a digest of the DSN: each run
        # empties its own target directory, but the skeleton would stay
        # behind under data/dbt_scratch/ once per database name.
        mp.undo()
        equiv_support.restore(original)
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)
        if not os.environ.get("EQUIV_KEEP_DATABASES"):
            _drop_database(db_name)


@pytest.fixture(scope="module")
def both(corpus, worker_id):
    real_before = _real_tree_listing()
    # Named per xdist worker, not per process: a stable name is dropped and
    # recreated by the next run rather than accumulating.
    suffix = worker_id
    started = time.monotonic()
    sequential, seq_t = _bootstrap_into(corpus, f"equiv_seq_{suffix}", sequential=True)
    parallel, par_t = _bootstrap_into(corpus, f"equiv_par_{suffix}", sequential=False)
    print(f"\nsequential {seq_t}\nparallel   {par_t}\n"
          f"both {time.monotonic() - started:.0f}s")
    assert _real_tree_listing() == real_before, "the real delivery tree changed"
    return sequential, parallel


class TestTheCorpusIsWorthComparing:
    """A comparison of two empty histories passes and proves nothing, so
    the corpus has to be shown to exercise what parallelism could break."""

    def test_both_collections_ran(self, both):
        sequential, _ = both
        cols, runs = sequential["qa.run"]
        collections = {json.loads(row[cols.index("collection_id")]) for row in runs}
        assert collections == {"civil-registration", "child-protection"}, collections

    def test_every_tool_recorded_results(self, both):
        sequential, _ = both
        cols, rows = sequential["qa.check_result"]
        tools = {json.loads(row[cols.index("tool")]) for row in rows}
        assert {"dbt", "soda", "datacontract", "evidently"} <= tools, tools

    def test_some_checks_failed_and_some_passed(self, both):
        sequential, _ = both
        cols, rows = sequential["qa.check_result"]
        statuses = {json.loads(row[cols.index("status")]) for row in rows}
        assert {"pass", "fail"} <= statuses, statuses

    def test_the_decision_log_has_promotions_and_something_else(self, both):
        sequential, _ = both
        cols, rows = sequential["qa.decision"]
        actions = {json.loads(row[cols.index("action")]) for row in rows}
        assert {"promote", "promotion-withheld"} <= actions, actions

    def test_a_filing_depended_on_an_earlier_promotion(self, both):
        """A supply filed anywhere but its own current slot - the branch
        that reads what the collection has promoted so far."""
        sequential, _ = both
        cols, rows = sequential["qa.filing"]
        branches = {json.loads(row[cols.index("branch")]) for row in rows}
        assert branches - {"on-time-current-slot"}, branches


class TestParallelRecordsTheSameHistory:
    def test_identical_apart_from_the_named_exclusions(self, both):
        sequential, parallel = both
        diffs = equiv_support.differences(sequential, parallel)
        assert not diffs, "parallel bootstrap differs from sequential:\n" + "\n".join(diffs)
