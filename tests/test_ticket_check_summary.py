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


class TestAgainstTheRealCommittedCheckDefinitions:
    """Reads the committed check definitions, never reports/*.json.

    The first version of this class read the built dashboard JSON, and
    that was wrong in a way local runs could not show: reports/ is
    gitignored, so it exists on a machine that has just built it and
    not in a fresh CI checkout. It passed here and failed on GitHub
    with a FileNotFoundError, which is the exact shape CLAUDE.md's own
    "a passing local pytest is not evidence CI is green" bullet
    describes.

    Reading the definitions is also the better layer for both claims
    below: contract/, dbt_project/ and the Soda YAML are committed, and
    they are where the values these tests are about actually originate.
    """

    def test_no_authored_check_text_carries_stray_whitespace(self):
        """REQ-GHUB-027's whitespace fix at its source. Fails against the
        pre-fix parser, where 210 self-evident sentinels and 40 ODCS
        descriptions arrived with a trailing newline from their YAML
        block scalars."""
        import qa_tools.common.validate_check_lifecycle as v

        offenders = [
            (c.check_id, field, value)
            for c in v.collect_checks(None)
            for field, value in (("name", c.name), ("description", c.description),
                                 ("failure_indicates", c.failure_indicates),
                                 ("technical_note", c.technical_note))
            if isinstance(value, str) and value != value.strip()
        ]
        assert offenders == []

    def test_the_self_evident_sentinel_is_recognised_on_every_check_that_uses_it(self):
        """The consequence that made the whitespace matter. Before the
        fix only 3 of 213 matched the sentinel exactly, so any consumer
        comparing without trimming would have printed the literal word
        into a ticket."""
        import qa_tools.common.validate_check_lifecycle as v
        from qa_tools.common.check_lifecycle import SELF_EVIDENT, is_self_evident

        sentinels = [c for c in v.collect_checks(None) if is_self_evident(c.failure_indicates)]
        assert sentinels, "expected some checks to declare their failure cause self-evident"
        assert all(c.failure_indicates == SELF_EVIDENT for c in sentinels)

    def test_every_real_check_id_yields_a_tool_ref_matching_its_url_key(self):
        """The property the ticket links depend on, asserted across every
        real check rather than a sample: what a ticket prints and what
        the URL carries are the same string, tool moved to the front."""
        import qa_tools.common.validate_check_lifecycle as v
        from pipeline.dashboard_check_labels import tool_ref, url_key

        checks = v.collect_checks(None)
        assert len(checks) > 200, "expected the real corpus, not a fixture"
        for check in checks:
            key, ref = url_key(check.check_id), tool_ref(check.check_id)
            tool, terse = ref.split(":", 1)
            assert key == f"{terse}_{tool}", check.check_id
            assert check_url("a", "b", "c", "col", key).endswith(f"/check/{key}")
