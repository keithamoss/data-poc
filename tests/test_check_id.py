"""Tests for qa_tools/common/check_id.py - the check_id grammar
(REQ-QAC-023).

The grammar existed before this module, but only in prose: Thread D
described it, and every reader that needed one piece of a check_id took
that piece by splitting on dots and indexing. Nothing could check that
an authored id matched, and nothing did.
"""
from __future__ import annotations

import pytest

from qa_tools.common import check_id as ci
from qa_tools.common import validate_check_lifecycle as vcl

_REAL = ("data-asset-1.registry-services.civil-registration.birth-registrations"
         ".registration_number.unique_dbt")
_TABLE_LEVEL = ("data-asset-1.child-protection-family-support.child-protection.cp-carers"
                ".rowCount_datacontract")


def test_parses_a_real_check_id_into_named_segments():
    c = ci.parse(_REAL)
    assert c.data_asset == "data-asset-1"
    assert c.agency == "registry-services"
    assert c.collection == "civil-registration"
    assert c.dataset == "birth-registrations"
    assert c.column == "registration_number"
    assert c.check_name == "unique"
    assert c.tool == "dbt"


def test_the_grammar_carries_no_table_segment():
    """REQ-QAC-039 dropped it, and it is worth asserting rather than
    inferring from the test above: the old segment named the dbt STAGING
    MODEL (stg_birth_registrations), so every check - including the
    Soda, datacontract-cli and Evidently ones with no staging model -
    carried one tool's vocabulary in a tool-neutral identifier."""
    assert "table" not in ci.SEGMENT_NAMES
    assert not hasattr(ci.parse(_REAL), "table")


def test_a_table_level_check_has_no_column_rather_than_a_guessed_one():
    """The optional segment is what makes 5- and 6-segment ids ambiguous
    by dot-counting alone. Anchoring the tail on a known tool suffix is
    what resolves it - so a row count reports column None, not the table
    name shifted into the column slot."""
    c = ci.parse(_TABLE_LEVEL)
    assert c.column is None
    assert c.dataset == "cp-carers"
    assert c.check_name == "rowCount"
    assert c.tool == "datacontract"


@pytest.mark.parametrize("bad", [
    "",
    "not-a-check-id",
    "data-asset-1.agency.collection.dataset.column.unique_mystery",  # unknown tool
    "data-asset-1.agency.dataset.unique_dbt",                        # too few segments
    "data-asset-1.a.b.c.d.e.f.unique_dbt",                           # too many
])
def test_a_malformed_check_id_raises_and_names_itself(bad):
    with pytest.raises(ci.InvalidCheckIdError) as e:
        ci.parse(bad)
    assert repr(bad) in str(e.value), "the error must name the offending id"


def test_every_real_check_id_in_this_repo_matches_the_grammar():
    """The grammar is only worth having if it describes what is actually
    authored. This asserts against every real check definition across all
    four tools and both datasets, not a fixture."""
    ids = [c.check_id for c in vcl.collect_checks(None)]
    assert len(ids) > 200, "collect_checks() returned suspiciously few checks"
    assert ci.validate_grammar(ids) == []


def test_no_two_real_checks_collide_on_the_url_segment():
    assert ci.validate_tail_uniqueness([c.check_id for c in vcl.collect_checks(None)]) == []


def test_a_tail_collision_is_reported_even_when_both_ids_are_unique():
    """The reason this rule exists at all. Both ids below are globally
    unique - they differ in their data_asset segment - so the existing
    duplicate-check_id scan passes them. A dashboard URL carries no
    data_asset segment, so both resolve to the same place and whichever
    the lookup found first would silently win.

    Before REQ-QAC-039 this test used two ids differing only by TABLE,
    which was the same point made with the segment that has since gone."""
    errors = ci.validate_tail_uniqueness([
        "data-asset-1.a.coll.ds.col.unique_dbt",
        "data-asset-2.a.coll.ds.col.unique_dbt",
    ])
    assert len(errors) == 1
    assert "'ds'" in errors[0] and "unique_dbt" in errors[0]


def test_two_checks_differing_only_by_dataset_do_not_collide():
    """The rule is scoped to one dataset and column, deliberately - the
    same check name on two different datasets is normal and must not be
    reported."""
    assert ci.validate_tail_uniqueness([
        "data-asset-1.a.coll.ds_one.col.unique_dbt",
        "data-asset-1.a.coll.ds_two.col.unique_dbt",
    ]) == []


