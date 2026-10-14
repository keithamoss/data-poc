"""One implementation of every filing decision, whoever raises it
(REQ-GHUB-082 criterion 13).

THERE ARE TWO OPERATOR ROUTES - a GitHub ticket and the terminal - and
criterion 3 says they SHALL write an identical entry and SHALL NOT give
either an operation the other lacks. That is not something two
implementations can be held to; it is something ONE implementation makes
true, with each route as an adapter that decides only who is asking and
what they asked for.

WHAT AN ADAPTER DOES, therefore, is small on purpose: identify the
person, read the operation and its arguments, call `apply`, and render
what comes back. Everything a decision MEANS - who may raise it, whether
it needs a reason, whether the filing rules permit it, whether it would
change anything at all, and what to say when it would not - lives here,
once. Criterion 24 says the two routes must never disagree about what is
permitted; there is only one place for them to agree.

THE JUDGEMENT IS NOT HERE, and that is deliberate (criterion 20). It is
in decision_log._judge(), inside the transaction that appends the entry,
because whether a slot is already filled is a fact about other rows and
a caller who checked a moment ago may be wrong by now. This module
refuses what it can answer without the log - an unknown actor, a missing
reason, an operation nobody offers - and lets the log refuse the rest at
the instant it matters.

A NO-OP IS NOT A REFUSAL (criterion 26). Promoting a supply already
promoted into that slot, de-substituting a period that holds no
substitution, un-inheriting one that never inherited: each of those is
an operator arriving at a state that already holds, which happens
constantly when two people look at the same ticket. Reporting it as a
failure teaches them to ignore failures.
"""
from __future__ import annotations

from dataclasses import dataclass

from qa_tools.common import (decision_log, hierarchy, inheritance, people,
                             promotion, rejection, substitution, supply_db)

#: The eight operations criterion 1 names, and the vocabulary both
#: routes speak. They are the decision log's own action names rather
#: than a second set mapped onto them - a route's word for something
#: should be the word the log records, or a reader has to translate.
PROMOTE = decision_log.PROMOTE
REJECT = decision_log.REJECT
DEMOTE = decision_log.DEMOTE
REFILE = decision_log.REFILE
SUBSTITUTE = decision_log.SUBSTITUTE
DE_SUBSTITUTE = decision_log.DE_SUBSTITUTE
INHERIT = decision_log.INHERIT
UN_INHERIT = decision_log.UN_INHERIT
#: The ninth (REQ-PIPE-132 criterion 4): accept that a closed period was
#: not supplied. Period-scoped, person only, changes no data.
MARK_NOT_SUPPLIED = decision_log.MARK_NOT_SUPPLIED
#: The tenth (REQ-PIPE-122 criterion 13): acknowledge an amber supply
#: promoted under promote-and-acknowledge. Supply-scoped, person only,
#: reason required, changes no data.
ACKNOWLEDGE = decision_log.ACKNOWLEDGE

#: The eleventh and twelfth (REQ-PIPE-120 criterion 1): set a waiting
#: supply aside for a newer one, and bring a superseded one back.
SUPERSEDE = decision_log.SUPERSEDE
UN_SUPERSEDE = decision_log.UN_SUPERSEDE

#: The thirteenth and fourteenth (REQ-PIPE-161 criteria 1 and 14): excuse a
#: late supply's lateness, and withdraw an excuse. Supply-scoped, person
#: only, reason required, change no data - the verdict stays late.
EXCUSE_LATENESS = decision_log.EXCUSE_LATENESS
WITHDRAW_EXCUSE = decision_log.WITHDRAW_EXCUSE

#: The fifteenth (REQ-PIPE-193): settle a contested pair by saying what each
#: of its two files is. Supply-scoped, person only, reason required -
#: offered on the TERMINAL route only (criterion 1).
CHOOSE_FILE = decision_log.CHOOSE_FILE

#: The sixteenth (REQ-PIPE-163): place a HELD supply into a period. Recorded
#: in the log as a re-file from no period by the person (criterion 2), so it
#: is not one of the log's actions - but every route calls it place
#: (criterion 41). Supply-scoped, person only, reason required, terminal only.
PLACE = "place"

#: The seventeenth (REQ-PIPE-164): run a waiting or promoted supply's QA
#: again where it is filed. Supply-scoped, person only, reason required;
#: it moves nothing, and owes a re-check run (rechecking.record).
RECHECK = decision_log.RECHECK

OPERATIONS = (PROMOTE, REJECT, DEMOTE, REFILE, SUBSTITUTE, DE_SUBSTITUTE,
              INHERIT, UN_INHERIT, MARK_NOT_SUPPLIED, ACKNOWLEDGE, SUPERSEDE, UN_SUPERSEDE,
              EXCUSE_LATENESS, WITHDRAW_EXCUSE, CHOOSE_FILE, PLACE, RECHECK)

#: Offered on the terminal and never on GitHub (REQ-PIPE-193 criteria 1 and
#: 16; Keith, 2026-10-13: "given the complexity of this, the choices and the
#: options here ... just via the terminal"). Placing too (REQ-PIPE-163
#: criterion 14), which offers its periods as a choice.
TERMINAL_ONLY = (CHOOSE_FILE, PLACE)

#: The four that act on a SUPPLY - "what do I do with this thing that
#: arrived" - and so belong in the queue of supplies awaiting a decision
#: (criterion 16).
SUPPLY_SCOPED = (PROMOTE, REJECT, DEMOTE, REFILE, ACKNOWLEDGE, SUPERSEDE, UN_SUPERSEDE,
                 EXCUSE_LATENESS, WITHDRAW_EXCUSE, CHOOSE_FILE, PLACE, RECHECK)

#: The four that act on a PERIOD - how it is filled when a supply for it
#: never came. None of them answers a question about an arriving supply,
#: which is why criterion 31 puts them somewhere else entirely.
PERIOD_SCOPED = (SUBSTITUTE, DE_SUBSTITUTE, INHERIT, UN_INHERIT, MARK_NOT_SUPPLIED)

#: Which operations destroy something a reader depends on, and so need
#: an explicit confirmation on every route (criteria 9 and 28, and
#: REQ-PIPE-099 criterion 10). The TUI confirms EVERYTHING (criterion
#: 28); these are the ones the underlying operation refuses without it,
#: so a route that forgot to ask is refused rather than obeyed.
NEEDS_CONFIRMATION = (REFILE, DE_SUBSTITUTE, UN_INHERIT)


#: WHICH DECISIONS REQUIRE A ROLE, and at which level (REQ-GHUB-171 criterion
#: 3): operation -> (role, people.DATA_ASSET or "agency"). Checked here, in the
#: one implementation every route shares (its NFR 1). EMPTY TODAY: the one
#: decision that needs a role - REQ-PIPE-170's confirmation of a correction's
#: moves, by the asset manager - is asset-wide rather than a slot operation,
#: so it is not among these and checks the role in correction_apply.confirm.
REQUIRED_ROLE: dict[str, tuple[str, str]] = {}


class NotOffered(Exception):
    """An operation neither route offers.

    SEPARATE FROM DecisionRefused because the answers differ: a refusal
    means "this decision is not permitted and here is why", which an
    operator can act on, and this means "that is not a thing", which is
    usually a typo in a comment.
    """


