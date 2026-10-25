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

import dataclasses

import re

import sys

import rich_click as click

from rich.console import Console
from rich.panel import Panel
from rich.markup import escape
from rich.table import Table
from rich.text import Text

from cli import common
from qa_tools.common import (asset_time, decision_log, filing_decisions,
                             filing_queue, git_identity, hierarchy, inheritance, people,
                             qa_store, slot_state, substitution, supply_db)

console = Console()

_MENU_QUEUE = "Supplies waiting on a decision"
_MENU_PERIOD = "Decide about a period - pick a dataset and a period"
_MENU_STANDING = "Where every period stands"

_FLAG_HINT = ("mothman supply decide --operation <op> --dataset <id> "
              "--period <period> --reason '<why>' --yes (plus --acknowledge KEY where "
              "the decision's warning gives one)")

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
    # REQ-PIPE-280 criterion 8: the one description, shared with --help.
    # WITHIN 80 COLUMNS WITH THE POINTER (CLI UX critic minor, #267): the
    # --help description in full wrapped mid-word in the choice list.
    filing_decisions.CARRY_FORWARD: "carry forward - inherit the newest promoted supply",
    filing_decisions.MARK_NOT_SUPPLIED: ("mark as not supplied - accept that this closed "
                                         "period was missed, with a reason"),
    filing_decisions.ACKNOWLEDGE: ("acknowledge - say you have looked at this amber "
                                   "supply and why it is acceptable"),
    filing_decisions.SUPERSEDE: ("supersede - set this supply aside for a newer version; "
                                 "it is kept, and can be brought back"),
    filing_decisions.UN_SUPERSEDE: ("un-supersede - bring a superseded version back to be "
                                    "checked again"),
    filing_decisions.EXCUSE_LATENESS: ("excuse lateness - it stays late, shown as excused, "
                                       "with your reason"),
    filing_decisions.WITHDRAW_EXCUSE: ("withdraw the excuse - it reads late and not excused "
                                       "again"),
    # NEVER 'choose-file' ON A SCREEN (REQ-PIPE-193 criterion 27).
    filing_decisions.CHOOSE_FILE: "settle - say what each file is",
    # REACHED FROM A HELD SUPPLY'S ROW (REQ-PIPE-163 criterion 10), never a slot's.
    filing_decisions.PLACE: "place - say which period this held supply belongs to",
    # WHAT IT DOES AND WHAT IT COSTS (REQ-PIPE-164 criterion 26).
    filing_decisions.RECHECK: ("Re-check: run its checks again where it is (about a "
                               "minute; recorded and published)"),
    # REQ-PIPE-166: each takes back an annotation, and can be recorded again.
    filing_decisions.WITHDRAW_ACKNOWLEDGEMENT: ("withdraw the acknowledgement - it needs a "
                                                "person again, and stays in its history"),
    filing_decisions.WITHDRAW_NOT_SUPPLIED: ("withdraw the mark as not supplied - the "
                                             "period reads missed again"),
}

#: The same operations on ANOTHER VERSION WAITING in a promoted period
#: (#113): there the period keeps its promoted supply whatever is decided
#: about this one, and the waiting one is usually the newer.
_WHAT_IT_DOES_TO_ANOTHER_VERSION = {
    filing_decisions.PROMOTE: ("promote - this version becomes the period's data; the "
                               "promoted one is set aside as superseded"),
    filing_decisions.REJECT: ("reject - this version is not fit; the period keeps the "
                              "one already promoted"),
    filing_decisions.SUPERSEDE: ("supersede - set this version aside without rejecting "
                                 "it; the period keeps the one already promoted"),
}

#: The operations that act on one SUPPLY, so the confirmation names it -
#: a period can hold one supply and have another waiting (#113).
_NAMES_THE_SUPPLY = (filing_decisions.PROMOTE, filing_decisions.REJECT,
                     filing_decisions.DEMOTE, filing_decisions.SUPERSEDE,
                     filing_decisions.UN_SUPERSEDE, filing_decisions.ACKNOWLEDGE,
                     filing_decisions.REFILE, filing_decisions.EXCUSE_LATENESS,
                     filing_decisions.WITHDRAW_EXCUSE, filing_decisions.PLACE,
                     filing_decisions.RECHECK, filing_decisions.WITHDRAW_ACKNOWLEDGEMENT)

#: How an operation reads as a NOUN in a prompt - "this acknowledge" was
#: the verb doing a noun's job (#107).
_NOUN = {filing_decisions.ACKNOWLEDGE: "acknowledgement", filing_decisions.REFILE: "re-file",
         filing_decisions.PLACE: "placement",
         filing_decisions.EXCUSE_LATENESS: "excuse",
         filing_decisions.WITHDRAW_EXCUSE: "withdrawal of the excuse",
         filing_decisions.RECHECK: "re-check",
         filing_decisions.WITHDRAW_ACKNOWLEDGEMENT: "withdrawal of the acknowledgement",
         filing_decisions.WITHDRAW_NOT_SUPPLIED: "withdrawal of the mark as not supplied"}

#: Decisions whose reason is PUBLISHED beside the supply on the dashboard
#: (REQ-PIPE-161 criterion 18), said when the reason is asked for.
_PUBLISHED_REASON = (filing_decisions.EXCUSE_LATENESS, filing_decisions.WITHDRAW_EXCUSE,
                     filing_decisions.PLACE,
                     # REQ-PIPE-164 criterion 14.
                     filing_decisions.RECHECK,
                     # REQ-PIPE-166 criterion 10.
                     filing_decisions.WITHDRAW_ACKNOWLEDGEMENT,
                     filing_decisions.WITHDRAW_NOT_SUPPLIED)

_HOW_IT_READS = {
    slot_state.NOT_YET_DUE: "[dim]not yet due[/dim]",
    slot_state.OVERDUE: "[yellow]overdue[/yellow]",
    slot_state.NEVER_SUPPLIED: "[red]never supplied[/red]",
    slot_state.AWAITING_DECISION: "[yellow]awaiting a decision[/yellow]",
    slot_state.RETURNED: "[yellow]returned by a person[/yellow]",
    slot_state.TWO_FILES: "[yellow]two files arrived - say what each file is[/yellow]",
    slot_state.PROMOTED: "[green]promoted[/green]",
    slot_state.REJECTED: "[red]rejected[/red]",
    slot_state.SUBSTITUTED: "[blue]substituted[/blue]",
    slot_state.INHERITED: "[blue]inherited[/blue]",
    # REQ-PIPE-280 criterion 1: an opened period owing nothing, carrying nothing.
    filing_queue.CARRIES_NOTHING: "[yellow]owes nothing, carries nothing forward[/yellow]",
    slot_state.NOT_SUPPLIED_ACCEPTED: "[dim]not supplied (accepted)[/dim]",
    # REQ-PIPE-122 criteria 17 and 18: each distinguishable from a red
    # supply awaiting a decision, and the first never called "held".
    slot_state.AMBER_WAITING: "[yellow]amber, waiting for a person (amber setting: hold)[/yellow]",
    slot_state.AWAITING_ACKNOWLEDGEMENT: "[yellow]promoted, awaiting acknowledgement[/yellow]",
    filing_queue.COULD_NOT_LOAD: "[red]could not be loaded[/red]",
    filing_queue.ANOTHER_VERSION_WAITING:
        "[yellow]another version waiting - the period holds a promoted one[/yellow]",
    # REQ-PIPE-164 criterion 15 - _words() gives its new verdict from the reason.
    filing_queue.RECHECKED_WORSE: "[red]Promoted, then re-checked worse[/red]",
    # REQ-GHUB-229: a version set aside, listed among its period's supplies.
    filing_queue.SUPERSEDED: "[dim]superseded[/dim]",
}

#: A SUPPLY LISTED AMONG ITS PERIOD'S (REQ-GHUB-229 criterion 5) - in words
#: about that supply rather than about the period, which is what
#: _HOW_IT_READS says. Never a raw state or operation name.
_LISTED_AS = {
    # IN PLACE IN THE WAREHOUSE, saying where (REQ-DASH-277 criterion 2).
    slot_state.PROMOTED: "in place in the warehouse (promoted)",
    slot_state.AWAITING_ACKNOWLEDGEMENT: "in place in the warehouse, awaiting acknowledgement",
    slot_state.AWAITING_DECISION: "waiting on a decision",
    slot_state.RETURNED: "taken back out by a person, waiting on a decision",
    slot_state.AMBER_WAITING: "amber and held for a person",
    filing_queue.ANOTHER_VERSION_WAITING: "waiting behind the promoted supply",
    filing_queue.COULD_NOT_LOAD: "could not be loaded",
    slot_state.REJECTED: "rejected",
    filing_queue.SUPERSEDED: "superseded",
    slot_state.TWO_FILES: "an open pair",
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
        title="Decision log not available", border_style="red", expand=False))


# ---------------------------------------------------------------------------
# Applying one decision. THE ONLY WRITE PATH IN THIS MODULE, and every
# door above funnels into it, so the confirmation criterion 28 requires
# cannot be missed by one screen.
# ---------------------------------------------------------------------------

def _consequences(request) -> "filing_decisions.Consequences":
    """The warning for this request, read now - or none where the log
    cannot be read, in which case apply() refuses with it anyway.

    RAISES DecisionRefused where the decision cannot happen at all, so the
    person is told before being asked (post-build-review #112)."""
    try:
        with open_log() as conn:
            return filing_decisions.consequences(conn, request)
    except decision_log.DecisionRefused:
        raise
    except Exception:  # noqa: BLE001 - apply() is the authority and says why
        return filing_decisions.Consequences(lines=())


def _show(text: str, *, title: str, style: str) -> None:
    """A panel of prose, with every command in it printed BELOW the panel,
    one per line and never wrapped - inside a bordered panel a terminal
    copy picks up the border and the line breaks (post-build-review #112)."""
    prose, commands = [], []
    for line in text.split("\n"):
        (commands if line.strip().startswith("mothman ") else prose).append(line)
    console.print(Panel(Text("\n".join(prose).rstrip()), title=title, border_style=style,
                        expand=False))
    for command in commands:
        console.print(command.strip(), soft_wrap=True, highlight=False, markup=False)


def _refused(exc: Exception, operation: str, *, flag_route: bool) -> None:
    """A refusal in its panel. On the FLAG route, a plain decision refused on
    an open pair also prints the settle form below the panel, with the
    pair's real filenames filled in (REQ-PIPE-193 criterion 25) - _show()
    puts every `mothman` line below the panel, never wrapped."""
    text = str(exc)
    if flag_route and isinstance(exc, filing_decisions.OpenPair):
        text += ("\nmothman supply decide --operation choose-file "
                 f"--dataset {exc.dataset_id} --period {exc.period} "
                 + " ".join(f"--file-outcome '{f}=<supply|refile:<period>|reject|supersede>'"
                            for f in exc.files)
                 + " --reason '<why>'")
    _show(text, title=f"{operation} refused", style="red")
    if flag_route and getattr(exc, "exit_code", None) == filing_decisions.EXIT_TRY_LATER:
        # NOTHING CHANGED, TRY LATER (REQ-PIPE-276 criterion 20): a lock wait
        # that timed out exits 75 as every other 'try later' refusal does.
        raise SystemExit(filing_decisions.EXIT_TRY_LATER)


def _gate_busy(exc, operation: str, *, flag_route: bool) -> None:
    """A decision a gate is deciding right now: said, nothing recorded, and
    on the flag route exit 75 (REQ-PIPE-266 criteria 15 and 16) - a script
    can tell 'wait and retry' from 'no'."""
    _show(str(exc), title=f"{operation} not recorded", style="yellow")
    if flag_route:
        raise SystemExit(filing_decisions.EXIT_TRY_LATER)


