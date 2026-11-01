"""REQ-DASH-228: every rule kind declared in committed configuration has a
measure, so a new kind is noticed rather than charted as 'Value'.

REQ-DASH-299 criterion 1: a check may DECLARE its own phrase in its check
file (`measures:`), read ahead of MEASURES for its kind - so a kind is named
either by MEASURES or by every check of it declaring one.

Reads configuration, never recorded results, so it sits in CI's fast half."""

import pytest

import re

from pipeline.dashboard_check_labels import MEASURES, measure, measures_phrase, tool_ref
from qa_tools.common import validate_check_lifecycle


def _active():
    return [m for m in validate_check_lifecycle.collect_checks(None) if not m.retired_as_of]


def _declared_kinds() -> set[str]:
    return {tool_ref(m.check_id) for m in _active()}


def test_the_configuration_declares_rule_kinds():
    assert _declared_kinds(), "no rule kinds found - the test would pass on nothing"


def test_every_declared_rule_kind_names_its_measure():
    """MEASURES names the kind, or every check of it declares its own."""
    unnamed = sorted({tool_ref(m.check_id) for m in _active()
                      if not m.measures and tool_ref(m.check_id) not in MEASURES})
    assert not unnamed, (
        "rule kinds declared in configuration with no entry in "
        f"pipeline.dashboard_check_labels.MEASURES and no `measures:` on the check: {unnamed}"
    )


def test_measure_joins_the_phrase_and_the_unit():
    cid = "daily.registry-services.civil-registration.birth-registrations.mother_surname.not_null_dbt"
    assert measure(cid, "count") == "Rows with no value (count)"


def test_an_unmapped_kind_falls_back_to_the_unit_alone():
    cid = "daily.registry-services.civil-registration.birth-registrations.mother_surname.brand_new_soda"
    assert measure(cid, "%") == "Value (%)"
    assert measures_phrase(cid) is None


def test_a_declared_phrase_wins_over_the_kinds():
    cid = "daily.registry-services.civil-registration.birth-registrations.mother_surname.not_null_dbt"
    assert measure(cid, "count", "Mothers with no surname") == "Mothers with no surname (count)"
    assert measures_phrase(cid, "Mothers with no surname") == "Mothers with no surname"
    assert measures_phrase(cid, None) == "Rows with no value"


def test_each_geocoding_dataset_declares_its_four_phrases():
    """REQ-DASH-299 criterion 1: the three year checks and the share check,
    on each geocoding dataset - read from the check files, not from code."""
    by = {}
    for m in _active():
        parts = m.check_id.split(".")
        if parts[4] in ("census_year", "match_level") and parts[5] in (
                "missing_set_members_dbt", "duplicated_set_members_dbt",
                "unexpected_set_members_dbt", "value_share_soda"):
            by.setdefault(parts[3], {})[parts[5]] = m.measures
    assert len(by) >= 2, by
    for dataset, phrases in by.items():
        assert phrases == {
            "missing_set_members_dbt": "Missing census years",
            "duplicated_set_members_dbt": "Duplicated census years",
            "unexpected_set_members_dbt": "Unexpected census years",
            "value_share_soda": "Rows not geocoded",
        }, dataset


def test_no_census_or_geocoding_word_is_in_shared_code():
    """NFR 2: the words are on the checks, never in MEASURES."""
    said = " ".join(MEASURES.values())
    assert said
    assert not re.search(r"census|geocod", said, re.I), said


def test_the_cross_collection_kinds_read_as_siblings():
    """REQ-DASH-299 criterion 2 (Keith, 2026-10-31, Q11 a)."""
    assert MEASURES["soda:referential"] == "Rows matching no source record"
    assert MEASURES["soda:coverage"] == "Source records matched"


#: The data asset this module's tests act for, unless a test says otherwise
#: (C11, Keith 2026-11-02: every test module names its asset).
pytestmark = pytest.mark.asset("daily")
