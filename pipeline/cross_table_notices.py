"""The top-of-page lines that say a dataset's red comes from ANOTHER table
(REQ-DASH-204), and that a supply was held back with its delivery
(REQ-DASH-275) - worked out at build time, as at every date, and looked up
by the page.

THE ANSWERS TRAVEL, NOT THE RULE (pipeline/warehouse_counts.py's reasoning).
The page cannot ask Python "as at Tuesday", so for each supply of a dataset
this works out, on every asset day anything relevant changed, what the line
says - and keeps only the days on which the answer changed. The page looks
up the newest on or before the date on show.

WHAT IT READS: the cross-table cards build_one_table has just made (each
history entry's structured `unreadable` tables, and which result counts
toward each supply on each date, REQ-PIPE-269's `counted`), and the decision
log - the gate's 'promotion-withheld' entries with their structured fields
(REQ-PIPE-267 criterion 13), each supply's rejections and supersessions, a
contested pair's settlement and an owed re-check's promotion. RECORDED QA
RESULTS AND RECORDED DECISIONS ONLY (CLAUDE.md's build rule): never a schema
holding supply rows, never a reason's prose.

WHICH TABLE COULD NOT BE READ is root_cause.blocking_tables - the one
structured reading the tickets' root and these lines share (REQ-DASH-204
criterion 10; REQ-PIPE-278 criterion 1).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from qa_tools.common import asset_time, decision_log, hierarchy, period_schema

#: A line's form - REQ-DASH-204 criterion 2's one wording and the cases it
#: names, and criterion 7's two.
GENERAL = "general"
PACKAGE = "package"
JOINED = "joined"
TURNED_DOWN = "turned-down"
REPLACED = "replaced"
OWED = "owed"
SETTLED = "settled"

#: supply_status's reason for a red that an owed re-check stands behind.
RECHECK_OWED = "recheck-owed"

#: Reasons whose cause has no item of its own in the terminal's queue
#: (REQ-DASH-204 criterion 16; REQ-PIPE-210 criterion 9): a partner slot past
#: due, or one a person rejected that nothing has replaced.
_NO_ITEM_CODES = (period_schema.PAST_DUE, period_schema.REJECTED)


def _day(value, zones=None) -> str | None:
    if not value:
        return None
    return asset_time.local_date(asset_time.parse_instant(str(value), "notice"),
                                 zones).isoformat()


def _iso(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


@dataclass
class Log:
    """What the decision log says, read once per collection."""
    #: {supply: [(day, action, held_back_by, detail, effective iso)]}, oldest
    #: first: the gate's entries about each supply.
    gate: dict = field(default_factory=dict)
    #: {supply: [(day, action, superseded_by)]}: what took it out of the view.
    states: dict = field(default_factory=dict)
    #: {supply: received instant iso}
    receipts: dict = field(default_factory=dict)
    #: {decision id: (dataset, supply, effective iso)}
    decisions: dict = field(default_factory=dict)
    #: [contested-pair Blocker]
    contests: list = field(default_factory=list)
    #: {supply: [(instant, action, superseded_by)]}: states, by instant.
    state_instants: dict = field(default_factory=dict)

    def held_back_at(self, supply: str, when) -> dict | None:
        """The supply's newest gate entry at or before `when`, where it is a
        hold-back by another supply: {by, came, by_received}, else None."""
        found = None
        for at, action, by, detail in self.gate_instants.get(supply, ()):
            if at <= when:
                found = (action, by, detail)
        if not found or found[0] != decision_log.PROMOTION_WITHHELD or not found[1]:
            return None
        detail = found[2] or {}
        return {"by": found[1], "came": detail.get("came"), "by_received": detail.get("by_received"),
                "failed": detail.get("failed"), "checks": detail.get("checks") or []}

    #: {supply: [(instant, action, held_back_by, detail)]}
    gate_instants: dict = field(default_factory=dict)
    #: {supply: [(decision id, effective iso, actor kind, promoted_with, gate application)]}
    promotes: dict = field(default_factory=dict)
    #: {gate application: [(dataset, supply)]} - the supplies it did not promote.
    withheld_in: dict = field(default_factory=dict)

    def gate_entry_on(self, supply: str, day: str):
        found = None
        for entry in self.gate.get(supply, ()):
            if entry[0] <= day:
                found = entry
        return found

    def state_on(self, supply: str, day: str):
        """(action, superseded_by) of the newest decision about the supply's
        place in the view on or before `day`, or None."""
        found = None
        for when, action, newer in self.states.get(supply, ()):
            if when <= day:
                found = (action, newer)
        return found

    def turned_down_on(self, supply: str, day: str) -> bool:
        got = self.state_on(supply, day)
        return bool(got) and got[0] == decision_log.REJECT

    def replaced_on(self, supply: str, day: str) -> str | None:
        """The supply that superseded this one by `day`, or None."""
        got = self.state_on(supply, day)
        return got[1] if got and got[0] == decision_log.SUPERSEDE else None

    def days_about(self, supplies) -> set[str]:
        out = set()
        for s in supplies:
            out |= {e[0] for e in self.gate.get(s, ())}
            out |= {e[0] for e in self.states.get(s, ())}
        return out


_GATE_ACTIONS = (decision_log.PROMOTE, decision_log.PROMOTION_WITHHELD,
                 decision_log.PROMOTION_REFUSED)
_STATE_ACTIONS = (decision_log.PROMOTE, decision_log.REJECT, decision_log.SUPERSEDE,
                  decision_log.UN_SUPERSEDE, decision_log.DEMOTE, decision_log.REFILE)


def read_log(conn, collection_id: str) -> Log:
    """The collection's decision log, in the shapes the lines read."""
    from qa_tools.common import dataset_blockers

    log = Log()
    actions = tuple(dict.fromkeys(_GATE_ACTIONS + _STATE_ACTIONS))
    for (decision_id, dataset_id, supply, action, at, by, detail,
         newer, actor_kind, promoted_with, application) in conn.execute(
            f"SELECT id, dataset_id, supply, action, effective_at, held_back_by, "
            f"held_back_detail, superseded_by, actor_kind, promoted_with, gate_application "
            f"FROM {decision_log.TABLE} "
            f"WHERE collection_id = ? AND action IN ({', '.join('?' * len(actions))}) "
            "ORDER BY effective_at, id", [collection_id, *actions]).fetchall():
        log.decisions[decision_id] = (dataset_id, supply, _iso(at))
        if not supply:
            continue
        day = _day(at)
        if action == decision_log.PROMOTE:
            log.promotes.setdefault(supply, []).append(
                (decision_id, _iso(at), actor_kind, list(promoted_with or []), application))
        # NOT PROMOTED IN THAT APPLICATION: held back by another, or refused on
        # its own data - either way the supply received with it was held back.
        if action in (decision_log.PROMOTION_WITHHELD, decision_log.PROMOTION_REFUSED) \
                and application is not None:
            log.withheld_in.setdefault(application, []).append((dataset_id, supply))
        if action in _GATE_ACTIONS:
            log.gate.setdefault(supply, []).append((day, action, by, detail or {}, _iso(at)))
            log.gate_instants.setdefault(supply, []).append((at, action, by, detail or {}))
        if action in _STATE_ACTIONS:
            log.states.setdefault(supply, []).append((day, action, newer))
            log.state_instants.setdefault(supply, []).append((at, action, newer))
    for supply, received in conn.execute(
            "SELECT supply_id, received_at FROM qa.supply_receipt").fetchall():
        log.receipts[supply] = _iso(received)
    # THE CONTESTS, read as recorded - a failure to read them is a failure of
    # the build, never "no contest" (functional critic on 7093c20).
    log.contests = list(dataset_blockers.contests(conn))
    return log


