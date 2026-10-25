"""The bulk re-check and its trial in the terminal (REQ-PIPE-177, REQ-PIPE-178):
`mothman supply recheck --check <check_id>` and the filing-decisions door's
'Supplies checked before a check changed (N)'.

BOTH ROUTES SHOW ONE PANEL AND ASK ONE CONFIRMATION (criterion 6), built from
the one plan bulk_recheck.plan makes, and record through bulk_recheck.record,
which refuses where what it covers is not what the panel showed (criterion
12). The terminal route only - a bulk re-check spans many periods, so no
ticket can carry it (criterion 21).
"""
from __future__ import annotations

import time

from rich.panel import Panel
from rich.text import Text

from cli import common
from cli.common import console
from qa_tools.common import bulk_recheck as bulk
from qa_tools.common import decision_log, people, supply_db

#: The door's entry, above the collection choice (criterion 13).
MENU_ENTRY = "Supplies checked before a check changed"

HAND_OFF = "Hand it to the processing pass"
RUN_HERE = "Run it here now"
TRY_FIRST = "Try it on a few supplies first - nothing is recorded"
RECHECK_ALL = "Re-check them all"
PROCESS = "mothman pipeline process"

#: How many period rows the panel shows, and how many supplies the trial's
#: chooser lists, before a count line stands in for the rest - at thirty
#: collections one fix can cover hundreds.
PANEL_ROWS = 20
CHOOSER_ROWS = 40

FLAG_HINT = ("mothman supply recheck --check <check_id> --reason '<why>' --yes "
             "--acknowledge <key>")


def _command(check_id: str) -> str:
    return f"mothman supply recheck --check {check_id} --reason '<why>'"


def _show(text: str, *, title: str, style: str) -> None:
    """A panel, with any line that is a command printed below it on a line
    of its own, so it can be copied whole."""
    lines = text.split("\n")
    # ONLY A COMMAND ON A LINE OF ITS OWN is lifted out; an indented one sits
    # under its own heading inside the panel (critic polish, 2026-10-25).
    commands = [ln for ln in lines if ln.startswith("mothman ")]
    body = "\n".join(ln for ln in lines if not ln.startswith("mothman "))
    console.print(Panel(Text(body), title=title, border_style=style, expand=False))
    for c in commands:
        console.print(c, markup=False, highlight=False, soft_wrap=True)


# ---- the panel (criteria 6, 18, 27, 28, 33) --------------------------------------------

def panel_lines(p: bulk.Plan, *, flag_route: bool) -> list[str]:
    n = len(p.covered)
    entry = p.changelog
    lines = [f"Check: {p.check_id}",
             f"Its current changelog entry ({bulk.changed_on(entry)}): {bulk.headline(entry)}",
             f"Supplies it covers: {n}, {p.promoted} of them promoted."]
    rows = p.by_dataset_period()
    for ds, period, count in rows[:PANEL_ROWS]:
        lines.append(f"  {ds} {period}: {count}")
    if len(rows) > PANEL_ROWS:
        rest = sum(n for _ds, _p, n in rows[PANEL_ROWS:])
        lines.append(f"  ... and {rest} more in {len(rows) - PANEL_ROWS} more period(s) - "
                     f"`--list` lists every one")
    pairs = p.left_out_as("open-pair")
    if pairs:
        lines.append(f"Left out: {len(pairs)} supply/supplies of an open contested pair - settling the "
                     f"pair checks each file under the check's current definition.")
    for ds, refusal in sorted(p.refused.items()):
        count = sum(1 for x in p.left_out_as("backstop") if x.dataset_id == ds)
        lines.append(f"Left out: {ds}'s {count} supply/supplies - its judged past changed "
                     f"without a declared correction. They are covered once the correction "
                     f"is declared:")
        lines.extend(f"  {line}" for line in refusal.message().split("\n"))
    owed = p.left_out_as("already-owed")
    if owed:
        lines.append(f"Left out: {len(owed)} supply/supplies already owe a re-check, recorded "
                     f"and waiting to run - the processing pass runs them, or "
                     f"`mothman pipeline process`.")
    rejected, superseded = p.left_out_as("rejected"), p.left_out_as("superseded")
    if rejected or superseded:
        lines.append(f"Not covered: {len(rejected)} rejected and {len(superseded)} superseded "
                     f"supply/supplies the old definition also judged. Promote a rejected one, "
                     f"or un-supersede a superseded one, to bring it back to be covered:")
        lines.append("  mothman supply decide --operation promote --dataset <id> --period <p> "
                     "--supply <supply> --reason '<why>'")
        lines.append("  mothman supply decide --operation un-supersede --dataset <id> "
                     "--period <p> --supply <supply> --reason '<why>'")
    if n > bulk.WARN_ABOVE:
        lines.append(f"That is more than {bulk.WARN_ABOVE} supplies - about a minute each, so "
                     f"{bulk.estimate(n)}.")
        if flag_route:
            lines.append("--hand-off records every re-check and leaves them to the processing "
                         "pass instead of running them here. Closing the terminal part way "
                         "leaves the rest owed for the processing pass.")
    lines.append(f"Key: {p.key}")
    return lines


