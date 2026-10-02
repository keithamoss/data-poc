"""The explainer glossary: its strict schema, the alias and idea rules,
its categories, and the generated glossary.md with derived badges
(REQ-DOCS-119)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from qa_tools.common import explainers as ex
from qa_tools.common import validate_explainers as v

DIAGRAM = '''```mermaid
---
config:
  look: handDrawn
  handDrawnSeed: 42
  theme: neutral
---
flowchart LR
  accTitle: A delivery holds arrivals, and each arrival holds supplies.
  accDescr: A delivery holds arrivals, and each arrival holds supplies.
  D[Delivery] --> A[Arrival] --> S[Supply]
```

*A delivery holds arrivals, and each arrival holds supplies.*
'''


def entry(term, **over):
    e = {"term": term, "definition": f"What {term} means.", "aliases": [], "forms": [],
         "defined_by": ["REQ-DOCS-900"], "page": None, "draft": False, "idea": False,
         "category": "data"}
    e.update(over)
    return e


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / ".claude/skills/docs-house-style").mkdir(parents=True)
    shutil.copy(v.REPO_ROOT / v.HOUSE_STANDARD, tmp_path / v.HOUSE_STANDARD)
    reqs = {"requirements": [
        {"id": "REQ-DOCS-900", "status": "built", "signed_off": {"by": "Keith", "date": "2026-09-29"}},
        {"id": "REQ-DOCS-902", "status": "not_started"},
    ]}
    (tmp_path / "requirements.yaml").write_text(yaml.safe_dump(reqs))
    (tmp_path / "docs/explainers").mkdir(parents=True)
    write(tmp_path, [entry("supply", aliases=["drop"]),
                     entry("supply calendar", part_of="delivery agreement", category="calendar"),
                     entry("delivery agreement", category="calendar"),
                     entry("one-off extraction", defined_by=[], idea=True, draft=True)])
    ex.write_glossary_md(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


CATEGORIES = [{"key": "data", "title": "The data"},
              {"key": "calendar", "title": "The supply calendar"}]


def write(repo: Path, entries: list[dict], categories: list[dict] | None = None) -> None:
    cats = CATEGORIES if categories is None else categories
    (repo / "docs/explainers/glossary.yaml").write_text(
        yaml.safe_dump({"categories": cats, "entries": entries, "diagram": DIAGRAM}, sort_keys=False))


def findings(repo):
    return [f for f in v.Validator(repo).run() if f.rule.startswith("glossary") or f.rule.startswith("V-")]


def test_a_good_glossary_passes(repo):
    assert findings(repo) == [], "\n".join(f.render() for f in findings(repo))


def test_an_unknown_key_is_rejected(repo):
    write(repo, [entry("supply", colour="blue")])
    assert any(f.rule == "glossary-schema" for f in v.Validator(repo).run())


def test_a_missing_key_is_rejected(repo):
    e = entry("supply")
    del e["forms"]
    write(repo, [e])
    assert any(f.rule == "glossary-schema" for f in v.Validator(repo).run())


def test_an_alias_cannot_also_be_an_entry(repo):
    write(repo, [entry("supply", aliases=["drop"]), entry("drop")], CATEGORIES[:1])
    assert any("never has its own definition" in f.message for f in v.Validator(repo).run())


@pytest.mark.parametrize("over,msg", [
    ({"idea": True}, "marked as an idea but names"),
    ({"defined_by": []}, "names no defining requirement"),
    ({"defined_by": ["REQ-DOCS-999"]}, "not in requirements.yaml"),
])
def test_the_idea_rule_holds_both_ways(repo, over, msg):
    write(repo, [entry("supply", **over)], CATEGORIES[:1])
    assert any(msg in f.message for f in v.Validator(repo).run())


def test_a_stale_glossary_md_fails_the_validator(repo):
    write(repo, [entry("supply", definition="A changed definition.")], CATEGORIES[:1])
    assert any(f.rule == "glossary-stale" for f in v.Validator(repo).run())
    ex.write_glossary_md(repo)
    assert not any(f.rule == "glossary-stale" for f in v.Validator(repo).run())


def test_badges_are_derived_never_typed(repo):
    md = (repo / "docs/explainers/glossary.md").read_text()
    supply = md.split("### Supply\n", 1)[1].split("### ", 1)[0]
    assert "Build state" not in supply  # REQ-DOCS-900 is built
    idea = md.split("### One-off extraction\n", 1)[1].split("## ", 1)[0]
    assert "Build state: an idea, not designed yet." in idea
    assert "placeholder" in idea


def test_an_unsigned_definition_shows_as_proposed(repo):
    write(repo, [entry("supply", defined_by=["REQ-DOCS-902"])], CATEGORIES[:1])
    ex.write_glossary_md(repo)
    assert "Build state: proposed." in (repo / "docs/explainers/glossary.md").read_text()


def test_nesting_is_shown(repo):
    md = (repo / "docs/explainers/glossary.md").read_text()
    assert "Part of: delivery agreement." in md


def test_the_glossary_diagram_is_held_to_the_diagram_rules(repo):
    bad = DIAGRAM.replace("handDrawnSeed: 42", "handDrawnSeed: 7")
    (repo / "docs/explainers/glossary.yaml").write_text(
        yaml.safe_dump({"categories": CATEGORIES[:1], "entries": [entry("supply")], "diagram": bad},
                       sort_keys=False))
    ex.write_glossary_md(repo)
    assert any(f.rule == "V-hand-drawn-seed" for f in v.Validator(repo).run())


def test_an_entry_without_a_category_is_rejected(repo):
    e = entry("supply")
    del e["category"]
    write(repo, [e], CATEGORIES[:1])
    assert any(f.rule == "glossary-schema" for f in v.Validator(repo).run())


def test_an_entry_in_an_unknown_category_is_rejected(repo):
    write(repo, [entry("supply", category="nowhere")], CATEGORIES[:1])
    assert any("which is not in the categories list" in f.message for f in v.Validator(repo).run())


def test_an_empty_or_repeated_category_is_rejected(repo):
    write(repo, [entry("supply")], CATEGORIES)
    assert any("'calendar' has no entries" in f.message for f in v.Validator(repo).run())
    write(repo, [entry("supply")], CATEGORIES[:1] * 2)
    assert any("listed more than once" in f.message for f in v.Validator(repo).run())


def test_sections_render_in_the_listed_order_not_alphabetically(repo):
    """The supply calendar sits at the back (Keith, 2026-10-02), even
    though "delivery agreement" sorts before "supply" alphabetically."""
    md = (repo / "docs/explainers/glossary.md").read_text()
    assert md.index("## The data\n") < md.index("## The supply calendar\n")
    data = md.split("## The data\n", 1)[1].split("## The supply calendar\n", 1)[0]
    calendar = md.split("## The supply calendar\n", 1)[1]
    assert "### Supply\n" in data and "### One-off extraction\n" in data
    assert "### Delivery agreement\n" in calendar and "### Supply calendar\n" in calendar
    assert "### Delivery agreement\n" not in data


def test_entries_sort_alphabetically_within_a_section(repo):
    md = (repo / "docs/explainers/glossary.md").read_text()
    assert md.index("### One-off extraction\n") < md.index("### Supply\n")
