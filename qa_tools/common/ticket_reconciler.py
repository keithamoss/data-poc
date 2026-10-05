"""One ticket per slot, reconciled to its current state (REQ-PIPE-083).

A TEAM SHARES ONE QUEUE, and the queue only works if everything in it
wants somebody and nothing in it says the same thing twice. That is the
whole design, and both halves are easy to get wrong in opposite
directions: a stream of events fills the queue with things already
dealt with, and a queue nobody updates fills it with things already
done.

RECONCILE, NEVER REACT (criterion 4). Every pass computes where each
slot IS and makes the ticket say that. Running it twice over an
unchanged world changes nothing, which is what makes it safe to call
after every QA run, from a schedule, and from an operator's own
command - three triggers, one pass, the same result (criteria 13 and
22).

IT SPEAKS ONLY TO ITS OWN COMMENTS (criterion 11). What it last said is
read from comments carrying its own marker, never from a person's -
because a person's comment is a THING SOMEBODY SAID, not a state to
reconcile, and treating it as one would have the reconciler answer
people. A person's comment may still be read as a filing decision, by
the decision intake, which is a different reader and REQ-GHUB-082's
concern.

IT NEVER CLOSES ANYTHING (criterion 10). When a slot stops needing
attention the outcome goes on the ticket and the ticket stays open,
because closing is a person saying "I am done with this" and a rule
saying it for them is how somebody's work disappears. It will REOPEN
one a person closed if the slot moves again (criterion 12), which is
the same principle from the other side: the person closed the thing
they saw, and this is a different thing.

IT NEVER TOUCHES A TICKET FROM BEFORE THIS SCHEME (criterion 19).
Adoption, re-keying and clearing away are one-off acts by a person.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Protocol

from qa_tools.common import slot_state

#: The marker that makes a comment THIS reconciler's own (criterion 11).
#: An HTML comment, so it is invisible on the rendered ticket and exact
#: to match - a prefix a person could type by accident is not a marker.
MARKER = "<!-- mothman:slot-state "
MARKER_END = " -->"

#: The two policies criterion 21 requires, and the default it names.
ALL = "all"
NEEDS_ACTION = "needs-action"
POLICIES = (ALL, NEEDS_ACTION)
DEFAULT_POLICY = NEEDS_ACTION


class TicketService(Protocol):
    """What this needs of a ticketing service, and nothing more.

    A PROTOCOL RATHER THAN THE REAL CLIENT, so the reconciler can be
    driven in a test without a network and so a second backend is a new
    class rather than a branch in here. It is also what criterion 17
    rests on: every one of these may raise, and the caller's operation
    still stands on its durable record.
    """

    def find(self, key: str) -> "Ticket | None": ...
    def open(self, key: str, title: str, body: str) -> "Ticket": ...
    def comment(self, ticket: "Ticket", body: str) -> None: ...
    def set_body(self, ticket: "Ticket", body: str) -> None: ...
    def reopen(self, ticket: "Ticket") -> None: ...
    def comments(self, ticket: "Ticket") -> list[str]: ...


@dataclass
class Ticket:
    """One ticket, as this module needs to see it."""

    key: str
    number: int
    closed: bool = False


@dataclass(frozen=True)
class Outcome:
    """What one pass did, in four lists that mean four things."""

    opened: tuple[str, ...] = ()
    updated: tuple[str, ...] = ()
    reopened: tuple[str, ...] = ()
    unchanged: tuple[str, ...] = ()
    failed: dict = field(default_factory=dict)

    @property
    def quiet(self) -> bool:
        """A pass that changed nothing, which is the ordinary case."""
        return not (self.opened or self.updated or self.reopened)


def fingerprint(state: slot_state.SlotState) -> str:
    """What "the state has changed" means, exactly (criterion 5).

    A HASH OF WHAT THE COMMENT WOULD SAY, not of the whole SlotState.
    Two states that would produce identical prose are the same state as
    far as a reader is concerned, and posting for a difference nobody
    can see is the repetition criterion 5 forbids. Deriving it from the
    rendered body rather than the object also means a change to the
    WORDING is a change - which is right: the ticket would then be
    showing something it has never shown.
    """
    return hashlib.sha256(body_for(state).encode("utf-8")).hexdigest()[:16]


def body_for(state: slot_state.SlotState) -> str:
    """What the ticket says about this slot, and what a person can do.

    NAMED, NEVER OFFERED (criterion 9). The responses are a list of what
    a person can do, not buttons - a route that does nothing is worse
    than no route, and REQ-GHUB-082 is where the routes come from.
    """
    from qa_tools.common import display_time

    lines = [f"**{state.dataset_id}** — {display_time.format_period(state.period)}",
             "", f"State: **{state.state}**"
             + (" (closed)" if state.closed else "")]
    if state.closed and state.state != slot_state.NOT_SUPPLIED_ACCEPTED:
        # REQ-PIPE-132 criteria 1 and 12: closed, and what that means.
        lines.append(f"This period has closed: {slot_state.CLOSED_NOTE}.")
    if state.supply:
        lines.append(f"Supply: `{state.supply}`")
    if state.stands_on:
        lines.append(f"Stands on: {display_time.format_period(state.stands_on)}")
    if state.decided_by:
        lines.append(f"Decided by: {state.decided_by}")
    if state.reason:
        lines.append(f"Reason given: {state.reason}")
    if state.responses:
        lines += ["", "What somebody can do:"]
        lines += [f"- {r}" for r in state.responses]
    else:
        # CRITERION 10: the outcome is recorded and the ticket stays
        # open. A rule closing somebody's ticket is how their work
        # disappears.
        lines += ["", "Nothing is waiting on a person. Left open for whoever "
                       "owns this to close."]
    return "\n".join(lines)


def _own_comment(state: slot_state.SlotState) -> str:
    return f"{MARKER}{fingerprint(state)}{MARKER_END}\n\n{body_for(state)}"


def _last_said(comments: list[str]) -> str | None:
    """The fingerprint of the last thing THIS reconciler said.

    FROM ITS OWN COMMENTS ALONE (criterion 11). A person's comment is
    skipped rather than parsed, so somebody writing the marker text into
    a comment by hand is the only way to confuse it - and an HTML
    comment is not something a person types by accident.
    """
    for text in reversed(comments or []):
        if text.startswith(MARKER):
            return text[len(MARKER):].split(MARKER_END, 1)[0].strip()
    return None


def wanted(state: slot_state.SlotState, policy: str) -> bool:
    """Whether this slot gets a ticket at all (criterion 21)."""
    return True if policy == ALL else state.needs_action


def policy_from_config(config: dict | None = None) -> str:
    """The asset's ticket policy, defaulting rather than guessing.

    AN UNKNOWN VALUE FALLS BACK TO THE DEFAULT AND SAYS SO, rather than
    raising: a typo in the asset config should not stop a pipeline run
    from reconciling anything at all, which is the same blast-radius
    rule this batch applies everywhere.
    """
    if config is None:
        import yaml

        from qa_tools.common import hierarchy

        with open(hierarchy.DATA_ASSET_YAML) as handle:
            config = yaml.safe_load(handle) or {}
    value = (config or {}).get("ticket_policy") or DEFAULT_POLICY
    if value not in POLICIES:
        print(f"note: ticket_policy {value!r} is not one of "
              f"{', '.join(POLICIES)} - using {DEFAULT_POLICY!r}.")
        return DEFAULT_POLICY
    return value


def reconcile(service: TicketService, states, *, policy: str | None = None,
              title_for=None) -> Outcome:
    """Bring every slot's ticket up to date with its current state.

    `states` is the set of slots to reconcile, which the caller narrows
    or does not (criterion 18) - a narrowed invocation is THE SAME PASS
    over fewer slots rather than a second code path, which is why there
    is no `only=` argument doing something different.

    ONE SLOT'S FAILURE IS SCOPED TO IT (criterion 20). At ~30 datasets a
    pass that abandons twenty-nine tickets because the thirtieth raised
    is a pass somebody turns off.
    """
    policy = policy or policy_from_config()
    opened, updated, reopened, unchanged = [], [], [], []
    failed: dict = {}

    for state in states:
        if not wanted(state, policy):
            continue
        try:
            ticket = service.find(state.key)
            if ticket is None:
                service.open(state.key, (title_for or _title)(state),
                              _own_comment(state))
                opened.append(state.key)
                continue
            if _last_said(service.comments(ticket)) == fingerprint(state):
                # CRITERION 5, and criterion 4's "running it twice
                # changes nothing" in its observable form.
                unchanged.append(state.key)
                continue
            if ticket.closed:
                # CRITERION 12: the same ticket, reopened. A second
                # ticket for one slot is the thing criterion 2 forbids,
                # and a person closing one is not a reason to break it.
                service.reopen(ticket)
                reopened.append(state.key)
            # THE BODY FIRST, THEN THE COMMENT (REQ-GHUB-109 criterion
            # 3). The body is WHERE IT IS NOW, rewritten in place, so a
            # thread quiet for a month still says where the supply has
            # got to without anybody scrolling; the comment is WHAT
            # CHANGED, which is what a notification is for. One slot's
            # state in one place, and the history beside it.
            service.set_body(ticket, body_for(state))
            service.comment(ticket, _own_comment(state))
            updated.append(state.key)
        except Exception as exc:  # noqa: BLE001 - see the docstring
            failed[state.key] = f"{type(exc).__name__}: {exc}"

    return Outcome(opened=tuple(opened), updated=tuple(updated),
                    reopened=tuple(reopened), unchanged=tuple(unchanged),
                    failed=failed)


def _title(state: slot_state.SlotState) -> str:
    from qa_tools.common import display_time

    return (f"{state.dataset_id}: supply for "
            f"{display_time.format_period(state.period)}")


def report(outcome: Outcome) -> None:
    """Say what the pass did, in the terminal, without flooding it.

    IDENTICAL FAILURES COLLAPSE TO ONE LINE, and that is not cosmetic.
    The commonest failure by far is the whole service being unreachable,
    which fails every slot with the same sentence - thirty-five copies
    of it would bury the one line that matters and train somebody to
    scroll past the end of a pipeline run. A failure that is genuinely
    per-slot still gets its own line, because then the slot is the
    information.
    """
    if outcome.opened:
        print(f"tickets: opened {len(outcome.opened)} "
              f"({', '.join(sorted(outcome.opened)[:3])}"
              f"{', ...' if len(outcome.opened) > 3 else ''})")
    if outcome.reopened:
        print(f"tickets: reopened {len(outcome.reopened)} "
              f"({', '.join(sorted(outcome.reopened))})")
    if outcome.updated:
        print(f"tickets: updated {len(outcome.updated)}")
    if not outcome.failed:
        return

    by_message: dict[str, list[str]] = {}
    for key, message in outcome.failed.items():
        by_message.setdefault(message, []).append(key)
    for message, keys in sorted(by_message.items()):
        if len(keys) == 1:
            print(f"tickets: {keys[0]} could not be reconciled - {message}")
        else:
            print(f"tickets: {len(keys)} slot(s) could not be reconciled - "
                  f"{message}")


def service_from_env():
    """The real ticketing service this deployment talks to, or None.

    None RATHER THAN A RAISE where the environment does not turn ticketing on,
    because a pipeline run on somebody's laptop is not a broken run - it
    is a run with no ticketing configured, which is the ordinary state
    of this repository for most of its life. Criterion 13 asks for the
    reconciler to be INVOKED after every QA run; it does not ask for
    every deployment to have a ticket service.
    """
    from qa_tools.common import environments
    from qa_tools.common.ticket_github import GitHubTickets

    # THE ENVIRONMENT SWITCHES IT ON, NOTHING ELSE (REQ-PIPE-093 criteria 10
    # and 12). This used to read GITHUB_REPOSITORY, which GitHub Actions
    # sets on every run, so any workflow that ran the pipeline turned
    # ticketing on whether or not anybody meant it to. The repository is
    # the data asset's, from contract/data-asset.yaml.
    env = environments.current_or_none()
    if env is None or not env.ticketing:
        return None
    slug = environments.ticket_repository() or ""
    if "/" not in slug:
        # Unreachable through supply_db.connect, which refuses this before
        # connecting (criterion 13) - said again here for a caller that
        # asks for the service without a connection.
        raise environments.EnvironmentError_(
            f"the {env.id!r} environment turns ticketing on, but contract/data-asset.yaml "
            f"names no ticket_repository")
    owner, repo = slug.split("/", 1)
    return GitHubTickets(owner, repo)


def after_runs(collection_id: str, *, conn=None) -> Outcome:
    """Reconcile every slot this collection is responsible for.

    THE ONE ENTRY POINT the orchestrators, a schedule and an operator
    command all use, which is criteria 13, 18 and 22 in one function: a
    narrowed pass is this same pass over fewer slots, and the answer
    does not depend on who called.

    AFTER THE CHANGE IS DURABLY RECORDED (criterion 16), which is the
    caller's responsibility and is why this is called after promotion
    rather than beside it. A ticket that says something the decision log
    does not is worse than a ticket that is a minute behind.
    """
    from qa_tools.common import slot_state, supply_db

    service = service_from_env()
    if service is None:
        return Outcome()
    if conn is None:
        with supply_db.connect(read_only=True,
                                label="mothman:reconcile-tickets") as opened:
            return after_runs(collection_id, conn=opened)
    return reconcile(service, slot_state.states_for(conn, collection_id))
