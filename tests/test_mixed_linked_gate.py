"""A collection holds only source datasets or only derived ones (REQ-DASH-356
criterion 6): the period view sections the agencies list by whether a
collection's datasets declare linked_datasets, so a collection holding both
would sit under a heading that misdescribes it - `mothman check` fails it,
naming the collection and both datasets."""
from __future__ import annotations

import pytest

from asset_model import hierarchy
from qa_tools.common import validate_collections


def test_the_real_assets_mix_none():
    assert validate_collections.mixed_linked_problems() == []


def test_a_collection_holding_both_is_refused_by_name(monkeypatch):
    real = hierarchy.all_datasets()
    lp = [d for d in real if d.collection_id == "linkage-products"]
    assert any(d.linked for d in lp), "test precondition - Linkage Products links datasets"
    # linkage-keys, made a source dataset: no linked_datasets.
    import dataclasses

    mixed = [dataclasses.replace(d, linked=()) if d.dataset_id == "linkage-keys" else d
             for d in real]
    monkeypatch.setattr(hierarchy, "all_datasets", lambda: mixed)
    problems = validate_collections.mixed_linked_problems()
    assert len(problems) == 1, problems
    said = problems[0]
    assert "linkage-products" in said and "linkage-keys" in said, said
    assert any(d.dataset_id in said for d in lp if d.dataset_id != "linkage-keys"), said


pytestmark = pytest.mark.asset("quarterly")
