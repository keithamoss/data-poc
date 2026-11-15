"""The on-disk delivery format's READER (REQ-GEN-043; split by REQ-PIPE-380
criterion 2): a delivery, its receipts, the survey of the tree, and which
dataset each file is for.

THE WRITER IS qa_tools/common/delivery.py (v6 Q1, SETTLED by Keith
2026-11-14): asset_model/ reads the delivery tree and writes it nowhere
(criterion 18), so writing a delivery or a receipt stays in the real
pipeline, where hand filing calls it.

READ docs/delivery-format.md FIRST - it is the normative specification
and this module is its implementation. What follows is only what a
reader of the code needs that the spec does not already say.

A DELIVERY IS ONE PHYSICAL ARRIVAL of one or more files, and one
directory under `data/deliveries/` is one delivery. The boundary is the
directory, observable from a listing without opening anything - which
is what a real transport gives you: one S3 prefix, one SFTP session,
one folder drop.

THE DELIVERY ASSERTS ONLY WHAT PHYSICALLY HAPPENED. It does not say
which period it is for or which slot it fills; those are judgments we
would have to trust and cannot enforce across a varied supplier base
(plans/supply-model.md Thread B). Nothing here reads a statement of
intent out of a delivery, and `read_delivery()` reports one as an
anomaly if it finds it.

THE RECEIPT INSTANT IS OURS, lives outside the delivery, and is
SIMULATED rather than taken from a file's mtime. A generated history
spans years but is written in seconds, so real file metadata would
collapse every arrival onto one instant and destroy every injected
scenario. Labelled here rather than quietly relied upon.

WHY A RECEIPT LOOKALIKE INSIDE A DELIVERY IS AN ANOMALY, never a value:
the moment the receipt time lives in a file rather than somewhere only
we control, a supplier who writes a file of that name is setting our
own clock. The boundary is that the record lives in a directory the
supplier has no path to write to.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from qa_tools.common import arrival_patterns, asset_time, assets, delivery_boundary

ROOT = Path(__file__).resolve().parent.parent


# WHERE THE SELECTED ASSET'S DELIVERIES, RECEIPTS AND BOOKKEEPING LIVE, asked
# of the resolver at CALL TIME (REQ-PIPE-342 criterion 6, REQ-PIPE-365
# criterion 1) - these were module constants, which a module imported before
# a test selected its asset would have kept pointing at the wrong folder.
# Each is the DEFAULT a reader here uses when its caller names no directory,
# and the one thing a test redirects them all through (monkeypatch the
# function). generator/driver.py has its own three, so redirecting the
# generator's output leaves these alone, as the constants did.

def default_deliveries_dir() -> Path:
    """The selected asset's delivery tree."""
    return assets.deliveries_dir()


def default_receipts_dir() -> Path:
    """The selected asset's receipts, beside its delivery tree."""
    return assets.receipts_dir()

#: WHERE A RECEIPT'S INSTANT CAME FROM (REQ-PIPE-105 criteria 3 and 4).
#:
#: `STORAGE` means our own storage recorded when it took the object, and
#: that instant is what the receipt carries - S3's `LastModified`, set by
#: S3 when the object is stored rather than by whoever uploaded it. This is
#: the one to prefer, because it is the moment the thing actually became
#: ours.
#:
#: `OUR_CLOCK` means storage reported no such instant and we stamped it
#: ourselves at the moment of receipt. A local folder drop is the ordinary
#: case: a filesystem mtime survives a copy, so it can be a timestamp the
#: SUPPLIER set, which criterion 3 rules out explicitly.
#:
#: NEITHER IS EVER THE FILE'S CONTENTS. A date inside an extract is the
#: supplier's claim about their own data and has nothing to do with when we
#: received it - and a resupply exists precisely because the first attempt
#: was wrong, possibly wrong in its dates.
#:
#: RECORDED RATHER THAN INFERRED, which is criterion 4's own requirement
#: and the part that is easy to leave out: the two instants mean different
#: things to anyone judging whether a supply was late, and a receipt that
#: does not say which it holds cannot be judged at all.
RECEIVED_FROM_STORAGE = "storage"
RECEIVED_FROM_OUR_CLOCK = "our-clock"
RECEIPT_SOURCES = (RECEIVED_FROM_STORAGE, RECEIVED_FROM_OUR_CLOCK)

