"""Real Evidently AI integration test for qa_tools/bdm/
run_evidently_bdm.py's evaluate_evidently_bdm() - the actual "compute a
real PSI drift metric and a real row-count-growth comparison, then
shape them into our check-result records" logic, not previously
exercised under pytest at all (see tests/conftest.py's own docstring
and tests/test_orchestrate_reference_run.py, which monkeypatches this
exact function out for its own, narrower purpose). Runs the REAL
evidently.Report + DataDriftPreset/RowCount classes against a small,
real, session-scoped BDM CSV fixture."""
from __future__ import annotations

import qa_tools.bdm.run_evidently_bdm as run_evidently_bdm

from fixture_ids import BDM_DIRTY_RUN_ID as _DIRTY_RUN_ID, BDM_REF_RUN_ID as _REF_RUN_ID

_REF_CSV = "pytest_bdm_ref.csv"
_DIRTY_CSV = "pytest_bdm_dirty.csv"


#: THE STAGING FIXTURE IS NAMED BY EVERY TEST HERE (2026-09-27), and it
#: was not before. These tests read the warehouse through the run's own
#: view schema, and nothing in this file staged anything - so they were
#: passing on a warehouse ANOTHER TEST FILE happened to have populated
#: on the same worker. `--dist loadfile` pins a file to a worker but
#: several files share that worker's database, so the dependency was
#: invisible until the file distribution changed: adding two unrelated
#: test files moved this one onto a worker where no BDM run had been
#: staged, and all three tests failed with `relation
#: "birth_registrations" does not exist`.
#:
#: `bdm_raw_dir` went at the same time. It named the flat CSVs, which
#: nothing here reads - the run ids and the warehouse are what these
#: tests are about.


def _patch(monkeypatch, bdm_delivery_dirs):
    """The row-count-growth check finds "the run before this one" from
    the arrivals RECOGNISED on disk (REQ-GEN-043), and recognition
    falls back to the real data/deliveries/ tree when nothing says
    otherwise - so a test that does not redirect it is comparing the
    fixture's dirty run against 42 real deliveries, or (more likely)
    finding no previous run at all and silently losing the check."""
    from qa_tools.common import delivery

    deliveries, receipts = bdm_delivery_dirs
    monkeypatch.setattr(delivery, "DELIVERIES_DIR", deliveries)
    monkeypatch.setattr(delivery, "RECEIPTS_DIR", receipts)
    monkeypatch.setattr(run_evidently_bdm, "write_qa_result", lambda *a, **k: None)


def _run(monkeypatch, bdm_delivery_dirs, run_id, run_timestamp, **kw):
    _patch(monkeypatch, bdm_delivery_dirs)
    return run_evidently_bdm.evaluate_evidently_bdm(
        run_id, run_timestamp,
        reference_run_id=kw.get("reference_run_id", _REF_RUN_ID),
    )