def _dataset_ref(dataset_id: str) -> dict:
    try:
        ds = hierarchy.dataset(dataset_id)
    except hierarchy.UnknownDatasetError:
        return {"datasetId": dataset_id, "name": dataset_id}
    return {"datasetId": dataset_id, "name": ds.dataset_name, "agencyId": ds.agency_id,
            "collectionId": ds.collection_id}


def check_key(card: dict) -> tuple:
    """ONE CHECK, however many tools ran it (UX critic on 7093c20, B2; Keith
    Q2 = a, PROVISIONAL): a line counts checks as the grid shows them - one row
    per check name and the tables it is between - never tool results."""
    between = card.get("between") or {}
    return (card.get("name") or card.get("check_id"), between.get("declared_on"),
            tuple(between.get("reads") or ()))


def _entries_by_rank(card: dict) -> dict:
    return {h["rank"]: h for h in [*card.get("history", []), *card.get("superseded", [])]
            if isinstance(h.get("rank"), int)}


def _counted_on(points, day: str):
    found = None
    for p in points or ():
        if p["on"] <= day:
            found = p
    return found


def _settled_on(log: Log, dataset_id: str, at: str | None, day: str) -> str | None:
    """The day the contested pair of `dataset_id` that was open when the
    result was recorded (`at`) was settled, where that is on or before
    `day` - else None (REQ-DASH-204 criterion 7's second line)."""
    if not at:
        return None
    from datetime import datetime

    when = asset_time.parse_instant(at, "notice")
    for b in log.contests:
        if b.dataset_id != dataset_id or not b.resolved_at:
            continue
        try:
            if not b.open_at(when):
                continue
        except (TypeError, ValueError):
            continue
        settled = _day(b.resolved_at)
        if settled and settled <= day and datetime.fromisoformat(b.resolved_at) > when:
            return settled
    return None


