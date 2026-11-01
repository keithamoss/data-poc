"""THE GENERATION-TIME TRIAL IN A SLOT'S PERIOD (REQ-GEN-298 criteria 10 to 15).

REQ-GEN-186's trial runs the four real tools over a supply the generator has
just written, before anything is kept, and compares the verdict with what the
supply was built to. For a collection whose checks read ANOTHER collection's
tables - Linkage Products' geocoding checks read the Client Register and ED
Presentations - a trial with no period cannot evaluate those reads, nor the
census-year checks, whose declared set is the period's. So such a trial runs
IN THE PERIOD OF THE SLOT the generator built the supply for:

- the tried supply is staged in the trial's own scope (qa_tools/common/trial.py)
  from the generator's just-written file, and its reference beside it;
- for each other collection's table its checks read, ONLY the source supply
  the generator's plan promotes into that period before the tried supply's
  receipt is staged, from the generator's own file, into the same scope - and
  nothing where the plan promotes none (criterion 11);
- the run's view schema is built for that period through period_overlay's
  trial branch, which reads nothing of the real database's period or staging
  schemas, with the declared set in force for the period (REQ-QAC-297);
- the results are judged by target_agreement.compare over own_results and by
  the trial's own rule, trial_reads_agree (criterion 15);
- and everything the trial staged goes when it ends: it records and files
  nothing (REQ-PIPE-079 criterion 9 as amended by A6).

ONE PROCESS PER TRIAL, IN PARALLEL (criterion 13): the four tools keep
process-wide state (bootstrap._run_concurrently gives the reasons), and each
trial's own id keeps its trial schemas, its dbt schemas and its dbt target
path apart from every other. SPAWNED, each handed the asset first.

Lives in cli/ because what it tries comes from the generator's own record
(generator/targets.py), which no pipeline, QA or dashboard-build module may
read (REQ-GEN-043 criterion 7).
"""
from __future__ import annotations

import os
import time

#: Who a trial's results say ran it - recorded nowhere, since a trial
#: records nothing.
RUN_BY = "target-trial"


def spec_of(one, written_to) -> dict:
    """What a spawned trial needs, as plain values: the tried supply's own
    file, its reference's, its period and receipt, and each source table's
    file or None (criterion 12 - from the supply's own record, never from the
    command's one dataset)."""
    from generator import targets
    from qa_tools.common import asset_time, hierarchy

    from datetime import date

    received = one.received_at or asset_time.isoformat(
        asset_time.start_of_day(date.fromisoformat(one.day)))
    sources = []
    for table, dataset_id, deliveries, at in one.sources:
        csv = None
        if deliveries:
            # THE ONE DELIVERY RECEIVED THEN THAT HOLDS THE DATASET'S FILE.
            held = []
            for name in deliveries:
                try:
                    held.append(targets.csv_of(name, written_to, dataset_id=dataset_id))
                except ValueError:
                    continue
            if len(held) != 1:
                raise ValueError(f"{one.label}: {len(held)} of the deliveries received at {at} "
                                 f"({', '.join(deliveries)}) hold a file for {dataset_id}, not "
                                 f"one")
            csv = str(held[0])
        sources.append({"table": table, "dataset_id": dataset_id, "received_at": at,
                        "csv": csv})
    return {"label": one.label, "dataset_id": one.dataset_id, "target": one.target,
            "rules": list(one.rules), "period": one.period, "received_at": received,
            "aimed": list(one.rules) if one.scenario else [],
            "table": hierarchy.dataset(one.dataset_id).table,
            "csv": str(targets.csv_of(one.delivery, written_to, one.filename,
                                      dataset_id=one.dataset_id)),
            "reference_csv": str(targets.csv_of(one.reference, written_to, one.filename,
                                                dataset_id=one.dataset_id)),
            "sources": sources}


