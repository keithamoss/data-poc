"""
Parses `plans/*.md` - the project's own persistent planning memory
(CLAUDE.md's own orientation section) - into structured data the
dashboard's "Plans" tab (running-thoughts.md #10) can render, filter, and
search, mirroring dashboard/changelog_md.py's narrow line-based style
rather than pulling in a real markdown library.

There are two real, deliberately different tag placements in these files
(a genuine finding from the 2026-09-18 scoping, not assumed - see
plans/running-thoughts.md #10's own write-up):

1. Numbered-item files (`wider.md`, `qa-pipeline.md`, `dashboard.md`,
   `data-generation.md`, `tooling.md`) - a plain markdown ordered list,
   each item tagged at its own first token:
       N. **[status, date]** **[Component]** <text, wrapped across
          multiple lines/paragraphs, indented like a real markdown list
          continuation>
   An item can carry more than one `**[Component]**` tag. `qa-pipeline.md`
   also has one section this parser deliberately does NOT retrofit-match:
   "## Held over from the original (equivalent-only) build" restarts its
   own, unrelated numbering in the OLD (untagged) format - items there
   simply don't match `_ITEM_RE` and are silently skipped, exactly like
   any other historical content this parser doesn't recognise. No special
   casing needed for that section by name.

2. Thread/Phase essay files (`publishing-and-history.md`,
   `conceptual-design.md`) - long-form prose under `## Thread X`/`##
   Phase N` headings, each carrying one tag line directly under its own
   heading:
       ## Thread X - title
       **Status:** status (date) · **Category:** Component

       <body prose, possibly many paragraphs/sub-headers/bullet lists>
   Not every `##` heading in these files is a tagged Thread/Phase (e.g.
   publishing-and-history.md's own "## Doc updates needed once this
   starts landing" isn't) - a heading with no `**Status:** ... ·
   **Category:** ...` line immediately under it is simply not captured
   as a thread, same "skip what doesn't match" philosophy as above.

`running-thoughts.md` is deliberately NOT part of either tagged scheme
(Keith's own call, recorded in plans/running-thoughts.md #10 fork 2: "no
forced status field... just a looser feed the dashboard shows as-is") -
`parse_notes()` only extracts each `### N. Title` item's number, title,
and body, with no status/component parsing at all.

Every parsed body/text field keeps real markdown (bold, inline code, `-`/
`*` bullet lists, blank-line paragraph breaks) as a plain string - unlike
changelog_md.py's single-line items, these can be long multi-paragraph
essays, so the dashboard's own JS does a slightly richer (but still not
full-CommonMark) markdown-to-HTML pass at render time, not this module.
"""
from __future__ import annotations
import re

from dashboard.markdown_text import join_wrapped
from pathlib import Path

_ITEM_RE = re.compile(
    r"^(\d+)\.\s+\*\*\[([a-z-]+),\s*(\d{4}-\d{2}-\d{2})\]\*\*((?:\s*\*\*\[[^\]]+\]\*\*)+)\s*(.*)$"
)
_COMPONENT_RE = re.compile(r"\*\*\[([^\]]+)\]\*\*")
_HEADING_RE = re.compile(r"^#{2,3}\s+(.*)$")
_THREAD_HEADING_RE = re.compile(r"^##\s+(.+)$")
_THREAD_STATUS_RE = re.compile(
    r"^\*\*Status:\*\*\s*([a-z-]+)\s*\((\d{4}-\d{2}-\d{2})\)\s*·\s*\*\*Category:\*\*\s*(.+)$"
)
_NOTE_HEADING_RE = re.compile(r"^###\s+(?:(\d+)\.\s+)?(.+)$")
# A list-item marker within an item's own body - either a "- "/"* " bullet
# or a "1. "/"2. " ordered marker (real bug, found via Keith's own
# dashboard report 2026-09-19: only bullets were recognised, so a numbered
# sub-list like plans/tooling.md #1's own "Build order" phase list got
# silently word-joined into one illegible paragraph).
_LIST_MARKER_RE = re.compile(r"^(?:[-*]\s+|\d+\.\s+)")

# The 5 numbered-item files and the 2 Thread/Phase essay files, keyed by
# the short "file" id the dashboard's URL/filter state uses - deliberately
# not just the filename stem, so a rename of the .md file itself doesn't
# silently change every embedded id.
# Every plans file that carries numbered items. publishing-and-history
# and performance were MISSING here until 2026-09-20 - both were
# classified as essay/thread files when this was written and both had
# since grown numbered items (8 and 5), so 13 items were invisible to
# the dashboard's Plans tab, including publishing-and-history #6, the
# HIGH-priority per-dataset architecture work. A file appearing here AND
# in THREAD_FILES is fine and intended - parse_plans() walks the two
# independently, and publishing-and-history genuinely has both shapes.
# tests/test_plans_md.py asserts generically that no numbered item in
# any plans/*.md goes unparsed, rather than checking this list, so the
# next file to grow items cannot be forgotten the same way.
NUMBERED_FILES = {
    "wider": "wider.md",
    "qa-pipeline": "qa-pipeline.md",
    "publishing-and-history": "publishing-and-history.md",
    "dashboard": "dashboard.md",
    "data-generation": "data-generation.md",
    "tooling": "tooling.md",
    "performance": "performance.md",
}
THREAD_FILES = {
    "publishing-and-history": "publishing-and-history.md",
    "conceptual-design": "conceptual-design.md",
}
NOTES_FILE = "running-thoughts.md"


