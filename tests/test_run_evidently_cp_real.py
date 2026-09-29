"""Real Evidently AI integration test for qa_tools/cp/run_evidently_cp.py's
evaluate_evidently_cp() - the CP counterpart to
tests/test_run_evidently_bdm.py (concern_type PSI drift, not sex - see
that module's own docstring). Named test_run_evidently_cp_real.py, not
test_run_evidently_cp.py, since tests/test_run_evidently_cp.py already
exists (an earlier, narrower test of where this module's own results
get written, not its output-parsing logic - see that file's own
docstring)."""
from __future__ import annotations

import qa_tools.cp.run_evidently_cp as run_evidently_cp

from fixture_ids import CP_DIRTY_RUN_ID as _DIRTY_RUN_ID, CP_REF_RUN_ID as _REF_RUN_ID


def _run(monkeypatch, cp_duckdb_dir, run_id, run_timestamp, reference_run_id=_REF_RUN_ID):
    # THE WAREHOUSE, not a directory of CSVs (REQ-PIPE-102) -
    # cp_duckdb_dir is what staged the fixture's two arrivals into it.
    monkeypatch.setattr(run_evidently_cp, "write_qa_result", lambda *a, **k: None)
    return run_evidently_cp.evaluate_evidently_cp(run_id, run_timestamp, reference_run_id=reference_run_id)


def _psi(results):
    return next(r for r in results if r["check_name"] == "drift:PSI")


def _volume(results):
    return [r for r in results if r["check_name"] == "evidently:row_count_growth"]


def test_a_run_measured_against_itself_has_no_psi_drift(monkeypatch, cp_duckdb_dir):
    """NAMED FOR WHAT IT DRIVES rather than for a code path, because the
    path it used to name is gone. Passing a run as its own reference is
    something a test can still do; the pipeline cannot, since
    REQ-QAC-108 made the reference an EARLIER period's supply."""
    results = _run(monkeypatch, cp_duckdb_dir, _REF_RUN_ID, "2026-01-01T09:00:00Z")

    psi = _psi(results)
    assert psi["status"] == "pass"
    assert psi["engine"] == run_evidently_cp.ENGINE_TAG
    assert psi["reference_run_id"] == _REF_RUN_ID


def test_dirty_run_has_a_real_check_id_and_reference(monkeypatch, cp_duckdb_dir):
    """generator.dirty.apply_cp_notifications_presets(severity="red")
    perturbs concern_type's own value distribution (the same column
    this check watches) - real evidence this is a genuine, non-trivial
    PSI computation against real data, not just a shape check."""
    results = _run(monkeypatch, cp_duckdb_dir, _DIRTY_RUN_ID, "2026-04-01T09:00:00Z")

    psi = _psi(results)
    assert psi["check_id"] == run_evidently_cp.PSI_CHECK_ID
    assert psi["metric_value"] is not None
    assert psi["reference_run_id"] == _REF_RUN_ID


