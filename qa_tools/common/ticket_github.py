"""The reconciler's ticket service, over real GitHub Issues
(REQ-PIPE-083 criteria 2, 3 and 19).

A SECOND SCHEME BESIDE `ticket_sync.py`, NOT A REPLACEMENT, and the two
have to coexist without touching each other. That module is
REQ-GHUB-027's: one ticket per DATASET, keyed off that dataset's current
aggregate status. This one is REQ-PIPE-083's: one ticket per SLOT - one
dataset, one period - reconciled to where that supply has got to.

SO EVERY READ IS FENCED BY THIS SCHEME'S OWN LABEL, which is criterion
19 in its enforceable form. "SHALL NOT adopt, re-key, migrate, close or
delete any ticket opened before this scheme" is not a rule to remember
while writing a query: a query that can only ever SEE this scheme's
tickets cannot do any of those things to another one, however the code
around it changes. Clearing older tickets away is a one-off act by a
person.

THE SLOT KEY LIVES IN A LABEL TOO, not in the title. A title is
something a person edits, and a ticket that stops being findable because
somebody tidied its wording is a second ticket for the same slot on the
next pass - which is the one thing criterion 2 forbids.

`gh` RATHER THAN AN API CLIENT, matching ticket_sync.py: the GitHub
Actions runner has it, it carries the workflow's own token without this
module handling one, and there is then one way this project talks to
GitHub rather than two. THIS CONTAINER DOES NOT HAVE IT, which is not a
gap in the tests - it is what makes criterion 17 genuinely observable
here rather than only asserted: every method below raises, the
reconciler records a failure per slot, and the operation that prompted
it stands on its durable record.
"""
from __future__ import annotations

import json
import subprocess

from qa_tools.common.ticket_reconciler import Ticket

#: The label every ticket in THIS scheme carries. The fence in criterion
#: 19's form: a query filtered on it can only ever see this scheme's own.
SCHEME_LABEL = "slot-ticket"

#: The prefix of the per-slot label. `slot:cp-carers/2026-Q3` - the
#: stable key from slot_state.SlotState.key, which is the dataset and
#: the period and nothing that changes between runs.
SLOT_LABEL_PREFIX = "slot:"

#: Colours are required by `gh label create`; these are the repo's own
#: existing convention rather than a new one.
_SCHEME_COLOUR = "0e8a16"
_SLOT_COLOUR = "c5def5"


class TicketServiceUnavailable(RuntimeError):
    """The ticketing service could not be reached or is not installed.

    ITS OWN TYPE so a caller can tell "GitHub is down" from "this slot's
    ticket is malformed" - the first is every slot's problem and the
    second is one slot's, and criterion 20 turns on the difference.
    """


def slot_label(key: str) -> str:
    return f"{SLOT_LABEL_PREFIX}{key}"


def _gh(args: list[str]) -> str:
    try:
        result = subprocess.run(["gh", *args], capture_output=True, text=True,
                                 check=True)
    except FileNotFoundError as exc:
        raise TicketServiceUnavailable(
            "`gh` is not installed here, so no ticket can be read or written. "
            "The change stands on its durable record and the next pass will "
            "bring the ticket up to date.") from exc
    except subprocess.CalledProcessError as exc:
        raise TicketServiceUnavailable(
            f"`gh {' '.join(args[:2])}` failed: "
            f"{(exc.stderr or '').strip() or exc}") from exc
    return result.stdout