def apply_decision(*, operation: str, dataset_id: str, period: str | None,
                   supply: str | None = None, stands_on: str | None = None,
                   to_period: str | None = None, reason: str | None = None,
                   actor: dict | None = None,
                   yes: bool = False,
                   acknowledged: str | None = None,
                   through_period: str | None = None,
                   flag_route: bool = False,
                   wait: bool = False) -> filing_decisions.Outcome | None:
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
        _show(str(exc), title=f"{operation} refused", style="red")
        return None

    # NOT YET - A GATE IS DECIDING IT (REQ-PIPE-266 criteria 15 and 16):
    # refused before a reason is asked for, recording nothing; on the flag
    # route with exit 75, the 'try later' the processing pass already uses.
    try:
        filing_decisions.refuse_while_gated(filing_decisions.Request(
            operation=operation, dataset_id=dataset_id, actor=actor, reason="",
            period=period, to_period=to_period, supply=supply, stands_on=stands_on,
            through_period=through_period))
    except filing_decisions.GateBusy as exc:
        _gate_busy(exc, operation, flag_route=flag_route)
        return None
    except filing_queue.LogUnreachable as exc:
        say_unreachable(exc)
        return None
    except Exception:  # noqa: BLE001 - apply() checks again, under the locks, and says why
        pass
    if flag_route and supply and period and operation in (
            filing_decisions.PROMOTE, filing_decisions.REJECT, filing_decisions.SUPERSEDE):
        # REACHED BY NAMING IT, IT SAYS THE SAME AS THE DOOR (REQ-PIPE-210
        # criterion 4) before anything is decided - its own decisions stay
        # available on the same terms.
        note, _nothing = door_note(slot_state.SlotState(
            dataset_id=dataset_id, period=period, state=slot_state.AWAITING_DECISION,
            supply=supply))
        if note:
            _show(note, title=f"{dataset_id} {period}", style="yellow")
    # REFUSED BEFORE THE REASON IS ASKED FOR, where it cannot happen at all
    # (#113): a reason typed for a decision about to be refused is wasted.
    try:
        _consequences(filing_decisions.Request(
            operation=operation, dataset_id=dataset_id, actor=actor, reason="",
            period=period, to_period=to_period, supply=supply, stands_on=stands_on,
            through_period=through_period))
    except decision_log.DecisionRefused as exc:
        _refused(exc, operation, flag_route=flag_route)
        return None
    if operation == filing_decisions.CARRY_FORWARD and period:
        # NOTHING TO DO IS SAID BEFORE A REASON IS ASKED FOR (CLI UX critic M2,
        # #267) - in the 'Already so' panel, as criterion 6 has it.
        from qa_tools.common import carry_forward

        try:
            with open_log() as conn:
                p = carry_forward.plan(conn, dataset_id, period)
        except filing_queue.LogUnreachable as exc:
            say_unreachable(exc)
            return None
        if p.already:
            _show(carry_forward.already_words(p), title="Already so", style="blue")
            return filing_decisions.Outcome(operation=operation, dataset_id=dataset_id,
                                            period=period, changed=False,
                                            message=carry_forward.already_words(p))

    if reason is None:
        reason = common.text_prompt(
            f"Why are you recording this {_NOUN.get(operation, operation)}?"
            + ((" It is published on the dashboard, in the period's row."
                if operation in filing_decisions.PERIOD_SCOPED else
                " It is published beside the supply on the dashboard.")
               if operation in _PUBLISHED_REASON else ""),
            flag_hint=_FLAG_HINT)
        if reason is None:
            console.print("No reason given - nothing recorded.", style="yellow")
            return None

    where = f"{dataset_id}" + (f" {period}" if period else "") \
        + (f" -> {to_period}" if to_period else "") \
        + (f" to {through_period}" if through_period else "")
    if operation == filing_decisions.PLACE:
        # SAID AS A PLACEMENT (REQ-PIPE-163 criterion 41), never "None -> period".
        where = f"{dataset_id}, into {to_period}"
    if supply and operation in _NAMES_THE_SUPPLY:
        where += f" (the supply that arrived {arrived(supply)})"
    request = filing_decisions.Request(
        operation=operation, dataset_id=dataset_id, actor=actor, reason=reason,
        period=period, to_period=to_period, supply=supply, stands_on=stands_on,
        confirmed=True, acknowledged=acknowledged, through_period=through_period)

    # ONE WARNING PANEL ABOVE THE ONE CONFIRMATION (REQ-PIPE-128 criterion
    # 6): what this decision does beyond its own slot, and how each is
    # undone. None where it does nothing more. Confirming it IS the
    # acknowledgement - there is no second yes or no. A scripted `--yes`
    # does not acknowledge on its own: it needs `--acknowledge <key>`.
    previous: tuple[str, ...] = ()
    for _attempt in range(2):
        try:
            shown = _consequences(request)
        except decision_log.DecisionRefused as exc:
            _refused(exc, operation, flag_route=flag_route)
            return None
        if shown.lines:
            if previous:
                # WHAT CHANGED, said rather than left to be spotted in a
                # second panel identical but for one id (#112).
                console.print("[yellow]Somebody else's decision changed what this one "
                              "does while you were deciding. New:[/yellow]")
                for line in shown.lines:
                    if line not in previous:
                        console.print(f"  [bold]{line.split(chr(10))[0]}[/bold]")
            _show("\n".join(f"- {line}" for line in shown.lines),
                  title="This decision also does", style="yellow")
        if shown.notes and not previous:
            # WHAT IT TAKES BACK AND WHAT FOLLOWS (REQ-PIPE-166 criterion 14) -
            # said before the one confirmation, never keyed.
            notes, title = "\n".join(shown.notes), "What this does"
            if operation == filing_decisions.UN_INHERIT:
                # NOT WHAT UN-INHERIT DOES, but a better way to the same end
                # (CLI UX critic M3, #267) - and in the wizard, the way there is
                # the door, not a command to copy.
                title = "Instead"
                if not flag_route:
                    notes = "\n".join(
                        "Answer no here, and choose carry forward from the period's "
                        "door instead." if line.startswith("mothman ") else line
                        for line in notes.split("\n"))
            _show(notes, title=title, style="blue")
        # THE FIRST CONFIRMATION OF THE FLOW is the one where a production
        # change is typed (REQ-PIPE-093 criterion 4); a second pass here only
        # re-confirms consequences that changed underneath it, and asking for
        # the id again would be asking twice in one flow.
        ask = common.confirm if previous else common.confirm_change
        previous = shown.lines
        if not ask(f"Record {_NOUN.get(operation, operation)} for {where}, "
                   f"as {people.actor_name(actor)}?",
                   yes=yes, default=False,
                   flag_hint=("pass --yes --acknowledge " + shown.key
                              if shown.lines else "pass --yes")):
            console.print("Not recorded.", style="yellow")
            return None
        if shown.lines and not yes:
            request = dataclasses.replace(request, acknowledged=shown.key)
        # NEVER A SILENT WAIT (#113): a decision waits up to the lock
        # timeout for a run or another decision using the same tables.
        console.print(f"Recording - this waits up to {decision_log.LOCK_TIMEOUT} if a QA "
                      f"run or another decision is using these tables.", style="dim")
        try:
            outcome = filing_decisions.apply(
                request, effective_at=asset_time.now().isoformat())
            break
        except filing_decisions.ConsequencesNotAcknowledged as exc:
            # CRITERION 9: the consequences changed between the warning and
            # the yes. Refused, and the new warning is shown to confirm.
            if yes or not shown.lines:
                # The warning is already on screen where it was shown, so
                # the refusal says only what is wrong and how to go ahead.
                body = (f"{exc.lead}\n{exc.instruction}" if shown.lines
                        and shown.key == exc.key else str(exc))
                _show(body, title=f"{operation} refused", style="red")
                return None
            continue
        except filing_decisions.GateBusy as exc:
            _gate_busy(exc, operation, flag_route=flag_route)
            return None
        except (decision_log.DecisionRefused, filing_decisions.NotOffered,
                people.UnknownActor, substitution.SubstitutionRefused,
                inheritance.InheritanceRefused) as exc:
            # CRITERION 22: told why, on the route it was raised on. And
            # criterion 25's remedy comes through unchanged - the refusal
            # decision_log raises already names the de-substitute or
            # un-inherit that would unblock it, so repeating it here would
            # be a second copy of a sentence that must not drift.
            _refused(exc, operation, flag_route=flag_route)
            return None
    else:
        # Changed twice while being decided - said, never a silent exit.
        console.print("Not recorded: what this decision does kept changing while you "
                      "were deciding. Look at the period again before deciding.",
                      style="yellow")
        return None

    if outcome.changed:
        # THROUGH _show, so a command in it - a promotion's 'available to carry
        # forward' line (K4) - prints below the panel, copyable.
        _show(outcome.message, title="Recorded", style="green")
        carried = (_readers_of(dataset_id, period)
                   if operation == filing_decisions.CARRY_FORWARD else None)
        if outcome.owed and flag_route and not wait:
            # THE FLAG ROUTE DOES NOT WAIT (REQ-PIPE-163 criteria 4 and 32):
            # the checks are owed, and the processing pass runs them.
            _show("Its checks are owed. The processing pass runs them - it runs every "
                  "owed QA run, not only this one:\nmothman pipeline process\n"
                  # REQ-PIPE-164 criterion 5.
                  "Nothing runs until the processing pass or that command does.",
                  title="Checks owed", style="yellow")
        elif outcome.owed:
            finished = all(_run_owed(owed_id, operation=operation, supply=supply,
                                     to_period=to_period or period)
                           for owed_id in outcome.owed)
            outcome = dataclasses.replace(outcome, checks_finished=finished)
        _follow_up(hierarchy.dataset(dataset_id).collection_id,
                   carried=(dataset_id, period, carried) if carried is not None else None)
        filing_decisions.reconcile_after(
            outcome, hierarchy.dataset(dataset_id).collection_id)
    else:
        # CRITERION 26: a no-op is not a refusal, and must not look like
        # one. Two people working the same ticket arrive here constantly.
        # Through _show, so a command in it (REQ-PIPE-280 criterion 8's
        # carry-forward hint) prints below the panel, copyable.
        _show(outcome.message, title="Already so", style="blue")
    return outcome


def _readers_of(dataset_id: str, period: str | None) -> list:
    """The other supplies whose cross-table checks read this dataset in this
    period - the ones a carry-forward re-checks (REQ-PIPE-280 criterion 5).
    Read after the decision, so they are the readers of what it carries now."""
    from qa_tools.common import knock_on, promotion

    if not period:
        return []
    try:
        with open_log() as conn:
            table = hierarchy.dataset(dataset_id).table
            return [r for r in knock_on.readers(conn, period, [table],
                                                promotion._declared_reads())
                    if r.dataset_id != dataset_id]
    except Exception:  # noqa: BLE001 - the follow-up says what it can
        return []


