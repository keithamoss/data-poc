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
        # A thin marker like "Decision:" says nothing on its own, so carry
        # the sentence it introduces.
        rest = " ".join(m.group(2).split())
        text = f"{lead} {rest}".strip() if len(lead) < 45 and rest else lead
        text = _MD_NOISE_RE.sub("", text)
        if len(text) > _MAX_SUMMARY:
            text = text[:_MAX_SUMMARY].rsplit(" ", 1)[0] + "..."
        out.append(text)
    return out


def _file_sort_key(name: str) -> tuple[int, str]:
    return (_FILE_ORDER.index(name), "") if name in _FILE_ORDER else (len(_FILE_ORDER), name)


def build_index(plans_dir: str = "plans") -> str:
    parsed = parse_plans(plans_dir)
    items, threads = parsed["items"], parsed["threads"]

    by_file: dict[str, list[tuple]] = {}
    for it in items:
        by_file.setdefault(it["file"], []).append(
            (it["number"], f"#{it['number']}", it["status"], it.get("date"),
             _summarise(it["text"]), []))
    for th in threads:
        by_file.setdefault(th["file"], []).append(
            (10_000, th["heading"].split(" - ")[0], th["status"], th.get("date"),
             _summarise(th["heading"].split(" - ", 1)[-1] if " - " in th["heading"] else th["body"]),
             _sub_entries(th["body"])))
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
        for _, label, status, date, summary, subs in rows:
            bits = [f"**{label}**"]
            if status:
                bits.append(f"`{status}`")
            if date:
                bits.append(date)
            out.append(f"- {' '.join(bits)} - {summary}")
            out.extend(f"  - {sub}" for sub in subs)
        out.append("")
    return "\n".join(out).rstrip() + "\n"
