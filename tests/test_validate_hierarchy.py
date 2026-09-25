"""Tests for qa_tools/common/validate_hierarchy.py (REQ-QAC-039).

The gate that stops the dataset contracts drifting from the one
hierarchy again. Its value is entirely in what it REJECTS, so most of
these build a deliberately wrong contract and assert it is caught -
including, first, the three real drifts that existed on 2026-09-23 and
that nothing had noticed.
"""
from __future__ import annotations

import pytest
import yaml

from qa_tools.common import hierarchy, validate_hierarchy


@pytest.fixture(autouse=True)
def _clear_cache():
    hierarchy._load.cache_clear()
    yield
    hierarchy._load.cache_clear()


def _contract(tmp_path, monkeypatch, filename, doc, describes):
    """One contract, in a directory of its own, as the only thing the
    gate looks at.

    Patches `contracts()` rather than a `CONTRACTS` constant since
    2026-09-25: the list is derived from the hierarchy now rather than
    hand-maintained (post-build-review #36). Pinning it here is still
    right - these tests are about what the gate REJECTS in a contract
    file, not about which files it finds."""
    (tmp_path / filename).write_text(yaml.safe_dump(doc))
    monkeypatch.setattr(validate_hierarchy, "CONTRACT_DIR", tmp_path)
    monkeypatch.setattr(validate_hierarchy, "contracts",
                         lambda: ((filename, describes),))


class TestTheRealRepo:
    def test_the_real_contracts_agree_with_the_real_hierarchy(self):
        assert validate_hierarchy.validate() == []

    def test_it_reports_a_count_of_what_it_checked(self, capsys):
        assert validate_hierarchy.main() == 0
        assert "in agreement" in capsys.readouterr().out


class TestTheDriftsThatActuallyHappened:
    """The three real disagreements found on 2026-09-23. Each is
    reproduced rather than described, so this file is evidence the gate
    would have caught them rather than an assertion that it would."""

    def test_a_dataset_contract_id_that_is_not_the_dataset_id(self, tmp_path, monkeypatch):
        entry = hierarchy.dataset("birth-registrations")
        _contract(tmp_path, monkeypatch, "c.yaml", {
            "id": "bdm-birth-registrations",  # the real pre-fix value
            "name": entry.dataset_name, "domain": entry.agency_id,
        }, "birth-registrations")
        errors = validate_hierarchy.validate()
        assert len(errors) == 1
        assert "id is 'bdm-birth-registrations'" in errors[0]
        assert "'birth-registrations'" in errors[0]

    def test_a_domain_that_names_neither_the_collection_nor_the_agency(self, tmp_path, monkeypatch):
        _contract(tmp_path, monkeypatch, "c.yaml", {
            "id": "child-protection", "name": "Child Protection",
            "domain": "child-and-family-safety",  # the real pre-fix value
        }, "child-protection")
        errors = validate_hierarchy.validate()
        assert len(errors) == 1
        assert "child-and-family-safety" in errors[0]
        assert "child-protection-family-support" in errors[0]

    def test_a_display_name_that_drifted_from_the_hierarchy(self, tmp_path, monkeypatch):
        entry = hierarchy.dataset("birth-registrations")
        _contract(tmp_path, monkeypatch, "c.yaml", {
            "id": entry.dataset_id,
            "name": "Birth Registrations Feed",  # the real pre-fix value
            "domain": entry.agency_id,
        }, "birth-registrations")
        errors = validate_hierarchy.validate()
        assert len(errors) == 1
        assert "name is 'Birth Registrations Feed'" in errors[0]


class TestItFailsUsefully:
    def test_every_wrong_field_is_reported_not_just_the_first(self, tmp_path, monkeypatch):
        # An author fixing a contract should see all three in one run,
        # the same reasoning validate_requirements.py's own docstring
        # gives for catching per entry.
        _contract(tmp_path, monkeypatch, "c.yaml", {
            "id": "wrong", "name": "Wrong", "domain": "wrong",
        }, "birth-registrations")
        assert len(validate_hierarchy.validate()) == 3

    def test_the_error_says_not_to_fix_both_sides_independently(self, tmp_path, monkeypatch):
        # Fixing the contract AND the hierarchy to match each other is
        # how two wrong values become consistent and stay wrong.
        _contract(tmp_path, monkeypatch, "c.yaml", {"id": "x"}, "birth-registrations")
        assert any("not both independently" in e for e in validate_hierarchy.validate())

    def test_a_missing_contract_file_is_an_error_not_a_skip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(validate_hierarchy, "CONTRACT_DIR", tmp_path)
        monkeypatch.setattr(validate_hierarchy, "contracts",
                             lambda: (("gone.yaml", "birth-registrations"),))
        assert validate_hierarchy.validate() == ["gone.yaml: no such contract"]

    def test_a_contract_describing_something_the_hierarchy_lacks_is_named(self, tmp_path, monkeypatch):
        _contract(tmp_path, monkeypatch, "c.yaml", {"id": "x"}, "not-a-real-thing")
        errors = validate_hierarchy.validate()
        assert len(errors) == 1
        assert "not-a-real-thing" in errors[0]

    def test_main_returns_nonzero_and_writes_to_stderr(self, tmp_path, monkeypatch, capsys):
        _contract(tmp_path, monkeypatch, "c.yaml", {"id": "x"}, "birth-registrations")
        assert validate_hierarchy.main() == 1
        assert "FAILED" in capsys.readouterr().err


