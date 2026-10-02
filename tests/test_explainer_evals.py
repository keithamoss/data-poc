"""The docs-* agents' eval set (REQ-DOCS-123): seven pages with known
content, each beside an expected-findings file in one fixed schema.

These tests check the SET, not the agents - running the agents needs a
real Claude session and real tokens, so it is not done in CI, and its
outcome is recorded as a dated summary in each agent's requirement."""
from __future__ import annotations

import shutil
import subprocess

import pytest
import yaml

from qa_tools.common import docs_guard
from qa_tools.common import explainers as ex
from qa_tools.common import validate_explainers as v

ROOT = v.REPO_ROOT
EVALS = ROOT / ex.EVALS
PAGES = sorted(EVALS.glob("*.md"))
EXPECTED = sorted(EVALS.glob("*.expected.yaml"))

#: Which agents each page targets (criterion 8, Keith set 6).
TARGETS = {
    "jargon.md": {"docs-critic"},
    "decorative-diagram.md": {"docs-critic"},
    "sensitivity-breach.md": {"docs-critic"},
    "wrong-fact.md": {"docs-fact-checker"},
    "naming-trap.md": {"docs-fact-checker"},
    "clean.md": {"docs-critic", "docs-fact-checker"},
    "injection.md": set(ex.DOCS_AGENTS),
}


def test_the_set_lives_outside_docs_explainers():
    assert not EVALS.resolve().is_relative_to((ROOT / ex.EXPLAINERS).resolve())


def test_there_are_exactly_the_seven_agreed_pages():
    assert {p.name for p in PAGES} == set(TARGETS)


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_each_page_says_it_is_a_test_fixture(page):
    front = yaml.safe_load(page.read_text().split("---")[1])
    assert "TEST FIXTURE" in front["eval_fixture"]


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_each_page_has_one_valid_expected_findings_file(page):
    path = page.with_name(page.stem + ".expected.yaml")
    exp = ex.load_eval_expectation(path)
    assert exp.page == page.name
    assert set(exp.targets) == TARGETS[page.name]
    assert ex.eval_expectation_problems(exp, page.read_text()) == []


def test_no_expected_file_is_orphaned():
    assert {p.name.removesuffix(".expected.yaml") + ".md" for p in EXPECTED} == set(TARGETS)


def test_only_the_injection_page_names_an_instruction_not_to_follow():
    for path in EXPECTED:
        exp = ex.load_eval_expectation(path)
        assert (exp.must_not_follow is not None) == (exp.page == "injection.md"), exp.page


def test_the_clean_page_tolerates_nothing_beyond_polish():
    exp = ex.load_eval_expectation(EVALS / "clean.expected.yaml")
    assert exp.must_find == []
    assert exp.worst_allowed == {"docs-critic": "polish", "docs-fact-checker": "supported"}


def test_the_sensitivity_breach_must_be_a_blocker():
    exp = ex.load_eval_expectation(EVALS / "sensitivity-breach.expected.yaml")
    assert [f.min_severity for f in exp.must_find] == ["blocker"]


def test_the_critic_claude_md_step_is_present():
    step = ex.EvalStep.model_validate(yaml.safe_load((EVALS / "critic-reads-claude-md.step.yaml").read_text()))
    assert step.agent == "docs-critic" and "CLAUDE.md" in step.ask


@pytest.mark.parametrize("broken", [
    {"colour": "blue"},
    {"must_find": [{"agent": "docs-critic", "quote": "x"}]},
])
def test_a_malformed_expected_file_fails(tmp_path, broken):
    """Criterion 10."""
    good = yaml.safe_load((EVALS / "jargon.expected.yaml").read_text())
    good.update(broken)
    path = tmp_path / "x.expected.yaml"
    path.write_text(yaml.safe_dump(good))
    with pytest.raises(ex.ValidationError):
        ex.load_eval_expectation(path)


def test_a_severity_off_the_agents_scale_fails():
    exp = ex.load_eval_expectation(EVALS / "wrong-fact.expected.yaml")
    exp.must_find[0].min_severity = "blocker"  # a critic severity, not a verdict
    assert any("not on docs-fact-checker's scale" in p
               for p in ex.eval_expectation_problems(exp, (EVALS / "wrong-fact.md").read_text()))


def test_a_quote_not_on_the_page_fails():
    exp = ex.load_eval_expectation(EVALS / "jargon.expected.yaml")
    exp.must_find[0].quote = "words the page never says"
    assert any("is not on the page" in p for p in ex.eval_expectation_problems(exp, (EVALS / "jargon.md").read_text()))


@pytest.mark.parametrize("agent", ex.DOCS_AGENTS)
def test_every_docs_agent_is_refused_the_eval_folder(agent):
    """An agent that could read the expected findings would be marking
    its own homework (criterion 13, REQ-DOCS-124)."""
    import json
    payload = json.dumps({"tool_name": "Read", "tool_input": {"file_path": str(EVALS / "jargon.expected.yaml")}})
    assert not docs_guard.guard_read(agent, payload).allowed


def test_the_clean_page_meets_the_house_standard(tmp_path):
    """The negative control is only a control if it is genuinely clean -
    so it is held to the real validator, as a page in group 2 would be."""
    text = (EVALS / "clean.md").read_text()
    text = text.replace("../../../../docs/explainers/glossary.md", "../glossary.md").replace("../../../../", "../../../")
    for f in ("requirements.yaml", str(v.HOUSE_STANDARD), "contract/data-asset.yaml",
              "contract/child-protection-contract.yaml", "docs/explainers/glossary.yaml",
              "docs/explainers/glossary.md"):
        (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / f, tmp_path / f)
    (tmp_path / "docs/explainers/2-calendar").mkdir(parents=True)
    (tmp_path / "docs/explainers/2-calendar/periods-and-slots.md").write_text(text)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    findings = v.Validator(tmp_path).run()
    assert findings == [], "\n".join(f.render() for f in findings)
