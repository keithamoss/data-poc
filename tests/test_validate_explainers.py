"""`mothman docs validate` (REQ-DOCS-122, REQ-DOCS-132).

One known-good page passes with zero findings, and each rule is proven
by breaking that page in exactly one way. The good page runs the real
Mermaid parse, so a missing `npm ci` fails here rather than passing."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from qa_tools.common import validate_explainers as v

REAL = v.REPO_ROOT

GOOD = '''---
question: Why does a supply go into a slot?
summary: Each period has one slot per dataset, and a supply fills it.
group: 2-calendar
sources:
  - REQ-DOCS-900
  - contract/data-asset.yaml
build_state: designed, not built yet
status: draft
---

# Periods and slots

Build state: designed, not built yet.

> [!NOTE]
> A period is one quarter of the year, and each dataset has one slot in it.
> A supply fills the slot for its period.
> The slot tells you whether the supply you expected has arrived.

Priya sends a file on a Tuesday, and Sam wonders where it will land.
It lands in the slot for its period, which is how you find it later.

```mermaid
---
config:
  look: handDrawn
  handDrawnSeed: 42
  theme: neutral
---
flowchart LR
  accTitle: Each supply fills one slot in one period.
  accDescr: Each supply fills one slot in one period.
  S[A supply] --> P[Its slot]
```

*Each supply fills one slot in one period.*

## Why it's this way

Build state: designed, not built yet.

- We chose one slot per period because it makes a missing supply visible.

A slot belongs to a period. A supply fills a slot. See the [glossary](../glossary.md) next.

## Where this comes from

- [REQ-DOCS-900](../../../requirements.yaml)
- [contract/data-asset.yaml](../../../contract/data-asset.yaml)
'''


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / ".claude/skills/docs-house-style").mkdir(parents=True)
    shutil.copy(REAL / v.HOUSE_STANDARD, tmp_path / v.HOUSE_STANDARD)
    reqs = {"requirements": [
        {"id": "REQ-DOCS-900", "status": "not_started", "signed_off": {"by": "Keith", "date": "2026-09-29"}},
        {"id": "REQ-DOCS-901", "status": "built", "signed_off": {"by": "Keith", "date": "2026-09-29"}},
        {"id": "REQ-DOCS-902", "status": "not_started"},
    ]}
    (tmp_path / "requirements.yaml").write_text(yaml.safe_dump(reqs))
    (tmp_path / "contract").mkdir()
    (tmp_path / "contract/data-asset.yaml").write_text("x: 1\n")
    (tmp_path / "docs/explainers/2-calendar").mkdir(parents=True)
    (tmp_path / "docs/explainers/glossary.md").write_text("# Glossary\n")
    write(tmp_path, GOOD)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    return tmp_path


def write(repo: Path, text: str) -> None:
    (repo / "docs/explainers/2-calendar/periods-and-slots.md").write_text(text)


def rules_hit(repo: Path) -> set[str]:
    return {f.rule for f in v.Validator(repo).run()}


def test_the_good_page_passes_with_zero_findings(repo):
    findings = v.Validator(repo).run()
    assert findings == [], "\n".join(f.render() for f in findings)


def test_the_rule_ids_match_the_house_standard_both_ways():
    assert set(v.RULES) == v.standard_rule_ids()


def test_no_banned_word_is_copied_into_the_code():
    """The standard owns the lists (REQ-DOCS-132 criterion 8)."""
    code = (REAL / "qa_tools/common/validate_explainers.py").read_text().lower()
    rules = v.load_house_rules()
    words = [w for ws in rules["banned"].values() for w in ws] + list(rules["watch"])
    for w in words:
        assert f'"{w.lower()}"' not in code and f"'{w.lower()}'" not in code, w


def test_one_watch_word_alone_passes(repo):
    write(repo, GOOD.replace("Sam wonders where it will land.", "Sam runs a quick check."))
    assert rules_hit(repo) == set()


def test_two_watch_words_in_one_paragraph_fail(repo):
    """Keith, 2026-10-02: fine alone, a tell when they gather."""
    write(repo, GOOD.replace("Sam wonders where it will land.", "Sam runs a quick, robust check."))
    assert "V-banned-cluster" in rules_hit(repo)
    assert "V-banned-phrase" not in rules_hit(repo)


def test_the_same_watch_word_twice_counts_twice(repo):
    write(repo, GOOD.replace("Sam wonders where it will land.", "A quick look, then a quick fix."))
    assert "V-banned-cluster" in rules_hit(repo)


def test_watch_words_in_different_paragraphs_pass(repo):
    write(repo, GOOD.replace("Sam wonders where it will land.", "Sam runs a quick check.")
                    .replace("It lands in the slot for its period, which is how you find it later.",
                             "It lands in the slot for its period.\n\nThe slot is simple to find."))
    assert "V-banned-cluster" not in rules_hit(repo)


@pytest.mark.parametrize("phrase", ["intricate", "serves as", "stands as"])
def test_wikipedias_gaps_fail_on_sight(repo, phrase):
    write(repo, GOOD.replace("Sam wonders where it will land.", f"Sam wonders, and it {phrase} a clue."))
    assert "V-banned-phrase" in rules_hit(repo)


@pytest.mark.parametrize("old,new,rule", [
    ("Sam wonders where it will land.", "Sam wonders where it will land; it lands.", "V-semicolon"),
    ("Sam wonders where it will land.", "Sam wonders, eg where it will land.", "V-latin-abbreviation"),
    ("Sam wonders where it will land.", "Sam doesn't know where it will land.", "V-negative-contraction"),
    ("Sam wonders where it will land.", "Sam wonders what happens at midnight.", "V-midnight"),
    ("## Why it's this way", "## Why is it this way?", "V-question-heading"),
    ("Sam wonders where it will land.", "Sam wonders—where will it land.", "V-dash"),
    ("Sam wonders where it will land.", "Sam waits 3-5 days.", "V-range-dash"),
    ("Sam wonders where it will land.", "Sam simply wonders where it will land.", "V-banned-phrase"),
    ("Sam wonders where it will land.", "Sam wonders where REQ-DOCS-900 lands.", "V-body-requirement-id"),
    ("Sam wonders where it will land.", "Sam runs `mothman` to see.", "V-body-code"),
    ("Sam wonders where it will land.", "Sam reads contract/data-asset.yaml first.", "V-body-file-path"),
    ("Sam wonders where it will land.", "Sam wonders <b>where</b> it will land.", "V-raw-html"),
    ("Sam wonders where it will land.", "Sam wonders. <!-- hidden -->", "V-raw-html"),
    ("Sam wonders where it will land.", "Sam wonders ![x](../glossary.md) it.", "V-image"),
    ("Sam wonders where it will land.", "Sam reads postgresql://user:pw@host/db here.", "V-external-url"),
    ("[glossary](../glossary.md)", "[glossary](../../../contract/data-asset.yaml)", "V-link-target"),
    ("[glossary](../glossary.md)", "[glossary](../nope.md)", "V-link-target"),
    ("Sam wonders where it will land.", "Sam wonders where it will​ land.", "V-hidden-character"),
    ("> [!NOTE]", "> [!TIP]", "V-in-short"),
    ("  accDescr: Each supply fills one slot in one period.\n", "  click S call x()\n  accDescr: Each supply fills one slot in one period.\n", "V-mermaid-directive"),
    ("  S[A supply] --> P[Its slot]", "  S[A supply --> P[Its slot]", "V-mermaid-parse"),
    ("  theme: neutral\n", "", "V-mermaid-config"),
    ("  handDrawnSeed: 42\n", "  handDrawnSeed: 7\n", "V-hand-drawn-seed"),
    ("*Each supply fills one slot in one period.*", "Each supply fills one slot in one period.", "V-caption"),
    ("  accTitle: Each supply fills one slot in one period.", "  accTitle: Something else.", "V-caption-accessible"),
    ("group: 2-calendar\n", "", "V-front-matter"),
    ("summary: Each period has one slot per dataset, and a supply fills it.", "summary: " + "x" * 161, "V-summary-length"),
    ("status: draft", "status: signed off", "V-sign-off-record"),
    ("build_state: designed, not built yet", "build_state: built", "V-build-state"),
])
def test_each_rule_catches_its_own_breakage(repo, old, new, rule):
    assert old in GOOD
    write(repo, GOOD.replace(old, new, 1))
    assert rule in rules_hit(repo)


def test_a_long_sentence_and_a_long_paragraph(repo):
    long = " ".join(["word"] * 26) + "."
    write(repo, GOOD.replace("Sam wonders where it will land.", long))
    assert "V-sentence-length" in rules_hit(repo)
    many = " ".join(["One short one."] * 6)
    write(repo, GOOD.replace("Sam wonders where it will land.", many))
    assert "V-paragraph-length" in rules_hit(repo)


def test_an_exempted_phrase_passes(repo):
    write(repo, GOOD.replace("Sam wonders where it will land.", "Sam likes just-in-time supplies."))
    assert "V-banned-phrase" not in rules_hit(repo)


def test_a_period_name_is_not_a_range(repo):
    write(repo, GOOD.replace("Sam wonders where it will land.", "Sam checks the 2026-Q3 period."))
    assert "V-range-dash" not in rules_hit(repo)


def test_the_hand_drawn_look_is_refused_on_a_timeline(repo):
    write(repo, GOOD.replace("flowchart LR", "timeline").replace("  S[A supply] --> P[Its slot]", "  2026 : one"))
    assert "V-hand-drawn-type" in rules_hit(repo)


def test_a_signed_page_passes_with_its_hash_and_fails_after_an_edit(repo):
    signed = GOOD.replace("status: draft", "status: signed off")
    h = v.page_hash(signed)
    record = (f"signed_off:\n  by: Keith\n  date: '2026-09-29'\n  hash: {h}\n"
              "  last_reviewed: '2026-09-29'\n  review_by: '2026-11-01'\n---")
    signed = signed.replace("status: signed off\n---", "status: signed off\n" + record, 1)
    write(repo, signed)
    assert v.Validator(repo).run() == []
    write(repo, signed.replace("Sam wonders", "Sam asks"))
    assert "V-sign-off-hash" in rules_hit(repo)


def test_a_badge_change_does_not_change_the_hash():
    """Signing or building a cited requirement changes only the build
    state, which must never force a fresh sign-off."""
    after = GOOD.replace("build_state: designed, not built yet", "build_state: built") \
                .replace("Build state: designed, not built yet.\n\n", "")
    assert v.page_hash(GOOD) == v.page_hash(after)


def test_a_mixed_page_needs_the_by_section_block_and_markers(repo):
    mixed = GOOD.replace("status: draft", "status: draft\nsection_sources:\n  Why it's this way:\n    - REQ-DOCS-901")
    write(repo, mixed)
    hits = [f for f in v.Validator(repo).run() if f.rule == "V-build-state"]
    assert hits, "a built section still carries the not-built marker and the one-line block"
    msg = " ".join(f.message for f in hits)
    assert 'Built: "Why it\'s this way"' in msg
    fixed = mixed.replace(
        "Build state: designed, not built yet.\n\n> [!NOTE]",
        'Build state, by section:\n- Designed, not built yet: "Periods and slots".\n'
        '- Built: "Why it\'s this way".\n\n> [!NOTE]').replace(
        "## Why it's this way\n\nBuild state: designed, not built yet.\n\n", "## Why it's this way\n\n")
    write(repo, fixed)
    assert [f for f in v.Validator(repo).run() if f.rule == "V-build-state"] == []


def test_an_unsigned_source_makes_the_page_proposed(repo):
    write(repo, GOOD.replace("REQ-DOCS-900", "REQ-DOCS-902"))
    msgs = [f.message for f in v.Validator(repo).run() if f.rule == "V-build-state"]
    assert any("proposed" in m for m in msgs)


def test_the_working_folder_is_not_checked(repo):
    work = repo / "docs/explainers/_work/2026-09-29-x"
    work.mkdir(parents=True)
    (work / "report.md").write_text("Anything <b>at all</b> goes; https://example.org\n")
    assert v.Validator(repo).run() == []


def test_a_stray_file_type_is_refused(repo):
    (repo / "docs/explainers/2-calendar/diagram.svg").write_text("<svg/>")
    assert "V-file-type" in rules_hit(repo)


def test_a_missing_node_fails_rather_than_skips(repo, monkeypatch):
    monkeypatch.setattr(v.shutil, "which", lambda _: None)
    findings = [f for f in v.Validator(repo).run() if f.rule == "V-mermaid-parse"]
    assert findings and "never skipped" in findings[0].message


def test_list_rules_prints_every_rule():
    from click.testing import CliRunner

    from cli.app import cli
    out = CliRunner().invoke(cli, ["docs", "validate", "--list-rules"]).output
    for rule in v.RULES:
        assert rule in out


# ---- REQ-DOCS-121: the source index and the recall check

GLOSSARY = {
    "categories": [{"key": "c", "title": "C"}],
    "entries": [
        {"term": "slot", "definition": "One expected supply.", "aliases": [], "forms": [],
         "defined_by": ["REQ-DOCS-900"], "page": None, "draft": False, "idea": False, "category": "c"},
        {"term": "promote", "definition": "Move it in.", "aliases": [], "forms": ["promotion"],
         "defined_by": ["REQ-DOCS-901"], "page": None, "draft": False, "idea": False, "category": "c"},
    ],
    "diagram": "x",
}


def with_glossary(repo: Path) -> None:
    (repo / "docs/explainers/glossary.yaml").write_text(yaml.safe_dump(GLOSSARY, sort_keys=False))


def recall(repo: Path) -> list[str]:
    return [f.message for f in v.Validator(repo).run() if f.rule == "recall"]


def test_a_defined_term_must_cite_its_defining_requirement(repo):
    with_glossary(repo)
    write(repo, GOOD.replace("Sam wonders where it will land.", "Sam meets a **promotion** today."))
    msgs = recall(repo)
    assert len(msgs) == 1 and "'promote'" in msgs[0] and "REQ-DOCS-901" in msgs[0]


def test_a_passing_mention_needs_no_citation(repo):
    with_glossary(repo)
    write(repo, GOOD.replace("Sam wonders where it will land.", "Sam waits for the promotion."))
    assert recall(repo) == []


def test_a_cited_definition_passes(repo):
    with_glossary(repo)
    write(repo, GOOD.replace("Sam wonders where it will land.", "Each period has one **slot** per dataset."))
    assert recall(repo) == []


@pytest.mark.parametrize("word", ["promoted", "promoting", "Promotes", "PROMOTION"])
def test_regular_inflections_and_listed_forms_match(repo, word):
    with_glossary(repo)
    write(repo, GOOD.replace("Sam wonders where it will land.", f"It was **{word}** today."))
    assert recall(repo), word


def test_a_longer_term_does_not_also_define_the_shorter_one_inside_it(repo):
    """Found 2026-10-02: bolding 'delivery months' counted as defining
    'delivery' too, demanding a citation for a concept the page never
    explains. The longer term that covers the shorter one is the one
    being defined."""
    g = yaml.safe_load(yaml.safe_dump(GLOSSARY))
    g["entries"].append({"term": "promotion queue", "definition": "What waits.", "aliases": [], "forms": [],
                         "defined_by": ["REQ-DOCS-902"], "page": None, "draft": False, "idea": False,
                         "category": "c"})
    (repo / "docs/explainers/glossary.yaml").write_text(yaml.safe_dump(g, sort_keys=False))
    write(repo, GOOD.replace("Sam wonders where it will land.", "Each period has one **promotion queue**."))
    msgs = recall(repo)
    assert len(msgs) == 1 and "REQ-DOCS-902" in msgs[0], msgs


def test_bold_in_the_sources_list_does_not_count(repo):
    with_glossary(repo)
    write(repo, GOOD.replace("- [contract/data-asset.yaml]", "- **promotion** [contract/data-asset.yaml]"))
    assert recall(repo) == []


@pytest.mark.parametrize("src,msg", [
    ("plans/explainers.md", "neither may be cited"),
    ("CLAUDE.md", "neither may be cited"),
    ("REQ-DOCS-999", "not in requirements.yaml"),
    ("contract/missing.yaml", "not a file in the repository"),
])
def test_a_page_cannot_cite_plans_claude_or_what_does_not_exist(repo, src, msg):
    write(repo, GOOD.replace("  - contract/data-asset.yaml\n", f"  - contract/data-asset.yaml\n  - {src}\n")
                    .replace("- [contract/data-asset.yaml](../../../contract/data-asset.yaml)",
                             f"- [contract/data-asset.yaml](../../../contract/data-asset.yaml)\n- {src}"))
    assert any(msg in f.message for f in v.Validator(repo).run() if f.rule == "sources")


def test_front_matter_and_the_closing_list_must_agree(repo):
    write(repo, GOOD.replace("- [contract/data-asset.yaml](../../../contract/data-asset.yaml)\n", ""))
    msgs = [f.message for f in v.Validator(repo).run() if f.rule == "sources"]
    assert msgs and "add contract/data-asset.yaml to the list" in msgs[0]


def write_index(repo: Path, body: dict) -> Path:
    path = repo / "docs/explainers/2-calendar/sources.yaml"
    path.write_text(yaml.safe_dump(body, sort_keys=False))
    return path


def test_a_good_source_index_passes(repo):
    write_index(repo, {"group": "2-calendar", "sources": [
        {"source": "REQ-DOCS-900", "context": "What a slot is."},
        {"source": "contract/data-asset.yaml", "context": "The calendars."}]})
    assert v.Validator(repo).run() == []


def test_a_source_index_is_strict(repo):
    write_index(repo, {"group": "2-calendar", "sources": [{"source": "REQ-DOCS-900"}]})
    assert any(f.rule == "sources-schema" for f in v.Validator(repo).run())


@pytest.mark.parametrize("src", ["plans/supply-model.md", "CLAUDE.md", "REQ-DOCS-999", "nope.yaml"])
def test_a_source_index_cannot_list_what_may_not_be_cited(repo, src):
    write_index(repo, {"group": "2-calendar", "sources": [{"source": src, "context": "x"}]})
    assert any(f.rule == "sources" for f in v.Validator(repo).run())


def test_a_source_index_names_its_own_group(repo):
    write_index(repo, {"group": "3-arrives", "sources": []})
    assert any("set group to '2-calendar'" in f.message for f in v.Validator(repo).run())


def test_the_working_folder_is_not_recall_checked(repo):
    with_glossary(repo)
    work = repo / "docs/explainers/_work/run"
    work.mkdir(parents=True)
    (work / "brief.md").write_text(GOOD.replace("Sam wonders where it will land.", "A **promotion**."))
    assert recall(repo) == []
