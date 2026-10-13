"""Settling a contested pair in the terminal (REQ-PIPE-193 criteria 3, 4, 7,
15, 19, 20, 24 and 27; REQ-PIPE-194 criteria 3 and 4).

THE TUI DRIVES IT (Keith, 2026-10-13): each file in turn, its four outcomes
as options to pick - never a command to paste - then a summary that can
change either answer, the reason, one warning panel and one confirmation.
The flag form (`mothman supply decide --operation choose-file
--file-outcome ...`) lands on the same summary, warning and confirmation.

AN ADAPTER. What a settlement MEANS - its rules, its effects, its
refusals - is qa_tools/common/settlement.py's, reached through
filing_decisions like every other decision. What is here is what a
terminal owns: asking, showing, and saying what came back. The option
rules below are pure functions, so the screens can be tested without one.

`choose-file` NEVER APPEARS ON A SCREEN (criterion 27): the operation's
name is for the flag form and the decision log.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from cli import common
from qa_tools.common import (asset_time, decision_log, filing_decisions, hierarchy, people,
                             settlement)

console = Console()

SUPPLY, REFILE, REJECT, SUPERSEDE = (settlement.SUPPLY, settlement.REFILE,
                                     settlement.REJECT, settlement.SUPERSEDE)

#: The four outcomes as the person reads them, in this order (criterion 3).
WORDS = {
    SUPPLY: "the supply for {period}",
    REFILE: "re-file - this file belongs to another period (named next)",
    REJECT: "reject - this file is wrong; it can be promoted back later on its own",
    SUPERSEDE: "a spare copy - kept, can be brought back",
}
#: The same, said back on the summary and the closing panel.
SAID = {
    SUPPLY: "the supply for {period}",
    REFILE: "re-filed to {to}",
    REJECT: "rejected",
    SUPERSEDE: "a spare copy - kept, can be brought back",
}

REFUSED_TITLE = "Settlement refused"
REASON_PROMPT = "Why are you settling these two files?"
CONFIRM = "Record the settlement of the two files for {dataset} {period}, as {person}?"
RECORD = "Record this settlement"
#: REQ-PIPE-194 criterion 4's two offers on an open pair.
SETTLE = "settle - say what each file is"
REJECT_BOTH = "reject both - neither file is usable; the period stays empty"
REJECT_BOTH_KEEPS = ("reject both - neither file is usable; the period keeps the supply "
                     "already promoted")

_FLAG_HINT = ("mothman supply decide --operation choose-file --dataset <id> --period <period> "
              "--file-outcome '<filename>=<supply|refile:<period>|reject|supersede>' (once per "
              "file) --reason '<why>' --yes")


@dataclass(frozen=True)
class Option:
    outcome: str
    label: str
    #: Why it is not available now, or None - an outcome ruled out is SHOWN
    #: with its reason, never hidden (criterion 4).
    unavailable: str | None = None

    @property
    def shown(self) -> str:
        return self.label if self.unavailable is None else (
            f"{self.label}  (not available: {self.unavailable})")


def first_options(files, period: str) -> list[Option]:
    """The first file's question (receipt order). An outcome that would
    leave the second file only one outcome says which, on the option
    itself (criterion 4)."""
    first, second = files
    out = []
    for outcome in settlement.OUTCOMES:
        label = WORDS[outcome].format(period=period)
        why = None
        if first.refused and outcome != REJECT:
            why = "this file never loaded, so it can only be rejected"
        elif outcome == SUPERSEDE:
            if second.refused:
                why = "the other file never loaded, so it cannot be the supply"
            else:
                label += f"; the other file becomes the supply for {period}"
        out.append(Option(outcome, label, why))
    return out


def second_options(files, period: str, first: settlement.Answer) -> list[Option]:
    """The second file's question, given the first's answer (criterion 4)."""
    _, second = files
    out = []
    for outcome in settlement.OUTCOMES:
        label = WORDS[outcome].format(period=period)
        why = None
        if second.refused and outcome != REJECT:
            why = "this file never loaded, so it can only be rejected"
        elif first.outcome == SUPERSEDE and outcome != SUPPLY:
            why = (f"the first file is a spare copy, so this one is the supply for "
                   f"{period}")
        elif outcome == SUPPLY and first.outcome == SUPPLY:
            why = f"the first file is already the supply for {period}"
        elif outcome == SUPERSEDE and first.outcome != SUPPLY:
            why = f"a spare copy needs the other file to be the supply for {period}"
        out.append(Option(outcome, label, why))
    return out


def said(answer: settlement.Answer, period: str) -> str:
    return SAID[answer.outcome].format(period=period, to=answer.to_period)


def summary_table(files, answers, period: str) -> Table:
    table = Table("File", "Received", "What it is", box=None, pad_edge=False)
    by_name = {a.filename: a for a in answers}
    for f in files:
        from qa_tools.common import display_time

        a = by_name.get(f.filename)
        table.add_row(f.filename, display_time.format_instant(f.received_at),
                      said(a, period) if a else "[dim]-[/dim]")
    return table


def _pick(message: str, options: list[Option]) -> Option | None:
    """Ask until an AVAILABLE option is picked, or Back (None). An
    unavailable one says why and asks again."""
    by_label = {o.shown: o for o in options}
    while True:
        choice = common.select(message, list(by_label), flag_hint=_FLAG_HINT)
        if choice is None:
            return None
        picked = by_label[choice]
        if picked.unavailable is None:
            return picked
        console.print(f"Not available: {picked.unavailable}.", style="yellow")


def _next_period(dataset_id: str, period: str) -> str | None:
    from qa_tools.common import slots

    try:
        return slots.relative_period(dataset_id, period, 1)
    except Exception:  # noqa: BLE001 - no default is still a question
        return None


def _target(dataset_id: str, period: str, filename: str, taken: str | None) -> str | None:
    """Which period a re-filed file belongs to, the next period offered as
    the default (criterion 19). A refused target says why and asks again,
    before the reason is asked and keeping both files' answers."""
    import questionary

    from qa_tools.common import refiling

    default = _next_period(dataset_id, period) or ""
    while True:
        common.require_tty(_FLAG_HINT)
        answer = common._ask(questionary.text(
            f"Which period does {filename} belong to?", default=default))
        answer = (answer or "").strip()
        if not answer:
            return None
        why = None
        if answer == period:
            why = (f"{period} is the pair's own period - that is 'the supply for "
                   f"{period}'")
        elif answer == taken:
            why = f"the other file is already re-filed to {answer}"
        elif not refiling._on_calendar(dataset_id, answer):
            why = f"{answer} is not a period {dataset_id} is delivered in"
        else:
            with _open() as conn:
                h = decision_log.held(conn, dataset_id, answer)
            if h and h.held_as == decision_log.INHERITED:
                why = f"nothing was expected for {answer}: it is inherited"
        if why is None:
            return answer
        console.print(f"Not that period: {why}. Name another.", style="yellow")