def show_panel(p: bulk.Plan, *, flag_route: bool) -> None:
    _show("\n".join(panel_lines(p, flag_route=flag_route)), title="Bulk re-check",
          style="yellow")


def reason_question(p: bulk.Plan) -> str:
    """Criterion 22: where the reason is published."""
    n = len(p.covered)
    return (f"Why are you re-checking these? It is published on the dashboard against each "
            f"of the {n} supplies this bulk re-check covers.")


# ---- running (criteria 14, 15, 23, 25) -------------------------------------------------

def _received(c: bulk.Covered) -> str:
    from qa_tools.common import filing

    try:
        at = filing.received_at_of(c.dataset_id, c.supply)
    except Exception:  # noqa: BLE001 - a progress line, never the run
        at = None
    return at.date().isoformat() if at is not None else "an unrecorded day"


def _minutes(seconds: float) -> str:
    m = int(round(seconds / 60))
    return f"{m}m" if m else f"{int(seconds)}s"


def run_foreground(recorded: bulk.Recorded) -> bulk.Summary:
    """Run a bulk re-check's own owed re-checks here, one line per supply, and
    return what ran - stopped by Ctrl-C at any point with the rest owed."""
    pairs = list(zip(recorded.covered, recorded.owed))
    n = len(pairs)
    console.print(f"Re-checking {n} supply/supplies. Ctrl-C stops it at any point - whatever "
                  f"has not run stays owed for the processing pass.", markup=False)
    s = bulk.Summary()
    start = time.monotonic()
    try:
        for k, (c, owed_id) in enumerate(pairs, start=1):
            elapsed = time.monotonic() - start
            left = (elapsed / (k - 1)) * (n - k + 1) if k > 1 else None
            timing = (f" ({_minutes(elapsed)} elapsed, about {_minutes(left)} left)"
                      if left is not None else "")
            console.print(f"[{k}/{n}] re-checking {c.dataset_id} {c.period} "
                          f"(received {_received(c)})...{timing}", markup=False,
                          highlight=False)
            r = bulk.run_one(c, owed_id)
            s.ran.append(r)
            if not r.completed:
                console.print(f"    did not finish - still owed: {r.outcome.message}",
                              markup=False, style="yellow")
            elif r.elsewhere:
                console.print("    already run elsewhere - its verdict is that run's",
                              markup=False)
            elif r.changed:
                console.print(f"    now {r.now or 'no verdict'}, was {c.status or 'no verdict'}",
                              markup=False, style="bold")
    except KeyboardInterrupt:
        s.owed = n - len(s.ran)
        console.print()
        console.print("Stopped.", style="yellow")
        show_summary(s, stopped=True)
        return s
    show_summary(s)
    return s


def show_summary(s: bulk.Summary, *, stopped: bool = False) -> None:
    lines = bulk.summary_lines(s)
    if s.still_owed:
        lines.append(f"The other {s.still_owed} are still owed - the processing pass runs "
                     f"them, or:")
        lines.append(PROCESS)
    _show("\n".join(lines), title="Bulk re-check - stopped" if stopped else "Bulk re-check",
          style="yellow" if s.still_owed else "green")


def say_handed_off(recorded: bulk.Recorded) -> None:
    """Criteria 18 and 23: recorded, none run."""
    _show(f"Recorded {len(recorded.owed)} re-check(s), and ran none of them. The processing "
          f"pass runs them - it runs every owed QA run, not only these. Nothing runs until "
          f"it or this command does:\n{PROCESS}", title="Handed to the processing pass",
          style="yellow")


# ---- the trial (REQ-PIPE-178) --------------------------------------------------------