@dataclass(frozen=True)
class Request:
    """What somebody asked for, before anybody has decided whether it is
    allowed.

    FROZEN, and carrying the ACTOR RECORD rather than a name, so that
    the actor written into the log is the one that was identified rather
    than a string that travelled alongside. Criterion 4's "SHALL NOT
    accept an actor stated in the body" is enforced by the GitHub
    adapter having nowhere to put one.
    """

    operation: str
    dataset_id: str
    actor: dict
    reason: str
    #: The period the decision concerns. Every operation names one:
    #: which slot a supply is promoted into, rejected out of, or which
    #: period is being substituted or inherited.
    period: str | None = None
    #: A re-file's destination, and nothing else's.
    to_period: str | None = None
    #: The supply being acted on, where the operation acts on one.
    supply: str | None = None
    #: The period a substitution stands on.
    stands_on: str | None = None
    confirmed: bool = False
    #: The LAST period of a range excuse (REQ-PIPE-161 criteria 9 and 15);
    #: `period` is its first. None for every other decision.
    through_period: str | None = None
    #: The key of the consequences the person was shown and confirmed
    #: (REQ-PIPE-128 criteria 6 and 9) - None where nothing was shown.
    acknowledged: str | None = None
    #: A settlement's answer for each file of the pair (REQ-PIPE-193):
    #: settlement.Answer per file. Empty for every other decision.
    file_outcomes: tuple = ()

    @property
    def actor_name(self) -> str:
        return people.actor_name(self.actor)


@dataclass(frozen=True)
class Outcome:
    """What happened, in the terms both routes report in.

    `changed` IS THE FIELD THAT MATTERS. A decision that changed nothing
    because the log already recorded that outcome is a success with
    `changed=False` - never a refusal (criterion 26) - and a route that
    tells an operator "already done" is telling them something true and
    useful. `ticket_reconciler` is only called where something changed,
    for the same reason REQ-GHUB-109 gave: a ticket that says something
    new, or says nothing.
    """

    operation: str
    dataset_id: str
    period: str | None
    changed: bool
    message: str
    #: The re-checks this decision left owed (REQ-PIPE-140 criterion 7), in
    #: the order they run - run by the terminal while the person waits, by
    #: the processing pass for a decision made on GitHub (Keith, 2026-10-05).
    #: A TUPLE since a settlement owes up to two (REQ-PIPE-193 criterion 21).
    owed: tuple[int, ...] = ()
    #: Whether the owed checks finished where a route ran them while the
    #: person waited (REQ-PIPE-163 criterion 28) - None where none ran.
    checks_finished: bool | None = None


@dataclass(frozen=True)
class Consequences:
    """What a decision does beyond the slot it names, as lines for one
    warning panel, and the key a confirmation names (REQ-PIPE-128
    criteria 6, 7 and 9). No lines means no panel."""

    lines: tuple[str, ...]
    #: What the success message confirms was done - the things the person
    #: was warned about, said back at the end.
    done: tuple[str, ...] = ()
    #: Said in the panel but NOT part of the key: what always follows the
    #: decision, so confirming it adds nothing - a settlement's QA runs
    #: (Keith, 2026-10-13, post-build-review #170).
    notes: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        import hashlib

        return hashlib.sha1("\n".join(self.lines).encode()).hexdigest()[:10] if self.lines else ""


class ConsequencesNotAcknowledged(decision_log.DecisionRefused):
    """A decision with consequences, not confirmed against the warning in
    force now - never shown, or shown and since changed (criterion 9)."""

    def __init__(self, found: Consequences, *, given: str | None,
                 terminal_only: bool = False):
        self.lines, self.key, self.given = found.lines, found.key, given
        # A WRONG KEY IS NOT NECESSARILY A CHANGE (post-build-review #112):
        # it may be mistyped, and blaming something that did not happen
        # sends the person looking for it. Both are said.
        self.lead = (
            f"The key {given} does not match this decision's warning - mistyped, or what "
            f"the decision does has changed since it was shown. Nothing was done."
            if given else ("This decision has the consequences below, so it needs them "
                           "confirmed. Nothing was done." if terminal_only else
                           "This decision does more than its own slot, so it needs that "
                           "confirmed. Nothing was done."))
        # A TERMINAL-ONLY DECISION HAS NO TICKET TO COMMENT ON (#170).
        self.instruction = (
            f"To go ahead, confirm the current key {found.key}: add "
            f"`--acknowledge {found.key}` to the same command"
            + ("." if terminal_only else
               f", or on a ticket comment `acknowledge: {found.key}`."))
        super().__init__(
            self.lead + "\n" + "\n".join(f"  - {line}" for line in found.lines)
            + "\n" + self.instruction)


def consequences(conn, request: Request) -> Consequences:
    """Everything this decision does beyond the slot it names, each with
    how it is undone and what the affected period reads until then
    (REQ-PIPE-128 criteria 6 and 7). Empty where it does nothing more.

    Which OTHER supplies' checks read a table it moves and will be
    re-checked (criterion 8) is said too - from knock_on.readers(), the
    same answer the re-evaluation it owes will act on.
    """
    # ONE FILE OF AN OPEN PAIR IS REFUSED BEFORE ANYONE IS ASKED (REQ-PIPE-193
    # criterion 25): the warning is the first thing every route asks for.
    _refuse_on_an_open_pair(conn, request)
    # NOR A PROMOTE OF WHAT IS NOT FILED TO THIS PERIOD (#173): refused
    # before the reason is asked, for the same reason.
    _refuse_promoting_where_it_is_not_filed(conn, request)
    lines: list[str] = []
    done: list[str] = []
    if request.operation == PROMOTE and request.period and request.supply:
        from qa_tools.common import promotion

        ds, period, supply = request.dataset_id, request.period, request.supply
        # REFUSED BEFORE THE PROMPT where it cannot happen (Keith,
        # 2026-10-05, post-build-review #112): an inherited slot, or a
        # displaced supply a later period stands on. Asking someone to
        # confirm a decision about to be refused undoes the point of the yes.
        h = promotion._refuse_what_the_slot_forbids(
            conn, ds, supply, period, decision_log.PERSON, remove_substitution=True)
        if h and h.held_as == decision_log.PROMOTED and h.holder != supply:
            decision_log.refuse_if_stood_on(conn, ds, h.holder, decision_log.SUPERSEDE)
            # THE UNDO, HONESTLY (Keith, 2026-10-05): un-supersede returns
            # it to waiting only; putting it back takes a promotion too.
            lines.append(
                f"{h.holder}, the supply {period} holds now, moves to superseded. "
                f"{period} reads {supply} from this decision on. To put {h.holder} back, "
                f"un-supersede it (it returns to waiting), then promote it again:\n"
                f"  mothman supply decide --operation un-supersede --dataset {ds} "
                f"--period {period} --supply {h.holder} --reason '<why>' --yes\n"
                f"  mothman supply decide --operation promote --dataset {ds} "
                f"--period {period} --supply {h.holder} --reason '<why>'")
            done.append(f"{h.holder} moved to superseded.")
        elif h and h.held_as == decision_log.SUBSTITUTED:
            lines.append(
                f"The substitution of {period} onto {h.stands_on} ({h.holder}) is "
                f"removed. {period} reads {supply} from this decision on. To restore the "
                f"substitution, demote {supply}, then substitute again:\n"
                f"  mothman supply decide --operation demote --dataset {ds} "
                f"--period {period} --supply {supply} --reason '<why>'\n"
                # THE SUPPLY STOOD ON, NAMED (#112 re-check): left out, the
                # command took the slot's own supply - the one just demoted -
                # and the substitution was refused.
                f"  mothman supply decide --operation substitute --dataset {ds} "
                f"--period {period} --stands-on {h.stands_on} --supply {h.holder} "
                f"--reason '<why>'")
            done.append(f"The substitution of {period} onto {h.stands_on} was removed.")
    if request.operation == REFILE and request.supply and request.to_period:
        lines, done = _refile_consequences(conn, request)
    if request.operation == PLACE:
        lines, done = _place_consequences(conn, request)
    notes: list[str] = []
    if request.operation == CHOOSE_FILE:
        lines, done, notes = _settlement_consequences(conn, request)
    if request.operation == EXCUSE_LATENESS and request.through_period:
        lines, done = _range_consequences(conn, request)
    readers = _readers_rechecked(conn, request)
    if readers:
        lines += readers
        count = readers[0].count("\n")
        done.append(f"{count} supply/supplies reading it owed a re-check.")
    return Consequences(lines=tuple(lines), done=tuple(done), notes=tuple(notes))