def _follow_up(collection_id: str, *, carried=None) -> None:
    """The knock-on of what the decision moved (REQ-PIPE-121): every period
    it moved a table into or out of re-evaluates its readers, and the gate
    looks at each waiting one again. Said only where something happened; a
    failure stays owed for the processing pass (criterion 14).

    A CARRY-FORWARD SAYS MORE (REQ-PIPE-280 criterion 8): `carried` is
    (dataset, period, readers), and every reader re-checked is listed with
    its outcome - or, where the re-evaluation could not run, 'Re-evaluation
    owed' with the command that runs it on a line of its own."""
    import contextlib
    import io

    from qa_tools.common import knock_on

    mine = _owed_for(carried[1]) if carried is not None else set()
    try:
        # THE KNOCK-ON'S OWN PROGRESS LINES ('knock-on: ...', a run's '--- ...
        # ---') are the pipeline's, not this follow-up's (CLI UX critic minor,
        # #267): what happened is said below, in the person's terms.
        with contextlib.redirect_stdout(io.StringIO()):
            done = knock_on.follow_up(collection_id)
    except Exception as exc:  # noqa: BLE001 - the decision stands either way
        if carried is not None:
            _say_carry_forward_owed(carried, str(exc))
            return
        console.print(f"The re-evaluation of the period's readers did not run ({exc}); "
                      "it stays owed.", style="yellow")
        return
    if carried is not None:
        # ONLY THIS PERIOD'S RE-EVALUATION (functional critic S6, #267): the
        # follow-up runs everything the collection owes, and another period's
        # failure is not why this carry-forward's readers are owed.
        failed = [o for o in done if not o.completed and o.owed_id in mine]
        if failed:
            _say_carry_forward_owed(carried, failed[0].message)
        else:
            _say_carry_forward_readers(carried)
        others = [o for o in done if not o.completed and o.owed_id not in mine]
        for outcome in others:
            console.print(Panel(Text(outcome.message), title="Re-evaluation owed",
                                border_style="yellow", expand=False))
        return
    regated = [r for o in done if o.completed for r in (o.regated or ())]
    if regated:
        # EVERY SUPPLY THE KNOCK-ON RE-GATED, WITH ITS OUTCOME (REQ-PIPE-276
        # criterion 10) - not only the ones left incomplete.
        _show("\n".join(regated_lines(regated)), title="Re-gated after this decision",
              style="green")
    for outcome in done:
        if not outcome.completed:
            # WHAT IT IS UNTIL THEN, AND WHAT FINISHES IT (criterion 14): each
            # in-warehouse supply red only for the owed re-check, in
            # REQ-DASH-204 criterion 7's sentence - never 're-checked worse'.
            said = _owed_recheck_lines(outcome.owed_id)
            _show("\n".join([outcome.message, *said]) if said else
                  f"{outcome.message}\nThe re-check runs on the next processing pass:\n"
                  f"mothman pipeline process", title="Re-evaluation owed", style="yellow")


def _owed_recheck_lines(owed_id: int) -> list[str]:
    """For an owed re-evaluation, each promoted reader of its period that
    reads red only for 'recheck-owed': '<dataset>: Not yet re-checked against
    the <dataset> promoted <instant>; the re-check runs on the next
    processing pass:' and the command on a line of its own."""
    from qa_tools.common import knock_on, promotion, recheck, supply_status

    try:
        with open_log() as conn:
            item = next((o for o in recheck.owed(conn) if o.id == owed_id), None)
            if item is None or not item.period:
                return []
            out = []
            for r in knock_on.readers(conn, item.period, list(item.tables or []),
                                      promotion._declared_reads()):
                if r.waiting:
                    continue
                owed = supply_status.red_only_for_recheck_owed(conn, r.dataset_id, r.supply)
                words = supply_status.recheck_owed_words(conn, owed) if owed else None
                if words:
                    out.append(f"{r.dataset_id}: {words}")
    except Exception:  # noqa: BLE001 - the panel says what it can
        return []
    return out + ["mothman pipeline process"] if out else []


def regated_lines(regated) -> list[str]:
    """One line per resulting outcome - the status in words and the gate's
    result in REQ-PIPE-276's words ('promoted by the rule', 'still held back
    - <reason>', 'still promoted') - naming up to eight datasets, red lines
    first (REQ-PIPE-276 criterion 10; REQ-PIPE-211 criterion 14). A red
    owed only a re-check is said as not yet re-checked (criterion 14)."""
    from cli import lifecycle_report
    from qa_tools.common import root_cause, supply_status

    outcomes: list[tuple[str, str, str]] = []
    try:
        with open_log() as conn:
            for dataset_id, supply, _period, status, result in regated:
                if result == "still held back":
                    why = root_cause.holdback_reason(conn, dataset_id, supply)
                    if why:
                        result = f"still held back - {re.sub(r'^Held back[^:]*: ', '', why)}"
                if status == "red" and supply_status.red_only_for_recheck_owed(
                        conn, dataset_id, supply):
                    status = "not yet re-checked"
                outcomes.append((dataset_id, status, result))
    except filing_queue.LogUnreachable:
        outcomes = [(d, st, res) for d, _s, _p, st, res in regated]
    # THE ONE RENDERER (lifecycle_report.outcome_lines), shared with a
    # settlement's outcome panel.
    return lifecycle_report.outcome_lines(outcomes)


def _owed_for(period: str | None) -> set[int]:
    """The ids of the re-evaluations owed for this period now - before the
    follow-up runs them - so its outcomes can be told from other periods'."""
    from qa_tools.common import recheck

    if not period:
        return set()
    try:
        with open_log() as conn:
            return {o.id for o in recheck.owed(conn)
                    if o.kind == recheck.REEVALUATE and o.period == period}
    except filing_queue.LogUnreachable:
        return set()


def _say_carry_forward_owed(carried, why: str) -> None:
    dataset_id, period, _readers = carried
    name = hierarchy.dataset(dataset_id).dataset_name
    _show(f"The readers of {name} in {period} were not re-checked yet ({why}). "
          f"Until they are, their checks of it read 'not yet re-checked', and nothing is "
          f"raised for them. The processing pass runs it:\nmothman pipeline process",
          title="Re-evaluation owed", style="yellow")


def _say_carry_forward_readers(carried) -> None:
    """Every reader re-checked, and what it reads now (criterion 8)."""
    from qa_tools.common import carry_forward, supply_status

    dataset_id, period, readers = carried
    name = hierarchy.dataset(dataset_id).dataset_name
    if not readers:
        console.print(f"No other dataset's checks read {name} in {period}, so there "
                      f"was nothing to re-check.", style="dim")
        return
    lines = []
    try:
        with open_log() as conn:
            for r in readers:
                status = supply_status.status(conn, r.dataset_id, r.supply) or "no verdict"
                # ONE DATE STYLE IN ONE FOLLOW-UP (CLI UX critic minor, #267):
                # the instant as the consequences above it say one.
                lines.append(f"- {hierarchy.dataset(r.dataset_id).dataset_name}, received "
                             f"{carry_forward.received(r.dataset_id, r.supply, conn)}: "
                             f"{status}")
    except Exception as exc:  # noqa: BLE001 - said, never a traceback
        lines.append(f"(their verdicts could not be read: {exc})")
    _show(f"Re-checked against the {name} carried forward into {period}:\n"
          + "\n".join(lines), title="Readers re-checked", style="green")


#: decide --wait's exit code where the decision stands and its checks are
#: still owed - the run failed, was stopped, or is being run elsewhere
#: (REQ-PIPE-163 criterion 28). Distinct from 0 and from 1.
CHECKS_STILL_OWED_EXIT = 3


def _run_owed(owed_id: int, *, operation: str = filing_decisions.REFILE,
              supply: str | None = None, to_period: str | None = None) -> bool:
    """The decision's re-check, run while the person waits (REQ-PIPE-140;
    Keith, 2026-10-05), ending with the one outcome panel (REQ-PIPE-163
    criteria 19 and 26). A run that breaks, or is stopped with Ctrl-C,
    leaves the decision recorded and the re-check owed, and says so - the
    processing pass finishes it. Returns whether the checks finished."""
    from qa_tools.common import recheck

    console.print("Checking it against its period - this runs the four QA tools and takes "
                  "a minute or so. Ctrl-C stops it; the decision stands either way.",
                  style="dim")
    try:
        got = recheck.run(owed_id, on_step=lambda label: console.print(f"  {label}",
                                                                     style="dim"))
    except recheck.RecheckRefused as exc:
        got = recheck.Outcome(owed_id, "", False, str(exc))
    except KeyboardInterrupt:
        # Criterion 29: no traceback - the decision stands, its checks owed.
        got = recheck.Outcome(owed_id, "", False, "stopped with Ctrl-C")
    text, title, style = outcome_panel(operation, supply, to_period, got)
    _show(text, title=title, style=style)
    return got.completed


_STANDS = {filing_decisions.PLACE: "placement", filing_decisions.REFILE: "re-file",
           filing_decisions.RECHECK: "re-check"}


def outcome_panel(operation: str, supply: str | None, period: str | None,
                  got) -> tuple[str, str, str]:
    """THE ONE OUTCOME PANEL for a placement, a re-file and a re-check
    (REQ-PIPE-163 criteria 19 and 26): where the supply now stands - its
    period, its verdict and what the gate did. Never 'rejected' or 'refused'
    for a gate outcome (criterion 20) - those words name a person's
    decision. Returns (text, title, style); a `mothman` line in the text is
    printed below the panel."""
    from qa_tools.common import recheck

    decision = _STANDS.get(operation, "decision")
    who = supply or "The supply"
    if got.completed and got.message == "already run":
        return (f"Its checks had already run, elsewhere. The {decision} stands; "
                f"`mothman supply decisions` shows what the gate did.", "Already checked", "blue")
    if not got.completed and got.message == recheck.CLAIMED_ELSEWHERE:
        # Criterion 30: no verdict shown.
        return (f"Its checks are being run elsewhere and will finish there. The {decision} "
                f"stands.", "Being run elsewhere", "blue")
    if not got.completed:
        why = _gate_words(got.message)
        return (f"The {decision} stands. Its checks did not finish ({why}), so they are "
                f"still owed - the processing pass will finish them:\nmothman pipeline "
                f"process", "Checks still owed", "yellow")
    where = got.period or period or "its period"
    if operation == filing_decisions.RECHECK:
        return _recheck_panel(who, where, got)
    lines = [f"{who} is filed to {where}, checked {got.status or 'without a verdict'}."]
    if operation == filing_decisions.PLACE:
        lines.append(f"It had not been checked in {where} before.")
    step = None
    if got.promoted:
        lines.append(f"The promotion gate promoted it into {where}.")
        why = _rule_promotion_words(who, got.period or period)
        if why:
            lines.append(f"It was {why}.")
    else:
        step = next_step(who, where)
        lines.append(f"It is waiting in {where}: filed, and nothing is lost. The promotion "
                     f"gate did not promote it - {_gate_words(got.waits_because or 'it waits for a person')}."
                     + ("" if step else " Promote or reject it next, at Filing decisions > "
                        "Supplies waiting on a decision."))
    style = ("green" if got.status in ("green", "amber") else
             "red" if got.status == "red" else "yellow")
    # THE NEXT STEP NEVER THROUGH _gate_words (REQ-PIPE-276 criterion 2):
    # 'turned down' is a person's decision, not a gate's outcome.
    return " ".join(lines) + (f"\n{step}" if step else ""), "Where it stands now", style


def _rule_promotion_words(supply: str | None, period: str | None) -> str | None:
    """REQ-PIPE-276 criterion 15 in the outcome panel - the kept report's
    own words (lifecycle_report.rechecked_promotion_words), never a copy."""
    from cli import lifecycle_report

    if not supply or "@" not in supply:
        return None
    try:
        with open_log() as conn:
            why = lifecycle_report.rechecked_promotion_words(
                conn, supply.split("@", 1)[0], supply)
    except Exception:  # noqa: BLE001 - the panel says what it can
        return None
    return f"promoted by the rule - {why}" if why else None


