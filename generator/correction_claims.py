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

    agr = agreement.from_doc(cal)
    return {s.name: (s.date, s.due_at, s.grace, s.claim_opens_at, s.closes_at)
            for s in slots.slots_for_dataset(dataset_id, until=until, agreement=agr)}


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
            docs=None) -> dict[str, list[str]]:
    """Each dataset's claimed periods: every altered one with its neighbours,
    among the periods generated for it, oldest first."""
    out: dict[str, list[str]] = {}
    for dataset_id, names in altered(reference, list(generated), docs=docs).items():
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
        claim = claimed(reference, {d: generated[d] for d in riding_sets}, docs=docs)
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
    generated = {}
    for d in hierarchy.all_datasets():
        try:
            generated[d.dataset_id] = collections.for_dataset(d.dataset_id).generated_periods()
        except collections.NoProviderError:
            continue
    check(scenario_injection.INJECTIONS, generated, history_end=get_anchor_date())
