"""Where each cross-table result sits on a dataset page, and what it says it
read - REQ-DASH-272's grid of "against what's staged" and "against what's in
the warehouse", the verdict line's warehouse clause, and every sentence that
names a supply - worked out at build time, as at every date, and looked up by
the page.

THE ANSWERS TRAVEL, NOT THE RULE (pipeline/warehouse_counts.py). For each
history entry of a cross-table card this works out, at every instant
anything it read changed place - promoted, inherited, turned down, replaced -
which cell it belongs in on the page of the supply it is about, the short
note under it and the full "Read against ..." sentence; the page keeps only
the answer in force on the date on show.

A CELL IS DECIDED FROM STRUCTURED FIELDS (criterion 7): the supplies the
check recorded reading (qa.check_read, REQ-PIPE-279), what the decision log
says each one was at that instant (the slot timeline's `held_as` and holder,
each supply's rejections and supersessions), and the run's cause - never a
reason's prose. RECORDED QA RESULTS AND THE DECISION LOG ONLY.

ONE NAMING HELPER (criterion 22): every supply named in a note, a sentence or
the clause goes through `named()`, so the period-clarity work changes how a
supply is named in one place. A name is a SEGMENT the page renders as a real
link (criterion 15) - text segments are set as text, never markup.
"""
from __future__ import annotations

import bisect
from datetime import datetime

from qa_tools.common import asset_time, decision_log, display_time, hierarchy, qa_store

#: The two cells (criterion 6); None is neither (criterion 7's third bucket).
STAGED = "staged"
WAREHOUSE = "warehouse"

IN_THE_WAREHOUSE = ("promoted", "substituted", "inherited")

_LEAVES = {decision_log.REJECT: "turned-down", decision_log.SUPERSEDE: "replaced",
           decision_log.DEMOTE: "replaced"}


def _instant(value) -> datetime:
    return asset_time.parse_instant(value if isinstance(value, datetime) else str(value),
                                    "grid")


def _day(value, zones=None) -> str:
    return asset_time.local_date(_instant(value), zones).isoformat()


# ---- segments ----------------------------------------------------------------

def text(words: str) -> dict:
    return {"text": words}


def dataset_segment(dataset_id: str) -> dict:
    """A dataset named in a sentence: its id alone, which the page resolves
    to its name and its address (every dataset is in the page's index)."""
    return {"dataset": dataset_id}


def words_of(segments: list[dict]) -> str:
    """The plain text of a sentence - for an accessible name, and for tests."""
    return "".join(s["text"] if "text" in s else _name_of(s["dataset"]) for s in segments)


def _name_of(dataset_id: str) -> str:
    try:
        return hierarchy.dataset(dataset_id).dataset_name
    except hierarchy.UnknownDatasetError:
        return dataset_id


def _period(name: str | None) -> str:
    return display_time.format_period(name) if name else "this period"


class Receipts:
    """When each supply was received, and which share a day with another of
    their table (criterion 8 adds the time only there)."""

    def __init__(self, receipts: dict[str, str]):
        self._at = {s: r for s, r in receipts.items() if r}
        self._days: dict[tuple[str, str], int] = {}
        # The asset's zones, read once for this value and passed down to
        # every day it is asked (REQ-PIPE-254 criterion 19).
        self._zones = asset_time.timezone_versions()
        for supply, at in self._at.items():
            key = (supply.split("@", 1)[0], _day(at, self._zones))
            self._days[key] = self._days.get(key, 0) + 1

    def at(self, supply: str | None) -> str | None:
        return self._at.get(supply) if supply else None

    def shares_a_day(self, supply: str) -> bool:
        at = self.at(supply)
        return bool(at) and self._days.get((supply.split("@", 1)[0], _day(at, self._zones)),
                                           0) > 1


