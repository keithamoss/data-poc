"""Tests for dashboard/plans_md.py - the plans/*.md parser (running-
thoughts.md #10). Fixture-based (small hand-written markdown strings per
test), not the real committed plans/*.md files - those change over time
and aren't what this module's own correctness depends on."""
from __future__ import annotations

from dashboard.plans_md import _parse_numbered_items, _parse_threads, parse_plans


def test_parses_a_single_numbered_item_with_one_component(tmp_path):
    text = """1. **[done, 2026-09-18]** **[Dashboard UI]** A real feature shipped.
"""
    items = _parse_numbered_items(text, "wider")
    assert items == [{
        "file": "wider", "number": 1, "status": "done", "date": "2026-09-18",
        "components": ["Dashboard UI"], "section": None, "text": "A real feature shipped.",
    }]


def test_parses_multiple_components_on_one_item(tmp_path):
    text = "1. **[todo, 2026-09-18]** **[QA checks & contract]** **[Pipeline & publishing]** Two things.\n"
    items = _parse_numbered_items(text, "qa-pipeline")
    assert items[0]["components"] == ["QA checks & contract", "Pipeline & publishing"]


def test_joins_a_wrapped_paragraph_across_multiple_lines(tmp_path):
    text = """1. **[investigate, 2026-09-18]** **[Docs & process]** A long item that wraps
   across multiple lines in the markdown
   source, same paragraph.
"""
    items = _parse_numbered_items(text, "wider")
    assert items[0]["text"] == "A long item that wraps across multiple lines in the markdown source, same paragraph."


def test_preserves_paragraph_breaks_within_one_item(tmp_path):
    text = """1. **[done, 2026-09-18]** **[Dashboard UI]** First paragraph.

   Second paragraph, a separate thought.
"""
    items = _parse_numbered_items(text, "wider")
    assert items[0]["text"] == "First paragraph.\n\nSecond paragraph, a separate thought."


def test_preserves_a_bullet_list_within_one_item_as_its_own_lines(tmp_path):
    text = """1. **[done, 2026-09-18]** **[Dashboard UI]** Built:
   - first thing done
   - second thing done, wrapped
     across two lines
"""
    items = _parse_numbered_items(text, "wider")
    assert items[0]["text"] == (
        "Built:\n\n- first thing done\n- second thing done, wrapped across two lines"
    )


def test_preserves_a_numbered_list_within_one_item_as_its_own_lines(tmp_path):
    """Real bug, found via Keith's own dashboard report (2026-09-19): a
    numbered/ordered sub-list inside an item's body (e.g. plans/
    tooling.md #1's own "Build order" phase list) was silently word-
    joined into one flowing, illegible paragraph - only "- "/"* " bullet
    markers were recognised as list-item boundaries, not "1. "/"2. "
    ones."""
    text = """1. **[done, 2026-09-18]** **[Testing & dev tooling]** Build order:
   1. Phase one does the first thing.
   2. Phase two does the second thing.
"""
    items = _parse_numbered_items(text, "wider")
    assert items[0]["text"] == (
        "Build order:\n\n1. Phase one does the first thing.\n2. Phase two does the second thing."
    )


def test_a_numbered_list_item_that_wraps_across_lines_stays_one_list_item(tmp_path):
    text = """1. **[done, 2026-09-18]** **[Testing & dev tooling]** Build order:
   1. Phase one does the first thing,
      wrapped across two lines.
   2. Phase two.
"""
    items = _parse_numbered_items(text, "wider")
    assert items[0]["text"] == (
        "Build order:\n\n1. Phase one does the first thing, wrapped across two lines.\n2. Phase two."
    )


def test_parses_multiple_items_in_file_order(tmp_path):
    text = """1. **[done, 2026-09-18]** **[Dashboard UI]** First item.

2. **[todo, 2026-09-18]** **[Docs & process]** Second item.
"""
    items = _parse_numbered_items(text, "wider")
    assert [i["number"] for i in items] == [1, 2]
    assert [i["status"] for i in items] == ["done", "todo"]


def test_captures_the_nearest_preceding_section_heading(tmp_path):
    text = """## Found running the real tools

1. **[done, 2026-09-18]** **[QA checks & contract]** First item.

## Held over from the original build

7. **[old-format-not-a-real-status]** Untagged legacy item, skipped entirely.
"""
    items = _parse_numbered_items(text, "qa-pipeline")
    assert len(items) == 1
    assert items[0]["section"] == "Found running the real tools"