def next_step(supply: str | None, period: str | None) -> str | None:
    """REQ-PIPE-276 criteria 2 and 4 (REQ-PIPE-210 criteria 4 and 6): for a
    supply held back because of another supply, the next step - while that
    other supply is waiting, ITS decision first, that nothing needs deciding
    on this one where its red is wholly that supply's doing, and the
    override as a complete command on a line of its own; once that supply
    has been turned down or replaced, this supply's own decision, worded
    from the decision log as it stands. None where it was held back by no
    other supply. A `mothman` line is printed below the panel by _show."""
    from qa_tools.common import display_time, filing, root_cause

    if not supply or "@" not in supply or not period:
        return None
    dataset_id = supply.split("@", 1)[0]
    try:
        with open_log() as conn:
            by = root_cause.held_back_by(conn, dataset_id, supply)
            if by is None:
                return None
            by_ds, by_supply, _came = by
            head = root_cause.turned_down_words(conn, dataset_id, supply)
            if head:
                return (head + " Promote or reject it next, at Filing decisions > Supplies "
                        "waiting on a decision.")
            if decision_log.promoted_into(conn, by_ds, period) == by_supply:
                # ITS CAUSE IS IN THE WAREHOUSE NOW and the re-check it owes this
                # supply has not run (REQ-PIPE-276 criterion 4): nothing to
                # decide first - the processing pass re-checks and re-gates it.
                got = filing.received_at_of(by_ds, by_supply, conn=conn)
                when = display_time.format_instant(got) if got else by_supply
                return (f"The {by_ds} it was held back by (received {when}) has been "
                        f"promoted into {period}; its re-check against it is owed and runs "
                        f"on the next processing pass:\nmothman pipeline process")
            wholly = root_cause.root_of(conn, dataset_id, supply, period) is not None
            got = filing.received_at_of(by_ds, by_supply, conn=conn)
            when = display_time.format_instant(got) if got else by_supply
    except filing_queue.LogUnreachable:
        return None
    lines = [f"Decide {by_ds} {period} (received {when}) - promoting it re-checks this one."]
    if wholly:
        lines.append("Nothing needs deciding on this supply.")
    lines.append("To override:")
    lines.append(override_command(dataset_id, period, supply))
    lines.append(f"or from the {period} door.")
    return "\n".join(lines)


def override_command(dataset_id: str, period: str, supply: str) -> str:
    """The override, complete but for the reason (REQ-PIPE-276 criterion 4;
    REQ-PIPE-210 criterion 3) - real dataset, period and supply."""
    return (f"mothman supply decide --operation promote --dataset {dataset_id} "
            f"--period {period} --supply {supply} --reason '<why>'")


def _recheck_panel(who: str, where: str, got) -> tuple[str, str, str]:
    """A re-check's outcome (REQ-PIPE-164 criteria 13 and 17): the verdict
    before and after, and what the gate did with a waiting supply - or, for a
    promoted one, that it stays promoted, naming demote and acknowledge where
    it came back red, each command on a line of its own."""
    lines = [f"{who} in {where} was {got.before or 'without a verdict'}, re-checked "
             f"{got.status or 'without a verdict'}."]
    if got.stays_promoted:
        lines.append(f"It is still promoted - {where} keeps it.")
        text = " ".join(lines)
        if got.status == "red":
            text += (f"\nTo take it out of {where}, demote it:\n"
                     f"mothman supply decide --operation demote --dataset "
                     f"{_dataset_of(who)} --period {where} --supply {who} --reason '<why>'\n"
                     f"To record that it stays, acknowledge its new verdict:\n"
                     f"mothman supply decide --operation acknowledge --dataset "
                     f"{_dataset_of(who)} --period {where} --supply {who} --reason '<why>'")
    elif got.promoted:
        lines.append(f"The promotion gate promoted it into {where}.")
        why = _rule_promotion_words(who, where)
        if why:
            lines.append(f"It was {why}.")
        text = " ".join(lines)
    else:
        step = next_step(who, where)
        lines.append(f"It is waiting in {where}. The promotion gate did not promote it - "
                     f"{_gate_words(got.waits_because or 'it waits for a person')}."
                     + ("" if step else " Promote or reject it next, at Filing decisions > "
                        "Supplies waiting on a decision."))
        # NEVER THROUGH _gate_words (REQ-PIPE-276 criterion 2).
        text = " ".join(lines) + (f"\n{step}" if step else "")
    style = ("green" if got.status in ("green", "amber") else
             "red" if got.status == "red" else "yellow")
    return text, "Where it stands now", style


def _dataset_of(supply: str) -> str:
    from qa_tools.common import supply_files

    return supply_files.dataset_of(supply)


def _gate_words(text: str) -> str:
    """A gate's own reason, in words that cannot be read as a person's
    decision (criterion 20)."""
    import re

    return re.sub(r"\b(refused|rejected)\b", "held back", text or "", flags=re.IGNORECASE)


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
    from qa_tools.common import asset_time, filing, supply_files

    key = filing_queue.arrival_key_of(supply or "")
    # ITS OWN FILE'S RECEIPT where it has one (REQ-PIPE-193 criterion 10,
    # post-build-review #170): a settled pair's supply may be the LATER
    # file, whose receipt is not the key its id carries.
    if supply and "@" in supply:
        own = filing.received_at_of(supply_files.dataset_of(supply), supply)
        if own is not None:
            key = asset_time.arrival_key(own)
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
                       # ITS OWN HEADING WITH BOTH VERDICTS AND THE RE-CHECK
                       # (REQ-PIPE-164 criterion 15; post-build-review #192 F1).
                       escape(s.reason) if s.state == filing_queue.RECHECKED_WORSE
                       and s.reason else _HOW_IT_READS.get(s.state, s.state))
    return table


def _own_red_words(conn, state) -> str:
    """'red - 3 of its own checks fail' for a root's own line (REQ-PIPE-276
    criterion 6), from its counted results - the slot's state in words where
    none of its own checks fails."""
    from qa_tools.common import promotion, supply_status

    words = re.sub(r"\[/?[a-z ]+\]", "", _HOW_IT_READS.get(state.state, state.state))
    if not state.supply:
        return words
    try:
        latest = supply_status.latest_results(conn, state.dataset_id, state.supply)
    except Exception:  # noqa: BLE001 - the state words stand
        return words
    own = [r for r in promotion._contributing_records(state.dataset_id, latest,
                                                      promotion._declared_reads())
           if not r.get("reads") and (r.get("status") or "") in ("fail", "error")]
    if not own:
        return words
    return ("red - 1 of its own checks fails" if len(own) == 1
            else f"red - {len(own)} of its own checks fail")


def queue_groups(conn, waiting, *, held=()):
    """The queue split once for every surface that shows it (REQ-PIPE-210
    criteria 7 and 8): root_cause.group_queue, the one function."""
    from qa_tools.common import root_cause

    try:
        return root_cause.group_queue(conn, waiting, held=held)
    except Exception as exc:  # noqa: BLE001 - the queue is still shown, every row counted
        # SAID, NEVER A BLANK QUEUE: a grouping that cannot be read leaves
        # every supply its own counted row, as before REQ-PIPE-210.
        console.print(f"The queue could not be grouped by cause ({type(exc).__name__}: "
                      f"{exc}); every supply is listed as its own row.", style="dim",
                      markup=False, highlight=False)
        return root_cause.QueueGroups(rows=list(waiting))


#: The supplier hint beneath a supply held back by a joined supply
#: (REQ-PIPE-276 criterion 19).
SUPPLIER_HINT = ("Files sent separately are gated as each arrives; sent as one zip they are "
                 "gated together (supplier guidance, REQ-DOCS-274).")


def say_queue(conn, groups, collection_id: str) -> None:
    """THE ONE RENDERER the Filing decisions queue and `mothman supply queue`
    share (REQ-PIPE-276 criteria 6 and 12; REQ-PIPE-210 criteria 1 to 3, 5,
    8 and 9): the counted rows in their table; beneath each root's item, the
    supplies it holds back, through lifecycle_report.beneath_lines, each with
    its override on a line of its own below the table; the lines a counted
    row carries; and each delivery still being gated as one quiet,
    uncounted line. Words, never colour alone; no Rich markup in any line
    that names a state (criterion 21)."""
    from cli import lifecycle_report
    from qa_tools.common import root_cause

    name = _collection_name(collection_id)
    plain = dict(markup=False, highlight=False)
    if groups.rows:
        head = (f"{groups.count} {'supply' if groups.count == 1 else 'supplies'} waiting "
                f"on a decision in {name}")
        if groups.listed_beneath:
            came = ("joined" if any(b.traced.came == "joined"
                                     for v in groups.beneath.values() for b in v)
                    else "package-mate")
            head += " " + lifecycle_report.header_more(groups.listed_beneath, came)
        console.print(head + "\n", **plain)
        console.print(queue_table(groups.rows))
        console.print()
    by_key = {root_cause.row_key(r): r for r in groups.rows}
    for key, lines in groups.lines.items():
        row = by_key.get(key)
        if row is None:
            continue
        for line in lines:
            console.print(f"{row.dataset_id}  {row.period}: {line}", **plain)
    if groups.lines:
        console.print()
    for key, members in groups.beneath.items():
        root = by_key.get(key)
        if root is None:
            # A HELD ROOT (filing_queue.HeldRow) - its own group above.
            root_line = f"{members[0].traced.root.dataset_id}  held - no period yet"
            root_name = members[0].traced.root.dataset_id
        else:
            root_line = (f"{root.dataset_id}  {root.period}  received {arrived(root.supply)}"
                         f"  {_own_red_words(conn, root)}")
            root_name = root.dataset_id
        rows = []
        for b in members:
            why = (b.reason or "").strip()
            why = re.sub(r"^Held back(, not judged)?: ", "", why).rstrip(".")
            why = why or f"its checks of {b.traced.root.dataset_id} could not run"
            rows.append((lifecycle_report.label_for(b.traced.came), b.state.dataset_id,
                         f"nothing needs deciding on this supply - {why}. Deciding "
                         f"{root_name} settles it: its checks run again and the gate is "
                         f"applied again once that decision is made or a "
                         f"{b.state.period} {b.traced.root.dataset_id} supply is promoted. "
                         f"To override:",
                         [ds for ds, _s in b.traced.via]))
        for line in lifecycle_report.beneath_lines(root_line, rows, root_name=root_name):
            console.print(line, **plain)
        # EACH OVERRIDE WHOLE, ON A LINE OF ITS OWN, OUTSIDE ANY TABLE
        # (criterion 21; _show's convention, post-build-review #112).
        for b in members:
            console.print(override_command(b.state.dataset_id, b.state.period,
                                           b.state.supply), soft_wrap=True, **plain)
            console.print(f"or from the {b.state.period} door.", **plain)
        if any(b.traced.came == "joined" for b in members):
            console.print(SUPPLIER_HINT, style="dim", **plain)
        console.print()
    say_gating(groups)


def say_gating(groups) -> None:
    """Each delivery still being checked or gated, as ONE dim line of its
    own - never counted, never offered (REQ-PIPE-276 criterion 12)."""
    from qa_tools.common import gate

    for package, _states in groups.gating:
        console.print(gate.gating_words(package), style="dim", markup=False, highlight=False)
    if groups.gating:
        console.print()


def _label(state: slot_state.SlotState, count: int = 0) -> str:
    where = f"arrived {arrived(state.supply)}" if state.supply else "nothing arrived"
    # NOTHING ARRIVED INTO A PERIOD THAT CARRIES ONE FORWARD (CLI UX critic
    # minors, #267): "arrived ... (inherited)" read as a supply filed there,
    # and "nothing arrived (owes nothing...)" said the same thing twice.
    if state.state == slot_state.INHERITED and state.supply:
        where = f"carries forward the one received {arrived(state.supply)}"
    elif state.state == filing_queue.CARRIES_NOTHING:
        return f"{state.period}  {state.dataset_id}  owes nothing, carries nothing forward"
    # IN WORDS, as the table above it says it (CLI UX critic, #107): the
    # picker used to show the machine id - `awaiting-acknowledgement`.
    words = re.sub(r"\[/?[a-z ]+\]", "", _HOW_IT_READS.get(state.state, state.state))
    if state.state == filing_queue.RECHECKED_WORSE and state.reason:
        # 'Promoted, then re-checked <verdict>' (REQ-PIPE-164 criterion 15).
        words = state.reason.split(":")[0]
    # HOW MANY, where more than one (REQ-GHUB-229 criterion 3).
    many = f"  - {count} supplies" if count > 1 else ""
    return f"{state.period}  {state.dataset_id}  {where}  ({words}){many}"


def _pick_slot(states, message: str, counts: dict | None = None) -> slot_state.SlotState | None:
    counts = counts or {}
    by_label = {_label(s, counts.get((s.dataset_id, s.period), 0)): s for s in states}
    choice = common.select(message, list(by_label), flag_hint=_FLAG_HINT)
    return by_label.get(choice) if choice else None


