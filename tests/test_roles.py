"""Roles, the three levels of assignment, and the data asset's manager
(REQ-GHUB-171).

The gate's half is tested against copies of the real contract/people.yaml
broken one way each; the decision half against the real file, through the
one implementation every route shares (filing_decisions.apply).
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from qa_tools.common import filing_decisions, people, validate_people

REAL = Path(__file__).resolve().parent.parent / "contract" / "people.yaml"
KEITH = "fpycnkgvmt@privaterelay.appleid.com"


def _problems(tmp_path, mutate):
    doc = yaml.safe_load(REAL.read_text())
    mutate(doc)
    path = tmp_path / "people.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False))
    return validate_people.problems(path)


class TestTheGate:
    def test_the_committed_file_passes(self):
        assert validate_people.problems(REAL) == []

    def test_an_undeclared_role_on_a_person_is_refused(self, tmp_path):
        """Criterion 1."""
        def mutate(doc):
            doc["people"][0]["roles"].append("manger")
        assert any("'manger'" in p for p in _problems(tmp_path, mutate))

    def test_an_undeclared_role_on_an_assignment_is_refused(self, tmp_path):
        def mutate(doc):
            doc["assignments"][1]["role"] = "auditor"
        assert any("'auditor'" in p for p in _problems(tmp_path, mutate))

    def test_a_file_declaring_no_roles_is_refused(self, tmp_path):
        def mutate(doc):
            doc.pop("roles")
        assert any("declares no `roles:`" in p for p in _problems(tmp_path, mutate))

    @pytest.mark.parametrize("levels", [{}, {"agency": "registry-services",
                                              "dataset": "cp-clients"}])
    def test_an_assignment_names_exactly_one_level(self, tmp_path, levels):
        """Criterion 2."""
        def mutate(doc):
            doc["assignments"].append({"person": KEITH, "role": "qa", **levels})
        assert any("exactly one" in p for p in _problems(tmp_path, mutate))

    def test_a_data_asset_assignment_names_this_asset(self, tmp_path):
        def mutate(doc):
            doc["assignments"][0]["data_asset"] = "some-other-asset"
        assert any("'some-other-asset'" in p for p in _problems(tmp_path, mutate))

    def test_no_real_asset_manager_fails_the_gate(self, tmp_path):
        """Criterion 6."""
        def mutate(doc):
            doc["assignments"] = [a for a in doc["assignments"] if "data_asset" not in a]
        assert any("data-asset level" in p for p in _problems(tmp_path, mutate))

    def test_a_placeholder_asset_manager_does_not_count(self, tmp_path):
        def mutate(doc):
            doc["assignments"][0]["person"] = "arthur.pendragon@example.com"
        assert any("data-asset level" in p for p in _problems(tmp_path, mutate))


class TestTheAssetManager:
    def test_keith_is_the_data_assets_manager(self):
        """Criteria 4 and 5."""
        assert [p["email"] for p in people.asset_managers()] == [KEITH]

    def test_an_agency_manager_is_not_the_asset_manager(self):
        """Criterion 4's second half: per-agency managers stay in force for
        their own agency, and are not the asset's."""
        config = people.parse_people_config()
        config = copy.deepcopy(config)
        config["asset_assignments"] = []
        assert people.asset_managers(config) == []
        keith = config["people"][KEITH]
        assert people.holds(keith, "manager", "agency", "registry-services", config)


class TestRequiringARole:
    """Criteria 3 and 7."""

    def test_the_asset_manager_passes(self):
        people.require_role(people.person_by_email(KEITH), "manager", people.DATA_ASSET)

    def test_someone_without_it_is_refused_naming_the_role_and_level(self):
        stranger = {"email": "someone@example.com", "name": "Someone"}
        with pytest.raises(people.RoleRefused) as refused:
            people.require_role(stranger, "manager", people.DATA_ASSET)
        assert "manager" in str(refused.value) and "data-asset level" in str(refused.value)

    def test_an_agency_role_is_for_its_own_agency_only(self):
        keith = people.person_by_email(KEITH)
        people.require_role(keith, "manager", "agency", "registry-services")
        with pytest.raises(people.RoleRefused) as refused:
            people.require_role(keith, "manager", "agency", "child-protection-family-support")
        assert "agency level for child-protection-family-support" in str(refused.value)

    def test_a_placeholder_is_refused(self):
        arthur = people.parse_people_config()["people"]["arthur.pendragon@example.com"]
        with pytest.raises(people.RoleRefused):
            people.require_role(arthur, "manager", "agency", "child-protection-family-support")

    def test_the_synthetic_actor_is_asset_manager_only_in_playback(self):
        actor = next(p for p in people.parse_people_config()["people"].values()
                     if people.is_synthetic(p))
        with pytest.raises(people.RoleRefused):
            people.require_role(actor, "manager", people.DATA_ASSET)
        with people.playback():
            people.require_role(actor, "manager", people.DATA_ASSET)

    def test_and_only_on_a_synthetic_asset(self, monkeypatch):
        monkeypatch.setattr(people, "_asset_is_synthetic", lambda: False)
        actor = next(p for p in people.parse_people_config()["people"].values()
                     if people.is_synthetic(p))
        with people.playback(), pytest.raises(people.RoleRefused):
            people.require_role(actor, "manager", people.DATA_ASSET)


class TestADecisionCanRequireARole:
    def test_the_shared_implementation_refuses_before_anything_else(self, monkeypatch):
        """Criterion 3 through REQ-GHUB-082's one implementation (NFR 1):
        a decision requiring the asset manager, raised by someone else, is
        refused before any database is touched."""
        monkeypatch.setitem(filing_decisions.REQUIRED_ROLE, filing_decisions.PROMOTE,
                            ("manager", people.DATA_ASSET))
        request = filing_decisions.Request(
            operation=filing_decisions.PROMOTE, dataset_id="cp-clients",
            actor={"email": "someone@example.com"}, reason="r", period="2026-Q1",
            supply="s", confirmed=True)

        def no_database(*a, **k):
            raise AssertionError("the role is checked before the database is opened")

        monkeypatch.setattr(filing_decisions.supply_db, "connect", no_database)
        with pytest.raises(people.RoleRefused):
            filing_decisions.apply(request, effective_at="2026-10-11T03:00:00+08:00")

    def test_no_decision_requires_one_yet(self):
        """REQ-PIPE-170's confirmation is the first; until it is built
        nothing in this table refuses anybody who could act before."""
        assert filing_decisions.REQUIRED_ROLE == {}
