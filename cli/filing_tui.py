"""The terminal's own route onto a filing decision (REQ-GHUB-082
criteria 2, 12, 15-19, 28, 30 and 31).

AN ADAPTER, THE SAME SIZE AS THE OTHER ONE. Everything a decision MEANS
lives in `qa_tools/common/filing_decisions.py`, once, because criterion
3 says the two routes must write an identical entry and criterion 24
says they must never disagree about what is permitted. What is here is
the two things that are genuinely a terminal's: finding out who is at
the keyboard and what they want, and saying plainly what came back.

THE SHAPE OF THE MENU, which Keith left to this session's judgement
(2026-09-29: "happy for you to make a decision on how that looks... just
make your best judgment call"). Three doors, and the split between the
first two is criterion 31 rather than taste:

  Supplies waiting on a decision   the standing queue (criterion 16) -
                                   something arrived, what happens to it
  Decide about a period            any slot, reached by dataset and
                                   period (criterion 31)
  Where every period stands        read-only (criterion 18)

THE CONSTRAINT IS ONE-WAY, and getting that wrong cost a door. Criterion
31 says the four period-scoped operations are reached per period and
dataset RATHER THAN FROM THE SUPPLY QUEUE - somebody working through
arrivals should never be offered "inherit", because inheriting is what
you do when there is no arrival. It says nothing against the reverse,
and the reverse is necessary: a DEMOTE acts on a supply, and a promoted
slot is not awaiting a decision, so it is never in the queue. Offering
only the period-scoped four here left demote reachable from no wizard
door at all. So the queue is supply-scoped only and the period door
offers whatever applies to the slot in front of you.

The third door exists because a person about to decide something wants
to see what is already true, and because the decision log alone does not
answer it - a log is a list of events, and "where does this period
stand" is what those events resolve to.

IT CALLS NO GITHUB (criterion 30). The decision goes into the log and
the ticket is brought up to date by REQ-PIPE-083's own pass, which is
also why a slot with no ticket at all is decidable from here
(criterion 12) - nothing is opened to carry a decision that has
somewhere better to live.

IT NEVER SHOWS A CACHED ANSWER (criterion 19). Where the log cannot be
read, this says so and shows nothing, because a person acts on what a
filing screen tells them and a stale one is worse than a blank one.
"""
from __future__ import annotations

import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from cli import common
from qa_tools.common import (asset_time, decision_log, filing_decisions,
                             filing_queue, git_identity, hierarchy, people,
                             qa_store, slot_state, supply_db)

console = Console()

_MENU_QUEUE = "Supplies waiting on a decision"
_MENU_PERIOD = "Decide about a period - pick a dataset and a period"
_MENU_STANDING = "Where every period stands"

_FLAG_HINT = ("mothman supply decide --operation <op> --dataset <id> "
              "--period <period> --reason '<why>'")

#: How each operation reads to somebody choosing one. The log's own
#: action names are the vocabulary (`filing_decisions` keeps them
#: deliberately), so this adds the sentence rather than a second word.
_WHAT_IT_DOES = {
    filing_decisions.PROMOTE: "promote - this supply becomes the period's data",
    filing_decisions.REJECT: "reject - this supply is not fit, and the period stays empty",
    filing_decisions.DEMOTE: "demote - take the promoted supply back out",
    filing_decisions.REFILE: "re-file - move this supply to a different period",
    filing_decisions.SUBSTITUTE: "substitute - this period stands on an earlier one",
    filing_decisions.DE_SUBSTITUTE: "de-substitute - remove the substitution",
    filing_decisions.INHERIT: "inherit - nothing was owed, so carry the last one forward",
    filing_decisions.UN_INHERIT: "un-inherit - remove the inheritance",
    filing_decisions.MARK_NOT_SUPPLIED: ("mark as not supplied - accept that this closed "
                                         "period was missed, with a reason"),
}