def stands_on_line(state: slot_state.SlotState) -> str:
    """The line a period standing on another's supply prints above its own
    (REQ-GHUB-229 criterion 6) - saying where (REQ-DASH-277 criterion 2)."""
    how = "substituted" if state.state == slot_state.SUBSTITUTED else "inherited"
    # TWO LINES rather than one past 80 columns (REQ-DASH-277 criterion 5).
    return (f"{state.period} stands on {state.stands_on}'s supply ({how}) -\n"
            f"the supply in place in the warehouse is not one of these.")


def listed_words(entry: "filing_queue.FiledSupply") -> str:
    """One listed supply's state in words (REQ-GHUB-229 criterion 5), with
    what each needs: why it could not be loaded, who rejected it and when,
    what superseded it, both files of an open pair."""
    s = entry.state
    words = _LISTED_AS.get(s.state, "")
    if s.state == filing_queue.RECHECKED_WORSE and s.reason:
        words = "in place in the warehouse - " + s.reason.split(":")[0].lower()
    elif s.state == slot_state.TWO_FILES:
        words = f"{words} - {' and '.join(s.files)}" if s.files else words
    elif s.state in (filing_queue.COULD_NOT_LOAD, slot_state.REJECTED,
                     filing_queue.SUPERSEDED) and s.reason:
        words = f"{words} - {s.reason}" if s.state == filing_queue.COULD_NOT_LOAD \
            else f"{words} {s.reason}"
    return words


#: The columns questionary's pointer takes before every choice it lists.
_POINTER_WIDTH = 3


def _supply_line(entry: "filing_queue.FiledSupply") -> str:
    """Arrived, state, verdict (criterion 4) - and the line a person picks.
    Under the table that heads those three columns, so it carries no labels
    of its own, and WITHIN 80 COLUMNS WITH THE POINTER BEFORE IT
    (REQ-DASH-277 criterion 5; post-build-review #266 S2): the state words
    are shortened with _short where the line would run past, never wrapped
    - the arrival and the verdict always stay, and the table above holds
    the words in full."""
    head, tail = f"{arrived(entry.state.supply)}  ", f"  ({entry.verdict})"
    words = listed_words(entry) or "-"
    room = 80 - _POINTER_WIDTH - len(head) - len(tail)
    return head + (words if len(words) <= room else _short(words, room)) + tail


def _excuse_offers(state: slot_state.SlotState) -> tuple[str, ...]:
    """REQ-PIPE-161 criterion 10: excuse (or withdraw) where the slot's
    current supply is late - read from the log, so it needs a connection."""
    try:
        with open_log() as conn:
            # AND THE ACKNOWLEDGEMENT'S WITHDRAWAL (REQ-PIPE-166 criterion 6),
            # read from the log the same way.
            return (filing_queue.excuse_offers(conn, state)
                    + filing_queue.acknowledgement_offers(conn, state))
    except filing_queue.LogUnreachable:
        return ()


def _supersede_offers(state: slot_state.SlotState) -> tuple[str, ...]:
    """REQ-GHUB-165 criterion 1: un-supersede wherever a superseded version
    could come back - read from the log, so it needs a connection."""
    try:
        with open_log() as conn:
            return filing_queue.supersede_offers(conn, state)
    except filing_queue.LogUnreachable:
        return ()


def _offers(state: slot_state.SlotState, supply_scoped: tuple[str, ...]) -> tuple[str, ...]:
    """A slot's supply-scoped offers plus the two read from the log - the
    excuse (REQ-PIPE-161) and un-supersede (REQ-GHUB-165) - once each."""
    extra = tuple(op for op in _excuse_offers(state) + _supersede_offers(state)
                  if op not in supply_scoped)
    return supply_scoped + extra


def _something_newer(state: slot_state.SlotState) -> bool:
    """Whether a carry-forward here would change anything (M2)."""
    from qa_tools.common import carry_forward

    try:
        with open_log() as conn:
            return not carry_forward.plan(conn, state.dataset_id, state.period).already
    except (decision_log.DecisionRefused, filing_queue.LogUnreachable):
        return False


def _decide_on(state: slot_state.SlotState, *, offer: tuple[str, ...]) -> None:
    """Offer this slot's operations and carry one out.

    WHAT IS OFFERED COMES FROM `filing_queue.operations_for`, so the
    queue, the period door and the after-a-run offer cannot disagree
    about what is possible on the same slot.
    """
    if not offer:
        console.print("There is nothing to decide about this one.", style="dim")
        return
    # WHAT IS SAID BEFORE ANY DECISION IS OFFERED (REQ-PIPE-276 criteria 11,
    # 14 and 16; REQ-PIPE-210 criterion 4).
    note, offer_nothing = door_note(state)
    if note:
        _show(note, title=f"{state.dataset_id} {state.period}",
              style="dim" if offer_nothing else "yellow")
    if offer_nothing:
        return
    if state.state == slot_state.TWO_FILES:
        _settle_on(state)
        return
    if state.state == filing_queue.COULD_NOT_LOAD:
        # The recorded reason, and the response that is not a control.
        console.print(f"{state.supply} could not be loaded: {state.reason}. Reject it "
                       f"here, or {filing_queue.REPROCESS}.", style="yellow")
    words = dict(_WHAT_IT_DOES)
    if state.state == filing_queue.ANOTHER_VERSION_WAITING:
        words.update(_WHAT_IT_DOES_TO_ANOTHER_VERSION)
    if filing_decisions.UN_SUPERSEDE in offer and state.state != filing_queue.SUPERSEDED:
        # NO COUNT ON A CHOSEN VERSION (#201 F7): only it comes back.
        # THE OFFER CARRIES A COUNT (REQ-GHUB-165 criterion 1): a choice is
        # coming, and the person sees that before taking it.
        try:
            with open_log() as conn:
                n = len(filing_queue.superseded_to_bring_back(conn, state))
        except filing_queue.LogUnreachable:
            n = 0
        if n:
            words[filing_decisions.UN_SUPERSEDE] = (
                f"{words[filing_decisions.UN_SUPERSEDE]} ({n} earlier "
                f"version{'s' if n != 1 else ''})")
    if filing_decisions.CARRY_FORWARD in offer and not _something_newer(state):
        # NOTHING NEWER, SAID ON THE CHOICE (CLI UX critic M2, #267), before
        # anyone is asked for a reason for a decision that would do nothing.
        words[filing_decisions.CARRY_FORWARD] = ("carry forward (nothing newer to carry "
                                                 "forward)")
    by_label = {words[op]: op for op in offer}
    picked = common.select(f"{state.dataset_id} {state.period} - what are you "
                            f"recording?", list(by_label), flag_hint=_FLAG_HINT)
    if picked is None:
        return
    operation = by_label[picked]

    to_period = stands_on = None
    supply = state.supply
    if operation == filing_decisions.UN_SUPERSEDE and state.state == filing_queue.SUPERSEDED:
        # ALREADY NAMED: the person chose this version from the period's list
        # (REQ-GHUB-229 criterion 7), so there is nothing to pick again.
        pass
    elif operation == filing_decisions.UN_SUPERSEDE:
        # WHICH VERSION, NAMED, NEVER A DEFAULT (REQ-PIPE-120 criterion 8).
        from qa_tools.common import supersession

        with open_log() as conn:
            versions = supersession.superseded_in(conn, state.dataset_id, state.period)
        if not versions:
            console.print(f"Nothing is superseded for {state.dataset_id} {state.period}.",
                          style="dim")
            return
        by_label = {f"{v['supply']}  (superseded by {v['superseded_by'] or 'a person'})":
                    v["supply"] for v in versions}
        picked_version = common.select("Which superseded version should come back?",
                                       list(by_label), flag_hint=_FLAG_HINT)
        if picked_version is None:
            return
        supply = by_label[picked_version]
    if operation == filing_decisions.REFILE:
        # CHOSEN, NEVER TYPED (REQ-PIPE-163 criterion 16), opening on the
        # periods nearest the supply's receipt.
        to_period = choose_period(state.dataset_id, _receipt_of(state.dataset_id, supply),
                                  "Which period should it move to?", current=state.period)
        if to_period is None:
            return
    if operation == filing_decisions.SUBSTITUTE:
        stands_on = common.text_prompt(
            "Which earlier period should this one stand on?", flag_hint=_FLAG_HINT)
        if stands_on is None:
            return

    through_period = None
    if operation == filing_decisions.EXCUSE_LATENESS:
        # THE RANGE FORM HERE TOO (Keith, 2026-10-11, answer (c)): from this
        # period to one the person names, the same range the CLI's
        # --from-period/--through-period records - the warning panel lists
        # what it excuses and skips before the one confirmation.
        form = common.select("Excuse this supply alone, or every late supply from "
                             f"{state.period} to a later period?",
                             [_EXCUSE_ONE, _EXCUSE_A_RANGE], flag_hint=_FLAG_HINT)
        if form is None:
            return
        if form == _EXCUSE_A_RANGE:
            through_period = common.text_prompt(
                f"Through which period? Every late supply from {state.period} to it, "
                f"inclusive, is excused with one reason.", flag_hint=_FLAG_HINT)
            if through_period is None:
                return
            supply = None

    apply_decision(operation=operation, dataset_id=state.dataset_id,
                    period=state.period, supply=supply,
                    stands_on=stands_on, to_period=to_period,
                    through_period=through_period)


def door_note(state: slot_state.SlotState) -> tuple[str | None, bool]:
    """(what the door says about this supply before offering anything,
    whether it offers nothing at all):

      - a supply of a delivery still being checked or gated reads 'checking
        with its delivery (<n> of <m> files checked)' and is offered no
        decision - the refusal is the flag route's backstop only (REQ-PIPE-276
        criterion 11);
      - a supply held back because of another supply names that supply's
        decision first, and keeps its own decisions on the same terms
        (REQ-PIPE-210 criterion 4; REQ-PIPE-276 criterion 4);
      - a red in-warehouse supply owed only a re-check is worded as not yet
        re-checked, never as re-checked worse (criterion 14);
      - the Order B link (criterion 16)."""
    from qa_tools.common import gate, root_cause, supply_status

    if not state.supply:
        return None, False
    lines: list[str] = []
    try:
        with open_log() as conn:
            if conn is None:
                return None, False
            package = gate.being_gated(conn, state.dataset_id, state.supply)
            if package is not None:
                return (f"{state.dataset_id} {state.period}: {gate.door_words(package)}. "
                        f"It is decided once its delivery is gated.", True)
            owed = supply_status.red_only_for_recheck_owed(conn, state.dataset_id,
                                                          state.supply)
            if owed:
                said = supply_status.recheck_owed_words(conn, owed)
                if said:
                    lines += [said, "mothman pipeline process"]
            link = root_cause.order_b_link(conn, state.dataset_id, state.supply,
                                           state.period)
            if link:
                lines.append(link)
            slot_line = _slot_root_words(conn, state)
            if slot_line:
                lines.append(slot_line)
    except filing_queue.LogUnreachable:
        return None, False
    step = next_step(state.supply, state.period)
    if step:
        lines.append(step)
    return ("\n".join(lines) or None), False


def _slot_root_words(conn, state) -> str | None:
    """For a supply red wholly for want of another table (REQ-PIPE-210
    criteria 4 and 9): where that table's slot has an item of its own - an
    open pair, a supply waiting on a decision - its decision first and that
    nothing needs deciding on this supply; where it has none, the counted
    row's own line naming the root, never 'nothing needs deciding'."""
    from qa_tools.common import root_cause

    traced = root_cause.trace(conn, state.dataset_id, state.supply, state.period)
    if traced is None or traced.root.kind != "slot":
        return None
    root = traced.root
    items = [s for s in filing_queue.slots_of(
        conn, hierarchy.dataset(root.dataset_id).collection_id, dataset_id=root.dataset_id)
        if s.period == root.period and s.state in filing_queue.WITH_A_SUPPLY]
    if not items:
        return root_cause._overdue_words(root)
    what = ("settle its pair of files" if items[0].state == slot_state.TWO_FILES
            else "decide its supply")
    return (f"Nothing needs deciding on this supply - its checks of {root.dataset_id} could "
            f"not run. {root.dataset_id} {root.period}: {what} first - that re-checks this "
            f"one.")