def _join_blocks(blocks: list[str]) -> str:
    """Joins block strings (plain paragraphs or `- `/`* `/`N. ` list-item
    lines) back into one markdown string - consecutive list items stay on
    their own single-newline-separated lines (one real list), everything
    else gets a blank-line paragraph break, so the renderer can tell the
    two apart without re-parsing indentation."""
    out: list[str] = []
    prev_bullet = None
    for b in blocks:
        is_bullet = bool(_LIST_MARKER_RE.match(b))
        if out:
            out.append("\n" if (is_bullet and prev_bullet) else "\n\n")
        out.append(b)
        prev_bullet = is_bullet
    return "".join(out)


def _parse_numbered_items(text: str, file_key: str) -> list[dict]:
    lines = text.splitlines()
    items: list[dict] = []
    section: str | None = None
    i, n = 0, len(lines)
    while i < n:
        h = _HEADING_RE.match(lines[i])
        if h:
            section = h.group(1).strip()
            i += 1
            continue
        m = _ITEM_RE.match(lines[i])
        if not m:
            i += 1
            continue
        number = int(m.group(1))
        status, date = m.group(2), m.group(3)
        components = _COMPONENT_RE.findall(m.group(4))
        blocks: list[str] = []
        cur_words = m.group(5).split()
        i += 1
        while i < n and not _ITEM_RE.match(lines[i]) and not _HEADING_RE.match(lines[i]):
            stripped = lines[i].strip()
            if not stripped:
                if cur_words:
                    blocks.append(join_wrapped(cur_words))
                    cur_words = []
            elif _LIST_MARKER_RE.match(stripped):
                if cur_words:
                    blocks.append(join_wrapped(cur_words))
                    cur_words = []
                blocks.append(stripped)
            elif blocks and _LIST_MARKER_RE.match(blocks[-1]) and not cur_words:
                blocks[-1] = join_wrapped([blocks[-1], stripped])
            else:
                cur_words.extend(stripped.split())
            i += 1
        if cur_words:
            blocks.append(join_wrapped(cur_words))
        items.append({
            "file": file_key, "number": number, "status": status, "date": date,
            "components": components, "section": section, "text": _join_blocks(blocks),
        })
    return items


def _parse_threads(text: str, file_key: str) -> list[dict]:
    lines = text.splitlines()
    threads: list[dict] = []
    i, n = 0, len(lines)
    while i < n:
        h = _THREAD_HEADING_RE.match(lines[i])
        if not h:
            i += 1
            continue
        heading = h.group(1).strip()
        i += 1
        j = i
        while j < n and not lines[j].strip():
            j += 1
        sm = _THREAD_STATUS_RE.match(lines[j].strip()) if j < n else None
        if not sm:
            continue  # a real heading, but not a tagged Thread/Phase - skip
        status, date, category = sm.group(1), sm.group(2), sm.group(3).strip()
        i = j + 1
        body_lines: list[str] = []
        while i < n and not _THREAD_HEADING_RE.match(lines[i]):
            body_lines.append(lines[i])
            i += 1
        body = "\n".join(body_lines).strip("\n")
        threads.append({
            "file": file_key, "heading": heading, "status": status,
            "date": date, "category": category, "body": body,
        })
    return threads


def _parse_notes(text: str) -> list[dict]:
    lines = text.splitlines()
    notes: list[dict] = []
    i, n = 0, len(lines)
    while i < n:
        h = _NOTE_HEADING_RE.match(lines[i])
        if not h:
            i += 1
            continue
        number = int(h.group(1)) if h.group(1) else None
        title = h.group(2).strip()
        i += 1
        body_lines: list[str] = []
        while i < n and not _NOTE_HEADING_RE.match(lines[i]) and not lines[i].startswith("## "):
            body_lines.append(lines[i])
            i += 1
        body = "\n".join(body_lines).strip("\n")
        notes.append({"number": number, "title": title, "body": body})
    return notes


def parse_plans(plans_dir: str | Path) -> dict:
    """Returns {"items": [...], "threads": [...], "notes": [...]} across
    every plans/*.md file - items/threads in each file's own top-to-bottom
    order, grouped by file in NUMBERED_FILES/THREAD_FILES iteration order
    (not re-sorted; the dashboard's own filters/sort are a rendering
    concern, not this module's)."""
    plans_dir = Path(plans_dir)
    items: list[dict] = []
    for key, fname in NUMBERED_FILES.items():
        items.extend(_parse_numbered_items((plans_dir / fname).read_text(), key))
    threads: list[dict] = []
    for key, fname in THREAD_FILES.items():
        threads.extend(_parse_threads((plans_dir / fname).read_text(), key))
    notes = _parse_notes((plans_dir / NOTES_FILE).read_text())
    return {"items": items, "threads": threads, "notes": notes}