class GitHubTickets:
    """One repository's slot tickets.

    Holds no state beyond which repository it is talking to, because the
    reconciler is a pure pass over current state and an object that
    remembered anything between passes would be a second place for the
    truth to live.
    """

    def __init__(self, owner: str, repo: str):
        self.owner = owner
        self.repo = repo
        self._labels_ensured: set[str] = set()

    @property
    def _repo(self) -> str:
        return f"{self.owner}/{self.repo}"

    def _ensure_label(self, name: str, description: str, colour: str) -> None:
        """`gh issue create --label` needs a real repo label, unlike
        `gh issue list --label` which silently matches nothing - a real
        bug this project already hit once (plans/qa-pipeline.md item
        79). `--force` makes it create-or-update, so it is safe on every
        pass rather than only the first."""
        if name in self._labels_ensured:
            return
        _gh(["label", "create", name, "--repo", self._repo,
             "--description", description, "--color", colour, "--force"])
        self._labels_ensured.add(name)

    def find(self, key: str) -> Ticket | None:
        """This slot's ticket, open or closed, or None.

        BOTH STATES, because criterion 12 has to find a ticket a person
        CLOSED in order to reopen it - and a query filtered to open ones
        would quietly open a second ticket for that slot instead, which
        is criterion 2's whole risk.
        """
        out = _gh(["issue", "list", "--repo", self._repo,
                   "--label", SCHEME_LABEL, "--label", slot_label(key),
                   "--state", "all", "--json", "number,state", "--limit", "2"])
        found = json.loads(out or "[]")
        if not found:
            return None
        # LOWEST NUMBER WINS where two exist, which is criterion 2 under
        # the race it names: two reconcilers running at the same moment
        # can both find nothing and both create. Neither can be stopped
        # from creating, so the rule is that they agree afterwards on
        # WHICH is the ticket - and the older one is the one anybody may
        # already have commented on.
        chosen = min(found, key=lambda item: item["number"])
        return Ticket(key=key, number=chosen["number"],
                       closed=str(chosen.get("state", "")).upper() == "CLOSED")

    def open(self, key: str, title: str, body: str) -> Ticket:
        self._ensure_label(SCHEME_LABEL,
                            "One ticket per expected supply (REQ-PIPE-083)",
                            _SCHEME_COLOUR)
        self._ensure_label(slot_label(key), f"Slot {key}", _SLOT_COLOUR)
        out = _gh(["issue", "create", "--repo", self._repo, "--title", title,
                   "--body", body, "--label", SCHEME_LABEL,
                   "--label", slot_label(key)])
        return Ticket(key=key, number=_number_from_url(out), closed=False)

    def comment(self, ticket: Ticket, body: str) -> None:
        _gh(["issue", "comment", str(ticket.number), "--repo", self._repo,
             "--body", body])

    def set_body(self, ticket: Ticket, body: str) -> None:
        """Rewrite the ticket's body in place (REQ-GHUB-109 criterion 3).

        THE BODY, NOT A PINNED COMMENT. GitHub has no pinned comment,
        and the body is the one part of a thread a reader sees without
        scrolling - which is the whole requirement: a thread quiet for a
        month still has to say where the supply has got to.

        IT REPLACES ONLY WHAT THIS SCHEME WROTE, because this scheme
        opened the ticket and nothing else writes its body. A ticket
        from before the scheme is never found by `find()` at all, so it
        can never reach here (criterion 19).
        """
        _gh(["issue", "edit", str(ticket.number), "--repo", self._repo,
             "--body", body])

    def reopen(self, ticket: Ticket) -> None:
        _gh(["issue", "reopen", str(ticket.number), "--repo", self._repo])
        ticket.closed = False

    def comments(self, ticket: Ticket) -> list[str]:
        out = _gh(["issue", "view", str(ticket.number), "--repo", self._repo,
                   "--json", "comments"])
        payload = json.loads(out or "{}")
        return [c.get("body") or "" for c in (payload.get("comments") or [])]


def _number_from_url(text: str) -> int:
    """`gh issue create` prints the new issue's URL and nothing else.

    A FAILURE TO PARSE IT IS THE SERVICE'S FAILURE, not a slot's: it
    means `gh` printed something this does not understand, which is the
    same class of problem as it not being there at all.
    """
    tail = (text or "").strip().rsplit("/", 1)[-1]
    if not tail.isdigit():
        raise TicketServiceUnavailable(
            f"could not read an issue number out of `gh issue create`'s output: "
            f"{(text or '').strip()!r}")
    return int(tail)