def _own_red(own_cards: list[dict], supply: str, day: str) -> bool:
    """Whether the supply's newest own (non-cross-table) result of any check,
    recorded by `day`, is red."""
    zones = asset_time.timezone_versions()  # once (REQ-PIPE-254 criterion 19)
    for card in own_cards:
        newest = None
        for h in card.get("history", []):
            if h.get("supply_id") != supply or not isinstance(h.get("rank"), int):
                continue
            recorded = _day(h.get("recorded_at"), zones)
            if recorded and recorded > day:
                continue
            if newest is None or h["rank"] > newest["rank"]:
                newest = h
        if newest is not None and newest.get("status") == "red":
            return True
    return False


def no_promoted(dataset_id: str, table: str, cross_cards: list[dict], own_cards: list[dict],
                period_of: dict[str, str | None], log: Log) -> dict[str, list[dict]]:
    """REQ-DASH-204: {supply: [{on, lines, ownRed, noItem}]} - from each
    `on`, the lines the supply's page shows for the tables it could not
    read. `cross_cards` are the cross-table cards DECLARED on this dataset
    (criterion 1); `period_of` each supply's period."""
    supplies = sorted({s for c in cross_cards for s in (c.get("counted") or {})})
    by_rank = {id(c): _entries_by_rank(c) for c in cross_cards}
    out: dict[str, list[dict]] = {}
    for supply in supplies:
        relevant, days, partners = False, set(), set()
        for c in cross_cards:
            for p in (c.get("counted") or {}).get(supply, ()):
                days.add(p["on"])
                if p.get("reason") == RECHECK_OWED:
                    relevant = True
                e = by_rank[id(c)].get(p.get("rank"))
                if e and e.get("unreadable"):
                    relevant = True
                    # THE DAY A NOT-YET-DUE PARTNER FALLS DUE is a day the
                    # line changes (criterion 16): from then it is overdue.
                    if e.get("due_at"):
                        days.add(_day(e["due_at"]))
        if not relevant:
            continue
        for e in log.gate.get(supply, ()):
            if e[2]:
                partners.add(e[2])
        days |= log.days_about([supply, *partners])
        days |= {_day(b.resolved_at) for b in log.contests if b.resolved_at}
        first = min(days)
        points: list[dict] = []
        for day in sorted(d for d in days if d and d >= first):
            point = _lines_on(dataset_id, table, supply, day, cross_cards, by_rank, own_cards,
                              period_of.get(supply), log)
            if points and {k: v for k, v in points[-1].items() if k != "on"} == \
                    {k: v for k, v in point.items() if k != "on"}:
                continue
            if not points and not point["lines"]:
                continue
            points.append(point)
        if points:
            out[supply] = points
    return out


