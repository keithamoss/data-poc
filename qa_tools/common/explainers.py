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

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPLAINERS = Path("docs/explainers")
GLOSSARY_YAML = EXPLAINERS / "glossary.yaml"
GLOSSARY_MD = EXPLAINERS / "glossary.md"

_Loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


class _Strict(BaseModel):
    # Unknown AND missing keys both fail (REQ-DOCS-119 criterion 1): a
    # misspelled key silently ignored is a lost definition.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class GlossaryEntry(_Strict):
    term: str
    definition: str
    aliases: list[str]
    forms: list[str]
    defined_by: list[str]
    page: str | None
    draft: bool
    idea: bool
    # Optional: the entry this one sits inside, such as the supply
    # calendar inside the delivery agreement (criterion 12).
    part_of: str | None = None

    @field_validator("term", "definition")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v:
            raise ValueError("must not be blank")
        return v


class Glossary(_Strict):
    entries: list[GlossaryEntry]
    diagram: str


def load_glossary(repo: Path = REPO_ROOT) -> Glossary:
    raw = yaml.load((repo / GLOSSARY_YAML).read_text(), Loader=_Loader)
    return Glossary.model_validate(raw)


def glossary_problems(glossary: Glossary, known_requirements: set[str]) -> list[str]:
    """Rules the schema alone cannot state (criteria 3 and 8)."""
    problems: list[str] = []
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
        if e.part_of and e.part_of.lower() not in terms:
            problems.append(f"'{e.term}' is part of '{e.part_of}', which is not an entry")
    return problems


# ------------------------------------------------------------- rendering


def render_glossary_md(glossary: Glossary, req_states: dict[str, str]) -> str:
    """glossary.md, derived and never hand-edited. Badges come from
    requirements.yaml through the same derivation the validator uses."""
    from qa_tools.common.validate_explainers import MARKER_TEXT, least_built

    lines = [
        "# Glossary",
        "",
        "This page is generated from glossary.yaml by `mothman docs glossary`. "
        "Edit that file, never this one.",
        "",
        glossary.diagram.rstrip(),
        "",
    ]
    for e in sorted(glossary.entries, key=lambda x: x.term.lower()):
        lines += [f"## {e.term[:1].upper()}{e.term[1:]}", ""]
        state = ("an idea, not designed yet" if e.idea
                 else least_built(req_states.get(r, "proposed") for r in e.defined_by))
        if state != "built":
            lines += [MARKER_TEXT[state], ""]
        if e.draft:
            lines += ["Draft: this name is a placeholder and may change.", ""]
        lines += [e.definition, ""]
        if e.part_of:
            lines += [f"Part of: {e.part_of}.", ""]
        if e.aliases:
            lines += ["Also called: " + ", ".join(e.aliases) + ".", ""]
        if e.page:
            lines += [f"Explained in: [{e.page}]({e.page}).", ""]
        else:
            lines += ["Not explained on a page of its own yet.", ""]
    return "\n".join(lines).rstrip() + "\n"


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
    "Glossary", "GlossaryEntry", "ValidationError", "load_glossary", "glossary_problems",
    "render_glossary_md", "write_glossary_md", "glossary_is_current",
]