def run_trial(p: bulk.Plan, chosen: list[bulk.Covered]) -> list[bulk.Tried]:
    """Run each chosen supply's trial, showing each as it finishes; stopped by
    Ctrl-C with the verdicts of those that finished (criterion 15)."""
    tried: list[bulk.Tried] = []
    try:
        for k, c in enumerate(chosen, start=1):
            console.print(f"[{k}/{len(chosen)}] trying {c.dataset_id} {c.period} "
                          f"(received {_received(c)})...", markup=False, highlight=False)
            tried.append(bulk.try_one(c))
    except KeyboardInterrupt:
        console.print()
        console.print("Stopped.", style="yellow")
    _show("\n".join(bulk.trial_lines(tried)), title="Trial - nothing was recorded",
          style="blue")
    console.print(f"The real bulk re-check covers {len(p.covered)} supply/supplies:",
                  markup=False)
    console.print(_command(p.check_id), markup=False, highlight=False, soft_wrap=True)
    return tried


def trial_count_line(p: bulk.Plan, chosen: list[bulk.Covered]) -> str:
    """Criterion 8: by dataset and period, beside the real run's number."""
    from collections import Counter

    counts = Counter((c.dataset_id, c.period) for c in chosen)
    where = ", ".join(f"{ds} {period} ({n})" for (ds, period), n in sorted(counts.items()))
    return (f"The trial runs {len(chosen)} supply/supplies - {where} - of the "
            f"{len(p.covered)} the real bulk re-check would cover.")


# ---- the door (criteria 13, 16, 18, 19) ------------------------------------------------

def nudges_or_none() -> list[bulk.Nudge]:
    """The asset's nudges, or none where they cannot be read - the door still
    works without them."""
    try:
        with supply_db.connect(read_only=True, label="mothman:bulk-recheck") as conn:
            return bulk.nudges(conn)
    except Exception as exc:  # noqa: BLE001 - see the docstring
        first = (str(exc).splitlines() or [type(exc).__name__])[0]
        console.print(f"The checks with supplies to re-check could not be read ({first}).",
                      style="dim", markup=False)
        return []


def menu_label(nudges: list[bulk.Nudge]) -> str:
    return f"{MENU_ENTRY} ({sum(n.total for n in nudges)})"


def door(nudges: list[bulk.Nudge]) -> None:
    """One check: its bulk re-check. More than one: a chooser of them, each
    with its supply count, the date it changed and its changelog headline."""
    if not nudges:
        return
    if len(nudges) == 1:
        flow(nudges[0].check_id)
        return
    labels = {f"{n.check_id} - {n.total} supply/supplies, changed {n.changed}: "
              f"{n.headline}": n for n in nudges}
    picked = common.select("Which check?", list(labels), flag_hint=FLAG_HINT)
    if picked is not None:
        flow(labels[picked].check_id)


def flow(check_id: str) -> None:
    """The terminal's bulk re-check of one check: the panel, a trial first if
    wanted (REQ-PIPE-178 criterion 14), the reason, one confirmation, then
    run here or handed to the processing pass."""
    from cli.filing_tui import actor_at_the_keyboard

    try:
        actor = actor_at_the_keyboard()
    except people.UnknownActor as exc:
        _show(str(exc), title="Bulk re-check - who is deciding?", style="red")
        return
    while True:
        with supply_db.connect(read_only=True, label="mothman:bulk-recheck") as conn:
            try:
                p = bulk.plan(conn, check_id)
            except bulk.Refused as exc:
                _show(str(exc), title="Bulk re-check refused", style="red")
                return
        if not p.covered:
            # WHAT WAS LEFT OUT IS SHOWN (critic D2): where the old definition's
            # supplies were all left out, the panel says which and why.
            if p.left_out:
                show_panel(p, flag_route=False)
            _show(bulk.nothing_to_cover(p), title="Nothing to re-check now", style="blue")
            return
        show_panel(p, flag_route=False)
        choice = common.select("Re-check them all, or try it on a few first?",
                               [RECHECK_ALL, TRY_FIRST], flag_hint=FLAG_HINT)
        if choice is None:
            return
        if choice == TRY_FIRST:
            trial_flow(p)
            continue  # back to the real run's confirmation (REQ-PIPE-178 criterion 18)
        break
    hand_off = False
    if len(p.covered) > bulk.WARN_ABOVE:
        console.print(f"That is {len(p.covered)} supplies - about a minute each, so "
                      f"{bulk.estimate(len(p.covered))}.", style="yellow", markup=False)
        how = common.select("How should it run?", [HAND_OFF, RUN_HERE], flag_hint=FLAG_HINT)
        if how is None:
            return
        hand_off = how == HAND_OFF
    reason = common.text_prompt(reason_question(p), flag_hint=FLAG_HINT)
    if reason is None:
        console.print("No reason given - nothing recorded.", style="yellow")
        return
    if not common.confirm_change(
            f"Record a bulk re-check of {len(p.covered)} supply/supplies for {p.check_id}, "
            f"as {people.actor_name(actor)}?", yes=False, default=False, flag_hint=FLAG_HINT):
        console.print("Not recorded.", style="yellow")
        return
    _record_and_go(p, actor=actor, reason=reason, hand_off=hand_off)


