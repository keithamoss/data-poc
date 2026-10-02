"""Regression test for a real, silent bug found while verifying
generator/generate_cp_runs.py's dirty.py import-resolution fix (2026-09-14):
qa_tools/bdm/orchestrate_bdm.py and qa_tools/cp/orchestrate_cp.py's
_run_one() called their Evidently evaluators with no reference_run_id/
reference_csv, so they always fell back to run_evidently_bdm.py's and
run_evidently_cp.py's own module-level REFERENCE_RUN_ID - a hardcoded
literal date string that goes stale every time the rolling anchor date
(generator/anchor_date.py) advances. Because data/raw/ and data/cp_raw/
aren't cleared between regenerations, a stale file left over from a
previous anchor date can still exist on disk under that old name, so
Evidently silently drifted against genuinely wrong reference data instead
of raising - CP's manifest happened not to have a stale file under that
exact old name, so it raised FileNotFoundError instead, which is what
surfaced this.

Fixed by threading the reference through _run_one() explicitly rather
than relying on the evaluator's own default.

WHAT THIS MODULE NOW GUARDS, since REQ-QAC-108 (2026-09-29), because
the original fix was itself replaced. Deriving the reference from the
manifest's first entry removed the stale LITERAL and kept the defect
underneath it: every supply, for ever, measured against the beginning
of history. Both the module-level constants and the batch-level choice
are gone, `None` means THERE IS NO REFERENCE rather than "fall back",
and the reference is resolved per supply from what was recorded. What
is still worth asserting here is the narrower property these tests were
always really about: an EXPLICIT reference - the one an operator names
by hand - reaches the check unchanged, and nothing in between
second-guesses it. This test doesn't
invoke the real dbt/Soda/datacontract-cli/Evidently tools (out of
pytest's scope - see test_build_dashboard_data.py's own docstring);
it stubs out the three other real-tool evaluators and only checks what
reference_run_id/reference_csv actually reaches the Evidently call.

_run_one() also computes+commits dataset_stats.json now
(plans/publishing-and-history.md Phase 3) - stubbed out here too, both
because it needs a real warehouse connection this fake entry has none
of, and because write_qa_result() defaults to the REAL qa_results_dir;
without stubbing it, this test would silently write a stray directory
into the actual project's committed qa_results/ tree on every run (a
real bug this test itself introduced and caught - see the "verify a
regression test actually fails first" convention, CLAUDE.md)."""
from __future__ import annotations

import qa_tools.bdm.orchestrate_bdm as orchestrate_bdm
import qa_tools.cp.orchestrate_cp as orchestrate_cp