def named(dataset_id: str, supply: str | None, receipts: Receipts, *, style: str) -> list[dict]:
    """THE ONE HELPER THAT NAMES A SUPPLY (criterion 22).

    style 'note'     '<dataset> received <day>' - with the time where two
                     supplies of that table share the day (criterion 8)
    style 'instant'  '<dataset> ... received <instant>' - a sentence's form
    style 'received' 'received <instant>' alone, for a supply already named
    """
    at = receipts.at(supply)
    if style == "note":
        when = "" if not at else (display_time.format_instant(at) if receipts.shares_a_day(supply)
                                  else display_time.format_day(at))
        return [dataset_segment(dataset_id), text(f" received {when}" if when else "")]
    when = display_time.format_instant(at) if at else "on an unrecorded date"
    if style == "received":
        return [text(f"received {when}")]
    return [dataset_segment(dataset_id), text(f" received {when}")]


# ---- what a slot held, as at an instant ----------------------------------------

class Slots:
    """(held_as, holder, stands_on) of a dataset's slot at an instant, by
    lookup over the slot timelines the build already read."""

    def __init__(self, timelines: dict[str, list[dict]]):
        self._by: dict[tuple[str, str], tuple[list[datetime], list[tuple]]] = {}
        for ds, entries in timelines.items():
            grouped: dict[str, list] = {}
            for e in entries:
                grouped.setdefault(e["slot"], []).append(
                    (_instant(e["at"]), e.get("held_as"), e.get("holder"), e.get("stands_on")))
            for slot, rows in grouped.items():
                rows.sort(key=lambda r: r[0])
                self._by[(ds, slot)] = ([r[0] for r in rows], [r[1:] for r in rows])

    def at(self, dataset_id: str, period: str | None, when: datetime) -> tuple:
        got = self._by.get((dataset_id, period or ""))
        if not got:
            return (None, None, None)
        i = bisect.bisect_right(got[0], when) - 1
        return got[1][i] if i >= 0 else (None, None, None)

    def in_warehouse(self, dataset_id, period, supply, when) -> bool:
        held_as, holder, _ = self.at(dataset_id, period, when)
        return held_as in IN_THE_WAREHOUSE and holder == supply

    def instants(self, dataset_id: str, period: str | None) -> list[datetime]:
        got = self._by.get((dataset_id, period or ""))
        return list(got[0]) if got else []

    def ever_held(self, dataset_id, period, supply, before: datetime) -> bool:
        got = self._by.get((dataset_id, period or ""))
        if not got:
            return False
        return any(t <= before and r[1] == supply and r[0] in IN_THE_WAREHOUSE
                   for t, r in zip(*got))


# ---- one entry's place, as at an instant ---------------------------------------

def _left(log, supply: str, when: datetime):
    """('turned-down' | 'replaced', the supply that replaced it) where the
    decision log has taken `supply` out by `when`, else None."""
    found = None
    for at, action, newer in log.state_instants.get(supply, ()):
        if at <= when:
            found = (action, newer)
    if found and found[0] in _LEAVES:
        return _LEAVES[found[0]], found[1]
    return None


def _reads_of(entry: dict, own_table: str) -> dict[str, dict]:
    return {t: r for t, r in (entry.get("reads") or {}).items() if t != own_table}


