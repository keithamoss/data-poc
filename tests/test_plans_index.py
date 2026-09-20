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
    top_level = [ln for ln in text.splitlines() if ln.startswith("- ")]
    expected = len(parsed["items"]) + len(parsed["threads"])
    assert len(top_level) == expected, f"{len(top_level)} index lines for {expected} entries"


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


def test_a_thread_advertises_what_is_actually_inside_it():
    """Encodes a real incident rather than a hypothetical.

    A `delivery-scoper` run on 2026-09-20 was given an index WITHOUT
    sub-entries and asked to scope a feature that Thread D had already
    designed. Thread D's whole index line was "check lifecycle:
    retirement + definition changes (build together with B)", and the
    agent reported back: "Too thin to judge relevance from... Had I
    trusted the index line, I'd have skipped the single most relevant
    document in the repo and drafted requirements for something already
    built." It only got there via a cross-reference in an unrelated item.

    A one-line summary of a multi-thousand-word design essay is not
    enough to decide whether to open it. Sub-entries are what make the
    index safe to route from, so this asserts the specific thing that
    would have saved that run."""
    text = build_index("plans")
    thread_d = text.split("**Thread D**")[1].split("\n- ")[0]
    assert "Confirmed field set for the metadata" in thread_d, (
        "Thread D's index entry no longer advertises the field design it contains")
    # A header alone is not enough, and that is not hypothetical either.
    # A second run, against an index whose sub-entries stopped AT the
    # colon, reported this exact line as still too thin - "a colon-ended
    # fragment that names no fields... I reached it by grepping the file
    # for 'description', not by following this line." So assert the
    # sub-entry carries what the header introduces.
    assert "check_id" in thread_d, (
        "Thread D's sub-entry names no actual field - it is truncated before "
        "the content begins, which is what made it useless twice")


def test_phases_inside_a_build_order_thread_are_individually_listed():
    """The same failure in its other form - Phase 5c built a shipped UI
    feature, and lived inside a thread whose own one-line summary was
    about the section's renumbering housekeeping."""
    text = build_index("plans")
    build_order = text.split("**Build order**")[1].split("\n- ")[0]
    for phase in ("Phase 1", "Phase 2", "Phase 3", "Phase 4", "Phase 5", "Phase 6"):
        assert phase in build_order, f"{phase} missing from the Build order sub-entries"
