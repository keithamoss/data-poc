"""mothman schedule - the delivery calendars (REQ-PIPE-049).

ITS OWN GROUP RATHER THAN FOLDED INTO `pipeline`, and that was the one
point the two pre-build reviewers disagreed on. delivery-architect
argued for `pipeline` on taxonomy grounds; delivery-cli-ux argued for a
group of its own, and won on something the architect had not weighed -
Keith's own cli/pipeline.py docstring calls that group "not
human-facing", and somebody editing thirty delivery calendars is
exactly a human. Also rejected: fold in now and move to a `mothman
supply` group later, because renames are how a CLI surface rots.

Everything here is CONFIG ONLY. Nothing opens data/, a warehouse, or
committed history, so it is safe under the CI rule and fast enough to
run while editing a calendar.
"""
from __future__ import annotations

from datetime import date, timedelta

import rich_click as click
from rich.console import Console
from rich.table import Table

from qa_tools.common import display_time

console = Console()


@click.group("schedule")
def schedule_group() -> None:
    """Delivery calendars - who is expected to deliver what, and when."""


#: How many periods either side of today the default window shows.
#: Small on purpose - the question this command is usually asked is
#: "is my next supply due, and am I past it?", which needs the last
#: couple and the next few, not three years (post-build-review #29).
WINDOW_BEFORE = 3
WINDOW_AFTER = 5


class _KnownChoice(click.ParamType):
    """A finite, known set of values, listed in `--help`.

    `--dataset TEXT` and `--calendar TEXT` enumerated nothing although
    both sets are small, fixed and readable straight out of the config -
    and the penalty for guessing wrong used to be a traceback
    (post-build-review #30).

    RESOLVED LAZILY rather than at import: the values come from
    `contract/data-asset.yaml`, and reading it while the module is
    being imported would make every `mothman --help` - including the
    ones that never touch a schedule - depend on that file parsing.
    A gate exists to tell you it does not; the help should not be the
    thing that breaks first.
    """

    name = "choice"

    def __init__(self, load, what: str):
        self._load = load
        self._what = what

    def _values(self) -> list[str]:
        try:
            return list(self._load())
        except Exception:
            return []

    def get_metavar(self, param, ctx=None) -> str:
        values = self._values()
        return f"[{'|'.join(values)}]" if values else self._what.upper()

    def convert(self, value, param, ctx):
        values = self._values()
        if not values or value in values:
            return value
        self.fail(f"{value!r} is not a known {self._what}. "
                  f"Known: {', '.join(values)}.", param, ctx)
        return None


def _unwrap(exc: Exception) -> str:
    """A config error's own message, without Python's quoting.

    `UnknownDatasetError` subclasses `KeyError`, whose `str()` wraps the
    message in its own repr - so printing it raw gives a message inside
    double quotes with escaped inner quotes. That is the traceback
    showing through the thing meant to replace it.
    """
    message = exc.args[0] if exc.args else str(exc)
    return str(message)


def _datasets() -> list[str]:
    from qa_tools.common import hierarchy
    return sorted(d.dataset_id for d in hierarchy.all_datasets())


def _calendars() -> list[str]:
    from qa_tools.common import schedule
    return sorted(c.name for c in schedule.calendars())


@schedule_group.command("show")
@click.option("--dataset", type=_KnownChoice(lambda: _datasets(), "dataset"),
              help="One dataset's own periods, rather than every calendar.")
@click.option("--until", type=click.DateTime(formats=["%Y-%m-%d"]),
              help="Last date to list. Implies --all up to that date.")
@click.option("--all", "show_all", is_flag=True,
              help="Every period, not just the ones around today. For a daily "
                   "calendar that is thousands of rows - pair it with --until.")