_HOW_IT_READS = {
    slot_state.NOT_YET_DUE: "[dim]not yet due[/dim]",
    slot_state.OVERDUE: "[yellow]overdue[/yellow]",
    slot_state.NEVER_SUPPLIED: "[red]never supplied[/red]",
    slot_state.AWAITING_DECISION: "[yellow]awaiting a decision[/yellow]",
    slot_state.RETURNED: "[yellow]returned by a person[/yellow]",
    slot_state.HELD: "[yellow]held - which file is the supply?[/yellow]",
    slot_state.PROMOTED: "[green]promoted[/green]",
    slot_state.REJECTED: "[red]rejected[/red]",
    slot_state.SUBSTITUTED: "[blue]substituted[/blue]",
    slot_state.INHERITED: "[blue]inherited[/blue]",
    slot_state.NOT_SUPPLIED_ACCEPTED: "[dim]not supplied (accepted)[/dim]",
    filing_queue.COULD_NOT_LOAD: "[red]could not be loaded[/red]",
}


def _collections() -> list[str]:
    return sorted({d.collection_id for d in hierarchy.all_datasets()})


def _collection_name(collection_id: str) -> str:
    for d in hierarchy.all_datasets():
        if d.collection_id == collection_id:
            return d.collection_name
    return collection_id


def actor_at_the_keyboard() -> dict:
    """Who is deciding, from the identity this tool already has.

    THE GIT EMAIL, and no second notion of identity (criterion 14).
    `git_identity.get_run_by()` is what stamps every QA run, and
    `contract/people.yaml` keys a person by exactly that address - so
    the allowlist is checked against something the operator has already
    configured rather than something this flow has to ask for.
    """
    return people.person_by_email(git_identity.get_run_by())


def open_log() -> supply_db.SupplyConnection:
    """The decision log, or criterion 19's refusal.

    NO FALLBACK EXISTS TO TAKE, which is how the criterion is kept
    rather than remembered.
    """
    try:
        conn = supply_db.connect(read_only=True, label="mothman:filing-tui")
        qa_store.ensure_schema(conn)
        return conn
    except supply_db.SupplyDbError as exc:
        raise filing_queue.LogUnreachable(str(exc)) from exc


def say_unreachable(exc: Exception) -> None:
    console.print(Panel(
        Text.assemble(
            ("The decision log cannot be read, so this cannot tell you where "
             "anything stands.\n\n", "bold red"),
            (f"{exc}\n\n", "red"),
            ("Nothing cached or exported is shown in its place: a filing "
             "screen is acted on, and a stale one is worse than a blank one.",
             "dim")),
        title="Unreachable", border_style="red", expand=False))


# ---------------------------------------------------------------------------
# Applying one decision. THE ONLY WRITE PATH IN THIS MODULE, and every
# door above funnels into it, so the confirmation criterion 28 requires
# cannot be missed by one screen.
# ---------------------------------------------------------------------------

def apply_decision(*, operation: str, dataset_id: str, period: str,
                   supply: str | None = None, stands_on: str | None = None,
                   to_period: str | None = None, reason: str | None = None,
                   actor: dict | None = None,
                   yes: bool = False) -> filing_decisions.Outcome | None:
    """Collect what is missing, confirm, apply, and say what happened.

    RETURNS None WHERE NOTHING WAS APPENDED and an Outcome where the
    decision went through - including one whose `changed` is False,
    which is a success (criterion 26). A caller that needs an exit code
    needs those two apart: a refusal is a failure and "already so" is
    not.


    THE CONFIRMATION IS UNCONDITIONAL (criterion 28), not reserved for
    the destructive three. A person in a terminal has just picked a line
    out of a list, and the distance between "promote" and "reject" is
    one arrow key. `--yes` skips the prompt for the scripted form, which
    is the same bypass every other write in this CLI offers - and is not
    the same thing as `confirmed`, which the underlying operation
    requires for its own reasons and which this sets from the same act.
    """
    try:
        actor = actor or actor_at_the_keyboard()
    except people.UnknownActor as exc:
        console.print(f"[red]Refused:[/red] {exc}")
        return None

    if reason is None:
        reason = common.text_prompt(
            f"Why are you recording this {operation}?", flag_hint=_FLAG_HINT)
        if reason is None:
            console.print("No reason given - nothing recorded.", style="yellow")
            return None

    where = f"{dataset_id} {period}" + (f" -> {to_period}" if to_period else "")
    if not common.confirm(f"Record {operation} for {where}, as {people.actor_name(actor)}?",
                           yes=yes, default=False):
        console.print("Not recorded.", style="yellow")
        return None

    request = filing_decisions.Request(
        operation=operation, dataset_id=dataset_id, actor=actor, reason=reason,
        period=period, to_period=to_period, supply=supply, stands_on=stands_on,
        confirmed=True)
    try:
        outcome = filing_decisions.apply(
            request, effective_at=asset_time.now().isoformat())
    except (decision_log.DecisionRefused, filing_decisions.NotOffered,
            people.UnknownActor) as exc:
        # CRITERION 22: told why, on the route it was raised on. And
        # criterion 25's remedy comes through unchanged - the refusal
        # decision_log raises already names the de-substitute or
        # un-inherit that would unblock it, so repeating it here would
        # be a second copy of a sentence that must not drift.
        console.print(Panel(Text(str(exc)), title=f"{operation} refused",
                             border_style="red", expand=False))
        return None

    if outcome.changed:
        console.print(Panel(Text(outcome.message, style="bold green"),
                             title="Recorded", border_style="green", expand=False))
        filing_decisions.reconcile_after(
            outcome, hierarchy.dataset(dataset_id).collection_id)
    else:
        # CRITERION 26: a no-op is not a refusal, and must not look like
        # one. Two people working the same ticket arrive here constantly.
        console.print(Panel(Text(outcome.message), title="Already so",
                             border_style="blue", expand=False))
    return outcome


