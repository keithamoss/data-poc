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

from dashboard.changelog_yaml import CATEGORIES, parse_changelog
from qa_tools.common.validate_requirements import _COMPONENT_CODES

ROOT = Path(__file__).resolve().parent.parent.parent
CHANGELOG_YAML = ROOT / "CHANGELOG.yaml"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# The same taxonomy requirement ids are built from, by full name. Taken
# from `_COMPONENT_CODES` rather than restated, so there is one source
# of truth and adding a component cannot leave this behind.
VALID_COMPONENTS = frozenset(_COMPONENT_CODES.values())


def validate(feed: dict) -> list[str]:
    """Pure function over parsed feed data - no file I/O, testable
    against a fixture dict, same pattern as `validate_requirements.py`'s
    own `validate()`."""
    errors: list[str] = []
    entries = feed.get("entries") or []
    if not entries:
        errors.append("CHANGELOG.yaml has no releases")

    seen_dates: set[str] = set()
    for entry in entries:
        date = entry.get("date") or ""
        where = f"release {date!r}" if date else "a release with no date"

        if not _DATE_RE.match(date):
            errors.append(f'{where}: date must be a real "YYYY-MM-DD" string')
        elif date in seen_dates:
            # Two blocks for one day means a reader sees the same date
            # twice and cannot tell which is authoritative. Append to the
            # existing day instead.
            errors.append(f"{where}: appears more than once - merge the day's entries")
        else:
            seen_dates.add(date)

        if not (entry.get("summary") or "").strip():
            errors.append(f"{where}: missing summary - one sentence for the whole day, "
                           f"so a reader can stop there")

        sections = entry.get("sections") or []
        if not sections:
            errors.append(f"{where}: has no changes")

        for section in sections:
            category = section.get("category") or ""
            if category not in CATEGORIES:
                errors.append(f"{where}: category {category!r} is not one of "
                               f"{', '.join(CATEGORIES)}")
            items = section.get("items") or []
            if not items:
                errors.append(f"{where}, {category or 'a section'}: has no items")

            for item in items:
                headline = (item.get("headline") or "").strip()
                item_where = f"{where}, {category}, {headline or '(no headline)'!r}"
                if not headline:
                    errors.append(f"{item_where}: missing headline")
                if not (item.get("text") or "").strip():
                    errors.append(f"{item_where}: missing description")
                components = item.get("components") or []
                if not components:
                    errors.append(f"{item_where}: names no components")
                for component in components:
                    if component not in VALID_COMPONENTS:
                        errors.append(
                            f"{item_where}: component {component!r} is not one of the "
                            f"project's own {len(VALID_COMPONENTS)}: "
                            f"{', '.join(sorted(VALID_COMPONENTS))}")
    return errors


def main() -> int:
    if not CHANGELOG_YAML.exists():
        print(f"CHANGELOG.yaml not found at {CHANGELOG_YAML}", file=sys.stderr)
        return 1
    feed = parse_changelog(CHANGELOG_YAML)
    errors = validate(feed)
    if errors:
        print(f"changelog validation FAILED ({len(errors)} error(s)):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    items = sum(len(s["items"]) for e in feed["entries"] for s in e["sections"])
    print(f"changelog validation OK - {len(feed['entries'])} day(s), {items} item(s), "
          f"zero errors.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
