"""The one parser for the explainers' committed configuration
(REQ-DOCS-119, REQ-DOCS-122 criterion 2).

The glossary, and later the concept map and each group's source index,
are read ONLY through this module - by the validator, by `mothman docs
glossary`, by the recall check and, in slice 2, by the dashboard embed.
A second parser anywhere is how two readers come to disagree about the
same file.

THE GLOSSARY'S SOURCE IS glossary.yaml. glossary.md is generated from it
and from requirements.yaml, committed so a person can read it on GitHub,
and held current by `mothman docs glossary --check`. It is the
CHANGELOG.yaml precedent (REQ-DOCS-028): six structured fields per term
were too many for a markdown line, and the build-state badge has to be
DERIVED from requirements.yaml rather than typed, which only a generator
can guarantee.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPLAINERS = Path("docs/explainers")
GLOSSARY_YAML = EXPLAINERS / "glossary.yaml"
GLOSSARY_MD = EXPLAINERS / "glossary.md"
CONCEPT_MAP = EXPLAINERS / "concept-map.yaml"

_Loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


class _Strict(BaseModel):
    # Unknown AND missing keys both fail (REQ-DOCS-119 criterion 1): a
    # misspelled key silently ignored is a lost definition.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class GlossaryEntry(_Strict):
    term: str
    definition: str
    # Optional, and held APART from the definition so a reader can tell
    # what the term means from an illustration of it, and so each can be
    # styled on its own (Keith, 2026-10-02).
    example: str | None = None
    aliases: list[str]
    forms: list[str]
    defined_by: list[str]
    page: str | None
    draft: bool
    idea: bool
    # Which section of glossary.md the entry is listed under - one of
    # the keys in Glossary.categories (Keith, 2026-10-02).
    category: str
    # Optional: the entry this one sits inside, such as the supply
    # calendar inside the delivery agreement (criterion 12).
    part_of: str | None = None

    @field_validator("example")
    @classmethod
    def _example_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v:
            raise ValueError("must not be blank - leave the key out instead")
        return v

    @field_validator("term", "definition")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v:
            raise ValueError("must not be blank")
        return v


class Category(_Strict):
    """One section of glossary.md. The ORDER of Glossary.categories is
    the order the sections render in, which is how the supply calendar's
    terms sit at the back (Keith, 2026-10-02) - a reader meets the data
    and what happens to it before the scheduling machinery."""

    key: str
    title: str


class Glossary(_Strict):
    categories: list[Category]
    entries: list[GlossaryEntry]
    diagram: str


def load_glossary(repo: Path = REPO_ROOT) -> Glossary:
    raw = yaml.load((repo / GLOSSARY_YAML).read_text(), Loader=_Loader)
    return Glossary.model_validate(raw)


def glossary_problems(glossary: Glossary, known_requirements: set[str]) -> list[str]:
    """Rules the schema alone cannot state (criteria 3 and 8)."""
    problems: list[str] = []
    keys = [c.key for c in glossary.categories]
    for key in sorted({k for k in keys if keys.count(k) > 1}):
        problems.append(f"category '{key}' is listed more than once")
    used = {e.category for e in glossary.entries}
    for key in keys:
        if key not in used:
            problems.append(f"category '{key}' has no entries - remove it or file an entry under it")
    seen: dict[str, str] = {}
    terms = {e.term.lower() for e in glossary.entries}
    for e in glossary.entries:
        for word in [e.term, *e.aliases]:
            key = word.lower()
            if key in seen and seen[key] != e.term:
                problems.append(f"'{word}' belongs to both '{seen[key]}' and '{e.term}'")
            seen[key] = e.term
        for alias in e.aliases:
            if alias.lower() in terms and alias.lower() != e.term.lower():
                problems.append(f"'{alias}' is an alias of '{e.term}' and also an entry of its own - "
                                "an alias never has its own definition")
        if e.idea and e.defined_by:
            problems.append(f"'{e.term}' is marked as an idea but names a defining requirement")
        if not e.idea and not e.defined_by:
            problems.append(f"'{e.term}' names no defining requirement - mark it as an idea or cite one")
        for rid in e.defined_by:
            if rid not in known_requirements:
                problems.append(f"'{e.term}' cites {rid}, which is not in requirements.yaml")
        if e.category not in keys:
            problems.append(f"'{e.term}' is filed under category '{e.category}', which is not "
                            "in the categories list")
        if e.part_of and e.part_of.lower() not in terms:
            problems.append(f"'{e.term}' is part of '{e.part_of}', which is not an entry")
    return problems


# ----------------------------------------------------------- concept map
#
# REQ-DOCS-120. The agreed groups, reading order and page list, so the
# tiering decisions made one by one with Keith survive the plans file
# that recorded them being deleted. Configuration for the next /explain
# run rather than anything a reader sees.

#: The four parts every group page carries (criterion 5), in order.
GROUP_PAGE_PARTS = ("story", "overview_diagram", "concept_cards", "read_first")

#: Where an excluded concept went (criterion 4).
EXCLUDED_TO = ("pipeline-docs", "parked", "not-explained")


class MapPage(_Strict):
    slug: str
    title: str
    # The concepts this page carries as sections, beyond its own.
    sections: list[str]


class MapGroup(_Strict):
    number: int
    slug: str
    title: str
    read_first: list[int]
    pages: list[MapPage]


class Excluded(_Strict):
    concept: str
    went: str
    why: str


class ConceptMap(_Strict):
    group_page_parts: list[str]
    groups: list[MapGroup]
    glossary_only: list[str]
    excluded: list[Excluded]


def load_concept_map(repo: Path = REPO_ROOT) -> ConceptMap:
    raw = yaml.load((repo / CONCEPT_MAP).read_text(), Loader=_Loader)
    return ConceptMap.model_validate(raw)


def concept_map_problems(cmap: ConceptMap) -> list[str]:
    """Criterion 6's rules beyond the schema: no repeated group number
    or page, and no concept in more than one place. A concept's PLACE
    is a page (its title), a section of a page, the glossary-only list,
    or the excluded list - so one concept answered twice is a tiering
    decision recorded twice, and the two copies can disagree."""
    problems: list[str] = []
    if tuple(cmap.group_page_parts) != GROUP_PAGE_PARTS:
        problems.append("group_page_parts must be exactly " + ", ".join(GROUP_PAGE_PARTS) + ", in that order")
    numbers = [g.number for g in cmap.groups]
    for n in sorted({n for n in numbers if numbers.count(n) > 1}):
        problems.append(f"group {n} is listed more than once")
    if numbers != sorted(numbers):
        problems.append("groups must be listed in their numbered reading order")
    if numbers and (numbers[0] != 0 or numbers != list(range(len(numbers)))):
        problems.append("groups must be numbered 0, 1, 2 and so on, with no gaps")
    for g in cmap.groups:
        for r in g.read_first:
            if r not in numbers:
                problems.append(f"group {g.number} reads group {r} first, which does not exist")
            elif r >= g.number:
                problems.append(f"group {g.number} reads group {r} first, which comes after it")
    places: dict[str, str] = {}

    def place(concept: str, where: str) -> None:
        key = " ".join(concept.lower().split())
        if key in places:
            problems.append(f"'{concept}' is in two places: {places[key]} and {where}")
        else:
            places[key] = where

    slugs: dict[str, int] = {}
    for g in cmap.groups:
        for pg in g.pages:
            if pg.slug in slugs:
                problems.append(f"page '{pg.slug}' is listed in group {slugs[pg.slug]} and group {g.number}")
            slugs[pg.slug] = g.number
            place(pg.title, f"the page '{pg.slug}'")
            for s in pg.sections:
                place(s, f"a section of '{pg.slug}'")
    for c in cmap.glossary_only:
        place(c, "the glossary-only list")
    for x in cmap.excluded:
        place(x.concept, "the excluded list")
        if x.went not in EXCLUDED_TO:
            problems.append(f"'{x.concept}' went to '{x.went}' - say one of " + ", ".join(EXCLUDED_TO))
    return problems


# --------------------------------------------------------- source index
#
# REQ-DOCS-121. One per group, at docs/explainers/<group>/sources.yaml:
# every requirement and config or code file relevant to the group, each
# with one line of context, reviewed once by Keith before the group's
# first brief. It closes the gap the fact-checker leaves - faithfulness
# to CITED sources says nothing about a source nobody cited.

SOURCE_INDEX = "sources.yaml"
REQ_ID = re.compile(r"REQ-[A-Z]+-\d+")


class SourceEntry(_Strict):
    source: str
    context: str


class SourceIndex(_Strict):
    group: str
    sources: list[SourceEntry]


def load_source_index(path: Path) -> SourceIndex:
    return SourceIndex.model_validate(yaml.load(path.read_text(), Loader=_Loader))


def source_problem(source: str, repo: Path, known_requirements: set[str]) -> str | None:
    """Why a cited source may not be cited, or None (criteria 9 and 10).
    Shared by the source index and a page's own sources, so the two can
    never disagree about what counts as citable."""
    s = source.strip()
    if s == "CLAUDE.md" or s.startswith("plans/"):
        return f"'{s}' is under plans/ or is CLAUDE.md, and neither may be cited"
    if REQ_ID.fullmatch(s):
        return None if s in known_requirements else f"'{s}' is not in requirements.yaml"
    if not (repo / s).is_file():
        return f"'{s}' is not a file in the repository"
    return None


# ----------------------------------------------------------- term matching
#
# The recall check (REQ-DOCS-121 criteria 5 to 8): a page that DEFINES a
# glossary term - its bold first use - must cite that term's defining
# requirements. Matching is deliberately plain: the term, its aliases,
# its listed forms, and the regular inflections of each, case-
# insensitively at word boundaries. An irregular form goes in the
# entry's forms rather than being guessed at here.


def _inflections(word: str) -> list[str]:
    out = [word, word + "s", word + "es", word + "d", word + "ed", word + "ing"]
    if word.endswith("e"):
        out += [word[:-1] + "ing", word[:-1] + "ed"]
    return out


def term_pattern(entry: GlossaryEntry) -> re.Pattern:
    """Every way a page may write this entry's term."""
    words: set[str] = set()
    for phrase in [entry.term, *entry.aliases]:
        head, _, last = phrase.lower().rpartition(" ")
        words.update(f"{head} {w}".strip() for w in _inflections(last))
    words.update(f.lower() for f in entry.forms)
    alts = sorted(words, key=len, reverse=True)
    return re.compile(r"(?<![\w-])(?:" + "|".join(re.escape(w) for w in alts) + r")(?![\w-])", re.I)


