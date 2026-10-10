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

**This raises on a feed that does not match the schema** (2026-09-20,
Keith: "I don't mind if the parsers would choke and throw an error").
The shape is declared once, in `qa_tools/common/schemas.py`, and both
this and the CI gate read it from there. What is left here is purely
the rename from the file's own field names to the renderer's -
`description` becomes `text`, `changes` becomes `sections` - which is
the only difference between the two shapes and not worth changing the
authored file to remove, since `description` is the clearer word in a
file people write by hand.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from qa_tools.common.schemas import Changelog
from qa_tools.common.vocab import CHANGELOG_CATEGORIES

# Re-exported under this module's own name for the dashboard build,
# which imports categories from here rather than reaching into
# qa_tools/. Plain words rather than Keep a Changelog's
# Added/Changed/Fixed, which read as a spec for a maintainer; these read
# as a sentence for a reader.
CATEGORIES = CHANGELOG_CATEGORIES


def parse_changelog(path: str | Path) -> dict:
    """Returns the feed in the file's own top-to-bottom order.

    Never re-sorted here: the file is authored newest-first and that is
    the intended reading order, same convention `requirements_yaml.py`
    follows.

    Raises pydantic's ValidationError if the file does not match the
    schema. `qa_tools/common/validate_changelog.py` remains the CI gate,
    and still reads the raw YAML itself rather than going through this,
    so it can report every problem in one run instead of stopping at the
    first."""
    with open(path) as f:
        doc = yaml.safe_load(f) or {}

    feed = Changelog(**(doc or {}))
    intro_paragraphs = [p.strip() for p in feed.intro.split("\n\n") if p.strip()]

    entries = [
        {
            "date": release.date,
            "summary": release.summary,
            "sections": [
                {
                    "category": section.category,
                    "items": [
                        {
                            "headline": item.headline,
                            "components": list(item.components),
                            "text": item.description,
                            # Optional and normally absent - day-grouping
                            # is the point, and a to-the-minute timestamp
                            # is detail this audience does not need. Kept
                            # in the shape so the renderer needs no change
                            # if one day a single item genuinely wants one.
                            "time": item.time,
                        }
                        for item in section.items
                    ],
                }
                for section in release.changes
            ],
        }
        for release in feed.releases
    ]
    return {"intro": intro_paragraphs, "entries": entries}
