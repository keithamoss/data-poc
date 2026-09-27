"""Evidently's reference comes from what was RECORDED, not from rows.

WHY THIS SHAPE OF TEST. The existing Evidently tests pass whether the
reference is read from a CSV, from the warehouse, or from recorded
stats - they assert on the PSI verdict, which is the same either way
when all three agree. So they could not have caught the change this
module is about, and they cannot catch it regressing.

These assert the thing that is actually new: that the reference is
rebuilt from `dataset_stats`, and that rebuilding it that way is EXACT
rather than approximate. The exactness is the claim the whole design
rests on - if it were approximate, drift verdicts would move for no
reason a reader could explain.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from qa_tools.common import evidently_common as ec


class TestRebuildingAReferenceFromRecordedCounts:
    def test_the_frame_matches_the_recorded_distribution(self):
        counts = [["M", 897], ["F", 815], ["X", 25]]
        frame = ec.frame_from_value_counts(counts, "sex")
        assert len(frame) == 1737
        assert frame["sex"].value_counts().to_dict() == {"M": 897, "F": 815, "X": 25}

    def test_psi_is_bit_identical_to_using_the_real_rows(self):
        """THE CLAIM THE DESIGN RESTS ON. PSI over a categorical column
        depends only on the category proportions, so a reference rebuilt
        from counts is not an approximation of the real rows - it is the
        same distribution. Asserted as exact equality on purpose: an
        `approx` here would hide precisely the drift this is about."""
        rng = np.random.default_rng(7)
        real_reference = pd.DataFrame(
            {"sex": rng.choice(["M", "F", "U"], size=4000, p=[.48, .49, .03])})
        current = pd.DataFrame(
            {"sex": rng.choice(["M", "F", "U"], size=3500, p=[.40, .55, .05])})

        recorded = [[v, int(c)] for v, c in real_reference["sex"].value_counts().items()]
        rebuilt = ec.frame_from_value_counts(recorded, "sex")

        from_rows, _ = ec.compute_psi(current, real_reference, "sex")
        from_counts, _ = ec.compute_psi(current, rebuilt, "sex")
        assert from_rows == from_counts

    def test_scaling_every_count_down_preserves_psi_exactly(self):
        """Proportions are all PSI sees, so a reference of 41 rows and
        one of 492,000 with the same shape give the same answer. Worth
        pinning because it is what makes this safe at the scale this
        PoC is for - a million-row reference need not be materialised
        in full if it ever matters."""
        current = pd.DataFrame({"sex": ["M"] * 100 + ["F"] * 80 + ["U"] * 5})
        big, small = [["F", 240000], ["M", 240000], ["U", 12000]], [["F", 20], ["M", 20], ["U", 1]]
        psi_big, _ = ec.compute_psi(current, ec.frame_from_value_counts(big, "sex"), "sex")
        psi_small, _ = ec.compute_psi(current, ec.frame_from_value_counts(small, "sex"), "sex")
        assert psi_big == psi_small

    def test_an_empty_recording_gives_an_empty_frame(self):
        assert len(ec.frame_from_value_counts([], "sex")) == 0
        assert len(ec.frame_from_value_counts(None, "sex")) == 0


class TestItRefusesRatherThanGuessing:
    """A wrong count silently rounded is a wrong number inside a drift
    verdict, which is the direction that does not announce itself."""

    @pytest.mark.parametrize("bad", [
        [["M", "not-a-number"]],
        [["M"]],
        [["M", 10, 20]],
        [["M", None]],
    ])
    def test_a_malformed_entry_raises(self, bad):
        with pytest.raises(ValueError, match="value_counts"):
            ec.frame_from_value_counts(bad, "sex")

    def test_a_negative_count_raises(self):
        with pytest.raises(ValueError, match="negative"):
            ec.frame_from_value_counts([["M", -1]], "sex")


class TestReadingTheRealCommittedHistory:
    """Against this repository's own committed results rather than a
    fixture - the point is that the recording these depend on is really
    there, in the shape the code expects."""

    AGENCY, COLLECTION = "registry-services", "civil-registration"

    def test_a_real_run_has_a_recorded_sex_distribution(self, deployment_history):
        counts = ec.reference_value_counts(self.AGENCY, self.COLLECTION, "run_001", "sex")
        assert counts, "run_001 has no recorded value_counts - the reference has nowhere to come from"
        assert all(isinstance(c, int) and c >= 0 for _, c in counts)

    def test_a_real_run_has_a_recorded_row_count(self, deployment_history):
        assert ec.recorded_row_count(self.AGENCY, self.COLLECTION, "run_001") > 0

    def test_the_recorded_count_and_distribution_agree(self, deployment_history):
        """If these ever disagree, one of them is being computed from
        something other than the rows that landed."""
        counts = ec.reference_value_counts(self.AGENCY, self.COLLECTION, "run_001", "sex")
        assert sum(c for _, c in counts) == \
            ec.recorded_row_count(self.AGENCY, self.COLLECTION, "run_001")

    def test_an_unknown_run_reads_as_absent_rather_than_raising(self, deployment_history):
        """Absence is ordinary - a run checked as a trial and never staged
        has no recorded stats, and the caller falls back."""
        assert ec.reference_value_counts(self.AGENCY, self.COLLECTION, "no_such_run", "sex") is None
        assert ec.recorded_row_count(self.AGENCY, self.COLLECTION, "no_such_run") is None
