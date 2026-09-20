"""REQ-GHUB-027 - the plain-English "what is actually failing" section
that goes into a QA ticket's body and every run comment.

Built against small hand-made dataset dicts rather than the real
committed dashboard JSON, for the same reason test_validate_requirements
does: the real file's content changes with every pipeline run, and a
test that asserts on today's failures would go red the day a check goes
green. The one test that does read the real files asserts a property
that must hold whatever is failing."""
from __future__ import annotations

import json
from pathlib import Path

from qa_tools.common.ticket_check_summary import (
    DASHBOARD_BASE_URL, build_check_summary, check_url,
)

ROOT = Path(__file__).resolve().parent.parent


def _check(key, name, description, status, tool_ref=None, **over):
    check = {
        "key": key, "name": name, "description": description,
        "tool_ref": tool_ref or f"dbt:{key}",
        "current": 1 if status != "green" else 0,
        "current_status": status, "warn": None, "fail": None,
    }
    check.update(over)
    return check


def _dataset(*columns):
    return {"id": "cp-placements", "name": "Placements",
            "columns": [{"name": n, "checks": list(cs)} for n, cs in columns]}


def _summary(dataset, status="red"):
    return build_check_summary(dataset, status, "child-protection-family-support",
                               "child-protection", "cp-placements")


def test_a_green_dataset_produces_no_section_at_all():
    """The resolved-to-green comment says so in a sentence and has
    nothing to list."""
    ds = _dataset(("carer_id", [_check("unique_dbt", "Duplicate rate", "Must be unique.", "green")]))
    assert _summary(ds, "green") == ""


def test_checks_asking_the_same_question_are_grouped_into_one_entry():
    """The reason this is readable at all: cp-placements' real failing
    checks are 17 rows but 5 distinct questions, and an ungrouped list
    would say "Null rate" six times."""
    ds = _dataset(
        ("a", [_check("not_null_dbt", "Null rate", "Must never be empty.", "red"),
               _check("nullValues_datacontract", "Null rate", "Must never be empty.", "red",
                      tool_ref="datacontract:nullValues")]),
        ("b", [_check("not_null_dbt", "Null rate", "Must never be empty.", "red")]),
    )
    out = _summary(ds)
    assert out.count("**Null rate**") == 1
    assert out.count("Must never be empty.") == 1
    assert "3 checks, 2 columns" in out


def test_grouping_never_drops_a_check_each_one_keeps_its_own_link():
    ds = _dataset(
        ("a", [_check("not_null_dbt", "Null rate", "Must never be empty.", "red"),
               _check("nullValues_datacontract", "Null rate", "Must never be empty.", "red",
                      tool_ref="datacontract:nullValues")]),
    )
    out = _summary(ds)
    assert "/check/not_null_dbt)" in out
    assert "/check/nullValues_datacontract)" in out


def test_amber_checks_are_listed_under_a_red_ticket_but_kept_separate():
    """Keith's own amendment, 2026-09-20: a red ticket still lists the
    amber checks. They go under their own heading, because "why is this
    red" and "also worth knowing" are different questions."""
    ds = _dataset(
        ("a", [_check("unique_dbt", "Duplicate rate", "Must be unique.", "red"),
               _check("duplicate_count_soda", "Duplicate rate",
                      "A few are tolerated.", "amber", tool_ref="soda:duplicate_count")]),
    )
    out = _summary(ds, "red")
    assert "## Failing checks" in out
    assert "## Checks in warning" in out
    assert out.index("## Failing checks") < out.index("## Checks in warning")
    assert "Must be unique." in out and "A few are tolerated." in out


def test_an_amber_ticket_leads_with_its_own_amber_checks():
    ds = _dataset(
        ("a", [_check("duplicate_count_soda", "Duplicate rate", "A few are tolerated.", "amber")]),
    )
    out = _summary(ds, "amber")
    assert out.lstrip().startswith("## Checks in warning")


def test_green_checks_are_never_listed():
    ds = _dataset(
        ("a", [_check("unique_dbt", "Duplicate rate", "Must be unique.", "red"),
               _check("not_null_dbt", "Null rate", "Fine.", "green")]),
    )
    assert "Fine." not in _summary(ds)


def test_a_retired_check_is_never_listed_even_when_not_green():
    ds = _dataset(
        ("a", [_check("unique_dbt", "Duplicate rate", "Must be unique.", "red", retired=True)]),
    )
    assert _summary(ds) == ""


