"""
Parses `plans/*.md` - the project's own persistent planning memory
(CLAUDE.md's own orientation section) - into structured data the
dashboard's "Plans" tab (running-thoughts.md #10) can render, filter, and
search, mirroring the narrow line-based style dashboard/changelog_md.py used before CHANGELOG became structured YAML
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

`running-thoughts.md` used to be a third, untagged shape - `### N. Title`
headings parsed by their own `parse_notes()`, with no status or
component at all (Keith's original call, plans/running-thoughts.md #10
fork 2: "no forced status field... just a looser feed the dashboard
shows as-is"). Reversed 2026-09-20 at his own suggestion once the
generated index made the cost visible: 10 of its 12 entries were
actually done, and showing them untagged was misleading rather than
loose. They are now ordinary numbered items, the third parser path is
gone, and the file keeps its character through its own prose and section
headings rather than through a separate record type.

Every parsed body/text field keeps real markdown (bold, inline code, `-`/
`*` bullet lists, blank-line paragraph breaks) as a plain string - unlike
a changelog item, these can be long multi-paragraph
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
# A list-item marker within an item's own body - either a "- "/"* " bullet
# or a "1. "/"2. " ordered marker (real bug, found via Keith's own
# dashboard report 2026-09-19: only bullets were recognised, so a numbered
# sub-list like plans/tooling.md #1's own "Build order" phase list got
# silently word-joined into one illegible paragraph).
_LIST_MARKER_RE = re.compile(r"^(?:[-*]\s+|\d+\.\s+)")

# Every `plans/*.md` file is walked, and its `file` id is its filename
# stem. Keith's own call, 2026-09-20: "I'm happy for it just to walk all
# of the markdown files in a given directory - that's probably safer
# because we will probably add more files as we go."
#
# This replaced two hardcoded allowlists, and the reason is a real bug
# they caused: publishing-and-history.md and performance.md had both
# grown numbered items after being classified as essay/thread files, so
# 13 items - including the HIGH-priority per-dataset architecture work -
# were invisible to the dashboard's Plans tab. Nothing looked wrong; the
# tab just under-reported. An allowlist fails silently by construction,
# which is the worst shape for a file that is meant to be this project's
# own memory.
#
# What the old indirection bought, and what dropping it costs: a `file`
# key decoupled from the filename meant renaming a .md file didn't
# change every embedded id. Now it does. Judged acceptable - a rename is
# a deliberate act that would want the dashboard's own filter chip
# renamed too, and the template already falls back to the raw key
# (`PLANS_FILE_LABEL[i.file] || i.file`), so an unlabelled file degrades
# to showing its stem rather than breaking.
#
# Each file is parsed for BOTH numbered items and threads, since
# publishing-and-history.md genuinely carries both shapes. Both have
# strong, unambiguous signals (`N. **[status, YYYY-MM-DD]**`, and a `##`
# heading followed by a `**Status:** ... · **Category:** ...` line), so
# walking every file cannot invent entries that aren't there.
# Deliberately NOT walked: the generated index lives in the same
# directory and is built FROM these files, so parsing it back in would
# be circular.
GENERATED_FILES = {"INDEX.md"}


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


def parse_plans(plans_dir: str | Path) -> dict:
    """Returns {"items": [...], "threads": [...]} across
    every `plans/*.md` file, walked from the directory rather than listed
    - a new plans file needs no code change here. Items and threads come
    back in each file's own top-to-bottom order, grouped by file in
    filename order and not re-sorted; the dashboard's own filters and
    sort are a rendering concern, not this module's."""
    plans_dir = Path(plans_dir)
    items: list[dict] = []
    threads: list[dict] = []
    for path in sorted(plans_dir.glob("*.md")):
        if path.name in GENERATED_FILES:
            continue
        text = path.read_text()
        items.extend(_parse_numbered_items(text, path.stem))
        threads.extend(_parse_threads(text, path.stem))
    return {"items": items, "threads": threads}