def _record_and_go(p: bulk.Plan, *, actor, reason: str, hand_off: bool,
                   acknowledged: str | None = None) -> int:
    """Record, then run here or hand off. Returns the exit status (criterion 30)."""
    from cli.filing_tui import CHECKS_STILL_OWED_EXIT

    try:
        with supply_db.connect(label="mothman:bulk-recheck") as conn:
            recorded = bulk.record(conn, p.check_id, actor=actor, reason=reason,
                                   effective_at=bulk.now_iso(),
                                   acknowledged=acknowledged or p.key, handed_off=hand_off,
                                   shown=p)
    except decision_log.DecisionRefused as exc:
        _show(str(exc), title="Bulk re-check refused", style="red")
        return 1
    _show(f"Recorded a bulk re-check of {len(recorded.owed)} supply/supplies for "
          f"{p.check_id}.", title="Recorded", style="green")
    if hand_off:
        say_handed_off(recorded)
        return 0
    s = run_foreground(recorded)
    return CHECKS_STILL_OWED_EXIT if s.still_owed else 0


def trial_flow(p: bulk.Plan) -> None:
    """Choose supplies from a list, or one dataset's period range, from what
    the real run would cover; confirm the count; run; nothing recorded."""
    by_label = {f"{c.dataset_id} {c.period} - {c.supply} ({c.status or 'no verdict'})": c
                for c in p.covered[:CHOOSER_ROWS]}
    if len(p.covered) > CHOOSER_ROWS:
        console.print(f"Listing the first {CHOOSER_ROWS} of {len(p.covered)} supplies - a "
                      f"period range reaches the rest.", markup=False)
    chosen: list[bulk.Covered] = []
    while True:
        left = [label for label, c in by_label.items() if c not in chosen]
        picked = common.select(
            f"Which supplies? ({len(chosen)} chosen) - or a dataset's period range",
            (["Done - run the trial"] if chosen else [])
            + ["A period range of one dataset"] + left, flag_hint="--trial --supply <id>")
        if picked is None:
            return
        if picked == "Done - run the trial":
            break
        if picked == "A period range of one dataset":
            chosen = _range_choice(p)
            if not chosen:
                return
            break
        chosen.append(by_label[picked])
    console.print(trial_count_line(p, chosen), markup=False)
    if not common.confirm("Run the trial? Nothing is recorded.", yes=False, default=True,
                          flag_hint="--trial --yes"):
        return
    run_trial(p, chosen)


def _range_choice(p: bulk.Plan) -> list[bulk.Covered]:
    datasets = sorted({c.dataset_id for c in p.covered})
    ds = datasets[0] if len(datasets) == 1 else common.select(
        "Which dataset?", datasets, flag_hint="--trial --dataset <id>")
    if ds is None:
        return []
    periods = sorted({c.period for c in p.covered if c.dataset_id == ds})
    first = common.select("From which period?", periods, flag_hint="--from-period")
    if first is None:
        return []
    last = common.select("Through which period?", [x for x in periods if x >= first],
                         flag_hint="--through-period")
    if last is None:
        return []
    console.print("This range applies to the trial only - the real bulk re-check covers "
                  "everything the check touches, with no range.", style="yellow", markup=False)
    return bulk.choose(p, dataset_id=ds, from_period=first, through_period=last)


# ---- the flag route ------------------------------------------------------------------