def test_nothing_is_capped_or_truncated():
    """Keith's own call over a 'and N more' cap: a genuinely broken
    dataset produces a long ticket, and hiding the tail hides it from
    the one person who opened the ticket to fix it."""
    ds = _dataset(*[
        (f"col_{i}", [_check("not_null_dbt", f"Check {i}", f"Sentence {i}.", "red")])
        for i in range(30)
    ])
    out = _summary(ds)
    for i in range(30):
        assert f"Sentence {i}." in out
    assert "more" not in out.lower().split("## ")[-1].replace("columns", "")


def test_the_contributor_note_never_reaches_a_ticket():
    ds = _dataset(
        ("a", [_check("unique_dbt", "Duplicate rate", "Must be unique.", "red",
                      technical_note="holds by construction, see the generator")]),
    )
    assert "by construction" not in _summary(ds)


def test_the_self_evident_sentinel_never_reaches_a_ticket():
    """It is not rendered because failure_indicates is not rendered at
    all - which is the point. Choosing name+description removed the whole
    class of "did this consumer remember to trim and compare" bug that
    210 trailing newlines had been waiting for."""
    ds = _dataset(
        ("a", [_check("unique_dbt", "Duplicate rate", "Must be unique.", "red",
                      failure_indicates="self-evident")]),
    )
    assert "self-evident" not in _summary(ds)


class TestCheckUrl:
    def test_it_matches_the_dashboards_own_path_shape(self):
        url = check_url("registry-services", "civil-registration",
                        "birth-registrations", "sex", "not_null_dbt")
        assert url == (DASHBOARD_BASE_URL + "#/agency/registry-services/collection/"
                       "civil-registration/dataset/birth-registrations/column/sex/"
                       "check/not_null_dbt")

    def test_it_encodes_a_pseudo_column_name_with_spaces_and_brackets(self):
        """The table-level pseudo-columns really are named "(table-level
        checks)", so this is a live case, not a hypothetical."""
        url = check_url("a", "b", "c", "(table-level checks)", "k")
        assert "/column/%28table-level%20checks%29/check/k" in url
        assert " " not in url

    def test_it_is_absolute_because_a_ticket_is_read_on_github(self):
        assert check_url("a", "b", "c", "d", "e").startswith("https://")


class TestAgainstTheRealCommittedDashboard:
    """Asserts a property that holds whatever happens to be failing
    today, rather than today's failures."""

    def test_every_link_it_generates_points_at_a_check_that_really_exists(self):
        from qa_tools.common.dataset_status import dataset_status
        from qa_tools.common.ticket_sync import _load_scopes

        checked = 0
        for scope, ds in _load_scopes():
            status = dataset_status(ds)
            if status == "green":
                continue
            out = build_check_summary(ds, status, scope.agency_id,
                                      scope.collection_id, scope.id)
            real_keys = {ck["key"] for col in ds["columns"]
                         for ck in col["checks"] if ck.get("key")}
            for line in out.splitlines():
                for part in line.split("/check/")[1:]:
                    key = part.split(")")[0]
                    assert key in real_keys, f"{scope.id}: {key} is not a real check key"
                    checked += 1
        assert checked > 0, "no non-green dataset to check against"

    def test_no_authored_sentence_reaches_a_ticket_with_stray_whitespace(self):
        """REQ-GHUB-027's whitespace fix, asserted at the layer that
        would have shown it. Fails against the pre-fix parser, where 210
        sentinels and 40 contract descriptions carried a trailing
        newline."""
        for path in ("reports/birth_registrations_dashboard.json",
                     "reports/child_protection_dashboard.json"):
            doc = json.loads((ROOT / path).read_text())
            stack = [doc]
            while stack:
                node = stack.pop()
                if isinstance(node, dict):
                    for key in ("name", "description", "failure_indicates"):
                        value = node.get(key)
                        if isinstance(value, str):
                            assert value == value.strip(), f"{path}: {key} is {value!r}"
                    stack.extend(node.values())
                elif isinstance(node, list):
                    stack.extend(node)


def test_a_placeholder_row_for_a_column_with_no_rule_is_never_listed():
    """The CP builder emits 11 of these, for columns no tool defines a
    rule against. They carry no key, name or description. They are green
    today, so a status filter alone would also exclude them - but "no
    check exists here" is not a passing check, and a ticket saying it
    failed would be nonsense."""
    ds = _dataset(("placement_end", [{
        "current": 1, "current_status": "red", "warn": None, "fail": None,
        "note": "Neither the ODCS contract nor the Soda/dbt check files "
                "define a rule for this column today",
    }]))
    assert _summary(ds) == ""
