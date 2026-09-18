"""Tests for qa_tools/common/people.py (running-thoughts.md #2, 2026-09-18
- "data-asset-level people/roles config"). Pure functions - plain fixture
YAML, no real gh/network."""
from __future__ import annotations

import textwrap

import pytest

from qa_tools.common import people as people_mod


def _write(tmp_path, content):
    path = tmp_path / "people.yaml"
    path.write_text(textwrap.dedent(content))
    return path


class TestParsePeopleConfig:
    def test_a_missing_file_returns_empty_config_rather_than_raising(self, tmp_path):
        config = people_mod.parse_people_config(tmp_path / "does-not-exist.yaml")
        assert config == {"people": {}, "agency_assignments": {}, "dataset_assignments": {}}

    def test_a_genuinely_empty_committed_file_also_returns_empty_config(self, tmp_path):
        path = _write(tmp_path, "people: []\nassignments: []\n")
        config = people_mod.parse_people_config(path)
        assert config == {"people": {}, "agency_assignments": {}, "dataset_assignments": {}}

    def test_parses_real_people_and_agency_and_dataset_assignments(self, tmp_path):
        path = _write(tmp_path, """
            people:
              - email: keith@example.com
                name: Keith Amoss
                nickname: Keith
                github: keithamoss
                roles: [qa, manager]
              - email: jane@example.com
                name: Jane Reviewer
                github: janereviewer
                roles: [peer_review]

            assignments:
              - agency: registry-services
                person: keith@example.com
                role: qa
              - dataset: cp-clients
                person: jane@example.com
                role: peer_review
        """)
        config = people_mod.parse_people_config(path)

        assert set(config["people"]) == {"keith@example.com", "jane@example.com"}
        assert config["agency_assignments"]["registry-services"][0]["github"] == "keithamoss"
        assert config["dataset_assignments"]["cp-clients"][0]["github"] == "janereviewer"

    def test_an_assignment_referencing_an_unknown_person_is_skipped_not_an_error(self, tmp_path):
        path = _write(tmp_path, """
            people: []
            assignments:
              - agency: registry-services
                person: nobody@example.com
                role: qa
        """)
        config = people_mod.parse_people_config(path)
        assert config["agency_assignments"] == {}


@pytest.fixture
def config():
    return {
        "people": {},
        "agency_assignments": {"registry-services": [{"email": "keith@example.com", "github": "keithamoss", "role": "qa"}]},
        "dataset_assignments": {"cp-clients": [{"email": "jane@example.com", "github": "janereviewer", "role": "peer_review"}]},
    }


class TestAssigneesFor:
    def test_dataset_level_assignment_wins_outright_over_agency_level(self, config):
        result = people_mod.assignees_for("cp-clients", "child-protection-family-support", config)
        assert [p["email"] for p in result] == ["jane@example.com"]

    def test_falls_back_to_agency_level_when_the_dataset_has_no_entries_of_its_own(self, config):
        result = people_mod.assignees_for("birth-registrations", "registry-services", config)
        assert [p["email"] for p in result] == ["keith@example.com"]

    def test_a_scope_with_neither_returns_an_empty_list(self, config):
        assert people_mod.assignees_for("cp-carers", "child-protection-family-support", config) == []

    def test_dataset_level_entries_are_never_merged_with_agency_level(self):
        """A dataset carrying its own explicit assignments overrides its
        agency's list outright - a real design choice (people.py's own
        docstring), not an oversight: this asserts the agency-level
        person never leaks into a dataset-level result even when both
        exist for the same real scope."""
        config = {
            "people": {},
            "agency_assignments": {"child-protection-family-support": [{"email": "keith@example.com", "github": "keithamoss", "role": "qa"}]},
            "dataset_assignments": {"cp-clients": [{"email": "jane@example.com", "github": "janereviewer", "role": "peer_review"}]},
        }
        result = people_mod.assignees_for("cp-clients", "child-protection-family-support", config)
        assert [p["email"] for p in result] == ["jane@example.com"]


class TestGithubUsernamesFor:
    def test_returns_sorted_real_usernames(self, config):
        config["agency_assignments"]["registry-services"].append(
            {"email": "aaron@example.com", "github": "aaronsomeone", "role": "manager"})
        assert people_mod.github_usernames_for("birth-registrations", "registry-services", config) == ["aaronsomeone", "keithamoss"]

    def test_a_person_with_no_real_github_username_is_silently_excluded(self):
        config = {
            "people": {},
            "agency_assignments": {"registry-services": [{"email": "keith@example.com", "github": None, "role": "qa"}]},
            "dataset_assignments": {},
        }
        assert people_mod.github_usernames_for("birth-registrations", "registry-services", config) == []

    def test_the_real_committed_contract_people_yaml_parses_cleanly(self):
        """Whatever real state contract/people.yaml is actually in right
        now (empty today, real entries once Keith fills them in) must
        always parse without raising - the same real-file smoke check
        tests/test_github_links.py already runs against this repo's own
        committed check-definition files."""
        config = people_mod.parse_people_config()
        assert isinstance(config["people"], dict)
