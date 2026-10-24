"""Tests for pipeline/dashboard_check_labels.py's status_rank/
rank_for_headline/display_name - the dashboard's shared "worst status
first" sort and the card title."""
from __future__ import annotations

from pipeline.dashboard_check_labels import (
    display_name, rank_for_headline, status_rank, tool_ref, url_key,
)


def test_status_rank_green_amber_red():
    assert status_rank(current=0, warn=1, fail=10) == 0
    assert status_rank(current=5, warn=1, fail=10) == 1
    assert status_rank(current=15, warn=1, fail=10) == 2


def test_status_rank_treats_none_current_as_zero():
    assert status_rank(current=None, warn=0, fail=0) == 0


def test_rank_for_headline_sorts_worst_first_and_is_stable():
    checks = [
        {"name": "green", "current": 0, "warn": 1, "fail": 10},
        {"name": "red", "current": 15, "warn": 1, "fail": 10},
        {"name": "amber", "current": 5, "warn": 1, "fail": 10},
        {"name": "red-2", "current": 20, "warn": 1, "fail": 10},
    ]

    rank_for_headline(checks)

    assert [c["name"] for c in checks] == ["red", "red-2", "amber", "green"]


def test_display_name_is_the_label_alone():
    """The tool and its macro used to be appended - "Duplicate rate —
    dbt:unique (dbt-core)". Both are gone (plans/running-thoughts.md
    #19): rules 10 and 11 of docs/check-authoring-rules.md forbid naming
    a tool or a macro anywhere in a check's prose, and this heading sat
    directly above that prose doing exactly that.

    Nothing is lost - every card and drawer still carries `note`,
    "Computed by dbt-core against this run's real data"."""
    assert display_name("dbt:unique", "dbt", "Duplicate rate") == "Duplicate rate"


def test_display_name_falls_back_to_the_check_name_with_no_label():
    """A check whose own name is already plain - a hand-written Soda
    `name:`, or a business rule whose name is a full sentence - has no
    label, and that name is used as-is."""
    assert display_name("Escalation completeness", "Soda Core", None) == "Escalation completeness"


def test_url_key_is_the_check_id_tail_not_the_heading():
    """What makes the heading free to be prose: the URL keys on this
    instead (REQ-QAC-023's validate_tail_uniqueness guarantees it is
    unique within a column)."""
    assert url_key("data-asset-1.ag.ds.tbl.sex.invalid_percent_soda") == "invalid_percent_soda"


def test_url_key_degrades_to_the_raw_id_when_it_cannot_parse():
    assert url_key("not-a-real-check-id") == "not-a-real-check-id"


# ---------------------------------------------------------------------
# tool_ref() - REQ-DASH-026's "dbt:not_null" line, the terse "which
# tool, which check" under a card's plain-English headline.
# ---------------------------------------------------------------------

def test_tool_ref_moves_the_tool_token_to_the_front():
    assert tool_ref("data-asset-1.ag.ds.tbl.sex.not_null_dbt") == "dbt:not_null"
    assert tool_ref("data-asset-1.ag.ds.tbl.sex.invalid_percent_soda") == "soda:invalid_percent"


def test_tool_ref_handles_a_terse_name_that_itself_contains_underscores():
    """The split is on the LAST token, not the first - "closed_case_
    hygiene_datacontract" is one check, not a tool called "closed"."""
    assert (tool_ref("data-asset-1.ag.ds.tbl.c.closed_case_hygiene_datacontract")
            == "datacontract:closed_case_hygiene")
    assert (tool_ref("data-asset-1.ag.ds.tbl.c.row_count_growth_evidently")
            == "evidently:row_count_growth")


def test_tool_ref_and_url_key_are_the_same_string_reordered():
    """The point of deriving this from the check_id rather than
    hand-authoring it: what a reader sees on the card is what they can
    deep-link to and grep the contract for."""
    cid = "data-asset-1.ag.ds.tbl.sex.not_null_dbt"
    assert url_key(cid) == "not_null_dbt"
    assert tool_ref(cid) == "dbt:not_null"


def test_tool_ref_reuses_the_grammars_own_tool_list_rather_than_a_copy():
    """Written as a duplicate tuple first, and these two cases are how
    that was caught. The check_id grammar ALREADY requires the tail to
    end in one of the four tools, so a second list in the label module
    could only ever drift out of agreement with the thing enforcing it.
    Asserting on the shared constant means adding a fifth tool in one
    place cannot leave this behind."""
    from qa_tools.common.check_id import TOOLS
    for tool in TOOLS:
        assert tool_ref(f"data-asset-1.ag.ds.tbl.c.some_check_{tool}") == f"{tool}:some_check"


def test_tool_ref_leaves_an_unrecognised_tool_token_alone():
    """A fifth tool arriving before the grammar knows about it reads
    oddly rather than being mangled into a wrong tool name. It falls all
    the way through to url_key()'s raw-id fallback, because the id does
    not parse in the first place - the protection is upstream of this
    function, which is the right place for it."""
    assert (tool_ref("data-asset-1.ag.ds.tbl.c.some_check_greatexpectations")
            == "data-asset-1.ag.ds.tbl.c.some_check_greatexpectations")


def test_tool_ref_does_not_strip_a_tail_that_is_only_a_tool_token():
    """"dbt" alone must not become "dbt:" with nothing after the colon,
    which would read as a truncation bug rather than as a check. Same
    mechanism as above - the grammar needs a real name before the
    underscore, so this never parses."""
    assert tool_ref("data-asset-1.ag.ds.tbl.c.dbt") == "data-asset-1.ag.ds.tbl.c.dbt"


def test_tool_ref_degrades_to_the_raw_id_when_it_cannot_parse():
    assert tool_ref("not-a-real-check-id") == "not-a-real-check-id"