def _lines_on(dataset_id, table, supply, day, cross_cards, by_rank, own_cards, period, log):
    groups: dict[str, dict] = {}
    owed: dict[str, dict] = {}
    own_red = _own_red(own_cards, supply, day)
    for c in cross_cards:
        p = _counted_on((c.get("counted") or {}).get(supply), day)
        if p is None:
            continue
        if p.get("rank") is None:
            if p.get("reason") == RECHECK_OWED and p.get("owedBy") in log.decisions:
                by_dataset, by_supply, at = log.decisions[p["owedBy"]]
                g = owed.setdefault(by_dataset, {"checks": set(), "promotedAt": at,
                                                 "supply": by_supply})
                g["checks"].add(check_key(c))
            continue
        e = by_rank[id(c)].get(p["rank"])
        if e is None:
            continue
        unreadable = {t: code for t, code in (e.get("unreadable") or {}).items() if t != table}
        if not unreadable:
            if e.get("status") == "red":
                own_red = True  # a real cross-table verdict, red: its own
            continue
        for t, code in unreadable.items():
            g = groups.setdefault(t, {"checks": set(), "codes": set(), "dueAt": None,
                                      "at": None})
            g["checks"].add(check_key(c))
            g["codes"].add(code or "")
            g["dueAt"] = g["dueAt"] or e.get("due_at")
            g["at"] = g["at"] or e.get("recorded_at")
    lines = []
    for t, g in sorted(groups.items()):
        try:
            other = hierarchy.dataset_for_table(t).dataset_id
        except Exception:  # noqa: BLE001 - not one of ours
            continue
        line = {**_dataset_ref(other), "period": period, "n": len(g["checks"]),
                "form": GENERAL}
        if period_schema.CONTESTED in g["codes"]:
            settled = _settled_on(log, other, g["at"], day)
            if settled:
                line.update(form=SETTLED, settledOn=settled)
        if line["form"] == GENERAL and period_schema.HELD_BACK_WITH_PACKAGE in g["codes"]:
            line.update(_package_form(log, supply, other, day))
        if line["form"] == GENERAL and g["dueAt"] and period_schema.NOT_YET_DUE in g["codes"]:
            line["dueAt"] = g["dueAt"]
        # NO ITEM OF ITS OWN IN THE TERMINAL'S QUEUE (criterion 16): a partner
        # slot past due - by its recorded code, or not due when checked and due
        # by the date on show - or one a person rejected.
        due_day = _day(g["dueAt"])
        # WHICH CAUSE WITHOUT AN ITEM (UX critic on 7093c20, S2): the causing
        # page says "turned down" or "overdue" in its one muted line.
        line["cause"] = "turned-down" if period_schema.REJECTED in g["codes"] else "overdue"
        line["noItem"] = line["form"] == GENERAL and (
            bool(set(_NO_ITEM_CODES) & g["codes"])
            or (period_schema.NOT_YET_DUE in g["codes"] and bool(due_day) and due_day <= day))
        lines.append(line)
    for other, g in sorted(owed.items()):
        lines.append({**_dataset_ref(other), "period": period, "n": len(g["checks"]),
                      "form": OWED, "promotedAt": g["promotedAt"], "noItem": False})
    return {"on": day, "lines": lines, "ownRed": own_red}


def _package_form(log: Log, supply: str, other: str, day: str) -> dict:
    """The package-mate or joined supply of `other`'s dataset held back with
    this one, from this supply's 'promotion-withheld' entry as at `day`, and
    what has happened to it since - or {} where no entry names one."""
    entry = log.gate_entry_on(supply, day)
    if entry is None or entry[1] != decision_log.PROMOTION_WITHHELD or not entry[2]:
        return {}
    by, detail = entry[2], entry[3] or {}
    if by.split("@", 1)[0] != other:
        return {}
    out = {"partner": by, "partnerReceived": detail.get("by_received") or log.receipts.get(by),
           "form": JOINED if detail.get("came") == "joined" else PACKAGE}
    if log.turned_down_on(by, day):
        out["form"] = TURNED_DOWN
    else:
        newer = log.replaced_on(by, day)
        if newer:
            out.update(form=REPLACED, replacedBy=newer, replacedReceived=log.receipts.get(newer))
    return out


def blocking_dataset_ids(points: dict[str, list[dict]]) -> set[str]:
    """Every dataset any of a dataset's lines ever names."""
    return {line["datasetId"] for pts in points.values() for p in pts for line in p["lines"]}


__all__ = ["Log", "read_log", "no_promoted", "blocking_dataset_ids"]
