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
    - **<time>** — **<Headline>** **[Component]** <entry, possibly wrapped
      across multiple indented lines>
    - **<time>** — **<Headline>** **[Component]** **[Component]** <entry>

    ### <category>
    - **<time>** — **<Headline>** **[Component]** <entry>

    ## <date>
    ...

An item's leading `**<time>**` (e.g. `**6:12am**`, real AWST git-commit
time, same convention as the date headings above it) is optional - a
bullet with no timestamp parses fine, just with `"time": None` - so
this stays backward compatible with any entry that predates the
2026-09-18 timestamp retrofit.

An item can also lead (after the time, if present) with a bold
headline - a short, unique-per-item title, e.g. `**Leaderboard
Streaks**` - followed by zero or more `**[Component]**` tags from the
same 7-item taxonomy `plans/*.md` items use (Data generation, QA
checks & contract, Pipeline & publishing, Dashboard UI, GitHub workflow
& people, Testing & dev tooling, Docs & process). Both are optional,
same reasoning as `time` above - parse fine as `None`/`[]` on an entry
that predates the 2026-09-18 evening headline/component retrofit
(Keith's own ask: a bold label to lead each entry, iconography, and the
component(s) shown alongside, in service of a punchier, friendlier,
still-technical page). The headline is deliberately NOT drawn from a
closed vocabulary (unlike `status` in `plans/*.md` items) - it's a
one-off mini-title per entry, not a category.

Deliberately narrow: no full CommonMark support (no nested lists, no
inline links, no code fences) - this file's own style is simple by
design (see its own intro), and a narrow, predictable parser is easier
to reason about and test than pulling in a real markdown library for a
shape this constrained.
"""
from __future__ import annotations
import re

from dashboard.markdown_text import join_wrapped
from pathlib import Path

_ITEM_TIME_RE = re.compile(r"^\*\*(\d{1,2}:\d{2}(?:am|pm))\*\* — (.*)$")
# A bold span that doesn't itself start with "[" - so a **[Component]**
# tag is never mistaken for the headline that precedes it.
# `(?:[^*\\]|\\.)*` rather than a plain `[^*]*`: a headline may contain a
# backslash-escaped asterisk (a real one does - "...Renamed to
# delivery-\*"), which puts `***` immediately before the closing `**`.
# The old `[^*]*` stopped at the backslash, `\*\*` then ate two of the
# three asterisks, and the leftover `*` blocked the component match that
# follows. The two alternatives here are deliberately non-overlapping
# (a backslash only ever matches via `\\.`), so there's no ambiguity for
# the engine to backtrack through. plans/dashboard.md #17.
_ITEM_HEADLINE_RE = re.compile(r"^\*\*([^*\[](?:[^*\\]|\\.)*)\*\*\s*(.*)$")
_ITEM_COMPONENT_RE = re.compile(r"^\*\*\[([^\]]+)\]\*\*\s*")
_MD_ESCAPE_RE = re.compile(r"\\(.)")


def _parse_item(text: str) -> dict:
    match = _ITEM_TIME_RE.match(text)
    time, rest = (match.group(1), match.group(2)) if match else (None, text)

    headline = None
    hmatch = _ITEM_HEADLINE_RE.match(rest)
    if hmatch:
        headline, rest = hmatch.group(1), hmatch.group(2)
        # `\*` is markdown escaping, not content - a reader should see
        # the asterisk, not the backslash that protects it.
        headline = _MD_ESCAPE_RE.sub(r"\1", headline)

    components = []
    while True:
        cmatch = _ITEM_COMPONENT_RE.match(rest)
        if not cmatch:
            break
        components.append(cmatch.group(1))
        rest = rest[cmatch.end():]

    return {"time": time, "headline": headline, "components": components, "text": rest}


def parse_changelog(path: str | Path) -> dict:
    """Returns {"intro": [str, ...], "entries": [{"date": str, "sections":
    [{"category": str, "items": [{"time": str | None, "text": str}, ...]},
    ...]}, ...]} - entries in the file's own top-to-bottom order (Keep a
    Changelog convention: newest first, so the file's own ordering is
    never re-sorted here)."""
    intro_paragraphs: list[str] = []
    entries: list[dict] = []
    current_entry: dict | None = None
    current_section: dict | None = None
    current_para: list[str] = []
    seen_first_heading = False
    pending_item: dict | None = None

    def flush_para():
        if current_para:
            intro_paragraphs.append(join_wrapped(current_para))
            current_para.clear()

    def flush_item():
        """Parse the open bullet from its FULL source text, then close it.
        Deliberately not done line-by-line - see plans/dashboard.md #17."""
        nonlocal pending_item
        if pending_item is not None:
            pending_item["section"]["items"].append(
                _parse_item(join_wrapped(pending_item["lines"]))
            )
            pending_item = None

    with open(path) as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")
            stripped = line.strip()

            if line.startswith("# "):  # the file's own H1 title - not content
                continue
            if line.startswith("## "):
                flush_item()
                flush_para()
                current_entry = {"date": line[3:].strip(), "sections": []}
                entries.append(current_entry)
                current_section = None
                seen_first_heading = True
                continue
            if line.startswith("### ") and current_entry is not None:
                flush_item()
                current_section = {"category": line[4:].strip(), "items": []}
                current_entry["sections"].append(current_section)
                continue
            if line.startswith("- ") and current_section is not None:
                flush_item()
                pending_item = {"section": current_section, "lines": [stripped[2:]]}
                continue
            if not seen_first_heading:
                # preamble before the first "## " heading - the page's own
                # intro text, paragraphs separated by blank lines
                if stripped:
                    current_para.append(stripped)
                else:
                    flush_para()
                continue
            # a non-empty, non-heading, non-bullet line while an item is
            # still open - a soft-wrapped continuation of that item's own
            # markdown source line. Buffered rather than appended straight
            # onto ["text"]: the headline and **[Component]** tags are
            # parsed off the WHOLE joined bullet at flush time, so a tag
            # that wrapped onto this line (or split across the wrap) is
            # still seen. plans/dashboard.md #17.
            if stripped and pending_item is not None:
                pending_item["lines"].append(stripped)

    flush_item()
    flush_para()
    return {"intro": intro_paragraphs, "entries": entries}