class _FakeConn:
    """Enough of a connection for the orchestrators' dataset_stats step,
    which is stubbed out in these tests - they are about which reference
    run gets forwarded, not about anything the database says.

    `execute` earns its place: since REQ-PIPE-068 the orchestrators set
    the run's view schema on the connection before handing it over, so a
    fake with only close() stopped being a connection. The context
    manager earns its place the same way: REQ-PIPE-089 opens connections
    with `with`, so a fake without one stopped being a connection
    again."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def execute(self, *args, **kwargs):
        return self

    def fetchall(self):
        return []

    def close(self):
        pass


def test_bdm_run_one_forwards_manifest_reference_not_the_stale_default(monkeypatch, tmp_path):
    captured = {}

    def fake_evaluate_evidently_bdm(run_id, run_timestamp, reference_run_id=None):
        captured["reference_run_id"] = reference_run_id
        return []

    monkeypatch.setattr(orchestrate_bdm.run_dbt_bdm, "evaluate_dbt_bdm", lambda *a, **k: [])
    monkeypatch.setattr(orchestrate_bdm.run_soda_bdm, "evaluate_soda_bdm", lambda *a, **k: [])
    monkeypatch.setattr(orchestrate_bdm.run_datacontract_bdm, "evaluate_datacontract_bdm", lambda *a, **k: [])
    monkeypatch.setattr(orchestrate_bdm.run_evidently_bdm, "evaluate_evidently_bdm", fake_evaluate_evidently_bdm)
    monkeypatch.setattr(orchestrate_bdm.dataset_stats, "compute_dataset_stats", lambda *a, **k: {})
    monkeypatch.setattr(orchestrate_bdm, "write_qa_result", lambda *a, **k: tmp_path / "unused.json")
    # REQ-PIPE-089 brackets a run with these two. Stubbed on the same
    # terms as write_qa_result above: this test is about which reference
    # run gets forwarded, and a real run row would need a real database.
    monkeypatch.setattr(orchestrate_bdm, "open_run", lambda *a, **k: None)
    monkeypatch.setattr(orchestrate_bdm, "finish_run", lambda *a, **k: None)
    # The orchestrators no longer import duckdb directly - they open
    # the supply database through supply_db.connect() and set the
    # run's view schema on it (REQ-PIPE-068).
    monkeypatch.setattr(orchestrate_bdm.supply_db, "connect", lambda *a, **k: _FakeConn())
    # THE TABLE IS READABLE, said outright (2026-10-02). A Birth
    # Registrations run that cannot read its one table skips its tools
    # (REQ-PIPE-105, a contested resupply), and the fake connection's
    # empty catalogue would read as exactly that.
    monkeypatch.setattr(orchestrate_bdm.supply_db, "readable_in",
                        lambda conn, run_id: frozenset({"birth_registrations"}))

    # An arrival record's own shape (REQ-GEN-043) - `csv_path` is the
    # real file inside the delivery, not a name built from the run_id.
    # NO HYPHEN IN THE RUN ID (2026-09-27). It used to read
    # "run_05_2099-01-05", which nothing in this system actually mints -
    # a real run id is `run_005` - and supply_db now REFUSES a run id
    # that is not a usable identifier, because it becomes a PostgreSQL
    # schema name and dbt and Soda write that name unquoted. The date
    # here was flavour; the property this fixture needs is that the run
    # id is unrelated to csv_path, which still holds.
    entry = {"run_id": "run_005",
             "csv_path": "/x/2099-01-drop/birth_registrations_2099-01-05.csv"}
    # An explicit reference, which is what an operator naming one by
    # hand produces - the whole point being that _run_one forwards
    # exactly what it is given.
    orchestrate_bdm._run_one(entry, "2099-01-05T00:00:00Z", "test@example.com",
                              "run_01_2099-01-01")

    # IT USED TO ASSERT "not the module's own stale default". There is
    # no default any more (REQ-QAC-108 criterion 4): the constant was
    # deleted, and `None` now means THERE IS NO REFERENCE rather than
    # "fall back". So the claim worth making is the other one - an
    # explicit reference is forwarded UNCHANGED, and nothing between
    # here and the check second-guesses it.
    assert captured["reference_run_id"] == "run_01_2099-01-01"
    assert "reference_csv" not in captured, \
        "the reference is forwarded as a run id now, not a filename (REQ-PIPE-102)"


def test_cp_run_one_forwards_manifest_reference_not_the_stale_default(monkeypatch, tmp_path):
    captured = {}

    def fake_evaluate_evidently_cp(run_id, run_timestamp, reference_run_id=None):
        captured["reference_run_id"] = reference_run_id
        return []

    monkeypatch.setattr(orchestrate_cp.run_dbt_cp, "evaluate_dbt_cp", lambda *a, **k: [])
    monkeypatch.setattr(orchestrate_cp.run_soda_cp, "evaluate_soda_cp", lambda *a, **k: [])
    monkeypatch.setattr(orchestrate_cp.run_datacontract_cp, "evaluate_datacontract_cp", lambda *a, **k: [])
    monkeypatch.setattr(orchestrate_cp.run_evidently_cp, "evaluate_evidently_cp", fake_evaluate_evidently_cp)
    monkeypatch.setattr(orchestrate_cp.dataset_stats, "compute_dataset_stats", lambda *a, **k: {})
    monkeypatch.setattr(orchestrate_cp, "write_qa_result", lambda *a, **k: tmp_path / "unused.json")
    # REQ-PIPE-089 brackets a run with these two. Stubbed on the same
    # terms as write_qa_result above: this test is about which reference
    # run gets forwarded, and a real run row would need a real database.
    monkeypatch.setattr(orchestrate_cp, "open_run", lambda *a, **k: None)
    monkeypatch.setattr(orchestrate_cp, "finish_run", lambda *a, **k: None)
    # The orchestrators no longer import duckdb directly - they open
    # the supply database through supply_db.connect() and set the
    # run's view schema on it (REQ-PIPE-068).
    monkeypatch.setattr(orchestrate_cp.supply_db, "connect", lambda *a, **k: _FakeConn())

    entry = {"run_id": "cp_run_005"}  # see the BDM fixture above on the hyphen
    orchestrate_cp._run_one(entry, "2099-02-02T00:00:00Z", "test@example.com", "cp_run_01_2099-01-01")

    # IT USED TO ASSERT "not the module's own stale default". There is
    # no default any more (REQ-QAC-108 criterion 4): the constant was
    # deleted, and `None` now means THERE IS NO REFERENCE rather than
    # "fall back". So the claim worth making is the other one - an
    # explicit reference is forwarded UNCHANGED, and nothing between
    # here and the check second-guesses it.
    assert captured["reference_run_id"] == "cp_run_01_2099-01-01"