def show_command(dataset: str | None, until, show_all: bool) -> None:
    """Print the delivery calendars, or one dataset's own periods.

    \b
    Examples:
      mothman schedule show
      mothman schedule show --dataset cp-case-workers
      mothman schedule show --dataset birth-registrations --until 2026-12-31

    By default a single dataset shows a WINDOW around today - the last
    few periods and the next few - because at daily cadence the full
    list is thousands of rows and the question is almost always "what
    is next?". Use --all for everything.
    """
    from qa_tools.common import hierarchy, schedule

    if dataset:
        # ORDINARY WRONG INPUT IS NOT A CRASH. A mistyped dataset id, or
        # a calendar with no end and no horizon, used to end in a 30-40
        # line traceback - while `candidate-dates`, in the same command
        # group, answered the same class of mistake with a clean Click
        # box. Same group, two languages (post-build-review #24). The
        # messages themselves were already good; they were buried.
        try:
            _show_dataset(dataset, until.date() if until else None, show_all,
                           hierarchy, schedule)
        except (hierarchy.UnknownDatasetError, schedule.ScheduleConfigError) as exc:
            raise click.ClickException(_unwrap(exc)) from None
        return

    for cal in schedule.calendars():
        version = cal.current
        shape = ("cadence rule: " + version.cadence_rule if version.is_cadence_rule
                 else f"{len(version.periods)} authored dates")
        console.print(f"\n[bold]{cal.name}[/bold] - {shape}, claim window "
                       f"{schedule.format_duration(version.claim_window)}")
        if cal.description:
            console.print(f"  [dim]{cal.description}[/dim]")
        console.print(f"  [dim]in force from {version.effective_from} "
                       f"({len(cal.versions)} version(s))[/dim]")
        users = [d.dataset_id for d in hierarchy.all_datasets()
                 if schedule.calendar_for_dataset(d.dataset_id).name == cal.name]
        console.print(f"  used by: {', '.join(users)}")
        if not version.is_cadence_rule:
            table = Table("Period", "Date", box=None, pad_edge=False)
            for period in version.periods:
                table.add_row(period.name, period.date.isoformat())
            console.print(table)


def _show_dataset(dataset: str, until: date | None, show_all: bool,
                   hierarchy, schedule) -> None:
    entry = hierarchy.dataset(dataset)
    cal = schedule.calendar_for_dataset(dataset)
    months = schedule.delivery_months(dataset)
    console.print(f"\n[bold]{entry.dataset_name}[/bold] ({entry.dataset_id})")
    console.print(f"  calendar: {cal.name}")
    console.print(f"  delivery months: "
                   f"{', '.join(schedule.MONTH_NAMES[m - 1] for m in months) if months else 'all'}")
    # Shown in the form the config authors it in - `14d`, not
    # `14 days, 0:00:00` (post-build-review #27).
    console.print(f"  claim window: {schedule.format_duration(schedule.claim_window(dataset))} "
                   f"before each deadline [dim](opens early, never closes)[/dim]")

    from qa_tools.common import asset_time
    today = asset_time.local_date(asset_time.now())

    # A CADENCE RULE GENERATES FOR EVER, so it needs a stop date - and
    # until this window existed, not passing one was a 34-frame
    # traceback on the most obvious invocation in this repo
    # (post-build-review #24/#29). The default horizon is the window's
    # own far edge, which is enough to answer "what is next?" without
    # asking the reader to name a date they have no reason to know.
    stop = until
    if stop is None and cal.current.is_cadence_rule:
        stop = today + timedelta(days=WINDOW_AFTER + 1)
    periods = schedule.periods_for_dataset(dataset, until=stop)

    # THE SLOT IS WHAT THIS DATASET ACTUALLY OWES (REQ-PIPE-052), and
    # showing periods without it would leave the one per-dataset fact
    # somebody editing a calendar most needs - the deadline - off the
    # page. Keyed by period name, because a not-expected period has no
    # slot at all and that difference is the point.
    from qa_tools.common import slots as slots_mod
    by_period = {s.name: s for s in slots_mod.slots_for_dataset(dataset, until=stop)}

    shown, hidden = _window(periods, today, show_all or until is not None)

    table = Table("", "Period", "Date", "Expected", "Due", "Claimable from",
                   box=None, pad_edge=False)
    for p in shown:
        # A not-expected period is SHOWN, with its reason - never
        # dropped. "We agreed there would be no November file" and "we
        # forgot to configure November" must not look the same.
        expected = "yes" if p.expected else f"no - {p.not_expected_reason}"
        slot = by_period.get(p.name)
        # The reader's actual question is "is my next supply due, and am
        # I past it?" - so the next one owed is marked rather than left
        # to be worked out from the dates.
        marker = ""
        if slot and p.date >= today:
            marker = "->" if p.name == _next_owed(shown, by_period, today) else ""
        # THE PERIOD'S DATE IS A CONFIG ECHO and keeps its written form
        # (criterion 8) - a reader comparing this table against
        # contract/data-asset.yaml is comparing those two columns. The
        # DUE and CLAIMABLE instants are not in any file: this computes
        # them, so they are written the way everything else a person
        # reads is written (REQ-DASH-071).
        table.add_row(marker, p.name, p.date.isoformat(), expected,
                       display_time.format_instant(slot.due_at) if slot else "-",
                       display_time.format_instant(slot.claim_opens_at) if slot else "-")
    console.print(table)

    owed = len(by_period)
    footer = f"  [dim]{len(periods)} period(s), {owed} slot(s)"
    if owed < len(periods):
        footer += (f"; {len(periods) - owed} period(s) carry no supply for this "
                    f"dataset, so it owes nothing for them")
    # THE THING A READER ACTUALLY WONDERS, answered rather than left to
    # inference: why cp-case-workers shows ten rows where its calendar
    # has twenty dates. The old footer instead explained a period/slot
    # distinction no shipped config exercises (post-build-review #30).
    if months:
        on_calendar = len(schedule.periods_for_calendar(cal.name, until=stop))
        if on_calendar > len(periods):
            named = ", ".join(schedule.MONTH_NAMES[m - 1] for m in months)
            footer += (f". The calendar has {on_calendar}; this dataset takes "
                        f"delivery in {named} only")
    console.print(footer + "[/dim]")
    if hidden:
        console.print(f"  [dim]{hidden} further period(s) not shown - "
                       f"`--all` for every one, `--until YYYY-MM-DD` for a horizon.[/dim]")


