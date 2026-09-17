"""Tests for pipeline/dashboard_check_labels.py's status_rank/
rank_for_headline/display_name - the dashboard's shared "worst status
first" sort and the "<label> — <check_name> (<engine>)" card title."""
from __future__ import annotations

from pipeline.dashboard_check_labels import display_name, rank_for_headline, status_rank


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


def test_display_name_with_no_label_is_just_check_and_engine():
    assert display_name("dbt:unique", "dbt", None) == "dbt:unique (dbt)"


def test_display_name_with_a_label_prefixes_it():
    assert display_name("dbt:unique", "dbt", "Duplicate rate") == "Duplicate rate — dbt:unique (dbt)"