def from_flags(*, check_id: str, reason: str | None, yes: bool, acknowledged: str | None,
               hand_off: bool, listing: bool) -> int:
    """`mothman supply recheck --check` (criteria 11, 12, 18, 23, 30, 31, 32).
    Returns the exit status."""
    from cli.filing_tui import actor_at_the_keyboard

    with supply_db.connect(read_only=True, label="mothman:bulk-recheck") as conn:
        try:
            p = bulk.plan(conn, check_id)
        except bulk.Refused as exc:
            _show(str(exc), title="Bulk re-check refused", style="red")
            return 1
    if listing:
        say_list(p)
        return 0
    if not p.covered:
        if p.left_out:
            show_panel(p, flag_route=True)
        _show(bulk.nothing_to_cover(p), title="Bulk re-check refused", style="red")
        return 1
    show_panel(p, flag_route=True)
    interactive = _interactive()
    if not yes and not interactive:
        _show(f"Nothing was recorded. To go ahead without a terminal, pass --yes and "
              f"--acknowledge {p.key}:\n"
              f"mothman supply recheck --check {p.check_id} --reason '<why>' --yes "
              f"--acknowledge {p.key}", title="Bulk re-check needs confirming", style="red")
        return 1
    if yes and acknowledged != p.key:
        why = (f"The key {acknowledged} does not match this bulk re-check's - mistyped, or what "
               f"it covers has changed since it was shown." if acknowledged else
               "--yes needs --acknowledge with the key above.")
        _show(f"{why} Nothing was recorded. The current key is {p.key}:\n"
              f"mothman supply recheck --check {p.check_id} --reason '<why>' --yes "
              f"--acknowledge {p.key}", title="Bulk re-check refused", style="red")
        return 1
    try:
        actor = actor_at_the_keyboard()
    except people.UnknownActor as exc:
        _show(str(exc), title="Bulk re-check refused", style="red")
        return 1
    if reason is None:
        if not interactive:
            _show("A bulk re-check needs --reason. Nothing was recorded.",
                  title="Bulk re-check refused", style="red")
            return 1
        reason = common.text_prompt(reason_question(p), flag_hint="--reason")
        if reason is None:
            console.print("No reason given - nothing recorded.", style="yellow")
            return 1
    try:
        ok = common.confirm_change(
            f"Record a bulk re-check of {len(p.covered)} supply/supplies for {p.check_id}, as "
            f"{people.actor_name(actor)}?", yes=yes, default=False,
            flag_hint=f"pass --yes --acknowledge {p.key}")
    except common.NotInteractive as exc:
        _show(str(exc), title="Bulk re-check refused", style="red")
        return 1
    if not ok:
        console.print("Not recorded.", style="yellow")
        return 1
    return _record_and_go(p, actor=actor, reason=reason, hand_off=hand_off,
                          acknowledged=acknowledged if yes else p.key)


def _interactive() -> bool:
    import sys

    return sys.stdin.isatty() and sys.stdout.isatty()


def say_list(p: bulk.Plan) -> None:
    """Criterion 32: what the real run would cover, for choosing trial ids."""
    if not p.covered:
        console.print(bulk.nothing_to_cover(p).replace(" Nothing was recorded.", ""),
                      markup=False)
        return
    from rich.table import Table

    table = Table("Dataset", "Period", "Supply", "Verdict now", box=None, pad_edge=False)
    for c in p.covered:
        table.add_row(c.dataset_id, c.period, c.supply, c.status or "no verdict")
    console.print(f"The bulk re-check of {p.check_id} would cover {len(p.covered)} "
                  f"supply/supplies:", markup=False)
    console.print(table)


def trial_from_flags(*, check_id: str, supplies: tuple[str, ...], dataset_id: str | None,
                     from_period: str | None, through_period: str | None, yes: bool) -> int:
    """`mothman supply recheck --check <id> --trial` (REQ-PIPE-178 criteria
    8, 9, 11, 16, 17, 18)."""
    with supply_db.connect(read_only=True, label="mothman:bulk-recheck") as conn:
        try:
            p = bulk.plan(conn, check_id)
        except bulk.Refused as exc:
            _show(str(exc), title="Trial refused", style="red")
            return 1
    try:
        chosen = bulk.choose(p, supplies=supplies, dataset_id=dataset_id,
                             from_period=from_period, through_period=through_period)
    except bulk.Refused as exc:
        _show(str(exc), title="Trial refused", style="red")
        return 1
    if from_period or through_period:
        console.print("This range applies to the trial only - the real bulk re-check covers "
                      "everything the check touches, with no range.", style="yellow",
                      markup=False)
    console.print(trial_count_line(p, chosen), markup=False)
    if not yes and not _interactive():
        _show("Nothing was run. To run the trial without a terminal, pass --yes.",
              title="Trial needs confirming", style="red")
        return 1
    if not common.confirm("Run the trial? Nothing is recorded.", yes=yes, default=True,
                          flag_hint="pass --yes"):
        return 1
    run_trial(p, chosen)
    return 0