# ---------------------------------------------------------------------------
# The three doors.
# ---------------------------------------------------------------------------

def arrived(supply: str | None) -> str:
    """When the supply arrived, from the key its id carries.

    THE KEY RATHER THAN THE WHOLE ID, because the id is
    `<dataset>@<20 digits>` and both halves are already on the row - the
    dataset in its own column and the digits as this. A column of
    `cp-investigations@20230501010000000000` truncates to nothing useful
    at any terminal width, and what a person reads it for is when the
    thing turned up.
    """
    key = filing_queue.arrival_key_of(supply or "")
    if len(key) >= 12 and key.isdigit():
        return f"{key[0:4]}-{key[4:6]}-{key[6:8]} {key[8:10]}:{key[10:12]}"
    return key or "-"


def _who_decided(state: slot_state.SlotState) -> str:
    """Who decided, or nobody.

    "A RULE" IS ONLY SAID WHERE SOMETHING WAS DECIDED (criterion 34).
    `SlotState.decided_by` is None both for an automatic decision and
    for a slot nobody has touched, and rendering both as "a rule" would
    tell a reader that a supply sitting in the queue had already been
    dealt with by one.
    """
    if state.decided_by:
        return state.decided_by
    return ("[dim]a rule[/dim]" if state.state in filing_queue.FROM_A_DECISION
            else "[dim]-[/dim]")


def _short(reason: str, limit: int = 48) -> str:
    """One line of a reason, at most.

    AN AUTOMATIC PROMOTION'S REASON IS ONE LONG SENTENCE repeated on
    every row it applies to, and letting it wrap turns a fifteen-period
    table into three screens of the same words. `mothman supply
    decisions` is where a reason is read in full; this column is for
    telling one row from another.
    """
    text = (reason or "").strip()
    if not text:
        return "[dim]-[/dim]"
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "\u2026"


def queue_table(states) -> Table:
    table = Table("Period", "Dataset", "Arrived", "State", box=None, pad_edge=False)
    for s in states:
        table.add_row(s.period, s.dataset_id,
                       arrived(s.supply) if s.supply else "[dim]-[/dim]",
                       _HOW_IT_READS.get(s.state, s.state))
    return table


def _label(state: slot_state.SlotState) -> str:
    where = f"arrived {arrived(state.supply)}" if state.supply else "nothing arrived"
    return f"{state.period}  {state.dataset_id}  {where}  ({state.state})"


def _pick_slot(states, message: str) -> slot_state.SlotState | None:
    by_label = {_label(s): s for s in states}
    choice = common.select(message, list(by_label), flag_hint=_FLAG_HINT)
    return by_label.get(choice) if choice else None


