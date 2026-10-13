"""What arrived, what is promoted, and why they differ (REQ-DASH-056).

THE TWO LOOK IDENTICAL ON THE PAGE TODAY, and that is the whole problem.
A data engineer triaging a red dataset cannot tell "their latest file is
bad" from "the data everyone downstream is using is bad". The first is a
supplier's problem and nothing has changed for anyone reading the
warehouse; the second is an incident.

RECORDED HISTORY ONLY, never supply rows (criterion 5). Arrived and
promoted are both facts somebody WROTE DOWN - a filing and a decision -
so this reads the two record tables and nothing else. It opens its own
connection for the same reason filing.filled_slots() does: a narrow
reader can only answer questions about records, where a connection
handed to a build could answer any question at all.

QUIET WHEN THEY AGREE (criterion 3). The ordinary state of a healthy
dataset is that the latest arrival IS what is promoted, and a panel
section saying so on all thirty datasets is exactly the noise this
requirement's own non-functional constraint forbids. So `differs` is
False in the ordinary case and the page renders nothing extra.
"""
from __future__ import annotations

from dataclasses import dataclass

from qa_tools.common import asset_time, decision_log, supply_db

#: Why an arrival is not the promoted supply (criterion 4). Three
#: reasons, and they are different actions for whoever reads them: wait,
#: nothing to do, or go and fix the schedule.
AWAITING_DECISION = "awaiting-decision"
RETURNED_BY_A_PERSON = "returned-by-a-person"
REJECTED = "rejected"
NO_SLOT = "no-slot"
SUPERSEDED = "superseded"
#: AN OPEN CONTEST (REQ-DASH-197 criterion 4): the latest arrival is two
#: files for one table, and nobody has yet said what each one is.
TWO_FILES = "two-files-for-one-table"
#: THE LATEST ARRIVAL WAS PROMOTED - into its own period - but a supply
#: promoted later into ANOTHER period is what downstream reads most
#: recently (REQ-DASH-197 criterion 6). Not "not promoted", which it was.
PROMOTED_ELSEWHERE = "promoted-into-its-own-period"

#: The sentence the page shows for each, PRESENT AND PAST SIDE BY SIDE
#: (REQ-DASH-197 criterion 19): a past date reads in the past tense, and
#: the page picks one rather than re-tensing a sentence itself. Written
#: here rather than in the template because the same words belong in a
#: ticket and in a terminal, and three copies of a sentence drift.
#: `{period}` is the one placeholder, a period's name, filled by the reader.
WHY_NOT = {
    AWAITING_DECISION: (
        "this supply is staged and nobody has decided about it yet",
        "this supply was staged and nobody had decided about it yet"),
    RETURNED_BY_A_PERSON: (
        "a person looked at this supply and returned it to the queue",
        "a person had looked at this supply and returned it to the queue"),
    REJECTED: (
        "a person rejected this supply, so it was never promoted",
        "a person had rejected this supply, so it was not promoted"),
    NO_SLOT: (
        "no slot could be claimed for this supply, so there is no period for it "
        "to be promoted into",
        "no slot could be claimed for this supply, so there was no period for it "
        "to be promoted into"),
    # F11 of post-build-review #109: since REQ-PIPE-118 this also covers a
    # newer version arriving and a person setting this one aside.
    SUPERSEDED: (
        "this one was superseded - a newer version arrived for the same period, a "
        "person set it aside, or a later supply was promoted into the period - so it "
        "is no longer what the period holds",
        "this one had been superseded - a newer version had arrived for the same "
        "period, a person had set it aside, or a later supply had been promoted into "
        "the period - so it was no longer what the period held"),
    TWO_FILES: (
        "two files arrived for this table and nobody has yet said what each one is",
        "two files had arrived for this table and nobody had yet said what each one "
        "was"),
    PROMOTED_ELSEWHERE: (
        "a supply promoted later into {period} is what downstream reads most recently",
        "a supply promoted later into {period} was what downstream read most "
        "recently"),
}