# Names that would be a receipt record if we trusted one from inside a
# delivery. We do not - see the module docstring. Matched loosely and
# case-insensitively on purpose: the point is to NOTICE a supplier
# claiming to set our clock, and an attacker or a confused supplier
# would not use our exact filename.
_RECEIPT_LOOKALIKE = re.compile(
    r"^(_?receipt|_?received|received[_-]?at|arrival|transport[_-]?record)\b.*\.(json|ya?ml|txt)$",
    re.IGNORECASE)

# Names that assert what a delivery is FOR. A supplier-declared manifest
# is exactly what Thread B rejected, so finding one is worth reporting
# even though nothing reads it.
_INTENT_LOOKALIKE = re.compile(
    r"^(manifest|metadata|period|slot|delivery[_-]?info|control)\b.*\.(json|ya?ml|xml|txt)$",
    re.IGNORECASE)


class DeliveryFormatError(ValueError):
    """A delivery that cannot be written or read as the format defines
    it. Always names the delivery and what is wrong with it."""


class ReceiptOrderError(RuntimeError):
    """A receipt that can be read but cannot be ORDERED.

    DELIBERATELY NOT A DeliveryFormatError, and the distinction is
    load-bearing rather than taxonomic: survey() catches that one and
    reclassifies the delivery as still in flight. A receipt missing its
    sequence is not an incomplete upload - it is a complete arrival we
    cannot place in the processing order - and reporting it as in
    flight would hide the one thing worth seeing behind an ordinary
    operational state.
    """


@dataclass(frozen=True)
class Delivery:
    """One arrival, as read back off disk.

    `received_at` comes from OUR receipt record, never from anything
    inside the delivery. `anomalies` is every unexpected artefact found
    while reading - reported, never acted on.
    """

    name: str
    path: Path
    received_at: datetime
    files: tuple[str, ...]          # file names, sorted, relative to the delivery
    anomalies: tuple[str, ...]
    #: Where this receipt fell in the order receipts were WRITTEN - the
    #: tiebreak for two arrivals sharing a receipt instant
    #: (REQ-PIPE-061 criterion 3). Never a supplier's fact.
    sequence: int = 0
    #: WHICH CLOCK STAMPED `received_at` (REQ-PIPE-105 criterion 4) -
    #: storage's own record of taking the object, or ours at the moment of
    #: receipt. Carried rather than left in the receipt file, because
    #: anything judging whether a supply was late is judging this instant
    #: and has to know which it is.
    #:
    #: DEFAULTS TO OUR_CLOCK for a receipt written before this field
    #: existed, which is the conservative direction: it claims the weaker
    #: provenance rather than asserting storage said something it never
    #: did.
    received_from: str = RECEIVED_FROM_OUR_CLOCK
    #: EACH FILE'S OWN RECEIPT (REQ-GEN-044 criterion 12; Keith,
    #: 2026-10-02: one receipt per file). filename -> (instant, sequence,
    #: source). `received_at`/`sequence` above are the delivery's FIRST
    #: file's, which is what a delivery-level reader means by "when it
    #: arrived"; an ARRIVAL - one file since REQ-PIPE-105 - reads its own.
    file_receipts: Mapping[str, tuple[datetime, int, str]] = field(default_factory=dict)
    #: A STATED ORIGINAL ARRIVAL per file (REQ-PIPE-103 criteria 9-10):
    #: filename -> an ISO instant with its offset, or NOT_KNOWN. Only ever
    #: present for a supply a person filed by hand and answered for; a file
    #: absent here was never asked about (criterion 18). RECORDED, NEVER
    #: USED - nothing orders, names, files, judges or promotes on it
    #: (criterion 11).
    stated_original: Mapping[str, str] = field(default_factory=dict)
    #: WHO FILED IT (REQ-PIPE-147): {"kind": "automated"} or {"kind":
    #: "person", "route": one of HAND_FILING_ROUTES, "who": an identity}.
    filed_by: Mapping[str, str] = field(default_factory=lambda: dict(AUTOMATED))

    @property
    def file_paths(self) -> tuple[Path, ...]:
        return tuple(self.path / name for name in self.files)

    def received_at_of(self, filename: str) -> datetime:
        """When OUR storage took this one file."""
        return self.file_receipts[filename][0] if filename in self.file_receipts \
            else self.received_at

    def sequence_of(self, filename: str) -> int:
        """Where this file's receipt fell in the order receipts were written."""
        return self.file_receipts[filename][1] if filename in self.file_receipts \
            else self.sequence

