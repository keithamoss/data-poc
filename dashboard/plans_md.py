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
from datetime import date
from urllib.parse import unquote_to_bytes

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
        after_blank = False
        i += 1
        while i < n and not _ITEM_RE.match(lines[i]) and not _HEADING_RE.match(lines[i]):
            stripped = lines[i].strip()
            if not stripped:
                if cur_words:
                    blocks.append(join_wrapped(cur_words))
                    cur_words = []
                after_blank = True
                i += 1
                continue
            if _LIST_MARKER_RE.match(stripped):
                if cur_words:
                    blocks.append(join_wrapped(cur_words))
                    cur_words = []
                blocks.append(stripped)
            # A wrapped bullet's continuation - but never across a blank
            # line, where it is a new paragraph after the list
            # (post-build-review #185).
            elif blocks and _LIST_MARKER_RE.match(blocks[-1]) and not cur_words and not after_blank:
                blocks[-1] = join_wrapped([blocks[-1], stripped])
            else:
                cur_words.extend(stripped.split())
            after_blank = False
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


# ---------------------------------------------------------------------------
# FEEDBACK CARDS (REQ-DOCS-219). Every numbered entry of plans/road-testing.md
# carries a short labelled bullet list directly after its opening paragraph:
# what was raised, what we heard, what we built, where to see it. This one
# parser serves both the gate (`mothman dashboard validate-feedback`) and the
# dashboard build (REQ-DASH-220's Feedback tab), so the two can never
# disagree about what a card is.
#
# Unlike the rest of this module it FAILS LOUDLY (NFR 3): skipping what does
# not match is right for historical prose and wrong here, where a silently
# dropped card is a piece of feedback nobody sees answered. The relative-
# address check on Evidence links lives here rather than only in the gate
# (criterion 22), so a card cannot put an absolute or javascript: href on
# the public page even if the gate were skipped.
# ---------------------------------------------------------------------------
FEEDBACK_FILE = "road-testing.md"
CARD_FIRST_LABELS = ("You told us", "We noticed")
CARD_LABELS = ("You told us", "We noticed", "What we heard", "What we built", "Evidence", "Card status")
CARD_STATUSES = ("fixed", "parked", "wont-do", "not-reproduced")
_CARD_LINE_RE = re.compile(r"^- \*\*(%s):\*\*\s*(.*)$" % "|".join(re.escape(x) for x in CARD_LABELS))
_CARD_ANY_LABEL_RE = re.compile(r"^- \*\*([^*:]+):\*\*")
_EVIDENCE_LINK_RE = re.compile(r"^\[([^\]]+)\]\(([^)\s]+)\)$")
_REQ_ID_RE = re.compile(r"^REQ-[A-Z]+-\d{3}$")
_SPRINT_ITEM_RE = re.compile(r"^sprint (\d+)$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _evidence_item(raw: str) -> tuple[dict | None, str | None]:
    """One Evidence item, or the reason it is refused (criteria 7, 8, 21)."""
    item = raw.strip()
    if _REQ_ID_RE.match(item):
        return {"kind": "req", "id": item}, None
    m = _SPRINT_ITEM_RE.match(item)
    if m:
        return {"kind": "sprint", "n": int(m.group(1))}, None
    m = _EVIDENCE_LINK_RE.match(item)
    if not m:
        return None, (f"evidence item {item!r} is not a requirement id (REQ-XXX-NNN), "
                      "'sprint <n>', or a [label](link)")
    label, target = m.group(1), m.group(2)
    if not (target.startswith("?") or target.startswith("#/")):
        return None, (f"evidence link {item!r} must be a relative dashboard address "
                      "beginning '?' or '#/'")
    query = target.split("#", 1)[0].lstrip("?")
    pairs = [p.split("=", 1) if "=" in p else (p, "") for p in query.split("&") if p]
    keys = [k.lower() for k, _ in pairs]
    if "req" in keys:
        return None, (f"evidence link {item!r} names a requirement through req= - "
                      f"write the bare id {dict((k.lower(), v) for k, v in pairs)['req']!r} instead")
    # ONLY in-place-on, ONCE, A REAL DATE (post-build-review #187): the page
    # follows a link by its route and its date and nothing else, so any other
    # parameter would act on a new tab but not on a plain click; and a
    # repeated one is read first-wins by a browser and last-wins here.
    if any(k != "in-place-on" for k in keys):
        return None, f"evidence link {item!r} may carry only in-place-on= in its query"
    if len(keys) > 1:
        return None, f"evidence link {item!r} carries in-place-on= more than once"
    params = dict(pairs)
    if "in-place-on" in params:
        when = params["in-place-on"]
        if not _DATE_RE.match(when):
            return None, f"evidence link {item!r} has in-place-on={when!r}, not a YYYY-MM-DD date"
        try:
            date.fromisoformat(when)
        except ValueError:
            return None, f"evidence link {item!r} has in-place-on={when!r}, not a real date"
    path = target.split("#", 1)[1] if "#" in target else ""
    try:
        unquote_to_bytes(path).decode("utf-8")
        if re.search(r"%(?![0-9A-Fa-f]{2})", path):
            raise ValueError
    except ValueError:
        return None, f"evidence link {item!r} has malformed %-encoding in its route"
    return {"kind": "link", "label": label, "href": target, "path": path,
            "inPlaceOn": params.get("in-place-on")}, None


def parse_feedback_cards(path: str | Path) -> tuple[list[dict], list[str]]:
    """Every entry's card in plans/road-testing.md, and every structural error
    found (criteria 1-7, 11-13, 21, 22). Cross-checks against requirements.yaml,
    the sprint list and the hierarchy are the validator's."""
    path = Path(path)
    if not path.is_file():
        return [], [f"{path} is missing"]
    entries = _parse_numbered_items(path.read_text(), path.stem)
    if not entries:
        return [], [f"{path} holds no numbered entry"]
    cards: list[dict] = []
    errors: list[str] = []
    for e in entries:
        where = f"entry #{e['number']}"
        chunks = e["text"].split("\n\n")
        title = chunks[0] if chunks else ""
        lines = chunks[1].split("\n") if len(chunks) > 1 else []
        if not lines or not _CARD_ANY_LABEL_RE.match(lines[0]):
            errors.append(f"{where} has no feedback card directly after its opening paragraph")
            continue
        fields: dict[str, str] = {}
        order: list[str] = []
        bad = False
        for ln in lines:
            m = _CARD_LINE_RE.match(ln)
            if not m:
                errors.append(f"{where}: {ln[:60]!r} is not a card line")
                bad = True
                continue
            label, value = m.group(1), m.group(2).strip()
            if label in fields:
                errors.append(f"{where}: label {label!r} appears twice")
                bad = True
                continue
            fields[label] = value
            order.append(label)
        firsts = [x for x in order if x in CARD_FIRST_LABELS]
        if len(firsts) != 1 or order[0] not in CARD_FIRST_LABELS:
            errors.append(f"{where}: a card begins with exactly one of 'You told us' or 'We noticed'")
            bad = True
        if "What we heard" not in fields:
            errors.append(f"{where}: label 'What we heard' is missing")
            bad = True
        rank = {"You told us": 0, "We noticed": 0, "What we heard": 1, "What we built": 2,
                "Evidence": 3, "Card status": 4}
        for a, b in zip(order, order[1:]):
            if rank[b] < rank[a]:
                errors.append(f"{where}: label {b!r} is out of order")
                bad = True
        status = fields.get("Card status")
        if status is not None and status not in CARD_STATUSES:
            errors.append(f"{where}: Card status {status!r} is not one of {', '.join(CARD_STATUSES)}")
            bad = True
        evidence: list[dict] = []
        for raw in (fields.get("Evidence") or "").split(";"):
            if not raw.strip():
                continue
            item, why = _evidence_item(raw)
            if why:
                errors.append(f"{where}: {why}")
                bad = True
            else:
                evidence.append(item)
        if "What we built" in fields and not evidence and status not in ("parked", "wont-do", "not-reproduced"):
            errors.append(f"{where}: a card saying what we built needs Evidence to point at")
            bad = True
        if status == "fixed" and any(i["kind"] == "req" for i in evidence):
            errors.append(f"{where}: Card status 'fixed' is for a fix with no requirement - "
                          "a card citing a requirement takes its status from it")
            bad = True
        if status in ("parked", "wont-do", "not-reproduced") and "What we built" not in fields:
            errors.append(f"{where}: a {status} card says why in its 'What we built' line")
            bad = True
        if bad:
            continue
        first = firsts[0]
        cards.append({
            "number": e["number"], "status": e["status"], "date": e["date"], "title": title,
            "firstLabel": first, "first": fields[first], "heard": fields["What we heard"],
            "built": fields.get("What we built"), "evidence": evidence, "cardStatus": status,
        })
    return cards, errors


_SPRINT_LINE_RE = re.compile(r"^- \*\*Sprint (\d+) - (.+?)\s*\(")


def road_testing_sprints(text: str) -> dict[int, str]:
    """The proposed sprints listed in plans/road-testing.md's introduction,
    number -> title (REQ-DOCS-219 criterion 20)."""
    out: dict[int, str] = {}
    for line in text.splitlines():
        m = _SPRINT_LINE_RE.match(line)
        if m:
            out[int(m.group(1))] = m.group(2).strip().strip('"')
    return out


# What a card's derived status is called on the page (REQ-DASH-220 criterion 6).
_OVERRIDE_LABEL = {"fixed": "Fixed", "parked": "Parked", "wont-do": "Won't do",
                   "not-reproduced": "Couldn't reproduce"}
_REQ_STATUS_WORDS = {"built": "built", "in_progress": "in progress", "not_started": "not started",
                     "retired": "retired"}


def card_status(card: dict, reqs: dict) -> str:
    """A card's status, derived from the requirements its evidence names, or
    its own Card status override (REQ-DASH-220 criterion 6). 'Built' is
    sprint_state's own predicate for a met requirement: built, with nothing
    in unmet_criteria (NFR 8)."""
    if card.get("cardStatus"):
        return _OVERRIDE_LABEL[card["cardStatus"]]
    cited = [reqs[i["id"]] for i in card["evidence"] if i["kind"] == "req" and i["id"] in reqs]
    if cited:
        from qa_tools.common.sprint_state import requirement_met
        if all(requirement_met(r) for r in cited):
            return "Built"
        if all(r.get("status") == "not_started" for r in cited):
            return "Planned"
        return "In progress"
    if any(i["kind"] == "sprint" for i in card["evidence"]):
        return "Planned"
    return "Heard"


def feedback_data(plans_dir: str | Path, requirements_path: str | Path) -> dict:
    """The Feedback tab's embedded data (REQ-DASH-220 criterion 2), from the
    same parser the gate uses. REFUSES TO BUILD on any card error
    (criterion 21): a card the gate would reject never reaches the public
    page, whether or not the gate ran."""
    import yaml

    path = Path(plans_dir) / FEEDBACK_FILE
    cards, errors = parse_feedback_cards(path)
    if errors:
        raise ValueError("plans/road-testing.md has feedback card errors - run "
                         "`mothman dashboard validate-feedback`:\n  " + "\n  ".join(errors))
    reqs = {r["id"]: r for r in (yaml.safe_load(Path(requirements_path).read_text()) or {}).get("requirements", [])}
    sprints = road_testing_sprints(path.read_text())
    unknown = sorted({i["id"] for c in cards for i in c["evidence"]
                      if i["kind"] == "req" and i["id"] not in reqs})
    if unknown:
        # A card citing a requirement the register lacks would derive the
        # wrong status in silence (post-build-review #187).
        raise ValueError(f"feedback cards cite requirements not in requirements.yaml: {', '.join(unknown)}")
    out = []
    for c in cards:
        evidence = []
        for i in c["evidence"]:
            if i["kind"] == "req":
                r = reqs.get(i["id"], {})
                evidence.append({"kind": "req", "id": i["id"], "title": r.get("title", ""),
                                 "status": _REQ_STATUS_WORDS.get(r.get("status"), r.get("status", ""))})
            elif i["kind"] == "sprint":
                evidence.append({"kind": "sprint", "n": i["n"], "title": sprints.get(i["n"], "")})
            else:
                evidence.append({"kind": "link", "label": i["label"], "href": i["href"],
                                 "inPlaceOn": i["inPlaceOn"]})
        out.append({"firstLabel": c["firstLabel"], "first": c["first"], "heard": c["heard"],
                    "built": c["built"], "date": c["date"], "number": c["number"],
                    "status": card_status(c, reqs), "evidence": evidence})
    return {"cards": out}
