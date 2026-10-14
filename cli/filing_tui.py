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
                     filing_decisions.RECHECK)

#: How an operation reads as a NOUN in a prompt - "this acknowledge" was
#: the verb doing a noun's job (#107).
_NOUN = {filing_decisions.ACKNOWLEDGE: "acknowledgement", filing_decisions.REFILE: "re-file",
         filing_decisions.PLACE: "placement",
         filing_decisions.EXCUSE_LATENESS: "excuse",
         filing_decisions.WITHDRAW_EXCUSE: "withdrawal of the excuse",
         filing_decisions.RECHECK: "re-check"}

#: Decisions whose reason is PUBLISHED beside the supply on the dashboard
#: (REQ-PIPE-161 criterion 18), said when the reason is asked for.
_PUBLISHED_REASON = (filing_decisions.EXCUSE_LATENESS, filing_decisions.WITHDRAW_EXCUSE,
                     filing_decisions.PLACE,
                     # REQ-PIPE-164 criterion 14.
                     filing_decisions.RECHECK)

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

    if reason is None:
        reason = common.text_prompt(
            f"Why are you recording this {_NOUN.get(operation, operation)}?"
            + (" It is published beside the supply on the dashboard."
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
            _show(str(exc), title=f"{operation} refused", style="red")
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
        console.print(Panel(Text(outcome.message, style="bold green"),
                             title="Recorded", border_style="green", expand=False))
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
        _follow_up(hierarchy.dataset(dataset_id).collection_id)
        filing_decisions.reconcile_after(
            outcome, hierarchy.dataset(dataset_id).collection_id)
    else:
        # CRITERION 26: a no-op is not a refusal, and must not look like
        # one. Two people working the same ticket arrive here constantly.
        console.print(Panel(Text(outcome.message), title="Already so",
                             border_style="blue", expand=False))
    return outcome


def _follow_up(collection_id: str) -> None:
    """The knock-on of what the decision moved (REQ-PIPE-121): every period
    it moved a table into or out of re-evaluates its readers, and the gate
    looks at each waiting one again. Said only where something happened; a
    failure stays owed for the processing pass (criterion 14)."""
    from qa_tools.common import knock_on

    try:
        done = knock_on.follow_up(collection_id)
    except Exception as exc:  # noqa: BLE001 - the decision stands either way
        console.print(f"The re-evaluation of the period's readers did not run ({exc}); "
                      "it stays owed.", style="yellow")
        return
    for outcome in done:
        if not outcome.completed:
            console.print(Panel(Text(outcome.message), title="Re-evaluation owed",
                                border_style="yellow", expand=False))


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
    if got.promoted:
        lines.append(f"The promotion gate promoted it into {where}.")
    else:
        lines.append(f"It is waiting in {where}: filed, and nothing is lost. The promotion "
                     f"gate did not promote it - {_gate_words(got.waits_because or 'it waits for a person')}. "
                     f"Promote or reject it next, at Filing decisions > Supplies waiting on a "
                     f"decision.")
    style = ("green" if got.status in ("green", "amber") else
             "red" if got.status == "red" else "yellow")
    return " ".join(lines), "Where it stands now", style


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
        text = " ".join(lines)
    else:
        lines.append(f"It is waiting in {where}. The promotion gate did not promote it - "
                     f"{_gate_words(got.waits_because or 'it waits for a person')}. Promote or "
                     f"reject it next, at Filing decisions > Supplies waiting on a decision.")
        text = " ".join(lines)
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


def _label(state: slot_state.SlotState) -> str:
    where = f"arrived {arrived(state.supply)}" if state.supply else "nothing arrived"
    # IN WORDS, as the table above it says it (CLI UX critic, #107): the
    # picker used to show the machine id - `awaiting-acknowledgement`.
    words = re.sub(r"\[/?[a-z ]+\]", "", _HOW_IT_READS.get(state.state, state.state))
    if state.state == filing_queue.RECHECKED_WORSE and state.reason:
        # 'Promoted, then re-checked <verdict>' (REQ-PIPE-164 criterion 15).
        words = state.reason.split(":")[0]
    return f"{state.period}  {state.dataset_id}  {where}  ({words})"


def _pick_slot(states, message: str) -> slot_state.SlotState | None:
    by_label = {_label(s): s for s in states}
    choice = common.select(message, list(by_label), flag_hint=_FLAG_HINT)
    return by_label.get(choice) if choice else None


def _excuse_offers(state: slot_state.SlotState) -> tuple[str, ...]:
    """REQ-PIPE-161 criterion 10: excuse (or withdraw) where the slot's
    current supply is late - read from the log, so it needs a connection."""
    try:
        with open_log() as conn:
            return filing_queue.excuse_offers(conn, state)
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


def _decide_on(state: slot_state.SlotState, *, offer: tuple[str, ...]) -> None:
    """Offer this slot's operations and carry one out.

    WHAT IS OFFERED COMES FROM `filing_queue.operations_for`, so the
    queue, the period door and the after-a-run offer cannot disagree
    about what is possible on the same slot.
    """
    if not offer:
        console.print("There is nothing to decide about this one.", style="dim")
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
    if filing_decisions.UN_SUPERSEDE in offer:
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
    by_label = {words[op]: op for op in offer}
    picked = common.select(f"{state.dataset_id} {state.period} - what are you "
                            f"recording?", list(by_label), flag_hint=_FLAG_HINT)
    if picked is None:
        return
    operation = by_label[picked]

    to_period = stands_on = None
    supply = state.supply
    if operation == filing_decisions.UN_SUPERSEDE:
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
    except filing_queue.LogUnreachable as exc:
        say_unreachable(exc)
        return
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
    if held:
        # HELD SUPPLIES, THEIR OWN GROUP ABOVE THE SLOT ROWS (REQ-PIPE-163
        # criterion 17): a dataset and a receipt in place of a period, and why
        # it was held in the hold's own reason (criterion 10).
        console.print(f"[bold]Held - no period yet ({len(held)})[/bold] - each needs a "
                      f"period chosen, or rejecting")
        console.print(held_table(held))
        console.print()
    if not waiting and not held:
        if not gaps:
            console.print(f"Nothing is waiting on a person in "
                           f"{_collection_name(collection_id)}.", style="green")
        if not quiet:
            return
    if waiting:
        console.print(f"[bold]{len(waiting)}[/bold] supply/supplies waiting on a "
                       f"decision in {_collection_name(collection_id)}\n")
        console.print(queue_table(waiting))
        console.print()
    if quiet:
        total = sum(len(g.rows) for g in quiet)
        console.print(f"[dim]Received while turned off ({total})[/dim]")
        for g in quiet:
            console.print(f"[dim]  {g.line}[/dim]", markup=True)
        console.print()
    if held or quiet:
        labels = {_held_label(h): h for h in held}
        labels.update({_label(s): s for s in waiting})
        labels.update({g.line: g for g in quiet})
        picked = common.select("Which one?", list(labels), flag_hint=_FLAG_HINT)
        if picked is None:
            return
        chosen = labels[picked]
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
    _decide_on(state, offer=_offers(state, supply_scoped) + period_scoped)


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
    by_name = {_collection_name(c): c for c in _collections()}
    collections = list(by_name)
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
        picked = common.select("Which collection - or the corrections?",
                               entries + collections, flag_hint=_FLAG_HINT)
        if picked and picked.startswith(_MENU_CORRECTIONS):
            corrections_flow(waiting)
            return
        if picked and picked.startswith(_MENU_PARKED):
            parked_flow(parked)
            return
        collection_id = by_name.get(picked)
    else:
        picked = (collections[0] if len(collections) == 1 else
                  common.select("Which collection?", collections, flag_hint=_FLAG_HINT))
        collection_id = by_name.get(picked)
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
