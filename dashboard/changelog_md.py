"""
Parses the repo's own hand-maintained CHANGELOG.md (item 62, plans/qa-
pipeline.md) - "what changed about the PoC/tool itself over time," a
genuinely different feed from qa_tools/common/changelog.py's build_
changelog() (who published QA results for which dataset, when) and a
single check's own changelog inside its detail panel (that one check's
definition-change history). Keith's own call on how this one gets
authored: a hand-maintained file, not derived from `qa_results/` or
real git commit messages - so this module's only job is turning that
file's Keep-a-Changelog-style markdown into something the dashboard can
render as a real page, not producing the content itself.

Expected shape (see CHANGELOG.md itself for the real, current file):
    # Changelog

    <intro prose, one or more paragraphs, blank-line separated>

    ## <date>

    ### <category>
    - <entry, possibly wrapped across multiple indented lines>
    - <entry>

    ### <category>
    - <entry>

    ## <date>
    ...

Deliberately narrow: no full CommonMark support (no nested lists, no
inline links, no code fences) - this file's own style is simple by
design (see its own intro), and a narrow, predictable parser is easier
to reason about and test than pulling in a real markdown library for a
shape this constrained.
"""
from __future__ import annotations
from pathlib import Path


def parse_changelog(path: str | Path) -> dict:
    """Returns {"intro": [str, ...], "entries": [{"date": str, "sections":
    [{"category": str, "items": [str, ...]}, ...]}, ...]} - entries in
    the file's own top-to-bottom order (Keep a Changelog convention:
    newest first, so the file's own ordering is never re-sorted here)."""
    intro_paragraphs: list[str] = []
    entries: list[dict] = []
    current_entry: dict | None = None
    current_section: dict | None = None
    current_para: list[str] = []
    seen_first_heading = False

    def flush_para():
        if current_para:
            intro_paragraphs.append(" ".join(current_para))
            current_para.clear()

    with open(path) as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")
            stripped = line.strip()

            if line.startswith("# "):  # the file's own H1 title - not content
                continue
            if line.startswith("## "):
                flush_para()
                current_entry = {"date": line[3:].strip(), "sections": []}
                entries.append(current_entry)
                current_section = None
                seen_first_heading = True
                continue
            if line.startswith("### ") and current_entry is not None:
                current_section = {"category": line[4:].strip(), "items": []}
                current_entry["sections"].append(current_section)
                continue
            if line.startswith("- ") and current_section is not None:
                current_section["items"].append(stripped[2:])
                continue
            if not seen_first_heading:
                # preamble before the first "## " heading - the page's own
                # intro text, paragraphs separated by blank lines
                if stripped:
                    current_para.append(stripped)
                else:
                    flush_para()
                continue
            # a non-empty, non-heading, non-bullet line while inside a
            # section with at least one item already - a soft-wrapped
            # continuation of that item's own markdown source line
            if stripped and current_section is not None and current_section["items"]:
                current_section["items"][-1] += " " + stripped

    flush_para()
    return {"intro": intro_paragraphs, "entries": entries}
