"""The five docs-* agent definitions hold to REQ-DOCS-124 to 128 and 133: least
privilege, a read and write guard in each agent's own hooks, a pinned
model, the right preloaded skills, and prompts that never copy a skill.

Whether the agents then BEHAVE is the eval set's job (REQ-DOCS-123),
which needs a real session. This is what can be checked from the files."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from qa_tools.common import explainers as ex
from qa_tools.common.validate_agents import MODEL_ALIASES, split_frontmatter, validate_file

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / ".claude/agents"
SKILLS = [ROOT / ".claude/skills/docs-house-style/SKILL.md", ROOT / ".claude/skills/docs-reader-judgement/SKILL.md"]

TOOLS = {
    "docs-writer": {"Read", "Grep", "Glob", "Write", "Edit"},
    "docs-illustrator": {"Read", "Grep", "Glob", "Write", "Edit"},
    "docs-fact-checker": {"Read", "Grep", "Glob"},
    "docs-critic": {"Read"},
    "docs-finding-checker": {"Read", "Grep", "Glob"},
}
FORBIDDEN = {"Bash", "WebFetch", "WebSearch", "Agent"}


def front(agent: str) -> dict:
    return yaml.safe_load(split_frontmatter((AGENTS / f"{agent}.md").read_text()))


def body(agent: str) -> str:
    return (AGENTS / f"{agent}.md").read_text().split("---", 2)[2]


@pytest.mark.parametrize("agent", ex.DOCS_AGENTS)
def test_the_file_passes_the_agents_gate(agent):
    errors, _ = validate_file(AGENTS / f"{agent}.md")
    assert errors == []


@pytest.mark.parametrize("agent", ex.DOCS_AGENTS)
def test_tools_are_exactly_what_the_job_needs(agent):
    """REQ-DOCS-124 criteria 1 to 4."""
    f = front(agent)
    tools = {t.strip() for t in f["tools"].split(",")}
    assert tools == TOOLS[agent]
    assert not tools & FORBIDDEN
    assert FORBIDDEN <= {t.strip() for t in f["disallowedTools"].split(",")}
    assert "mcpServers" not in f and "memory" not in f


@pytest.mark.parametrize("agent", ex.DOCS_AGENTS)
def test_each_agent_has_a_turn_limit_and_a_pinned_model(agent):
    """REQ-DOCS-124 criteria 5 and 16."""
    f = front(agent)
    assert isinstance(f["maxTurns"], int) and f["maxTurns"] > 0
    assert f["model"] not in MODEL_ALIASES and re.fullmatch(r"claude-[a-z]+-\d+(-\d+)*", f["model"])


@pytest.mark.parametrize("agent", ex.DOCS_AGENTS)
def test_both_guards_run_in_the_agents_own_hooks_under_its_own_name(agent):
    """REQ-DOCS-124 criteria 6 and 7. `|| exit 2` because exit 2 is the
    only code that blocks a tool call - an error exit of 1 would let it
    through."""
    hooks = front(agent)["hooks"]["PreToolUse"]
    by_matcher = {h["matcher"]: h["hooks"][0]["command"] for h in hooks}
    assert by_matcher["Read|Grep|Glob"].endswith(f"mothman docs guard-read {agent} || exit 2")
    assert by_matcher["Write|Edit|MultiEdit|NotebookEdit"].endswith(f"mothman docs guard-write {agent} || exit 2")


@pytest.mark.parametrize("agent,skills", [
    ("docs-writer", ["docs-house-style", "docs-reader-judgement"]),
    ("docs-illustrator", ["docs-house-style", "docs-reader-judgement"]),
    ("docs-fact-checker", ["docs-house-style", "docs-reader-judgement"]),
    ("docs-critic", ["docs-reader-judgement"]),
    ("docs-finding-checker", ["docs-reader-judgement"]),
])
def test_preloaded_skills(agent, skills):
    """REQ-DOCS-124 criterion 17, REQ-DOCS-127 criterion 4."""
    assert front(agent)["skills"] == skills


def _sentences(text: str) -> list[str]:
    flat = " ".join(text.split())
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", flat) if len(s.split()) >= 8]


@pytest.mark.parametrize("agent", ex.DOCS_AGENTS)
def test_no_prompt_copies_a_skills_wording(agent):
    """REQ-DOCS-124 criterion 17: a copied rule drifts from the skill it
    came from, and the skill is the one that gets updated."""
    prompt = " ".join(body(agent).split())
    for skill in SKILLS:
        for sentence in _sentences(skill.read_text()):
            assert sentence not in prompt, f"{agent} copies from {skill.parent.name}: {sentence}"


@pytest.mark.parametrize("agent", ex.DOCS_AGENTS)
def test_repository_text_is_material_and_an_injection_is_reported(agent):
    """REQ-DOCS-124 criteria 13 and 14."""
    text = body(agent)
    assert "material" in text and "not instructions" in text and "addressed to an AI" in text


@pytest.mark.parametrize("agent", ["docs-writer", "docs-illustrator", "docs-fact-checker", "docs-finding-checker"])
def test_the_reading_agents_are_told_to_stay_out_of_data(agent):
    """REQ-DOCS-124 criterion 15. The guard enforces it; the prompt says it."""
    assert "`data/`, `reports/` or any database" in body(agent)


@pytest.mark.parametrize("agent", ex.DOCS_AGENTS)
def test_every_agent_starts_cold(agent):
    """REQ-DOCS-127 criterion 1, REQ-DOCS-133 criterion 4, and the
    decision that all of them start without CLAUDE.md."""
    assert front(agent)["omitClaudeMd"] is True


def test_the_finding_checker_has_room_for_a_source_read_per_finding():
    """REQ-DOCS-133 criterion 4 and its SCALE note: findings are uncapped."""
    assert front("docs-finding-checker")["maxTurns"] >= 60


def test_the_critic_anchors_every_serious_finding():
    """REQ-DOCS-127 as amended 2026-10-02: no open channel and no
    'every finding' instruction; a named criterion, an outside-the-brief
    list, a not-a-finding list, and the re-review rules."""
    text = " ".join(body("docs-critic").split())
    assert "no confidence filter" not in text and "anything else you found yourself wondering" not in text
    for needle in ("names the one thing it breaks", "outside-the-brief list", "If you are not sure a reader would actually fail",
                   "These are not findings", "Raise new findings only on text the word diff marks as changed",
                   "Never raise again anything Keith did not pick", "manager test", "R<round>-F<number>"):
        assert needle in text, needle


def test_the_finding_checker_judges_and_never_rates():
    """REQ-DOCS-133 criteria 9 to 14 and 17."""
    text = " ".join(body("docs-finding-checker").split())
    for needle in ("**confirmed** or **rejected**", "does not actually break the criterion",
                   "the page already does what the finding says", "your reason names the sources you checked",
                   "non-scope", "Do not change a finding's severity, give it a score, or raise problems of your own",
                   "confirm that finding and add the injection row"):
        assert needle in text, needle


def _requirement(rid: str) -> dict:
    reqs = yaml.safe_load((ROOT / "requirements.yaml").read_text())["requirements"]
    return next(r for r in reqs if r["id"] == rid)


def _quoted(text: str) -> str:
    return re.search(r"word for word: '(.*?)'(?=\s+It SHALL|\s*$)", text, re.S).group(1)


def test_the_critic_carries_both_personas_word_for_word():
    """REQ-DOCS-127 criteria 5 and 10."""
    criteria = _requirement("REQ-DOCS-127")["acceptance_criteria"]
    prompt = " ".join(body("docs-critic").split())
    personas = [c for c in criteria if "persona Keith approved on 2026-09-29, word for word" in c]
    assert len(personas) == 2
    for c in personas:
        assert " ".join(_quoted(c).split()) in prompt


def test_the_writer_carries_its_approved_voice_word_for_word():
    """REQ-DOCS-125's decision, Keith 2026-10-02."""
    decision = next(d for d in _requirement("REQ-DOCS-125")["decisions"] if "POSITIVE PROSE" in d)
    voice = re.search(r"verbatim: '(.*)'", decision, re.S).group(1)
    assert " ".join(voice.split()) in " ".join(body("docs-writer").split())


def test_the_fact_checker_lists_story_sentences_but_still_checks_facts_inside_them():
    """REQ-DOCS-128 (Keith, 2026-10-02): an invented story sentence gets
    the verdict `story`, and a real fact inside a story is still checked."""
    text = body("docs-fact-checker")
    assert "gets the verdict `story`, with no source and no quote" in text
    assert "A real fact inside a story is still a claim of its own and is checked" in text
    assert "then exempt and story, then supported" in text


def test_the_fact_checker_names_one_source_per_row():
    """REQ-DOCS-128 (Keith, 2026-10-02): quote-check tolerates drift, the
    prompt still asks for the strict form."""
    assert "Name exactly one source for every row" in body("docs-fact-checker")


def test_the_fact_checker_returns_one_yaml_table_with_the_four_verdicts():
    """REQ-DOCS-128 criteria 1 and 2."""
    text = body("docs-fact-checker")
    for verdict in ("supported", "contradicted", "not found", "sources disagree"):
        assert f"**{verdict}**" in text
    assert "```yaml" in text
