"""The configuration as it stood before REQ-GEN-207 grew Child Protection ten
years at its old end (2026-10-15) - eight since REQ-GEN-238 dropped the oldest
two (2026-10-26).

Many configuration tests edit "the first version" of a dataset's participation,
the collection's defaults or the quarterly calendar, meaning the 2023-01-01
version that governs the supplies the test files and judges. Since the growth,
the first version is a grown one, which no such test is about. These tests keep
their meaning by reading the calendar without the grown versions - a history
that starts in 2023, as they were written against - rather than by re-indexing a
hundred call sites.

BY THEIR DATES (REQ-GEN-238 criterion 4): each grown version is named here by
its effective_from, so a version that moves is noticed rather than silently
filtered or silently kept - and every block filtered must lose at least one.
"""
from __future__ import annotations

#: The quarterly calendar's grown version, which Emergency Department's
#: history still uses, and the amber and replacement settings' (REQ-GEN-207
#: criterion 5; left in place by REQ-GEN-238 criterion 3).
GROWN_FROM = "2013-01-01"
#: Child Protection's earliest participation and defaults since REQ-GEN-238.
CP_GROWN_FROM = "2015-01-01"
#: Every grown version's date: the two above, cp-carers' turn back on after
#: TS-63 (REQ-GEN-218) and Emergency Department's gap (REQ-GEN-251).
GROWN_DATES = frozenset({GROWN_FROM, CP_GROWN_FROM, "2022-06-01", "2015-10-01", "2015-12-01"})
#: Where the history started before the growth: no version effective before it
#: may survive the filter.
ORIGINAL_FROM = "2023-01-01"
#: The collections whose blocks carry grown versions.
GROWN_COLLECTIONS = ("child-protection", "emergency-department")


def _datasets_of(doc: dict) -> set[str]:
    from qa_tools.common import hierarchy

    return {d.dataset_id for c in GROWN_COLLECTIONS for d in hierarchy.datasets_in_collection(c)}


def calendar(doc: dict) -> dict:
    """`doc` (a parsed calendar.yaml) with every grown version removed, in
    place; returns it."""
    lost: dict[str, int] = {}

    def keep(where: str, versions):
        kept = [v for v in versions if str(v.get("effective_from")) not in GROWN_DATES]
        early = [str(v.get("effective_from")) for v in kept
                 if str(v.get("effective_from")) < ORIGINAL_FROM]
        assert not early, f"{where}: version(s) {early} predate {ORIGINAL_FROM} and are " \
                          f"not named in GROWN_DATES - a grown version moved"
        lost[where] = len(versions) - len(kept)
        return kept

    for cal in doc.get("calendars") or []:
        if cal.get("name") == "quarterly":
            cal["versions"] = keep("calendar quarterly", cal.get("versions") or [])
    for coll in doc.get("collections") or []:
        block = coll.get("participation_defaults")
        if coll.get("id") in GROWN_COLLECTIONS and block and block.get("versions"):
            block["versions"] = keep(f"collection {coll['id']}", block["versions"])
    grown = _datasets_of(doc)
    for entry in doc.get("datasets") or []:
        block = entry.get("participation")
        if entry.get("id") in grown and block and block.get("versions"):
            block["versions"] = keep(f"dataset {entry['id']}", block["versions"])
    # EVERY BLOCK FILTERED LOST SOMETHING (post-build-review #207 E3; REQ-GEN-238
    # criterion 4): if a grown version ever moves off its date, this would strip
    # nothing there and the tests edit the grown version instead, passing for
    # the wrong reason.
    assert lost and all(lost.values()), \
        f"before_growth stripped nothing from {[k for k, v in lost.items() if not v]}"
    return doc


def asset(doc: dict) -> dict:
    """`doc` (a parsed data-asset.yaml) with the grown history's settings
    versions removed, in place; returns it."""
    for key in ("amber_setting", "replacement_setting"):
        block = doc.get(key)
        if block and block.get("versions"):
            kept = [v for v in block["versions"] if str(v.get("effective_from")) != GROWN_FROM]
            assert len(kept) < len(block["versions"]), \
                f"before_growth stripped nothing from {key}: no version is effective {GROWN_FROM}"
            block["versions"] = kept
    return doc
