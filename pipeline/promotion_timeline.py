"""The promotion panel and the standing-in qualifier, as at each date
(REQ-DASH-197, REQ-DASH-198).

A PAST DATE ASKS A PAST QUESTION. The panel comparing what was promoted
with the latest arrival, and the qualifier saying a period stands on an
earlier one, were both answered once, as at the build - so a past view
warned about files that had not arrived yet, and named a period that had
not happened.

THE ANSWERS TRAVEL, NOT THE RULE - the same decision slot_timeline.py
records for the slots. The page cannot ask Python "as at Tuesday", so the
build works out the answer at the end of every asset day on which
anything relevant happened, keeps only the days on which the answer
CHANGED (criteria 10, 11 and 21), and the page shows the newest one on or
before the date on show.

ONE WALK, IN MEMORY (REQ-DASH-197's build-cost NFR). Everything is read
once - the slot timeline the build already computes, the dataset's
filings, its decisions and the contests - and each day is answered from
those, rather than a qa.slot_holds query per day, so the cost grows with
the change points and not with change points times the whole history.
The SQL readers in promotion_state answer the same questions one instant
at a time; tests/test_promotion_timeline.py holds every change point
against them (criterion 22), which is what stops this walk becoming a
second rule.

RECORDED METADATA ONLY (criterion 12): filings, decisions, slot holds and
delivery records. Never a schema holding supply rows.
"""
from __future__ import annotations

from datetime import datetime

from qa_tools.common import (asset_time, dataset_blockers, decision_log, filing,
                              promotion_state, rejection, supply_db)

PROMOTED, SUBSTITUTED, INHERITED = "promoted", "substituted", "inherited"
_STANDS = {SUBSTITUTED: promotion_state.SUBSTITUTED, INHERITED: promotion_state.INHERITED}


def _instant(value) -> datetime:
    return value if isinstance(value, datetime) else asset_time.parse_instant(
        value, "promotion timeline")


