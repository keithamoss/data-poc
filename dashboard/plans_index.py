"""Generates `plans/INDEX.md` - a one-line-per-entry table of contents
for this project's own planning memory (`plans/tooling.md` #17).

Why this exists. `CLAUDE.md` opens by telling every new session to read
seven `plans/*.md` files "in full before doing anything else", and that
instruction now costs roughly 159,000 tokens before any work starts. The
awkward part is that it is NOT dead weight: those completed write-ups
are precisely what stops a session re-deriving a settled decision, which
is the instruction's own stated reason for existing. Cutting them would
cause the failure it was written to prevent.

So nothing is cut. This is a derived VIEW - the plans files keep every
word, and the index points into them. What changes is the reading
instruction: read this first, read the live items in full, and open a
completed one when it turns out to matter. The saving is at read time
and it is fully reversible.

Generated rather than hand-written, deliberately. A hand-maintained
summary of 150+ entries drifts from its source the moment anyone is in a
hurry - and this project has already been bitten by exactly that (see
`dashboard/markdown_text.py` for a bug that survived a "fix" which
patched the symptom in the source text rather than the cause). Being
generated from `plans_md.py`'s own parser means the index cannot say
something the files do not, and a CI freshness check means it cannot
quietly go stale either.
"""
from __future__ import annotations
import re

from pathlib import Path

from dashboard.plans_md import parse_plans

# Files in the order CLAUDE.md's own orientation section introduces them,
# so the index reads in the sequence a session is told to read in rather
# than alphabetically. Anything parsed but not listed here still appears,
# appended afterwards, so a new plans file can never be silently dropped.
_FILE_ORDER = [
    "wider", "qa-pipeline", "publishing-and-history", "conceptual-design",
    "dashboard", "data-generation", "tooling", "performance", "running-thoughts",
]

_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s")
# A block that OPENS with a bold run is this project's own section-header
# convention inside a long thread or phase essay - "**Decision:**",
# "**Confirmed field set for the metadata, each check gets:**",
# "**Phase 3 (Thread A - CI-gated publishing) - [complete, ...]:**".
# Surfacing these is the whole point of sub-entries (see build_index).
_BOLD_LEAD_RE = re.compile(r"^\*\*(.+?)\*\*(.*)$", re.S)
_MIN_BOLD_LEAD = 8

# Real source paths named in an entry's own prose. 61% of entries already
# name at least one that resolves on disk (352 mentions across 171
# entries, measured 2026-09-20), so this costs no authoring at all - it
# just surfaces what someone already wrote down.
#
# This exists because of a ceiling two real proof runs hit independently.
# The index covers plans/ only, so it cannot answer "is this already
# built?" - and both runs found that the feature they were scoping had
# already shipped by GREPPING THE CODE, not through the index. Keith's
# own suggestion on being told that: "what if the index pointed to
# implementation in code?" Thread D's entry names the dashboard template,
# which is exactly the signal both runs needed and neither got.
_SRC_ROOTS = ("qa_tools", "pipeline", "dashboard", "generator", "cli", "contract",
              "tests", "dbt_project", "scripts", "aws", "synthetic_data_generator")
_PATH_RE = re.compile(
    r"\b((?:" + "|".join(_SRC_ROOTS) + r")/[A-Za-z0-9_./-]+\.(?:py|html|yml|yaml|sql|js|md))")
# The built dashboard is gitignored - prose naming it means the template.
_BUILD_OUTPUT = "dashboard/qa-reporting-dashboard.html"
_TEMPLATE = "dashboard/qa-reporting-dashboard.template.html"
_MAX_PATHS = 6
_MD_NOISE_RE = re.compile(r"[*`]")
_MAX_SUMMARY = 120


def _summarise(text: str) -> str:
    """One line describing an entry, taken from its own first sentence.

    Deliberately not a rewrite or a generated paraphrase - a summary that
    says something the item does not is worse than no summary, because
    the whole point is deciding whether to go and read the real thing."""
    flat = " ".join(text.split())
    first = _SENTENCE_END_RE.split(flat, 1)[0] if flat else ""
    first = _MD_NOISE_RE.sub("", first).strip()
    if len(first) > _MAX_SUMMARY:
        first = first[:_MAX_SUMMARY].rsplit(" ", 1)[0] + "..."
    return first


