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
        """`--all` since 2026-09-25: the default is now a window around
        today, so 2023-Q1 is deliberately out of frame
        (post-build-review #29). What this test is actually about - that
        a dataset's own delivery months and periods are shown - is
        unchanged."""
        result = _runner.invoke(schedule_cli.schedule_group,
                                 ["show", "--dataset", "cp-case-workers", "--all"])
        assert result.exit_code == 0, result.output
        assert "February" in result.output and "August" in result.output
        assert "2023-Q1" in result.output

    def test_a_daily_dataset_no_longer_needs_an_until(self):
        """REPLACES "a daily dataset needs an --until", which asserted
        the behaviour post-build-review #29 exists to remove.

        A cadence rule generates periods for ever, so something has to
        bound the list - but requiring the READER to supply that bound
        meant the most obvious invocation for this repo's flagship
        dataset ended in a 34-frame traceback, and supplying it printed
        1370 rows. Keith's call, 2026-09-25: default to a window, keep
        `--all` for the dump. The bound now comes from the window.
        """
        result = _runner.invoke(schedule_cli.schedule_group,
                                 ["show", "--dataset", "birth-registrations"])
        assert result.exit_code == 0, result.output
        assert "Traceback" not in result.output
        # A handful of rows, not three years of them.
        assert result.output.count("+0800") < 40

    def test_all_is_a_real_escape_hatch_and_still_prints_everything(self):
        """The window trims by default; `--all` must genuinely not.
        Otherwise the default becomes a cap with no way past it, which
        is a worse problem than the one #29 set out to fix."""
        windowed = _runner.invoke(schedule_cli.schedule_group,
                                   ["show", "--dataset", "birth-registrations"])
        everything = _runner.invoke(schedule_cli.schedule_group,
                                     ["show", "--dataset", "birth-registrations", "--all"])
        assert everything.exit_code == 0, everything.output
        # Counted on the time-of-day, which every Due and Claimable
        # cell carries. It used to count "+0800" - the offset the
        # display standard stopped printing (REQ-DASH-071 criterion 6:
        # one clock, so nothing to distinguish it from).
        assert everything.output.count("2:00pm") > windowed.output.count("2:00pm") * 10

    def test_the_window_says_how_much_it_left_out(self):
        """A trimmed list that does not admit it is trimmed is the same
        class of problem as the summary that said "Every gate passed"
        over a warning."""
        result = _runner.invoke(schedule_cli.schedule_group,
                                 ["show", "--dataset", "cp-case-workers"])
        assert "not shown" in result.output
        assert "--all" in result.output

    def test_the_window_marks_the_next_supply_owed(self):
        """The reader's actual question - is my next supply due, and am
        I past it? - was answerable only by reading dates out of up to
        1370 rows."""
        result = _runner.invoke(schedule_cli.schedule_group,
                                 ["show", "--dataset", "cp-case-workers"])
        assert "->" in result.output

    def test_a_daily_dataset_with_until_lists_its_periods(self):
        result = _runner.invoke(schedule_cli.schedule_group,
                                 ["show", "--dataset", "birth-registrations",
                                  "--until", "2023-01-05"])
        assert result.exit_code == 0, result.output
        assert "2023-01-05" in result.output


class TestCandidateDates:
    # 2028 rather than 2029/2026 since 2026-09-25: the command now
    # proposes only the year actually next in line, because proposing
    # any other either duplicates authored dates or leaves a gap behind
    # it (post-build-review #28). The year is the calendar's own
    # business, so these use whichever one is next rather than a
    # constant that goes stale the moment somebody authors 2028.

    def _next_year(self):
        from qa_tools.common import schedule
        return max(p.date.year for p in schedule.periods_for_calendar("quarterly")) + 1

    def test_it_says_plainly_that_nothing_evaluates_against_its_output(self):
        """The one thing this command must never be mistaken for. The
        authored dates ARE the supplier agreement; this only saves
        somebody typing four of them out."""
        year = self._next_year()
        result = _runner.invoke(schedule_cli.schedule_group,
                                 ["candidate-dates", "--calendar", "quarterly",
                                  "--year", str(year)])
        assert result.exit_code == 0, result.output
        assert "Nothing evaluates" in result.output
        assert f"{year}-Q1" in result.output

    def test_a_weekend_candidate_carries_its_note_column(self):
        """The weekend RULE itself is covered where it lives -
        tests/test_schedule.py's own
        `test_a_weekend_is_FLAGGED_not_silently_moved`, against a year
        that actually has one. This asserts only that the CLI carries a
        note through, since the year it may propose is now fixed by the
        calendar rather than chosen by the test."""
        year = self._next_year()
        result = _runner.invoke(schedule_cli.schedule_group,
                                 ["candidate-dates", "--calendar", "quarterly",
                                  "--year", str(year)])
        assert result.exit_code == 0, result.output
        assert "Note" in result.output
        assert "Day" in result.output

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


