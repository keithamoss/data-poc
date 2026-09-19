"""Tests for cli/github.py - the mothman CLI's GitHub workflow/people
automation commands (plans/tooling.md #1 Phase 4). Each command is a
1-line wrapper around a retired script's own real main() - these tests
verify the dispatch, not GitHub itself (no `gh` CLI in this sandbox -
real verification happens in CI, which has one - see cli/github.py's
own module docstring)."""
from __future__ import annotations

from click.testing import CliRunner

import cli.github as github_cli

_runner = CliRunner()


def test_sync_tickets_calls_ticket_sync_main(monkeypatch):
    import qa_tools.common.ticket_sync as ticket_sync

    called = []
    monkeypatch.setattr(ticket_sync, "main", lambda: called.append(True))

    result = _runner.invoke(github_cli.github_group, ["sync-tickets"])

    assert result.exit_code == 0, result.output
    assert called == [True]


def test_sync_acceptances_calls_acceptance_sync_main(monkeypatch):
    import qa_tools.common.acceptance_sync as acceptance_sync

    called = []
    monkeypatch.setattr(acceptance_sync, "main", lambda: called.append(True))

    result = _runner.invoke(github_cli.github_group, ["sync-acceptances"])

    assert result.exit_code == 0, result.output
    assert called == [True]


def test_sync_leaderboard_calls_leaderboard_main(monkeypatch):
    import qa_tools.common.leaderboard as leaderboard

    called = []
    monkeypatch.setattr(leaderboard, "main", lambda: called.append(True))

    result = _runner.invoke(github_cli.github_group, ["sync-leaderboard"])

    assert result.exit_code == 0, result.output
    assert called == [True]