#: What a delivery nobody filed by hand records (REQ-PIPE-147 criterion 5).
AUTOMATED = {"kind": "automated"}


def read_receipt(name: str, receipts_dir: Path | None = None) -> datetime:
    """Our recorded receipt instant for one delivery.

    A missing receipt is a hard error, not a fallback to a file's mtime:
    an arrival we have no record of receiving is a gap to notice, and
    inventing a time for it would hide exactly the thing worth seeing.
    """
    return read_receipt_record(name, receipts_dir)[0]


def read_receipt_record(name: str,
                         receipts_dir: Path | None = None) -> tuple[datetime, int, str]:
    """Our receipt for one delivery as a whole: its FIRST file's instant,
    sequence and clock - when the delivery began to arrive.

    Built from the per-file receipts (REQ-GEN-044 criterion 12); see
    read_file_receipts() for the rules each one is held to.
    """
    receipts = read_file_receipts(name, receipts_dir)
    first = min(receipts.values(), key=lambda r: (r[0], r[1]))
    return first


def read_file_receipts(name: str, receipts_dir: Path | None = None
                       ) -> dict[str, tuple[datetime, int, str]]:
    """Every file's receipt for one delivery: filename -> (instant,
    sequence, clock).

    A DELIVERY WITH NO RECEIPTS IS A HARD ERROR, not a fallback to a
    file's mtime: an arrival we have no record of receiving is a gap to
    notice, and inventing a time for it would hide exactly the thing
    worth seeing. survey() reads that error as "in flight".

    A MISSING SEQUENCE IS A HARD ERROR, not a default of zero
    (REQ-PIPE-061). Defaulting would put every such receipt at the same
    position, so a tie between two of them would fall to sort stability
    over a directory listing - exactly the non-determinism criterion 3
    removes, reintroduced by the fallback written to tolerate it.

    A RECEIPT IN THE OLD ONE-PER-DELIVERY FORMAT is refused with the fix
    in the message. Receipts live under gitignored `data/`, so the answer
    is to regenerate rather than to migrate - the same call REQ-PIPE-061
    made when the sequence arrived.
    """
    receipts_dir = Path(receipts_dir or default_receipts_dir())
    receipt_dir = receipts_dir / name
    if not receipt_dir.is_dir():
        if (receipts_dir / f"{name}.json").exists():
            raise ReceiptOrderError(
                f"delivery {name!r} has a receipt in the old one-per-delivery format at "
                f"{receipts_dir / (name + '.json')}. Receipts are one per FILE since "
                f"2026-10-02 (REQ-GEN-044 criterion 12).\n\nFix: remove data/deliveries/ "
                f"and data/receipts/, then regenerate BOTH collections (`mothman bdm "
                f"generate-synthetic-data` and `mothman cp generate-synthetic-data`).")
        raise DeliveryFormatError(
            f"delivery {name!r} has no receipt record at {receipt_dir}. The receipt is written "
            f"by the receiving side; an arrival with none is a gap to investigate, and this "
            f"will not fall back to a file modification time.")
    out: dict[str, tuple[datetime, int, str]] = {}
    for path in sorted(receipt_dir.glob("*.json")):
        with open(path) as f:
            record = json.load(f)
        received_at = asset_time.parse_instant(record["received_at"], f"received_at in {path}")
        sequence = record.get("sequence")
        if not isinstance(sequence, int):
            raise ReceiptOrderError(
                f"the receipt at {path} has no `sequence`, so this arrival cannot be placed in "
                f"the processing order.\n\nFix: remove data/deliveries/ and data/receipts/, then "
                f"regenerate BOTH collections. Not defaulted to zero on purpose: that would put "
                f"every such receipt in one place, so a tie between two of them would fall to a "
                f"directory listing - the non-determinism this sequence exists to remove.")
        # A MISSING SOURCE READS AS OUR_CLOCK rather than raising, and the
        # asymmetry with `sequence` above is deliberate: a missing sequence
        # breaks ORDERING, which has no safe default, while a missing
        # source only makes provenance less certain, and the honest default
        # is the weaker of the two claims.
        received_from = record.get("received_from")
        if received_from not in RECEIPT_SOURCES:
            received_from = RECEIVED_FROM_OUR_CLOCK
        out[record.get("file") or path.name[:-len(".json")]] = (
            received_at, sequence, received_from)
    if not out:
        raise DeliveryFormatError(
            f"delivery {name!r} has a receipt directory at {receipt_dir} with nothing in it - "
            f"no file of it has been received yet.")
    return out