def test_show_dataset_puts_the_deadline_on_the_page():
    """REQ-PIPE-052. Periods without slots would leave the one
    per-dataset fact somebody editing a calendar most needs - when the
    supply is actually due - off the page entirely."""
    from click.testing import CliRunner

    from cli.schedule import schedule_group

    result = CliRunner().invoke(schedule_group, ["show", "--dataset", "cp-clients"])
    assert result.exit_code == 0, result.output
    assert "Due" in result.output
    assert "Claimable from" in result.output
    # "9:00am", not "09:00" - REQ-DASH-071 criterion 3.
    assert "9:00am" in result.output, "the dataset's own expected time of day"
    assert "slot(s)" in result.output


def test_show_dataset_says_the_window_opens_early_and_never_closes():
    """The claim window reads as a deadline unless the page says
    otherwise - and read that way it would mean the opposite of what it
    does (Thread E)."""
    from click.testing import CliRunner

    from cli.schedule import schedule_group

    result = CliRunner().invoke(schedule_group, ["show", "--dataset", "cp-clients"])
    assert result.exit_code == 0, result.output
    flat = " ".join(result.output.split())
    assert "before each deadline" in flat
    assert "never closes" in flat


class TestAWarningSurvivesTheCliWrapper:
    """post-build-review #23, and a bug found by driving the real
    command rather than by reading it.

    `mothman check` can now render a fourth outcome - "passed, with a
    warning" - which the gate signals by exiting with a sentinel code
    the runner asked it to use. The first build of that worked at the
    gate and still rendered red, because THIS wrapper turned every
    non-zero return into the same `ClickException`. The warning arrived
    as a plain exit 1.

    Worth a test rather than just a fix: a wrapper that flattens codes
    reads as correct, and nothing else in the chain would notice.
    """

    def test_the_sentinel_passes_through_instead_of_becoming_a_failure(self, monkeypatch):
        from qa_tools.common import validate_schedule as gate

        monkeypatch.setenv(gate.WARNING_EXIT_VAR, "78")
        monkeypatch.setattr(gate, "main", lambda *a, **k: 78)
        result = _runner.invoke(schedule_cli.schedule_group, ["validate"])
        assert result.exit_code == 78, result.output
        assert "failed" not in result.output.lower()

    def test_a_real_failure_is_still_a_failure_while_the_variable_is_set(self, monkeypatch):
        """The dangerous direction. Having asked for warnings must not
        turn a genuine error into one."""
        from qa_tools.common import validate_schedule as gate

        monkeypatch.setenv(gate.WARNING_EXIT_VAR, "78")
        monkeypatch.setattr(gate, "main", lambda *a, **k: 1)
        result = _runner.invoke(schedule_cli.schedule_group, ["validate"])
        assert result.exit_code != 0
        assert "failed" in result.output.lower()

    def test_without_the_variable_the_gate_never_emits_the_sentinel(self, monkeypatch):
        """What CI sees. deploy-pages.yml runs this as its own step, so
        a non-zero exit there is a failed step - the runway warning must
        leave it at 0."""
        from qa_tools.common import validate_schedule as gate

        monkeypatch.delenv(gate.WARNING_EXIT_VAR, raising=False)
        assert gate.main() == 0


