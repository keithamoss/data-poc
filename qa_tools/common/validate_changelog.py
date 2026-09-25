"""
CI gate for `CHANGELOG.yaml` (2026-09-20).

Keith's own ask when the format was settled - the component tags stay,
and "the components should be CI checked as well, obviously". This is
that check, plus the schema rules that stop a hand-authored feed
degrading: every release needs a real date and a summary, every item
needs a headline and a description, and every category comes from a
closed vocabulary.

Why a component typo matters more than it looks: the tags are what the
7-part taxonomy means on this page, and that taxonomy is already
cross-checked between `validate_requirements.py`'s codes, the
dashboard's own consts and `docs/components.md`
(`tests/test_component_taxonomy_consistency.py`). A changelog entry
tagged "Dashboard" instead of "Dashboard UI" would not fail any of
those - it would simply render as a tag that matches no filter and
groups with nothing, silently. So this validates against the same
single source of truth the requirement ids use, rather than a list
copied here.

What this deliberately does NOT check is the VOICE, which is the thing
the rewrite was actually for - second person, outcome-only, no file
paths or tool names. That is not machine-checkable, and a proxy for it
(banning "refactor", requiring "you") would be gamed within a week and
wrong more often than right. The header of `CHANGELOG.yaml` states the
standard; review is what holds it.

Run as `mothman dashboard validate-changelog`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


from qa_tools.common import yaml_io
from pydantic import ValidationError

from qa_tools.common.schemas import Changelog, format_error
from qa_tools.common.vocab import CHANGELOG_CATEGORIES, COMPONENT_CODES

ROOT = Path(__file__).resolve().parent.parent.parent
CHANGELOG_YAML = ROOT / "CHANGELOG.yaml"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# The same taxonomy requirement ids are built from, by full name. Taken
# from `_COMPONENT_CODES` rather than restated, so there is one source
# of truth and adding a component cannot leave this behind.
VALID_COMPONENTS = frozenset(COMPONENT_CODES.values())
CATEGORIES = CHANGELOG_CATEGORIES


def validate(raw: dict) -> list[str]:
    """Schema first, then the one rule a schema cannot express.

    Restructured 2026-09-20 (REQ-DOCS-029). Almost all of this module
    was schema work - required fields, a closed category vocabulary, a
    date pattern, nesting - and now lives as a declaration in
    `qa_tools/common/schemas.py`. What is left is the duplicate-date
    rule, which is about the relationship BETWEEN releases rather than
    the shape of any one of them.

    Takes the RAW parsed YAML rather than `changelog_yaml.parse_changelog()`
    output, deliberately: that parser's documented job is to render
    whatever is really there and never raise, so it fills in defaults
    that would hide exactly the absences this is meant to report."""
    errors: list[str] = []
    try:
        feed = Changelog(**(raw or {}))
    except ValidationError as e:
        for err in e.errors():
            loc = list(err["loc"])
            # Name the release by its DATE rather than its index - "the
            # third release" means nothing to someone looking at a file
            # ordered newest-first.
            where = "CHANGELOG.yaml"
            if len(loc) >= 2 and loc[0] == "releases" and isinstance(loc[1], int):
                releases = (raw or {}).get("releases") or []
                if loc[1] < len(releases):
                    where = f"release {releases[loc[1]].get('date', '(no date)')!r}"
            trimmed = dict(err, loc=tuple(loc[2:]) or tuple(loc))
            errors.append(format_error(trimmed, where))
        return errors

    seen: dict[str, int] = {}
    for release in feed.releases:
        seen[release.date] = seen.get(release.date, 0) + 1
    for date, count in seen.items():
        if count > 1:
            # Two blocks for one day means a reader sees the same date
            # twice and cannot tell which is authoritative.
            errors.append(f"release {date!r}: appears {count} times - merge the day's entries")
    return errors


def main() -> int:
    if not CHANGELOG_YAML.exists():
        print(f"CHANGELOG.yaml not found at {CHANGELOG_YAML}", file=sys.stderr)
        return 1
    with open(CHANGELOG_YAML) as f:
        raw = yaml_io.load(f) or {}
    errors = validate(raw)
    if errors:
        print(f"changelog validation FAILED ({len(errors)} error(s)):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    feed = Changelog(**raw)
    items = sum(len(s.items) for r in feed.releases for s in r.changes)
    print(f"changelog validation OK - {len(feed.releases)} day(s), {items} item(s), "
          f"zero errors.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