def _settle_on(state: slot_state.SlotState) -> None:
    """An open pair offers exactly two things (REQ-PIPE-194 criterion 4):
    settle, or reject both - the second a settlement too, through the same
    summary, reason and single confirmation."""
    from cli import settle_tui
    from qa_tools.common import settlement

    with open_log() as conn:
        promoted = decision_log.promoted_into(conn, state.dataset_id, state.period)
        _delivery, _period, files = settlement.pair_files(conn, state.dataset_id, state.supply)
    both = settle_tui.REJECT_BOTH_KEEPS if promoted else settle_tui.REJECT_BOTH
    name = hierarchy.dataset(state.dataset_id).dataset_name
    # BACK ON THE FIRST FILE'S QUESTION RETURNS HERE (criterion 24, #170).
    while True:
        picked = common.select(f"{name} {state.period} - two files arrived. What are you "
                               f"recording?", [settle_tui.SETTLE, both],
                               flag_hint=_FLAG_HINT)
        if picked is None:
            return
        answers = ([settlement.Answer(f.filename, settlement.REJECT) for f in files]
                   if picked == both else None)
        got = settle_tui.settle(state.dataset_id, state.period, state.supply,
                                answers=answers)
        if got is not settle_tui.BACK:
            return


def queue_flow(collection_id: str) -> None:
    """The standing queue (criterion 16) - what is waiting on a person.

    ONLY THE SUPPLY-SCOPED FOUR ARE REACHED FROM HERE (criterion 31).
    """
    try:
        with open_log() as conn:
            waiting = filing_queue.awaiting(conn, collection_id)
            gaps = filing_queue.closed_gaps(conn, collection_id)
            held = filing_queue.held_in(conn, collection_id)
            carry = carry_forward_warnings(conn, collection_id)
            # ONE ROW PER CAUSE (REQ-PIPE-210; REQ-PIPE-276 criteria 6 and 12).
            groups = queue_groups(conn, waiting,
                                  held=[h for h in held if not h.turned_off])
            shown = _queue_screen(conn, collection_id, gaps=gaps, held=held, carry=carry,
                                  groups=groups)
    except filing_queue.LogUnreachable as exc:
        say_unreachable(exc)
        return
    if shown is not None:
        _queue_choice(collection_id, *shown)


def _queue_screen(conn, collection_id: str, *, gaps, held, carry, groups):
    """queue_flow's screen, over one open log - then (rows, held, quiet,
    carry) for the choice, or None where there is nothing to choose."""
    waiting = groups.rows
    # RECEIVED WHILE TURNED OFF (REQ-PIPE-179 criterion 34): a quiet last
    # group, after the slot rows and outside every count of what waits on a
    # decision - one row per dataset.
    quiet = filing_queue.turned_off_groups(held)
    held = [h for h in held if not h.turned_off]

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
    # A NEWER SUPPLY THAT COULD BE CARRIED FORWARD (REQ-PIPE-271 criterion 7),
    # in the period-items group above the slot rows, and NOT COUNTED: it is
    # not a supply waiting on a decision.
    say_carry_forward_warnings(carry)
    if held:
        # HELD SUPPLIES, THEIR OWN GROUP ABOVE THE SLOT ROWS (REQ-PIPE-163
        # criterion 17): a dataset and a receipt in place of a period, and why
        # it was held in the hold's own reason (criterion 10).
        console.print(f"[bold]Held - no period yet ({len(held)})[/bold] - each needs a "
                      f"period chosen, or rejecting")
        console.print(held_table(held))
        console.print()
    if not waiting and not held and not gaps:
        console.print(f"Nothing is waiting on a person in "
                       f"{_collection_name(collection_id)}.", style="green")
    # WHATEVER IS COUNTED (post-build critic D3): the counted rows, the supplies
    # beneath a root - a held one included - and a delivery being gated, as
    # one quiet line beneath the rest and never asked about (REQ-PIPE-276
    # criterion 12): no 'Which one?' when it is all there is.
    say_queue(conn, groups, collection_id)
    if not waiting and not held and not quiet and not carry:
        return None
    if quiet:
        total = sum(len(g.rows) for g in quiet)
        console.print(f"[dim]Received while turned off ({total})[/dim]")
        for g in quiet:
            console.print(f"[dim]  {g.line}[/dim]", markup=True)
        console.print()
    return waiting, held, quiet, carry


def _queue_choice(collection_id: str, waiting, held, quiet, carry) -> None:
    """'Which one?' over what the screen counted - never a supply listed
    beneath its cause, nor a delivery being gated (REQ-PIPE-210 criterion
    3; REQ-PIPE-276 criterion 12)."""
    if held or quiet or carry:
        labels = {_held_label(h): h for h in held}
        labels.update({_label(s): s for s in waiting})
        labels.update({g.line: g for g in quiet})
        # ONE SELECTABLE ITEM FOR THE WARNINGS (Keith, 2026-10-24, K3): it opens
        # the period's door, as 'Received while turned off (n)' opens its own -
        # still outside every count of what waits on a decision.
        if carry:
            labels[f"{CARRY_FORWARD_ITEM} ({len(carry)})"] = _CARRY
        picked = common.select("Which one?", list(labels), flag_hint=_FLAG_HINT)
        if picked is None:
            return
        chosen = labels[picked]
        if chosen is _CARRY:
            carry_forward_flow(collection_id, carry)
            return
        if isinstance(chosen, filing_queue.TurnedOffGroup):
            turned_off_flow(chosen)
            return
        if isinstance(chosen, filing_queue.HeldRow):
            held_flow(chosen)
            return
        state = chosen
    else:
        state = _pick_slot(waiting, "Which one?")
    if state is None:
        return
    supply_scoped, _period_scoped = filing_queue.operations_for(state)
    _decide_on(state, offer=_offers(state, supply_scoped))


#: The queue's one selectable item for the warnings (K3), and its marker.
CARRY_FORWARD_ITEM = "Could be carried forward"
_CARRY = object()


def carry_forward_warnings(conn, collection_id: str, dataset_id: str | None = None,
                           period: str | None = None) -> list:
    """The carry-forward warnings standing for this collection (REQ-PIPE-271
    criterion 7), one per dataset and period.

    ONLY AN UNREACHABLE LOG IS LogUnreachable (post-build-review #267): a
    defect in reading the warnings is a defect, and raising it is louder
    than telling a person the database is down when it is not."""
    import psycopg

    from qa_tools.common import carry_forward

    mine = {d.dataset_id for d in hierarchy.datasets_in_collection(collection_id)}
    try:
        found = carry_forward.standing(conn, dataset_id=dataset_id, period=period)
    except (supply_db.SupplyDbError, psycopg.OperationalError) as exc:
        raise filing_queue.LogUnreachable(str(exc)) from exc
    return [w for w in found if w.dataset_id in mine]


def say_carry_forward_warnings(warnings, *, in_door: bool = False) -> None:
    """Each warning in the terminal's own voice, its command on a line of its
    own below the prose - never inside a panel or a table cell (criterion 7).

    THE PROSE WORD-WRAPS AND ONLY THE COMMAND IS SOFT-WRAPPED (CLI UX critic
    M4, #267): soft-wrapped, the sentences broke mid-word at the terminal's
    edge; a command must not be broken at all, so it is copied whole. Inside
    the period's own door it does not send the person to that door (M5)."""
    from qa_tools.common import carry_forward

    if not warnings:
        return
    n = len(warnings)
    console.print(f"[bold]{CARRY_FORWARD_ITEM} ({n})[/bold] - a newer supply was promoted "
                  f"after {'this period' if n == 1 else 'these periods'} opened")
    for w in warnings:
        for line in carry_forward.lines(w, voice="terminal", in_door=in_door):
            if line.startswith("mothman "):
                console.print(line, soft_wrap=True, highlight=False, markup=False)
            else:
                console.print(line, highlight=False, markup=False)
        console.print()


def carry_forward_flow(collection_id: str, warnings) -> None:
    """The queue's 'Could be carried forward (n)' item (K3): which one, where
    there is more than one, then that period's door."""
    from qa_tools.common import carry_forward

    if len(warnings) == 1:
        (w,) = warnings
    else:
        by_label = {carry_forward.headline(x): x for x in warnings}
        picked = common.select("Which one?", list(by_label), flag_hint=_FLAG_HINT)
        if picked is None:
            return
        w = by_label[picked]
    try:
        with open_log() as conn:
            found = [s for s in carry_forward.carried_periods(conn, w.dataset_id)
                     if s.period == w.period]
    except filing_queue.LogUnreachable as exc:
        say_unreachable(exc)
        return
    if not found:
        console.print(f"{w.period} no longer carries anything forward that can be "
                      f"changed here.", style="yellow")
        return
    _owed_nothing_door(collection_id, found[0])


def turned_off_flow(group) -> None:
    """One dataset's supplies received while turned off, each saying what
    can be done (REQ-PIPE-179 criterion 34) - then the held supply's own
    place-or-reject flow."""
    if len(group.rows) == 1:
        held_flow(group.rows[0])
        return
    labels = {f"{_held_label(r)}": r for r in group.rows}
    picked = common.select(f"{group.line}: which one?", list(labels), flag_hint=_FLAG_HINT)
    if picked is not None:
        held_flow(labels[picked])


def held_table(held) -> Table:
    """The held group: dataset, receipt on the asset's clock, and why."""
    table = Table("Dataset", "Received", "Why it is held", box=None, pad_edge=False)
    for h in held:
        table.add_row(h.dataset_name, h.received_text, h.why)
    return table


def _held_label(h) -> str:
    """Said as a slot row is - the dataset id and when it arrived - under the
    group's own heading (#188, cli-ux M4)."""
    if getattr(h, "turned_off", False):
        return (f"Received while turned off: {h.dataset_id} (the supply that arrived "
                f"{arrived(h.supply)})")
    return f"Held, no period yet: {h.dataset_id} (the supply that arrived {arrived(h.supply)})"


def held_flow(h) -> None:
    """What a person can do about one held supply (REQ-PIPE-163 criteria 10
    and 22): place or reject it - or, where its schedule ended, add dates,
    which is configuration, so nothing is offered to choose."""
    from qa_tools.common import placing

    console.print(Panel(Text(h.why), title=f"Held - {h.dataset_name}", border_style="yellow",
                        expand=False))
    if h.agreement_refused:
        console.print("It files itself on the next processing pass once the delivery "
                      "agreement matches its recorded judgements again - nothing to decide "
                      "here.", style="yellow")
        return
    if not filing_queue.held_operations(h):
        _show(f"{h.why}\nAdd the next delivery dates to contract/calendar.yaml - it files "
              f"itself on the next processing pass. Where a declared correction is "
              f"needed:\nmothman schedule draft-correction",
              title="Held - its schedule has ended", style="yellow")
        return
    if h.files:
        console.print(f"Two files of one delivery are held together: "
                      f"{' and '.join(h.files)}. Placing puts both into the period, still "
                      f"contested, to be settled there.", style="dim")
    place = "place - say which period it belongs to"
    reject = "reject - it is not fit for any period"
    # WHAT held_operations OFFERS, and nothing it does not (#189 F8).
    words = {filing_decisions.PLACE: place, filing_decisions.REJECT: reject}
    picked = common.select(f"{h.supply}: what now?",
                           [words[op] for op in filing_queue.held_operations(h) if op in words],
                           flag_hint=(
        placing.flag_form(h.dataset_id, h.supply)))
    if picked == place:
        place_flow(h)
    elif picked == reject:
        apply_decision(operation=filing_decisions.REJECT, dataset_id=h.dataset_id,
                       period=None, supply=h.supply)