def _open():
    from cli import filing_tui

    return filing_tui.open_log()


def _ask_file(dataset_id: str, period: str, files, n: int,
              first: settlement.Answer | None) -> settlement.Answer | None:
    f = files[n]
    options = first_options(files, period) if n == 0 else second_options(files, period, first)
    if f.refused:
        console.print(f"{f.filename} never loaded - the load refused it - so it can only be "
                      f"rejected.", style="yellow")
    picked = _pick(f"What is {f.filename}?", options)
    if picked is None:
        return None
    to = None
    if picked.outcome == REFILE:
        to = _target(dataset_id, period, f.filename,
                     first.to_period if first is not None else None)
        if to is None:
            return None
    return settlement.Answer(f.filename, picked.outcome, to)


def _still_allowed(files, period: str, first: settlement.Answer,
                   second: settlement.Answer | None) -> bool:
    if second is None:
        return False
    option = next(o for o in second_options(files, period, first)
                  if o.outcome == second.outcome)
    return option.unavailable is None and not (
        second.outcome == REFILE and second.to_period == first.to_period)


def collect(dataset_id: str, period: str, files, *,
            given: list[settlement.Answer] | None = None,
            reason: str | None = None,
            summary: bool = True) -> tuple[list[settlement.Answer], str] | None:
    """Each file's answer, then the summary and the reason (criterion 24).
    `given` answers (the flag form, or 'reject both') skip straight to the
    summary. Back on either file's question returns to the one before - the
    second file's to the first's, the first's out - keeping no answer from
    the abandoned screen. Returns (answers, reason), or None where nothing
    is to be recorded."""
    by_name = {a.filename: a for a in (given or [])}
    first = by_name.get(files[0].filename)
    second = by_name.get(files[1].filename)
    step = 2 if first and second else 0
    while True:
        if step == 0:
            first = _ask_file(dataset_id, period, files, 0, None)
            if first is None:
                return None
            step = 1 if not _still_allowed(files, period, first, second) else 2
            if step == 1:
                second = None
        if step == 1:
            second = _ask_file(dataset_id, period, files, 1, first)
            if second is None:
                first, step = None, 0
                continue
            step = 2
        if not summary:
            # THE FLAG FORM WITH EVERY FILE ANSWERED (criterion 15): the
            # summary is the TUI's affordance; the rules, the warning and the
            # confirmation still apply, after this.
            console.print(summary_table(files, [first, second], period))
            asked = reason or common.text_prompt(REASON_PROMPT, flag_hint=_FLAG_HINT)
            return ([first, second], asked) if asked else None
        # THE SUMMARY (criterion 24): each file with its outcome, either one
        # changeable, the other re-checked against the rules.
        console.print()
        console.print(summary_table(files, [first, second], period))
        change_first = f"Change what {files[0].filename} is"
        change_second = f"Change what {files[1].filename} is"
        choice = common.select("Is that right?", [RECORD, change_first, change_second],
                               flag_hint=_FLAG_HINT)
        if choice is None:
            console.print("Not recorded.", style="yellow")
            return None
        if choice == change_first:
            step = 0
            continue
        if choice == change_second:
            step = 1
            continue
        if reason is None:
            asked = common.text_prompt(REASON_PROMPT, flag_hint=_FLAG_HINT)
            if asked is None:
                # BLANK RETURNS TO THE SUMMARY, both answers kept.
                continue
            return [first, second], asked
        return [first, second], reason


