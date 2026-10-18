"""WHAT A DECLARED CORRECTION CLAIMS (REQ-GEN-205 criteria 10 and 18,
REQ-GEN-237 criterion 3), checked before anything is written.

A correction that alters a period's slot claims that period with the one
before and the one after, ONCE however many scenarios ride it. A scenario
that rides it (Injection.correction) may sit inside the claim; any other
scenario claiming one of those periods is refused naming both, never shifted.
Every altered period must hold no supply in any collection no riding
scenario is in - it lies outside that collection's history or its routine
supply is suppressed there. And a correction dated after the history, or
altering a period the riding scenario's dataset never generates, is refused
naming the scenario and the change reference.

From configuration alone: the agreement as it stood just before the
correction's date and as it stood from it (correction_replay.docs_at).
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Mapping, Sequence

from generator.scenario_injection import CannotPlace


def _docs_either_side(reference: str, docs):
    from qa_tools.common import correction_apply, correction_replay, correction_trial

    docs = docs or correction_trial.working()
    p = next((p for p in correction_apply._declared(*docs) if p.reference == reference), None)
    if p is None:
        return None, None, None
    at = correction_replay.merge_instant(p)
    return (p, correction_replay.docs_at(at - timedelta(microseconds=1), docs),
            correction_replay.docs_at(at, docs))


def _slots(dataset_id: str, cal: dict, until: date) -> dict:
    from qa_tools.common import agreement, slots

    from qa_tools.common import schedule

    agr = agreement.from_doc(cal)
    try:
        found = slots.slots_for_dataset(dataset_id, until=until, agreement=agr)
    except (schedule.ScheduleConfigError, LookupError):
        # A DATASET ON NO CALENDAR has no slot a correction could alter.
        return {}
    return {s.name: (s.date, s.due_at, s.grace, s.claim_opens_at, s.closes_at) for s in found}


def _history_end() -> date:
    from generator.anchor_date import get_anchor_date

    return get_anchor_date()


def altered(reference: str, datasets: Sequence[str], *, docs=None,
            until: date | None = None) -> dict[str, set[str]]:
    """Each dataset's periods whose slot the correction alters, up to `until`
    (default the generated history's end)."""
    until = until or _history_end()
    p, before, after = _docs_either_side(reference, docs)
    if p is None:
        raise CannotPlace(f"{reference!r} is not a declared correction - declare it in "
                          f"contract/calendar.yaml first")
    out: dict[str, set[str]] = {}
    for dataset_id in datasets:
        old, new = _slots(dataset_id, before[0], until), _slots(dataset_id, after[0], until)
        changed = {name for name in old.keys() | new.keys() if old.get(name) != new.get(name)}
        if changed:
            out[dataset_id] = changed
    return out


def claimed(reference: str, generated: Mapping[str, Sequence], *,
            docs=None, changed: Mapping[str, set[str]] | None = None) -> dict[str, list[str]]:
    """Each dataset's claimed periods: every altered one (or, given
    `changed`, every one named there) with its neighbours, among the periods
    generated for it, oldest first."""
    out: dict[str, list[str]] = {}
    if changed is None:
        changed = altered(reference, list(generated), docs=docs)
    for dataset_id, names in changed.items():
        if dataset_id not in generated:
            continue
        order = [p.name for p in generated[dataset_id]]
        keep = set()
        for i, name in enumerate(order):
            if name in names:
                keep.update(order[max(0, i - 1):i + 2])
        if keep:
            out[dataset_id] = [n for n in order if n in keep]
    return out


def _collection_of(dataset_id: str) -> str:
    from qa_tools.common import hierarchy

    try:
        return hierarchy.dataset(dataset_id).collection_id
    except hierarchy.UnknownDatasetError:
        return dataset_id


def check(injections: Sequence, generated: Mapping[str, Sequence], *, docs=None,
          history_end: date, suppressed: Mapping[str, set[str]] | None = None) -> None:
    """Refuse, naming what to change, before anything is written."""
    from generator import scenario_injection as si

    suppressed = {k: set(v) for k, v in (suppressed or {}).items()}
    for inj in injections:
        if inj.dataset_id in generated:
            placement = si.resolve(si.dataclasses.replace(inj, links=()),
                                   generated[inj.dataset_id])
            suppressed.setdefault(inj.dataset_id, set()).update(placement.suppressed)
    riders: dict[str, list] = {}
    for inj in injections:
        if inj.correction:
            riders.setdefault(inj.correction, []).append(inj)
    for reference, riding in riders.items():
        p, _before, _after = _docs_either_side(reference, docs)
        names = ", ".join(i.scenario_id for i in riding)
        if p is None:
            raise CannotPlace(f"{names} ride {reference!r}, which is not a declared "
                              f"correction - declare it in contract/calendar.yaml first")
        if date.fromisoformat(p.date[:10]) > history_end:
            raise CannotPlace(f"{names}: correction {reference} is dated {p.date}, after the "
                              f"generated history ends ({history_end}) - move its date "
                              f"inside the history")
        if is_version_level(reference, docs=docs):
            # ONLY THE FILINGS IT CHANGES (criterion 10's narrowing): every
            # injected arrival's instant, by the filing rule's own function.
            # Ordinary arrivals are checked once written (check_written).
            instants = _injected_instants(injections, generated)
            changed = {d: filing_changes(reference, d, at, docs=docs, until=history_end)
                       for d, at in instants.items()}
            changed = {d: v for d, v in changed.items() if v}
        else:
            changed = altered(reference, list(generated), docs=docs, until=history_end)
        riding_sets = {i.dataset_id for i in riding}
        riding_collections = {_collection_of(d) for d in riding_sets}
        for inj in riding:
            have = {q.name for q in generated[inj.dataset_id]}
            outside = sorted(changed.get(inj.dataset_id, set()) - have)
            if outside:
                raise CannotPlace(f"{inj.scenario_id}: correction {reference} alters "
                                  f"{', '.join(outside)} of {inj.dataset_id}, outside its "
                                  f"generated history - grow the history or move the change")
        for dataset_id, periods in sorted(changed.items()):
            if _collection_of(dataset_id) in riding_collections:
                continue
            held = sorted(set(periods) & {q.name for q in generated[dataset_id]}
                          - suppressed.get(dataset_id, set()))
            if held:
                raise CannotPlace(
                    f"correction {reference} alters {', '.join(held)}, where "
                    f"{_collection_of(dataset_id)} ({dataset_id}) holds a supply - a quarter "
                    f"a correction alters must lie outside that collection's history or have "
                    f"its routine supply suppressed")
        claim = claimed(reference, {d: generated[d] for d in riding_sets}, docs=docs,
                        changed=changed)
        # BY COLLECTION, NOT DATASET: a collection delivering every table
        # together has one delivery a period, so a claim on one dataset's
        # period is a claim on that period's delivery.
        by_collection: dict[str, set[str]] = {}
        for dataset_id, names_claimed in claim.items():
            by_collection.setdefault(_collection_of(dataset_id), set()).update(names_claimed)
        for inj in injections:
            wanted = by_collection.get(_collection_of(inj.dataset_id))
            if inj.correction == reference or not wanted or inj.dataset_id not in generated:
                continue
            mine = set(si.claimed_periods(inj, generated[inj.dataset_id]))
            met = sorted(mine & wanted)
            if met:
                raise CannotPlace(
                    f"{inj.scenario_id} and correction {reference} (ridden by {names}) both "
                    f"need {', '.join(met)} of {inj.dataset_id} - move one")


def check_all() -> None:
    """Every injection against every collection's generated periods - the
    driver's check before it writes anything."""
    from generator import collections, scenario_injection
    from generator.anchor_date import get_anchor_date
    from qa_tools.common import hierarchy

    if not any(i.correction for i in scenario_injection.INJECTIONS):
        return
    generated, suppressed = {}, {}
    for d in hierarchy.all_datasets():
        try:
            provider = collections.for_dataset(d.dataset_id)
        except collections.NoProviderError:
            continue
        generated[d.dataset_id] = provider.generated_periods()
        if provider.suppresses_others_corrections:
            suppressed[d.dataset_id] = foreign_altered(d.collection_id)
    check(scenario_injection.INJECTIONS, generated, history_end=get_anchor_date(),
          suppressed=suppressed)
    check_version_after(scenario_injection.INJECTIONS,
                        last_link_day=last_req_gen_199_link_day())


#: REQ-GEN-205 criterion 25: TS-47's following day, the last day its
#: four-hour claim window has to stand under the version before TS-62's.
TS47_FOLLOWING_DAY = date(2026, 9, 8)
#: The scenarios REQ-GEN-199 planted, whose quoted texts stand under that
#: version too (TS-75 to TS-79, lettered or not).
_REQ_GEN_199 = re.compile(r"TS-7[5-9][a-z]?$")


def added_versions(reference: str, *, docs=None) -> list[date]:
    """The effective dates of every calendar version the correction adds -
    those present just after its date and not just before it."""
    p, before, after = _docs_either_side(reference, docs)
    if p is None:
        raise CannotPlace(f"{reference!r} is not a declared correction")

    def versions(cal):
        return {(c.get("name"), str(v.get("effective_from")))
                for c in cal.get("calendars") or [] for v in c.get("versions") or []}

    return sorted(date.fromisoformat(day[:10])
                  for _name, day in versions(after[0]) - versions(before[0]))


def last_req_gen_199_link_day() -> date | None:
    """The last day any REQ-GEN-199 scenario link names, through the one
    link resolver the generator writes with (REQ-GEN-201 criterion 9)."""
    from generator import scenario_injection as si

    days = []
    for inj in si.INJECTIONS:
        if not inj.links:
            continue
        placement = si.resolve(si.dataclasses.replace(inj, links=()),
                               si.generated_periods(inj.dataset_id))
        days += [d.on for d in si.link_dates(inj, placement)
                 if d.on and _REQ_GEN_199.match(d.scenario_id)]
    return max(days, default=None)


def check_version_after(injections: Sequence, *, docs=None,
                        last_link_day: date | None) -> None:
    """REQ-GEN-205 criterion 25: TS-62's version takes effect after
    2026-09-08 and after the last day a REQ-GEN-199 link names, so that
    TS-47's window and every text REQ-GEN-199 quotes stand under the version
    before it. Refused naming TS-62, never shifted."""
    ts62 = next((i for i in injections if i.scenario_id == "TS-62"), None)
    if ts62 is None or not ts62.correction:
        return
    added = added_versions(ts62.correction, docs=docs)
    if not added:
        raise CannotPlace(f"TS-62: correction {ts62.correction} adds no calendar version - "
                          f"it must add the wider claim window as a new version")
    bounds = [(TS47_FOLLOWING_DAY, "TS-47's following day")]
    if last_link_day is not None:
        bounds.append((last_link_day, "the last day a REQ-GEN-199 link names"))
    for day in added:
        for bound, what in bounds:
            if day <= bound:
                raise CannotPlace(
                    f"TS-62: correction {ts62.correction}'s version takes effect on "
                    f"{day.isoformat()}, on or before {bound.isoformat()} ({what}) - "
                    f"move the version later; it is never shifted")


def _datasets_of(collection_id: str) -> list[str]:
    from qa_tools.common import hierarchy

    return [d.dataset_id for d in hierarchy.all_datasets() if d.collection_id == collection_id]


def foreign_altered(collection_id: str, *, docs=None) -> set[str]:
    """The periods of `collection_id` that a correction ridden only by OTHER
    collections' scenarios alters (REQ-GEN-237 criterion 3) - where its
    routine supply is suppressed, so the corrected quarters hold no supply of
    its own."""
    from generator import scenario_injection

    mine = set(_datasets_of(collection_id))
    riders: dict[str, set[str]] = {}
    for inj in scenario_injection.INJECTIONS:
        if inj.correction:
            riders.setdefault(inj.correction, set()).add(inj.dataset_id)
    out: set[str] = set()
    for reference, datasets in riders.items():
        if datasets & mine:
            continue
        for names in altered(reference, sorted(mine), docs=docs).values():
            out |= names
    return out


def is_version_level(reference: str, *, docs=None) -> bool:
    """Whether every change a correction declares is to a whole calendar or
    participation version (a claim window, a due time) rather than to one
    period's date - TS-62's kind, which claims only the filings it changes."""
    p, _before, _after = _docs_either_side(reference, docs)
    if p is None:
        raise CannotPlace(f"{reference!r} is not a declared correction")
    return bool(p.changes) and all(" period " not in item for item, _o, _n in p.changes)


def filing_changes(reference: str, dataset_id: str, instants, *, docs=None,
                   until: date | None = None) -> set[str]:
    """The periods whose filing the correction changes for arrivals at
    `instants`: each instant's open slot before and after it, by the filing
    rule's own function (assignment.open_slot, as the impact trial uses -
    REQ-PIPE-169 criterion 6), both named where they differ."""
    from qa_tools.common import agreement, assignment, slots

    p, before, after = _docs_either_side(reference, docs)
    if p is None:
        raise CannotPlace(f"{reference!r} is not a declared correction")
    instants = list(instants)
    if not instants:
        return set()
    horizon = until or max(i.date() for i in instants) + timedelta(days=2)
    old = slots.slots_for_dataset(dataset_id, until=horizon,
                                  agreement=agreement.from_doc(before[0]))
    new = slots.slots_for_dataset(dataset_id, until=horizon,
                                  agreement=agreement.from_doc(after[0]))
    out: set[str] = set()
    for at in instants:
        was, now = assignment.open_slot(old, at), assignment.open_slot(new, at)
        was_name, now_name = (was.name if was else None), (now.name if now else None)
        if was_name != now_name:
            out |= {n for n in (was_name, now_name) if n}
    return out


def _injected_instants(injections, generated) -> dict[str, list]:
    """Each dataset's injected arrival instants, from configuration."""
    from generator import scenario_injection as si
    from qa_tools.common import asset_time

    out: dict[str, list] = {}
    for inj in injections:
        if inj.dataset_id not in generated:
            continue
        placement = si.resolve(si.dataclasses.replace(inj, links=()), generated[inj.dataset_id])
        out.setdefault(inj.dataset_id, []).extend(
            asset_time.wall_clock(date.fromisoformat(a["date"]), a["at"])
            for a in placement.arrivals)
    return out


def _carries(entry, dataset_id) -> bool:
    """Whether a written arrival carries the dataset: by the tables its entry
    counts, or every dataset where it counts none. An arrival that does not
    carry a dataset has no filing of it for a correction to change."""
    counts = entry.get("row_counts")
    if not counts:
        return True
    from qa_tools.common import hierarchy

    return hierarchy.dataset(dataset_id).table in counts


def _on_a_calendar(dataset_id: str) -> bool:
    """A DATASET ON NO CALENDAR has no filing a correction could change - as
    _slots() says of its slots."""
    from qa_tools.common import schedule, slots

    try:
        slots.slots_for_dataset(dataset_id, until=_history_end())
    except (schedule.ScheduleConfigError, LookupError):
        return False
    return True


def check_written(dataset_ids, entries, injected_periods=frozenset(), *, docs=None) -> None:
    """After the deliveries are written: no ORDINARY arrival's filing may be
    changed by a version-level correction (REQ-GEN-205 criterion 10, REQ-GEN-237
    criterion 4) - only a scenario's may, and those are its riders' own,
    already checked from configuration. Refused naming the run.

    ONLY AN ARRIVAL RECEIVED BEFORE THE CORRECTION'S DATE is asked
    (post-build-review #244): one received on or after it was filed under the
    corrected agreement as it arrived, so a confirmation has nothing of its to
    move. REQ-GEN-218's gap deliveries are those."""
    from generator import scenario_injection
    from qa_tools.common import asset_time

    riders = {}
    for inj in scenario_injection.INJECTIONS:
        if inj.correction:
            riders.setdefault(inj.correction, set()).add(inj.dataset_id)
    for reference, datasets in riders.items():
        if not is_version_level(reference, docs=docs):
            continue
        p, _before, _after = _docs_either_side(reference, docs)
        merged = asset_time.wall_clock(date.fromisoformat(p.date[:10]), "00:00")
        for e in entries:
            if e.get("period") in injected_periods or not e.get("received_at"):
                continue
            at = asset_time.parse_instant(e["received_at"], e["run_id"])
            if at >= merged:
                continue
            for dataset_id in dataset_ids:
                if not _carries(e, dataset_id) or not _on_a_calendar(dataset_id):
                    continue
                moved = filing_changes(reference, dataset_id, [at], docs=docs)
                if moved:
                    raise CannotPlace(
                        f"correction {reference} would change where {e['run_id']} "
                        f"({dataset_id}, an ordinary supply no scenario names) is filed - "
                        f"{', '.join(sorted(moved))}; move the correction's effective date "
                        f"or the change")
