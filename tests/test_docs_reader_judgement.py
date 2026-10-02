"""The reader-judgement skill (REQ-DOCS-131): the one standard docs-critic
preloads. The skill's own wording is Keith's, approved rule by rule, so
these pin what it holds and what it must never hold rather than how a
run applies it - that is the eval set's job (REQ-DOCS-123)."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".claude/skills/docs-reader-judgement/SKILL.md"
HOUSE = ROOT / ".claude/skills/docs-house-style/SKILL.md"
TEXT = SKILL.read_text()
FRONT = yaml.safe_load(TEXT.split("---")[1])
BODY = TEXT.split("---", 2)[2]

RULES = ["The answer comes first", "Every page stands alone", "Stories are about data, never the people in it",
         "A diagram earns its place", "Every sentence earns its place", "Rhetorical tics that follow a pattern"]


def _sentences(text: str) -> set[str]:
    flat = " ".join(text.split())
    return {s.strip() for s in re.split(r"(?<=[.!?])\s+", flat) if len(s.split()) >= 8}


def test_it_holds_the_six_rules_in_order():
    """Criteria 4 to 8 and 11: one heading per rule, the approved sixth
    rule after the diagram rule."""
    assert re.findall(r"^## (.+)$", BODY, re.M) == RULES


def test_the_sensitivity_rule_is_a_blocker():
    """Criterion 6."""
    section = BODY.split("## Stories are about data, never the people in it")[1].split("## ")[0]
    assert "A breach of this rule is a blocker." in section


def test_the_every_sentence_rule_and_the_description_are_keiths_approved_wording():
    """Criterion 11 (Keith, 2026-10-02, approved word for word)."""
    section = " ".join(BODY.split("## Every sentence earns its place")[1].split("## ")[0].split())
    assert section == (
        "Each sentence helps the reader with the page's why-question: it answers it, explains the answer, "
        "or shows it at work. A sentence that does none of these is excess, even when it is true. Detail that "
        "belongs to another concept is excess here too. It goes on that concept's page, and this page links to it.")
    assert FRONT["description"] == (
        "The rules a reader judges a finished Mothman documentation page by: answer first, each page stands "
        "alone, the sensitivity rule, whether a diagram argues, whether every sentence earns its place, and "
        "pattern-shaped rhetorical tics. Preloaded by docs-critic, docs-writer, docs-illustrator, "
        "docs-fact-checker, and docs-finding-checker.")


def test_it_can_be_preloaded_but_not_invoked_by_a_person():
    """Criterion 9."""
    assert FRONT["user-invocable"] is False and "disable-model-invocation" not in FRONT


def test_it_holds_only_rules_a_reader_can_apply():
    """Criterion 3: no validator rule id, no cast, no banned list - those
    live in the house standard."""
    assert not re.search(r"\bV-[a-z]", BODY)
    for name in ("Priya", "Sam", "Leah", "Squirrel", "Hannah"):
        assert name not in BODY, name
    assert "banned" not in BODY.lower()


def test_neither_skill_restates_the_other():
    """Criterion 1: one copy of each rule. Same test as the agent prompts
    get (test_docs_agents.test_no_prompt_copies_a_skills_wording)."""
    assert not _sentences(BODY) & _sentences(HOUSE.read_text())
