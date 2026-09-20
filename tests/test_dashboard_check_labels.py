"""Tests for pipeline/dashboard_check_labels.py's status_rank/
rank_for_headline/display_name - the dashboard's shared "worst status
first" sort and the card title."""
from __future__ import annotations

from pipeline.dashboard_check_labels import display_name, rank_for_headline, status_rank, url_key


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
