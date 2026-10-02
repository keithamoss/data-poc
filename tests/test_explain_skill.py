"""The /explain skill (REQ-DOCS-129): a main-session playbook that runs
the docs-* team in fixed steps. Whether a run FOLLOWS it is a matter for
the run itself; this checks the playbook says what the requirement says."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".claude/skills/explain/SKILL.md"
TEXT = SKILL.read_text()


def test_it_is_a_user_only_skill():
    """Criterion 1: Keith starts it; the model never invokes it itself."""
    front = yaml.safe_load(TEXT.split("---")[1])
    assert front["name"] == "explain" and front["disable-model-invocation"] is True


def test_the_steps_come_in_the_agreed_order():
    """Criterion 2."""
    steps = ["Scope the topic with Keith", "docs-writer drafts the brief", "Keith approves the brief",
             "docs-writer writes the page", "docs-illustrator fills the slots",
             "The validator and the recall check pass", "The reviews", "Push the draft",
             "Keith triages the findings", "docs-writer revises", "Keith signs off"]
    positions = [TEXT.index(f"## Step {n}. {s}") for n, s in enumerate(steps, 1)]
    assert positions == sorted(positions)


def test_every_agent_is_wrapped_in_a_snapshot_and_a_change_check():
    """Criterion 9."""
    assert "uv run mothman docs snapshot" in TEXT and "uv run mothman docs verify-changes" in TEXT


def test_commits_stage_paths_by_name():
    """Criterion 15."""
    assert "never `git add -A` or `git add .`" in TEXT


def test_the_reviews_run_the_fact_checker_twice_and_check_its_quotes():
    """Criterion 12."""
    assert "twice" in TEXT and "uv run mothman docs quote-check" in TEXT


def test_two_revision_loops_then_hand_back():
    """Criterion 18."""
    assert "After two loops without sign-off, stop" in TEXT


def test_the_working_folder_is_ignored_at_the_repository_root():
    """Criteria 4 and 5."""
    assert "docs/explainers/_work/" in (ROOT / ".gitignore").read_text().split()
    assert not (ROOT / "docs/explainers/.gitignore").exists()
