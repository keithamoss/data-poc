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

Fixed by having run_pipeline()/run_pipeline_cp() derive the reference
run from the manifest's own first entry (run_01, always clean by
RUN_PLAN construction) and thread it through _run_one() explicitly,
rather than relying on the evaluator's own default. This test doesn't
invoke the real dbt/Soda/datacontract-cli/Evidently tools (out of
pytest's scope - see test_build_dashboard_data.py's own docstring);
it stubs out the three other real-tool evaluators and only checks what
reference_run_id/reference_csv actually reaches the Evidently call."""
from __future__ import annotations

import qa_tools.bdm.orchestrate_bdm as orchestrate_bdm
import qa_tools.cp.orchestrate_cp as orchestrate_cp


def test_bdm_run_one_forwards_manifest_reference_not_the_stale_default(monkeypatch):
    captured = {}

    def fake_evaluate_evidently_bdm(run_id, csv_filename, run_timestamp, reference_run_id=None, reference_csv=None):
        captured["reference_run_id"] = reference_run_id
        captured["reference_csv"] = reference_csv
        return []

    monkeypatch.setattr(orchestrate_bdm.run_dbt_bdm, "evaluate_dbt_bdm", lambda *a, **k: [])
    monkeypatch.setattr(orchestrate_bdm.run_soda_bdm, "evaluate_soda_bdm", lambda *a, **k: [])
    monkeypatch.setattr(orchestrate_bdm.run_datacontract_bdm, "evaluate_datacontract_bdm", lambda *a, **k: [])
    monkeypatch.setattr(orchestrate_bdm.run_evidently_bdm, "evaluate_evidently_bdm", fake_evaluate_evidently_bdm)

    entry = {"run_id": "run_05_2099-01-05", "file": "run_05_2099-01-05.csv"}
    # A reference deliberately different from run_evidently_bdm's own
    # hardcoded REFERENCE_RUN_ID default - the whole point being that
    # _run_one must forward exactly what it's given, not fall back.
    orchestrate_bdm._run_one(entry, "2099-01-05T00:00:00Z", "run_01_2099-01-01", "run_01_2099-01-01.csv")

    assert captured["reference_run_id"] == "run_01_2099-01-01"
    assert captured["reference_run_id"] != orchestrate_bdm.run_evidently_bdm.REFERENCE_RUN_ID
    assert captured["reference_csv"] == "run_01_2099-01-01.csv"


def test_cp_run_one_forwards_manifest_reference_not_the_stale_default(monkeypatch):
    captured = {}

    def fake_evaluate_evidently_cp(run_id, run_timestamp, reference_run_id=None):
        captured["reference_run_id"] = reference_run_id
        return []

    monkeypatch.setattr(orchestrate_cp.run_dbt_cp, "evaluate_dbt_cp", lambda *a, **k: [])
    monkeypatch.setattr(orchestrate_cp.run_soda_cp, "evaluate_soda_cp", lambda *a, **k: [])
    monkeypatch.setattr(orchestrate_cp.run_datacontract_cp, "evaluate_datacontract_cp", lambda *a, **k: [])
    monkeypatch.setattr(orchestrate_cp.run_evidently_cp, "evaluate_evidently_cp", fake_evaluate_evidently_cp)

    entry = {"run_id": "cp_run_05_2099-02-02"}
    orchestrate_cp._run_one(entry, "2099-02-02T00:00:00Z", "cp_run_01_2099-01-01")

    assert captured["reference_run_id"] == "cp_run_01_2099-01-01"
    assert captured["reference_run_id"] != orchestrate_cp.run_evidently_cp.REFERENCE_RUN_ID
