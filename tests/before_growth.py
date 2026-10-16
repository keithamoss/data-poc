"""The configuration as it stood before REQ-GEN-207 grew Child Protection ten
years at its old end (2026-10-15).

Many configuration tests edit "the first version" of a dataset's participation,
the collection's defaults or the quarterly calendar, meaning the 2023-01-01
version that governs the supplies the test files and judges. Since the growth,
the first version is the 2013-01-01 one, which no such test is about. These
tests keep their meaning by reading the calendar without the grown versions -
a history that starts in 2023, as they were written against - rather than by
re-indexing a hundred call sites.
"""
from __future__ import annotations

GROWN_FROM = "2013-01-01"


def calendar(doc: dict) -> dict:
    """`doc` (a parsed calendar.yaml) with every version effective from the
    grown history's first day removed, in place; returns it."""
    stripped = []

    def keep(versions):
        kept = [v for v in versions if str(v.get("effective_from")) != GROWN_FROM]
        stripped.append(len(versions) - len(kept))
        return kept

    for cal in doc.get("calendars") or []:
        cal["versions"] = keep(cal.get("versions") or [])
    for coll in doc.get("collections") or []:
        block = coll.get("participation_defaults")
        if block and block.get("versions"):
            block["versions"] = keep(block["versions"])
    for entry in doc.get("datasets") or []:
        block = entry.get("participation")
        if block and block.get("versions"):
            block["versions"] = keep(block["versions"])
    # IT MUST HAVE REMOVED SOMETHING (post-build-review #207 E3): if the grown
    # versions ever move off GROWN_FROM, this would strip nothing and every
    # test edits the grown version instead, passing for the wrong reason.
    assert sum(stripped), f"before_growth stripped nothing: no version is effective {GROWN_FROM}"
    return doc


def asset(doc: dict) -> dict:
    """`doc` (a parsed data-asset.yaml) with the grown history's settings
    versions removed, in place; returns it."""
    for key in ("amber_setting", "replacement_setting"):
        block = doc.get(key)
        if block and block.get("versions"):
            block["versions"] = [v for v in block["versions"]
                                 if str(v.get("effective_from")) != GROWN_FROM]
    return doc