def test_an_item_in_the_old_untagged_format_is_silently_skipped(tmp_path):
    """Real content: qa-pipeline.md's own "Held over from the original
    (equivalent-only) build" section restarts its own numbering in the
    OLD, pre-retrofit tag format - this parser doesn't retrofit-match it,
    same "skip what doesn't match" philosophy the changelog parser has always had
    optional fields."""
    text = "7. **[open]** An old-format item with no date/component tags.\n"
    assert _parse_numbered_items(text, "qa-pipeline") == []


def test_parses_a_tagged_thread_with_status_and_category(tmp_path):
    text = """## Thread A - resupply-chain modeling (2026-09-17)

**Status:** done (2026-09-17) · **Category:** QA checks & contract

**The tension.** Some real design prose here,
wrapped across two lines.

A second paragraph.
"""
    threads = _parse_threads(text, "conceptual-design")
    assert len(threads) == 1
    t = threads[0]
    assert t["heading"] == "Thread A - resupply-chain modeling (2026-09-17)"
    assert t["status"] == "done"
    assert t["date"] == "2026-09-17"
    assert t["category"] == "QA checks & contract"
    assert t["body"] == "**The tension.** Some real design prose here,\nwrapped across two lines.\n\nA second paragraph."


def test_a_heading_with_no_status_line_is_not_captured_as_a_thread(tmp_path):
    text = """## Doc updates needed once this starts landing

Just some prose, no Status/Category tag line under this heading at all.

## Thread B - a real tagged section

**Status:** parked (2026-09-16) · **Category:** Pipeline & publishing

Body.
"""
    threads = _parse_threads(text, "publishing-and-history")
    assert len(threads) == 1
    assert threads[0]["heading"] == "Thread B - a real tagged section"


def test_parses_multiple_threads_in_file_order(tmp_path):
    text = """## Thread B - first

**Status:** done (2026-09-16) · **Category:** Pipeline & publishing

First body.

## Thread A - second

**Status:** parked (2026-09-17) · **Category:** QA checks & contract

Second body.
"""
    threads = _parse_threads(text, "publishing-and-history")
    assert [t["heading"] for t in threads] == ["Thread B - first", "Thread A - second"]


def test_parse_plans_reads_all_files_and_returns_the_combined_shape(tmp_path):
    plans_dir = tmp_path
    (plans_dir / "wider.md").write_text("1. **[done, 2026-09-18]** **[Dashboard UI]** A wider item.\n")
    (plans_dir / "qa-pipeline.md").write_text("1. **[todo, 2026-09-18]** **[QA checks & contract]** A QA item.\n")
    (plans_dir / "dashboard.md").write_text("1. **[done, 2026-09-18]** **[Dashboard UI]** A dashboard item.\n")
    (plans_dir / "data-generation.md").write_text("1. **[parked, 2026-09-18]** **[Data generation]** A data-gen item.\n")
    (plans_dir / "tooling.md").write_text("1. **[in-progress, 2026-09-18]** **[Testing & dev tooling]** A tooling item.\n")
    (plans_dir / "publishing-and-history.md").write_text(
        "## Thread B - a thread\n\n**Status:** done (2026-09-16) · **Category:** Pipeline & publishing\n\nBody.\n"
    )
    (plans_dir / "conceptual-design.md").write_text(
        "## Thread A - a thread\n\n**Status:** parked (2026-09-17) · **Category:** QA checks & contract\n\nBody.\n"
    )
    # publishing-and-history legitimately carries BOTH numbered items and
    # threads; performance.md was never listed when this was an
    # allowlist. Both are picked up by the directory walk now.
    (plans_dir / "performance.md").write_text(
        "1. **[done, 2026-09-18]** **[Testing & dev tooling]** A perf item.\n"
    )

    result = parse_plans(plans_dir)
    assert len(result["items"]) == 6
    assert {i["file"] for i in result["items"]} == {
        "wider", "qa-pipeline", "dashboard", "data-generation", "tooling", "performance"}
    assert len(result["threads"]) == 2
    assert {t["file"] for t in result["threads"]} == {"publishing-and-history", "conceptual-design"}


