"""Tests for `mothman schedule` (REQ-PIPE-049).

The group exists at all because of a real disagreement between the two
pre-build reviewers: delivery-architect wanted this folded into
`pipeline` on taxonomy grounds, delivery-cli-ux wanted its own group and
won on a point the architect had not weighed - cli/pipeline.py's own
docstring calls that group "not human-facing", and somebody editing
thirty delivery calendars is exactly a human. So the first thing worth
testing is that it IS discoverable where a human would look.
"""
from __future__ import annotations

from click.testing import CliRunner

from cli import schedule as schedule_cli
from cli.app import cli

_runner = CliRunner()


class TestItIsWhereAHumanWouldLookForIt:
    def test_schedule_is_a_top_level_mothman_group(self):
        result = _runner.invoke(cli, ["--help"])
        assert result.exit_code == 0, result.output
        assert "schedule" in result.output

    def test_its_help_says_what_it_is_for_without_jargon(self):
        result = _runner.invoke(schedule_cli.schedule_group, ["--help"])
        assert result.exit_code == 0, result.output
        assert "candidate-dates" in result.output and "show" in result.output


class TestShow:
    def test_it_prints_both_real_calendars_and_who_uses_them(self):
        result = _runner.invoke(schedule_cli.schedule_group, ["show"])
        assert result.exit_code == 0, result.output
        assert "quarterly" in result.output and "daily" in result.output
        assert "birth-registrations" in result.output

    def test_one_dataset_shows_its_own_participation(self):
        result = _runner.invoke(schedule_cli.schedule_group, ["show", "--dataset", "cp-case-workers"])
        assert result.exit_code == 0, result.output
        assert "February" in result.output and "August" in result.output
        assert "2023-Q1" in result.output

    def test_a_daily_dataset_needs_an_until_because_every_day_has_no_end(self):
        result = _runner.invoke(schedule_cli.schedule_group,
                                 ["show", "--dataset", "birth-registrations"])
        assert result.exit_code != 0
        assert "until" in str(result.exception) or "until" in result.output

    def test_a_daily_dataset_with_until_lists_its_periods(self):
        result = _runner.invoke(schedule_cli.schedule_group,
                                 ["show", "--dataset", "birth-registrations",
                                  "--until", "2023-01-05"])
        assert result.exit_code == 0, result.output
        assert "2023-01-05" in result.output


class TestCandidateDates:
    def test_it_says_plainly_that_nothing_evaluates_against_its_output(self):
        """The one thing this command must never be mistaken for. The
        authored dates ARE the supplier agreement; this only saves
        somebody typing four of them out."""
        result = _runner.invoke(schedule_cli.schedule_group,
                                 ["candidate-dates", "--calendar", "quarterly", "--year", "2029"])
        assert result.exit_code == 0, result.output
        assert "Nothing evaluates" in result.output
        assert "2029-Q1" in result.output

    def test_a_weekend_candidate_carries_its_warning_into_the_output(self):
        result = _runner.invoke(schedule_cli.schedule_group,
                                 ["candidate-dates", "--calendar", "quarterly", "--year", "2026"])
        assert result.exit_code == 0, result.output
        assert "Sunday" in result.output

    def test_extending_a_cadence_rule_calendar_fails_with_a_reason(self):
        result = _runner.invoke(schedule_cli.schedule_group,
                                 ["candidate-dates", "--calendar", "daily", "--year", "2029"])
        assert result.exit_code != 0
        assert "cadence-rule" in result.output

    def test_an_unknown_calendar_names_the_real_ones(self):
        result = _runner.invoke(schedule_cli.schedule_group,
                                 ["candidate-dates", "--calendar", "nope", "--year", "2029"])
        assert result.exit_code != 0
        assert "quarterly" in str(result.exception) + result.output
