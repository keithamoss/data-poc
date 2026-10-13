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

BDM_DATASET = "birth-registrations"
CP_AMBER_DATASET = "cp-clients"


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
    from qa_tools.common import scenario_map

    # READ AT CALL TIME, from the modules whose paths a test or a corpus
    # redirects (tests/equiv_support.apply_redirects) - the same two the
    # scenario map reads.
    book = _read(bookkeeping or delivery.BOOKKEEPING_PATH)
    placed = (_read(placements or scenario_map.PLACEMENTS_PATH).get("placements") or [])
    out: list[Built] = []
    bdm = book.get(BDM_DATASET, [])
    by_period: dict[str, list[dict]] = {}
    for entry in bdm:
        by_period.setdefault(entry["period"], []).append(entry)
    for entry in bdm:
        if entry.get("dirty_severity") == "amber":
            out.append(Built(f"the ordinary amber for {entry['period']}", BDM_DATASET,
                             entry["delivery"], "amber", day=entry["period"]))
    for record in placed:
        # EVERY DAY BUILT GREEN, targeted placement or not (post-build-review
        # #172): TS-73's green following day has no target of its own and
        # read red on the page with nothing to say so.
        if record.get("dataset") != BDM_DATASET or not (
                record.get("targets") or record.get("lead_in") or record.get("follow")):
            continue
        scenario = record["scenario_id"]
        lead_in = record.get("lead_in") or []
        reference = _only(by_period, lead_in[-1], scenario)["delivery"] if lead_in else None
        for period in (*lead_in, *(record.get("follow") or [])):
            role = "lead-in" if period in lead_in else "following day"
            out.append(Built(f"{scenario}'s green {role} {period}", BDM_DATASET,
                             _only(by_period, period, scenario)["delivery"], "green",
                             scenario=scenario, day=period))
        for target in record.get("targets") or ():
            if target.get("filename"):
                # A PAIR'S FILE, keyed by its delivery and filename, on the
                # day its extract is for (REQ-GEN-196 criterion 19).
                out.append(Built(f"{scenario}'s {target['filename']}", BDM_DATASET,
                                 target["delivery"], target["built_to"],
                                 rules=tuple(target.get("rules") or ()), scenario=scenario,
                                 reference=reference, injected=True, day=target["day"],
                                 filename=target["filename"]))
                continue
            entry = _arriving_at(by_period, target["date"], target["at"], scenario)
            out.append(Built(f"{scenario}'s {target['date']} {target['at']} arrival",
                             BDM_DATASET, entry["delivery"], target["built_to"],
                             rules=tuple(target.get("rules") or ()), scenario=scenario,
                             reference=reference, injected=True, day=target["date"]))
    for dataset_id, entries in book.items():
        if dataset_id == BDM_DATASET:
            continue
        for entry in entries:
            if entry.get("dirty_severity") == "amber":
                out.append(Built(f"the ordinary amber for {entry['period']}", CP_AMBER_DATASET,
                                 entry["delivery"], "amber"))
    return out


def just_written() -> tuple[list[Built], Path]:
    """What the Birth Registrations generator has just written and where:
    its own path constants - which is what a test redirects - never the
    pipeline's view of data/. For the generation-time trial (REQ-GEN-186
    criterion 1), which lives in cli/ and so may not name the bookkeeping
    itself (REQ-GEN-043 criterion 7)."""
    from generator import generate_runs, scenario_injection

    return (written(generate_runs.BOOKKEEPING_PATH, scenario_injection.PLACEMENTS_PATH),
            Path(generate_runs.DELIVERIES_DIR))


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
