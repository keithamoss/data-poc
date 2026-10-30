"""The one generator driver every collection's synthetic history goes through
(REQ-GEN-246).

WHAT IT OWNS: the slot loop, the bookkeeping, writing each arrival as a real
delivery with its receipt, and placing the injected scenarios. What it does
not own - how a collection's rows are made, its seed schedule and its period
plan - is the collection's provider's, at generator/collections/<id>.py.

THE ORDER IS THE CONTRACT, and it is the order both collections' own
generators used before they were merged here:

1. Seeds checked against the provider's declared ranges, and every scenario
   and target resolved - all BEFORE THE FIRST WRITE (REQ-GEN-044 criterion
   4; REQ-GEN-184 criterion 11), so a refusal leaves the history already on
   disk standing rather than half-replaced.
2. Each slot's arrivals BUILT, in plan order and in memory: receipt
   instant, then a delivery name (unique against what will remain on disk,
   REQ-GEN-043), then the files.
3. No two arrivals may share a receipt instant - within the collection (a
   staged table is named for its arrival, so the second would drop the
   first) or with another collection's delivery (REQ-GEN-334 criterion
   13). Refused here, still before the first write.
4. Only then is what this collection wrote last time cleared, so a
   regeneration overwrites its own history rather than accumulating beside
   it (REQ-GEN-042), and each arrival written as one directory with a
   receipt OUTSIDE it (docs/delivery-format.md).
5. The bookkeeping, then where every scenario landed, resolved against what
   RECOGNITION found on disk rather than what was meant to be written.

WHERE IT WRITES, all of it, read at call time and redirectable in one place
(generator/output.py's redirect()).
"""
from __future__ import annotations

import json
import os

from qa_tools.common import delivery

DELIVERIES_DIR = delivery.DELIVERIES_DIR
RECEIPTS_DIR = delivery.RECEIPTS_DIR
BOOKKEEPING_PATH = delivery.BOOKKEEPING_PATH


def write_bookkeeping(key: str, manifest: list[dict]) -> None:
    """The generator's own record, OUTSIDE every delivery (REQ-GEN-043
    criterion 6), under the provider's bookkeeping key.

    Which slot each delivery was built to fill, which scenario it came from,
    what severity was injected - real and worth keeping, because it is how a
    test asserts that recognition got the right answer.

    NO PIPELINE, QA OR DASHBOARD-BUILD MODULE MAY READ IT (criterion 7). One
    that did would be making filing decisions from a declaration rather than
    from arrival plus slot state. The generator reads it back for two
    purposes only: to delete what it wrote last time, and to say what each
    supply was built to (generator/targets.py, REQ-GEN-186)."""
    path = BOOKKEEPING_PATH
    book = {}
    if path.exists():
        with open(path) as f:
            book = json.load(f)
    book[key] = manifest
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(book, f, indent=2)


def previous_delivery_names(key: str) -> list[str]:
    """What the collection keyed `key` wrote last time, from the bookkeeping."""
    path = BOOKKEEPING_PATH
    if not path.exists():
        return []
    with open(path) as f:
        book = json.load(f)
    return [e["delivery"] for e in book.get(key, []) if e.get("delivery")]


def no_two_arrivals_share_an_instant(manifest: list[dict]) -> None:
    """Refuse a history where two supplies claim one receipt instant.

    A STAGED TABLE IS NAMED FOR ITS ARRIVAL, so two supplies at the same
    instant claim one physical table and loading the second DROPs the first
    - the failure this guard exists for was real, and what it reported was a
    missing relation several steps downstream rather than anything about a
    duplicate instant. Loud here, where the cause is still visible."""
    seen: dict[str, str] = {}
    for entry in manifest:
        instant = entry.get("received_at")
        if instant in seen:
            raise ValueError(
                f"{entry['run_id']} and {seen[instant]} both claim receipt instant "
                f"{instant}. A staged table is named for its arrival, so these two "
                f"would claim one table and the second would drop the first.")
        seen[instant] = entry["run_id"]


def no_instant_shared_with_another_collection(key: str, manifest: list[dict]) -> None:
    """Refuse an arrival at the receipt instant of another collection's
    delivery (REQ-GEN-334 criterion 13), naming both: receipt order decides
    what a run can read, so a tie would be settled by sort order. The others
    are what each collection generated last, from the bookkeeping - every
    collection generates in hierarchy order, so each pair is compared by the
    later of the two."""
    from qa_tools.common import asset_time

    path = BOOKKEEPING_PATH
    if not path.exists():
        return
    with open(path) as f:
        book = json.load(f)
    theirs: dict = {}
    for other, entries in book.items():
        if other == key:
            continue
        for e in entries:
            if e.get("received_at"):
                theirs[asset_time.parse_instant(e["received_at"], other)] = (
                    f"{other}'s delivery {e.get('delivery') or e.get('run_id')}")
    for entry in manifest:
        at = asset_time.parse_instant(entry["received_at"], entry["run_id"])
        if at in theirs:
            raise ValueError(
                f"{entry['run_id']} (delivery {entry['delivery']}) and {theirs[at]} would "
                f"share one receipt instant, {entry['received_at']} - receipt order decides "
                f"what a run can read, so nothing was written")