def settle(dataset_id: str, period: str, supply: str, *,
           answers: list[settlement.Answer] | None = None, reason: str | None = None,
           yes: bool = False, acknowledged: str | None = None,
           actor: dict | None = None, summary: bool = True) -> filing_decisions.Outcome | None:
    """The whole flow, from the files to the runs. None where nothing was
    recorded."""
    from cli import filing_tui

    try:
        actor = actor or filing_tui.actor_at_the_keyboard()
    except people.UnknownActor as exc:
        filing_tui._show(str(exc), title=REFUSED_TITLE, style="red")
        return None
    # REFUSED BEFORE ASKING ABOUT EITHER FILE (criterion 5).
    with filing_tui.open_log() as conn:
        why = settlement.refused_before_asking(conn, dataset_id, supply)
        _delivery, _period, files = settlement.pair_files(conn, dataset_id, supply)
    if why:
        filing_tui._show(why, title=REFUSED_TITLE, style="red")
        return None
    if len(files) != 2:
        filing_tui._show(f"{supply} carries {len(files)} files; a settlement is of two.",
                         title=REFUSED_TITLE, style="red")
        return None
    name = hierarchy.dataset(dataset_id).dataset_name
    # BOTH FILES, BY NAME AND RECEIPT, BEFORE ANY QUESTION (criterion 3).
    console.print(f"[bold]Two files arrived for {name}'s table in {period}[/bold] "
                  f"(earlier first):")
    console.print(summary_table(files, [], period))
    console.print()

    while True:
        got = collect(dataset_id, period, files, given=answers, reason=reason,
                      summary=summary)
        if got is None:
            return None
        chosen, why_settle = got
        request = filing_decisions.Request(
            operation=filing_decisions.CHOOSE_FILE, dataset_id=dataset_id, actor=actor,
            reason=why_settle, period=period, supply=supply, confirmed=True,
            acknowledged=acknowledged, file_outcomes=tuple(chosen))
        try:
            shown = filing_tui._consequences(request)
        except decision_log.DecisionRefused as exc:
            filing_tui._show(str(exc), title=REFUSED_TITLE, style="red")
            if answers is not None:
                return None
            # A REFUSED COMBINATION SAYS WHICH RULE AND ASKS AGAIN, keeping
            # the answers to change (criterion 4).
            answers, reason = chosen, why_settle
            continue
        break

    # THE RUNS THAT FOLLOW, from the plan the warning was built from - the
    # owed ids come back in this order.
    with filing_tui.open_log() as conn:
        runs = [(f.file.filename, f.checked_in)
                for f in filing_decisions.settlement_plan(conn, request).runs]
    if shown.lines:
        filing_tui._show("\n".join(f"- {line}" for line in shown.lines),
                         title="This settlement also does", style="yellow")
    if not common.confirm_change(
            CONFIRM.format(dataset=name, period=period, person=people.actor_name(actor)),
            yes=yes, default=False,
            flag_hint=("pass --yes --acknowledge " + shown.key if shown.lines
                       else "pass --yes")):
        console.print("Not recorded.", style="yellow")
        return None
    if shown.lines and not yes:
        request = dataclasses.replace(request, acknowledged=shown.key)
    console.print(f"Recording - this waits up to {decision_log.LOCK_TIMEOUT} if a QA run or "
                  f"another decision is using these tables.", style="dim")
    try:
        outcome = filing_decisions.apply(request, effective_at=asset_time.now().isoformat())
    except (decision_log.DecisionRefused, filing_decisions.NotOffered,
            people.UnknownActor) as exc:
        # CRITERION 18: what changed is said; the person asks again.
        filing_tui._show(str(exc), title=REFUSED_TITLE, style="red")
        return None
    console.print(Panel(Text(outcome.message, style="bold green"), title="Recorded",
                        border_style="green", expand=False))
    results = _run_what_it_owed(outcome, runs, period)
    _closing_panel(chosen, results, period)
    filing_tui._follow_up(hierarchy.dataset(dataset_id).collection_id)
    filing_decisions.reconcile_after(outcome, hierarchy.dataset(dataset_id).collection_id)
    return outcome


