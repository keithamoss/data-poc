"""Deliveries on disk, recognised as arrivals the pipeline can act on
(REQ-GEN-043).

THIS IS THE TREE-RECOGNITION HALF (REQ-PIPE-380 criterion 2, QB SETTLED by
Keith 2026-11-14): it reads configuration and the delivery tree, so the
generator checks its placements against exactly what the pipeline
recognises. Building arrivals from the delivery RECORDS -
arrivals_from_records, which reads the database - is the other half, and
stays in qa_tools/common/arrivals.py because asset_model/ opens no
connection.

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

import dataclasses
import os
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


from asset_model import asset_time, delivery, hierarchy, holds, slots
from asset_model import assets as _assets


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
    #: The receipt's own sequence, carried through from the Delivery
    #: (REQ-PIPE-061 criterion 3). Without it an Arrival cannot be
    #: placed in the processing order at all - and the first version of
    #: this left it off, which nothing noticed because the reader
    #: defaulted a missing one to zero.
    sequence: int
    files_by_dataset: dict[str, tuple[str, ...]]
    unmatched: tuple[str, ...]
    anomalies: tuple[str, ...]
    #: WHERE EACH OF ITS FILES IS (REQ-PIPE-152): (filename, storage URI)
    #: pairs, from qa.delivery_file. Empty for an arrival recognised straight
    #: off the deliveries tree, whose files are under `path`; an S3 object is
    #: fetched to a local `path` by s3_arrival.materialise() before staging.
    sources: tuple[tuple[str, str], ...] = ()

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
                "delivery": self.delivery_name, "path": str(self.path),
                # WHICH DATASET ITS FILE IS FOR, recognised by the dataset's own
                # pattern - what the run is recorded as being for (Keith,
                # 2026-10-24, provisional #23), never read off the run id.
                "dataset_id": self.dataset_id}

    @property
    def dataset_id(self) -> str:
        """The one dataset this arrival's file is for (REQ-PIPE-105 criterion 1:
        one arrival is one file, so one dataset)."""
        (dataset_id,) = self.files_by_dataset
        return dataset_id

    @property
    def contested(self) -> frozenset[str]:
        """Datasets in this arrival that several files claim, so nothing
        may choose which is the supply - CONTESTED (REQ-PIPE-105
        criterion 6). It was `held`, REQ-PIPE-059's word, until that hold
        was retired on 2026-10-02 (renamed by Keith's call).

        A CALLER MUST CHECK THIS BEFORE path_for(), which still refuses
        rather than guessing.
        """
        return frozenset(ds for ds, names in self.files_by_dataset.items()
                          if len(names) > 1)

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
    contract/data-asset.yaml and asset_model/arrival_patterns.py
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
            f"configuration error - see {_assets.config_dir()}/data-asset.yaml.",
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
    # A DATASET THAT WILL NEVER OWE ANYTHING (`no_calendar: never` - a
    # one-off's) is not "a supplier sending something extra": nothing is owed
    # by design, so the note says nothing (the mock run of 2026-11-22: fifteen
    # of them on one three-delivery load).
    unexpected = tuple(sorted(
        ds for ds in found.by_dataset
        if not slots.is_owed_supplies(ds) and not _never_owes(ds)))
    if unexpected:
        print(f"note: delivery {d.name!r} carries {', '.join(unexpected)}, which "
               f"nothing is currently owed from - processed as usual.")
    # A SUPPLY NOBODY MAY CHOOSE FOR YOU (REQ-PIPE-059). Reported as
    # needing action rather than informationally: an unexpected table
    # is a supplier sending something extra, and this is a supply that
    # will not be checked until somebody resolves it.
    found_holds = holds.holds_in(Recognition(
        delivery_name=d.name,
        by_dataset={ds: tuple(names) for ds, names in found.by_dataset.items()},
        unmatched=(), contested={}))
    for hold in found_holds:
        warnings.warn(hold.describe(), stacklevel=2)

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

    WHILE A DELIVERY-TREE SNAPSHOT IS INSTALLED (REQ-PIPE-430) - a bootstrap's
    replay of a tree generated before it began - a collection it holds, asked
    of the same folders, is answered from it rather than recognised again,
    each caller getting arrivals no other caller can change. Otherwise the
    tree is recognised as it is now, on every call, so a live pass sees a
    delivery the moment it lands (criterion 4).
    """
    held = _tree
    if held is not None:
        found = held.answer(collection_id, deliveries_dir, receipts_dir)
        if found is not None:
            return found
    return recognise_arrivals(collection_id, run_id_prefix, deliveries_dir, receipts_dir)


def recognise_arrivals(collection_id: str, run_id_prefix: str,
                       deliveries_dir: Path | None = None,
                       receipts_dir: Path | None = None) -> list[Arrival]:
    """arrivals_for, recognised from the tree on disk now - never answered
    from a snapshot. What a snapshot is taken with.

    AN UNKNOWN COLLECTION RAISES rather than answering `[]`, which is
    what it used to do. Empty means "nothing has arrived yet", an
    ordinary state; a collection the tree does not define is a
    different thing entirely, and returning the same answer for both
    made a renamed collection look like a quiet day - a pipeline
    processing nothing and reporting nothing wrong
    (post-build-review #41).

    ONE ARRIVAL IS ONE FILE (REQ-PIPE-105 criterion 1). It was one
    delivery FOLDER until 2026-10-02, so Child Protection's six files
    were recognised as one thing and checked as one run - which is
    what made "is the delivery complete?" a question anything had to
    ask. Now each file is its own arrival and is processed without
    waiting for any other.

    THE SHAPE IS KEPT AND ONLY THE CONTENTS NARROW. `files_by_dataset`
    is still a mapping, carrying exactly one dataset, so every caller
    that iterates it still works. Collapsing it to a scalar would have
    made this a rewrite of every consumer rather than a change of
    unit, for no gain.

    RUN IDS ARE NO LONGER POSITIONAL, and the two changes had to land
    together. `cp_run_007` meant "the seventh delivery recognised",
    which REQ-PIPE-057 criterion 18 forbids - an id must not come from
    a position recognition can reorder or shorten - and which had
    already bitten once, leaving run_022 to run_027 each carrying a
    neighbour's instant when two days were suppressed. Splitting one
    delivery into six would have made that six times worse.

    THE NEW ID ALREADY EXISTED. One arrival is one file, so one
    dataset, so one supply - run identity and supply identity
    converge. It takes the staged PHYSICAL TABLE's spelling,
    `cp_clients__202305010100000000`, rather than the supply id's
    `cp-clients@...`, because `run_schema()` uses a run id UNCHANGED
    as a PostgreSQL schema name and `_ident()` refuses `-` and `@`.
    That refusal is deliberate (Keith, 2026-09-27): hex-encoding was
    dropped because `qa_run_run_5f_001` is what a person then reads in
    psql, in a log and in every error message.

    `run_id_prefix` IS NOW UNUSED FOR THE ID and is kept in the
    signature on purpose, rather than removed in the same change: it
    still says which collection a caller means, every call site passes
    it, and retiring a parameter is a separate, mechanical change that
    does not belong in one that moves the unit of work.
    """
    hierarchy.datasets_in_collection(collection_id)  # raises if unknown
    out: list[Arrival] = []
    for d in delivery.list_deliveries(deliveries_dir, receipts_dir):
        found = recognise(d)
        by_dataset = {ds: names for ds, names in found.by_dataset.items()
                      if hierarchy.dataset(ds).collection_id == collection_id}
        # ONE DELIVERY, POSSIBLY TWO COLLECTIONS. A delivery spanning
        # collections contributes to each: the DELIVERY is the
        # transport unit and the RUN is the QA unit, and they were only
        # ever the same thing by coincidence of this PoC's data.
        if not by_dataset:
            continue
        for dataset_id in sorted(by_dataset):
            names = by_dataset[dataset_id]
            table = hierarchy.dataset(dataset_id).table
            # THIS FILE'S OWN RECEIPT, not the delivery's (REQ-GEN-044
            # criterion 12). Six files can land over ten minutes, and the
            # instant is what names the run and orders the pipeline. Two
            # files for one dataset - the contested case - take the
            # earlier of the two, which is when that supply began to land.
            received_at, sequence = min(
                (d.received_at_of(n), d.sequence_of(n)) for n in names)
            key = asset_time.arrival_key(received_at)
            out.append(Arrival(
                run_id=f"{table}__{key}",
                # POSITION IS STILL REPORTED, and is no longer
                # IDENTITY. Something has to order the processing -
                # filing depends on what the arrival before it
                # promoted - and a sequence number is the honest way
                # to say "fourth of this batch" without anything
                # keying on it.
                run_index=len(out) + 1,
                collection_id=collection_id, delivery_name=d.name, path=d.path,
                received_at=received_at, sequence=sequence,
                # SEVERAL FILES FOR ONE DATASET STAY TOGETHER in one
                # arrival, which is the contested case rather than two
                # arrivals: nobody has said which file is the supply,
                # so splitting them would be choosing between them.
                files_by_dataset={dataset_id: names},
                unmatched=found.unmatched, anomalies=d.anomalies))
    # IN THE ORDER STORAGE TOOK THEM, across every delivery: receipt
    # instant, then the order receipts were written (REQ-PIPE-061). Once
    # files carry their own instants a delivery's files no longer arrive
    # in dataset-name order, and processing them that way would file
    # each against a decision log one step out of date. `run_index` is
    # renumbered to match - it reports position and is not identity.
    out.sort(key=lambda a: (a.received_at, a.sequence, a.run_id))
    return [dataclasses.replace(a, run_index=i) for i, a in enumerate(out, start=1)]


def unplaceable(deliveries_dir: Path | None = None,
                 receipts_dir: Path | None = None) -> list[delivery.Delivery]:
    """Deliveries nothing could place - reported, never guessed at."""
    return [d for d in delivery.list_deliveries(deliveries_dir, receipts_dir)
            if recognise(d).is_unplaceable]


# ---- THE DELIVERY-TREE SNAPSHOT (REQ-PIPE-430) --------------------------------
#
# WHY. REQ-PIPE-250's profile put a quarter of the quarterly replay's samples in
# recognising the whole delivery tree - every arrival, and every next-receipt
# look-up, re-read every delivery and every receipt (0.6s on 229 deliveries,
# several times an arrival). A bootstrap generates the whole tree BEFORE any
# replay starts ('so no pipeline recognises a delivery tree a generator is
# still writing'), so for the replay's span the tree cannot have changed.
#
# ITS OWN INSTALLATION, NOT THE CONFIGURATION PIN (the architect's B4): a
# generation pins the configuration too, and recognises the tree it has just
# written, so this is installed by the bootstrap after generation and never
# during one (REQ-GEN-398 criterion 4). Its end digest is what proves the
# 'cannot have changed': a tree that did change mid-replay fails the bootstrap.
#
# NOT A CONFIGURATION CACHE: the tree is supplier files, not configuration, so
# REQ-PIPE-254's content rule does not govern it.


class TreeChanged(RuntimeError):
    """A delivery tree changed while a snapshot of it was installed."""


def _folder(path) -> str:
    return os.path.abspath(os.fspath(path))


def _arrival_facts(found) -> list:
    return [(a.run_id, a.delivery_name, a.received_at.isoformat(), a.sequence,
             sorted((k, tuple(v)) for k, v in a.files_by_dataset.items()),
             tuple(a.unmatched), tuple(a.anomalies)) for a in found]


def _listing(folder: Path, read: bool) -> list:
    """(relative path, size, and the content where `read`) of every file
    under `folder`, sorted."""
    out = []
    if not folder.is_dir():
        return out
    for root, dirs, files in os.walk(folder):
        dirs.sort()
        for f in sorted(files):
            path = Path(root) / f
            rel = path.relative_to(folder).as_posix()
            try:
                out.append((rel, path.stat().st_size,
                            path.read_bytes().hex() if read else ""))
            except OSError:
                out.append((rel, None, ""))
    return out


def _tree_digest(collection_id: str, found, deliveries_dir: Path, receipts_dir: Path) -> str:
    """A collection's recognised tree: its arrivals as recognised, and the
    listing and receipts of every delivery folder they came from."""
    import hashlib
    import json

    names = sorted({a.delivery_name for a in found})
    facts = {"arrivals": _arrival_facts(found),
             "deliveries": {n: _listing(deliveries_dir / n, read=False) for n in names},
             "receipts": {n: _listing(receipts_dir / n, read=True) for n in names}}
    return hashlib.sha256(json.dumps(facts, sort_keys=True, default=str).encode()).hexdigest()


class TreeSnapshot:
    """Each named collection's arrivals, recognised ONCE from the delivery
    tree at `deliveries_dir` and `receipts_dir` (the selected asset's by
    default), with a digest of each collection's recognised tree.

    install() answers arrivals_for from it; release() puts recognition back
    and returns each collection whose tree no longer matches its digest.
    Picklable, so a bootstrap hands it to each process it starts
    (assets.handoff)."""

    def __init__(self, collection_ids, deliveries_dir: Path | None = None,
                 receipts_dir: Path | None = None):
        self.deliveries_dir = Path(deliveries_dir or delivery.default_deliveries_dir())
        self.receipts_dir = Path(receipts_dir or delivery.default_receipts_dir())
        self.collections = tuple(dict.fromkeys(collection_ids))
        self.arrivals: dict[str, tuple[Arrival, ...]] = {}
        self.digests: dict[str, str] = {}
        for cid in self.collections:
            found = recognise_arrivals(cid, "", self.deliveries_dir, self.receipts_dir)
            self.arrivals[cid] = tuple(found)
            self.digests[cid] = _tree_digest(cid, found, self.deliveries_dir,
                                             self.receipts_dir)
        self._folders = (_folder(self.deliveries_dir), _folder(self.receipts_dir))

    def __eq__(self, other) -> bool:
        return isinstance(other, TreeSnapshot) and self.key == other.key

    def __hash__(self) -> int:
        return hash(self.key)

    @property
    def key(self) -> tuple:
        return (self._folders, tuple(sorted(self.digests.items())))

    def answer(self, collection_id: str, deliveries_dir=None, receipts_dir=None):
        """The collection's arrivals from the snapshot, each the caller's own
        (files_by_dataset copied, criterion 5) - or None where the snapshot
        does not hold that collection or those folders."""
        held = self.arrivals.get(collection_id)
        if held is None:
            return None
        asked = (_folder(deliveries_dir or delivery.default_deliveries_dir()),
                 _folder(receipts_dir or delivery.default_receipts_dir()))
        if asked != self._folders:
            return None
        return [dataclasses.replace(a, files_by_dataset=dict(a.files_by_dataset))
                for a in held]

    def install(self) -> "TreeSnapshot":
        global _tree
        _tree = self
        return self

    def changed(self) -> list[str]:
        """Each collection whose tree, recognised again now, no longer
        matches the digest taken at install."""
        out = []
        for cid in self.collections:
            found = recognise_arrivals(cid, "", self.deliveries_dir, self.receipts_dir)
            if _tree_digest(cid, found, self.deliveries_dir, self.receipts_dir) \
                    != self.digests[cid]:
                out.append(cid)
        return out

    def release(self, *, check: bool = True) -> list[str]:
        """Put recognition back; with `check`, every collection whose tree
        changed while this was installed (criterion 3)."""
        global _tree
        if _tree is self:
            _tree = None
        return self.changed() if check else []


#: The snapshot installed in this process, or None.
_tree: TreeSnapshot | None = None


def installed_tree() -> TreeSnapshot | None:
    """The delivery-tree snapshot installed in this process, or None - for the
    hand-off to a started process (assets.handoff)."""
    return _tree


def adopt_tree(snapshot: TreeSnapshot | None) -> None:
    """A started process's half of the hand-off: hold the tree snapshot it was
    handed, or none. Its digest is checked by the process that took it."""
    global _tree
    _tree = snapshot


def _never_owes(dataset_id: str) -> bool:
    """Whether a dataset declares it will never have a calendar
    (`no_calendar: never`, a one-off's)."""
    from asset_model import schedule

    try:
        return schedule.no_calendar(dataset_id) == schedule.NEVER
    except Exception:  # noqa: BLE001 - only the note depends on it; it stays said
        return False