def generate(collection_id: str) -> list[dict]:
    """Write `collection_id`'s whole synthetic history; returns its
    bookkeeping. Refused by name for a collection with no provider."""
    from generator import collections, delivery_names, scenario_injection
    from generator.resupply import MAX_ATTEMPTS
    from qa_tools.common import arrivals

    provider = collections.provider(collection_id)
    # 1. BEFORE THE FIRST WRITE. A scenario naming a dataset no provider
    # makes would otherwise be skipped without a word (criterion 8).
    unprovided = scenario_injection.unprovided_scenarios()
    if unprovided:
        raise scenario_injection.CannotPlace(
            "no generator provider makes the dataset these scenarios name, so nothing was "
            "written:\n" + "\n".join(f"  - {u}" for u in unprovided))
    # WHAT EACH DECLARED CORRECTION CLAIMS (REQ-GEN-205 criteria 10 and 18).
    from generator import correction_claims

    # WHAT IT READS IS GENERATED FIRST (REQ-GEN-334 criterion 6).
    order = collections.order_problems(only=collection_id)
    if order:
        raise collections.base.GenerationOrderRefused(
            "; ".join(order) + " - nothing was written")
    correction_claims.check_all(collection_id)
    provider.check_seeds()
    plan = provider.plan()

    # 3. Each slot's arrivals, BUILT before anything is written: what they
    # are, their names and receipts - so that a receipt instant shared with
    # another collection's delivery refuses before the first write
    # (REQ-GEN-334 criterion 13). Delivery-name uniqueness is seeded from
    # what will remain on disk once this collection's last history is
    # cleared - the same set step 2 used to leave behind.
    previous = previous_delivery_names(provider.dataset_id)
    # Delivery names are arbitrary BY DESIGN, which means they can collide -
    # and a collision would write two arrivals into one directory, silently
    # merging deliveries that never arrived together.
    taken_names: set[str] = delivery.existing_delivery_names(DELIVERIES_DIR) - set(previous)
    manifest: list[dict] = []
    writes: list[tuple] = []
    for job in plan.jobs:
        deliveries = provider.slot(plan, job)
        if deliveries is None:
            continue
        entries = provider.entries(plan, job, deliveries, len(manifest))
        injected = plan.injected_by_period.get(job.period.name)
        for n, (delivery_obj, entry) in enumerate(zip(deliveries, entries), start=1):
            entry["received_at"] = provider.received_at(plan, job, n, delivery_obj, entry)
            name = delivery_names.delivery_name(job.period.round_date, job.seed, attempt=n,
                                                taken=taken_names)
            taken_names.add(name)
            entry["delivery"] = name
            if injected is not None:
                # THE DELIVERY NAME, NOT THE GENERATOR'S OWN RUN ID: run
                # identity comes from RECEIPT ORDER over recognised deliveries
                # (REQ-GEN-043), so the placement's run ids are resolved from
                # recognition below - observed rather than predicted.
                injected[1].arrivals[n - 1]["delivery"] = name
            files, received = provider.files(plan, job, n, delivery_obj, entry, name)
            writes.append((name, files, received, entry, delivery_obj, n))
        manifest.extend(entries)
        provider.after_slot(plan, job, deliveries)
    no_two_arrivals_share_an_instant(manifest)
    no_instant_shared_with_another_collection(provider.dataset_id, manifest)

    # 2. Only then is the last history cleared, and the new one written.
    delivery.remove_deliveries(previous, DELIVERIES_DIR, RECEIPTS_DIR)
    for name, files, received, entry, delivery_obj, n in writes:
        delivery.write_delivery(
            name, files, received_at=received,
            deliveries_dir=DELIVERIES_DIR, receipts_dir=RECEIPTS_DIR,
            # STORAGE, because in this PoC the generator IS storage
            # (REQ-PIPE-105 criterion 4): it stands in for the moment our
            # own object store took a supplier's file.
            received_from=delivery.RECEIVED_FROM_STORAGE)

        tag = f"DIRTY({delivery_obj.severity})" if delivery_obj.severity else "clean"
        resupply_tag = (f"  [resupply {n - 1}, received "
                        f"{delivery_obj.received_date.isoformat()}]") if n > 1 else ""
        print(f"{entry['run_id']}: {provider.describe(entry, delivery_obj)}  "
              f"[{tag}]{resupply_tag}  -> {name}/")
        if delivery_obj.severity == "red" and n >= MAX_ATTEMPTS:
            print(f"  -> still red after {n} deliveries - "
                  f"giving up (hit MAX_ATTEMPTS={MAX_ATTEMPTS})")

    # 5.
    # NO ORDINARY ARRIVAL REFILED BY A VERSION-LEVEL CORRECTION (REQ-GEN-205
    # criterion 10): its instants exist only once written.
    from qa_tools.common import hierarchy

    correction_claims.check_written(
        [d.dataset_id for d in hierarchy.datasets_in_collection(collection_id)], manifest,
        frozenset(plan.injected_by_period))
    write_bookkeeping(provider.dataset_id, manifest)
    if plan.resolved:
        placed = [placement for _, placement in plan.resolved]
        recognised = arrivals.arrivals_for(collection_id, provider.run_prefix,
                                           DELIVERIES_DIR, RECEIPTS_DIR)
        # AGAINST WHAT RECOGNITION FOUND, not against what was meant to be
        # written - see each function's own docstring.
        scenario_injection.check_suppressed_days_are_empty(placed, recognised)
        scenario_injection.resolve_run_ids(placed, recognised)
        scenario_injection.check_every_index_has_its_supply(placed)
        placed += provider.extra_placements(plan)
        written = scenario_injection.write_placements(placed, merge=True)
        print(f"Recorded {len(placed)} scenario placement(s) -> {written}")
    print(f"\nWrote {len(manifest)} deliveries across {len(plan.jobs)} scheduled slots "
          f"to {os.path.abspath(DELIVERIES_DIR)}")
    return manifest