def _run_what_it_owed(outcome, runs: list[tuple[str, str]], period: str) -> dict[str, str]:
    """The QA runs the settlement owed, one at a time while the person waits,
    with the QA wizard's own progress display labelled 'run N of M -
    {filename} for {period}' (criterion 20). Returns {filename: what came of
    it}. A run that fails says the settlement is recorded and the run owed -
    never to settle again."""
    from qa_tools.common import recheck

    out: dict[str, str] = {}
    total = len(outcome.owed)
    for n, (owed_id, (filename, target)) in enumerate(zip(outcome.owed, runs), 1):
        label = f"run {n} of {total} - {filename} for {target}"
        try:
            with common.chain_progress(label) as on_step:
                got = recheck.run(owed_id, on_step=on_step)
        except Exception as exc:  # noqa: BLE001 - said, and left owed
            got = recheck.Outcome(owed_id, "", False, f"{type(exc).__name__}: {exc}")
        if got.completed:
            out[filename] = got.message
        else:
            out[filename] = "not checked yet - owed"
            console.print(Panel(Text(
                f"The settlement is recorded. {label} did not finish ({got.message}), so it "
                f"is owed, and is finished by 'Process what has arrived' (mothman pipeline "
                f"process) or the next processing pass."),
                title="Run owed", border_style="yellow", expand=False))
    return out


def _closing_panel(chosen, results: dict[str, str], period: str) -> None:
    """One panel: each file's outcome, its QA status and what the gate did
    (criterion 20)."""
    lines = []
    for a in chosen:
        line = f"{a.filename}: {said(a, period)}"
        if a.filename in results:
            line += f" - {results[a.filename]}"
        lines.append(line)
    console.print(Panel(Text("\n".join(lines)), title="Settled", border_style="green",
                        expand=False))


def parse_outcome(token: str, filenames: list[str]) -> settlement.Answer:
    """One `--file-outcome '<filename>=<supply|refile:<period>|reject|supersede>'`
    (criterion 15), matched EXACTLY against the pair's recorded filenames -
    never split on '=' or ':' inside a filename."""
    import click

    for name in sorted(filenames, key=len, reverse=True):
        prefix = f"{name}="
        if not token.startswith(prefix):
            continue
        rest = token[len(prefix):]
        if rest in (SUPPLY, REJECT, SUPERSEDE):
            return settlement.Answer(name, rest)
        if rest.startswith(f"{REFILE}:") and rest[len(REFILE) + 1:]:
            return settlement.Answer(name, REFILE, rest[len(REFILE) + 1:])
        raise click.UsageError(
            f"{token!r}: the outcome must be supply, refile:<period>, reject or supersede.")
    raise click.UsageError(
        f"{token!r} names a file that is not in the pair - its files are "
        f"{' and '.join(filenames)}. Use --file-outcome '<filename>=...' with one of them.")