def test_a_hyphenated_word_wrapped_across_lines_is_rejoined_without_a_space():
    """Real bug, found 2026-09-20 while checking whether a generated index
    line would be legible: plans_md.py joins wrapped lines with " ".join,
    so a hyphenated word split across two source lines ("requirements-\n
    analysis") comes back as "requirements- analysis". It renders that way
    in the live dashboard's Plans tab. 195 occurrences across 74 of 137
    items when this test was written."""
    import re
    items = parse_plans("plans")["items"]
    bad = [(i["file"], i["number"], m.group(0))
           for i in items for m in re.finditer(r"\w+- \w+", i["text"])]
    assert not bad, f"{len(bad)} hyphen-wrap artifacts, e.g. {bad[:5]}"


def test_a_real_dash_between_words_keeps_its_spaces():
    """The other half of the same fix, and the reason it can't just strip
    every trailing hyphen: this project uses ' - ' as a dash constantly
    ("a real bug - not a design gap"). A line ending in a standalone
    hyphen is punctuation, not a wrapped word, and must keep its space."""
    from dashboard.markdown_text import join_wrapped
    assert join_wrapped(["a real bug -", "not a design gap"]) == "a real bug - not a design gap"
    assert join_wrapped(["requirements-", "analysis subagent"]) == "requirements-analysis subagent"
    assert join_wrapped(["plain", "words"]) == "plain words"


def test_every_numbered_item_in_every_plans_file_is_parsed():
    """Real bug, found 2026-09-20 while building the plans index
    (plans/tooling.md #17): NUMBERED_FILES was an allowlist of five
    files, and two others had since grown numbered items -
    publishing-and-history.md (8) and performance.md (5). All 13 were
    invisible to the dashboard's Plans tab, which presents itself as the
    browsable view of this project's memory and was silently showing 138
    of 151. Among the missing was publishing-and-history #6, the
    HIGH-priority per-dataset architecture item.

    Asserted generically against the real files rather than against a
    count, so that a NEW plans file growing items cannot be forgotten
    the same way - which is exactly how this happened.

    Writing it caught a second, separate thing: 10 items across three
    files still carried the pre-2026-09-18 shape (`**[open, low]**`,
    `**[done]**` - a status and a PRIORITY, no date), left behind by that
    convention's own retrofit and silently unparsed for the same reason.
    Those were retrofitted 2026-09-20, so this assertion is deliberately
    UNSCOPED - anything shaped like a numbered item must parse, whatever
    format it is in. An item written in some third shape should fail here
    rather than vanish."""
    import re
    from pathlib import Path
    seen = {(i["file"], i["number"]) for i in parse_plans("plans")["items"]}
    missing = []
    for path in sorted(Path("plans").glob("*.md")):
        if path.name == "INDEX.md":
            continue
        for m in re.finditer(r"^(\d+)\.\s+\*\*\[", path.read_text(), re.M):
            if (path.stem, int(m.group(1))) not in seen:
                missing.append(f"{path.name}#{m.group(1)}")
    assert not missing, f"{len(missing)} numbered items never parsed: {missing}"


def test_a_brand_new_plans_file_is_picked_up_with_no_code_change(tmp_path):
    """Keith's own call, 2026-09-20, on being shown that two files had
    grown numbered items nobody had added to an allowlist: "I'm happy for
    it just to walk all of the markdown files in a given directory -
    that's probably safer because we will probably add more files as we
    go."

    The failure mode the allowlist had is the dangerous kind: a file it
    didn't know about was skipped SILENTLY, so the dashboard's Plans tab
    under-reported without anything looking wrong."""
    (tmp_path / "a-brand-new-topic.md").write_text(
        "1. **[todo, 2026-09-20]** **[Dashboard UI]** An item in a file nobody listed.\n"
    )
    result = parse_plans(tmp_path)
    assert [(i["file"], i["number"]) for i in result["items"]] == [("a-brand-new-topic", 1)]


def test_the_generated_index_is_not_parsed_as_planning_content(tmp_path):
    """plans/INDEX.md lives in the same directory and is generated FROM
    these files - walking the directory must not read it back in, or the
    index becomes self-referential."""
    (tmp_path / "real.md").write_text(
        "1. **[todo, 2026-09-20]** **[Dashboard UI]** A real item.\n"
    )
    (tmp_path / "INDEX.md").write_text(
        "## plans/real.md\n\n- **#1** `todo` 2026-09-20 - A real item.\n"
    )
    result = parse_plans(tmp_path)
    assert {i["file"] for i in result["items"]} == {"real"}
    assert not [t for t in result["threads"] if t["file"] == "INDEX"]
