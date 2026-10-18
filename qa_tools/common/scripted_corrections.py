"""SCRIPTED CORRECTION CONFIRMATIONS, played back into the synthetic history
(REQ-GEN-205 criteria 4-7). A top-level `corrections:` list in
contract/scripted_decisions.yaml, separate from its `decisions:`, says how
the asset manager confirms one declared correction: keeping named supplies
where they are, with one reason covering them, or leaving it pending.

READ ONLY BY correction_replay.confirm_due - never by the Player that plays
filing decisions, nor by filing_decisions' operation validation: a
confirmation is not a filing decision and has no time of its own (it is
confirmed when the replay confirms the due corrections). A correction with
no entry here is confirmed as it always was, moving everything it proposes.

Each kept supply is named by scenario, dataset and that scenario's supply
index, never a generated id, and resolved to its supply id exactly as a
scripted decision's is (scripted_decisions._supply_of).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from qa_tools.common import config_yaml

#: Fields a confirmation must not carry: it is timed by the replay, not by
#: an offset from a supply (criterion 5).
TIMING_FIELDS = ("after_hours", "at", "day_offset")
_KNOWN = {"change_reference", "keep", "keep_reason", "pending"}


@dataclass(frozen=True)
class Keep:
    scenario: str
    dataset_id: str
    supply_index: int | None


@dataclass(frozen=True)
class Confirmation:
    change_reference: str
    keep: tuple[Keep, ...] = ()
    keep_reason: str | None = None
    pending: bool = False
    #: Timing fields written on the entry, kept so validation can refuse them.
    timing: tuple[str, ...] = ()
    #: Any other field written, refused likewise.
    unknown: tuple[str, ...] = ()


def _path(path):
    from qa_tools.common import scripted_decisions

    return Path(path or scripted_decisions.SCRIPT_PATH)


def load(path: Path | str | None = None) -> list[Confirmation]:
    """The committed confirmations, in file order. Absent is empty."""
    p = _path(path)
    if not p.exists():
        return []
    doc = config_yaml.parse(p.read_text()) or {}
    out = []
    for raw in doc.get("corrections") or []:
        raw = raw or {}
        keeps = tuple(Keep(scenario=str((k or {}).get("scenario") or ""),
                           dataset_id=str((k or {}).get("dataset") or ""),
                           supply_index=(int(k["supply"]) if (k or {}).get("supply")
                                         is not None else None))
                      for k in raw.get("keep") or [])
        reason = raw.get("keep_reason")
        out.append(Confirmation(
            change_reference=str(raw.get("change_reference") or ""), keep=keeps,
            keep_reason=None if reason is None else str(reason),
            pending=bool(raw.get("pending", False)),
            timing=tuple(f for f in TIMING_FIELDS if f in raw),
            unknown=tuple(sorted(set(raw) - _KNOWN - set(TIMING_FIELDS)))))
    return out


def problems(confirmations: list[Confirmation], *, declared: set[str],
             injections) -> list[str]:
    """Criterion 5, from configuration alone. Each names the entry and the
    fault. `injections` is the generator's injection table, handed in by the
    caller (cli/), since no QA module may import the generator."""
    from qa_tools.common import hierarchy

    by_scenario = {}
    for inj in injections:
        for sid in (inj.scenario_id, *inj.also_demonstrates):
            by_scenario.setdefault(sid, inj)
    out: list[str] = []
    seen: dict[str, int] = {}
    for i, c in enumerate(confirmations, 1):
        where = f"contract/scripted_decisions.yaml correction {i} ({c.change_reference or '?'})"
        if c.change_reference not in declared:
            out.append(f"{where}: {c.change_reference!r} is not a declared correction - "
                       f"declare it in contract/calendar.yaml (or contract/data-asset.yaml) "
                       f"first")
        first = seen.setdefault(c.change_reference, i)
        if first != i:
            out.append(f"{where}: correction {first} already names {c.change_reference!r} - "
                       f"one confirmation per correction; merge the two")
        for field_name in c.timing:
            out.append(f"{where}: `{field_name}:` means nothing on a correction confirmation, "
                       f"which is confirmed when the replay confirms the due corrections - "
                       f"drop it")
        for field_name in c.unknown:
            out.append(f"{where}: `{field_name}:` is not a field of a correction confirmation "
                       f"- one of {', '.join(sorted(_KNOWN))}")
        if c.pending and c.keep:
            out.append(f"{where}: says both `pending: true` and `keep:` - a pending "
                       f"correction is not confirmed, so it keeps nothing; drop one")
        if not c.pending and not c.keep:
            out.append(f"{where}: keeps nothing - a confirmation with no keeps says nothing "
                       f"the default does not; give `keep:` or `pending: true`, or drop it")
        if c.keep and not (c.keep_reason or "").strip():
            out.append(f"{where}: keeps supplies with no `keep_reason:` - keeping a supply "
                       f"needs a reason, as a person's does")
        if c.keep_reason is not None and not c.keep:
            out.append(f"{where}: gives a `keep_reason:` but keeps nothing - drop it, or "
                       f"name the supplies it covers under `keep:`")
        for k in c.keep:
            what = f"{where}: keep {k.scenario or '?'} {k.dataset_id or '?'} supply {k.supply_index}"
            inj = by_scenario.get(k.scenario)
            if inj is None:
                out.append(f"{what}: scenario {k.scenario!r} is not placed by the generator")
                continue
            if k.supply_index is None:
                out.append(f"{what}: names no `supply:` - give the scenario's supply index")
            else:
                count = max(1, len(inj.arrivals))
                if not 0 <= k.supply_index < count:
                    out.append(f"{what}: {k.scenario} has {count} supply(ies) per dataset, "
                               f"indexed 0 to {count - 1}")
            try:
                carried = {d.dataset_id for d in hierarchy.all_datasets()
                           if d.collection_id == hierarchy.dataset(inj.dataset_id).collection_id}
            except hierarchy.UnknownDatasetError:
                carried = {inj.dataset_id}
            if k.dataset_id not in carried:
                out.append(f"{what}: {k.scenario}'s arrival does not carry {k.dataset_id!r} - "
                           f"one of {', '.join(sorted(carried))}")
    return out


def by_reference(confirmations: list[Confirmation]) -> dict[str, Confirmation]:
    return {c.change_reference: c for c in confirmations}


def resolve(c: Confirmation, placements=None) -> dict[tuple[str, str], Keep]:
    """Each kept supply's (dataset, supply id), from where the generator
    recorded the scenario - as scripted decisions resolve theirs."""
    from qa_tools.common import scenario_map, scripted_decisions

    placements = scenario_map.read_placements() if placements is None else placements
    out: dict[tuple[str, str], Keep] = {}
    for k in c.keep:
        placement = placements.get(k.scenario)
        if placement is None or k.supply_index is None \
                or k.supply_index >= len(placement.supplies):
            raise scripted_decisions.ScriptRefused(
                f"scripted correction {c.change_reference}: {k.scenario} has no recorded "
                f"supply {k.supply_index} - regenerate the synthetic history, or put the "
                f"script right")
        run_id = placement.supplies[k.supply_index]
        out[(k.dataset_id, scripted_decisions._supply_of(k.dataset_id, run_id))] = k
    return out


def describe_moves(moves, placements=None) -> list[str]:
    """A correction's proposed moves, each by scenario, dataset and supply
    index where a scenario names it (criterion 7), else by supply id."""
    from qa_tools.common import scenario_map, scripted_decisions

    placements = scenario_map.read_placements() if placements is None else placements
    named: dict[tuple[str, str], str] = {}
    datasets = {m.dataset_id for m in moves}
    for sid, placement in sorted(placements.items()):
        for index, run_id in enumerate(placement.supplies):
            for dataset_id in datasets:
                try:
                    supply = scripted_decisions._supply_of(dataset_id, run_id)
                except scripted_decisions.ScriptRefused:
                    continue
                named.setdefault((dataset_id, supply), f"{sid} {dataset_id} supply {index}")
    out = []
    for m in moves:
        where = named.get((m.dataset_id, m.supply_id), f"{m.dataset_id} {m.supply_id}")
        out.append(f"{where}: {m.from_period or 'held'} -> {m.to_period or 'held'}")
    return out