#: These move a table only where the supply named is the one the period holds.
_MOVES_IF_HELD = (DEMOTE, REJECT, REFILE)


def _readers_rechecked(conn, request: Request) -> list[str]:
    """REQ-PIPE-128 criterion 8: the OTHER supplies whose checks read the
    table this decision moves, which the re-evaluation it owes
    (REQ-PIPE-121) will re-check - said only where the decision really
    changes what the period holds, since a promise of a re-check that does
    not happen would be false."""
    from qa_tools.common import hierarchy, knock_on, promotion

    period, ds, op = request.period, request.dataset_id, request.operation
    if not period:
        return []
    held = decision_log.held(conn, ds, period)
    holder = held.holder if held else None
    held_as = held.held_as if held else None
    if op == PROMOTE:
        moves = bool(request.supply) and request.supply != holder
    elif op in _MOVES_IF_HELD:
        moves = bool(request.supply) and request.supply == holder
    elif op == UN_INHERIT:
        moves = held_as == decision_log.INHERITED
    elif op == DE_SUBSTITUTE:
        moves = held_as == decision_log.SUBSTITUTED
    elif op == INHERIT:
        # THE OPERATION'S OWN REFUSALS, so a re-check is never promised for
        # an inheritance about to be refused (delivery-critic on 128 c8).
        from qa_tools.common import inheritance
        moves = inheritance.inherit_one_refusal(conn, ds, period) is None
    elif op == SUBSTITUTE and request.stands_on and request.supply:
        from qa_tools.common import substitution
        try:
            substitution._refuse_unless_substitutable(
                conn, dataset_id=ds, period=period, stands_on=request.stands_on,
                supply=request.supply, participates=True)
            moves = True
        except substitution.SubstitutionRefused:
            moves = False
    else:
        moves = False
    if not moves:
        return []
    table = hierarchy.dataset(ds).table
    found = [r for r in knock_on.readers(conn, period, [table], promotion._declared_reads())
             if r.dataset_id != ds]
    if not found:
        return []
    # IN PLAIN TERMS (REQ-GHUB-142 NFR 2, as the re-file warning): datasets
    # by name, supplies by the day they arrived - ids are for commands only.
    # ONE ENTRY, its readers indented inside it, so a route that bullets
    # each entry shows one bullet with its list rather than a bullet each.
    from qa_tools.common import asset_time, filing

    def described(r) -> str:
        received = filing.received_at_of(r.dataset_id, r.supply)
        day = (asset_time.local_date(received.isoformat()).strftime("%-d %B %Y")
               if received else "an unknown date")
        state = "waiting" if r.waiting else "accepted"
        return f"    {hierarchy.dataset(r.dataset_id).dataset_name}, received {day} ({state})"

    name = hierarchy.dataset(ds).dataset_name
    return ["\n".join(
        [f"Checks in other datasets read {name} in {period}. Each of these supplies is "
         f"owed a re-check by this decision, and may go red:"]
        + [described(r) for r in found])]


def _range_consequences(conn, request: Request) -> tuple[list[str], list[str]]:
    """A range excuse's warning: which supplies it excuses and which it
    skips and why (REQ-PIPE-161 criterion 16), from the same plan the
    decision applies - so the key changes if the set does. A range that
    would excuse nothing is refused here, before anyone confirms
    (criterion 17)."""
    from qa_tools.common import excuse

    plan = excuse.range_plan(conn, request.dataset_id, request.period,
                             request.through_period)
    span = f"{request.period} to {request.through_period}"
    if not plan.excuse:
        skipped = "".join(f"\n  - {s} ({slot}): {why}" for s, slot, why in plan.skipped)
        raise decision_log.DecisionRefused(
            f"nothing in {span} for {request.dataset_id} can be excused, so nothing was "
            f"done." + (f" Every supply filed there was skipped:{skipped}" if skipped
                        else " No supply is filed in those periods."))
    lines = [f"Excuses {len(plan.excuse)} late supply/supplies of {request.dataset_id} "
             f"in {span}, one entry each, with this reason:"]
    lines += [f"  excuse {s} ({slot})" for s, slot in plan.excuse]
    if plan.skipped:
        lines.append(f"Skips {len(plan.skipped)}:")
        lines += [f"  skip {s} ({slot}) - {why}" for s, slot, why in plan.skipped]
    lines.append("Each stays late, shown as excused. To undo one: "
                 "mothman supply decide --operation withdraw-excuse "
                 f"--dataset {request.dataset_id} --period <period> --supply <supply> "
                 "--reason '<why>'")
    return lines, [f"{len(plan.excuse)} supply/supplies excused."]


