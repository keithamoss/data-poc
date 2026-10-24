"""Which cross-table result COUNTS toward the supply on show, on each date -
the dashboard's half of REQ-PIPE-269, and the fix for post-build-review
#262 R4.

THE ANSWERS TRAVEL, NOT THE RULE (the slot timeline's own reasoning). The
page cannot ask Python "as at Tuesday", so for every cross-table check card
and every supply of the page's table a result is about, the build works out
- through supply_status.count, the gate's own function (criterion 7) - which
result counts toward that supply at each instant anything relevant changed:
a result being recorded, or a decision changing what a period beside it
holds. It keeps only the instants at which the answer CHANGED, one per
asset day (the page's date means the end of that day), and the page looks
up the newest on or before the date on show. Nothing here is decided in
JavaScript.

THE CASE R4 NAMED: the as-of clip kept every result recorded under another
table's run as the card's newest, whatever supply it read - so a late reader
of an older Clients supply showed as current on the page of the newer one,
while the gate would never have used it. A result now becomes the card's
current only where it is about the supply on show and counts toward it on
that date.

RECORDED QA RESULTS AND THE DECISION LOG ONLY (CLAUDE.md's build rule): the
results file's entries, the slot timeline and qa.owed_run. Never a schema
holding supply rows. Linear in recorded cross-table results times the
instants that matter to each one's supply (the PERFORMANCE NFR), never a
per-render walk of history.
"""
from __future__ import annotations

from qa_tools.common import asset_time, qa_store, supply_status

#: A point's reasons where no result counts: an owed check reads red with
#: one of supply_status's two reasons; NOT_COUNTED is a check owed nothing
#: (criterion 6) or a could-not-run that counts only toward the table that
#: asks (criterion 4) - "No data" on the page, never a colour.
NOT_COUNTED = "not-counted"


def _record(entry: dict, check_id: str, declared_on: str) -> dict:
    """A history entry in the shape supply_status.count reads."""
    record = {"check_id": check_id, "dataset_id": declared_on, "run_id": entry["run_id"],
              "status": entry.get("status"), "reads": entry.get("reads"), "_rank": entry["rank"]}
    if entry.get("not_evaluated"):
        record["unrunnable_reason"] = entry["not_evaluated"]
    return record


def _about(entry: dict) -> str | None:
    """The supply of the page's table an entry is about - None for one that
    met a held supply (REQ-PIPE-279 criterion 15), which is shown and never
    counted."""
    if entry.get("read_state") not in (None, qa_store.READ):
        return None
    return entry.get("supply_id")


def points(dataset_id: str, check_id: str, history: list[dict], *,
           warehouse: supply_status.HoldingsTimeline,
           owed: supply_status.Owing | None) -> dict[str, list[dict]]:
    """{supply: [{on, rank, reason, owedBy, owedSince}]} for one cross-table
    card: from each `on` (an asset day), the result with that `rank` counts
    toward the supply - or, with no rank, nothing does and `reason` says why.
    `history` is the card's entries, in rank order."""
    declared_on = check_id.split(".")[3] if check_id.count(".") >= 4 else dataset_id
    by_supply: dict[str, list[dict]] = {}
    for entry in history:
        supply = _about(entry)
        if supply:
            by_supply.setdefault(supply, []).append(entry)
    out: dict[str, list[dict]] = {}
    for supply, entries in sorted(by_supply.items()):
        records = [(_at(e), _record(e, check_id, declared_on)) for e in entries]
        tables = {t for e in entries for t in (e.get("reads") or {})}
        involved = {dataset_id, *(d for d in map(supply_status.dataset_of, tables) if d)}
        first = min((at for at, _r in records if at is not None), default=None)
        instants = sorted({at for at, _r in records if at is not None}
                          | {t for t in warehouse.instants(involved)
                             if first is None or t >= first})
        found: list[dict] = []
        for when in instants:
            got = [r for at, r in records if at is None or at <= when]
            if not got:
                continue
            counted = supply_status.count(dataset_id, supply, got, holdings=warehouse.at(when),
                                          owed=owed, at=when)
            point = _point(counted[-1] if counted else None)
            point["on"] = asset_time.local_date(when).isoformat()
            if found and found[-1]["on"] == point["on"]:
                found.pop()
            if found and {k: v for k, v in found[-1].items() if k != "on"} == \
                    {k: v for k, v in point.items() if k != "on"}:
                continue
            found.append(point)
        if found:
            out[supply] = found
    return out


def _point(newest: dict | None) -> dict:
    if newest is None:
        return {"rank": None, "reason": NOT_COUNTED}
    if newest.get("warehouse_reason"):
        return {"rank": None, "reason": newest["warehouse_reason"],
                "owedBy": newest.get("owed_by_decision"), "owedSince": newest.get("owed_since")}
    return {"rank": newest["_rank"], "reason": None}


def _at(entry: dict):
    """When the result came to exist - the page's own 'recorded by' rule: its
    run's recorded instant (qa.run.run_timestamp, which run_instant is written
    from), the one clock red_promoted and supply_status.recorded_by date by
    too (post-build-review #266 D2, Keith Q4 = A)."""
    value = entry.get("recorded_at")
    return supply_status.instant(value) if value else None