def place(entry: dict, *, dataset_id: str, own_table: str, period: str | None, when: datetime,
          slots: Slots, log, receipts: Receipts, held_back: dict | None,
          tables=None) -> dict:
    """The entry's cell, note and sentence on the page of the supply it is
    about (criteria 7, 8, 12 and 13), as at `when`."""
    supply = entry.get("supply_id")
    waiting_page = not slots.in_warehouse(dataset_id, period, supply, when)
    states, notes, sentences = [], [], []
    tables = hierarchy.by_table() if tables is None else tables
    for table, read in sorted(_reads_of(entry, own_table).items()):
        try:
            other = hierarchy.dataset_for_table(table, tables).dataset_id
        except Exception:  # noqa: BLE001 - not one of ours
            continue
        other_supply = read.get("supply_id") if read.get(
            "state") in (qa_store.READ, qa_store.HELD) else None
        if other_supply is None:
            states.append("none")
            notes.append([text("no "), dataset_segment(other),
                          text(f" in the warehouse for {_period(period)}")])
            sentences.append([text("Read against: no "), dataset_segment(other),
                              text(f" in place in the warehouse for {_period(period)}")])
            continue
        held_as, holder, stands_on = slots.at(other, period, when)
        left = _left(log, other_supply, when)
        if held_as in IN_THE_WAREHOUSE and holder == other_supply:
            states.append("warehouse")
            if held_as != "promoted" and stands_on:
                notes.append([*named(other, other_supply, receipts, style="note"),
                              text(f", carried forward from {_period(stands_on)}")])
                sentences.append([text("Read against the "), dataset_segment(other),
                                  text(f" in place in the warehouse for {_period(period)}, "
                                       f"carried forward from {_period(stands_on)} ("),
                                  *named(other, other_supply, receipts, style="received"),
                                  text(")")])
            else:
                notes.append(named(other, other_supply, receipts, style="note"))
                sentences.append([text("Read against the "), dataset_segment(other),
                                  text(" in place in the warehouse, "),
                                  *named(other, other_supply, receipts, style="received")])
            continue
        if left is None and slots.ever_held(other, period, other_supply, when) \
                and holder and holder != other_supply:
            left = ("replaced", holder)
        notes.append(named(other, other_supply, receipts, style="note"))
        if left is not None:
            states.append("left")
            kind, newer = left
            if kind == "turned-down":
                sentences.append([text("Read against the "), dataset_segment(other),
                                  text(" "), *named(other, other_supply, receipts,
                                                    style="received"),
                                  text(", since turned down")])
            else:
                newer = newer or holder
                tail = ([text(", since replaced in the warehouse by the one "),
                         *named(other, newer, receipts, style="received")] if newer
                        else [text(", since replaced in the warehouse")])
                sentences.append([text("Read against the "), dataset_segment(other), text(" "),
                                  *named(other, other_supply, receipts, style="received"),
                                  *tail])
            continue
        states.append("waiting")
        sentences.append([text("Read against the "), dataset_segment(other), text(" supply "),
                          *named(other, other_supply, receipts, style="received"),
                          text(", not in place in the warehouse yet")])
    if not states:
        bucket = None
    elif "left" in states:
        bucket = None
    elif all(s in ("warehouse", "none") for s in states):
        bucket = WAREHOUSE
    elif waiting_page:
        bucket = STAGED
    else:
        bucket = None
    sentence = _joined(sentences)
    recheck = _recheck_sentence(entry, held_back, receipts)
    out = {"bucket": bucket, "note": _joined(notes, "; "), "sentence": recheck or sentence}
    if recheck:
        out["recheck"] = True
    return out


def _joined(parts: list[list[dict]], sep: str = "; ") -> list[dict]:
    out: list[dict] = []
    for i, p in enumerate(parts):
        if i:
            out.append(text(sep))
        out.extend(p)
    return out


def _recheck_sentence(entry: dict, held_back: dict | None, receipts: Receipts) -> list | None:
    """A result a gate application's re-evaluation recorded (REQ-PIPE-267
    criterion 6, its run caused by 'gate:<application>'): said in its own
    sentence in place of 'Read against' (criterion 13)."""
    cause = str(entry.get("cause") or "")
    if not cause.startswith("gate:") or not held_back or not entry.get("recorded_at"):
        return None
    by, came = held_back.get("by"), held_back.get("came")
    if not by:
        return None
    by_dataset = by.split("@", 1)[0]
    reads = entry.get("reads") or {}
    try:
        table = hierarchy.dataset(by_dataset).table
    except hierarchy.UnknownDatasetError:
        return None
    read = reads.get(table) or {}
    against = read.get("supply_id") if read.get("state") in (qa_store.READ,) else None
    when = display_time.format_instant(entry["recorded_at"])
    partner = ([text(" received with this supply was held back.")] if came != "joined"
               else [text(" waiting for a decision ("), *named(by_dataset, by, receipts,
                                                              style="received"),
                     text(") is held back.")])
    if against:
        return [text(f"Re-checked {when} against the "), dataset_segment(by_dataset),
                text(" in place in the warehouse ("),
                *named(by_dataset, against, receipts, style="received"),
                text("): the "), dataset_segment(by_dataset), *partner]
    return [text(f"Could not be checked {when}: no "), dataset_segment(by_dataset),
            text(" is in place in the warehouse, and the "), dataset_segment(by_dataset),
            *(partner if came == "joined" else [text(" received with this supply was held back.")])]