#: How a period comes to hold data that is not its own (REQ-DASH-085
#: and REQ-DASH-100). Two words, deliberately different ones, because
#: they mean opposite things about whether anybody failed: a
#: SUBSTITUTED period was owed a supply that never came and a person
#: decided what to stand on; an INHERITED one was owed nothing at all.
SUBSTITUTED = "substituted"
INHERITED = "inherited"

#: What level each reads at, and the pairing is the requirement rather
#: than a styling choice. A substitution is a WARNING - a supply that
#: was owed is missing, and somebody made a judgement call about it. An
#: inheritance is INFORMATION - the dataset is behaving exactly as
#: agreed. Rendering both the same would tell a reader that a
#: quarterly dataset skipping a quarter it never owed is as worth their
#: attention as a supplier who failed to deliver.
STANDING_IN_LEVEL = {SUBSTITUTED: "warning", INHERITED: "information"}


@dataclass(frozen=True)
class StandingIn:
    """A period holding an earlier period's supply, and how it got there.

    THE REASON IS CARRIED AS WRITTEN. Both requirements say so in as
    many words - "DISPLAYING that reason as written rather than
    summarising it or replacing it with a generic phrase" - because the
    reason is the only part a person actually authored, and a generic
    phrase in its place is the page claiming somebody explained
    themselves when nobody did.
    """

    kind: str
    period: str
    stands_on: str
    supply: str
    decided_by: str | None = None
    reason: str = ""

    @property
    def level(self) -> str:
        return STANDING_IN_LEVEL[self.kind]

    @property
    def by_a_person(self) -> bool:
        return self.kind == SUBSTITUTED

    def as_record(self) -> dict:
        return {"kind": self.kind, "level": self.level, "period": self.period,
                "standsOn": self.stands_on, "supply": self.supply,
                "decidedBy": self.decided_by, "reason": self.reason,
                "byAPerson": self.by_a_person}


@dataclass(frozen=True)
class State:
    """One dataset's arrived-versus-promoted state."""

    dataset_id: str
    #: The supply the period currently resolves to, and which period.
    promoted_supply: str | None = None
    promoted_period: str | None = None
    #: The most recent supply that ARRIVED, whatever became of it.
    arrived_supply: str | None = None
    arrived_period: str | None = None
    why_not: str | None = None
    #: The newest period this dataset has that holds somebody else's
    #: supply, if any (REQ-DASH-085 and REQ-DASH-100).
    standing_in: StandingIn | None = None
    #: An open contest's two files, by the names they arrived under, so the
    #: arrival cell names them rather than the `#1` id (REQ-DASH-197
    #: criterion 4).
    arrived_files: tuple[str, ...] = ()

    @property
    def differs(self) -> bool:
        """Whether the page should show both (criteria 1 and 3)."""
        return bool(self.arrived_supply
                    and self.arrived_supply != self.promoted_supply)

    @property
    def explanation(self) -> str | None:
        """The present-tense sentence, with its period filled in."""
        pair = WHY_NOT.get(self.why_not or "")
        if not pair:
            return None
        return pair[0].replace("{period}", self.promoted_period or "")

    def as_record(self) -> dict:
        """The shape the dashboard build embeds."""
        return {
            "differs": self.differs,
            "promoted": (None if not self.promoted_supply else
                          {"supply": self.promoted_supply,
                           "period": self.promoted_period}),
            "arrived": (None if not self.arrived_supply else
                         {"supply": self.arrived_supply,
                          "period": self.arrived_period,
                          "files": list(self.arrived_files)}),
            "whyNot": self.why_not,
            "explanation": self.explanation,
            "standingIn": self.standing_in.as_record() if self.standing_in else None,
        }