class TestARelativeVolumeCheckOnEveryDataset:
    """REQ-QAC-108 criterion 1, against the real staged fixture.

    Child Protection had only ABSOLUTE row-count bands, the same shape
    Birth Registrations had - so "judge volume the same way" meant
    adding something neither collection had rather than porting one to
    the other. A fixed lower bound cannot tell a table that has doubled
    in three years from one that arrived truncated; a proportional drop
    against the last promoted supply can.
    """

    def test_there_is_one_per_dataset_rather_than_one_per_collection(
            self, monkeypatch, cp_duckdb_dir):
        """SIX, because the question is about a TABLE. A collection-wide
        count would tell a reader something shrank without saying
        what."""
        volume = _volume(_run(monkeypatch, cp_duckdb_dir, _DIRTY_RUN_ID,
                               "2026-04-01T09:00:00Z"))
        assert len(volume) == 6
        assert len({r["dataset_id"] for r in volume}) == 6
        assert len({r["check_id"] for r in volume}) == 6

    def test_each_one_carries_both_bands(self, monkeypatch, cp_duckdb_dir):
        """A warn band and a fail band, in the criterion's own words -
        and the same two Birth Registrations uses, read from the one
        place both collections now get them from."""
        from qa_tools.common import evidently_common

        for r in _volume(_run(monkeypatch, cp_duckdb_dir, _DIRTY_RUN_ID,
                               "2026-04-01T09:00:00Z")):
            assert r["warn_threshold"] == round(evidently_common.WARN_ROW_DROP * 100, 2)
            assert r["fail_threshold"] == round(evidently_common.FAIL_ROW_DROP * 100, 2)
            assert r["warn_threshold"] < r["fail_threshold"]

    def _against(self, monkeypatch, counts):
        """Stand in for what the reference run RECORDED.

        THE FIXTURE STAGES BOTH RUNS AND CHECKS NEITHER, so there are no
        recorded dataset_stats for the reference - which is a fact about
        this fixture rather than about the code, and it would otherwise
        make every volume check here report "no reference" and prove
        nothing. The numbers handed in below are counted from the
        reference run's OWN REAL STAGED TABLES, so both sides of the
        comparison are real; only the recording step is skipped.
        """
        monkeypatch.setattr(run_evidently_cp, "recorded_row_counts",
                             lambda agency, collection, run_id: dict(counts))

    def test_it_measures_a_real_proportional_change(self, monkeypatch, cp_duckdb_dir):
        reference = run_evidently_cp._current_row_counts(_REF_RUN_ID)
        assert reference, "the fixture staged no reference tables to count"
        self._against(monkeypatch, reference)

        volume = _volume(_run(monkeypatch, cp_duckdb_dir, _DIRTY_RUN_ID,
                               "2026-04-01T09:00:00Z"))
        assert len(volume) == 6
        assert all(r["metric_value"] is not None for r in volume)
        assert all(r["row_count_total"] > 0 for r in volume)
        assert all(r["reference_run_id"] == _REF_RUN_ID for r in volume)

    def test_two_real_supplies_of_similar_size_do_not_trip_it(
            self, monkeypatch, cp_duckdb_dir):
        """The ordinary case, and the one a noisy check would ruin. The
        dirty run is a perturbed copy of the same population, so its
        tables are the same rough size - a volume check that reddens on
        that is a volume check people turn off."""
        self._against(monkeypatch, run_evidently_cp._current_row_counts(_REF_RUN_ID))
        volume = _volume(_run(monkeypatch, cp_duckdb_dir, _DIRTY_RUN_ID,
                               "2026-04-01T09:00:00Z"))
        assert all(r["status"] == "pass" for r in volume), \
            [(r["dataset_id"], r["metric_value"], r["status"]) for r in volume]

    def _reference_making_every_table_drop_by(self, fraction):
        """A reference chosen so EVERY table drops by `fraction`.

        Scaling the reference by one multiplier does not work, and the
        first version of this did: the dirty fixture perturbs
        cp_notifications, so its size relative to the reference is not
        the other five tables', and one multiplier put it in a
        different band. Deriving each table's reference from its own
        current count makes the test about the BANDS rather than about
        how much the fixture happens to have moved.
        """
        current = run_evidently_cp._current_row_counts(_DIRTY_RUN_ID)
        assert current, "the fixture staged no tables to count"
        return {t: round(n / (1 - fraction)) for t, n in current.items()}

    def test_it_can_reach_red(self, monkeypatch, cp_duckdb_dir):
        """Criterion 7. A check that cannot fail cannot make a supply
        ineligible for automatic promotion under REQ-PIPE-075 criterion
        3, which is the whole point of measuring volume rather than
        merely reporting it."""
        self._against(monkeypatch, self._reference_making_every_table_drop_by(0.40))

        volume = _volume(_run(monkeypatch, cp_duckdb_dir, _DIRTY_RUN_ID,
                               "2026-04-01T09:00:00Z"))
        assert len(volume) == 6
        assert all(r["status"] == "fail" for r in volume), \
            [(r["dataset_id"], r["metric_value"], r["status"]) for r in volume]

    def test_it_can_reach_amber_without_reaching_red(
            self, monkeypatch, cp_duckdb_dir):
        """TWO BANDS, NOT ONE - the criterion asks for both by name, and
        a check with one band cannot say "look at this" without also
        saying "stop"."""
        self._against(monkeypatch, self._reference_making_every_table_drop_by(0.17))

        volume = _volume(_run(monkeypatch, cp_duckdb_dir, _DIRTY_RUN_ID,
                               "2026-04-01T09:00:00Z"))
        assert len(volume) == 6
        assert all(r["status"] == "warn" for r in volume), \
            [(r["dataset_id"], r["metric_value"], r["status"]) for r in volume]

    def test_a_supply_that_GREW_is_never_flagged(self, monkeypatch, cp_duckdb_dir):
        """A drop only, not any change. A table that is accumulating
        arrives bigger than the last one every time, and a check that
        reddened on that would be red for ever on most real tables."""
        self._against(monkeypatch, self._reference_making_every_table_drop_by(-1.0))

        volume = _volume(_run(monkeypatch, cp_duckdb_dir, _DIRTY_RUN_ID,
                               "2026-04-01T09:00:00Z"))
        assert all(r["status"] == "pass" for r in volume), \
            [(r["dataset_id"], r["metric_value"], r["status"]) for r in volume]
        assert all(r["metric_value"] < 0 for r in volume), \
            "a supply that grew should report a negative drop, not zero"

    def test_no_reference_means_no_reference_rather_than_a_pass(
            self, monkeypatch, cp_duckdb_dir):
        """Criterion 5 again, on the volume half. It reports the same
        way the drift check does, because criterion 2 gives them one
        reference and they should have one answer to having none."""
        volume = _volume(_run(monkeypatch, cp_duckdb_dir, _DIRTY_RUN_ID,
                               "2026-04-01T09:00:00Z", reference_run_id=None))
        assert volume
        assert all(r["status"] == "nodata" for r in volume)
        assert all(r["metric_value"] is None for r in volume)
        # The measurement it COULD make is still reported - how many
        # rows arrived is a fact about this supply alone.
        assert all(r["row_count_total"] > 0 for r in volume)