def _decide_on(state: slot_state.SlotState, *, offer: tuple[str, ...]) -> None:
    """Offer this slot's operations and carry one out.

    WHAT IS OFFERED COMES FROM `filing_queue.operations_for`, so the
    queue, the period door and the after-a-run offer cannot disagree
    about what is possible on the same slot.
    """
    if not offer:
        console.print("There is nothing to decide about this one.", style="dim")
        return
    if state.state == filing_queue.COULD_NOT_LOAD:
        # The recorded reason, and the response that is not a control.
        console.print(f"{state.supply} could not be loaded: {state.reason}. Reject it "
                       f"here, or {filing_queue.REPROCESS}.", style="yellow")
    by_label = {_WHAT_IT_DOES[op]: op for op in offer}
    picked = common.select(f"{state.dataset_id} {state.period} - what are you "
                            f"recording?", list(by_label), flag_hint=_FLAG_HINT)
    if picked is None:
        return
    operation = by_label[picked]

    to_period = stands_on = None
    if operation == filing_decisions.REFILE:
        to_period = common.text_prompt("Which period should it move to?",
                                        flag_hint=_FLAG_HINT)
        if to_period is None:
            return
    if operation == filing_decisions.SUBSTITUTE:
        stands_on = common.text_prompt(
            "Which earlier period should this one stand on?", flag_hint=_FLAG_HINT)
        if stands_on is None:
            return

    apply_decision(operation=operation, dataset_id=state.dataset_id,
                    period=state.period, supply=state.supply,
                    stands_on=stands_on, to_period=to_period)


def queue_flow(collection_id: str) -> None:
    """The standing queue (criterion 16) - what is waiting on a person.

    ONLY THE SUPPLY-SCOPED FOUR ARE REACHED FROM HERE (criterion 31).
    """
    try:
        with open_log() as conn:
            waiting = filing_queue.awaiting(conn, collection_id)
            gaps = filing_queue.closed_gaps(conn, collection_id)
    except filing_queue.LogUnreachable as exc:
        say_unreachable(exc)
        return

    if gaps:
        # PERIOD ITEMS, GROUPED (REQ-PIPE-132 criterion 11): consecutive
        # closed, unfilled periods of one dataset are one line naming the
        # count and the range, with what a person can do about them.
        table = Table("Dataset", "No supply", "What you can do", box=None, pad_edge=False)
        for gap in gaps:
            table.add_row(gap.dataset_id, gap.describe(),
                          "; ".join(slot_state.CLOSED_RESPONSES))
        console.print(f"[bold]{len(gaps)}[/bold] closed period item(s) with no supply in "
                       f"{_collection_name(collection_id)} - {slot_state.CLOSED_NOTE}.\n")
        console.print(table)
        console.print("[dim]Answer one from the period door, or `mothman supply decide "
                       "--operation mark-not-supplied --dataset <id> --period <p> "
                       "--reason <why>`.[/dim]\n")
    if not waiting:
        if not gaps:
            console.print(f"Nothing is waiting on a person in "
                           f"{_collection_name(collection_id)}.", style="green")
        return
    console.print(f"[bold]{len(waiting)}[/bold] supply/supplies waiting on a "
                   f"decision in {_collection_name(collection_id)}\n")
    console.print(queue_table(waiting))
    console.print()
    state = _pick_slot(waiting, "Which one?")
    if state is None:
        return
    supply_scoped, _period_scoped = filing_queue.operations_for(state)
    _decide_on(state, offer=supply_scoped)


def period_flow(collection_id: str) -> None:
    """Any slot, reached by dataset and period (criterion 31).

    EVERY PERIOD, not only the overdue ones - criterion 12 is that a
    period quietly awaiting a supply that is not yet late is still
    decidable from the terminal, and no ticket is opened to carry that
    decision.

    AND EVERYTHING THAT APPLIES TO THE SLOT, supply-scoped included.
    Criterion 31 keeps the period-scoped four OUT OF THE QUEUE; it does
    not keep the supply-scoped four out of here, and it cannot, because
    a demote acts on a promoted slot and a promoted slot is never in the
    queue. This is where you take a supply back out.
    """
    datasets = [d.dataset_id for d in hierarchy.datasets_in_collection(collection_id)]
    dataset_id = common.select("Which dataset?", datasets, flag_hint=_FLAG_HINT)
    if dataset_id is None:
        return
    try:
        with open_log() as conn:
            states = filing_queue.slots_of(conn, collection_id, dataset_id=dataset_id)
    except filing_queue.LogUnreachable as exc:
        say_unreachable(exc)
        return
    if not states:
        console.print(f"{dataset_id} has no periods yet.", style="yellow")
        return
    state = _pick_slot(states, f"Which period of {dataset_id}?")
    if state is None:
        return
    supply_scoped, period_scoped = filing_queue.operations_for(state)
    _decide_on(state, offer=supply_scoped + period_scoped)