_EARLIER = "Earlier periods"
_LATER = "Later periods"


def choose_period(dataset_id: str, received_at, message: str,
                  first: str | None = None, current: str | None = None) -> str | None:
    """THE PERIOD CHOOSER (REQ-PIPE-163 criterion 16): periods offered as a
    choice, never typed - opening on the nearest either side of the receipt,
    owed-nothing periods shown in place and not selectable, paging earlier
    and later. Used to place a held supply, to re-file one, and for a
    settlement's re-file target (criterion 42). None on Back."""
    import questionary

    from qa_tools.common import placing

    with open_log() as conn:
        states = {s.period: s.state for s in filing_queue.slots_of(
            conn, hierarchy.dataset(dataset_id).collection_id, dataset_id=dataset_id)}
    page = 0
    while True:
        got = placing.period_choices(dataset_id, received_at, states, page=page)
        choices: list = []
        if got.has_earlier:
            choices.append(_EARLIER)
        for row in got.rows:
            if row.selectable and row.period == current:
                # ITS OWN PERIOD IS NOT A TARGET (#188, cli-ux M5).
                choices.append(questionary.Separator(f"  {row.label} - it is filed here now"))
            else:
                choices.append(row.label if row.selectable
                               else questionary.Separator(f"  {row.label}"))
        if got.has_later:
            choices.append(_LATER)
        # THE FIRST CHOICE, where the caller names one (REQ-PIPE-193 criterion
        # 19: a settlement's re-file target opens on the next period).
        # NEVER AN UNSELECTABLE ROW (#188 blocker: an owes-nothing row's period
        # is None, which matched first=None and crashed questionary), and the
        # nearest owed period where the caller names none.
        selectable = {r.period: r.label for r in got.rows
                      if r.selectable and r.period != current}
        default = selectable.get(first) or selectable.get(got.nearest)
        picked = common.select(message, choices, flag_hint="--to-period <period>",
                               default=default)
        if picked is None:
            return None
        if picked == _EARLIER:
            page -= 1
            continue
        if picked == _LATER:
            page += 1
            continue
        return next(r.period for r in got.rows if r.label == picked)


def place_flow(h) -> None:
    """Place a held supply (REQ-PIPE-163): choose the period, see how it
    would read there before the reason is asked (criterion 18), then the
    one decision path - whose run, while the person waits, ends with the
    outcome panel (criteria 3 and 19). A period refused is offered again."""
    from qa_tools.common import placing

    while True:
        target = choose_period(h.dataset_id, h.received_at,
                               f"Which period does {h.dataset_name}'s supply belong to?")
        if target is None:
            return
        try:
            with open_log() as conn:
                p = placing.plan(conn, dataset_id=h.dataset_id, supply=h.supply,
                                 to_period=target)
        except decision_log.DecisionRefused as exc:
            _refused(exc, "placement", flag_route=False)
            continue
        _show(preview(p), title=f"Placing it into {target}", style="blue")
        outcome = apply_decision(operation=filing_decisions.PLACE, dataset_id=h.dataset_id,
                                 period=target, supply=h.supply, to_period=target)
        if outcome is not None and outcome.changed and p.is_pair:
            # CRITERION 37: offer to settle the pair now, where it was placed.
            from cli import settle_tui

            if common.confirm("Settle the pair now?", yes=False, default=True):
                settle_tui.settle(h.dataset_id, target, h.supply)
        elif outcome is not None and outcome.changed and outcome.checks_finished:
            _offer_next_decision(h.dataset_id, target, h.supply)
        return


def _offer_next_decision(dataset_id: str, period: str, supply: str) -> None:
    """WHERE IT IS WAITING, THE NEXT DECISION (criterion 19): offered, not
    only named."""
    try:
        with open_log() as conn:
            states = [s for s in filing_queue.slots_of(
                conn, hierarchy.dataset(dataset_id).collection_id, dataset_id=dataset_id)
                if s.period == period and s.supply == supply
                and s.state in filing_queue.WITH_A_SUPPLY]
    except filing_queue.LogUnreachable:
        return
    if states and common.confirm("Decide on it now?", yes=False, default=True):
        # THROUGH THE ONE COMBINER (#189 F7): the excuse and un-supersede are
        # read from the log, as every other door adds them.
        supply_scoped, _ = filing_queue.operations_for(states[0])
        _decide_on(states[0], offer=_offers(states[0], supply_scoped))


def _receipt_of(dataset_id: str, supply: str | None):
    """The supply's receipt instant, or None - for the chooser to open on."""
    from qa_tools.common import supersession

    if not supply:
        return None
    try:
        with open_log() as conn:
            return supersession._receipt(conn, dataset_id, supply)
    except Exception:  # noqa: BLE001 - the chooser opens on the newest periods instead
        return None


def preview(p) -> str:
    """How the supply would read in the chosen period, what that period
    holds now, and what placing does to it (criterion 18) - no QA run."""
    holds = (f"{p.to_period} holds {p.target_holds} now ({p.target_held_as}); it keeps it "
             f"until this one is checked and promoted." if p.target_holds
             else f"{p.to_period} holds no accepted supply now.")
    reads = {"on_time": "on time", "late": "late", "early": "early",
             "unfiled": "unfiled"}.get(p.classification or "", "without a verdict")
    return (f"Against {p.to_period}'s slot it reads {reads}. {holds} Placing files it "
            f"there and owes its checks; the promotion gate then decides, as for any "
            f"arrival.")


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
    from qa_tools.common import carry_forward

    try:
        with open_log() as conn:
            states = filing_queue.slots_of(conn, collection_id, dataset_id=dataset_id)
            counts = filing_queue.filed_counts(conn, dataset_id)
            # THE PERIODS IT OWES NOTHING FOR (REQ-PIPE-280 criterion 1): not
            # slots, so listed here or nowhere - where carry-forward and
            # un-inherit are reached from the door.
            owed_nothing = carry_forward.carried_periods(conn, dataset_id)
    except filing_queue.LogUnreachable as exc:
        say_unreachable(exc)
        return
    owed_nothing = [s for s in owed_nothing if s.period not in {x.period for x in states}]
    states = sorted(states + owed_nothing, key=lambda s: (s.period, s.dataset_id),
                    reverse=True)
    if not states:
        console.print(f"{dataset_id} has no periods yet.", style="yellow")
        return
    state = _pick_slot(states, f"Which period of {dataset_id}?", counts)
    if state is None:
        return
    if state in owed_nothing:
        _owed_nothing_door(collection_id, state)
        return
    supply_scoped, period_scoped = filing_queue.operations_for(state)
    if counts.get((state.dataset_id, state.period), 0) == 1:
        # A FAILED LOAD ALONE IN ITS PERIOD is offered reject only, at the
        # door as in the queue (post-build-review #201 F4, Keith 2026-10-15;
        # REQ-GHUB-229's sign-off decision). The slot's state cannot say it
        # failed - the load log does, read as supplies_in reads it.
        try:
            with open_log() as conn:
                entries = filing_queue.supplies_in(conn, state)
        except filing_queue.LogUnreachable as exc:
            say_unreachable(exc)
            return
        if len(entries) == 1 and entries[0].state.state == filing_queue.COULD_NOT_LOAD:
            own = entries[0].state
            _decide_on(own, offer=_offers(own, filing_queue.operations_for(own)[0]))
            return
    if counts.get((state.dataset_id, state.period), 0) <= 1:
        # ONE SUPPLY OR NONE: straight to the period's decisions, as before
        # (REQ-GHUB-229 criterion 2).
        _decide_on(state, offer=_offers(state, supply_scoped) + period_scoped)
        return
    _choose_a_supply(state, period_scoped)


def _owed_nothing_door(collection_id: str, state: slot_state.SlotState) -> None:
    """A period the dataset owes nothing for (REQ-PIPE-280 criterion 1): what it
    carries forward, the warning where a newer one could be carried forward
    (REQ-PIPE-271 criterion 7), and carry-forward - with un-inherit where it
    inherits."""

    from qa_tools.common import carry_forward

    name = hierarchy.dataset(state.dataset_id).dataset_name
    try:
        with open_log() as conn:
            warned = carry_forward_warnings(conn, collection_id, dataset_id=state.dataset_id,
                                            period=state.period)
            # WHAT IT CARRIES, IN ITS OWN WORDS (CLI UX critic M5, #267):
            # stands_on_line() ends "...is not one of these", written for a
            # list of filed supplies this door does not show.
            if state.state == slot_state.INHERITED and state.stands_on:
                console.print(f"{state.period} carries forward the {name} received "
                              f"{carry_forward.received(state.dataset_id, state.supply, conn)}, "
                              f"promoted into {state.stands_on}.", style="cyan")
            else:
                console.print(f"{state.period} carries nothing forward for {name}.",
                              style="cyan")
    except filing_queue.LogUnreachable as exc:
        say_unreachable(exc)
        return
    say_carry_forward_warnings(warned, in_door=True)
    _decide_on(state, offer=filing_queue.operations_for(state)[1])


#: The choice beside the listed supplies for the period's own decisions
#: (REQ-GHUB-229 criterion 8) - offered once, never under each supply.
_THE_PERIOD_ITSELF = "The period itself"


def _being_gated_words(entries) -> dict[str, str]:
    """{supply: 'checking with its delivery (<n> of <m> files checked)'} for
    each listed supply whose delivery is still being checked or gated."""
    from qa_tools.common import gate

    out = {}
    try:
        with open_log() as conn:
            for e in entries:
                if not e.state.supply:
                    continue
                package = gate.being_gated(conn, e.state.dataset_id, e.state.supply)
                if package is not None:
                    out[e.state.supply] = gate.door_words(package)
    except filing_queue.LogUnreachable:
        return {}
    return out


def _choose_a_supply(state: slot_state.SlotState, period_scoped: tuple[str, ...]) -> None:
    """Every supply filed to the period, then the one the decision is about
    (REQ-GHUB-229 criteria 1, 6, 7, 8 and 9)."""
    try:
        with open_log() as conn:
            entries = filing_queue.supplies_in(conn, state)
    except filing_queue.LogUnreachable as exc:
        say_unreachable(exc)   # criterion 10: said, and nothing listed
        return
    if state.state in (slot_state.SUBSTITUTED, slot_state.INHERITED) and state.stands_on:
        # CRITERION 6: the supply in place is not one filed to this period.
        console.print(stands_on_line(state), style="cyan")
    gating = _being_gated_words(entries)
    table = Table("Arrived", "Where it stands", "Verdict", box=None, pad_edge=False)
    for e in entries:
        table.add_row(arrived(e.state.supply),
                      escape(gating.get(e.state.supply) or listed_words(e)), e.verdict)
    console.print(f"[bold]{len(entries)}[/bold] supplies filed to {state.dataset_id} "
                  f"{state.period}\n")
    console.print(table)
    pair = [e for e in entries if e.state.state == slot_state.TWO_FILES]
    if pair:
        # CRITERION 9: the pair is settled first, and nothing else here waits on it.
        console.print(f"\nNothing else in {state.period} can be decided until the pair is "
                      f"settled.", style="yellow")
        choosable = pair
        period_scoped = ()
    else:
        # NOTHING OFFERED ON A SUPPLY STILL BEING CHECKED WITH ITS DELIVERY
        # (REQ-PIPE-276 criterion 11): listed, never choosable.
        choosable = [e for e in entries if e.state.supply not in gating]
    console.print()
    by_label = {_supply_line(e): e for e in choosable}
    if period_scoped:
        words = ", ".join(re.sub(r" -.*", "", _WHAT_IT_DOES[op]).lower()
                          for op in period_scoped)
        by_label[f"{_THE_PERIOD_ITSELF} - {words}"] = None
    picked = common.select("Which is the decision about?", list(by_label),
                           flag_hint=_FLAG_HINT)
    if picked is None:
        return
    entry = by_label[picked]
    if entry is None:
        _decide_on(state, offer=period_scoped)
        return
    own = entry.state
    supply_scoped, _ = filing_queue.operations_for(own)
    _decide_on(own, offer=_offers(own, supply_scoped))