# ------------------------------------------------------------- rendering


def render_glossary_md(glossary: Glossary, req_states: dict[str, str]) -> str:
    """glossary.md, derived and never hand-edited. Badges come from
    requirements.yaml through the same derivation the validator uses."""
    lines = [
        "# Glossary",
        "",
        "This page is generated from glossary.yaml by `mothman docs glossary`. "
        "Edit that file, never this one.",
        "",
        glossary.diagram.rstrip(),
        "",
    ]
    by_category = {c.key: [] for c in glossary.categories}
    for e in glossary.entries:
        by_category.setdefault(e.category, []).append(e)
    for c in glossary.categories:
        if not by_category[c.key]:
            continue
        lines += [f"## {c.title}", ""]
        lines += _render_entries(by_category[c.key], req_states)
    return "\n".join(lines).rstrip() + "\n"


def _render_entries(entries: list[GlossaryEntry], req_states: dict[str, str]) -> list[str]:
    from qa_tools.common.validate_explainers import MARKER_TEXT, least_built

    lines: list[str] = []
    for e in sorted(entries, key=lambda x: x.term.lower()):
        lines += [f"### {e.term[:1].upper()}{e.term[1:]}", ""]
        state = ("an idea, not designed yet" if e.idea
                 else least_built(req_states.get(r, "proposed") for r in e.defined_by))
        if state != "built":
            lines += [MARKER_TEXT[state], ""]
        if e.draft:
            lines += ["Draft: this name is a placeholder and may change.", ""]
        lines += [e.definition, ""]
        if e.example:
            lines += [f"**Example:** {e.example}", ""]
        if e.part_of:
            lines += [f"Part of: {e.part_of}.", ""]
        if e.aliases:
            lines += ["Also called: " + ", ".join(e.aliases) + ".", ""]
        if e.page:
            lines += [f"Explained in: [{e.page}]({e.page}).", ""]
        else:
            lines += ["Not explained on a page of its own yet.", ""]
    return lines


def expected_glossary_md(repo: Path = REPO_ROOT) -> str:
    from qa_tools.common.validate_explainers import load_requirement_states

    return render_glossary_md(load_glossary(repo), load_requirement_states(repo))


def write_glossary_md(repo: Path = REPO_ROOT) -> Path:
    out = repo / GLOSSARY_MD
    out.write_text(expected_glossary_md(repo))
    return out


def glossary_is_current(repo: Path = REPO_ROOT) -> bool:
    md = repo / GLOSSARY_MD
    return md.exists() and md.read_text() == expected_glossary_md(repo)


__all__ = [
    "Category", "ConceptMap", "Glossary", "GlossaryEntry", "load_concept_map", "concept_map_problems",
    "SourceIndex", "load_source_index", "source_problem", "term_pattern", "ValidationError", "load_glossary", "glossary_problems",
    "render_glossary_md", "write_glossary_md", "glossary_is_current",
]