def read_delivery(name: str, deliveries_dir: Path | None = None,
                   receipts_dir: Path | None = None) -> Delivery:
    """One delivery as it is on disk, with every anomaly reported.

    Reports, never acts. A receipt lookalike and a supplier-declared
    manifest are both listed in `anomalies` and both excluded from
    `files`, so a caller cannot read one by accident - which is the
    whole reason they are excluded rather than merely flagged.
    """
    deliveries_dir = Path(deliveries_dir or default_deliveries_dir())
    path = deliveries_dir / name
    if not path.is_dir():
        raise DeliveryFormatError(f"no delivery directory at {path}")

    files, anomalies = [], []
    for entry in sorted(path.iterdir()):
        if entry.is_dir():
            anomalies.append(f"{entry.name}/ is a directory - a delivery is one flat drop, "
                              f"so this is ignored")
            continue
        if _RECEIPT_LOOKALIKE.match(entry.name):
            anomalies.append(
                f"{entry.name} looks like a receipt record, INSIDE the delivery. Ignored for "
                f"every purpose: our receipt instant comes from data/receipts/, which a supplier "
                f"cannot write to. A supplier placing this would be setting our own clock.")
            continue
        if _INTENT_LOOKALIKE.match(entry.name):
            anomalies.append(
                f"{entry.name} looks like a declaration of what this delivery is for. Ignored: a "
                f"delivery asserts only that these files landed together, and what it is FOR is "
                f"decided from arrival plus slot state, never from a supplier's own statement.")
            continue
        files.append(entry.name)

    receipts = read_file_receipts(name, receipts_dir)
    # A FILE PRESENT WITH NO RECEIPT HAS NOT BEEN RECEIVED YET - storage
    # has not told us it took it - so it is reported and left out, the
    # same treatment survey() gives a whole delivery with none.
    for filename in [f for f in files if f not in receipts]:
        anomalies.append(f"{filename} is present with no receipt - not received yet, so "
                          f"not processed")
        files.remove(filename)
    received_at, sequence, received_from = min(
        (receipts[f] for f in files if f in receipts),
        key=lambda r: (r[0], r[1]), default=read_receipt_record(name, receipts_dir))
    stated, filed_by = _receipt_extras(name, receipts_dir, files)
    return Delivery(name=name, path=path, received_at=received_at, sequence=sequence,
                     received_from=received_from,
                     files=tuple(files), anomalies=tuple(anomalies),
                     file_receipts={f: receipts[f] for f in files},
                     stated_original=stated, filed_by=filed_by)


