"""
Parses the repo's own `CHANGELOG.yaml` - the "What's New" feed the
dashboard's Release Notes panel renders.

Replaced `dashboard/changelog_md.py` on 2026-09-20. That module parsed a
hand-written Keep-a-Changelog Markdown file line by line, recovering
headline, components and prose out of bold runs and bracketed tags -
which worked, and was also the same shape of problem REQ-QAC-023 had just
removed from the contract: real structure recorded as prose and then
re-derived by matching text. It bit at least twice, both recorded in
`plans/dashboard.md` #17: hyphenated words broke across wrapped lines,
and an item's own text had to be reassembled before it could be parsed
at all.

So this module does almost nothing, deliberately. `CHANGELOG.yaml`'s own
shape IS the shape the dashboard renders; this loads it, applies
defaults, and hands it over - the same "no interpretation of its own"
posture `dashboard/requirements_yaml.py` already takes, and the opposite
of what a Markdown parser is forced into.

The output shape is unchanged from `changelog_md.py`'s, so the template's
own renderer needed no restructuring:

    {"intro": [str, ...],
     "entries": [{"date": str,
                  "summary": str,
                  "sections": [{"category": str,
                                "items": [{"headline": str,
                                           "components": [str, ...],
                                           "text": str,
                                           "time": str | None}]}]}]}

`summary` is the one genuinely new field - one sentence per day, so a
reader can stop there. Mapa's own What's New page is where that idea
comes from.
"""
from __future__ import annotations

from pathlib import Path

import yaml

# The closed set of categories. Plain words rather than Keep a
# Changelog's Added/Changed/Fixed, which read as a spec for a
# maintainer; these read as a sentence for a reader. Validated, because
# an open vocabulary drifts into six near-synonyms within a month.
CATEGORIES = ("New", "Improved", "Fixed")


def _item(raw: dict) -> dict:
    return {
        "headline": (raw.get("headline") or "").strip(),
        "components": list(raw.get("components") or []),
        "text": (raw.get("description") or "").strip(),
        # Optional and normally absent - day-grouping is the point, and a
        # to-the-minute timestamp is detail this audience does not need.
        # Kept in the shape so the renderer needs no change if one day a
        # single item genuinely wants one.
        "time": raw.get("time"),
    }


def parse_changelog(path: str | Path) -> dict:
    """Returns the feed in the file's own top-to-bottom order.

    Never re-sorted here: the file is authored newest-first and that is
    the intended reading order, same convention `requirements_yaml.py`
    follows. Missing optional fields default rather than raise - this
    module renders whatever is really there, and
    `qa_tools/common/validate_changelog.py` is what enforces the schema,
    as its own CI gate."""
    with open(path) as f:
        doc = yaml.safe_load(f) or {}

    intro = doc.get("intro") or ""
    intro_paragraphs = [p.strip() for p in intro.split("\n\n") if p.strip()]

    entries = []
    for release in doc.get("releases") or []:
        sections = [
            {"category": (s.get("category") or "").strip(),
             "items": [_item(i) for i in (s.get("items") or [])]}
            for s in (release.get("changes") or [])
        ]
        entries.append({
            "date": str(release.get("date") or ""),
            "summary": (release.get("summary") or "").strip(),
            "sections": sections,
        })
    return {"intro": intro_paragraphs, "entries": entries}
