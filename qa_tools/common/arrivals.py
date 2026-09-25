"""Deliveries on disk, recognised as arrivals the pipeline can act on
(REQ-GEN-043).

THIS IS WHERE THE FORMAT STOPS BEING A FILE LAYOUT and starts being
something the pipeline uses. Everything it knows, it works out from
what physically happened:

- WHICH DATASET a file belongs to, from the filename alone, through
  that dataset's own configured `arrivalPattern` (criterion 3).
- WHICH COLLECTION a delivery is for, from the datasets its files
  matched. A delivery is not labelled; it is recognised.
- WHEN it arrived, from OUR receipt record, never from anything inside
  the delivery (criterion 5).
- WHAT ORDER arrivals happened in, from those receipt instants - never
  from a delivery's name, which is arbitrary and means nothing.

WHAT IT DELIBERATELY DOES NOT DO is read the generator's bookkeeping.
`data/generator_bookkeeping.json` knows which slot each delivery was
built to fill, which scenario it came from and what severity was
injected - and a pipeline reading any of that would be making filing
decisions from a declaration rather than from arrival plus slot state,
which is the supplier-declared manifest Thread B rejected, wearing our
own badge (criterion 7). Tests may read it. Nothing here may.

RUN IDS COME FROM RECEIPT ORDER, which is a real observable rather than
a declaration: the first Birth Registrations delivery we received is
run_001. That keeps them dateless and deterministic (REQ-GEN-042) while
deriving them from arrival rather than from anything a supplier said.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


from qa_tools.common import delivery, hierarchy, slots


@dataclass(frozen=True)
class Arrival:
    """One recognised delivery, ready for the pipeline.

    `files_by_dataset` maps a dataset id to the file NAMES that matched
    it - a list, because a supplier splitting a large extract across
    two files is ordinary (criterion 8). `unmatched` holds files no
    pattern claimed, which is not an error: a covering note or a PDF is
    a real thing suppliers send, reported rather than swallowed
    (criterion 9).
    """

    run_id: str
    run_index: int
    collection_id: str
    delivery_name: str
    path: Path
    received_at: datetime
    files_by_dataset: dict[str, tuple[str, ...]]
    unmatched: tuple[str, ...]
    anomalies: tuple[str, ...]

    def as_entry(self) -> dict:
        """This arrival as the plain dict the orchestrators pass around.

        Carries ONLY what the pipeline legitimately knows from what
        arrived: which run it is, when we received it, and where its
        files are. No injected severity, no slot, no period - those are
        the generator's bookkeeping, and a pipeline reading them is
        filing from a declaration (criterion 7).
        """
        return {"run_id": self.run_id, "run_index": self.run_index,
                "received_at": self.received_at.isoformat(),
                "delivery": self.delivery_name, "path": str(self.path)}

    def path_for(self, dataset_id: str) -> Path:
        """The single file for one dataset, or an error naming why not.

        Deliberately refuses when a dataset matched several files: the
        loaders below handle one file per dataset today, and quietly
        taking the first would drop a supplier's second file without
        anybody noticing. Criterion 8 requires the format to CARRY that
        case; making the loader guess is a different thing.
        """
        names = self.files_by_dataset.get(dataset_id) or ()
        if len(names) != 1:
            raise delivery.DeliveryFormatError(
                f"delivery {self.delivery_name!r}: dataset {dataset_id!r} matched {len(names)} "
                f"files ({', '.join(names) or 'none'}). This loader handles exactly one; taking "
                f"the first would silently drop the rest.")
        return self.path / names[0]


@dataclass(frozen=True)
class Recognition:
    """What one delivery turned out to hold.

    A DELIVERY MAY SPAN COLLECTIONS (criteria 8 and 14, Keith
    2026-09-24), which this used to refuse: it raised, and a raise here
    took the whole run down for one odd drop. The argument for holding
    was that a mixed delivery means the transport BOUNDARY is wrong
    rather than the data, so every arrival fact derived from it is
    suspect - and it does not survive the observation that spanning is
    legitimate, because a hold would stop healthy supply on a boundary
    that is working. Each file is attributed on its own dataset's
    terms; nothing is held for the delivery's shape.

    What survives from that thread is the blast-radius rule, which
    applies to every odd delivery: whatever recognition decides about
    one, it must not take the rest of the run down - the same shape as
    failing 29 healthy datasets for one exhausted schedule.
    """

    delivery_name: str
    by_dataset: dict[str, tuple[str, ...]]
    unmatched: tuple[str, ...]
    contested: dict[str, tuple[str, ...]]
    #: Datasets whose files DID match, for a dataset nothing is owed
    #: from. An UNEXPECTED TABLE, which is a different event from an
    #: unrecognised artefact and gets a different level (criterion 11).
    unexpected: tuple[str, ...] = ()

    @property
    def collections(self) -> tuple[str, ...]:
        """Derived from the datasets the FILES were attributed to, never
        from the delivery's name (criterion 9)."""
        return tuple(sorted({hierarchy.dataset(ds).collection_id for ds in self.by_dataset}))

    @property
    def is_unplaceable(self) -> bool:
        """Nothing in it matched any dataset. A real operational event
        - reported, never a failed run (criterion 13)."""
        return not self.by_dataset


