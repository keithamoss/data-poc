"""Every singular dbt test a collection's schema declares has a home table in
its adapter's DbtSpec.singular_home - the collections gate's refusal, found
without a database (a defect found building REQ-QAC-350, 2026-11-18: a schema
naming `contact_in_its_week` with no home passed every gate, and the first run
of it crashed in dbt-core with UnknownCheck).
"""
from __future__ import annotations

import dataclasses

import pytest

from qa_tools import collections as registry
from qa_tools.common import validate_collections


def _without_home(monkeypatch, collection_id: str, test_name: str):
    real = registry.adapter(collection_id)
    home = {k: v for k, v in real.dbt.singular_home.items() if k != test_name}
    assert home != real.dbt.singular_home, "test precondition - the test has a home today"
    patched = dataclasses.replace(real, dbt=dataclasses.replace(real.dbt, singular_home=home))
    original = registry.adapter
    monkeypatch.setattr(registry, "adapter",
                        lambda c: patched if getattr(c, "id", c) == collection_id else original(c))


@pytest.mark.asset("daily")
def test_the_real_assets_singular_tests_all_have_a_home():
    assert validate_collections.singular_home_problems() == []


@pytest.mark.asset("daily")
def test_a_singular_test_without_a_home_is_refused_by_name(monkeypatch):
    _without_home(monkeypatch, "civil-registration", "multiple_birth_sibling")
    problems = validate_collections.singular_home_problems()
    assert len(problems) == 1, problems
    assert "multiple_birth_sibling" in problems[0] and "civil-registration" in problems[0], problems
    assert "singular_home" in problems[0], problems


@pytest.mark.asset("quarterly")
def test_a_home_that_is_not_one_of_its_tables_is_refused(monkeypatch):
    real = registry.adapter("emergency-department")
    patched = dataclasses.replace(real, dbt=dataclasses.replace(
        real.dbt, singular_home={**real.dbt.singular_home, "a_rule": "no_such_table"}))
    original = registry.adapter
    monkeypatch.setattr(registry, "adapter",
                        lambda c: patched if getattr(c, "id", c) == "emergency-department"
                        else original(c))
    problems = validate_collections.singular_home_problems()
    assert any("no_such_table" in p for p in problems), problems


pytestmark = pytest.mark.asset("daily")