def _receipt_extras(name: str, receipts_dir, files) -> tuple[dict[str, str], dict]:
    """The stated original arrivals and who filed it, from the receipts.

    A receipt written before these keys existed reads as automated with
    nothing stated - true of every delivery the generators wrote.
    """
    receipt_dir = Path(receipts_dir or default_receipts_dir()) / name
    stated: dict[str, str] = {}
    seen: list[tuple[str, dict]] = []
    for filename in files:
        path = receipt_dir / f"{filename}.json"
        if not path.is_file():
            continue
        record = json.loads(path.read_text())
        given = record.get("filed_by")
        seen.append((filename, given if isinstance(given, dict) and given.get("kind")
                     else dict(AUTOMATED)))
        original = record.get("originally_received")
        if isinstance(original, dict) and original.get("value"):
            stated[filename] = original["value"]
    # ONE DELIVERY, ONE ANSWER TO WHO FILED IT (REQ-PIPE-147's NFR). A
    # delivery whose receipts disagree is refused rather than read as
    # whichever came last - which is what it used to do, silently.
    distinct = {json.dumps(f, sort_keys=True) for _, f in seen}
    if len(distinct) > 1:
        raise DeliveryFormatError(
            f"delivery {name!r}: its receipts disagree about who filed it - "
            + "; ".join(f"{fn}: {json.dumps(f, sort_keys=True)}" for fn, f in seen)
            + ". Nothing is read from a delivery whose own record contradicts itself.")
    return stated, (seen[0][1] if seen else dict(AUTOMATED))


@dataclass(frozen=True)
class InFlight:
    """A delivery that is present and that we have no receipt for.

    THE NORMAL CASE, not an edge one (Keith, 2026-09-24). Under a real
    transport a delivery has no receipt until our own boundary rule
    says the drop is complete, so every delivery is in flight for a
    while - the receipt is what makes a mid-upload drop
    distinguishable from a short one, which is the whole reason it is
    required before anything is processed.

    It carries the FILE NAMES, not a count. A count answers "is
    anything in flight"; the question worth asking is "is anything
    STUCK", and three deliveries flowing through look identical to the
    same three sitting there for a week. A file list going 2, 4, 6
    across runs reads as an upload progressing; one stuck at 2 reads as
    one that died. Reading a directory listing records no contents,
    which is the same line drawn everywhere else here.
    """

    name: str
    files: tuple[str, ...]


@dataclass(frozen=True)
class Survey:
    """Everything present under the deliveries tree, read ONCE.

    One pass, not one per collection: at ~30 datasets with years of
    history this tree is thousands of deliveries, and re-reading it per
    collection is the shape that stops scaling first (REQ-PIPE-057's
    own non-functional constraint).
    """

    received: list[Delivery]
    in_flight: list[InFlight]


def survey(deliveries_dir: Path | None = None,
            receipts_dir: Path | None = None) -> Survey:
    """Read the whole deliveries tree once: what has been received, and
    what is present without a receipt.

    A RECEIPT-LESS DELIVERY IS SKIPPED, NOT FATAL (criteria 4 and 5).
    It used to take every other delivery down with it, because
    read_receipt() raises and this read them in a list comprehension -
    one incomplete upload stopped the entire pipeline. What has not
    changed is the rule underneath: we still never invent a receipt
    instant from a file's modification time. Skipping and reporting
    keeps that rule and drops the collateral damage.

    Nothing here needs to know how LONG a delivery has been present
    (criterion 6). Reporting it on every run needs no interval, no
    mtime and no new persistent state; knowing it had been stuck for
    two days would need one of those, and the mtime is the exact signal
    this module refuses to trust.
    """
    # WHAT ONE DELIVERY IS, BEFORE READING ANY (criteria 2 and 3). A
    # source that has not said fails here, naming itself, rather than
    # having a grouping inferred from filenames or arrival proximity -
    # and it fails before anything is read, so the error is about the
    # configuration rather than about whatever happened to be on disk.
    delivery_boundary.check_all()

    deliveries_dir = Path(deliveries_dir or default_deliveries_dir())
    # A freshly-cloned machine has no data/ at all. Absence is a state
    # to handle, not a precondition to assert - a test that asserted
    # this tree exists passed locally and went red in CI on 2026-09-23.
    if not deliveries_dir.is_dir():
        return Survey(received=[], in_flight=[])

    received, in_flight = [], []
    for entry in sorted(deliveries_dir.iterdir()):
        if not entry.is_dir():
            continue
        try:
            received.append(read_delivery(entry.name, deliveries_dir, receipts_dir))
        except DeliveryFormatError:
            in_flight.append(InFlight(
                name=entry.name,
                files=tuple(sorted(p.name for p in entry.iterdir() if p.is_file()))))
    # RECEIPT INSTANT, THEN THE ORDER THE RECEIPTS WERE WRITTEN
    # (REQ-PIPE-061 criteria 1 and 3). The second key is the whole
    # point: this used to sort on the instant alone, which is a STABLE
    # sort over the name-sorted iterdir() above - so two arrivals
    # sharing an instant were ordered by the supplier's own naming
    # habits, which REQ-PIPE-057 criterion 8 separately forbids. The
    # tiebreak has to be stated, because a stable sort over a directory
    # listing is still a directory listing.
    #
    # GLOBAL, ACROSS COLLECTIONS (criterion 4). One delivery may span
    # collections, so a per-collection ordering would visit it twice
    # and could place it differently each time.
    return Survey(received=sorted(received, key=lambda d: (d.received_at, d.sequence)),
                   in_flight=sorted(in_flight, key=lambda d: d.name))