def recognise(d: delivery.Delivery) -> Recognition:
    """Sort one delivery's files by the dataset each belongs to.

    THE PATTERNS NO LONGER COME FROM THE CONTRACT (REQ-PIPE-058). Each
    dataset declares its own regular expression in
    contract/data-asset.yaml and qa_tools/common/arrival_patterns.py
    owns the match.
    """
    found = delivery.files_by_dataset(d)
    # A FILE TWO DATASETS BOTH CLAIM is a configuration error, and it is
    # reported at warning level and attributed to nobody rather than
    # failing the delivery (REQ-PIPE-058 criterion 9). Failing would
    # mean one bad pattern stopping every other supply in the same drop.
    for name, claimants in sorted(found.contested.items()):
        warnings.warn(
            f"delivery {d.name!r}: {name!r} matches the arrival pattern of more than "
            f"one dataset ({', '.join(claimants)}), so it has been attributed to none "
            f"of them and is held for a human. Two datasets claiming one filename is a "
            f"configuration error - see contract/data-asset.yaml.",
            stacklevel=2)
    # AN UNRECOGNISED ARTEFACT IS A WARNING, not informational (Keith,
    # 2026-09-24). His own case is the dangerous one: a catch-up
    # delivery whose current files match their patterns while an older
    # one, named differently, does not - so the delivery looks healthy
    # and a real supply is silently on the floor. Its NAME is reported
    # and its CONTENTS are never read: a filename in a Birth
    # Registrations or Child Protection context is itself potentially
    # identifying, which is why the line is stated rather than assumed.
    if found.unmatched:
        warnings.warn(
            f"delivery {d.name!r}: {len(found.unmatched)} file(s) matched no dataset's "
            f"arrival pattern and were not processed - {', '.join(sorted(found.unmatched))}. "
            f"A covering note is ordinary; a renamed extract is a supply on the floor.",
            stacklevel=2)
    # AN UNEXPECTED TABLE IS INFORMATIONAL, and an unrecognised
    # artefact is a warning. The two sit adjacent and are easy to
    # collapse into one another, so the distinction is worth keeping:
    # a file matching NO pattern may be a renamed extract, which is a
    # real supply on the floor; a file matching a pattern for a dataset
    # nothing is owed from is a supplier sending something extra, which
    # is odd rather than lossy. Nothing is dropped either way - the
    # table is still attributed and still staged.
    #
    # NARROWER THAN THE CRITERION, deliberately. It says "no slot in
    # that period", and which period a supply fills is REQ-PIPE-062's
    # answer, which does not exist yet. What is checkable now is a
    # dataset with no slots AT ALL, which is the same event at a
    # coarser grain.
    unexpected = tuple(sorted(
        ds for ds in found.by_dataset if not slots.is_owed_supplies(ds)))
    if unexpected:
        print(f"note: delivery {d.name!r} carries {', '.join(unexpected)}, which "
               f"nothing is currently owed from - processed as usual.")
    return Recognition(
        delivery_name=d.name,
        unexpected=unexpected,
        by_dataset={ds: tuple(names) for ds, names in found.by_dataset.items()},
        unmatched=tuple(found.unmatched),
        contested={k: tuple(v) for k, v in found.contested.items()})


def arrivals_for(collection_id: str, run_id_prefix: str,
                  deliveries_dir: Path | None = None,
                  receipts_dir: Path | None = None) -> list[Arrival]:
    """Every recognised arrival for one collection, OLDEST FIRST.

    AN UNKNOWN COLLECTION RAISES rather than answering `[]`, which is
    what it used to do. Empty means "nothing has arrived yet", an
    ordinary state; a collection the tree does not define is a
    different thing entirely, and returning the same answer for both
    made a renamed collection look like a quiet day - a pipeline
    processing nothing and reporting nothing wrong
    (post-build-review #41).

    RUN IDS ARE STILL POSITIONAL, and that is a known gap rather than
    an oversight: REQ-PIPE-057 criterion 18 forbids deriving a run's
    identity from a position in a list recognition can reorder or
    shorten, and names no replacement. Keith's call, 2026-09-25: the
    identity belongs with REQ-PIPE-069's delivery log, which is where a
    delivery gets a durable record of its own, rather than being given
    a committed mapping here that 069 would absorb almost immediately.
    What IS built is criterion 19's guard - see run_id_guard.py - so a
    recognition change that would re-key committed history fails
    loudly, naming the runs, instead of being found when CI goes red.
    """
    hierarchy.datasets_in_collection(collection_id)  # raises if unknown
    out: list[Arrival] = []
    for d in delivery.list_deliveries(deliveries_dir, receipts_dir):
        found = recognise(d)
        by_dataset = {ds: names for ds, names in found.by_dataset.items()
                      if hierarchy.dataset(ds).collection_id == collection_id}
        # ONE DELIVERY, POSSIBLY TWO RUNS. A delivery spanning
        # collections contributes to each collection's own sequence:
        # the DELIVERY is the transport unit and the RUN is the
        # per-collection QA unit, and they were only ever the same
        # thing by coincidence of this PoC's generated data.
        if not by_dataset:
            continue
        index = len(out) + 1
        out.append(Arrival(
            run_id=f"{run_id_prefix}{index:03d}", run_index=index,
            collection_id=collection_id, delivery_name=d.name, path=d.path,
            received_at=d.received_at, files_by_dataset=by_dataset,
            unmatched=found.unmatched, anomalies=d.anomalies))
    return out


def unplaceable(deliveries_dir: Path | None = None,
                 receipts_dir: Path | None = None) -> list[delivery.Delivery]:
    """Deliveries nothing could place - reported, never guessed at."""
    return [d for d in delivery.list_deliveries(deliveries_dir, receipts_dir)
            if recognise(d).is_unplaceable]
