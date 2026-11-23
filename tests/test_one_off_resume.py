"""A one-off load that died INSIDE a run's checks is resumed by loading the same
package again: the retry opens a fresh attempt at that run, as a recurring
asset's re-check does (Keith 2026-11-22, 'Retry opens a new try';
REQ-PIPE-442 criterion 16).

THE DEFECT: the first load raised in Evidently, part way through the people
table's run - that run registered, its run_seq drawn, no completed_at. The
second load saw it as not completed and re-staged it, and staging's writes,
made before the orchestrator opens an attempt, were refused with
NoOpenAttempt (REQ-PIPE-279 criterion 8), so the load could never finish.
The committed fixture package, a throwaway supply_<id> and a temporary
repository and remote, as tests/test_one_off_end_to_end.py builds them.
"""
from __future__ import annotations

import pytest

from asset_model import assets

from test_one_off_end_to_end import Journey, _invoke, _reset
from test_one_off_load import _point

pytestmark = pytest.mark.asset("daily")


@pytest.fixture(scope="module")
def died_in_its_checks(tmp_path_factory):
    import subprocess

    from qa_tools.common import git_identity
    from qa_tools.tools import run_evidently

    j = Journey(tmp_path_factory.mktemp("one-off-resume"))
    with pytest.MonkeyPatch.context() as mp:
        _point(j, mp)
        mp.setattr(git_identity, "get_run_by", lambda: "tester@example.org")
        try:
            assert _invoke(["open", "--kind", "extraction", str(j.package)]).exit_code == 0
            subprocess.run(["git", "add", "-A"], cwd=j.repo, check=True)
            subprocess.run(["git", "commit", "-qm", "open"], cwd=j.repo, check=True)
            subprocess.run(["git", "push", "-q", "origin", "work"], cwd=j.repo, check=True)
            real = run_evidently.evaluate

            def dies(*a, **kw):
                raise RuntimeError("the test killed Evidently mid-run")

            mp.setattr(run_evidently, "evaluate", dies)
            j.first = _invoke(["load", "--id", j.id, str(j.package)])
            _reset()
            j.half = j.query("SELECT run_key, run_seq FROM qa.run WHERE completed_at IS NULL "
                             "AND run_seq IS NOT NULL")
            mp.setattr(run_evidently, "evaluate", real)
            j.second = _invoke(["load", "--id", j.id, str(j.package)])
            _reset()
            j.after = {k: s for k, s in j.query("SELECT run_key, run_seq FROM qa.run")}
            j.open = j.query("SELECT run_key FROM qa.run WHERE completed_at IS NULL")
            yield j
        finally:
            _reset()
            assets.use_one_offs_root(None)
            j.drop()


class TestALoadThatDiedInItsChecksIsResumed:
    def test_the_first_load_died_inside_a_run(self, died_in_its_checks):
        j = died_in_its_checks
        assert j.first.exit_code != 0
        assert j.half, "the first load must leave a run evaluated and unfinished, or this proves nothing"

    def test_loading_again_finishes_it(self, died_in_its_checks):
        j = died_in_its_checks
        assert j.second.exit_code == 0, (j.second.output[-2000:], j.second.exception)
        assert "Resuming the load into" in j.second.output
        assert j.open == []

    def test_on_a_fresh_attempt(self, died_in_its_checks):
        j = died_in_its_checks
        for run_key, seq in j.half:
            assert j.after[run_key] > seq, (run_key, seq, j.after[run_key])
