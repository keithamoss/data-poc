"""A supply held back with its delivery says so at the top of its page, names
the root of the chain, and the card says it once per delivery (REQ-DASH-275)
- worked out at build time, as at every date, and looked up by the page.

THE STRUCTURED FIELDS, NEVER PROSE (criterion 8): each supply's
'promotion-withheld' entries (REQ-PIPE-267 criterion 13: held_back_by, and
the detail's `came`, `by_received`, `failed` and `checks`) and what the
decision log says has happened to the supply that held it back since -
turned down, or replaced. Recorded decisions only, never supply rows.

WHICH HOLD-BACK THIS IS (criterion 1): the supply was held back because
another supply of its gate application was not promoting, re-checked
against the warehouse, and that re-check FAILED (the detail's `failed`) - a
real failing verdict (S1 red, S6). One that could not be checked at all is
REQ-DASH-204's notice instead.

THE CHAIN (criterion 2) follows held_back_by from supply to supply as at the
date, each step's own entry - so the Notifications held back by a held-back
Investigations names Investigations as the root.

Every sentence is SEGMENTS (pipeline/cross_table_grid.py): text set as text,
a dataset a real link the page builds, every supply named through
cross_table_grid.named, the one naming helper.
"""
from __future__ import annotations

from pipeline.cross_table_grid import Receipts, dataset_segment, named, text
from qa_tools.common import asset_time, decision_log, display_time


def _instant(value):
    return asset_time.parse_instant(value if not isinstance(value, str) else value, "held back")


def _end_of(day: str):
    """The end of an asset day: a page's date means the end of it."""
    from datetime import date

    return asset_time.end_of_day(date.fromisoformat(day))


def _latest_gate(log, supply: str, when):
    found = None
    for at, action, by, detail in log.gate_instants.get(supply, ()):
        if at <= when:
            found = (action, by, detail or {})
    return found


def _withdrawn(log, supply: str, when) -> tuple[str, str | None] | None:
    found = None
    for at, action, newer in log.state_instants.get(supply, ()):
        if at <= when:
            found = (action, newer)
    if found and found[0] in (decision_log.REJECT, decision_log.SUPERSEDE):
        return found
    return None


def _held_by(log, supply: str, when):
    """(held_back_by, detail) where the supply's newest gate entry by `when` is
    a hold-back by another supply and nothing has moved it since, else None."""
    got = _latest_gate(log, supply, when)
    if got is None or got[0] != decision_log.PROMOTION_WITHHELD or not got[1]:
        return None
    if _withdrawn(log, supply, when):
        return None
    return got[1], got[2]


def chain_of(log, supply: str, when) -> list[str]:
    """[the supply that held this one back, the one that held THAT back, ...],
    root last, as at `when` - empty where it is not held back by another."""
    out, seen, at = [], {supply}, supply
    while True:
        got = _held_by(log, at, when)
        if got is None:
            return out
        by = got[0]
        if by in seen:
            return out
        out.append(by)
        seen.add(by)
        at = by


def _ds(supply: str) -> str:
    return supply.split("@", 1)[0]


def _notice(log, supply: str, when, receipts: Receipts) -> dict | None:
    got = _held_by(log, supply, when)
    if got is None:
        return None
    by, detail = got
    if not detail.get("failed"):
        return None  # could not be checked: REQ-DASH-204's notice
    by_ds = _ds(by)
    n = len(detail.get("checks") or [])
    checks = f"{n} cross-table check{'s' if n != 1 else ''} {'fail' if n != 1 else 'fails'}"
    gone = _withdrawn(log, by, when)
    if gone is not None:
        # THE PARTNER TURNED DOWN OR REPLACED (criterion 6), from the log as it
        # now stands, where nothing has re-gated this supply since.
        action, newer = gone
        if action == decision_log.REJECT:
            return {"form": "turned-down", "head": [],
                    "body": [text("The "), dataset_segment(by_ds),
                             text(" file received with it was turned down; this supply now needs "
                                  "its own decision.")]}
        return {"form": "replaced", "head": [],
                "body": [text("The "), dataset_segment(by_ds),
                         text(" received with it has been replaced by the one "),
                         *named(by_ds, newer, receipts, style="received"),
                         text("; this supply now needs its own decision.")]}
    chain = chain_of(log, supply, when)
    joined = detail.get("came") == "joined"
    received = detail.get("by_received") or receipts.at(by)
    when_text = display_time.format_instant(received) if received else "on an unrecorded date"
    if len(chain) > 1:
        # THE ROOT AND THE CHAIN (criterion 2): root first, each step in order.
        root, steps = chain[-1], list(reversed(chain[:-1]))
        head = [text("Held back with its delivery:")]
        lead = [text(" the "), dataset_segment(_ds(root)), text(" file was held back")]
        for s in steps:
            lead += [text(", and the "), dataset_segment(_ds(s))]
        lead += [text(" with it.")]
        body = [*lead, text(f" That file (received {when_text}) was held back, so this supply "
                            "was re-checked against the "), dataset_segment(by_ds),
                text(f" in place in the warehouse, and {checks} against it. It is checked again by "
                     "itself once a "), dataset_segment(by_ds), text(" supply is promoted.")]
        return {"form": "chain", "head": head, "body": body, "root": root}
    if joined:
        head = [text("Held back by the "), dataset_segment(by_ds), text(" waiting for a decision.")]
        verb = "is held back"
    else:
        head = [text("Held back with the "), dataset_segment(by_ds), text(" received with it.")]
        verb = "was held back"
    body = [text(f" That file (received {when_text}) {verb}, so this supply was re-checked against "
                 "the "), dataset_segment(by_ds),
            text(f" in place in the warehouse, and {checks} against it. It is checked again by "
                 "itself once a "), dataset_segment(by_ds), text(" supply is promoted.")]
    return {"form": "joined" if joined else "package", "head": head, "body": body, "root": by}


