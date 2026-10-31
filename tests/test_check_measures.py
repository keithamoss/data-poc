"""REQ-DASH-228: every rule kind declared in committed configuration has a
measure, so a new kind is noticed rather than charted as 'Value'.

Reads configuration, never recorded results, so it sits in CI's fast half."""

from pipeline.dashboard_check_labels import MEASURES, measure, tool_ref
from qa_tools.common import validate_check_lifecycle


def _declared_kinds() -> set[str]:
    return {
        tool_ref(m.check_id)
        for m in validate_check_lifecycle.collect_checks(None)
        if not m.retired_as_of
    }


def test_the_configuration_declares_rule_kinds():
    assert _declared_kinds(), "no rule kinds found - the test would pass on nothing"


def test_every_declared_rule_kind_names_its_measure():
    missing = sorted(_declared_kinds() - MEASURES.keys())
    assert not missing, (
        "rule kinds declared in configuration with no entry in "
        f"pipeline.dashboard_check_labels.MEASURES: {missing}"
    )


def test_measure_joins_the_phrase_and_the_unit():
    cid = "data-asset-1.registry-services.civil-registration.birth-registrations.mother_surname.not_null_dbt"
    assert measure(cid, "count") == "Rows with no value (count)"


def test_an_unmapped_kind_falls_back_to_the_unit_alone():
    cid = "data-asset-1.registry-services.civil-registration.birth-registrations.mother_surname.brand_new_soda"
    assert measure(cid, "%") == "Value (%)"