def list_deliveries(deliveries_dir: Path | None = None,
                     receipts_dir: Path | None = None) -> list[Delivery]:
    """Every RECEIVED delivery on disk, OLDEST RECEIPT FIRST.

    Ordered by our own receipt instant, never by directory name -
    a delivery name is arbitrary and means nothing, so sorting by it
    would be inventing an order out of a supplier's naming habits.
    """
    return survey(deliveries_dir, receipts_dir).received


# ---- Which dataset does a file belong to? (criterion 3) --------------

def dataset_for_filename(filename: str) -> str | None:
    """The dataset a file belongs to, or None.

    None is a REAL ANSWER, not a failure: a covering note, a
    spreadsheet or a PDF is something suppliers genuinely send, and the
    pipeline has to have somewhere to put it. It is reported, never
    swallowed (criterion 10).

    WHAT WAS RETIRED HERE, 2026-09-25: this used to take the ODCS
    contract's arrivalPattern keyPatterns and match a file against each
    one's LAST SEGMENT, with `{placeholder}` expanded to a
    non-separator run. That made one configured value mean two
    different things to two consumers - whole S3 keys to
    file_arrival.py, bare filenames here - which is exactly the split
    REQ-PIPE-058 criterion 4 exists to end. The pattern now lives in
    the dataset's own configuration as a regular expression, and
    qa_tools/common/arrival_patterns.py owns the matching.
    file_arrival.py's whole-key matcher outlived it until REQ-PIPE-152,
    when the handlers stopped matching keys at all.
    """
    return arrival_patterns.dataset_for_filename(filename)


@dataclass(frozen=True)
class Attribution:
    """Every file in one delivery, sorted into what can be done with it.

    THREE BUCKETS, not two, and `contested` is the one worth
    explaining. A file matching SEVERAL datasets' patterns is always a
    configuration error - never a supplier's doing - so it is
    attributed to nobody and held for a person (criterion 9). It is
    deliberately NOT the same thing as one dataset's pattern matching
    several files, which is the legitimate split-extract shape and
    lives in `by_dataset` as a list. The two are adjacent in this code
    and have opposite correct behaviour.
    """

    by_dataset: dict[str, list[str]]
    unmatched: list[str]
    contested: dict[str, list[str]]


def files_by_dataset(delivery: "Delivery") -> Attribution:
    """Sort one delivery's files by the dataset whose pattern claims
    each of them.

    A LIST per dataset, not one filename, because a supplier splitting
    a large extract across two files is ordinary (criterion 11) and a
    shape that could only hold one would lose the second silently.
    """
    by_dataset: dict[str, list[str]] = {}
    unmatched: list[str] = []
    contested: dict[str, list[str]] = {}
    for name in delivery.files:
        found = arrival_patterns.attribute(name)
        if found.is_attributed:
            by_dataset.setdefault(found.dataset_id, []).append(name)
        elif found.is_contested:
            contested[name] = list(found.dataset_ids)
        else:
            unmatched.append(name)
    return Attribution(by_dataset=by_dataset, unmatched=unmatched, contested=contested)