def _next_owed(periods, by_period, today) -> str | None:
    """The first period on or after today that this dataset owes."""
    for p in periods:
        if p.date >= today and p.name in by_period:
            return p.name
    return None


def _window(periods, today, everything: bool):
    """(rows to show, how many were left out).

    A WINDOW AROUND TODAY rather than the whole sequence, because at
    daily cadence the whole sequence is thousands of rows and the
    question being asked is almost never "show me three years"
    (post-build-review #29, Keith's own call). `--all` and `--until`
    both mean the reader asked for a horizon on purpose, so neither
    gets trimmed.
    """
    if everything or len(periods) <= WINDOW_BEFORE + WINDOW_AFTER:
        return periods, 0
    after = [i for i, p in enumerate(periods) if p.date >= today]
    pivot = after[0] if after else len(periods)
    start = max(0, pivot - WINDOW_BEFORE)
    end = min(len(periods), pivot + WINDOW_AFTER)
    return periods[start:end], len(periods) - (end - start)


@schedule_group.command("candidate-dates")
@click.option("--calendar", "calendar_name", required=True,
              type=_KnownChoice(lambda: _calendars(), "calendar"),
              help="Which calendar to extend.")
@click.option("--year", type=int, required=True, help="The year to propose dates for.")
@click.option("--yaml", "as_yaml", is_flag=True,
              help="Emit the YAML to paste, rather than a table to read.")