class Phrases:
    """Each distinct note or sentence once per page, entries naming it by its
    index - the three tools of one check, and every day a result kept its
    place, share the same words, and the page's data is read on every date."""

    def __init__(self):
        self.items: list[list[dict]] = []
        self._index: dict[str, int] = {}

    def __call__(self, segments: list[dict]) -> int:
        import json

        key = json.dumps(segments, sort_keys=True)
        if key not in self._index:
            self._index[key] = len(self.items)
            self.items.append(segments)
        return self._index[key]


def place_entries(dataset_id: str, own_table: str, cards: list[dict],
                  period_of: dict[str, str | None], *, slots: Slots, log,
                  receipts: Receipts, phrases: Phrases | None = None) -> None:
    """Give every entry of every cross-table card on this page its `placed`
    points: [{on, bucket, note, sentence}], an answer per asset day on which
    it changed (the newest on or before the date on show is in force) - the
    note and sentence as indices into `phrases` where it is given."""
    # Read once for the page and passed down to every entry and instant
    # (REQ-PIPE-254 criterion 19).
    tables, zones = hierarchy.by_table(), asset_time.timezone_versions()
    for card in cards:
        for entry in [*card.get("history", []), *card.get("superseded", [])]:
            supply = entry.get("supply_id")
            if supply not in period_of or not entry.get("recorded_at"):
                continue
            period = period_of[supply]
            first = _instant(entry["recorded_at"])
            others = {}
            for table, read in _reads_of(entry, own_table).items():
                try:
                    others[hierarchy.dataset_for_table(table, tables).dataset_id] = \
                        read.get("supply_id")
                except Exception:  # noqa: BLE001
                    continue
            instants = {first}
            for ds in {dataset_id, *others}:
                instants |= {t for t in slots.instants(ds, period) if t > first}
            for s in [supply, *[s for s in others.values() if s]]:
                instants |= {t for t, _a, _n in log.state_instants.get(s, ()) if t > first}
            held_back = log.held_back_at(supply, first)
            points: list[dict] = []
            for when in sorted(instants):
                p = place(entry, dataset_id=dataset_id, own_table=own_table, period=period,
                          when=when, slots=slots, log=log, receipts=receipts,
                          held_back=held_back, tables=tables)
                p = {"on": asset_time.local_date(when, zones).isoformat(), **p}
                if points and points[-1]["on"] == p["on"]:
                    points.pop()
                if points and {k: v for k, v in points[-1].items() if k != "on"} == \
                        {k: v for k, v in p.items() if k != "on"}:
                    continue
                points.append(p)
            if phrases is not None:
                for p in points:
                    p["note"], p["sentence"] = phrases(p["note"]), phrases(p["sentence"])
            entry["placed"] = points


def owed_words(card: dict, log, receipts: Receipts) -> None:
    """An owed re-check's cell note and panel sentence (criteria 10 and 13),
    on each counted point that reads 'recheck-owed'."""
    for points in (card.get("counted") or {}).values():
        for p in points:
            if p.get("reason") != "recheck-owed" or p.get("owedBy") not in log.decisions:
                continue
            ds, supply, at = log.decisions[p["owedBy"]]
            p["owedNote"] = [dataset_segment(ds), text(f" promoted {display_time.format_day(at)}")]
            p["owedSentence"] = [text("Not yet re-checked against the "), dataset_segment(ds),
                                 text(f" promoted {display_time.format_instant(at)}; the "
                                      "re-check runs on the next processing pass.")]


# ---- the verdict line's warehouse clause (criteria 1 to 5) ---------------------

