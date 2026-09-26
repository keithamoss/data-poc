"""REQ-DOCS-073 - `mothman plans` (the CLI half of the dependency view)."""
from __future__ import annotations

from click.testing import CliRunner

from cli.app import cli


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
        dropped and every row rendered with its status missing."""
        out = _run("plans", "dependencies").output
        assert "[blocked]" in out or "[in-progress]" in out
        assert "[unscoped]" in out

    def test_it_exits_cleanly(self):
        assert _run("plans", "dependencies").exit_code == 0


class TestTheSprintsCommand:
    def test_it_prints_the_counts(self):
        out = _run("plans", "sprints").output
        assert "done" in out and "/" in out