def standing_view(collection_id: str, dataset_id: str | None = None) -> None:
    """Where every period stands (criterion 18).

    WHICHEVER ROUTE RECORDED EACH DECISION. This resolves the log rather
    than listing it, which is the difference between `mothman supply
    decisions` and this: one says what happened, this says what is true.
    """
    try:
        with open_log() as conn:
            states = filing_queue.slots_of(conn, collection_id, dataset_id=dataset_id)
    except filing_queue.LogUnreachable as exc:
        say_unreachable(exc)
        return
    if not states:
        console.print("No periods to show.", style="yellow")
        return
    table = Table("Period", "Dataset", "State", "Arrived", "Decided by", "Why",
                   box=None, pad_edge=False)
    for s in states:
        table.add_row(s.period, s.dataset_id, _HOW_IT_READS.get(s.state, s.state),
                       arrived(s.supply) if s.supply else "[dim]-[/dim]",
                       _who_decided(s), _short(s.reason))
    console.print(f"[bold]{len(states)}[/bold] period(s) in "
                   f"{_collection_name(collection_id)}"
                   + (f", {dataset_id}" if dataset_id else "") + "\n")
    console.print(table)


def filing_menu() -> None:
    """The TUI's filing-decisions door, off the main menu.

    A COLLECTION FIRST, because a slot belongs to one and a queue
    spanning all of them would be the thing this project's own scale
    note warns about: at thirty datasets, one undifferentiated list is
    what people stop reading.
    """
    collections = _collections()
    collection_id = (collections[0] if len(collections) == 1 else
                      common.select("Which collection?", collections, flag_hint=_FLAG_HINT))
    if collection_id is None:
        return
    while True:
        choice = common.select(
            f"{_collection_name(collection_id)} - what are you doing?",
            [_MENU_QUEUE, _MENU_PERIOD, _MENU_STANDING], flag_hint=_FLAG_HINT)
        if choice is None:
            return
        console.print()
        if choice == _MENU_QUEUE:
            queue_flow(collection_id)
        elif choice == _MENU_PERIOD:
            period_flow(collection_id)
        else:
            standing_view(collection_id)
        console.print()


def offer_after_run(collection_id: str, run_key: str) -> None:
    """Criterion 17: a run that leaves its supply awaiting a decision
    offers that decision in its own flow.

    THROUGH THE SAME IMPLEMENTATION THE STANDING QUEUE USES, which the
    criterion says in as many words and which is why this is eight lines
    rather than a screen of its own.

    SILENT WHERE THERE IS NOTHING TO DECIDE, and silent where the log
    cannot be read: a person who has just finished a QA run is being
    shown their results, and an error about a queue they did not ask for
    would bury them. The standing queue says so properly when they go
    looking.
    """
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return
    try:
        with open_log() as conn:
            waiting = filing_queue.from_run(conn, collection_id, run_key)
    except (filing_queue.LogUnreachable, supply_db.SupplyDbError):
        return
    if not waiting:
        return
    console.print()
    console.print("[bold]This run's supply is waiting on a decision.[/bold]")
    console.print(queue_table(waiting))
    if not common.confirm("Decide about it now?", yes=False, default=False):
        console.print("Left in the queue - `mothman supply queue` when you are "
                       "ready.", style="dim")
        return
    state = waiting[0] if len(waiting) == 1 else _pick_slot(waiting, "Which one?")
    if state is None:
        return
    supply_scoped, _period_scoped = filing_queue.operations_for(state)
    _decide_on(state, offer=supply_scoped)
