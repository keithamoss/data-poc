"""What a linkage product links is declared once and gated (REQ-QAC-330
criteria 5 and 6; REQ-QAC-333 criteria 3 and 8). Each test copies the real
contract folder, changes one thing, and asks the gate - the collections gate
calls the same function. The real files are untouched."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from qa_tools.common import linked_datasets

REAL = Path(__file__).resolve().parent.parent


@pytest.fixture
def repo(tmp_path):
    shutil.copytree(REAL / "contract", tmp_path / "contract")
    return tmp_path


def _asset(repo):
    return repo / "contract" / "data-asset.yaml"


def _linked(doc):
    for agency in doc["hierarchy"]["agencies"]:
        for coll in agency["collections"]:
            for ds in coll["datasets"]:
                if ds.get("linked_datasets"):
                    return ds["linked_datasets"]
    raise AssertionError("precondition: a dataset declares linked_datasets")


def _edit(repo, change):
    doc = yaml.safe_load(_asset(repo).read_text())
    change(_linked(doc))
    _asset(repo).write_text(yaml.safe_dump(doc, sort_keys=False))
    return "\n".join(linked_datasets.problems(repo))


def test_the_real_configuration_passes():
    assert linked_datasets.problems(REAL) == []


def test_the_linked_list_is_the_hierarchys():
    """Criterion 5: the one place - read through the hierarchy."""
    from qa_tools.common import hierarchy

    linked = hierarchy.dataset("linkage-keys").linked
    assert ("cp-clients", "DOC_CLIENTS", ("cp_client_id",)) in linked
    assert ("ed-presentations", "EDDC_PRESENTATION", ("presentation_id",)) in linked


class TestCriterionSix:
    def test_a_dataset_not_in_the_hierarchy(self, repo):
        text = _edit(repo, lambda ls: ls.append(
            {"dataset": "cp-nope", "code": "X", "id_columns": ["a"]}))
        assert "cp-nope" in text and "not in the hierarchy" in text

    def test_a_dataset_on_no_shared_calendar(self, repo):
        text = _edit(repo, lambda ls: ls.append(
            {"dataset": "birth-registrations", "code": "BR", "id_columns": ["registration_number"]}))
        assert "birth-registrations" in text and "calendar" in text

    def test_a_source_column_its_contract_does_not_declare(self, repo):
        def change(ls):
            ls[0]["id_columns"] = ["no_such_column"]
        text = _edit(repo, change)
        assert "cp-clients" in text and "no_such_column" in text

    def test_more_identifier_columns_than_the_contracts_id_n(self, repo):
        """The contract declares id_1 and id_2; three real source columns
        exceed it - and the message is that one, not any other naming id_1."""
        assert "linkage-keys links 'cp-clients' by" not in "\n".join(
            linked_datasets.problems(repo)), "precondition: the real mapping fits"

        def change(ls):
            ls[0]["id_columns"] = ["cp_client_id", "given_name", "family_name"]
        text = _edit(repo, change)
        assert ("linkage-keys links 'cp-clients' by 3 identifier columns, more than the "
                "contract's id_1 to id_2.") in text.splitlines(), text

    def test_a_dataset_naming_no_calendar(self, repo):
        cal_path = repo / "contract" / "calendar.yaml"
        cal = yaml.safe_load(cal_path.read_text())
        entry = next(d for d in cal["datasets"] if d["id"] == "cp-clients")
        entry["no_calendar"] = True
        cal_path.write_text(yaml.safe_dump(cal, sort_keys=False))
        text = "\n".join(linked_datasets.problems(repo))
        assert ("linkage-keys links 'cp-clients', which names no calendar, so it has no "
                "period to be read for.") in text.splitlines(), text

    def test_two_datasets_with_one_code(self, repo):
        def change(ls):
            ls[1]["code"] = ls[0]["code"]
        text = _edit(repo, change)
        assert "DOC_CLIENTS" in text and "two" in text


class TestTheHandWrittenChecksAgreeWithTheMapping:
    """REQ-QAC-333 criteria 3 and 8."""

    def _soda(self, repo):
        return repo / "contract" / "department-of-health" / "linkage-products-soda-checks.yml"

    def test_a_check_stating_another_code_is_refused_naming_both(self, repo):
        path = self._soda(repo)
        path.write_text(path.read_text().replace("linkage_code: DOC_CLIENTS", "linkage_code: DOC_CLIENT", 1))
        text = "\n".join(linked_datasets.problems(repo))
        assert "DOC_CLIENT" in text and "DOC_CLIENTS" in text and "cp-clients" in text
        assert "referential_soda" in text

    def test_a_check_stating_another_identifier_count_is_refused(self, repo):
        path = self._soda(repo)
        path.write_text(path.read_text().replace("id_counts: {DOC_CLIENTS: 1,", "id_counts: {DOC_CLIENTS: 2,", 1))
        text = "\n".join(linked_datasets.problems(repo))
        assert "expected_ids_soda" in text and "cp-clients" in text and "2" in text

    def test_a_linked_dataset_without_its_coverage_check_is_refused(self, repo):
        path = self._soda(repo)
        doc = yaml.safe_load(path.read_text())
        key = next(k for k in doc)
        doc[key] = [c for c in doc[key]
                    if "cp_clients_coverage_percent" not in c]
        path.write_text(yaml.safe_dump(doc, sort_keys=False))
        text = "\n".join(linked_datasets.problems(repo))
        assert "cp-clients" in text and "coverage" in text

    def test_a_check_naming_a_dataset_not_linked_is_refused(self, repo):
        path = self._soda(repo)
        path.write_text(path.read_text().replace("linked_dataset: ed-presentations", "linked_dataset: cp-carers", 1))
        text = "\n".join(linked_datasets.problems(repo))
        assert "cp-carers" in text and "not declared as linked" in text