def test_two_checks_differing_only_by_collection_do_not_collide():
    """The collection segment REQ-QAC-039 added is part of the URL, so
    it separates two otherwise-identical tails the same way dataset
    does."""
    assert ci.validate_tail_uniqueness([
        "data-asset-1.a.coll_one.ds.col.unique_dbt",
        "data-asset-1.a.coll_two.ds.col.unique_dbt",
    ]) == []


def test_a_column_segment_disagreeing_with_its_attachment_is_an_error():
    errors = ci.validate_column_matches([(_REAL, "some_other_column")])
    assert len(errors) == 1
    assert "registration_number" in errors[0] and "some_other_column" in errors[0]


def test_a_table_level_rule_is_not_reported_as_a_column_mismatch():
    assert ci.validate_column_matches([(_TABLE_LEVEL, None)]) == []


def test_every_real_contract_rule_sits_under_the_column_its_id_names():
    """AC5, against the real contracts. This is the assertion that makes
    'the column comes from schema structure' true rather than merely
    intended - the id and the attachment were free to disagree before,
    and nothing would have said so."""
    from qa_tools.common.check_lifecycle import contract_rule_attachments
    for path in ("contract/bdm-birth-registrations-contract.yaml",
                 "contract/child-protection-contract.yaml"):
        assert ci.validate_column_matches(contract_rule_attachments(path)) == [], path


def test_the_grammar_is_built_from_one_segment_list():
    """The KNOWN GAP in this module's own docstring: there is no
    `collection` segment, and closing that is real scheduled work which
    will change the grammar. It has to be one edit, so this asserts the
    pattern is derived from `_SEGMENTS` rather than hand-written
    alongside it."""
    assert all(name in ci._PATTERN.groupindex for name, _ in ci._SEGMENTS)
    assert ci.SEGMENT_NAMES[-2:] == ("check_name", "tool")


class TestHierarchyAgreement:
    """REQ-QAC-039's fourth rule. Grammar validation proves an id is
    SHAPED right; this proves it MEANS something - that the dataset
    exists and that the agency and collection it claims are the ones
    that dataset actually sits under. An id that validates and resolves
    to nothing is worse than one that fails, because it looks resolved.
    """

    def test_every_real_check_id_agrees_with_the_hierarchy(self):
        ids = [c.check_id for c in vcl.collect_checks(None)]
        assert len(ids) > 200, "collect_checks() returned suspiciously few checks"
        assert ci.validate_hierarchy_agreement(ids) == []

    def test_a_collection_the_dataset_does_not_sit_under_is_an_error(self):
        errors = ci.validate_hierarchy_agreement([
            "data-asset-1.registry-services.child-protection.birth-registrations.c.unique_dbt"])
        assert len(errors) == 1
        assert "civil-registration" in errors[0]

    def test_an_agency_the_dataset_does_not_sit_under_is_an_error(self):
        errors = ci.validate_hierarchy_agreement([
            "data-asset-1.child-protection-family-support.civil-registration"
            ".birth-registrations.c.unique_dbt"])
        assert len(errors) == 1
        assert "registry-services" in errors[0]

    def test_a_dataset_the_hierarchy_does_not_define_is_named(self):
        errors = ci.validate_hierarchy_agreement([
            "data-asset-1.registry-services.civil-registration.birth_registrations.c.unique_dbt"])
        assert len(errors) == 1
        assert "birth_registrations" in errors[0]

    def test_a_foreign_data_asset_is_an_error(self):
        """The segment exists so ids stay unique across several assets
        sharing one set of config files - so an id from another asset
        appearing in THIS deployment's checks is a real mistake, not a
        harmless label."""
        errors = ci.validate_hierarchy_agreement([
            "data-asset-9.registry-services.civil-registration.birth-registrations.c.unique_dbt"])
        assert len(errors) == 1
        assert "data-asset-9" in errors[0]

    def test_a_malformed_id_is_left_to_the_grammar_rule(self):
        """Reporting the same id twice, once per rule, makes a fixing
        session read two lists to find one problem."""
        assert ci.validate_hierarchy_agreement(["not-a-check-id"]) == []
