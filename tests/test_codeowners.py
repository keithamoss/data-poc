"""A calendar correction needs the named approver's review on GitHub
(REQ-GHUB-174). The gate's half is in test_agreement_freeze.py's
TestTheApprover; this is the committed file and its parser."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from qa_tools.common import agreement_freeze as freeze

ROOT = Path(__file__).resolve().parent.parent
CODEOWNERS = (ROOT / ".github" / "CODEOWNERS").read_text()


class TestTheCommittedFile:
    @pytest.mark.parametrize("path", ["contract/calendar.yaml", "contract/data-asset.yaml",
                                      "contract/people.yaml", ".github/CODEOWNERS"])
    def test_it_owns_the_four_files(self, path):
        """Criterion 1."""
        assert freeze.code_owners(CODEOWNERS, path)

    def test_every_owner_of_the_agreement_is_an_approver_in_people_yaml(self):
        """Criterion 2's match goes through people.yaml's github field, so a
        code owner nobody can name as approver is a file out of step."""
        people = yaml.safe_load((ROOT / "contract" / "people.yaml").read_text())
        handles = {str(p.get("github", "")).lower() for p in freeze.approvers(people)}
        assert freeze.code_owners(CODEOWNERS, "contract/calendar.yaml") <= handles

    def test_it_owns_nothing_else(self):
        assert freeze.code_owners(CODEOWNERS, "contract/bdm-birth-registrations.yaml") == set()

    def test_the_documentation_says_review_is_off_and_how_to_turn_it_on(self):
        """Criteria 3 and 4."""
        doc = (ROOT / "docs" / "code-owner-review.md").read_text()
        assert "off in this proof of concept" in doc.lower()
        assert "Require review from Code Owners" in doc


class TestTheParser:
    @pytest.mark.parametrize("pattern,path,owned", [
        ("/contract/calendar.yaml", "contract/calendar.yaml", True),
        ("/contract/calendar.yaml", "x/contract/calendar.yaml", False),
        ("calendar.yaml", "contract/calendar.yaml", True),
        ("/contract/", "contract/calendar.yaml", True),
        ("contract/", "a/contract/calendar.yaml", True),
        ("*.yaml", "contract/calendar.yaml", True),
        ("/contract/*.yaml", "contract/calendar.yaml", True),
        ("/docs/", "contract/calendar.yaml", False),
        ("*", "contract/calendar.yaml", True),
    ])
    def test_patterns(self, pattern, path, owned):
        assert bool(freeze.code_owners(f"{pattern} @someone", path)) is owned

    def test_comments_and_team_owners_are_not_people(self):
        text = "# /contract/ @nobody\n/contract/ @Keith @org/team  # trailing\n"
        assert freeze.code_owners(text, "contract/calendar.yaml") == {"keith"}

    def test_a_later_line_with_no_owner_unowns(self):
        text = "/contract/ @keith\n/contract/calendar.yaml\n"
        assert freeze.code_owners(text, "contract/calendar.yaml") == set()

    def test_none_owns_nothing(self):
        assert freeze.code_owners(None, "contract/calendar.yaml") == set()


class TestCriticFindingsOn174:
    """delivery-critic on REQ-GHUB-174 (51df202), post-build-review #143."""

    @pytest.mark.parametrize("pattern,path,owned", [
        ("/*.yaml", "contract/calendar.yaml", False),     # M4: root files only
        ("/*.yaml", "calendar.yaml", True),
        ("docs/*", "docs/a/b.md", False),                 # GitHub's own example
        ("docs/*", "docs/a.md", True),
        ("/contract/**", "contract/calendar.yaml", True),
    ])
    def test_M4_a_star_does_not_cross_a_slash(self, pattern, path, owned):
        assert bool(freeze.code_owners(f"{pattern} @someone", path)) is owned

    def test_M4_a_bare_at_is_not_an_owner(self):
        assert freeze.code_owners("/contract/calendar.yaml @", "contract/calendar.yaml") == set()

    def test_L1_may_approve_names_only_who_the_gate_accepts(self):
        """The paste-ready block's "May approve" must not name a manager the
        gate then refuses as not a code owner."""
        import copy
        from datetime import date, datetime, timedelta, timezone

        cal = yaml.safe_load((ROOT / "contract" / "calendar.yaml").read_text())
        asset = yaml.safe_load((ROOT / "contract" / "data-asset.yaml").read_text())
        people_doc = yaml.safe_load((ROOT / "contract" / "people.yaml").read_text())
        new = copy.deepcopy(cal)
        quarterly = next(c for c in new["calendars"] if c["name"] == "quarterly")
        for d in quarterly["versions"][-1]["dates"]:
            if d["period"] == "2024-Q1":
                d["date"] = "2024-02-05"
        at = datetime(2026, 10, 11, 3, tzinfo=timezone(timedelta(hours=8)))
        found = freeze.check(cal, new, asset, asset, people_doc, instant_of=lambda k: at,
                             today=date(2026, 10, 11),
                             base_codeowners="/contract/calendar.yaml @someone-else\n")
        text = "\n".join(f.fix for f in found)
        assert "May approve: nobody" in text, text