def candidate_dates_command(calendar_name: str, year: int, as_yaml: bool) -> None:
    """Propose next year's dates for a human to review, edit and commit.

    \b
    Examples:
      mothman schedule candidate-dates --calendar quarterly --year 2028
      mothman schedule candidate-dates --calendar quarterly --year 2028 --yaml

    These are CANDIDATES and nothing evaluates against them. The dates
    in the calendar ARE the supplier agreement; this only saves somebody
    typing out four dates and working out which ones fall on a weekend.
    Copy what you want into contract/data-asset.yaml, as a NEW version
    with its own effective_from and changelog entry.
    """
    from qa_tools.common import schedule

    cal = schedule.calendar(calendar_name)
    version = cal.current
    if version.is_cadence_rule:
        raise click.ClickException(
            f"{calendar_name!r} is a cadence-rule calendar ({version.cadence_rule}) - it generates "
            f"its own periods and has no authored dates to extend.")

    # ONLY THE NEXT YEAR ALONG, and this is the whole of
    # post-build-review #28: this command is what the runway warning
    # points at as the remedy, and it would happily propose a year
    # already authored (whose dates `validate` then rejects as
    # duplicates), a year in the past, or a year with a gap before it -
    # which is a dataset expecting nothing for the skipped years, the
    # exact hole REQ-PIPE-050 exists to catch. It knew the last
    # authored period all along; the warning prints it one screen
    # earlier.
    authored = [p.date.year for p in schedule.periods_for_calendar(calendar_name)]
    if authored:
        expected = max(authored) + 1
        if year <= max(authored):
            raise click.ClickException(
                f"{calendar_name!r} is already authored through {max(authored)}, so "
                f"{year} would duplicate dates that already exist - `validate` rejects "
                f"those. The next year to author is {expected}.")
        if year > expected:
            raise click.ClickException(
                f"{calendar_name!r} is authored through {max(authored)}, so proposing "
                f"{year} would leave "
                f"{', '.join(str(y) for y in range(expected, year))} unauthored - a gap "
                f"is a dataset expecting nothing for those years. Author {expected} "
                f"first.")

    proposals = schedule.candidate_dates(calendar_name, year)
    if not proposals:
        raise click.ClickException(
            f"{calendar_name!r} has no authored dates to infer a pattern from.")

    if as_yaml:
        # THE THING THE HELP TELLS YOU TO COPY. It said "copy what you
        # want into contract/data-asset.yaml" and printed a Rich table
        # (post-build-review #28). Printed bare, so it can be piped.
        import yaml as _yaml
        body = {"effective_from": f"{year}-01-01",
                 "changelog": [f"{year}-01-01: authored {year} dates"],
                 "dates": [{"period": period.name, "date": period.date.isoformat()}
                            for period, _note in proposals]}
        print(_yaml.safe_dump(body, sort_keys=False))
        notes = [f"{period.name}: {note}" for period, note in proposals if note]
        if notes:
            console.print("[dim]# review: " + "; ".join(notes) + "[/dim]")
        return

    console.print(f"\n[bold]Candidate dates for {calendar_name} in {year}[/bold]")
    console.print("[dim]Review, edit, and commit as a new calendar version. Nothing evaluates "
                   "against these - the authored dates are the agreement.[/dim]\n")
    table = Table("Period", "Date", "Day", "Note", box=None, pad_edge=False)
    for period, note in proposals:
        table.add_row(period.name, period.date.isoformat(),
                       period.date.strftime("%A"), note or "")
    console.print(table)


@schedule_group.command("validate")
def validate_command() -> None:
    """Check the delivery calendars for mistakes that would silently
    expect nothing.

    \b
    Examples:
      mothman schedule validate

    A calendar typo does not fail loudly - it produces a dataset that
    owes no supply, which looks exactly like a dataset with nothing
    wrong. This refuses that configuration instead.

    Low runway is reported as a warning and never fails the build.
    """
    # Sited here rather than under `dashboard` with the other
    # validators because this is the group somebody editing a calendar
    # is already in - and `mothman check` runs it either way.
    #
    # The requirement id and the siting rationale used to be the help
    # text a reader saw in `mothman schedule --help`; they are comments
    # now, which is who they were always written for
    # (post-build-review #30).
    import sys

    from qa_tools.common.validate_schedule import WARNING_EXIT_VAR
    from qa_tools.common.validate_schedule import main as validate_main

    code = validate_main()
    if code == 0:
        return
    # A WARNING IS NOT A FAILURE, and this wrapper is where that used
    # to stop being true: every non-zero code became the same
    # ClickException, so the gate's "passed, with a warning" sentinel
    # arrived at `mothman check` as a plain exit 1 and rendered red
    # (found driving the real command, post-build-review #23). The
    # sentinel is only ever emitted when the caller asked for it, so
    # passing it straight through cannot surprise CI.
    import os
    configured = (os.environ.get(WARNING_EXIT_VAR) or "").strip()
    if configured.isdigit() and code == int(configured):
        sys.exit(code)
    raise click.ClickException("schedule validation failed - see output above.")