class TestTheCliSpeaksOneLanguage:
    """post-build-review #24, #25, #27 and #30 - the same subject seen
    four ways: `mothman schedule` answers ordinary wrong input in two
    different idioms depending on which half of the command you hit.

    `candidate-dates`' Click-level errors were already model behaviour -
    a clean box, exit 2, a usage line, a `--help` pointer. `show` ended
    in a 30-40 line Python traceback for four ordinary inputs, including
    the single most obvious invocation for this repo's flagship dataset.
    """

    def test_the_flagship_datasets_most_obvious_invocation_does_not_crash(self):
        """`schedule show --dataset birth-registrations` is a daily
        cadence rule with no end, so it needs a stop date. The message
        saying so was genuinely good and sat under 34 frames of
        traceback - and named `until`, the Python parameter, rather than
        `--until`, the flag."""
        result = _runner.invoke(schedule_cli.schedule_group,
                                 ["show", "--dataset", "birth-registrations"])
        assert "Traceback" not in result.output
        assert result.exception is None or isinstance(result.exception, SystemExit), \
            result.output

    def test_an_unknown_dataset_is_an_ordinary_error_not_a_traceback(self):
        result = _runner.invoke(schedule_cli.schedule_group,
                                 ["show", "--dataset", "nope"])
        assert "Traceback" not in result.output
        assert "nope" in result.output

    def test_a_malformed_until_is_refused_by_click_like_every_other_flag(self):
        """`--until notadate` gave a bare ValueError from
        `date.fromisoformat`, naming neither the flag, the format nor
        the command - because the option was declared as free text. Every
        other mothman command gets Click's own convention for free."""
        result = _runner.invoke(schedule_cli.schedule_group,
                                 ["show", "--dataset", "cp-case-workers",
                                  "--until", "notadate"])
        assert "Traceback" not in result.output
        assert "--until" in result.output

    def test_a_claim_window_is_shown_in_the_form_it_is_authored_in(self):
        """#27. It printed `str(timedelta)` - `14 days, 0:00:00` and
        `4:00:00`. The config is authored `14d`/`4h` and REQ-PIPE-050
        rejects every other form on purpose; the one surface that
        displays it invented a fifth. `4:00:00` also reads as a time of
        day, in a table whose neighbouring columns are times."""
        result = _runner.invoke(schedule_cli.schedule_group,
                                 ["show", "--dataset", "cp-case-workers"])
        assert "0:00:00" not in result.output
        assert "14d" in result.output


class TestTheWarningCannotArriveBeforeTheVerdict:
    """post-build-review #26. The gate's own comment says the warning is
    printed AFTER the OK line "so it reads as an additional thing to
    know rather than as the gate's verdict". The OK line goes to stdout
    and the warning to stderr, so with stdout block-buffered - which is
    CI, and any plain shell - the warning arrived FIRST, with no verdict
    above it.

    Never seen in this sandbox because PYTHONUNBUFFERED is set here.
    """

    def test_stdout_is_flushed_before_anything_reaches_stderr(self, monkeypatch, capsys):
        from qa_tools.common import validate_schedule as mod

        order = []
        real_flush = __import__("sys").stdout.flush

        class _Tracking:
            def write(self, text):
                if text.strip():
                    order.append(("stderr", text.strip()[:20]))
                return len(text)

            def flush(self):
                order.append(("flush", ""))

        monkeypatch.setattr(mod.sys, "stderr", _Tracking())
        monkeypatch.setattr(mod.sys.stdout, "flush", lambda: order.append(("flush", "")))
        try:
            mod.main()
        finally:
            real_flush
        assert order, "nothing was written - the real config stopped warning"
        assert order[0][0] == "flush", (
            "stderr was written before stdout was flushed, so in a pipe the warning "
            "lands above the verdict it is supposed to follow")


class TestCandidateDatesCannotProposeAHole:
    """post-build-review #28. The command the runway warning points you
    at as the remedy would cheerfully produce the very hole
    REQ-PIPE-050 exists to catch.

    The quarterly calendar is authored to 2027. `--year 2027` proposed
    four periods already in the file, which `validate` then rejects as
    duplicates. `--year 2020` proposed six years into the past.
    `--year 2030` left 2028 and 2029 unauthored - a gap in the middle of
    a calendar, which is a dataset expecting nothing for two years.

    It knew the last authored period all along; the runway warning
    prints it one screen earlier.
    """

    def _run(self, year, extra=()):
        return _runner.invoke(schedule_cli.schedule_group,
                               ["candidate-dates", "--calendar", "quarterly",
                                "--year", str(year), *extra])

    def test_a_year_already_authored_is_refused(self):
        result = self._run(2027)
        assert result.exit_code != 0
        assert "2027" in result.output

    def test_a_year_in_the_past_is_refused(self):
        result = self._run(2020)
        assert result.exit_code != 0

    def test_a_year_that_would_skip_one_is_refused_and_names_the_next(self):
        """The dangerous one - it succeeds today and leaves a silent gap
        behind it."""
        result = self._run(2030)
        assert result.exit_code != 0
        assert "2028" in result.output

    def test_the_next_year_along_is_proposed_normally(self):
        result = self._run(2028)
        assert result.exit_code == 0, result.output
        assert "2028-Q1" in result.output

    def test_it_can_emit_the_yaml_its_own_help_tells_you_to_copy(self):
        """The help said "copy what you want into
        contract/data-asset.yaml" and printed a Rich table."""
        import yaml as _yaml

        result = self._run(2028, ["--yaml"])
        assert result.exit_code == 0, result.output
        parsed = _yaml.safe_load(result.output)
        assert isinstance(parsed, dict) and "dates" in parsed
        assert [d["period"] for d in parsed["dates"]][0] == "2028-Q1"
