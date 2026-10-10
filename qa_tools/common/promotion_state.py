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

from qa_tools.common import decision_log, supply_db

#: Why an arrival is not the promoted supply (criterion 4). Three
#: reasons, and they are different actions for whoever reads them: wait,
#: nothing to do, or go and fix the schedule.
AWAITING_DECISION = "awaiting-decision"
RETURNED_BY_A_PERSON = "returned-by-a-person"
REJECTED = "rejected"
NO_SLOT = "no-slot"
SUPERSEDED = "superseded"

#: The sentence the page shows for each. Written here rather than in the
#: template because the same words belong in a ticket and in a terminal,
#: and three copies of a sentence drift.
WHY_NOT = {
    AWAITING_DECISION: ("this supply is staged and nobody has decided about it "
                         "yet"),
    RETURNED_BY_A_PERSON: ("a person looked at this supply and returned it to "
                            "the queue"),
    REJECTED: "a person rejected this supply, so it was never promoted",
    NO_SLOT: ("no slot could be claimed for this supply, so there is no period "
               "for it to be promoted into"),
    # F11 of post-build-review #109: since REQ-PIPE-118 this also covers a
    # newer version arriving and a person setting this one aside.
    SUPERSEDED: ("this one was superseded - a newer version arrived for the same "
                  "period, a person set it aside, or a later supply was promoted "
                  "into the period - so it is no longer what the period holds"),
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

    @property
    def differs(self) -> bool:
        """Whether the page should show both (criteria 1 and 3)."""
        return bool(self.arrived_supply
                    and self.arrived_supply != self.promoted_supply)

    @property
    def explanation(self) -> str | None:
        return WHY_NOT.get(self.why_not or "")

    def as_record(self) -> dict:
        """The shape the dashboard build embeds."""
        return {
            "differs": self.differs,
            "promoted": (None if not self.promoted_supply else
                          {"supply": self.promoted_supply,
                           "period": self.promoted_period}),
            "arrived": (None if not self.arrived_supply else
                         {"supply": self.arrived_supply,
                          "period": self.arrived_period}),
            "whyNot": self.why_not,
            "explanation": self.explanation,
            "standingIn": self.standing_in.as_record() if self.standing_in else None,
        }


def _why_not(conn, dataset_id: str, supply: str, period: str | None) -> str:
    """Which of the reasons applies, most specific first.

    ORDERED BECAUSE SEVERAL CAN BE TRUE. A rejected supply is also one
    nobody promoted; a supply with no slot is also one awaiting a
    decision in the loosest sense. The one reported is the one that
    tells the reader what to do.
    """
    from qa_tools.common import rejection

    decisions = conn.execute(
        f"SELECT action FROM {decision_log.TABLE} "
        "WHERE dataset_id = ? AND supply = ? ORDER BY effective_at DESC, id DESC",
        [dataset_id, supply]).fetchall()
    actions = [row[0] for row in decisions]
    if decision_log.REJECT in actions:
        return REJECTED
    # A NEWER VERSION ARRIVED FOR THE SAME PERIOD (REQ-PIPE-118) - unless a
    # person has since brought it back (REQ-PIPE-120).
    from qa_tools.common import supersession

    if supersession.is_superseded(conn, dataset_id, supply):
        return SUPERSEDED
    if not period:
        # Criterion 4's third reason, and it is the one an operator can
        # actually fix: the schedule has no slot for this supply.
        return NO_SLOT
    if decision_log.promoted_into(conn, dataset_id, period) not in (None, supply):
        return SUPERSEDED
    return (RETURNED_BY_A_PERSON if rejection.decided_by_a_person(conn, dataset_id, supply)
            else AWAITING_DECISION)


def standing_in(conn: supply_db.SupplyConnection, dataset_id: str) -> StandingIn | None:
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
    rows = conn.execute(
        f"SELECT action, to_slot, stands_on, supply, actor, reason, actor_kind "
        f"FROM {decision_log.TABLE} "
        "WHERE dataset_id = ? AND action IN (?, ?) AND to_slot IS NOT NULL "
        "ORDER BY effective_at DESC, id DESC",
        [dataset_id, decision_log.SUBSTITUTE, decision_log.INHERIT]).fetchall()
    for action, slot, stands_on, supply, actor, reason, actor_kind in rows:
        h = decision_log.held(conn, dataset_id, slot)
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


def state_for(dataset_id: str, conn: supply_db.SupplyConnection | None = None) -> State:
    """This dataset's arrived-versus-promoted state, from records alone.

    THE LATEST ARRIVAL IS THE LATEST FILING, because a filing is written
    for every arrival before any check runs over it (REQ-PIPE-075
    criterion 7) - including one that will turn out red, which is
    exactly the case this requirement is about.

    THE PROMOTED SUPPLY IS THE MOST RECENT PROMOTION, across periods
    rather than within one. "What everyone downstream is using" is not a
    question about a particular period; it is about the newest thing the
    warehouse holds for this dataset.
    """
    if conn is None:
        with supply_db.connect(read_only=True,
                                label="mothman:promotion-state") as opened:
            return state_for(dataset_id, opened)

    from qa_tools.common import filing

    # THE NEWEST SUPPLY A SLOT STILL HOLDS, from qa.slot_holds through
    # decision_log.promoted_supply (REQ-PIPE-130 criterion 9). This took
    # the newest promotion and, if that slot had since been emptied,
    # reported nothing - never falling back to an older supply still
    # held, so two answers to one question disagreed (delivery-critic,
    # overnight sprint 2).
    newest = decision_log.promoted_supply(conn, dataset_id)
    promoted_period = newest["to_slot"] if newest else None
    promoted_supply = newest["supply"] if newest else None

    standing = standing_in(conn, dataset_id)

    filings = filing.filings_of(dataset_id)
    if not filings:
        return State(dataset_id=dataset_id, promoted_supply=promoted_supply,
                      promoted_period=promoted_period, standing_in=standing)

    latest = filings[-1]
    arrived_supply = latest.get("supply_id")
    arrived_period = latest.get("slot")
    state = State(
        dataset_id=dataset_id, promoted_supply=promoted_supply,
        promoted_period=promoted_period, arrived_supply=arrived_supply,
        arrived_period=arrived_period, standing_in=standing)
    if not state.differs:
        return state
    return State(
        dataset_id=dataset_id, promoted_supply=promoted_supply,
        promoted_period=promoted_period, arrived_supply=arrived_supply,
        arrived_period=arrived_period, standing_in=standing,
        why_not=_why_not(conn, dataset_id, arrived_supply, arrived_period))