def clause_points(dataset_id: str, period_of: dict[str, str | None], *, timeline: dict,
                  health: dict[str, dict], run_of: dict[str, str], log,
                  receipts: Receipts) -> dict[str, list[dict]]:
    """{supply: [{on, clause, status, tail}]} - for each supply of this
    dataset, what its page's awaiting line says about the supply in place in
    the warehouse, as at each day: the supply the promotion panel names (the
    most recently promoted, REQ-DASH-197 criterion 13 - `timeline` is
    promotion_timeline.for_dataset's answer), or the one the supply's period
    stands on (criterion 4), and its status counted by REQ-PIPE-269
    (red_promoted's timeline); or that nothing is in place."""
    from datetime import date

    points_all = timeline.get("points") or []
    standing = timeline.get("standing") or []
    zones = asset_time.timezone_versions()  # once (REQ-PIPE-254 criterion 19)
    out: dict[str, list[dict]] = {}
    for supply, period in sorted(period_of.items()):
        received = receipts.at(supply)
        if not received:
            continue
        first = asset_time.local_date(_instant(received), zones).isoformat()
        # ONLY WHILE IT CAN BE AWAITING: the line is shown for a supply waiting
        # on a decision, so nothing after its first promotion or withdrawal.
        left = [asset_time.local_date(at, zones).isoformat() for at, action, _n in
                log.state_instants.get(supply, ()) if action in _ENDS_WAITING]
        last = min(left) if left else "9999-12-31"
        days = {first} | {p["on"] for p in points_all if first < p["on"] <= last} \
            | {e["on"] for e in standing if e.get("period") == period and first < e["on"] <= last}
        holders = {(p.get("promoted") or {}).get("supply") for p in points_all
                   if p["on"] <= last} | {(e.get("standingIn") or {}).get("supply")
                                         for e in standing if e.get("period") == period}
        for h in holders - {None}:
            days |= {asset_time.local_date(_instant(t["at"]), zones).isoformat()
                     for t in (health.get(run_of.get(h)) or {}).get("timeline", []) if t.get("at")
                     and first < asset_time.local_date(_instant(t["at"]), zones).isoformat() <= last}
        points: list[dict] = []
        for day in sorted(days):
            promoted = None
            for p in points_all:
                if p["on"] <= day:
                    promoted = p.get("promoted")
            stand = None
            for e in standing:
                if e.get("period") == period and e["on"] <= day:
                    stand = e.get("standingIn")
            when = asset_time.end_of_day(date.fromisoformat(day), zones)
            if stand and stand.get("supply"):
                holder, stands_on = stand["supply"], stand.get("standsOn")
                kind = stand.get("kind")
            elif promoted and promoted.get("supply"):
                holder, stands_on, kind = promoted["supply"], None, None
            else:
                holder, stands_on, kind = None, None, None
            p = {"on": day, **_clause(dataset_id, supply, holder, stands_on, when, health,
                                      run_of, receipts, kind=kind)}
            if points and {k: v for k, v in points[-1].items() if k != "on"} == \
                    {k: v for k, v in p.items() if k != "on"}:
                continue
            points.append(p)
        out[supply] = points
    return out


_ENDS_WAITING = (decision_log.PROMOTE, decision_log.REJECT, decision_log.SUPERSEDE,
                 decision_log.DEMOTE)


def _clause(dataset_id, supply, holder, stands_on, when, health, run_of, receipts,
            kind=None) -> dict:
    if not holder:
        return {"clause": [text("Nothing is in place in the warehouse for this period yet.")],
                "status": None}
    if holder == supply:
        return {"clause": None, "status": None}
    h = health.get(run_of.get(holder)) or {}
    status, since, went_red = None, None, False
    for step in h.get("timeline", []):
        if step.get("at") and _instant(step["at"]) <= when:
            if not (status == "red" and step["status"] == "red"):
                since = step
            status = step["status"]
    # AN UNKNOWN STATUS IS NOT GREEN (functional critic on 7093c20): with no
    # recorded health for the holder the clause names it and gives no status.
    status = status or h.get("promotedOn")
    promoted_at = h.get("promotedAt")
    if status == "red" and since is not None and promoted_at:
        went_red = _instant(since["at"]) <= _instant(promoted_at)
    if stands_on:
        # THE PAGE'S OWN WORD FOR IT (UX critic on 7093c20, P4, PROVISIONAL):
        # the standing-in badge says "Substituted from" for a substitution.
        how = "substituted from" if kind == "substituted" else "carried forward from"
        lead = [text(f"The supply in place in the warehouse is the one {how} "
                     f"{_period(stands_on)} ("), *named(dataset_id, holder, receipts,
                                                        style="received"), text("), and is ")]
    else:
        lead = [text("The supply in place in the warehouse is the one "),
                *named(dataset_id, holder, receipts, style="received"), text(", and is ")]
    if status is None:
        lead[-1] = text(".")
        return {"clause": lead, "status": None, "tail": []}
    if status != "red":
        tail = [text(".")]
    elif went_red or since is None:
        tail = [text(": it was promoted while red.")]
    else:
        cause = since.get("cause") or "a later check"
        by = since.get("by")
        tail = [text(f": it turned red {display_time.format_instant(since['at'])}, after "
                     f"{cause}{f' by {by}' if by else ''}.")]
    return {"clause": lead, "status": status, "tail": tail}