def standing_view(collection_id: str, dataset_id: str | None = None) -> None:
    """Where every period stands (criterion 18).

    WHICHEVER ROUTE RECORDED EACH DECISION. This resolves the log rather
    than listing it, which is the difference between `mothman supply
    decisions` and this: one says what happened, this says what is true.
    """
    try:
        with open_log() as conn:
            states = filing_queue.slots_of(conn, collection_id, dataset_id=dataset_id)
            counts = filing_queue.filed_counts(conn, dataset_id)
    except filing_queue.LogUnreachable as exc:
        say_unreachable(exc)
        return
    if not states:
        console.print("No periods to show.", style="yellow")
        return
    table = Table("Period", "Dataset", "State", "Arrived", "Decided by", "Why",
                   box=None, pad_edge=False)
    for s in states:
        # THE SAME COUNT AS THE PERIOD PICKER (REQ-GHUB-229 criterion 15).
        n = counts.get((s.dataset_id, s.period), 0)
        many = f" [dim]- {n} supplies[/dim]" if n > 1 else ""
        table.add_row(s.period, s.dataset_id, _HOW_IT_READS.get(s.state, s.state) + many,
                       arrived(s.supply) if s.supply else "[dim]-[/dim]",
                       _who_decided(s), _short(s.reason))
    console.print(f"[bold]{len(states)}[/bold] period(s) in "
                   f"{_collection_name(collection_id)}"
                   + (f", {dataset_id}" if dataset_id else "") + "\n")
    console.print(table)
    _print_amber_settings(sorted({s.dataset_id for s in states}))


def _print_amber_settings(dataset_ids: list[str]) -> None:
    """What an amber supply does for each dataset shown, and where that
    was set (REQ-PIPE-122 NFR 1) - one line where they all share it."""
    from qa_tools.common import amber_setting, asset_time

    today = asset_time.local_date(asset_time.now())
    said = {}
    for ds in dataset_ids:
        try:
            said[ds] = amber_setting.describe(ds, today)
        except amber_setting.AmberSettingError as exc:
            said[ds] = f"none in force - {exc}"
    if not said:
        return
    if len(set(said.values())) == 1:
        console.print(f"\nAmber setting: {next(iter(said.values()))}")
        return
    console.print("\nAmber setting:")
    for ds, text in said.items():
        console.print(f"  {ds}  {text}")


def filing_menu() -> None:
    """The TUI's filing-decisions door, off the main menu.

    A COLLECTION FIRST, because a slot belongs to one and a queue
    spanning all of them would be the thing this project's own scale
    note warns about: at thirty datasets, one undifferentiated list is
    what people stop reading.
    """
    # WHO IS DECIDING, ASKED ON THE WAY IN (#188, cli-ux H2): an unlisted
    # person was told only after walking dataset, period, operation and target.
    try:
        actor_at_the_keyboard()
    except people.UnknownActor as exc:
        _show(str(exc), title="Filing decisions - who is deciding?", style="red")
        return
    # BY NAME, as every pointer into this menu names them (Keith,
    # 2026-10-13, post-build-review #170); the id is what the code keeps.
    # BY THE QA MENU'S LABELS, IN HIERARCHY ORDER, AT EVERY SIZE (Keith,
    # 2026-10-18): one rule for a collection's label in every picker, so the
    # word that finds it in one menu finds it in the next, and an asset that
    # grows past N_LIST does not see the order flip. It listed collections by
    # their own names, sorted by id, until then.
    from qa_tools import collections as registry

    filed = set(_collections())
    every = [c for c in registry.all_collections() if c.id in filed]
    by_name = {c.label: c.id for c in every}
    collections = list(by_name)
    terms = {c.label: common.collection_terms(c) for c in every}
    # GROUPED BY AGENCY AND FILTERED BY TYPING ABOVE N_LIST (REQ-TEST-252
    # criteria 4 and 5); today's list at or below it.
    by_agency: dict[str, list[str]] = {}
    for coll in every:
        by_agency.setdefault(coll.agency_name, []).append(coll.label)
    grouped = list(by_agency.items()) if common.many_collections() else [("", collections)]
    # PENDING CORRECTIONS ABOVE THE CHOICE OF COLLECTION (REQ-PIPE-170
    # criterion 13): a correction is asset-wide, so it cannot wait inside one.
    # Its PARKED moves likewise (Keith, 2026-10-11, (p)).
    waiting = _pending_corrections()
    parked = _parked_moves()
    if waiting or parked:
        if waiting:
            console.print(f"{len(waiting)} calendar correction(s) await the data asset's "
                          f"manager: {', '.join(p.reference for p in waiting)}.",
                          style="yellow", markup=False)
        entries = ([f"{_MENU_CORRECTIONS} ({len(waiting)})"] if waiting else []) \
            + ([f"{_MENU_PARKED} ({len(parked)})"] if parked else [])
        picked = common.grouped_select("Which collection - or the corrections?", grouped,
                                       flag_hint=_FLAG_HINT, many=common.many_collections(),
                                       top=tuple(entries), terms=terms)
        if picked and picked.startswith(_MENU_CORRECTIONS):
            corrections_flow(waiting)
            return
        if picked and picked.startswith(_MENU_PARKED):
            parked_flow(parked)
            return
        collection_id = by_name.get(picked)
    else:
        picked = (collections[0] if len(collections) == 1 else
                  common.grouped_select("Which collection?", grouped, flag_hint=_FLAG_HINT,
                                        many=common.many_collections(), terms=terms))
        collection_id = by_name.get(picked)
    if collection_id is None:
        return
    while True:
        choice = common.select(
            f"{registry.by_id(collection_id).label} - what are you doing?",
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


_EXCUSE_ONE = "This supply alone"
_EXCUSE_A_RANGE = "A range - this period through a later one"
_MENU_CORRECTIONS = "Calendar corrections awaiting confirmation"
_MENU_PARKED = "Parked correction moves"
_KEEP_DONE = "Done - confirm the rest"


def _pending_corrections() -> list:
    """Pending corrections, or none where they cannot be read - the filing
    menu still works without them, and `mothman supply corrections` says why."""
    from qa_tools.common import correction_apply

    try:
        with supply_db.connect(read_only=True, label="mothman:corrections") as conn:
            return correction_apply.pending(conn)
    except Exception as exc:  # noqa: BLE001 - see the docstring
        # SAID, not hidden (delivery-critic on 170, L2).
        console.print(f"Pending calendar corrections could not be read ({exc}) - "
                      f"`mothman supply corrections` says more.", style="dim", markup=False)
        return []


def _parked_moves() -> list:
    """Parked correction moves, or none where they cannot be read."""
    from qa_tools.common import correction_apply

    try:
        with supply_db.connect(read_only=True, label="mothman:parked-corrections") as conn:
            return correction_apply.parked(conn)
    except Exception as exc:  # noqa: BLE001 - as _pending_corrections
        console.print(f"Parked correction moves could not be read ({exc}) - "
                      f"`mothman supply corrections` says more.", style="dim", markup=False)
        return []


def parked_flow(parked: list) -> None:
    """The parked moves, and - for the asset manager - keep one where it is
    instead, with a reason (Keith, 2026-10-11, (p))."""
    from cli import supply as supply_cli

    supply_cli._show_parked(parked)
    actor = actor_at_the_keyboard()
    why = supply_cli.manager_refusal(actor)
    if why:
        _show(why, title="You can look; only the asset manager keeps one", style="yellow")
        return
    labels = _parked_keep_choices(parked)
    if not labels:
        console.print("None of them can be kept where it is - each is in a period that no "
                      "longer owes a supply.", style="dim", markup=False)
        return
    choice = common.select("Keep one where it is instead of moving it once cleared?",
                           [_KEEP_DONE_PARKED] + list(labels),
                           flag_hint="mothman supply confirm-correction --keep")
    if choice is None or choice == _KEEP_DONE_PARKED:
        return
    m = labels[choice]
    with supply_db.connect(label="mothman:keep-parked") as conn:
        try:
            supply_cli.keep_parked_moves(conn, m.reference, (m.supply_id,), None, actor=actor,
                                         yes=False)
        except click.ClickException as exc:
            _show(exc.message, title="Not kept", style="red")


_KEEP_DONE_PARKED = "Leave them parked"


def _parked_keep_choices(parked: list) -> dict:
    """The parked moves the asset manager may keep, by menu label - never
    one the keep would refuse (post-build-review #190 D5)."""
    from qa_tools.common import correction_apply

    return {f"Keep {m.dataset_id} {m.supply_id} in {m.from_period or 'its hold'} "
            f"({m.reference})": m for m in parked if not correction_apply.keep_refusal(m)}


def _keep_choices(moves) -> dict:
    """A correction's moves the asset manager may keep where they are, by
    menu label - never one whose period no longer owes a supply (REQ-PIPE-179
    criterion 36; post-build-review #190 D5). The trial report says why."""
    return {f"Keep {m.dataset_id} {m.supply_id} where it is "
            f"({m.from_period or 'held'} -> {m.to_period or 'held'})"
            + (" - BLOCKED, parked unless kept" if m.blocked else ""):
            (m.dataset_id, m.supply_id)
            for m in moves if not m.keep_refused}


def corrections_flow(waiting: list) -> None:
    """One pending correction: its moves summary first, each supply, then -
    for the asset manager only - choose any to keep, give one reason, and
    confirm the rest in one step (REQ-PIPE-170 criteria 2, 5, 14-17)."""
    from cli import supply as supply_cli
    from qa_tools.common import correction_apply

    p = waiting[0] if len(waiting) == 1 else None
    if p is None:
        labels = {f"{w.reference} ({w.date}) on {w.label}: {w.reason}": w for w in waiting}
        choice = common.select("Which correction? (oldest first - confirm them in order)",
                               list(labels), flag_hint="mothman supply corrections")
        if choice is None:
            return
        p = labels[choice]
    actor = actor_at_the_keyboard()
    with supply_db.connect(label="mothman:confirm-correction") as conn:
        from qa_tools.common import correction_trial

        try:
            p, t = correction_apply.trial_for(conn, p.reference)
        except (decision_log.DecisionRefused, correction_trial.Unreadable) as exc:
            _show(str(exc), title="Cannot open it", style="red")
            return
        key = supply_cli._show_correction(p, t)
        # VIEW FOR ALL, CONFIRM FOR ONE (criteria 17 and 18): said before any
        # choice or reason is asked for.
        why = supply_cli.manager_refusal(actor)
        if why:
            _show(why, title="You can look; only the asset manager confirms", style="yellow")
            return
        keep: set = set()
        moves = _keep_choices(t.moves)
        while moves:
            choice = common.select("Keep any where they are? Each one you keep is recorded as "
                                   "kept.", [_KEEP_DONE] + [k for k in moves
                                                            if moves[k] not in keep],
                                   flag_hint="--keep <supply>")
            if choice is None:
                return
            if choice == _KEEP_DONE:
                break
            keep.add(moves[choice])
        keep_reason = None
        if keep:
            keep_reason = common.text_prompt(
                f"Why do the {len(keep)} kept supplies stay where they are? (one reason, "
                f"recorded on each)", flag_hint="--keep-reason")
            if not keep_reason:
                console.print("No reason - nothing applied.", style="yellow")
                return
        try:
            supply_cli.apply_correction(conn, p, t, actor=actor, keep=keep,
                                        keep_reason=keep_reason, acknowledged=key, yes=False,
                                        output=None)
        except click.ClickException as exc:
            _show(exc.message, title="Not applied", style="red")


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
    _decide_on(state, offer=_offers(state, supply_scoped))
