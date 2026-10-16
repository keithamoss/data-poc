"""Whether a person in contract/people.yaml can actually act
(REQ-GHUB-082 criterion 29).

THE FAILURE IS SILENT AND LATE without this. Somebody added without a
`github:` is shown on the dashboard, assigned nothing, and discovers
they cannot raise a filing decision at the moment they try - which will
be the moment something is wrong.
"""
from __future__ import annotations

import textwrap

import pytest

from qa_tools.common import people
from qa_tools.common import validate_people


def _write(tmp_path, body: str):
    """The file as written, plus what REQ-GHUB-171 makes every valid file
    carry - its declared roles and a real asset manager - unless the test
    states its own, so each test still breaks exactly one thing."""
    import yaml

    doc = yaml.safe_load(textwrap.dedent(body)) or {}
    doc.setdefault("roles", ["qa", "peer_review", "manager"])
    if not any("data_asset" in (a or {}) for a in doc.get("assignments") or []):
        doc.setdefault("people", []).append(
            {"email": "asset.manager@example.com", "name": "Asset Manager",
             "github": "asset-manager-for-tests", "roles": ["manager"]})
        doc.setdefault("assignments", []).append(
            {"data_asset": "data-asset-1", "person": "asset.manager@example.com",
             "role": "manager"})
    path = tmp_path / "people.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False))
    return path


class TestTheGate:
    def test_the_real_committed_file_passes(self):
        """The file as committed is the thing this gate runs against on
        every build, so it is the case worth asserting first."""
        assert validate_people.problems() == []

    def test_a_real_person_without_a_github_username_is_a_problem(self, tmp_path):
        found = validate_people.problems(_write(tmp_path, """
            people:
              - email: real@example.com
                name: A Real Person
        """))
        assert len(found) == 1
        assert "no `github:`" in found[0]

    def test_a_placeholder_without_one_is_not(self, tmp_path):
        """The deliberate exception. Three of the four entries in this
        repo's own file are stand-ins for colleagues not yet named, and
        they exist so the "Owned by" badge reads as a name rather than a
        gap."""
        assert validate_people.problems(_write(tmp_path, """
            people:
              - email: brian.cohen@example.com
                name: Brian Cohen
                placeholder: true
        """)) == []

    def test_a_placeholder_WITH_one_is_a_problem(self, tmp_path):
        """The direction that matters more. A username makes a
        fictional person assignable to a real ticket."""
        found = validate_people.problems(_write(tmp_path, """
            people:
              - email: brian.cohen@example.com
                name: Brian Cohen
                github: not-a-real-account
                placeholder: true
        """))
        assert len(found) == 1
        assert "placeholder" in found[0]

    def test_two_people_sharing_one_github_account_is_a_problem(self, tmp_path):
        """A decision raised by that account cannot be attributed to
        one of them, which is the one thing the log exists to do."""
        found = validate_people.problems(_write(tmp_path, """
            people:
              - email: one@example.com
                github: shared
              - email: two@example.com
                github: shared
        """))
        assert any("two people" in line for line in found)

    def test_an_assignment_naming_nobody_is_a_problem(self, tmp_path):
        """It is silently skipped at read time, so the scope it names
        has nobody assigned and nothing says so."""
        found = validate_people.problems(_write(tmp_path, """
            people:
              - email: real@example.com
                github: real
            assignments:
              - agency: registry-services
                person: ghost@example.com
        """))
        assert any("ghost@example.com" in line for line in found)

    def test_a_missing_file_is_not_a_problem(self, tmp_path):
        """This repo ships the file empty until real people are added,
        and a gate that fails on a fresh clone is a gate people
        disable."""
        assert validate_people.problems(tmp_path / "absent.yaml") == []

    def test_a_duplicate_email_is_a_problem(self, tmp_path):
        found = validate_people.problems(_write(tmp_path, """
            people:
              - email: same@example.com
                github: one
              - email: same@example.com
                github: two
        """))
        assert any("listed twice" in line for line in found)


class TestWhoMayRaiseADecision:
    """REQ-GHUB-082 criteria 6, 14 and 27."""

    @pytest.fixture
    def config(self):
        return people.parse_people_config()

    def test_a_real_person_resolves_from_their_github_account(self, config):
        got = people.person_by_github("keithamoss", config)
        assert people.actor_name(got) == "fpycnkgvmt@privaterelay.appleid.com"

    def test_the_username_match_ignores_case(self, config):
        """GitHub's own usernames are case-insensitive, and a decision
        refused over the capitalisation in a config file is a refusal
        nobody can act on."""
        assert people.person_by_github("KeithAmoss", config) == \
            people.person_by_github("keithamoss", config)

    def test_an_unknown_account_is_refused_rather_than_None(self, config):
        """A None a caller forgets to check becomes a decision recorded
        against an empty actor."""
        with pytest.raises(people.UnknownActor) as exc:
            people.person_by_github("a-stranger", config)
        assert "a-stranger" in str(exc.value)

    def test_an_empty_username_matches_nobody(self, config):
        """Every placeholder has no `github:`, so a blank one must not
        fall through to the first of them."""
        with pytest.raises(people.UnknownActor):
            people.person_by_github("", config)

    def test_a_placeholder_cannot_raise_one_by_email_either(self, config):
        with pytest.raises(people.UnknownActor) as exc:
            people.person_by_email("brian.cohen@example.com", config)
        assert "placeholder" in str(exc.value)

    def test_somebody_outside_the_file_cannot_raise_one(self, config):
        """Criterion 14. Being able to comment on the repository, or to
        run the terminal, is not the same as being allowed to file."""
        with pytest.raises(people.UnknownActor):
            people.person_by_email("stranger@example.com", config)

    def test_the_actor_recorded_is_the_EMAIL(self, config):
        """Names are edited and two people share one; the email is what
        git_identity already stamps onto every QA run, so the terminal
        route needs no second notion of who is at the keyboard."""
        got = people.person_by_email("fpycnkgvmt@privaterelay.appleid.com", config)
        assert people.actor_name(got) == got["email"]
        assert people.actor_name(got) != got["name"]