# ---- the supply-history row of a joint promotion (criterion 20) ---------------

def _plain_list(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def _names(segs_list: list[list[dict]]) -> list[dict]:
    """'a', 'a and b', 'a, b and c'; past three, the first two and 'and <n> more'."""
    if len(segs_list) > 3:
        rest = len(segs_list) - 2
        # THE OTHERS ON DEMAND (UX critic on 7093c20, P6 and P7): "<n> more"
        # carries every name it stands for, for the page's tooltip and its
        # accessible name.
        hidden = _plain_list([words_of(segs) for segs in segs_list[2:]])
        segs_list = segs_list[:2] + [[{"text": f"{rest} more", "more": hidden}]]
    out: list[dict] = []
    for i, segs in enumerate(segs_list):
        if i:
            out.append(text(" and " if i == len(segs_list) - 1 else ", "))
        out.extend(segs)
    return out


def _order(dataset_id: str) -> int:
    ids = [d.dataset_id for d in hierarchy.all_datasets()]
    return ids.index(dataset_id) if dataset_id in ids else len(ids)


def promotion_words(dataset_id: str, period_of: dict[str, str | None], *, log, slots: Slots,
                    receipts: Receipts, runs: dict[str, list[dict]],
                    related: set[str] | None = None) -> dict[str, list[dict]]:
    """{decision id: segments} for each rule promotion of this dataset's
    supplies that was made with others in one gate application, or after a
    re-check against the warehouse because a supply received with it was held
    back. `runs` is {supply: [its runs' facts]}, each with a `cause`;
    `related` the datasets this dataset's cross-table checks are between -
    the re-check read one of those, never another held supply of the
    application (functional critic on 7093c20, D3)."""
    out: dict[str, list[dict]] = {}
    for supply in period_of:
        for decision_id, at, kind, with_, application in log.promotes.get(supply, ()):
            if kind != decision_log.RULE:
                continue
            when = display_time.format_instant(at)
            rechecked = application is not None and any(
                str(r.get("cause")) == f"gate:{application}" for r in runs.get(supply, ()))
            held = [s for _d, s in log.withheld_in.get(application, ()) if s != supply
                    and (related is None or s.split("@", 1)[0] in related)] \
                if application is not None else []
            if rechecked and held:
                by = held[0]
                by_ds = by.split("@", 1)[0]
                in_place = slots.at(by_ds, period_of[supply], _instant(at))[1]
                out[str(decision_id)] = [
                    text(f"Promoted {when} by the rule, re-checked against the "),
                    dataset_segment(by_ds), text(" in place in the warehouse ("),
                    *named(by_ds, in_place, receipts, style="received"),
                    text(") because the "), dataset_segment(by_ds),
                    text(" received with it was held back.")]
            elif with_:
                # SHORT ON THE ROW (UX critic on 7093c20, P6): a supply received
                # with this one is named without its receipt, as "of its
                # delivery"; one received apart keeps it.
                mine = receipts.at(supply)
                together = [s for s in with_ if s != supply and receipts.at(s) == mine]
                apart = [s for s in with_ if s != supply and receipts.at(s) != mine]
                others = [[dataset_segment(s.split("@", 1)[0])] for s in sorted(
                    together, key=lambda s: _order(s.split("@", 1)[0]))]
                words = [text(f"Promoted {when} with ")]
                if others:
                    words += [text("the "), *_names(others),
                              text(" supply of its delivery" if len(others) == 1
                                   else " supplies of its delivery")]
                for i, s in enumerate(apart):
                    words += [text(" and the " if others or i else "the "),
                              dataset_segment(s.split("@", 1)[0]), text(" supply "),
                              *named(s.split("@", 1)[0], s, receipts, style="received")]
                if others or apart:
                    out[str(decision_id)] = words + [text(", by the rule")]
    return out