def _refile_consequences(conn, request: Request) -> tuple[list[str], list[str]]:
    """A re-file's warning (REQ-GHUB-142), from the SAME plan that applies
    it (criterion 2) - so what is confirmed is what happens. Refused here,
    before anyone is asked, where the plan refuses.

    IN PLAIN TERMS (criterion 5, NFR 2): periods and tables by name, dates
    on the asset's own calendar, and supply ids only in the commands to
    paste - "This removes 2026-Q3's accepted Clients and supersedes
    2026-Q2's waiting Clients from 14 May"."""
    from qa_tools.common import asset_time, refiling

    p = refiling.plan(conn, dataset_id=request.dataset_id, supply=request.supply,
                      to_period=request.to_period)
    name = hierarchy.dataset(request.dataset_id).dataset_name

    def day(iso: str) -> str:
        return asset_time.local_date(iso).strftime("%-d %B %Y") if iso else "an unknown date"

    lines: list[str] = []
    done: list[str] = []
    if p.promoted:
        lines.append(
            f"This removes {p.from_period}'s accepted {name} (received {day(p.received)}). "
            f"{p.from_period} has no accepted {name} until another is promoted. To put it "
            f"back, re-file it to {p.from_period}, then promote it there once checked:\n"
            f"  mothman supply decide --operation refile --dataset {p.dataset_id} "
            f"--period {p.to_period} --supply {p.supply} --to-period {p.from_period} "
            f"--reason '<why>'\n"
            f"  mothman supply decide --operation promote --dataset {p.dataset_id} "
            f"--period {p.from_period} --supply {p.supply} --reason '<why>'")
        done.append(f"{p.from_period}'s accepted {name} was taken out.")
    # WHAT THE TARGET READS AFTERWARDS (post-build-review #114, D3): never
    # the re-filed supply straight away - it waits to be checked, and a
    # version already promoted there stays until it is (REQ-PIPE-141
    # criteria 4 and 9).
    if p.target_held_as in (decision_log.PROMOTED, decision_log.SUBSTITUTED):
        after = (f"{p.to_period} keeps its accepted {name} until the re-filed one is "
                 f"checked and promoted.")
    else:
        after = (f"{p.to_period} has no accepted {name}; the re-filed one waits there to "
                 f"be checked, and the promotion gate decides.")
    if not p.displaced and p.target_held_as in (decision_log.PROMOTED,
                                                 decision_log.SUBSTITUTED):
        # WHAT THE TARGET READS UNTIL THEN (REQ-GHUB-142 criterion 6; post-
        # build-review #115, W7): a re-file into a period that already holds
        # an accepted version said nothing about that period at all.
        lines.append(
            f"{after} Only a promotion of the re-filed one - by a person, or by the "
            f"promotion gate where the replacement setting allows - replaces it.")
    for d in p.displaced:
        lines.append(
            f"This supersedes {p.to_period}'s waiting {name} from {day(d.received)}. "
            f"{after} To bring the superseded one back, first reject, supersede or re-file "
            f"the re-filed one out of {p.to_period}, then un-supersede it:\n"
            f"  mothman supply decide --operation un-supersede --dataset {p.dataset_id} "
            f"--period {p.to_period} --supply {d.supply} --reason '<why>' --yes")
        done.append(f"{p.to_period}'s waiting {name} from {day(d.received)} was superseded.")
    return lines, done


def place_plan(conn, request: Request):
    """The placement's one plan, refused here where it cannot happen - so
    every route is refused before anyone is asked (REQ-PIPE-163)."""
    from qa_tools.common import placing

    if not request.supply:
        raise decision_log.DecisionRefused(
            "a placement names the held supply, with --supply.")
    if not request.to_period:
        raise decision_log.DecisionRefused(
            "a placement names the period it goes into, with --to-period.")
    return placing.plan(conn, dataset_id=request.dataset_id, supply=request.supply,
                        to_period=request.to_period)


def _place_consequences(conn, request: Request) -> tuple[list[str], list[str]]:
    """A placement does nothing beyond its own slot - except for an open
    pair held whole, whose SECOND file moves with it (criterion 37), which
    is named and confirmed."""
    from qa_tools.common import placing

    p = place_plan(conn, request)
    if not p.is_pair:
        return [], []
    first, *rest = p.pair_files
    return ([f"Both files of this pair are placed into {p.to_period}, still contested: "
             f"{first} and {', '.join(rest)}. Neither is checked or promoted until the "
             f"pair is settled there, by saying what each file is."],
            [f"Both files ({' and '.join(p.pair_files)}) were placed, still contested - "
             f"settle the pair now, at '{placing.where_to_decide(p.dataset_id)}'."])


def terminal_only_reply(dataset_id: str, period: str | None,
                        operation: str = CHOOSE_FILE) -> str:
    """What the GitHub route says to a choose-file comment (REQ-PIPE-193
    criterion 16): made in the terminal, and where - the pair's files named
    as code, never a command to paste. And to a place comment (REQ-PIPE-163
    criterion 36), in the same terms."""
    from qa_tools.common import dataset_blockers, supply_files

    if operation == PLACE:
        return (f"Placing a held supply into a period is made in the terminal, not on "
                f"GitHub - it offers the periods it can go into as a choice. It is made at "
                f"'{supply_files.where_to_settle(dataset_id)}'.")

    files: tuple[str, ...] = ()
    try:
        with supply_db.connect(read_only=True, label="mothman:terminal-only") as conn:
            for blocker in dataset_blockers.contests(conn):
                if blocker.dataset_id != dataset_id or not blocker.is_open:
                    continue
                found = supply_files.resolve(conn, dataset_id, blocker.supply)
                if found is not None and found.period == period:
                    files = blocker.files
                    break
    except Exception:  # noqa: BLE001 - the reply stands without the names
        files = ()
    named = (" Two files arrived: " + " and ".join(f"`{f}`" for f in files) + "."
             if files else "")
    return (f"Settling two files for one table is made in the terminal, not on GitHub - it "
            f"asks what each file is, with several choices for each.{named} It is settled "
            f"at '{supply_files.where_to_settle(dataset_id)}'.")


def settlement_plan(conn, request: Request):
    """The settlement's one plan (REQ-PIPE-193 criterion 17): the warning
    and the effect are both built from it."""
    from qa_tools.common import settlement

    return settlement.plan(conn, dataset_id=request.dataset_id, supply=request.supply,
                           answers=list(request.file_outcomes))


def _settlement_consequences(conn, request: Request
                             ) -> tuple[list[str], list[str], list[str]]:
    """EVERY consequence beyond moving the files it names, in one panel
    above the single confirmation (criterion 17): a changed period or
    verdict, a superseded waiting version, a hold, a second supply in
    another period - and the QA runs that follow, how many, each file and
    period, and that a green one may be promoted with no further decision.
    In plain terms: files by name, datasets by name, periods by name."""
    from qa_tools.common import settlement

    p = settlement_plan(conn, request)
    name = hierarchy.dataset(request.dataset_id).dataset_name
    lines: list[str] = []
    done: list[str] = []
    for f in p.files:
        if f.outcome == settlement.SUPPLY and f.held:
            lines.append(
                f"{f.file.filename} is received too early or too late for any period of "
                f"{name} that is open, so it is HELD, not filed to {p.period} - a person "
                f"places it later, and it is not checked until then.")
            done.append(f"{f.file.filename} is held.")
        elif f.outcome == settlement.SUPPLY and f.period_after != p.period:
            lines.append(
                f"{f.file.filename}'s own receipt files it to {f.period_after}, not "
                f"{p.period}: the supply moves to {f.period_after}"
                + (f" and is judged {f.classification_after}" if f.classification_after
                   else "") + ".")
        elif f.outcome == settlement.SUPPLY and f.new_filing:
            lines.append(
                f"{f.file.filename}'s own receipt is the supply's, so {p.period}'s supply is "
                f"judged {f.classification_after or 'without a verdict'}"
                + (f" rather than {p.classification}" if p.classification else "")
                + ". A new filing records it; the earlier one is kept.")
        elif f.outcome == settlement.REFILE:
            lines.append(f"{f.file.filename} becomes a second supply, filed to "
                         f"{f.to_period} on its own receipt.")
        for d in f.displaced:
            lines.append(f"{name}'s version waiting in {f.checked_in or f.to_period} "
                         f"({d}) is superseded by {f.file.filename}.")
            done.append(f"A waiting version in {f.checked_in or f.to_period} was superseded.")
    # THE RUNS ARE LISTED, NEVER KEYED (Keith, 2026-10-13, #170): every
    # settlement that makes a supply owes them, so confirming them adds a
    # second invocation and nothing else.
    notes: list[str] = []
    if p.runs:
        runs = "1 QA run" if len(p.runs) == 1 else f"{len(p.runs)} QA runs"
        notes.append("\n".join(
            [f"Then {runs}, one at a time, while you wait:"]
            + [f"    {f.file.filename} against {f.checked_in}" for f in p.runs]
            + ["  A supply that comes out green may be promoted by the promotion gate "
               "with no further decision."]))
        done.append(f"{runs} owed.")
    return lines, done, notes


