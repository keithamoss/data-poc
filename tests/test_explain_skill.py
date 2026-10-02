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


FLAT = " ".join(TEXT.split())


def test_each_agent_gets_its_own_snapshot_and_reports_are_saved_after_the_step():
    """REQ-DOCS-129 as amended 2026-10-02: per-agent snapshot files, and
    nothing saved mid-step, so a read-only agent's check never sees the
    main session's own saves."""
    assert "snapshot --out .git/docs-snapshot-<agent>-<n>.json" in FLAT
    assert "verify-changes <agent> --snapshot .git/docs-snapshot-<agent>-<n>.json" in FLAT
    assert "wait until every agent in the step has finished and passed verify-changes" in FLAT


def test_the_critics_report_is_checked_then_confirmed_by_the_finding_checker():
    """REQ-DOCS-129, REQ-DOCS-133, REQ-DOCS-134."""
    assert "uv run mothman docs check-findings" in FLAT and "docs-finding-checker" in FLAT
    assert FLAT.index("check-findings <report>") < FLAT.index("Start **docs-finding-checker**")


def test_a_re_review_works_from_a_round_copy_a_word_diff_and_saved_triage():
    """REQ-DOCS-129: the recipe is written down, not implied."""
    assert "round-<N>.md" in FLAT and "git diff --no-index --word-diff=plain" in FLAT
    assert "triage-round-<N>.yaml" in FLAT and "Anything he does not pick counts as declined" in FLAT
    assert "questions.yaml" in FLAT and "non_scope" in TEXT


def test_triage_shows_confirmed_findings_first_and_collapses_the_rest():
    """REQ-DOCS-129: rejected blockers stay visible; rejected should-fixes,
    code-rejected findings, polish and outside-the-brief are collapsed."""
    first, collapsed = FLAT.split("Then, collapsed below them:")
    assert "every blocker docs-finding-checker rejected, marked rejected" in first
    for item in ("should-fixes docs-finding-checker rejected", "findings check-findings rejected",
                 "polish findings", "outside-the-brief list"):
        assert item in collapsed, item
    assert "Nothing in the collapsed part sends the page back unless Keith picks it" in FLAT


def test_a_critic_sensitivity_blocker_holds_the_push_whatever_the_checker_says():
    """REQ-DOCS-129: the repository is public."""
    assert "whether or not docs-finding-checker confirmed it" in FLAT
