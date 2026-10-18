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

import sys
from datetime import date, timedelta
from pathlib import Path

import rich_click as click
from rich.console import Console
from rich.table import Table

from cli import common
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
    `contract/data-asset.yaml` and `contract/calendar.yaml`, and reading it while the module is
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
@click.option("--on", "on", type=click.DateTime(formats=["%Y-%m-%d"]),
              help="With --dataset: the date its participation values are resolved "
                   "for, and where each came from. Defaults to today.")
def show_command(dataset: str | None, until, show_all: bool, on) -> None:
    """Print the delivery calendars, or one dataset's own periods.

    \b
    Examples:
      mothman schedule show
      mothman schedule show --dataset cp-case-workers
      mothman schedule show --dataset birth-registrations --until 2026-12-31
      mothman schedule show --dataset cp-clients --on 2024-06-01

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
                           hierarchy, schedule, on.date() if on else None)
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
                 if _calendar_name(schedule, d.dataset_id) == cal.name]
        console.print(f"  used by: {', '.join(users)}")
        if not version.is_cadence_rule:
            table = Table("Period", "Date", box=None, pad_edge=False)
            for period in version.periods:
                table.add_row(period.name, period.date.isoformat())
            console.print(table)


def _calendar_name(schedule, dataset_id: str) -> str | None:
    """The calendar this dataset names, or None where it says it has none
    (REQ-PIPE-106 criterion 1)."""
    try:
        return schedule.calendar_for_dataset(dataset_id).name
    except schedule.NoCalendarAgreed:
        return None


def _show_dataset(dataset: str, until: date | None, show_all: bool,
                   hierarchy, schedule, on: date | None = None) -> None:
    entry = hierarchy.dataset(dataset)
    declared = schedule.no_calendar(dataset)
    if declared is not None:
        # SAID IN WORDS, and said differently for the two kinds
        # (REQ-PIPE-106 criteria 3 and 8). "Not yet agreed" is somebody's
        # outstanding job; "never" is a finished decision about a one-off
        # extraction, and presenting the second as the first would put a
        # permanent item on somebody's list.
        console.print(f"\n[bold]{entry.dataset_name}[/bold] ({entry.dataset_id})")
        if declared == schedule.NOT_YET_AGREED:
            console.print("  [yellow]No delivery schedule has been agreed for this "
                           "dataset yet.[/yellow]")
            console.print("  [dim]It owes no supply and is filed to no period. Data it "
                           "receives is held apart so checks can be developed against "
                           "it.[/dim]")
        else:
            console.print("  [dim]A one-off extraction: it has supplies and no cadence at "
                           "all, and never will.[/dim]")
            console.print("  [dim]It owes no supply and is filed to no period.[/dim]")
        return
    cal = schedule.calendar_for_dataset(dataset)
    months = schedule.delivery_months(dataset)
    console.print(f"\n[bold]{entry.dataset_name}[/bold] ({entry.dataset_id})")
    console.print(f"  calendar: {cal.name}")
    # Said in the file's own words - the key is `participates` since
    # REQ-PIPE-110, and a subset carries the reason its version states.
    from qa_tools.common import agreement as agreement_mod
    from qa_tools.common import asset_time as _at
    in_force = agreement_mod.current().participation_on(dataset, _at.local_date(_at.now()))
    console.print(f"  participates: "
                   f"{', '.join(schedule.MONTH_NAMES[m - 1] for m in months) if months else 'all'}"
                   + (f" [dim]- {in_force.reason}[/dim]" if months and in_force and in_force.reason
                      else ""))
    # Shown in the form the config authors it in - `14d`, not
    # `14 days, 0:00:00` (post-build-review #27).
    console.print(f"  claim window: {schedule.format_duration(schedule.claim_window(dataset))} "
                   f"before each deadline [dim](opens early; closes when the next period's opens)[/dim]")

    from qa_tools.common import asset_time, participation_view
    today = asset_time.local_date(asset_time.now())
    # EACH VALUE AND WHERE IT CAME FROM (REQ-PIPE-181 criterion 13), on
    # --on or today - the renderer the Calendar entry shares.
    _show_values(participation_view.view(dataset, on or today))

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

    shown, hidden = _window(periods, today, show_all or until is not None, by_period)

    table = Table("", "Period", "Date", "Expected", "Due", "Claimable from",
                   box=None, pad_edge=False)
    for p in shown:
        # A not-expected period is SHOWN, with its reason - never
        # dropped. "We agreed there would be no November file" and "we
        # forgot to configure November" must not look the same.
        # ITS KIND AND ITS REASON (REQ-PIPE-110 criterion 37): the only
        # owed-nothing period this table lists is a not_expected one;
        # periods outside the dataset's participation are not rows at
        # all, and the footer says which and why.
        expected = "yes" if p.expected else f"no (not expected) - {p.not_expected_reason}"
        slot = by_period.get(p.name)
        # The reader's actual question is "is my next supply due, and am
        # I past it?" - so the next one owed is marked rather than left
        # to be worked out from the dates.
        marker = ""
        if slot and _due_date(p, by_period) >= today:
            marker = "->" if p.name == _next_owed(shown, by_period, today) else ""
        # THE PERIOD'S DATE IS A CONFIG ECHO and keeps its written form
        # (criterion 8) - a reader comparing this table against
        # contract/calendar.yaml is comparing those two columns. The
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
            footer += (f". The calendar has {on_calendar}; this dataset participates in "
                        f"{named} only")
            if in_force and in_force.reason:
                footer += f" - {in_force.reason}"
    console.print(footer + "[/dim]")
    if hidden:
        console.print(f"  [dim]{hidden} further period(s) not shown - "
                       f"`--all` for every one, `--until YYYY-MM-DD` for a horizon.[/dim]")


def _due_date(period, by_period) -> date:
    """The day a period's slot is DUE, in the asset's clock - its own date
    where it has no slot. A following-period slot (REQ-PIPE-167) is due
    weeks before its period's date, so "next" and "around today" are
    measured by this, not the period's date (post-build-review #142)."""
    from qa_tools.common import asset_time

    slot = by_period.get(period.name)
    return asset_time.local_date(slot.due_at) if slot else period.date


