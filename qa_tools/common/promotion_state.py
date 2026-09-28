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
    SUPERSEDED: ("a later supply was promoted into this period, so this one is "
                  "no longer what the period holds"),
}


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
    if not period:
        # Criterion 4's third reason, and it is the one an operator can
        # actually fix: the schedule has no slot for this supply.
        return NO_SLOT
    if decision_log.promoted_into(conn, dataset_id, period) not in (None, supply):
        return SUPERSEDED
    return (RETURNED_BY_A_PERSON if rejection.decided_by_a_person(conn, dataset_id, supply)
            else AWAITING_DECISION)


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

    rows = conn.execute(
        f"SELECT to_slot, supply FROM {decision_log.TABLE} "
        "WHERE dataset_id = ? AND action IN (?, ?) AND to_slot IS NOT NULL "
        "ORDER BY effective_at DESC, id DESC LIMIT 1",
        [dataset_id, decision_log.PROMOTE, decision_log.REFILE]).fetchall()
    promoted_period, promoted_supply = rows[0] if rows else (None, None)
    if promoted_period is not None and decision_log.promoted_into(
            conn, dataset_id, promoted_period) != promoted_supply:
        # Promoted and since taken back out - a demote, a reject or a
        # re-file OUT. The period holds nothing, so neither does this.
        promoted_period, promoted_supply = None, None

    filings = filing.filings_of(dataset_id)
    if not filings:
        return State(dataset_id=dataset_id, promoted_supply=promoted_supply,
                      promoted_period=promoted_period)

    latest = filings[-1]
    arrived_supply = latest.get("supply_id")
    arrived_period = latest.get("slot")
    state = State(
        dataset_id=dataset_id, promoted_supply=promoted_supply,
        promoted_period=promoted_period, arrived_supply=arrived_supply,
        arrived_period=arrived_period)
    if not state.differs:
        return state
    return State(
        dataset_id=dataset_id, promoted_supply=promoted_supply,
        promoted_period=promoted_period, arrived_supply=arrived_supply,
        arrived_period=arrived_period,
        why_not=_why_not(conn, dataset_id, arrived_supply, arrived_period))
