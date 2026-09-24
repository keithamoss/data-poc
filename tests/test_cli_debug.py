"""Tests for cli/debug.py - the mothman CLI's per-tool debug runners
(plans/tooling.md #1 Phase 4's "if it wasn't in the CLI, how would a
human debug it?" group). Focuses on the real dispatch/manifest-lookup
logic this module adds on top of each retired script's own evaluate_*()
function (BDM's csv_filename lookup, the reference-run default for
run-evidently) - not the real tools themselves, already covered by
qa_tools' own tests. Every evaluate_*() call here is monkeypatched: the
real functions write to committed qa_results/ history as a side effect
(see cli/debug.py's own module docstring) and must never run for real
under pytest."""
from __future__ import annotations

import rich_click as click
from click.testing import CliRunner

import cli.debug as debug_cli

_runner = CliRunner()

# `csv_path` is the real file INSIDE the delivery that arrived
# (REQ-GEN-043) - an absolute path with a supplier's own filename, not
# f"{run_id}.csv", which is why these look nothing like the run ids.
_BDM_MANIFEST = [
    {"run_id": "run_001", "csv_path": "/x/BDM_20260101/birth_registrations_2026-01-01.csv"},
    {"run_id": "run_002", "csv_path": "/x/drop-4471/birth_registrations_2026-01-02.csv"},
]
_CP_MANIFEST = [{"run_id": "cp_run_01"}, {"run_id": "cp_run_02"}]


def _patch_bdm_manifest(monkeypatch, manifest=_BDM_MANIFEST):
    from cli import bdm
    monkeypatch.setattr(bdm, "load_manifest", lambda: manifest)


def _patch_cp_manifest(monkeypatch, manifest=_CP_MANIFEST):
    from cli import cp
    monkeypatch.setattr(cp, "load_manifest", lambda: manifest)


def test_bdm_manifest_entry_returns_matching_entry(monkeypatch):
    _patch_bdm_manifest(monkeypatch)
    assert debug_cli._bdm_manifest_entry("run_002") == _BDM_MANIFEST[1]


def test_bdm_manifest_entry_raises_click_exception_when_missing(monkeypatch):
    _patch_bdm_manifest(monkeypatch)
    try:
        debug_cli._bdm_manifest_entry("no_such_run")
        raise AssertionError("expected ClickException")
    except click.ClickException as exc:
        assert "no_such_run" in str(exc.message)


def test_run_dbt_bdm_looks_up_nothing_and_calls_evaluate_dbt_bdm(monkeypatch):
    import qa_tools.bdm.run_dbt_bdm as run_dbt_bdm

    seen = {}

    def _fake_evaluate(run_id, run_timestamp):
        seen["run_id"] = run_id
        return [{"engine": "dbt", "check": "x", "status": "pass"}]
    monkeypatch.setattr(run_dbt_bdm, "evaluate_dbt_bdm", _fake_evaluate)

    result = _runner.invoke(debug_cli.debug_group, ["run-dbt", "--collection", "bdm", "--run-id", "run_001"])

    assert result.exit_code == 0, result.output
    assert seen["run_id"] == "run_001"


def test_run_dbt_cp_calls_evaluate_dbt_cp(monkeypatch):
    import qa_tools.cp.run_dbt_cp as run_dbt_cp

    seen = {}

    def _fake_evaluate(run_id, run_timestamp):
        seen["run_id"] = run_id
        return []
    monkeypatch.setattr(run_dbt_cp, "evaluate_dbt_cp", _fake_evaluate)

    result = _runner.invoke(debug_cli.debug_group, ["run-dbt", "--collection", "cp", "--run-id", "cp_run_01"])

    assert result.exit_code == 0, result.output
    assert seen["run_id"] == "cp_run_01"


def test_run_datacontract_bdm_passes_the_manifest_csv_filename(monkeypatch):
    _patch_bdm_manifest(monkeypatch)
    import qa_tools.bdm.run_datacontract_bdm as run_datacontract_bdm

    seen = {}

    def _fake_evaluate(run_id, csv_filename, run_timestamp):
        seen["run_id"] = run_id
        seen["csv_filename"] = csv_filename
        return []
    monkeypatch.setattr(run_datacontract_bdm, "evaluate_datacontract_bdm", _fake_evaluate)

    result = _runner.invoke(debug_cli.debug_group, ["run-datacontract", "--collection", "bdm", "--run-id", "run_002"])

    assert result.exit_code == 0, result.output
    assert seen == {"run_id": "run_002", "csv_filename": _BDM_MANIFEST[1]["csv_path"]}


def test_run_datacontract_bdm_unknown_run_id_fails_clearly(monkeypatch):
    _patch_bdm_manifest(monkeypatch)

    result = _runner.invoke(debug_cli.debug_group,
                             ["run-datacontract", "--collection", "bdm", "--run-id", "does_not_exist"])

    assert result.exit_code != 0
    assert "does_not_exist" in result.output


