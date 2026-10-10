"""REQ-DOCS-073 - `mothman plans` (the CLI half of the dependency view)."""
from __future__ import annotations

import re

from click.testing import CliRunner

from cli.app import cli
from qa_tools.common import sprint_state


def _run(*args):
    return CliRunner().invoke(cli, list(args))


class TestTheDependencyView:
    def test_it_names_both_directions(self):
        out = _run("plans", "dependencies").output
        assert "waits on:" in out and "holds up:" in out

    def test_the_status_survives_rich_markup(self):
        """A REAL BUG, found by running it rather than by reading it.
        The view writes a sprint's state in square brackets, which Rich
        reads as a style tag - `[blocked]` is not a style, so it was
        dropped and every row rendered with its status missing.

        ASSERTED AGAINST THE DATA, NOT AGAINST A LIST OF STATUS WORDS.
        This used to name `[blocked]`, `[in-progress]` and `[unscoped]`
        literally, and went red the moment sprint 11 stopped being
        unscoped - a real, correct change to plans/supply-model.md
        breaking a test about Rich markup. Which statuses appear is a
        property of today's register; that none of them is swallowed is
        the property this test is for.
        """
        rows = sprint_state.dependency_view()
        expected = {m.group(0) for row in rows
                    for m in re.finditer(r"\[[a-z-]+\]", row)}
        assert expected, "no sprint heading carried a bracketed status at all"
        out = _run("plans", "dependencies").output
        missing = sorted(s for s in expected if s not in out)
        assert not missing, f"Rich swallowed these statuses: {missing}"

    def test_it_exits_cleanly(self):
        assert _run("plans", "dependencies").exit_code == 0


class TestTheSprintsCommand:
    def test_it_prints_the_counts(self):
        out = _run("plans", "sprints").output
        assert "done" in out and "/" in out
