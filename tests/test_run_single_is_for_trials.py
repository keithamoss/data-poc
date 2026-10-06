"""The single-run entry point is for trials only (REQ-PIPE-086 criterion 10).

Every route that KEEPS a supply goes through the per-arrival lifecycle
(criterion 1), and since REQ-PIPE-152 the Lambda handlers do too, so
nothing legitimate asks run_single to record under a real identity. It
refuses one before touching anything, so a caller that forgets this
records nothing at all rather than a run outside the lifecycle - unfiled,
never gated, and under an id the batch will later process as its own.
"""
from __future__ import annotations

import pytest

from qa_tools.bdm import orchestrate_bdm
from qa_tools.common import qa_store, supply_db, trial
from qa_tools.cp import orchestrate_cp


def _counts():
    with supply_db.connect(read_only=True, label="test-run-single") as conn:
        runs = conn.execute(f'SELECT count(*) FROM "{qa_store.SCHEMA}".run').fetchone()[0]
        staged = conn.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'staging'"
        ).fetchone()[0]
    return runs, staged


@pytest.fixture
def ensured(supply_dsn):
    with supply_db.connect(label="test-run-single") as conn:
        qa_store.ensure_schema(conn)


class TestARealIdentityIsRefused:

    def test_bdm_refuses_and_records_nothing(self, ensured, tmp_path):
        csv = tmp_path / "birth_registrations.csv"
        csv.write_text("not,read\n")
        before = _counts()
        with pytest.raises(trial.NotATrial, match="run_042"):
            orchestrate_bdm.run_single("run_042", str(csv), "2026-01-02",
                                       reference_run_id=None, run_by="t@example.com")
        assert _counts() == before

    def test_cp_refuses_and_records_nothing(self, ensured):
        before = _counts()
        with pytest.raises(trial.NotATrial, match="cp_run_042"):
            orchestrate_cp.run_single({"run_id": "cp_run_042", "received_at": None},
                                      reference_run_id=None, run_by="t@example.com")
        assert _counts() == before

    def test_the_refusal_says_what_to_use_instead(self):
        with pytest.raises(trial.NotATrial) as caught:
            trial.require_trial("run_042", "orchestrate_bdm.run_single")
        message = str(caught.value)
        assert "trial" in message and "per-arrival" in message

    def test_a_trial_identity_passes(self):
        trial.require_trial(trial.trial_run_id(), "orchestrate_bdm.run_single")