def _sub_entries(body: str) -> list[str]:
    """The bold section headers inside a thread or phase essay.

    These exist because a one-line summary of a multi-thousand-word design
    document is not enough to decide whether to open it - established the
    hard way. A real `delivery-scoper` run against an index without them
    (2026-09-20) reported that Thread D's single line, "check lifecycle:
    retirement + definition changes", gave no hint it was where a whole
    field design lived, and that it only found it via a cross-reference in
    an unrelated item: "Had I trusted the index line, I'd have skipped the
    single most relevant document in the repo and drafted requirements for
    something already built."

    Deliberately uncapped. A thread with 45 sections genuinely has 45
    things in it, and silently dropping some is the exact failure this is
    fixing - the index costs a few thousand tokens either way."""
    out = []
    for block in body.split("\n\n"):
        m = _BOLD_LEAD_RE.match(block.strip())
        if not m:
            continue
        lead = " ".join(m.group(1).split())
        if len(lead) < _MIN_BOLD_LEAD:
            continue
        # ALWAYS carry the text the header introduces, however long the
        # header itself is. An earlier version only did this for headers
        # under 45 characters, and a real re-proof run (2026-09-20) showed
        # that is exactly backwards: the longest headers are the ones that
        # end in a colon and announce something, so truncating at the colon
        # yields "Confirmed field set for the metadata, each check gets:" -
        # which names no fields, in the one sub-entry whose contents were
        # the entire subject of that agent's task. Its own words: "carry no
        # information about what was decided, only that something was."
        rest = " ".join(m.group(2).split())
        text = f"{lead} {rest}".strip() if rest else lead
        text = _MD_NOISE_RE.sub("", text)
        if len(text) > _MAX_SUMMARY:
            text = text[:_MAX_SUMMARY].rsplit(" ", 1)[0] + "..."
        out.append(text)
    return out


def _touches(text: str, repo_root: Path) -> list[str]:
    """Source files an entry's own prose names, that actually exist.

    Only resolvable paths are listed, which quietly does something useful:
    a superseded item citing a since-deleted module simply shows fewer
    paths rather than pointing a reader at a file that is gone. Not a
    validation gate - plans entries legitimately reference removed code
    (`engines/` is the standing example), and failing on that would be
    wrong.

    Ordered by FIRST MENTION, not alphabetically. Alphabetical put six
    `*-retired.yaml` files at the front of the longest entry and hid
    `check_lifecycle.py` behind a "+34 more" - the order an author
    introduces files in tracks how central they are far better than
    their names do."""
    found: list[str] = []
    for raw in _PATH_RE.findall(text):
        path = _TEMPLATE if raw == _BUILD_OUTPUT else raw
        if path not in found and (repo_root / path).exists():
            found.append(path)
    return found


def _file_sort_key(name: str) -> tuple[int, str]:
    return (_FILE_ORDER.index(name), "") if name in _FILE_ORDER else (len(_FILE_ORDER), name)


def build_index(plans_dir: str = "plans") -> str:
    parsed = parse_plans(plans_dir)
    root = Path(plans_dir).resolve().parent
    items, threads = parsed["items"], parsed["threads"]

    by_file: dict[str, list[tuple]] = {}
    for it in items:
        by_file.setdefault(it["file"], []).append(
            (it["number"], f"#{it['number']}", it["status"], it.get("date"),
             _summarise(it["text"]), [], _touches(it["text"], root)))
    for th in threads:
        by_file.setdefault(th["file"], []).append(
            (10_000, th["heading"].split(" - ")[0], th["status"], th.get("date"),
             _summarise(th["heading"].split(" - ", 1)[-1] if " - " in th["heading"] else th["body"]),
             _sub_entries(th["body"]), _touches(th["body"], root)))
    live = sum(1 for i in items if i["status"] in ("todo", "investigate", "in-progress"))
    out = [
        "# plans/ index",
        "",
        "Generated by `mothman dashboard plans-index` - **do not hand-edit**;",
        "a CI check fails if this file and `plans/*.md` disagree.",
        "",
        f"{len(items)} numbered items and {len(threads)} threads "
        f"across {len(by_file)} files. {live} are live work "
        f"(`todo`/`investigate`/`in-progress`).",
        "",
        "Nothing here replaces the files - each line points at an entry that",
        "still exists in full. Read the live ones properly; open a completed",
        "one when this line suggests it matters.",
        "",
    ]
    for name in sorted(by_file, key=_file_sort_key):
        rows = sorted(by_file[name], key=lambda r: r[0])
        out.append(f"## plans/{name}.md")
        out.append("")
        for _, label, status, date, summary, subs, touches in rows:
            bits = [f"**{label}**"]
            if status:
                bits.append(f"`{status}`")
            if date:
                bits.append(date)
            out.append(f"- {' '.join(bits)} - {summary}")
            if touches:
                shown = touches[:_MAX_PATHS]
                more = f" +{len(touches) - len(shown)} more" if len(touches) > len(shown) else ""
                out.append(f"  - *touches:* {', '.join(f'`{t}`' for t in shown)}{more}")
            out.extend(f"  - {sub}" for sub in subs)
        out.append("")
    return "\n".join(out).rstrip() + "\n"