def _spoken(operation: str) -> str:
    """The operation as a person writes it - `re-file`, as the menu and the
    warnings say it, never the identifier (#115, W8)."""
    return {REFILE: "re-file", CHOOSE_FILE: "settlement",
            PLACE: "placement", RECHECK: "re-check"}.get(operation, operation)


def offered(operation: str) -> str:
    """The operation, or a refusal naming what is on offer.

    THE SAME EIGHT ON BOTH ROUTES (criterion 3's second half), which is
    a property of there being one list rather than a promise two
    adapters make.
    """
    if operation not in OPERATIONS:
        raise NotOffered(
            f"{operation!r} is not a filing decision. The {len(OPERATIONS)} are: "
            f"{', '.join(OPERATIONS)}.")
    return operation


def _reason(request: Request) -> str:
    """Criterion 10: a PERSON raising a decision gives a reason, and is
    refused without one.

    UNCONDITIONALLY, which is stricter than the decision log's own rule
    - that one asks for a reason where somebody will ask why a year
    later, and lets a routine automatic promotion go without. This is
    about a person: they are here, they are deciding something, and the
    cost of a sentence is nothing against a log entry nobody can
    explain.
    """
    reason = (request.reason or "").strip()
    if not reason:
        raise decision_log.DecisionRefused(
            f"{'an' if request.operation[0] in 'aeiou' else 'a'} {request.operation} needs "
            f"a reason. You are deciding this on "
            f"purpose, and somebody will ask why - this log is where they "
            f"will look.")
    return reason


def _confirmation(request: Request) -> None:
    """Criteria 9 and 28: the destructive ones are confirmed explicitly.

    REFUSED HERE AS WELL AS BY THE OPERATION, so a route that forgot to
    ask gets the same answer wherever it forgot. The operations below
    take `confirmed` as a required argument for the same reason: a
    prompt inside a function is skipped by the first caller that is not
    a terminal.
    """
    if request.operation in NEEDS_CONFIRMATION and not request.confirmed:
        raise decision_log.DecisionRefused(
            f"a {request.operation} needs an explicit confirmation. It changes "
            f"what a period resolves to for everybody reading it.")


def _already(conn, request: Request) -> str | None:
    """The sentence to say where this decision would change nothing, or
    None (criterion 26).

    ASKED OF THE LOG, never of the catalogue, for the reason every other
    question in this system is: a view in a schema says an object
    exists, not what put it there or whether somebody has since removed
    the indirection and left the object behind.
    """
    if request.operation == REJECT and request.supply:
        # A REPEAT IS ALREADY SO (found by REQ-GHUB-165's parity test): a
        # supply rejected and not promoted back since is not rejected twice.
        from qa_tools.common import refiling, supersession

        if (supersession._rejected(conn, request.dataset_id, request.supply)
                and not refiling._since_unrejected(conn, request.dataset_id, request.supply)):
            return f"{request.supply} is already rejected. Nothing to do."
    period = request.period
    if period is None:
        return None
    holds = decision_log.held(conn, request.dataset_id, period)

    if request.operation == PROMOTE:
        # NAMING A SUPPLY (#189 F10): on an empty period nothing and nothing
        # compared equal, and it said "None is already promoted".
        if request.supply and \
                decision_log.promoted_into(conn, request.dataset_id, period) == request.supply:
            return (f"{request.supply} is already promoted into {period}. "
                    f"Nothing to do.")
    elif request.operation == SUBSTITUTE:
        current = substitution.substituted(conn, request.dataset_id, period)
        if current is not None and current.stands_on == request.stands_on:
            return (f"{period} already stands on {request.stands_on}, by a "
                    f"substitution somebody already recorded. Nothing to do.")
    elif request.operation == INHERIT:
        if inheritance.inherited(conn, request.dataset_id, period) is not None:
            return f"{period} already inherits. Nothing to do."
    elif request.operation == DE_SUBSTITUTE:
        if substitution.substituted(conn, request.dataset_id, period) is None:
            return (f"{period} holds no substitution for {request.dataset_id}. "
                    f"Either it was never substituted or somebody has already "
                    f"removed it.")
    elif request.operation == MARK_NOT_SUPPLIED:
        from qa_tools.common import not_supplied

        already = not_supplied.marked(conn, request.dataset_id, period)
        if already is not None:
            return (f"{period} is already marked as not supplied for "
                    f"{request.dataset_id}, by {already.actor}. Nothing to do.")
    elif request.operation in (SUPERSEDE, UN_SUPERSEDE) and request.supply:
        # A REPEAT IS DONE ALREADY, not refused (criterion 26; post-build-
        # review #109, F14) - the same as every other filing decision.
        from qa_tools.common import supersession

        now = supersession.is_superseded(conn, request.dataset_id, request.supply)
        if request.operation == SUPERSEDE and now:
            return f"{request.supply} is already superseded. Nothing to do."
        if (request.operation == UN_SUPERSEDE and not now
                and supersession._latest(conn, request.dataset_id, request.supply)):
            return (f"{request.supply} has already been brought back from superseded. "
                    f"Nothing to do.")
    elif request.operation == UN_INHERIT:
        if inheritance.inherited(conn, request.dataset_id, period) is None:
            # NOT where it holds a SUBSTITUTION - that is a real
            # refusal, because the two are identical in SQL and opposite
            # in meaning and the operator has asked to undo the wrong
            # one. inheritance.un_inherit() says so in those words.
            if not (holds and holds.held_as == decision_log.SUBSTITUTED):
                return (f"{period} holds no inheritance for "
                        f"{request.dataset_id}. Nothing to do.")
    return None