def try_in_period(collection_id: str, spec: dict) -> list:
    """One trial in its slot's period (criteria 10 and 11). Returns its
    disagreements - none where the real tools read it as built."""
    from cli import common
    from qa_tools.common import asset_time, hierarchy, period_overlay, run_reads
    from qa_tools.common import supply_db, target_agreement, trial
    from qa_tools.tools import orchestrate, stage

    run_id = trial.trial_run_id()
    reference = common.reference_run_id()
    received = asset_time.parse_instant(spec["received_at"], spec["label"])
    reads = run_reads.reads_for(collection_id)
    supplied: dict[str, str | None] = {}
    try:
        stage.stage_table(collection_id, run_id, spec["table"], spec["csv"],
                          received_at=received)
        for source in spec["sources"]:
            physical = None
            if source["csv"]:
                owner = hierarchy.dataset(source["dataset_id"]).collection_id
                physical = stage.stage_table(
                    owner, run_id, source["table"], source["csv"],
                    received_at=asset_time.parse_instant(source["received_at"],
                                                         source["dataset_id"]))
            supplied[source["table"]] = physical
        stage.stage_table(collection_id, reference, spec["table"], spec["reference_csv"])
        period_overlay.rebuild_for_trial(
            run_id, period=spec["period"], own_table=spec["table"],
            arrival_key=supply_db.arrival_segment(received), tables=reads.tables,
            trial_supplied={t: supplied.get(t) for t in reads.foreign})
        entry = {"run_id": run_id, "run_index": 1, "delivery": run_id,
                 "received_at": asset_time.isoformat(received)}
        results = orchestrate.run_one(collection_id, entry, asset_time.now().isoformat(),
                                      RUN_BY, reference)
    finally:
        # run_one discards the trial's own schemas; one that failed before
        # reaching it is discarded here, and the reference always is.
        orchestrate.discard_run_schemas(run_id)
        common.discard_reference(reference)
    found = []
    own = target_agreement.compare(spec["dataset_id"], target_agreement.own_results(results),
                                   spec["target"], spec["label"], spec["rules"])
    if own:
        found.append(own)
    reads_out = target_agreement.trial_reads_agree(
        spec["dataset_id"], results,
        staged=[t for t, physical in supplied.items() if physical],
        unstaged=[t for t, physical in supplied.items() if not physical],
        label=spec["label"])
    if reads_out:
        found.append(reads_out)
    if spec.get("aimed"):
        # A NAMED SCENARIO MOVES NO CHECK IT IS NOT AIMED AT (criterion 7).
        moved = target_agreement.unaimed(spec["dataset_id"], results, spec["aimed"],
                                         spec["label"])
        if moved:
            found.append(moved)
    return found


def workers_for(n: int) -> int:
    """One worker per core, never more than there are trials (criterion 13,
    PROPOSED: one per core)."""
    return max(1, min(n, os.cpu_count() or 1))


def try_all(collection_id: str, specs: list[dict], say=None) -> tuple[list, float, int]:
    """Every trial, in parallel; (disagreements, wall-clock seconds, workers).
    REFUSAL WAITS FOR ALL OF THEM (criterion 13), so it names every
    disagreement at once: an exception in one trial is reported as that
    trial's disagreement, never as the end of the others."""
    say = say or (lambda _m: None)
    started = time.monotonic()
    workers = workers_for(len(specs))
    found: list = []
    if workers <= 1:
        for spec in specs:
            say(f"Trying {spec['label']} against the real tools in {spec['period']} "
                f"(built to {spec['target']})")
            found += _guarded(collection_id, spec)
        return found, time.monotonic() - started, workers
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor

    from qa_tools.common import assets

    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=workers, mp_context=context,
                             initializer=assets.select,
                             initargs=(assets.selected().name,)) as pool:
        futures = [(spec, pool.submit(_guarded, collection_id, spec)) for spec in specs]
        for spec, future in futures:
            say(f"Trying {spec['label']} against the real tools in {spec['period']} "
                f"(built to {spec['target']})")
            try:
                found += future.result()
            except Exception as exc:  # noqa: BLE001 - a lost worker is that trial's disagreement
                from qa_tools.common import target_agreement

                found.append(target_agreement.ReadDisagreement(
                    spec["label"], spec["dataset_id"],
                    (f"the trial's worker was lost ({type(exc).__name__}: {exc})",)))
    return found, time.monotonic() - started, workers


def _guarded(collection_id: str, spec: dict) -> list:
    """try_in_period, with a trial that could not run reported as a
    disagreement naming it rather than raised past the others."""
    from qa_tools.common import target_agreement

    try:
        return try_in_period(collection_id, spec)
    except Exception as exc:  # noqa: BLE001 - every trial is waited for, then refused
        return [target_agreement.ReadDisagreement(
            spec["label"], spec["dataset_id"],
            (f"the trial could not run ({type(exc).__name__}: {exc})",))]
