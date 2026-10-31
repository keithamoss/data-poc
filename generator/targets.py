"""What each generated supply was BUILT TO, for REQ-GEN-186's two checks.

The generator aims some supplies at a verdict (REQ-GEN-184, REQ-GEN-185):
an injected arrival with a target, the green lead-in and following days
around it, and every ordinary amber in both collections. This module says
which supplies those are and what each was aimed at - read from the
generator's own two records, its bookkeeping and the scenario placements,
and from nothing else. It never says what a supply SCORED: that is the
real tools' answer, compared by qa_tools/common/target_agreement.py
(criterion 4 - no predicted verdict of the generator's own).

WHY HERE AND NOT IN qa_tools: the bookkeeping is the generator's, and no
pipeline, QA or dashboard-build module may read it (REQ-GEN-043 criterion
7). The comparison receives these expectations as plain values; it never
opens the file.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from qa_tools.common import asset_time, delivery


@dataclass(frozen=True)
class Built:
    """One supply and what it was built to."""

    #: Who wants it: the scenario and arrival, or the ordinary period.
    label: str
    dataset_id: str
    delivery: str
    target: str
    #: The rules the target named, for a failure message.
    rules: tuple[str, ...] = ()
    #: An injected target's own scenario, and the delivery its trial is
    #: measured against - the last lead-in (REQ-GEN-185 criterion 2).
    scenario: str | None = None
    reference: str | None = None
    injected: bool = False
    #: The day it was built for - its trial is checked on it, so freshness
    #: reads the supply as the replay will.
    day: str | None = None
    #: One file of a two-file delivery (REQ-GEN-196 criterion 19): a pair's
    #: two supplies share a delivery, so the file is part of the key.
    filename: str | None = None


def _read(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return {}


def written(bookkeeping: Path | None = None, placements: Path | None = None) -> list[Built]:
    """Every supply the last generation built to a target, oldest first
    within each collection."""
    from generator import collections
    from qa_tools.common import scenario_map

    # READ AT CALL TIME, from the modules whose paths a test or a corpus
    # redirects (tests/equiv_support.apply_redirects) - the same two the
    # scenario map reads.
    book = _read(bookkeeping or delivery.BOOKKEEPING_PATH)
    placed = (_read(placements or scenario_map.PLACEMENTS_PATH).get("placements") or [])
    out: list[Built] = []
    # WHOSE BOOKKEEPING IS WHOSE, from the providers (REQ-GEN-246 criterion
    # 6): a key no provider makes is refused by name, where it used to be
    # read as Child Protection's. The collections that trial their targets
    # first, as before, then the rest in the order they were written.
    owners = {}
    for key in book:
        try:
            owners[key] = collections.for_dataset(key)
        except collections.NoProviderError as exc:
            raise ValueError(f"the generator's record holds supplies for {key}, which no "
                             f"provider makes: {exc}") from None
    for key in sorted(book, key=lambda k: not owners[k].target_trial):
        if owners[key].target_trial:
            out += _trialled(key, book[key], placed)
        else:
            ambers = [e for e in book[key] if e.get("dirty_severity") == "amber"]
            # AN AMBER COMPARED UNDER NO DATASET IS A DISAGREEMENT NOBODY CAN
            # READ (post-build-review #248), so a provider that builds one
            # without naming where it lands is refused here.
            if ambers and not owners[key].amber_dataset:
                raise ValueError(f"{owners[key].collection_id} built ordinary ambers but "
                                 f"its provider declares no amber_dataset to compare them in")
            out += [Built(f"the ordinary amber for {entry['period']}", owners[key].amber_dataset,
                          entry["delivery"], "amber")
                    for entry in ambers]
    return out


def _trialled(dataset_id: str, entries: list[dict], placed: list[dict]) -> list[Built]:
    """A target-trial collection's ordinary ambers, then every day its
    scenarios built green or to a target."""
    out: list[Built] = []
    by_period: dict[str, list[dict]] = {}
    for entry in entries:
        by_period.setdefault(entry["period"], []).append(entry)
    for entry in entries:
        if entry.get("dirty_severity") == "amber":
            out.append(Built(f"the ordinary amber for {entry['period']}", dataset_id,
                             entry["delivery"], "amber", day=entry["period"]))
    for record in placed:
        # EVERY DAY BUILT GREEN, targeted placement or not (post-build-review
        # #172): TS-73's green following day has no target of its own and
        # read red on the page with nothing to say so.
        if record.get("dataset") != dataset_id or not (
                record.get("targets") or record.get("lead_in") or record.get("follow")):
            continue
        scenario = record["scenario_id"]
        lead_in = record.get("lead_in") or []
        reference = _only(by_period, lead_in[-1], scenario)["delivery"] if lead_in else None
        for period in (*lead_in, *(record.get("follow") or [])):
            role = "lead-in" if period in lead_in else "following day"
            out.append(Built(f"{scenario}'s green {role} {period}", dataset_id,
                             _only(by_period, period, scenario)["delivery"], "green",
                             scenario=scenario, day=period))
        for target in record.get("targets") or ():
            if target.get("filename"):
                # A PAIR'S FILE, keyed by its delivery and filename, on the
                # day its extract is for (REQ-GEN-196 criterion 19).
                out.append(Built(f"{scenario}'s {target['filename']}", dataset_id,
                                 target["delivery"], target["built_to"],
                                 rules=tuple(target.get("rules") or ()), scenario=scenario,
                                 reference=reference, injected=True, day=target["day"],
                                 filename=target["filename"]))
                continue
            entry = _arriving_at(by_period, target["date"], target["at"], scenario)
            out.append(Built(f"{scenario}'s {target['date']} {target['at']} arrival",
                             dataset_id, entry["delivery"], target["built_to"],
                             rules=tuple(target.get("rules") or ()), scenario=scenario,
                             reference=reference, injected=True, day=target["date"]))
    return out


def just_written() -> tuple[list[Built], Path]:
    """What the generator has just written and where: the shared driver's
    own path constants - which is what a test redirects - never the
    pipeline's view of data/. For the generation-time trial (REQ-GEN-186
    criterion 1), which lives in cli/ and so may not name the bookkeeping
    itself (REQ-GEN-043 criterion 7)."""
    from generator import driver, scenario_injection

    return (written(driver.BOOKKEEPING_PATH, scenario_injection.PLACEMENTS_PATH),
            Path(driver.DELIVERIES_DIR))


def _only(by_period: dict, period: str, scenario: str) -> dict:
    entries = by_period.get(period) or []
    if len(entries) != 1:
        raise ValueError(f"{scenario}: the generator's record holds {len(entries)} supplies "
                         f"for its green period {period}, where it built exactly one")
    return entries[0]


def _arriving_at(by_period: dict, day: str, at: str, scenario: str) -> dict:
    for entry in by_period.get(day) or []:
        local = asset_time.parse_instant(entry["received_at"], entry["run_id"])
        if asset_time.localise(local).strftime("%H:%M") == at:
            return entry
    raise ValueError(f"{scenario}: the generator's record holds no supply arriving "
                     f"{day} {at}, where its placement says one was built")


def csv_of(delivery_name: str, deliveries_dir: Path | None = None,
           filename: str | None = None) -> Path:
    """A Birth Registrations delivery's one file - or, for one file of a
    two-file delivery (REQ-GEN-196), the file named."""
    folder = Path(deliveries_dir or delivery.DELIVERIES_DIR, delivery_name)
    if filename is not None:
        path = folder / filename
        if not path.is_file():
            raise ValueError(f"delivery {delivery_name} holds no file {filename}")
        return path
    files = sorted(folder.glob("*.csv"))
    if len(files) != 1:
        raise ValueError(f"delivery {delivery_name} holds {len(files)} CSV files, not one")
    return files[0]


@dataclass(frozen=True)
class DeclaredGateOutcome:
    """What a scripted scenario declares the package gate does with one of
    its supplies (REQ-GEN-273 criterion 3): promoted, or held back - and
    where held back, because of which other supply's dataset, and whether
    after a re-check against the warehouse. A declaration, never a predicted
    verdict (REQ-GEN-186 criterion 4): it pins the GATE's decision."""
    scenario: str
    dataset_id: str
    delivery: str
    outcome: str
    because: str | None = None
    rechecked: bool = False


def gate_outcomes(placements: Path | None = None) -> list[DeclaredGateOutcome]:
    """Every gate outcome the last generation's placements declare."""
    from qa_tools.common import scenario_map

    placed = (_read(placements or scenario_map.PLACEMENTS_PATH).get("placements") or [])
    return [DeclaredGateOutcome(scenario=p["scenario_id"], dataset_id=g["dataset_id"],
                                delivery=g["delivery"], outcome=g["outcome"],
                                because=g.get("because"), rechecked=bool(g.get("rechecked")))
            for p in placed for g in (p.get("gate_outcomes") or [])]