def _apply_one(conn, request: Request, reason: str, *, effective_at: str) -> tuple[int, ...]:
    """Dispatch to the operation that owns this decision's effect.

    EVERY ONE OF THESE ALREADY EXISTS, and nothing here re-implements
    any of them. That is what makes this a single implementation rather
    than a third place a promotion could be defined: the module that
    owns the warehouse change owns it, and this decides only which one
    is being asked for.
    """
    entry = hierarchy.dataset(request.dataset_id)
    common = {"agency_id": entry.agency_id, "collection_id": entry.collection_id,
              "dataset_id": request.dataset_id, "actor": request.actor_name,
              "reason": reason, "effective_at": effective_at}

    if request.operation == PROMOTE:
        # A SUBSTITUTION IS REMOVED ONLY ONCE ITS CONSEQUENCE WAS CONFIRMED
        # (REQ-PIPE-128 criterion 4) - apply() has already held the person
        # to the warning, so reaching here is that confirmation.
        tables, source = _promotable(conn, request.dataset_id, request.supply)
        promotion.promote(
            conn, supply=request.supply, period=request.period,
            physical_tables=tables, from_schema=source,
            actor_kind=decision_log.PERSON, remove_substitution=True, **common)
    elif request.operation == REJECT:
        rejection.reject(
            conn, supply=request.supply, from_slot=request.period,
            # A promoted supply's table is in its period, not staging
            # (post-build-review #112): looking only in staging left it there.
            physical_tables=(_promoted_tables(conn, entry.table, request)
                             if _is_promoted(conn, request)
                             else _staged(conn, request.dataset_id, request.supply)),
            promoted=_is_promoted(conn, request), **common)
    elif request.operation == DEMOTE:
        rejection.demote(
            conn, supply=request.supply, from_slot=request.period,
            physical_tables=_promoted_tables(conn, entry.table, request), **common)
    elif request.operation == SUBSTITUTE:
        substitution.substitute(
            conn, logical_table=entry.table, period=request.period,
            stands_on=request.stands_on, supply=request.supply, **common)
    elif request.operation == DE_SUBSTITUTE:
        substitution.de_substitute(
            conn, logical_table=entry.table, period=request.period,
            confirmed=True, **common)
    elif request.operation == INHERIT:
        inheritance.inherit_one(
            conn, dataset_id=request.dataset_id, period=request.period,
            actor=request.actor_name, reason=reason, effective_at=effective_at)
    elif request.operation == MARK_NOT_SUPPLIED:
        from qa_tools.common import not_supplied

        not_supplied.mark(
            conn, agency_id=entry.agency_id, collection_id=entry.collection_id,
            dataset_id=request.dataset_id, period=request.period,
            actor=request.actor_name, reason=reason, effective_at=effective_at)
    elif request.operation == ACKNOWLEDGE:
        # CHANGES NO DATA (REQ-PIPE-122 criterion 15): one entry, nothing
        # moved. Whether it is owed is the log's to judge, inside the
        # transaction (criterion 14).
        with decision_log.apply_decision(conn, decision_log.Decision(
                agency_id=entry.agency_id, collection_id=entry.collection_id,
                dataset_id=request.dataset_id, action=decision_log.ACKNOWLEDGE,
                supply=request.supply, actor=request.actor_name,
                actor_kind=decision_log.PERSON, effective_at=effective_at,
                to_slot=request.period, reason=reason)):
            pass
    elif request.operation in (EXCUSE_LATENESS, WITHDRAW_EXCUSE):
        # CHANGES NO DATA (REQ-PIPE-161 criterion 4): one entry per supply,
        # nothing moved, nothing re-run. A range is one decision recorded
        # as one excuse per late supply in it (criterion 9).
        from qa_tools.common import excuse

        if request.operation == EXCUSE_LATENESS and request.through_period:
            plan = excuse.range_plan(conn, request.dataset_id, request.period,
                                     request.through_period)
            targets = list(plan.excuse)
        else:
            targets = [(request.supply, request.period)]
        # WHOLE OR NOT AT ALL (delivery-critic on 161, #4): one transaction
        # round every entry, so a supply another person excused since the
        # plan refuses the range rather than leaving it half-applied.
        with conn.raw.transaction():
            for supply, slot in targets:
                with decision_log.apply_decision(conn, decision_log.Decision(
                        agency_id=entry.agency_id, collection_id=entry.collection_id,
                        dataset_id=request.dataset_id, action=request.operation,
                        supply=supply, actor=request.actor_name,
                        actor_kind=decision_log.PERSON, effective_at=effective_at,
                        to_slot=slot, reason=reason)):
                    pass
    elif request.operation in (SUPERSEDE, UN_SUPERSEDE):
        from qa_tools.common import supersession

        act = supersession.supersede if request.operation == SUPERSEDE \
            else supersession.un_supersede
        owed = act(conn, agency_id=entry.agency_id, collection_id=entry.collection_id,
                   dataset_id=request.dataset_id, supply=request.supply,
                   period=request.period, actor=request.actor_name, reason=reason,
                   effective_at=effective_at)
        return (owed,) if owed is not None else ()
    elif request.operation == UN_INHERIT:
        inheritance.un_inherit(
            conn, dataset_id=request.dataset_id, period=request.period,
            actor=request.actor_name, reason=reason, effective_at=effective_at,
            confirmed=True)
    elif request.operation == REFILE:
        # REQ-PIPE-141: refiling owns the effect, from one plan shared
        # with the warning (REQ-GHUB-142 criterion 2).
        from qa_tools.common import refiling

        p = refiling.plan(conn, dataset_id=request.dataset_id, supply=request.supply,
                          to_period=request.to_period)
        return (refiling.apply(conn, p, agency_id=entry.agency_id,
                               collection_id=entry.collection_id,
                               actor=request.actor_name, reason=reason,
                               effective_at=effective_at),)
    elif request.operation == PLACE:
        # REQ-PIPE-163: placing owns the effect, through the one placer.
        from qa_tools.common import placing

        return placing.apply(conn, place_plan(conn, request), agency_id=entry.agency_id,
                             collection_id=entry.collection_id, actor=request.actor_name,
                             reason=reason, effective_at=effective_at)
    elif request.operation == RECHECK:
        # REQ-PIPE-164: the decision and its owed re-check, nothing run here
        # (criterion 3) - the route runs it after the commit, or leaves it owed.
        from qa_tools.common import rechecking

        return (rechecking.record(conn, agency_id=entry.agency_id,
                                  collection_id=entry.collection_id,
                                  dataset_id=request.dataset_id, supply=request.supply,
                                  period=request.period, actor=request.actor_name,
                                  reason=reason, effective_at=effective_at),)
    elif request.operation == CHOOSE_FILE:
        # REQ-PIPE-193: settlement owns the effect, from the plan the
        # warning was built from.
        from qa_tools.common import settlement

        p = settlement_plan(conn, request)
        _entry, owed = settlement.apply(
            conn, p, agency_id=entry.agency_id, collection_id=entry.collection_id,
            actor=request.actor_name, reason=reason, effective_at=effective_at,
            answers=list(request.file_outcomes))
        return owed
    return ()


def _staged(conn, dataset_id: str, supply: str) -> list[str]:
    """The physical tables this supply has in staging, by the one resolver
    (REQ-PIPE-193 criterion 13): an ordinary supply's one, a settled pair's
    supply's own file's - never the other file's - and an open pair's both.
    Only those actually in staging."""
    from qa_tools.common import supply_files

    return supply_files.tables_in(conn, dataset_id, supply, supply_db.STAGING_SCHEMA)


def _promotable(conn, dataset_id: str, supply: str) -> tuple[list[str], str]:
    """(tables, the schema they are in) a person's promotion takes: staging,
    or - for a supply a person REJECTED - the rejected schema, which is how
    a rejection is reversed (REQ-PIPE-075 criterion 9; REQ-PIPE-193
    criteria 3 and 26). No route could do it until post-build-review #170:
    promote looked only in staging, and refiling's own refusal advised it."""
    from qa_tools.common import supply_files

    staged = _staged(conn, dataset_id, supply)
    if staged:
        return staged, supply_db.STAGING_SCHEMA
    rejected = supply_files.tables_in(conn, dataset_id, supply, supply_db.REJECTED_SCHEMA)
    if rejected:
        return rejected, supply_db.REJECTED_SCHEMA
    return [], supply_db.STAGING_SCHEMA


def _promoted_tables(conn, logical: str, request: Request) -> list[str]:
    """The physical tables a period holds for this dataset."""
    from qa_tools.common import period_schema

    return list(period_schema.promoted_in(
        conn, request.period, [logical]).get(logical) or [])


def _is_promoted(conn, request: Request) -> bool:
    return decision_log.promoted_into(
        conn, request.dataset_id, request.period) == request.supply