def _iso(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


class _History:
    """One dataset's recorded facts, read once."""

    def __init__(self, conn, dataset_id: str, timeline: list[dict]):
        self.dataset_id = dataset_id
        self.slots = [{**e, "_at": _instant(e["at"])} for e in timeline]
        self.filings = filing.filing_history(conn, dataset_id)
        self.decisions = [{**d, "_at": _instant(d["effective_at"])}
                          for d in decision_log.decisions_for(conn, dataset_id)]
        self.by_id = {d["id"]: d for d in self.decisions}
        # The period an indirection stands on, which decisions_for() does not
        # carry - read for the substitutions and inheritances only.
        self.stands_on = dict(conn.execute(
            f"SELECT id, stands_on FROM {decision_log.TABLE} "
            "WHERE dataset_id = ? AND stands_on IS NOT NULL", [dataset_id]).fetchall())
        self.contests = [c for c in dataset_blockers.contests(conn)
                         if c.dataset_id == dataset_id]
        self._runs: dict[str, str | None] = {}
        self._conn = conn

    def run_of(self, supply: str | None) -> str | None:
        from pipeline import slot_timeline

        if not supply:
            return None
        if supply not in self._runs:
            self._runs[supply] = slot_timeline._run_for(self._conn, self.dataset_id, supply)
        return self._runs[supply]

    def instants(self) -> list[datetime]:
        out = [e["_at"] for e in self.slots] + [d["_at"] for d in self.decisions]
        out += [f["at"] for f in self.filings]
        for c in self.contests:
            out.append(_instant(c.opened_at))
            if c.resolved_at:
                out.append(_instant(c.resolved_at))
        return out

    # ---- what each slot held, as at an instant (from the slot timeline)
    def held(self, at: datetime) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for e in self.slots:
            if e["_at"] > at:
                break
            out[e["slot"]] = e
        return out

    # ---- the answers, as at an instant
    def promoted(self, held: dict[str, dict]) -> dict | None:
        best = None
        for slot, e in held.items():
            if e.get("held_as") != PROMOTED:
                continue
            # The decision that put it there: its effective instant, then the
            # LATER PERIOD at one instant (criterion 1), then the id - the
            # order decision_log.promoted_supply() reads.
            key = (e["_at"], slot, e["decision_id"])
            if best is None or key > best[0]:
                best = (key, e)
        if best is None:
            return None
        e = best[1]
        return {"supply": e["holder"], "period": e["slot"]}

    def why_not(self, supply: str, period: str | None, at: datetime,
                held: dict[str, dict], contested: bool) -> str:
        """promotion_state._why_not(), from what was read once."""
        mine = [d for d in self.decisions if d["supply"] == supply and d["_at"] <= at]
        if any(d["action"] == decision_log.REJECT for d in mine):
            return promotion_state.REJECTED
        moves = [d for d in mine if d["action"] in (
            decision_log.SUPERSEDE, decision_log.UN_SUPERSEDE, decision_log.REFILE)]
        if moves and max(moves, key=lambda d: (d["_at"], d["id"]))["action"] \
                == decision_log.SUPERSEDE:
            return promotion_state.SUPERSEDED
        if contested:
            return promotion_state.TWO_FILES
        if not period:
            return promotion_state.NO_SLOT
        h = held.get(period)
        holder = h["holder"] if h and h.get("held_as") in (PROMOTED, SUBSTITUTED) else None
        if holder == supply:
            return promotion_state.PROMOTED_ELSEWHERE
        if holder is not None:
            return promotion_state.SUPERSEDED
        by_a_person = any(
            d["actor_kind"] == decision_log.PERSON
            and d["action"] not in rejection.NOT_A_DECISION_ABOUT_ITS_DATA for d in mine)
        return (promotion_state.RETURNED_BY_A_PERSON if by_a_person
                else promotion_state.AWAITING_DECISION)

    def standing(self, held: dict[str, dict]) -> dict[str, dict]:
        """Every period holding an earlier period's supply, as
        promotion_state.standing_in() records it."""
        out = {}
        for slot, e in held.items():
            kind = _STANDS.get(e.get("held_as") or "")
            d = self.by_id.get(e["decision_id"])
            if not kind or not d:
                continue
            out[slot] = promotion_state.StandingIn(
                kind=kind, period=slot, stands_on=self.stands_on.get(d["id"]), supply=d["supply"],
                decided_by=d["actor"] if d["actor_kind"] == decision_log.PERSON else None,
                reason=d["reason"] or "").as_record()
        return out

    def panel(self, at: datetime) -> tuple[dict, dict[str, dict]]:
        held = self.held(at)
        promoted = self.promoted(held)
        filed = filing.filings_as_at(self.filings, at)
        answer = {"promoted": None, "arrived": None, "differs": False, "whyNot": None}
        if promoted:
            answer["promoted"] = {**promoted, "runId": self.run_of(promoted["supply"])}
        if filed:
            latest = filed[-1]
            files = promotion_state.contested_files(
                self.dataset_id, latest["supply_id"], at, self.contests)
            answer["arrived"] = {"supply": latest["supply_id"], "period": latest["slot"],
                                 "files": list(files)}
            differs = latest["supply_id"] != (promoted or {}).get("supply")
            answer["differs"] = differs
            if differs:
                answer["whyNot"] = self.why_not(latest["supply_id"], latest["slot"], at,
                                                held, bool(files))
        return answer, self.standing(held)

    def decisions_on(self, day) -> list[dict]:
        """The decisions that took effect on this asset day - what produced a
        change point (criterion 9), each with both instants so the page can
        tell a decision recorded after the date on show."""
        return [{"id": d["id"], "action": d["action"], "supply": d["supply"],
                 "at": _iso(d["effective_at"]), "recordedAt": _iso(d["recorded_at"])}
                for d in self.decisions if asset_time.local_date(d["_at"]) == day]


def for_dataset(dataset_id: str, timeline: list[dict],
                conn: supply_db.SupplyConnection | None = None) -> dict:
    """{points, standing} for one dataset.

    `points` is the panel's answer at the end of each asset day on which it
    CHANGED (at most one per day, criterion 21). `standing` is, per period,
    each day its standing-in answer changed (REQ-DASH-198) - kept apart
    because the qualifier is about the period on show, not the dataset.
    `timeline` is slot_timeline.for_dataset()'s answer, which the build
    already holds.
    """
    if conn is None:
        with supply_db.connect(read_only=True, label="mothman:promotion-timeline") as c:
            return for_dataset(dataset_id, timeline, conn=c)

    h = _History(conn, dataset_id, timeline)
    days = sorted({asset_time.local_date(i) for i in h.instants()})
    points: list[dict] = []
    standing: list[dict] = []
    last_panel = None
    last_standing: dict[str, dict | None] = {}
    last_entry: dict[str, dict] = {}
    for day in days:
        end = asset_time.end_of_day(day)
        answer, stands = h.panel(end)
        if answer != last_panel:
            points.append({"on": day.isoformat(), **answer,
                           "decisions": h.decisions_on(day)})
            last_panel = answer
        held = h.held(end)
        for period in sorted(set(last_standing) | set(stands)):
            now = stands.get(period)
            if now == last_standing.get(period):
                continue
            entry = {"on": day.isoformat(), "period": period, "standingIn": now,
                     "decisions": h.decisions_on(day)}
            if now:
                entry["earnedOn"] = _earned_on(h, now["standsOn"], now["supply"])
            # HOW THE STAND-IN BEFORE IT ENDED, said on that one (criterion 3):
            # replaced where the period now holds something, removed where it
            # holds nothing. The page reads it; it never works it out.
            prev = last_entry.get(period)
            if prev is not None and prev["standingIn"]:
                h_now = held.get(period)
                replaced = now is not None or bool(
                    h_now and h_now.get("held_as") in (PROMOTED, SUBSTITUTED, INHERITED))
                prev["since"] = {"how": "replaced" if replaced else "removed",
                                 "on": entry["on"]}
            standing.append(entry)
            last_standing[period] = now
            last_entry[period] = entry
    return {"points": points, "standing": standing}


def _earned_on(h: _History, period: str, supply: str) -> str | None:
    """The asset day the named supply was promoted into the period that
    earned the results - where REQ-DASH-198 criterion 14's drill lands, so
    those results are on the page."""
    for e in h.slots:
        if e["slot"] == period and e.get("held_as") == PROMOTED and e["holder"] == supply:
            return asset_time.local_date(e["_at"]).isoformat()
    return None


def at(points: list[dict], on: str) -> dict | None:
    """The newest change point on or before an asset date - the PAGE's
    lookup, written here so the suite can hold it against the readers."""
    found = None
    for p in points:
        if p["on"] > on:
            break
        found = p
    return found