def test_run_datacontract_cp_does_not_need_a_csv_filename(monkeypatch):
    import qa_tools.cp.run_datacontract_cp as run_datacontract_cp

    seen = {}

    def _fake_evaluate(run_id, run_timestamp):
        seen["run_id"] = run_id
        return []
    monkeypatch.setattr(run_datacontract_cp, "evaluate_datacontract_cp", _fake_evaluate)

    result = _runner.invoke(debug_cli.debug_group, ["run-datacontract", "--collection", "cp", "--run-id", "cp_run_02"])

    assert result.exit_code == 0, result.output
    assert seen["run_id"] == "cp_run_02"


def test_run_evidently_bdm_defaults_reference_to_manifests_first_entry(monkeypatch):
    _patch_bdm_manifest(monkeypatch)
    import qa_tools.bdm.run_evidently_bdm as run_evidently_bdm

    seen = {}

    def _fake_evaluate(run_id, csv_filename, run_timestamp, reference_run_id, reference_csv):
        seen.update(run_id=run_id, csv_filename=csv_filename,
                     reference_run_id=reference_run_id, reference_csv=reference_csv)
        return []
    monkeypatch.setattr(run_evidently_bdm, "evaluate_evidently_bdm", _fake_evaluate)

    result = _runner.invoke(debug_cli.debug_group, ["run-evidently", "--collection", "bdm", "--run-id", "run_002"])

    assert result.exit_code == 0, result.output
    assert seen["run_id"] == "run_002"
    assert seen["reference_run_id"] == "run_001"
    assert seen["reference_csv"] == _BDM_MANIFEST[0]["csv_path"]


def test_run_evidently_bdm_honours_an_explicit_reference_run_id(monkeypatch):
    _patch_bdm_manifest(monkeypatch)
    import qa_tools.bdm.run_evidently_bdm as run_evidently_bdm

    seen = {}

    def _fake_evaluate(run_id, csv_filename, run_timestamp, reference_run_id, reference_csv):
        seen.update(reference_run_id=reference_run_id, reference_csv=reference_csv)
        return []
    monkeypatch.setattr(run_evidently_bdm, "evaluate_evidently_bdm", _fake_evaluate)

    result = _runner.invoke(debug_cli.debug_group, [
        "run-evidently", "--collection", "bdm", "--run-id", "run_002", "--reference-run-id", "run_002",
    ])

    assert result.exit_code == 0, result.output
    assert seen["reference_run_id"] == "run_002"
    assert seen["reference_csv"] == _BDM_MANIFEST[1]["csv_path"]


def test_run_evidently_cp_defaults_reference_to_manifests_first_run_id(monkeypatch):
    _patch_cp_manifest(monkeypatch)
    import qa_tools.cp.run_evidently_cp as run_evidently_cp

    seen = {}

    def _fake_evaluate(run_id, run_timestamp, reference_run_id):
        seen.update(run_id=run_id, reference_run_id=reference_run_id)
        return []
    monkeypatch.setattr(run_evidently_cp, "evaluate_evidently_cp", _fake_evaluate)

    result = _runner.invoke(debug_cli.debug_group, ["run-evidently", "--collection", "cp", "--run-id", "cp_run_02"])

    assert result.exit_code == 0, result.output
    assert seen == {"run_id": "cp_run_02", "reference_run_id": "cp_run_01"}


def test_build_warehouses_bdm_calls_build_per_run_warehouses(monkeypatch):
    import qa_tools.bdm.build_per_run_warehouses as build_per_run_warehouses

    called = []
    monkeypatch.setattr(build_per_run_warehouses, "build_all", lambda: called.append("bdm"))

    result = _runner.invoke(debug_cli.debug_group, ["build-warehouses", "--collection", "bdm"])

    assert result.exit_code == 0, result.output
    assert called == ["bdm"]


def test_build_warehouses_cp_calls_build_cp_warehouses(monkeypatch):
    import qa_tools.cp.build_cp_warehouses as build_cp_warehouses

    called = []
    monkeypatch.setattr(build_cp_warehouses, "build_all", lambda: called.append("cp"))

    result = _runner.invoke(debug_cli.debug_group, ["build-warehouses", "--collection", "cp"])

    assert result.exit_code == 0, result.output
    assert called == ["cp"]


def test_load_warehouse_calls_pipeline_load_all(monkeypatch):
    import pipeline.load as load_mod

    called = []
    monkeypatch.setattr(load_mod, "load_all", lambda: called.append(True))

    result = _runner.invoke(debug_cli.debug_group, ["load-warehouse"])

    assert result.exit_code == 0, result.output
    assert called == [True]


def test_changelog_prints_real_build_changelog_output_as_json(monkeypatch):
    import qa_tools.common.changelog as changelog

    monkeypatch.setattr(changelog, "build_changelog",
                         lambda agency, dataset: [{"agency": agency, "dataset": dataset}])

    result = _runner.invoke(debug_cli.debug_group,
                             ["changelog", "--agency", "registry-services", "--dataset", "birth-registrations"])

    assert result.exit_code == 0, result.output
    assert '"agency": "registry-services"' in result.output
    assert '"dataset": "birth-registrations"' in result.output