def _refuse_promoting_where_it_is_not_filed(conn, request: Request) -> None:
    """A PERSON PROMOTES A SUPPLY ONLY INTO THE PERIOD IT IS FILED TO
    (post-build-review #173; Keith, 2026-10-13: "there should be no way to
    move things into a period and then skip doing checks"). A supply's QA
    runs against the period it is FILED to, so a held supply, one never
    filed, or one filed elsewhere would go in unchecked for this period.

    Here, in the one implementation every person's route shares - the
    terminal, the flags, a GitHub comment, scripted playback. The rule's
    own gate already promotes only into the filed period and refuses a held
    or unperioded supply (promotion.after_run), so it needs no second check.
    """
    if request.operation != PROMOTE or not request.supply or not request.period:
        return
    from qa_tools.common import filing

    rows = conn.execute(
        f"SELECT slot FROM {filing.CURRENT} WHERE dataset_id = ? AND supply_id = ?",
        [request.dataset_id, request.supply]).fetchall()
    where = rows[0][0] if rows else None
    if not rows:
        raise decision_log.DecisionRefused(
            f"{request.supply} is not filed to any period, so nothing has checked it "
            f"against {request.period}. A supply is promoted only into the period it "
            f"is filed to. Nothing was recorded.")
    if where is None:
        # THE HOLD'S OWN RESPONSES (REQ-PIPE-163 criterion 38), each command
        # on a line of its own.
        from qa_tools.common import supply_holds

        held = supply_holds.hold_on(conn, request.dataset_id, request.supply)
        raise decision_log.DecisionRefused(
            f"{request.supply} is held - it arrived when no period of "
            f"{request.dataset_id} was open - so its data has never been checked against "
            f"{request.period}, and it cannot be promoted there. Nothing was recorded.\n"
            + held_responses(request.dataset_id, request.supply, held))
    if where != request.period:
        raise decision_log.DecisionRefused(
            f"{request.supply} is filed to {where}, not {request.period}, so its checks ran "
            f"against {where}. Promote it there, or re-file it to {request.period} so its "
            f"checks run against that period first:\n"
            f"  mothman supply decide --operation refile --dataset {request.dataset_id} "
            f"--period {where} --supply {request.supply} --to-period {request.period} "
            f"--reason '<why>'")
    _refuse_promoting_what_is_not_checked_there(conn, request)


def held_responses(dataset_id: str, supply: str, held) -> str:
    """What can be done about a held supply, as its hold's label works them
    out (REQ-PIPE-163 criteria 12 and 38): place - its menu path and flag
    form - or reject, for a plain hold; adding dates for a schedule-ended one.
    Each command on a line of its own."""
    from qa_tools.common import placing

    if held is not None and held.schedule_ended:
        return ("Add the next delivery dates to contract/calendar.yaml and it files itself. "
                "Where a declared correction is needed:\n  mothman schedule draft-correction")
    return (f"Place it into the period it belongs to, at '{placing.where_to_decide(dataset_id)}', "
            f"or:\n  {placing.flag_form(dataset_id, supply)}\n"
            f"Or reject it:\n"
            f"  mothman supply decide --operation reject --dataset {dataset_id} "
            f"--supply {supply} --reason '<why>'")


def _refuse_promoting_what_is_not_checked_there(conn, request: Request) -> None:
    """NOR BEFORE ITS CHECKS HAVE RUN AGAINST THAT FILING (post-build-review
    #173 fix 2; Keith, 2026-10-13). A re-filed or settled supply is owed a
    re-check, and until it runs its verdicts are the old period's - so a
    promote is refused while a re-check is owed for the supply, or when no
    run of its own checks has completed since its latest filing. Red and
    amber stay a person's to promote; what is refused is no verdict at all
    for where it now stands."""
    from qa_tools.common import filing, qa_store, recheck

    owed = [o for o in recheck.owed(conn, request.dataset_id)
            if o.kind == recheck.RECHECK and o.supply_id == request.supply]
    if owed:
        raise decision_log.DecisionRefused(
            f"{request.supply} has a re-check owed against {request.period}, so the "
            f"verdicts it has now are from before it was last filed or settled. Let the "
            f"re-check run first - `mothman pipeline process` runs every owed one - and "
            f"then decide on its result. Nothing was recorded.")
    rows = conn.execute(
        f"SELECT f.recorded_at, r.completed_at FROM {filing.CURRENT} f "
        f'LEFT JOIN "{qa_store.SCHEMA}".supply_current_run r '
        "ON r.dataset_id = f.dataset_id AND r.supply_id = f.supply_id "
        "WHERE f.dataset_id = ? AND f.supply_id = ?",
        [request.dataset_id, request.supply]).fetchall()
    filed_at, completed_at = rows[0] if rows else (None, None)
    if completed_at is None or (filed_at is not None and completed_at < filed_at):
        raise decision_log.DecisionRefused(
            f"{request.supply} has no run of its checks that completed since it was "
            f"filed to {request.period}, so nothing has checked it there yet. Wait for "
            f"its run to finish (`mothman pipeline process` runs anything owed), then "
            f"decide on its result. Nothing was recorded.")


def _refuse_promoting_what_never_loaded(conn, request: Request) -> None:
    """REQ-PIPE-153 criterion 6: a supply whose current load record is
    FAILED cannot be promoted, on any route. Promotion moves the tables it
    is given - none - and would record a period filled by a supply nothing
    can read. Refused naming the failed load and its recorded reason, and
    before anything is written. ITS OWN FILE'S load (REQ-PIPE-193 criterion
    13): a refused sibling file says nothing about a settled supply."""
    if request.operation != PROMOTE or "@" not in (request.supply or ""):
        return
    from qa_tools.common import load_log, supply_files

    found = supply_files.resolve(conn, request.dataset_id, request.supply)
    if found is None or not found.refused or found.tables:
        return
    record = load_log.latest_for(found.refused[0], conn=conn)
    why = (record.reason if record else None) or "no reason was recorded"
    raise decision_log.DecisionRefused(
        f"{request.supply} could not be loaded ({why}), so there is nothing "
        f"to promote. Reject it, or fix the fault and reprocess the delivery. "
        f"Nothing was recorded.")


#: What a person may NOT do to one file of an open pair, on any route: the
#: pair is settled by saying what each file is (REQ-PIPE-193 criterion 25,
#: REQ-PIPE-194 criteria 4 and 6). Promoting it would put two versions of
#: one table into the period (REQ-PIPE-128).
_NOT_ON_AN_OPEN_PAIR = (PROMOTE, REJECT, SUPERSEDE, REFILE, DEMOTE, ACKNOWLEDGE,
                        EXCUSE_LATENESS, WITHDRAW_EXCUSE, UN_SUPERSEDE, RECHECK)


class OpenPair(decision_log.DecisionRefused):
    """A plain decision about one file of an open pair (criterion 25). The
    CLI route prints the settle form with the real filenames below it."""

    def __init__(self, message: str, *, dataset_id: str, period: str | None,
                 supply: str, files: tuple[str, ...]):
        super().__init__(message)
        self.dataset_id, self.period, self.supply, self.files = (
            dataset_id, period, supply, files)