class TestASupplyWithNothingToMeasureAgainst:
    """REQ-QAC-108 criterion 5, in as many words: "SHALL report the
    check as having no reference, and SHALL NOT report it as passing".

    IT REPLACED A TEST OF THE OPPOSITE. That test drove
    run_id == reference_run_id - a run compared against itself - and
    asserted "pass", which was the honest reading of the code at the
    time: the reference was one run the batch chose once, so the first
    supply legitimately WAS its own reference. Criterion 4 removed that
    arrangement, so a run can no longer be its own reference at all, and
    the state it stood in for - a dataset's first supply, with nothing
    earlier promoted - now arrives as `reference_run_id=None`.

    A PASS HERE WOULD BE THE FALSE GREEN THIS PROJECT KEEPS PAYING FOR:
    it says the supply was compared against what came before and found
    fine, when nothing was compared at all.
    """

    def _results(self, monkeypatch, bdm_delivery_dirs):
        return _run(monkeypatch, bdm_delivery_dirs, _REF_RUN_ID,
                     "2026-01-01T06:30:00Z", reference_run_id=None)

    def test_the_drift_check_says_no_reference_rather_than_pass(
            self, monkeypatch, bdm_delivery_dirs, bdm_duckdb_dir):
        psi = next(r for r in self._results(monkeypatch, bdm_delivery_dirs)
                    if r["check_name"] == "drift:PSI")
        assert psi["status"] == "nodata"
        assert psi["metric_value"] is None, "a PSI value implies a comparison happened"
        assert psi["reference_run_id"] is None
        assert psi["engine"] == run_evidently_bdm.ENGINE_TAG

    def test_the_volume_check_says_the_same_thing(
            self, monkeypatch, bdm_delivery_dirs, bdm_duckdb_dir):
        """Criterion 2 gives drift and volume ONE reference, so they
        have one answer to having none."""
        growth = next(r for r in self._results(monkeypatch, bdm_delivery_dirs)
                       if r["check_name"] == "evidently:row_count_growth")
        assert growth["status"] == "nodata"
        assert growth["metric_value"] is None

    def test_the_volume_check_still_appears_at_all(
            self, monkeypatch, bdm_delivery_dirs, bdm_duckdb_dir):
        """IT USED TO VANISH on the first run, which reads on the page
        as a check nobody defined rather than as one with nothing to
        measure. A check that disappears when it has no answer is a
        check whose absence nobody can act on."""
        results = self._results(monkeypatch, bdm_delivery_dirs)
        assert len(results) == 2
        assert {r["check_name"] for r in results} == {
            "drift:PSI", "evidently:row_count_growth"}

    def test_the_row_count_is_still_reported(
            self, monkeypatch, bdm_delivery_dirs, bdm_duckdb_dir):
        """Having no reference stops the COMPARISON, not the
        measurement - how many rows arrived is a fact about this supply
        alone."""
        growth = next(r for r in self._results(monkeypatch, bdm_delivery_dirs)
                       if r["check_name"] == "evidently:row_count_growth")
        assert growth["row_count_total"] > 0


def test_dirty_run_produces_a_real_row_count_drop_failure(monkeypatch, bdm_delivery_dirs, bdm_duckdb_dir):
    """The dirty fixture run is ~97% smaller than the reference run
    (tests/conftest.py) - a real, deterministic way to force
    evaluate_evidently_bdm's row-count-growth check into a genuine
    "fail" via real Evidently RowCount metrics on both files, not a
    hand-computed stand-in."""
    results = _run(monkeypatch, bdm_delivery_dirs, _DIRTY_RUN_ID, "2026-01-02T06:30:00Z")

    assert len(results) == 2, \
        "the dirty run has a real preceding arrival on disk - row-count-growth must run"
    growth = next(r for r in results if r["check_name"] == "evidently:row_count_growth")
    assert growth["status"] == "fail"
    # metric_value is a POSITIVE percentage drop ((previous-current)/previous),
    # not a signed delta - a real >25% drop is what pushes past FAIL_ROW_DROP.
    assert growth["metric_value"] > 25.0, f"expected a real >25% drop, got {growth['metric_value']}%"
    assert growth["check_id"] == run_evidently_bdm.ROW_COUNT_GROWTH_CHECK_ID


def test_evaluate_evidently_bdm_forwards_the_given_reference_not_the_module_default(
        monkeypatch, bdm_delivery_dirs, bdm_duckdb_dir, tmp_path):
    """Regression coverage in the same spirit as
    tests/test_orchestrate_reference_run.py, but for the real function
    itself rather than a monkeypatched stand-in: a caller-supplied
    reference must actually be used for the real PSI computation, not
    silently fall back to REFERENCE_RUN_ID's own module-level default
    (a stale hardcoded date, plans/publishing-and-history.md's own
    account of the bug this guards against)."""
    _patch(monkeypatch, bdm_delivery_dirs)

    results = run_evidently_bdm.evaluate_evidently_bdm(
        _DIRTY_RUN_ID, "2026-01-02T06:30:00Z", reference_run_id=_REF_RUN_ID,
    )
    psi = next(r for r in results if r["check_name"] == "drift:PSI")
    assert psi["reference_run_id"] == _REF_RUN_ID
