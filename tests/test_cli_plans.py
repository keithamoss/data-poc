"""REQ-DOCS-073 - `mothman plans` (the CLI half of the dependency view)."""
from __future__ import annotations

import pytest

import re

from click.testing import CliRunner

from cli.app import cli
from qa_tools.common import sprint_state


def _run(*args):
    return CliRunner().invoke(cli, list(args))


#: A register of the test's own: sprint 1 built all but one criterion and
#: defers that one to sprint 2, which has built nothing. So sprint 1 reads
#: [blocked] and waits on sprint 2, and sprint 2 reads [todo] and holds it up.
#: Built here rather than read from today's register, which finishes sprints
#: (CLAUDE.md's test rule 4: a test must not go red because work succeeded).
_PLAN = """\
1. **[blocked, 2026-01-01]** **[Pipeline & publishing]** **The first sprint.**
   Some prose.

   **Owns:** `REQ-TEST-901`

2. **[todo, 2026-01-01]** **[Pipeline & publishing]** **The second sprint.**
   Some prose.

   **Owns:** `REQ-TEST-902`
"""
_REGISTER = {"requirements": [
    {"id": "REQ-TEST-901", "status": "built",
     "acceptance_criteria": ["THE SYSTEM SHALL one.", "THE SYSTEM SHALL two."],
     "unmet_criteria": [{"criterion": "2", "why": "y", "owner": "sprint 2",
                         "blocked_by": {"sprints": [2]}}]},
    {"id": "REQ-TEST-902", "status": "draft",
     "acceptance_criteria": ["THE SYSTEM SHALL three."]},
]}


@pytest.fixture
def register(tmp_path, monkeypatch):
    """Point `mothman plans dependencies` at the register above. Returns
    the two paths, so a test can write a different one over them."""
    import functools

    import yaml

    plan, reqs = tmp_path / "plan.md", tmp_path / "requirements.yaml"
    plan.write_text(_PLAN)
    reqs.write_text(yaml.safe_dump(_REGISTER))
    monkeypatch.setattr(sprint_state, "dependency_view",
                        functools.partial(sprint_state.dependency_view, plan, reqs))
    return plan, reqs


class TestTheDependencyView:
    def test_it_names_both_directions(self, register):
        out = _run("plans", "dependencies").output
        assert "waits on:" in out and "holds up:" in out
        assert "sprint 2" in out.split("waits on:", 1)[1].splitlines()[0]
        assert "sprint 1" in out.split("holds up:", 1)[1].splitlines()[0]

    def test_the_status_survives_rich_markup(self, register):
        """A REAL BUG, found by running it rather than by reading it.
        The view writes a sprint's state in square brackets, which Rich
        reads as a style tag - `[blocked]` is not a style, so it was
        dropped and every row rendered with its status missing.

        ASSERTED AGAINST THE DATA, NOT AGAINST A LIST OF STATUS WORDS:
        which statuses appear is a property of the register; that none of
        them is swallowed is the property this test is for. The register is
        the test's own, so it always has some.
        """
        rows = sprint_state.dependency_view()
        expected = {m.group(0) for row in rows
                    for m in re.finditer(r"\[[a-z-]+\]", row)}
        assert expected == {"[blocked]", "[todo]"}, rows
        out = _run("plans", "dependencies").output
        missing = sorted(s for s in expected if s not in out)
        assert not missing, f"Rich swallowed these statuses: {missing}"

    def test_it_exits_cleanly(self):
        assert _run("plans", "dependencies").exit_code == 0


class TestTheSprintsCommand:
    def test_it_prints_the_counts(self):
        out = _run("plans", "sprints").output
        assert "done" in out and "/" in out


#: The data asset this module's tests act for, unless a test says otherwise
#: (C11, Keith 2026-11-02: every test module names its asset).
pytestmark = pytest.mark.asset("quarterly")