def _refuse_on_an_open_pair(conn, request: Request) -> None:
    """Refused before anything is written, saying where the pair is settled
    - judged by the open contest (dataset_blockers), never by the shape of
    the supply id (REQ-PIPE-194 criterion 8)."""
    if request.operation not in _NOT_ON_AN_OPEN_PAIR or "@" not in (request.supply or ""):
        return
    from qa_tools.common import supply_files

    contest = supply_files.open_contest(conn, request.dataset_id, request.supply)
    if contest is None:
        return
    name = hierarchy.dataset(request.dataset_id).dataset_name
    raise OpenPair(
        f"Two files arrived for {name}'s table ({' and '.join(contest.files)}), and nothing "
        f"yet says which is the supply, so a {_spoken(request.operation)} of one of them "
        f"is not recorded. The pair is settled by saying what each file is, at "
        f"'{supply_files.where_to_settle(request.dataset_id)}' - where 'reject both' "
        f"rejects each file on its own, so either can be brought back alone"
        # A RE-CHECK IS NOT NEEDED THERE (REQ-PIPE-164 criterion 22): the
        # settlement runs the checks itself (REQ-PIPE-193 criterion 21).
        + (", and where settling it checks each file that becomes a supply"
           if request.operation == RECHECK else "")
        + ". Nothing was recorded.",
        dataset_id=request.dataset_id, period=request.period, supply=request.supply,
        files=contest.files)


def apply(request: Request, *, effective_at: str, conn=None) -> Outcome:
    """Raise one filing decision, from whichever route.

    THE ORDER IS THE REQUIREMENT read in sequence: is this a thing
    (criterion 3), may this person do it (6, 14), did they say why (10),
    did they confirm it (9, 28), would it change anything (26), and only
    then the effect - whose own judgement, inside the transaction, is
    criteria 20 and 21.

    THE TICKET IS RECONCILED BY REQ-PIPE-083's OWN PASS (criterion 8),
    not by anything composed here. A decision taken in the terminal
    appears on its ticket the same way one raised on the ticket does,
    said once and in the same words - which is a property of there being
    one writer rather than a promise two of them keep.
    """
    offered(request.operation)
    if not request.actor:
        raise people.UnknownActor(
            "a filing decision needs an identified person. Nobody raised this.")
    if request.operation == PROMOTE and not request.supply:
        # A PROMOTION NAMES WHAT IT PROMOTES (#189 F10): with none, an empty
        # period's "already promoted" check compared nothing with nothing.
        raise decision_log.DecisionRefused(
            f"A promotion names the supply it promotes into {request.period} - pass "
            f"--supply. `mothman supply queue` lists what is waiting. Nothing was recorded.")
    # THE PLAYBACK LOCK, HERE AS WELL AS AT THE LOOKUP (REQ-GEN-135 NFR 2:
    # each lock refuses on its own). The lookup refused the synthetic actor
    # outside playback, but a caller already holding its record could reach
    # this path directly (sprint 11 critic, defect 3).
    if (isinstance(request.actor, dict) and people.is_synthetic(request.actor)
            and not people.in_playback()):
        raise people.UnknownActor(
            f"{request.actor.get('email')!r} is the scripted history's synthetic actor, "
            f"which can raise a decision only while a synthetic history is being "
            f"played back.")
    required = REQUIRED_ROLE.get(request.operation)
    if required:
        # A NON-RECORD ACTOR IS REFUSED, not waved past (delivery-critic on
        # 171, #3): require_role refuses anything that is not an identified
        # person.
        role, level = required
        agency = hierarchy.dataset(request.dataset_id).agency_id if level == "agency" else None
        people.require_role(request.actor, role, level, agency)
    reason = _reason(request)
    if request.operation != REFILE:
        _confirmation(request)

    if conn is None:
        with supply_db.connect(label="mothman:filing-decision") as opened:
            return apply(request, effective_at=effective_at, conn=opened)

    _refuse_on_an_open_pair(conn, request)
    if request.operation == REFILE:
        # REFUSED BEFORE ANYONE IS ASKED TO CONFIRM (decision 13; post-build-
        # review #114, D5): a re-file's refusals - rejected, contested,
        # inherited, stood on - come from its plan, which needs the
        # database, so on the GitHub route a rejected supply was asked to
        # confirm first and refused only after. The terminal already asked
        # in this order.
        consequences(conn, request)
        _confirmation(request)

    _refuse_promoting_what_never_loaded(conn, request)
    _refuse_promoting_where_it_is_not_filed(conn, request)
    if request.operation == RECHECK:
        # WHERE IT IS FILED, AND ONLY A WAITING OR PROMOTED SUPPLY (REQ-PIPE-164
        # criteria 10 and 23), refused before anything is written.
        from dataclasses import replace

        from qa_tools.common import rechecking

        where = rechecking.standing(conn, request.dataset_id, request.supply or "",
                                    request.period)
        rechecking.refuse_a_backstopped_dataset(conn, request.dataset_id)
        request = replace(request, period=where.period)
    already = _already(conn, request)
    if already is not None:
        return Outcome(operation=request.operation, dataset_id=request.dataset_id,
                        period=request.period, changed=False, message=already)

    # ONE CONFIRMATION, AGAINST THE WARNING IN FORCE NOW (REQ-PIPE-128
    # criteria 6 and 9): a decision with consequences goes ahead only
    # where the person confirmed exactly these; anything else is refused
    # with the warning as it stands.
    found = consequences(conn, request)
    if found.lines and request.acknowledged != found.key:
        raise ConsequencesNotAcknowledged(
            found, given=request.acknowledged,
            terminal_only=request.operation in TERMINAL_ONLY)

    owed = _apply_one(conn, request, reason, effective_at=effective_at)
    if request.operation == PLACE:
        # CALLED A PLACEMENT (criterion 41), never "re-file None -> period".
        from qa_tools.common import placing

        return Outcome(
            operation=PLACE, dataset_id=request.dataset_id, period=request.to_period,
            changed=True, owed=owed,
            message=(f"{request.supply} {placing.said(request.to_period)} for "
                     f"{request.dataset_id}, by {request.actor_name}."
                     + "".join(f" {line}" for line in found.done)))
    return Outcome(
        operation=request.operation, dataset_id=request.dataset_id,
        period=request.period, changed=True, owed=owed,
        message=(f"{_spoken(request.operation)} recorded for {request.dataset_id} "
                 f"{request.period or ''}".strip()
                 # WHERE IT WENT (post-build-review #115, W6): "re-file recorded
                 # for X 2026-Q3" read as though it went INTO Q3.
                 + (f" -> {request.to_period}" if request.operation == REFILE else "")
                 + f", by {request.actor_name}."
                 + "".join(f" {line}" for line in found.done)))


def reconcile_after(outcome: Outcome, collection_id: str) -> None:
    """Bring the slot's ticket up to date, through REQ-PIPE-083's pass.

    ONLY WHERE SOMETHING CHANGED. A no-op leaves the log exactly as the
    last pass found it, so the pass would correctly find nothing changed
    and say nothing - running it would be work to produce silence.

    NEVER FAILS THE DECISION. The entry is committed by the time this
    runs; an unreachable ticket service is a ticket that is a pass
    behind, which the next pass fixes, and losing the decision over it
    would be the wrong trade in the wrong direction.
    """
    if not outcome.changed:
        return
    from qa_tools.common import ticket_reconciler

    try:
        ticket_reconciler.report(ticket_reconciler.after_runs(collection_id))
    except Exception as exc:  # noqa: BLE001 - see the docstring
        print(f"note: the decision is recorded; its ticket could not be "
              f"reconciled ({type(exc).__name__}: {exc}). The next pass will "
              f"pick it up.")
