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
from conftest import mark_test_database

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
#: RED one (fails checks, so is filed and not promoted) and a later
#: supply, whose filing reads the decision log to tell a fill from a
#: resupply - which is what makes the chain a chain.
#:
#: Child Protection - its first quarterly delivery, six files and so six
#: arrivals into six datasets, all promoted into ONE period schema: the
#: shared-write case at its most concentrated. Then ONE file of its
#: second delivery: case workers are not due that quarter, so no slot of
#: theirs is open and the supply is HELD (REQ-PIPE-131) - a filing that
#: is not a fill. Trimmed to that one
#: file because each file is a whole run, and the other five add a minute
#: without adding a kind of record.
#:
#: Emergency Department (REQ-PIPE-262 criterion 14) - on Child Protection's
#: calendar, so the two replay as ONE receipt-ordered stream. Its 2013-Q1
#: supply is received on 22 January, before any Child Protection arrival in
#: that quarter. Its 2015-Q3 supply comes before Child Protection's first
#: grown delivery, on the 1 November 2015 round (one file kept): Child
#: Protection is at files_go_to_period 1, so that delivery fills 2016-Q1, and
#: as the first arrival after the claim window of ED's own November round
#: opens it makes ED's offset group's inheritances for 2015-Q4 (REQ-PIPE-323
#: criterion 3) - so ED's participation gap (REQ-GEN-251) inherits. Before
#: REQ-PIPE-262, --sequential ran Child Protection to its end and then ED,
#: so 2015-Q4's inheritances were made with ED's 2015-Q3 supply not yet
#: promoted - and its gap inherited nothing.
#:
#: BY RUN ID, which the generator numbers - so REQ-GEN-238 dropping Child
#: Protection's two oldest grown years renumbered them, and cp_run_025 (the
#: November 2015 delivery until then) became a 2016 one: the corpus lost the
#: delivery the gap depended on and CI run 40978105702 went red. The
#: corpus fixture's own check catches a run id that names nothing; this
#: one named the wrong delivery.
KEEP = {"birth-registrations": ("run_001", "run_002", "run_009", "run_017"),
        "cp-clients": ("cp_run_001", "cp_run_002", "cp_run_022"),
        "ed-presentations": ("ed_run_001", "ed_run_011"),
        # Linkage Products (REQ-GEN-334): its first delivery, 11 February
        # 2013 - the day of ED's first, on the same calendar, so the two
        # replay in one stream. No Child Protection supply of 2013-Q1 is
        # kept, so its Client Register reads are left out as not supplied:
        # a cross-collection run the equivalence still compares.
        "linkage-keys": ("lp_run_001",)}
#: Deliveries kept only in part: run id -> the files kept.
KEEP_ONLY_FILES = {"cp_run_002": {"cp_case_workers.csv"},
                   "cp_run_022": {"cp_clients.csv"}}

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
    from generator.output import generated_into

    root = tmp_path_factory.mktemp("equiv_corpus")
    with generated_into(root):
        pass

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
        mark_test_database(conn, name)
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
    from cli.collection_cli import of as _cli_of
    bdm, cp = _cli_of('bdm'), _cli_of('cp')
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
        mp.setattr(bdm, "generate_synthetic_data", lambda **_: None)
        mp.setattr(cp, "generate_synthetic_data", lambda **_: None)
        # AND THE BOOTSTRAP'S OWN GENERATION STEP, which reaches the generator
        # through cli.pipeline rather than these: regenerating here would
        # rewrite the cut-down corpus, under the redirected (empty) scripts
        # every scenario link is checked against.
        mp.setattr(boot, "_generate", lambda name, *, trial: None)
        # BOTH MODES through the same wrapper - see its docstring.
        mp.setattr(boot, "_run_collection", equiv_support.redirected_run_collection)
        mp.setattr(boot, "_run_stream", equiv_support.redirected_run_stream)
        # bootstrap() sets this per process from `sequential`; put it back.
        from qa_tools.common import parallel_orchestrate
        mp.setattr(parallel_orchestrate, "TOOLS_CONCURRENTLY",
                   parallel_orchestrate.TOOLS_CONCURRENTLY)

        result = boot.bootstrap(force=True, sequential=sequential)
        assert result.populated
        # OPENING ORDER WITHIN EACH COLLECTION, not the raw run_seq: the
        # parallel mode opens collections side by side, so their draws from
        # the one sequence interleave differently from the sequential mode's
        # while each collection's own order is the same (REQ-PIPE-279's rank
        # NFR). That order, and every row keyed on it, is still compared.
        return equiv_support.snapshot(dsn, run_seq_within_collection=True), result.timings
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
        from qa_tools import collections as registry

        assert collections == {c.id for c in registry.all_collections()}, collections

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

    def test_the_decision_log_has_promotions(self, both):
        sequential, _ = both
        cols, rows = sequential["qa.decision"]
        actions = {json.loads(row[cols.index("action")]) for row in rows}
        assert "promote" in actions, actions

    def test_a_filing_depended_on_an_earlier_promotion(self, both):
        """A supply filed anywhere but its own current slot - the branch
        that reads what the collection has promoted so far."""
        sequential, _ = both
        cols, rows = sequential["qa.filing"]
        branches = {json.loads(row[cols.index("branch")]) for row in rows}
        assert branches - {"open-slot-unfilled"}, branches


class TestASharedCalendarIsReplayedInReceiptOrder:
    """REQ-PIPE-262 criteria 12 and 14, in both modes: Emergency Department's
    2015-Q4 gap inherits ED's own newest supply, because that supply was
    promoted before Child Protection's 2015-Q4 delivery opened the quarter.
    WHICH PERIOD it sits in is the cut-down corpus's business - without ED's
    earlier quarters its 22 July supply files into 2015-Q2's open slot - so
    the test names the supply, not the period."""

    @staticmethod
    def _rows(history):
        cols, rows = history["qa.decision"]
        at = {c: cols.index(c) for c in ("dataset_id", "to_slot", "action", "supply")}
        return [{c: json.loads(row[i]) for c, i in at.items()} for row in rows
                if json.loads(row[at["dataset_id"]]) == "ed-presentations"]

    @pytest.mark.parametrize("mode", ["sequential", "parallel"])
    def test_eds_gap_inherits_its_newest_supply(self, both, mode):
        history = dict(zip(("sequential", "parallel"), both))[mode]
        rows = self._rows(history)
        promoted = [r for r in rows if r["action"] == "promote"]
        assert promoted, "the corpus promoted no ED supply - the test would prove nothing"
        # BY ITS ID, which embeds the receipt instant: the comparison snapshot
        # blanks a rule's effective_at (qa_tools/common/equivalence.py).
        newest = max(r["supply"] for r in promoted)
        gap = [(r["action"], r["supply"]) for r in rows if r["to_slot"] == "2015-Q4"]
        assert gap == [("inherit", newest)], (gap, newest)


class TestParallelRecordsTheSameHistory:
    def test_identical_apart_from_the_named_exclusions(self, both):
        sequential, parallel = both
        diffs = equiv_support.differences(sequential, parallel)
        assert not diffs, "parallel bootstrap differs from sequential:\n" + "\n".join(diffs)
