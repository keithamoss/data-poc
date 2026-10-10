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
# A markdown list directly under a sub-entry's own bold header, and the
# leading term of each of its items. See _list_leads() for why the terms
# alone beat the first item's full prose.
_LIST_ITEM_RE = re.compile(r"(?:^|\n)\s*-\s+(.+?)(?=\n\s*-\s|\Z)", re.S)
# A clause boundary INSIDE a list item. `\.\s` and not a bare `\.`
# deliberately: a term is very often a real filename, and splitting
# `qa_results_writer.py` or `CLAUDE.md` at its extension renames it
# to something that does not exist.
_LEAD_SPLIT_RE = re.compile(r"\s+-\s|\.\s|[,;(]")
_MAX_LEAD = 48
_MAX_LEADS = 10
# Two deliberate overruns past _MAX_SUMMARY, both measured rather than
# guessed (2026-09-20). Only 21 sub-entries in the whole index are term
# lists and only 27 summaries would otherwise stop inside an open
# bracket, so carrying each one to its natural end costs ~1,900 tokens
# on a ~7,000-token index. Raising _MAX_SUMMARY itself to cover the same
# two cases would have cost three times that, and spent it mostly on
# ordinary prose that was not the problem.
_MAX_TERM_LINE = 280
_MAX_PAREN_CLOSE = 280


def _clip(text: str, cap: int) -> str:
    """Truncate to roughly `cap`, but never stop inside an open bracket.

    Measured 2026-09-20: 72% of entry summaries and 98% of sub-entries
    are longer than the cap, so where the cut lands is not an edge case,
    it is the normal case. And this project's prose habitually puts the
    decision inside a parenthetical - `plans/dashboard.md` #8 reads
    "...scoped via AskUserQuestion before building (category axis: a real
    per-check metadata field...; UI surface: grouped collapsible
    sections...)", where everything that was actually decided is inside
    the brackets. Cutting at a fixed 120 characters landed on "(category
    axis: a real per-check", which a real proof run reported as giving no
    outcome at all - it names the axis of the decision and then stops.

    So when the cut would leave a bracket open, either take the whole
    parenthetical (if it closes within a modest overrun) or drop it
    entirely and end on the clause before. An unclosed bracket is the one
    place a truncation is actively misleading rather than merely short:
    it promises a qualification it then withholds."""
    if len(text) <= cap:
        return text
    cut = text[:cap].rsplit(" ", 1)[0]
    if cut.count("(") > cut.count(")"):
        close = text.find(")", len(cut))
        if close != -1 and close < _MAX_PAREN_CLOSE:
            return text[:close + 1] + ("..." if close + 1 < len(text) else "")
        cut = cut[:cut.rfind("(")].rstrip(" ,;-")
    return cut + "..."


def _summarise(text: str) -> str:
    """One line describing an entry, taken from its own first sentence.

    Deliberately not a rewrite or a generated paraphrase - a summary that
    says something the item does not is worse than no summary, because
    the whole point is deciding whether to go and read the real thing."""
    flat = " ".join(text.split())
    first = _SENTENCE_END_RE.split(flat, 1)[0] if flat else ""
    return _clip(_MD_NOISE_RE.sub("", first).strip(), _MAX_SUMMARY)


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
        leads = _list_leads(m.group(2))
        if leads:
            # A term list gets the longer budget: every character is a
            # field/option NAME, which is the densest thing the index
            # ever carries, and stopping one term short is precisely the
            # failure this whole path exists to fix.
            text = _MD_NOISE_RE.sub("", lead).rstrip(":") + ": " + ", ".join(leads)
            out.append(_clip(text, _MAX_TERM_LINE))
            continue
        rest = " ".join(m.group(2).split())
        text = _MD_NOISE_RE.sub("", f"{lead} {rest}".strip() if rest else lead)
        out.append(_clip(text, _MAX_SUMMARY))
    return out


def _list_leads(rest: str) -> list[str] | None:
    """The leading term of each item, when a header introduces a list.

    A header ending in a colon is announcing a set, and the set is the
    answer. Carrying the following prose verbatim spends the whole
    character budget on the FIRST member and names none of the others:
    "Confirmed field set for the metadata, each check gets: - check_id -
    human-entered, must be globally unique (CI-enforced). Format
    confirmed 2026-09-16..." is what a real proof run got, and it
    reported back that the line "names no fields" - in the one sub-entry
    whose contents were the entire subject of its task. Listing the terms
    instead yields "check_id, introduced_date, retired_as_of +
    retired_reason, description, changelog", which answers the question
    and is SHORTER than the truncation it replaces.

    Returns None for anything that isn't a real list of 2+ items, so a
    header followed by ordinary prose keeps the old behaviour."""
    items = _LIST_ITEM_RE.findall(rest)
    if len(items) < 2:
        return None
    leads: list[str] = []
    for item in items:
        term = _LEAD_SPLIT_RE.split(" ".join(item.split()), 1)[0]
        term = _MD_NOISE_RE.sub("", term).strip()
        if len(term) > _MAX_LEAD:
            term = term[:_MAX_LEAD].rsplit(" ", 1)[0].rstrip()
        if term and term not in leads:
            leads.append(term)
    return leads[:_MAX_LEADS] or None


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
