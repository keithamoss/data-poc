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


from qa_tools.common import delivery, hierarchy


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


def recognise(d: delivery.Delivery) -> tuple[str | None, dict[str, tuple[str, ...]], tuple[str, ...]]:
    """(collection_id, {dataset: files}, unmatched) for one delivery.

    A collection_id of None means nothing in the delivery matched any
    dataset's pattern - a drop we cannot place. Reported by the caller
    rather than raised here, because an unplaceable delivery is a real
    operational event, not a programming error.

    THE PATTERNS NO LONGER COME FROM THE CONTRACT (REQ-PIPE-058). This
    used to read each collection's ODCS `arrivalPattern` block and reuse
    the S3 keyPattern's last segment as a filename matcher; each dataset
    now declares its own regular expression in contract/data-asset.yaml
    and qa_tools/common/arrival_patterns.py owns the match.
    """
    found = delivery.files_by_dataset(d)
    grouped = found.by_dataset
    unmatched = tuple(found.unmatched)
    # A FILE TWO DATASETS BOTH CLAIM is a configuration error, and it is
    # reported at warning level and attributed to nobody rather than
    # failing the delivery (criterion 9). Failing would mean one bad
    # pattern stopping every other supply in the same drop, which is a
    # worse outcome than a held file somebody has to look at.
    for name, claimants in sorted(found.contested.items()):
        warnings.warn(
            f"delivery {d.name!r}: {name!r} matches the arrival pattern of more than "
            f"one dataset ({', '.join(claimants)}), so it has been attributed to none "
            f"of them and is held for a human. Two datasets claiming one filename is a "
            f"configuration error - see contract/data-asset.yaml.",
            stacklevel=2)
    collections = {hierarchy.dataset(ds).collection_id for ds in grouped}
    if len(collections) > 1:
        raise delivery.DeliveryFormatError(
            f"delivery {d.name!r} holds files for more than one collection ({', '.join(sorted(collections))}). "
            f"A delivery is one arrival from one supplier; this is a drop that needs a human.")
    return (collections.pop() if collections else None,
            {ds: tuple(names) for ds, names in grouped.items()},
            unmatched)


def arrivals_for(collection_id: str, run_id_prefix: str,
                  deliveries_dir: Path | None = None,
                  receipts_dir: Path | None = None) -> list[Arrival]:
    """Every recognised arrival for one collection, OLDEST FIRST.

    Run ids are assigned from receipt order within the collection, so
    they are dateless, deterministic and derived from a real observable.

    AN UNKNOWN COLLECTION RAISES rather than answering `[]`, which is
    what it used to do. Empty means "nothing has arrived yet", an
    ordinary state; a collection the tree does not define is a
    different thing entirely, and returning the same answer for both
    made a renamed collection look like a quiet day - a pipeline
    processing nothing and reporting nothing wrong
    (post-build-review #41). Everywhere else in this layer an unknown
    id raises, and this was the exception.
    """
    hierarchy.datasets_in_collection(collection_id)  # raises if unknown
    out: list[Arrival] = []
    for d in delivery.list_deliveries(deliveries_dir, receipts_dir):
        found, by_dataset, unmatched = recognise(d)
        if found != collection_id:
            continue
        index = len(out) + 1
        out.append(Arrival(
            run_id=f"{run_id_prefix}{index:03d}", run_index=index,
            collection_id=collection_id, delivery_name=d.name, path=d.path,
            received_at=d.received_at, files_by_dataset=by_dataset,
            unmatched=unmatched, anomalies=d.anomalies))
    return out


def unplaceable(deliveries_dir: Path | None = None,
                 receipts_dir: Path | None = None) -> list[delivery.Delivery]:
    """Deliveries nothing could place - reported, never guessed at."""
    return [d for d in delivery.list_deliveries(deliveries_dir, receipts_dir)
            if recognise(d)[0] is None]