class TestCollectionScopedContracts:
    def test_a_collection_contract_resolves_to_its_collection_not_a_dataset(self, tmp_path, monkeypatch):
        # Child Protection's contract describes six datasets at once,
        # so it is held to the COLLECTION's id and name - the asymmetry
        # that made this rule need stating at all.
        _contract(tmp_path, monkeypatch, "c.yaml", {
            "id": "child-protection", "name": "Child Protection",
            "domain": "child-protection-family-support",
        }, "child-protection")
        assert validate_hierarchy.validate() == []


class TestArrivalPatternsNameRealDatasets:
    """REQ-GEN-043 criterion 3: a file's own dataset is derivable from
    its name through that dataset's configured pattern - so a pattern
    naming a dataset that does not exist derives nothing.

    Added after the block turned out to have drifted in exactly the way
    this gate exists to catch, and to have survived REQ-QAC-039's own
    sweep the same morning because nothing looked INSIDE a
    customProperty's value.
    """

    def _doc(self, dataset_ids):
        return {"id": "birth-registrations", "name": "Birth Registrations",
                "domain": "registry-services",
                "customProperties": [{"property": "arrivalPattern", "value": [
                    {"type": "single_file", "keyPattern": f"x/{i}.csv", "dataset_id": d}
                    for i, d in enumerate(dataset_ids)]}]}

    def test_the_real_contracts_name_only_real_datasets(self):
        assert validate_hierarchy.validate() == []

    def test_the_real_pre_fix_bdm_value_is_caught(self, tmp_path, monkeypatch):
        """The id corrected hours earlier, still sitting in this block."""
        _contract(tmp_path, monkeypatch, "c.yaml",
                   self._doc(["bdm-birth-registrations"]), "birth-registrations")
        errors = validate_hierarchy.validate()
        assert len(errors) == 1
        assert "bdm-birth-registrations" in errors[0]

    def test_the_real_pre_fix_cp_value_is_caught(self, tmp_path, monkeypatch):
        """Stale AND wrong in kind - it named the COLLECTION where a
        per-file dataset belongs."""
        _contract(tmp_path, monkeypatch, "c.yaml",
                   self._doc(["child-protection-casework"]), "birth-registrations")
        assert any("child-protection-casework" in e for e in validate_hierarchy.validate())

    def test_every_offending_pattern_is_reported_not_just_the_first(self, tmp_path, monkeypatch):
        _contract(tmp_path, monkeypatch, "c.yaml",
                   self._doc(["nope-one", "nope-two", "cp-clients"]), "birth-registrations")
        assert len(validate_hierarchy.validate()) == 2

    def test_a_contract_with_no_arrival_pattern_is_fine(self, tmp_path, monkeypatch):
        """Not every dataset has one yet, and absence is not drift."""
        _contract(tmp_path, monkeypatch, "c.yaml",
                   {"id": "birth-registrations", "name": "Birth Registrations",
                    "domain": "registry-services"}, "birth-registrations")
        assert validate_hierarchy.validate() == []


class TestTheContractListIsDerivedNotMaintained:
    """post-build-review #36's structural half.

    `CONTRACTS` was a hand-maintained tuple of (filename, what it
    describes) - restating a relation the hierarchy already holds, since
    every dataset declares its own `contract:`. Two places to edit when
    a third collection arrives, and the failure mode of forgetting one
    is SILENT: the new contract simply never gets checked, by the gate
    whose whole job is noticing that a contract and the tree disagree.
    """

    def test_it_covers_every_contract_the_hierarchy_names(self):
        named = {d.contract for d in hierarchy.all_datasets()}
        covered = {filename for filename, _ in validate_hierarchy.contracts()}
        assert named == covered, (
            f"the gate checks {covered} but the hierarchy names {named}")

    def test_a_collection_scoped_contract_resolves_to_its_collection(self):
        """Shared by several datasets, so it describes what they have in
        common - which is the collection, not any one of them."""
        by_file = dict(validate_hierarchy.contracts())
        assert by_file["child-protection-contract.yaml"] == "child-protection"

    def test_a_dataset_scoped_contract_resolves_to_that_dataset(self):
        by_file = dict(validate_hierarchy.contracts())
        assert by_file["bdm-birth-registrations-contract.yaml"] == "birth-registrations"

    def test_a_contract_file_nothing_names_is_reported(self, tmp_path, monkeypatch):
        """The one thing deriving could have LOST. An orphan contract was
        never checked before either - nobody had added it to the tuple -
        so this is coverage the hand-maintained list did not have."""
        (tmp_path / "orphan-contract.yaml").write_text("id: nobody\n")
        for name in {d.contract for d in hierarchy.all_datasets()}:
            (tmp_path / name).write_text(
                (validate_hierarchy.CONTRACT_DIR / name).read_text())
        monkeypatch.setattr(validate_hierarchy, "CONTRACT_DIR", tmp_path)
        errors = validate_hierarchy.validate()
        assert any("orphan-contract.yaml" in e for e in errors), errors

    def test_the_real_repo_still_passes(self):
        assert validate_hierarchy.validate() == []
