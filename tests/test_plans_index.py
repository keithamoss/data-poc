"""Tests for dashboard/plans_index.py - the generated plans/INDEX.md
(plans/tooling.md #17).

The index exists so a session can orient in ~4,400 tokens instead of the
~159,000 CLAUDE.md's "read all seven files in full" instruction costs,
WITHOUT deleting anything - it is a derived view, and every entry it
lists still exists in full in its own file.
"""
from __future__ import annotations
from pathlib import Path

from dashboard.plans_index import build_index
from dashboard.plans_md import parse_plans


def test_the_committed_index_is_current():
    """A generated artifact that IS committed needs something that notices
    when it stops matching its source, or it quietly becomes a lie - the
    same reasoning behind this project's other CI gates. Run
    `mothman dashboard plans-index` and commit the result."""
    assert Path("plans/INDEX.md").read_text() == build_index("plans"), (
        "plans/INDEX.md is stale - run `mothman dashboard plans-index`")


def test_every_parsed_entry_appears_in_the_index():
    """The index's whole value is that a session can trust it to be
    complete - an index that silently omits entries is worse than none,
    because it is read INSTEAD of the files."""
    parsed = parse_plans("plans")
    text = build_index("plans")
    for item in parsed["items"]:
        assert f"**#{item['number']}**" in text
    for thread in parsed["threads"]:
        assert thread["heading"].split(" - ")[0] in text
    lines = [ln for ln in text.splitlines() if ln.startswith("- ")]
    expected = len(parsed["items"]) + len(parsed["threads"])
    assert len(lines) == expected, f"{len(lines)} index lines for {expected} entries"


def test_every_index_line_says_something():
    """A line that carries no summary defeats the point - the reader has to
    open the file to find out whether it is relevant, which is the cost
    the index exists to avoid."""
    bare = [ln for ln in build_index("plans").splitlines()
            if ln.startswith("- ") and len(ln.split(" - ", 1)[-1].strip()) < 10]
    assert not bare, f"{len(bare)} index lines with no useful summary: {bare[:3]}"


def test_the_index_never_claims_to_replace_the_files():
    """Keith's own question when this was scoped - whether the write-ups
    would be deleted. They are not, and the file says so, because a future
    reader finding a 4k index over a 159k source needs to know which is
    authoritative."""
    text = build_index("plans")
    assert "Nothing here replaces the files" in text
    assert "do not hand-edit" in text