def _next_owed(periods, by_period, today) -> str | None:
    """The first period owed whose slot is due on or after today."""
    for p in periods:
        if p.name in by_period and _due_date(p, by_period) >= today:
            return p.name
    return None


def _window(periods, today, everything: bool, by_period=None):
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
    after = [i for i, p in enumerate(periods) if _due_date(p, by_period or {}) >= today]
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
    Copy what you want into contract/calendar.yaml, as a NEW version
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
        # want into contract/calendar.yaml" and printed a Rich table
        # (post-build-review #28). Printed bare, so it can be piped.
        import yaml as _yaml
        body = {"effective_from": f"{year}-01-01",
                 # STRUCTURED, because a plain-string entry is refused
                 # (REQ-PIPE-110 criterion 13); the author is the one
                 # thing this cannot know.
                 "changelog": [{"date": f"{year}-01-01", "author": "YOUR NAME",
                                "change": f"authored {year} dates"}],
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


@schedule_group.command("check-agreement")
@click.option("--dataset", "dataset_id", default=None,
              help="Check one dataset rather than every one.")
def check_agreement_command(dataset_id: str | None) -> None:
    """Say which datasets the processing pass would refuse, and why.

    \b
    Examples:
      mothman schedule check-agreement
      mothman schedule check-agreement --dataset cp-clients

    Reads the database: each recorded verdict names the agreement that
    judged it, and this compares that with the agreement as it stands. A
    difference no declared correction accounts for refuses the dataset -
    its new supplies are held until the agreement is restored or the change
    is declared. Exits 3 where any dataset is refused - its own status, never
    the 1 that red data gives - and 2 where any could not be checked, which
    outranks a refusal as it does in the processing pass.
    """
    # REQ-PIPE-173: the backstop's own report, the same computation the
    # pass and the dashboard build make.
    from qa_tools.common import agreement_drift, hierarchy, supply_db

    known = {d.dataset_id for d in hierarchy.all_datasets()}
    if dataset_id and dataset_id not in known:
        # delivery-critic on 173, #9: an unknown dataset is not "nothing
        # refused" - it is nothing checked.
        console.print(f"{dataset_id} is not a dataset of this asset, so nothing was checked. "
                      f"Datasets: {', '.join(sorted(known))}.", style="red")
        raise SystemExit(2)
    errors: list = []
    try:
        found = agreement_drift.refusals(dataset_ids=[dataset_id] if dataset_id else None,
                                         errors=errors)
    except supply_db.SupplyDbError as exc:
        console.print(f"The database cannot be read, so nothing was checked: {exc}",
                      style="red")
        raise SystemExit(2) from exc
    for ds, exc in errors:
        console.print(f"{ds} could not be checked, so it is neither refused nor cleared: "
                      f"{exc}", style="red", markup=False)
    if not found and not errors:
        console.print("Every recorded judgement matches the delivery agreement, or a "
                      "declared correction accounts for the difference. Nothing is refused.",
                      style="green")
        return
    for refusal in found.values():
        console.print(refusal.message(), style="red")
    # A DATASET THAT COULD NOT BE CHECKED OUTRANKS A REFUSAL, as the pass ranks
    # them (delivery-critic on (f)-(i), finding 5): something to retry first.
    raise SystemExit(2 if errors else 3)


@schedule_group.command("preview-correction")
@click.option("--against", "ref", default=None,
              help="The git ref to compare the working copy against. Defaults to the base "
                   "the schedule gate uses - once a correction is committed, the working "
                   "copy and HEAD agree, so name the ref it is going into.")
@click.option("--output", type=click.Path(dir_okay=False), default=None,
              help="Also write the report as Markdown, to attach to the change reference.")
def preview_correction_command(ref: str | None, output: str | None) -> None:
    """Preview what a correction to the delivery agreement would change.

    \b
    Examples:
      mothman schedule preview-correction
      mothman schedule preview-correction --against origin/main --output impact.md

    READS THE DATABASE. Compares the working copy of contract/calendar.yaml
    and contract/data-asset.yaml with the same files at a git ref, and lists
    each slot whose times move, each period that gains or loses an
    obligation, each recorded verdict that would change and each supply the
    filing rule would file elsewhere or hold - marking any a later period
    stands on. Records nothing. Run it, and attach the report, before
    asking the change board to approve a correction.
    """
    # REQ-PIPE-169: the computation REQ-PIPE-170's trial shares.
    text = _preview(ref)
    if output:
        Path(output).write_text(text)
        console.print(f"Written to {output} - attach it to the correction's change reference.",
                      style="green", markup=False)


def _preview(ref) -> str:
    """Print the impact preview and return it - the command's body and the
    Calendar entry's. Exits 2 where nothing could be compared."""
    import psycopg

    from qa_tools.common import correction_trial, supply_db

    try:
        text = correction_trial.preview(ref)
    except correction_trial.Unreadable as exc:
        console.print(f"Nothing was compared: {exc}", style="red", markup=False)
        raise SystemExit(2) from exc
    except (supply_db.SupplyDbError, psycopg.Error) as exc:
        # Criterion 9: configuration alone is not the impact - and a database
        # that answers but cannot give the facts is the same (F8).
        console.print(f"The recorded facts could not be read, so no impact is reported - "
                      f"one computed from configuration alone would not be complete: {exc}",
                      style="red", markup=False)
        raise SystemExit(2) from exc
    console.print(text, markup=False, highlight=False, soft_wrap=True)
    return text


@schedule_group.command("draft-correction")
@click.option("--against", "ref", default=None,
              help="The git ref to compare the working copy against. Defaults to the base "
                   "the schedule gate uses.")
@click.option("--reference", default=None, help="The change reference, e.g. CAB-123.")
@click.option("--reason", default=None, help="Why the agreement was wrong.")
@click.option("--approver", default=None,
              help="Who approves it - a person contract/people.yaml allows to.")
@click.option("--author", default=None, help="You.")
def draft_correction_command(ref, reference, reason, approver, author) -> None:
    """Print the correction entry to declare for each change you made.

    \b
    Examples:
      mothman schedule draft-correction
      mothman schedule draft-correction --reference CAB-123 --reason 'the date was a typo'

    Compares the working copy with the same base the schedule gate uses and
    prints, for every frozen item you changed and have not declared yet, the
    same entry the gate's refusal would - grouped by the item that owns it,
    ready to paste into its corrections list. Asks for anything not given
    when run in a terminal, and leaves a placeholder otherwise. It never
    edits the file: you make the edit, and git records who.
    """
    # REQ-PIPE-169 criterion 14.
    _draft(ref, reference=reference, reason=reason, approver=approver, author=author,
           interactive=sys.stdin.isatty())


def _draft(ref, *, reference=None, reason=None, approver=None, author=None,
           interactive: bool) -> None:
    """Print the correction entries - the command's body and the Calendar
    entry's, so the two cannot differ."""
    from qa_tools.common import correction_trial

    try:
        # ONLY ASK WHERE SOMETHING NEEDS DECLARING (delivery-critic on 169,
        # F10): the reference and reason were asked for, then thrown away.
        if interactive and correction_trial.draft(ref):
            reference = reference or common.text_prompt(
                "Change reference (blank leaves a placeholder):", flag_hint="--reference")
            reason = reason or common.text_prompt(
                "Why was the agreement wrong? (blank leaves a placeholder):",
                flag_hint="--reason")
            if not approver:
                allowed = correction_trial.may_approve(ref)
                if allowed:
                    approver = common.select("Who will approve it?",
                                             allowed + ["Leave a placeholder"],
                                             flag_hint="--approver")
                    approver = None if approver == "Leave a placeholder" else approver
        entries = correction_trial.draft(ref, reference=reference or None,
                                         reason=reason or None, approver=approver or None,
                                         author=author or None)
    except correction_trial.Unreadable as exc:
        console.print(f"Nothing was compared: {exc}", style="red", markup=False)
        raise SystemExit(2) from exc
    if not entries:
        console.print("Nothing frozen changed without a declared correction - there is "
                      "nothing to declare.", style="green")
        return
    for entry in entries:
        console.print(entry, markup=False, highlight=False, soft_wrap=True)
        console.print()


_CAL_PREVIEW = "Preview what my working copy's changes would re-judge and move"
_CAL_DRAFT = "Draft the correction entry to declare them"
_CAL_ANOTHER = "Look at another dataset or date"


def calendar_menu() -> None:
    """The terminal's Calendar entry (REQ-PIPE-169 criterion 13): the
    agreement in force for a dataset on a date, the corrections declared
    and whether each is applied, and the impact preview and draft entry for
    the working copy. VIEWING AND PREVIEWING ONLY - configuration is edited
    in git, where it is reviewed and the schedule gate runs."""
    from qa_tools.common import agreement, asset_time, correction_trial, hierarchy, supply_db

    while True:
        every = hierarchy.all_datasets()
        # GROUPED BY COLLECTION AND FILTERED BY TYPING above N_LIST datasets
        # (REQ-TEST-252 criterion 6); today's list at or below it.
        by_collection: dict[str, list[str]] = {}
        for d in every:
            by_collection.setdefault(d.collection_name, []).append(d.dataset_id)
        dataset_id = common.grouped_select("Which dataset?", list(by_collection.items()),
                                           flag_hint="mothman schedule show --dataset <id>",
                                           many=len(every) > common.N_LIST)
        if dataset_id is None:
            return
        today = asset_time.local_date(asset_time.now())
        raw = common.text_prompt(f"As at which date? YYYY-MM-DD, or blank for today "
                                 f"({today.isoformat()}):", flag_hint="mothman schedule show")
        try:
            on = date.fromisoformat(raw) if raw else today
        except ValueError:
            console.print(f"{raw!r} is not a date like {today.isoformat()}.", style="red",
                          markup=False)
            continue
        try:
            # THE WORKING COPY, read fresh (F9): the agreement cached at start
            # would mix with a preview read from disk after an edit.
            fresh = agreement.from_doc(correction_trial.working()[0])
            _show_in_force(correction_trial.in_force(dataset_id, on, fresh))
            from qa_tools.common import participation_view

            _show_values(participation_view.view(dataset_id, on, fresh))
        except correction_trial.Unreadable as exc:
            # F4: part-way through an edit, said - not a crashed session.
            console.print(str(exc), style="red", markup=False)
            return
        try:
            with supply_db.connect(read_only=True, label="mothman:calendar") as conn:
                found = correction_trial.declared(conn)
            known = True
        except supply_db.SupplyDbError:
            found, known = correction_trial.declared(None), False
        _show_declared(found, known)
        while True:
            choice = common.select("What next?", [_CAL_PREVIEW, _CAL_DRAFT, _CAL_ANOTHER],
                                   flag_hint="mothman schedule preview-correction / "
                                             "mothman schedule draft-correction")
            if choice is None:
                return
            if choice == _CAL_ANOTHER:
                break
            try:
                if choice == _CAL_PREVIEW:
                    text = _preview(None)
                    path = common.path_prompt("Write it to a file to attach to the change "
                                              "reference? A path, or blank to skip:",
                                              flag_hint="--output")
                    if path:
                        Path(path).write_text(text)
                        console.print(f"Written to {path}.", style="green", markup=False)
                else:
                    _draft(None, interactive=True)
            except SystemExit:
                pass


def _show_values(v) -> None:
    """THE ONE RENDERER for a dataset's resolved participation values
    (REQ-PIPE-181 criterion 13) - `schedule show --on` and the Calendar
    entry both call this."""
    when = f"{v.on.day} {v.on.strftime('%b %Y')}"
    if v.not_yet is not None:
        console.print(f"  On {when}: not yet owing - first version takes effect "
                      f"{v.not_yet.day} {v.not_yet.strftime('%b %Y')}", markup=False)
        return
    if not v.values:
        # A DATASET WITH NO PARTICIPATION AT ALL (delivery-critic on 181, F8):
        # one declared as having no calendar, listed by the Calendar entry.
        console.print(f"  On {when}: it has no participation versions, so it owes nothing.",
                      markup=False)
        return
    console.print(f"  On {when}:" + (f" {v.headline}" if v.headline else ""), markup=False)
    width = max(len(x.label) for x in v.values)
    for x in v.values:
        console.print(f"    {x.label:<{width}}  {x.text}  ({x.source})"
                      + (f"; changes {x.changes}" if x.changes else ""), markup=False)
    # A TURN-OFF (REQ-PIPE-179 criterion 28): who, when, why, what is still
    # owed and until when, what is not, and how long an ordinary edit can
    # change it.
    for line in v.turn_off:
        console.print(f"    {line}", markup=False)


def _show_in_force(f) -> None:
    console.print(f"[bold]{f.dataset_id}[/bold] as at {f.on:%-d %b %Y}", highlight=False)
    console.print(f"  Calendar: {f.calendar}; times read in {f.zone}", markup=False)
    console.print(f"  Owes: {f.owes}", markup=False)
    if f.next_period and f.inputs:
        i = f.inputs
        console.print(f"  Next period owed: {f.next_period} ({f.next_date:%-d %b %Y}) - due "
                      f"{i['due_date']} at {i['expected_time']}"
                      + (f", {i['days_before']} day(s) before the period's date"
                         if i.get("days_before") else "")
                      + f"; grace {_duration(i['grace_seconds'])}; claim window opens "
                        f"{_duration(i['claim_window_seconds'])} before", markup=False)
    elif f.next_period:
        console.print(f"  Next period owed: {f.next_period} - its times cannot be resolved",
                      markup=False)
    else:
        console.print("  Nothing is owed within the next 400 days of that date.", markup=False)
    for period, why in f.not_expected:
        console.print(f"  Owes nothing for {period}: {why}", markup=False)
    console.print()


def _duration(seconds) -> str:
    if seconds is None:
        return "none"
    if seconds % 86400 == 0:
        return f"{seconds // 86400}d"
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    return f"{seconds // 60}m"


def _show_declared(found, known: bool) -> None:
    if not found:
        console.print("No corrections have been declared.", style="dim")
        console.print()
        return
    console.print("Declared corrections, newest first:", style="bold")
    for d in found:
        if not known:
            state = "applied or not unknown - the database could not be read"
        elif d.applied:
            state = "applied"
        else:
            state = "pending - awaiting the asset manager's confirmation"
        console.print(f"  {d.date} {d.reference} on {d.owner}: {d.reason} [{state}]",
                      markup=False)
        for item in d.items:
            console.print(f"      {item}", markup=False, style="dim")
    console.print()