def _why_not(conn, dataset_id: str, supply: str, period: str | None,
             as_at=None, contested: bool = False) -> str:
    """Which of the reasons applies, most specific first, AS AT `as_at`
    (REQ-DASH-197 criterion 22) - never a reason arising from a decision
    that took effect after it.

    ORDERED BECAUSE SEVERAL CAN BE TRUE. A rejected supply is also one
    nobody promoted; a supply with no slot is also one awaiting a
    decision in the loosest sense. The one reported is the one that
    tells the reader what to do.
    """
    from qa_tools.common import rejection

    decisions = conn.execute(
        f"SELECT action FROM {decision_log.TABLE} "
        "WHERE dataset_id = ? AND supply = ? "
        "AND (?::timestamptz IS NULL OR effective_at <= ?::timestamptz) "
        "ORDER BY effective_at DESC, id DESC",
        [dataset_id, supply, as_at, as_at]).fetchall()
    actions = [row[0] for row in decisions]
    if decision_log.REJECT in actions:
        return REJECTED
    # A NEWER VERSION ARRIVED FOR THE SAME PERIOD (REQ-PIPE-118) - unless a
    # person has since brought it back (REQ-PIPE-120).
    from qa_tools.common import supersession

    if supersession.is_superseded(conn, dataset_id, supply, as_at):
        return SUPERSEDED
    if contested:
        return TWO_FILES
    if not period:
        # Criterion 4's third reason, and it is the one an operator can
        # actually fix: the schedule has no slot for this supply.
        return NO_SLOT
    holder = decision_log.promoted_into(conn, dataset_id, period, as_at)
    if holder == supply:
        return PROMOTED_ELSEWHERE
    if holder is not None:
        return SUPERSEDED
    return (RETURNED_BY_A_PERSON
            if rejection.decided_by_a_person(conn, dataset_id, supply, as_at)
            else AWAITING_DECISION)


def standing_in(conn: supply_db.SupplyConnection, dataset_id: str, as_at=None,
                period: str | None = None) -> StandingIn | None:
    """The newest period of this dataset's that holds somebody else's
    supply, or None.

    NEWEST RATHER THAN ALL OF THEM, because the qualifier answers "is
    what I am looking at this period's own data", and what a reader is
    looking at is the current state. A dataset with a substitution three
    years back and a real supply since is not standing in on anything
    now, and saying it is would be a permanent warning about something
    already resolved.

    FROM THE LOG rather than from the period schemas, for the reason
    substitution.substituted() gives: a view in a schema says an object
    exists, never what put it there or whether the indirection has since
    been removed.
    """
    # AS AT AN INSTANT, AND FOR ONE PERIOD (REQ-DASH-198 criteria 1 and 2):
    # the qualifier is about the period on show on the date on show, never
    # the newest stand-in as at the build.
    rows = conn.execute(
        f"SELECT action, to_slot, stands_on, supply, actor, reason, actor_kind "
        f"FROM {decision_log.TABLE} "
        "WHERE dataset_id = ? AND action IN (?, ?) AND to_slot IS NOT NULL "
        "AND (?::text IS NULL OR to_slot = ?::text) "
        "AND (?::timestamptz IS NULL OR effective_at <= ?::timestamptz) "
        "ORDER BY effective_at DESC, id DESC",
        [dataset_id, decision_log.SUBSTITUTE, decision_log.INHERIT, period, period,
         as_at, as_at]).fetchall()
    for action, slot, stands_on, supply, actor, reason, actor_kind in rows:
        h = decision_log.held(conn, dataset_id, slot, as_at)
        wanted = (decision_log.SUBSTITUTED if action == decision_log.SUBSTITUTE
                  else decision_log.INHERITED)
        if not h or h.held_as != wanted or h.decision_id is None:
            # Something has happened to that period since - a real
            # supply promoted into it, or the indirection removed. Not
            # standing in any more.
            continue
        kind = SUBSTITUTED if action == decision_log.SUBSTITUTE else INHERITED
        return StandingIn(
            kind=kind, period=slot, stands_on=stands_on, supply=supply,
            # WHO DECIDED IT, and None where nobody did. An inheritance
            # is the rule acting on a schedule, and naming the rule as
            # though it were a person would put a decision on somebody
            # who never made one (REQ-DASH-100 criterion 12).
            decided_by=actor if actor_kind == decision_log.PERSON else None,
            reason=reason or "")
    return None