def _holding(log, root: str, when, receipts: Receipts, candidates) -> dict | None:
    """What a root's own page and card say it is holding back as at `when`."""
    held = [s for s in sorted(candidates)
            if s != root and (chain := chain_of(log, s, when)) and chain[-1] == root]
    if not held:
        return None
    held.sort(key=lambda s: (receipts.at(s) or "", s))
    links = []
    for i, s in enumerate(held):
        if i:
            links.append(text(", "))
        links.append(dataset_segment(_ds(s)))
    tail = [text("Holding back with it: "), *links, text(".")]
    failed = [s for s in held if (_held_by(log, s, when) or (None, {}))[1].get("failed")]
    if failed:
        tail += [text(" If this file is turned down, the "), dataset_segment(_ds(failed[0])),
                 text(" supply needs its own decision.")]
    return {"tail": tail, "card": _card(root, held, log, when, receipts),
            "datasets": sorted({_ds(s) for s in held})}


def _card(root: str, held: list[str], log, when, receipts: Receipts) -> list[dict]:
    """'Held back together: <names> (one delivery, received <instant>)', or
    '(received <instant> and <instant>)' where a joined supply came apart
    (criterion 4) - up to three names, then the first two and 'and <n> more'."""
    from pipeline.cross_table_grid import _names

    supplies = [root, *held]
    names = _names([[dataset_segment(_ds(s))] for s in supplies])
    joined = any(((_held_by(log, s, when) or (None, {}))[1]).get("came") == "joined" for s in held)
    instants = sorted({receipts.at(s) for s in supplies if receipts.at(s)})
    if not joined or len(instants) <= 1:
        at = display_time.format_instant(instants[0]) if instants else "on an unrecorded date"
        return [text("Held back together: "), *names, text(f" (one delivery, received {at})")]
    first, last = instants[0], instants[-1]
    if display_time.format_day(first) == display_time.format_day(last):
        clock = lambda v: display_time.format_instant(v).split(" ", 1)[0]  # noqa: E731
        when_text = f"{clock(first)} and {clock(last)}, {display_time.format_day(last)}"
    else:
        when_text = f"{display_time.format_instant(first)} and {display_time.format_instant(last)}"
    return [text("Held back together: "), *names, text(f" (received {when_text})")]


def involved(log) -> tuple[set[str], list[str]]:
    """(every supply ever held back by another or holding one back, every asset
    day a gate entry or a decision about one of them took effect) - read once
    per collection."""
    supplies: set[str] = set()
    for s, entries in log.gate_instants.items():
        for at, action, by, _detail in entries:
            if action == decision_log.PROMOTION_WITHHELD and by:
                supplies |= {s, by}
    days = set()
    for s in supplies:
        days |= {asset_time.local_date(e[0]).isoformat() for e in log.gate_instants.get(s, ())}
        days |= {asset_time.local_date(e[0]).isoformat() for e in log.state_instants.get(s, ())}
    return supplies, sorted(days)


def for_dataset(dataset_id: str, supplies: list[str], log, receipts: Receipts,
                involvement: tuple[set[str], list[str]]) -> dict[str, list[dict]]:
    """{supply: [{on, notice, holding}]} for each of this dataset's supplies
    ever held back with another or holding one back, from each asset day
    anything about such a hold-back changed."""
    held, days = involvement
    out: dict[str, list[dict]] = {}
    for supply in supplies:
        received = receipts.at(supply)
        if supply not in held or not received:
            continue
        first = asset_time.local_date(_instant(received)).isoformat()
        points: list[dict] = []
        for day in (d for d in days if d >= first):
            when = _end_of(day)
            point = {"on": day, "notice": _notice(log, supply, when, receipts),
                     "holding": _holding(log, supply, when, receipts, held)}
            if points and {k: v for k, v in points[-1].items() if k != "on"} == \
                    {k: v for k, v in point.items() if k != "on"}:
                continue
            if not points and point["notice"] is None and point["holding"] is None:
                continue
            points.append(point)
        if points:
            out[supply] = points
    return out
