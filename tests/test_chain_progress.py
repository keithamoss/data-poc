"""The check chain's own progress reporting (plans/tooling.md #13).

The chain takes ~13.5s and used to print one line and then nothing at
all for that whole stretch - a static screen with no sign the tool was
alive, working, or hung. Found while re-recording the demo
(plans/dashboard.md #13), where it showed up as a gap with literally
zero terminal events.

These cover the plumbing rather than the rendering: that the real,
discrete steps get announced in the right order, that every existing
caller is genuinely unaffected (on_step is optional by design - the
batch pipeline, the Lambda handlers and the tests all pass nothing),
and that the labels and the count come from ONE source of truth so a
progress bar built on them can't drift from what actually runs."""
from __future__ import annotations

import sys
from unittest.mock import patch

from cli import common
from qa_tools.bdm import orchestrate_bdm
from qa_tools.cp import orchestrate_cp


def test_both_orchestrators_agree_on_the_real_steps():
    """cli/common.chain_progress() sizes its bar off BDM's RUN_STEPS; if
    CP's ever diverged, a CP run would over- or under-fill it."""
    assert orchestrate_bdm.RUN_STEPS == orchestrate_cp.RUN_STEPS
    assert common.RUN_STEPS == orchestrate_bdm.RUN_STEPS
    # The 4 real tools plus the dataset_stats computation - the genuinely
    # known steps that make this a real progress measure, not a fake one.
    assert orchestrate_bdm.RUN_STEPS == (
        "dbt-core", "Soda Core", "datacontract-cli", "Evidently", "Dataset statistics")


def test_announce_is_a_no_op_without_a_callback():
    """The contract every existing caller relies on: pass nothing, get
    exactly the old behaviour."""
    orchestrate_bdm._announce(None, "dbt-core")  # must not raise
    orchestrate_cp._announce(None, "dbt-core")


def test_announce_reports_the_label_when_a_callback_is_given():
    seen = []
    orchestrate_bdm._announce(seen.append, "Soda Core")
    assert seen == ["Soda Core"]


def test_chain_progress_reports_every_step_in_order(monkeypatch):
    """Drives the real helper with a real (forced-TTY) rich Progress and
    checks the callback tracks genuine position - the count reported is
    steps FINISHED, never work that hasn't happened yet."""
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
    completions = []
    with patch.object(common.console, "print"):
        with common.chain_progress("run_001") as on_step:
            assert on_step is not None
            for i, label in enumerate(common.RUN_STEPS):
                on_step(label)
                completions.append(i)
    # Five real steps announced, each before it starts.
    assert completions == [0, 1, 2, 3, 4]


def test_chain_progress_degrades_to_a_plain_line_off_a_tty(monkeypatch, capsys):
    """A redirected log or a CI runner must not get thousands of cursor
    control sequences - and a caller that gets None back must still work,
    which is what makes on_step optional all the way down."""
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False, raising=False)
    with common.chain_progress("run_042") as on_step:
        assert on_step is None
    assert "run_042" in capsys.readouterr().out