def contested_files(dataset_id: str, supply: str | None, as_at=None,
                    contests=None) -> tuple[str, ...]:
    """The two files of an OPEN contest this supply is, as at `as_at`, or ().

    THE ONE JUDGEMENT IS dataset_blockers' (REQ-PIPE-194 criterion 8): a
    contest is open from its receipt until a decision that settles it,
    never inferred from the `#` in a supply id. `contests` is that list,
    passed in by a caller asking about many instants.
    """
    from qa_tools.common import dataset_blockers

    if not supply:
        return ()
    for c in (contests if contests is not None else dataset_blockers.contests()):
        if c.dataset_id != dataset_id or c.supply != supply:
            continue
        opened = asset_time.parse_instant(c.opened_at, "contest")
        resolved = (asset_time.parse_instant(c.resolved_at, "contest")
                    if c.resolved_at else None)
        at = as_at if as_at is not None else None
        if at is not None and opened > at:
            return ()
        if resolved is not None and (at is None or resolved <= at):
            return ()
        return tuple(c.files)
    return ()


def state_for(dataset_id: str, conn: supply_db.SupplyConnection | None = None,
              as_at=None) -> State:
    """This dataset's arrived-versus-promoted state, from records alone, AS
    AT `as_at` (REQ-DASH-197) - or as at now where it is None.

    THE LATEST ARRIVAL IS THE SUPPLY FIRST FILED LATEST (criteria 2 and 3),
    because a filing is written for every arrival before any check runs
    over it (REQ-PIPE-075 criterion 7) - including one that will turn out
    red, which is exactly the case this requirement is about. FIRST filed,
    never the newest filing ROW: a later re-file of an older supply writes
    a newer row, and used to make that older supply "the latest arrival"
    (post-build-review #163).

    THE PROMOTED SUPPLY IS THE MOST RECENT PROMOTION, across periods
    rather than within one. "What everyone downstream is using" is not a
    question about a particular period; it is about the newest thing the
    warehouse holds for this dataset.
    """
    if conn is None:
        with supply_db.connect(read_only=True,
                                label="mothman:promotion-state") as opened:
            return state_for(dataset_id, opened, as_at)

    from qa_tools.common import filing

    # THE NEWEST SUPPLY A SLOT STILL HOLDS, from qa.slot_holds through
    # decision_log.promoted_supply (REQ-PIPE-130 criterion 9). This took
    # the newest promotion and, if that slot had since been emptied,
    # reported nothing - never falling back to an older supply still
    # held, so two answers to one question disagreed (delivery-critic,
    # overnight sprint 2).
    newest = decision_log.promoted_supply(conn, dataset_id, as_at)
    promoted_period = newest["to_slot"] if newest else None
    promoted_supply = newest["supply"] if newest else None

    standing = standing_in(conn, dataset_id, as_at)

    filings = filing.filings_as_at(filing.filing_history(conn, dataset_id), as_at,
                                   filing.settled_away(conn, dataset_id))
    if not filings:
        return State(dataset_id=dataset_id, promoted_supply=promoted_supply,
                      promoted_period=promoted_period, standing_in=standing)

    latest = filings[-1]
    arrived_supply = latest.get("supply_id")
    arrived_period = latest.get("slot")
    files = contested_files(dataset_id, arrived_supply, as_at)
    state = State(
        dataset_id=dataset_id, promoted_supply=promoted_supply,
        promoted_period=promoted_period, arrived_supply=arrived_supply,
        arrived_period=arrived_period, standing_in=standing, arrived_files=files)
    if not state.differs:
        return state
    return State(
        dataset_id=dataset_id, promoted_supply=promoted_supply,
        promoted_period=promoted_period, arrived_supply=arrived_supply,
        arrived_period=arrived_period, standing_in=standing, arrived_files=files,
        why_not=_why_not(conn, dataset_id, arrived_supply, arrived_period, as_at,
                         contested=bool(files)))
