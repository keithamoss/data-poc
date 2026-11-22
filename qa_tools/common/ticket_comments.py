"""The processing pass reads new slot-ticket comments and hands each to the
GitHub filing route once (REQ-GHUB-433).

POLLED, OUTBOUND, FROM WHERE THE DATABASE IS (criteria 1 to 3; Keith
2026-11-21, Q2.1 (a)). No workflow can reach the decision log since
REQ-PIPE-089, so a command posted on a ticket is read by the pass that
already calls GitHub outbound to reconcile tickets - the same route and the
same credential, and no inbound connection.

HANDLED IDS, NOT A TIME MARKER (criteria 4 and 5). GitHub's `since` filters
on UPDATED time, so an edited old comment comes back in a later listing; the
ids recorded in qa.ticket_comment_handled are what make a comment's handling
happen once. The listing's anchor is the creation instant of the newest
comment already handled (v6, architect finding C): every comment not yet
handled was created after it or edited since, so the listing is a superset,
and the ids cut it down to exactly-once.

DRAIN THE BACKLOG (Thread H): every unhandled comment, oldest first by its
creation time, each handled and recorded before the next, so a pass that
fails partway keeps what it handled and the next pass reads the rest.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from qa_tools.common import qa_store, supply_db

TABLE = f'"{qa_store.SCHEMA}".ticket_comment_handled'


@dataclass
class CommentsRead:
    """What the stage did (criterion 14): comments read, decisions raised,
    refusals posted - and, where it stopped, what failed (criterion 8)."""

    read: int = 0
    raised: int = 0
    refused: int = 0
    failure: tuple[str, str] | None = None
    #: Comments this asset does not own - another asset's slot, a ticket
    #: of no slot - left alone (criterion 10). Never counted as read.
    not_ours: int = 0
    handled: list[int] = field(default_factory=list)

    def line(self) -> str:
        """The pass report's line - never 'nothing to process' once it has
        read a comment."""
        return (f"Read {self.read} new ticket comment(s): {self.raised} decision(s) raised, "
                f"{self.refused} refused.")


def handled_ids(conn) -> set[int]:
    return {r[0] for r in conn.execute(f"SELECT comment_id FROM {TABLE}").fetchall()}


def anchor(conn) -> str | None:
    """The creation instant of the newest comment already handled, as GitHub's
    `since` takes it - None before any is handled (no cut-over: Keith
    2026-11-21, 'still a local poc')."""
    found = conn.execute(f"SELECT max(created_at) FROM {TABLE}").fetchall()[0][0]
    if found is None:
        return None
    if found.tzinfo is None:
        found = found.replace(tzinfo=timezone.utc)
    return found.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mark(comment_id: int, created_at: str) -> None:
    with supply_db.connect(label="mothman:ticket-comments") as conn:
        conn.execute(f"INSERT INTO {TABLE} (comment_id, created_at) VALUES (?, ?) "
                     "ON CONFLICT (comment_id) DO NOTHING", [comment_id, created_at])


def _ours(slot_key: str):
    """The slot's dataset in the selected asset's hierarchy, or None where it
    is not one of this asset's (criterion 10)."""
    from asset_model import hierarchy

    dataset_id = (slot_key or "").partition("/")[0]
    try:
        return hierarchy.dataset(dataset_id)
    except hierarchy.UnknownDatasetError:
        return None


def read_and_handle(service) -> CommentsRead:
    """One pass's comment stage, against `service` (ticket_github.GitHubTickets,
    or a stand-in in tests - the real API is never called from one)."""
    from qa_tools.common import filing_from_github as route
    from qa_tools.common.ticket_reconciler import Ticket

    out = CommentsRead()
    with supply_db.connect(label="mothman:ticket-comments") as conn:
        qa_store.ensure_schema(conn)
        since, done = anchor(conn), handled_ids(conn)
    listings = {}
    for what, call in (("listing the repository's issue comments",
                        lambda: service.issue_comments_since(since)),
                       ("listing the slot tickets", service.slot_tickets),
                       ("reading the service's own GitHub login", service.own_login)):
        try:
            listings[what] = call()
        except Exception as exc:  # noqa: BLE001 - criterion 8: named, read next pass
            out.failure = (f"ticket comments ({what})", f"{type(exc).__name__}: {exc}")
            return out
    comments, tickets, own = listings.values()

    todo = []
    for c in comments:
        if c["id"] in done or c["issue"] not in tickets:
            continue
        # ITS OWN REPLIES AND RECONCILIATIONS ARE NEVER COMMANDS (criterion 6).
        if own and c["author"] == own:
            continue
        if _ours(tickets[c["issue"]]) is None:
            out.not_ours += 1
            continue
        todo.append(c)
    todo.sort(key=lambda c: (_instant(c["created_at"]), c["id"]))

    for c in todo:
        key = tickets[c["issue"]]
        out.read += 1
        try:
            kind, _outcome = route.handle_counted(
                # THE AUTHOR IS GITHUB'S RECORD OF WHO POSTED IT (criterion 9).
                route.Comment(body=c["body"], author=c["author"], slot_key=key),
                collection_id=_ours(key).collection_id,
                # ITS GITHUB CREATION INSTANT IS THE DECISION'S effective_at
                # (criterion 7).
                effective_at=c["created_at"],
                service=service, ticket=Ticket(key=key, number=c["issue"]))
            _mark(c["id"], c["created_at"])
        except Exception as exc:  # noqa: BLE001 - criterion 8: kept so far, the rest next pass
            out.failure = (f"ticket comment {c['id']} on #{c['issue']} ({key})",
                           f"{type(exc).__name__}: {exc}")
            return out
        out.handled.append(c["id"])
        if kind == route.RAISED:
            out.raised += 1
        elif kind == route.REFUSED:
            out.refused += 1
    return out


def _instant(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))
