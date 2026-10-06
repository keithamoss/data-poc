"""CI runs the tests marked on_demand on every push (post-build-review #128,
Keith 2026-10-06): a slow test deselected locally and run nowhere had already
failed unnoticed for two days."""
from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "test.yml"


def _jobs() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())["jobs"]


def test_a_job_runs_every_on_demand_test():
    runs = [step.get("run", "") for step in _jobs()["on-demand"]["steps"]]
    assert any("--run-on-demand" in r and "-m on_demand" in r for r in runs)


def test_it_runs_on_every_push_rather_than_on_a_schedule():
    triggers = yaml.safe_load(WORKFLOW.read_text())[True]  # YAML reads `on:` as True
    assert "push" in triggers
    assert "if" not in _jobs()["on-demand"], "the job must not be skipped conditionally"


def test_no_other_job_deselects_them_by_running_them():
    """They run in one place - the fast half must not pick them up too."""
    for name, job in _jobs().items():
        if name == "on-demand":
            continue
        for step in job.get("steps", []):
            assert "--run-on-demand" not in step.get("run", ""), name
