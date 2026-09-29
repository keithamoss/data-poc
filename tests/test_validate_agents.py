"""The `agents` gate's frontmatter checks, as far as the docs-* explainer
agents change them (REQ-DOCS-124 criteria 16 and 18)."""
from __future__ import annotations

from pathlib import Path

from qa_tools.common import validate_agents as va


def _agent(tmp_path: Path, name: str, extra: str) -> Path:
    p = tmp_path / f"{name}.md"
    p.write_text(f"---\nname: {name}\ndescription: A test agent.\n{extra}---\nBody.\n")
    return p


def test_the_keys_the_docs_agents_need_are_known(tmp_path):
    path = _agent(tmp_path, "docs-writer",
                  "model: claude-opus-5-5\nmaxTurns: 30\nomitClaudeMd: true\n"
                  "disallowedTools: Bash\nhooks: {}\n")
    errors, _ = va.validate_file(path)
    assert errors == []


def test_a_misspelled_key_is_still_caught(tmp_path):
    errors, _ = va.validate_file(_agent(tmp_path, "docs-writer", "model: claude-opus-5-5\nmaxturns: 30\n"))
    assert any("maxturns" in e for e in errors)


def test_a_docs_agent_must_pin_a_full_model_id(tmp_path):
    for bad in ("model: opus\n", "model: inherit\n", ""):
        errors, _ = va.validate_file(_agent(tmp_path, "docs-critic", bad))
        assert any("full model id" in e for e in errors), bad


def test_other_agents_may_still_use_an_alias(tmp_path):
    errors, _ = va.validate_file(_agent(tmp_path, "delivery-scoper", "model: opus\n"))
    assert errors == []
