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

from datetime import date

import rich_click as click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group("schedule")
def schedule_group() -> None:
    """Delivery calendars - who is expected to deliver what, and when."""


@schedule_group.command("show")
@click.option("--dataset", help="Show one dataset's own periods rather than every calendar.")
@click.option("--until", help="For a daily calendar, the last date to list (YYYY-MM-DD).")
def show_command(dataset: str | None, until: str | None) -> None:
    """Print the delivery calendars, or one dataset's own periods."""
    from qa_tools.common import hierarchy, schedule

    if dataset:
        _show_dataset(dataset, until, hierarchy, schedule)
        return

    for cal in schedule.calendars():
        version = cal.current
        shape = ("cadence rule: " + version.cadence_rule if version.is_cadence_rule
                 else f"{len(version.periods)} authored dates")
        console.print(f"\n[bold]{cal.name}[/bold] - {shape}, claim window {version.claim_window}")
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


def _show_dataset(dataset: str, until: str | None, hierarchy, schedule) -> None:
    entry = hierarchy.dataset(dataset)
    cal = schedule.calendar_for_dataset(dataset)
    months = schedule.delivery_months(dataset)
    console.print(f"\n[bold]{entry.dataset_name}[/bold] ({entry.dataset_id})")
    console.print(f"  calendar: {cal.name}")
    console.print(f"  delivery months: "
                   f"{', '.join(schedule.MONTH_NAMES[m - 1] for m in months) if months else 'all'}")
    console.print(f"  claim window: {schedule.claim_window(dataset)}")

    periods = schedule.periods_for_dataset(
        dataset, until=date.fromisoformat(until) if until else None)
    table = Table("Period", "Date", "Expected", box=None, pad_edge=False)
    for p in periods:
        # A not-expected period is SHOWN, with its reason - never
        # dropped. "We agreed there would be no November file" and "we
        # forgot to configure November" must not look the same.
        expected = "yes" if p.expected else f"no - {p.not_expected_reason}"
        table.add_row(p.name, p.date.isoformat(), expected)
    console.print(table)
    console.print(f"  [dim]{len(periods)} period(s)[/dim]")


@schedule_group.command("candidate-dates")
@click.option("--calendar", "calendar_name", required=True, help="Which calendar to extend.")
@click.option("--year", type=int, required=True, help="The year to propose dates for.")
def candidate_dates_command(calendar_name: str, year: int) -> None:
    """Propose next year's dates for a human to review, edit and commit.

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

    proposals = schedule.candidate_dates(calendar_name, year)
    if not proposals:
        raise click.ClickException(
            f"{calendar_name!r} has no authored dates to infer a pattern from.")

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
    """Gate: a config error can never silently produce zero slots (REQ-PIPE-050).

    Here rather than under `dashboard` with the other validators,
    because this is the group somebody editing a calendar is already
    in - and because `mothman check` runs it either way.
    """
    from qa_tools.common.validate_schedule import main as validate_main
    if validate_main() != 0:
        raise click.ClickException("schedule validation failed - see output above.")
