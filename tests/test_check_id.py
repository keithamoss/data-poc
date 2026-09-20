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

_REAL = "data-asset-1.registry-services.birth-registrations.stg_birth_registrations.registration_number.unique_dbt"
_TABLE_LEVEL = "data-asset-1.child-protection-family-support.cp-carers.stg_cp_carers.rowCount_datacontract"


def test_parses_a_real_check_id_into_named_segments():
    c = ci.parse(_REAL)
    assert c.data_asset == "data-asset-1"
    assert c.agency == "registry-services"
    assert c.dataset == "birth-registrations"
    assert c.table == "stg_birth_registrations"
    assert c.column == "registration_number"
    assert c.check_name == "unique"
    assert c.tool == "dbt"


def test_a_table_level_check_has_no_column_rather_than_a_guessed_one():
    """The optional segment is what makes 5- and 6-segment ids ambiguous
    by dot-counting alone. Anchoring the tail on a known tool suffix is
    what resolves it - so a row count reports column None, not the table
    name shifted into the column slot."""
    c = ci.parse(_TABLE_LEVEL)
    assert c.column is None
    assert c.table == "stg_cp_carers"
    assert c.check_name == "rowCount"
    assert c.tool == "datacontract"


@pytest.mark.parametrize("bad", [
    "",
    "not-a-check-id",
    "data-asset-1.agency.dataset.table.column.unique_mystery",   # unknown tool
    "data-asset-1.agency.dataset.unique_dbt",                    # too few segments
    "data-asset-1.a.b.c.d.e.f.unique_dbt",                       # too many
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
    unique - they differ in their table segment - so the existing
    duplicate-check_id scan passes them. A dashboard URL carries no table
    segment, so both resolve to the same place and whichever the lookup
    found first would silently win."""
    errors = ci.validate_tail_uniqueness([
        "data-asset-1.a.ds.table_one.col.unique_dbt",
        "data-asset-1.a.ds.table_two.col.unique_dbt",
    ])
    assert len(errors) == 1
    assert "table_one" in errors[0] and "table_two" in errors[0]


def test_two_checks_differing_only_by_dataset_do_not_collide():
    """The rule is scoped to one dataset and column, deliberately - the
    same check name on two different datasets is normal and must not be
    reported."""
    assert ci.validate_tail_uniqueness([
        "data-asset-1.a.ds_one.t.col.unique_dbt",
        "data-asset-1.a.ds_two.t.col.unique_dbt",
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
