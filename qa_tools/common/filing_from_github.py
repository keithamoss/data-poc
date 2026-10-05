"""Raising a filing decision from a comment on a slot's ticket
(REQ-GHUB-082 criteria 1, 4, 5, 7, 23 and 30).

AN ADAPTER, NOT A SECOND IMPLEMENTATION. Everything a decision MEANS -
who may raise it, whether it needs a reason, whether the filing rules
permit it - lives in `filing_decisions`, once, because criterion 3 says
the two routes must never differ and criterion 24 says they must never
disagree about what is permitted. What is here is the two things that
are genuinely this route's: reading an operation out of prose somebody
typed, and saying no on the thread they typed it in.

THE PERIOD COMES FROM THE TICKET, NOT THE COMMENT (criterion 1). A slot
ticket is one dataset in one period and carries that in a label, so the
decision's subject is a property of WHERE it was raised. A comment that
could name its own period would be a comment that could act on a period
its author is not looking at.

THE ACTOR COMES FROM THE AUTHENTICATED AUTHOR, NEVER THE BODY
(criterion 4). Anybody who can comment on a public repository can type
somebody else's name; only GitHub can say whose account posted. There is
nowhere in `Comment` to put a claimed actor, which is the rule made
structural rather than checked.

A COMMENT WITH NO KNOWN COMMAND IS IGNORED OUTRIGHT, and the prose
AROUND one is ignored too (criterion 5). People talk on tickets. A
route that read every sentence as an instruction would make a thread
unusable for the thing threads are for, and one that refused everything
it did not understand would fill the thread with refusals of ordinary
conversation.

REFUSALS ARE POSTED DIRECTLY, not through REQ-PIPE-083's pass
(criterion 23). A refusal appends nothing to the decision log, so that
pass would correctly find nothing changed and say nothing - and the
person who raised it would be told, in silence, that their decision had
been accepted.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from qa_tools.common import decision_log, filing_decisions, people

#: What a command looks like: `/promote`, on its own line, optionally
#: followed by arguments and then by anything at all.
#:
#: A LEADING SLASH, which is GitHub's own convention for a command in a
#: comment (`/close`, `/assign`) and is what makes criterion 5's
#: "ignore the prose AROUND a known command" decidable rather than a
#: guess: a line beginning with a slash is addressed to the machine, and
#: every other line is addressed to people.
_COMMAND = re.compile(r"^\s*/(?P<name>[a-z-]+)(?P<rest>.*)$", re.MULTILINE)

#: The arguments a command may carry, as `key: value` or `key=value`.
#: Only these three, and each is a NAME the system already knows rather
#: than free text: the supply being acted on, the period a substitution
#: stands on, and the confirmation criteria 9 and 28 require.
#: `to` (or `to-period`) is where a re-file goes (REQ-PIPE-141).
_ARGUMENT = re.compile(r"\b(?P<key>supply|stands-on|to-period|to|confirm|acknowledge)\s*[:=]\s*"
                       r"(?P<value>\S+)", re.IGNORECASE)

#: Everything after the command line, which is the reason. A person
#: raising a decision writes why in their own words, and criterion 10
#: refuses the decision without it - so the reason is the comment rather
#: than an argument somebody has to remember to label.
_AFFIRMATIVE = {"yes", "true", "1", "y", "confirm", "confirmed"}


class NoDecisionHere(Exception):
    """This comment is not raising a filing decision.

    NOT AN ERROR, and this type exists so a caller cannot accidentally
    treat it as one. A thread where people are talking is the ordinary
    case; criterion 5 says a comment carrying no known command is
    ignored OUTRIGHT, which means no refusal, no reply and no log entry.
    """


@dataclass(frozen=True)
class Comment:
    """One comment, as this route needs to see it.

    NO ACTOR FIELD BEYOND THE AUTHOR, deliberately (criterion 4). The
    author is who GitHub says posted; there is nowhere to put a name
    somebody typed.
    """

    body: str
    author: str
    #: The slot the ticket is for - `cp-carers/2026-Q3`, the key
    #: slot_state.SlotState.key mints and ticket_github puts in a label.
    slot_key: str


def _split_slot(slot_key: str) -> tuple[str, str]:
    dataset_id, _, period = (slot_key or "").partition("/")
    if not dataset_id or not period:
        raise NoDecisionHere(
            f"{slot_key!r} is not a slot key, so there is no period for a "
            f"decision to act on.")
    return dataset_id, period


def read(comment: Comment) -> filing_decisions.Request:
    """The decision this comment raises, or NoDecisionHere.

    ONE COMMAND PER COMMENT. Two would be two decisions raised together
    with one reason between them, and the second would inherit the
    first's justification - which is exactly the thing criterion 10
    exists to prevent. A comment carrying two is refused rather than
    half-obeyed.
    """
    found = [m for m in _COMMAND.finditer(comment.body or "")
             if m.group("name") in filing_decisions.OPERATIONS]
    if not found:
        raise NoDecisionHere(
            "no line in this comment begins with a known filing command.")
    if len(found) > 1:
        raise decision_log.DecisionRefused(
            f"this comment raises {len(found)} decisions "
            f"({', '.join(sorted(m.group('name') for m in found))}) with one "
            f"reason between them. Raise them in separate comments, so each "
            f"one says why it was made.")

    match = found[0]
    dataset_id, period = _split_slot(comment.slot_key)
    arguments = {m.group("key").lower(): m.group("value")
                 for m in _ARGUMENT.finditer(match.group("rest"))}

    # THE ACTOR IS RESOLVED BEFORE ANYTHING ELSE, so a stranger's
    # comment is refused for being a stranger's rather than for a
    # missing argument they were never entitled to supply.
    actor = people.person_by_github(comment.author)

    return filing_decisions.Request(
        operation=match.group("name"),
        dataset_id=dataset_id,
        actor=actor,
        reason=_reason_from(comment.body, match),
        period=period,
        supply=arguments.get("supply"),
        stands_on=arguments.get("stands-on"),
        to_period=arguments.get("to-period") or arguments.get("to"),
        confirmed=(arguments.get("confirm", "").lower() in _AFFIRMATIVE),
        # A DECISION WITH CONSEQUENCES TAKES A SECOND COMMENT (REQ-PIPE-128
        # criterion 9): the first is refused with the warning and its key,
        # and raising it again with `acknowledge: <key>` confirms exactly
        # what was shown.
        acknowledged=arguments.get("acknowledge"),
    )


def _reason_from(body: str, match: re.Match) -> str:
    """Everything that is not the command line.

    THE REASON IS THE COMMENT, not an argument somebody has to remember
    to label. A person raising a decision on a ticket writes why in
    their own words, above or below the command, and asking them to
    repeat it inside a `reason:` argument is how the reason becomes
    "see above".

    THE ARGUMENTS COME OFF THE COMMAND LINE ONLY, which is why this
    drops that one line rather than stripping `supply:` out of the
    prose: somebody writing "the supply: it was truncated" in a
    sentence is writing a sentence.
    """
    lines = (body or "").splitlines()
    start = body[:match.start()].count("\n")
    return "\n".join(lines[:start] + lines[start + 1:]).strip()


def handle(comment: Comment, *, collection_id: str, effective_at: str,
           service=None, ticket=None) -> filing_decisions.Outcome | None:
    """Read a comment, raise its decision, and say so on the thread.

    RETURNS None WHERE THERE IS NOTHING TO DO, which is criterion 5's
    "ignore outright": no refusal, no reply, no entry. People talk on
    tickets, and a route that answered every sentence would make the
    thread unusable for the thing threads are for.

    A REFUSAL IS POSTED DIRECTLY (criterion 23). It appends nothing to
    the decision log, so REQ-PIPE-083's pass would correctly find
    nothing changed and say nothing - and the person who raised it would
    be told, in silence, that it had been accepted. The reconciliation
    of a decision that DID happen still goes through that pass, so the
    ticket says it once and in the same words as one raised anywhere
    else (criterion 8).

    IT NEVER RAISES PAST THE CALLER for a refusal. Whatever invokes this
    is processing comments, possibly several, and one stranger's
    attempt must not stop the next person's real decision.
    """
    try:
        request = read(comment)
    except NoDecisionHere:
        return None
    except (decision_log.DecisionRefused, people.UnknownActor,
            filing_decisions.NotOffered) as exc:
        _say_no(service, ticket, exc)
        return None

    try:
        outcome = filing_decisions.apply(request, effective_at=effective_at)
    except (decision_log.DecisionRefused, people.UnknownActor,
            filing_decisions.NotOffered) as exc:
        _say_no(service, ticket, exc)
        return None
    except Exception as exc:  # noqa: BLE001 - criterion 22: never silently
        _say_no(service, ticket, exc)
        return None

    filing_decisions.reconcile_after(outcome, collection_id)
    return outcome


def _say_no(service, ticket, exc: Exception) -> None:
    """Tell the person who raised it, where they raised it (criteria 22
    and 23).

    NEVER FAILS THE HANDLING. If the thread cannot be written to, the
    refusal is printed instead - which is worse for the person who
    raised it and better than a crash that leaves the next comment
    unprocessed.
    """
    body = (f"**That decision was not recorded.**\n\n{exc}\n\n"
            f"Nothing was changed. Raise it again once that is sorted out.")
    if service is None or ticket is None:
        print(f"note: a filing decision was refused and there is no ticket to "
              f"say so on: {exc}")
        return
    try:
        service.comment(ticket, body)
    except Exception as posting:  # noqa: BLE001 - see the docstring
        print(f"note: a filing decision was refused ({exc}) and the refusal "
              f"could not be posted ({type(posting).__name__}: {posting}).")
