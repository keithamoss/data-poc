"""The on-disk delivery format, written and read (REQ-GEN-043).

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

from qa_tools.common import arrival_patterns, asset_time, delivery_boundary

ROOT = Path(__file__).resolve().parent.parent.parent
DELIVERIES_DIR = ROOT / "data" / "deliveries"
RECEIPTS_DIR = ROOT / "data" / "receipts"

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
BOOKKEEPING_PATH = ROOT / "data" / "generator_bookkeeping.json"

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

# Characters that are illegal or awkward in a path on Windows and
# macOS. A delivery name is arbitrary, not unconstrained - this repo
# gets run on other people's machines.
_UNSAFE_IN_PATH = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


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


#: A stated original arrival a person said they do not know
#: (REQ-PIPE-103 criterion 13) - recorded as such, never as a time.
NOT_KNOWN = "not-known"

#: The four routes by which a person supplies a file (REQ-PIPE-103
#: criterion 7, REQ-PIPE-147 criterion 2) - a closed set.
HAND_FILING_ROUTES = ("file", "folder", "table", "s3")

#: What a delivery nobody filed by hand records (REQ-PIPE-147 criterion 5).
AUTOMATED = {"kind": "automated"}


def filed_by_person(route: str, who: str) -> dict:
    if route not in HAND_FILING_ROUTES:
        raise DeliveryFormatError(f"{route!r} is not a hand-filing route - one of "
                                  f"{', '.join(HAND_FILING_ROUTES)}.")
    if not who:
        raise DeliveryFormatError("a delivery a person filed must say who filed it.")
    return {"kind": "person", "route": route, "who": who}


def remove_deliveries(names, deliveries_dir: Path | None = None,
                       receipts_dir: Path | None = None) -> int:
    """Deletes the named deliveries and their receipts. Returns the
    count removed.

    WHY A GENERATOR NEEDS THIS. Two guarantees pull against each other:
    delivery names must be unique across the whole directory (or two
    arrivals silently merge), and a regeneration must OVERWRITE its own
    history rather than accumulate beside it (REQ-GEN-042). Seeding
    uniqueness from what is on disk satisfies the first and breaks the
    second - a re-run simply avoids its own previous names and writes a
    whole second history. Measured: 42 Birth Registrations deliveries
    became 84.

    So a generator clears what IT wrote, from its own bookkeeping,
    before writing again. Each one owns its own output, and neither
    needs to know which deliveries belong to the other.
    """
    deliveries_dir = Path(deliveries_dir or DELIVERIES_DIR)
    receipts_dir = Path(receipts_dir or RECEIPTS_DIR)
    removed = 0
    for name in names:
        path = deliveries_dir / name
        if path.is_dir():
            for child in path.iterdir():
                child.unlink()
            path.rmdir()
            removed += 1
        # ONE RECEIPT PER FILE now, in a directory per delivery
        # (REQ-GEN-044 criterion 12) - and the single per-delivery file
        # an older tree may still carry, so a regenerate over it leaves
        # nothing behind.
        receipt_dir = receipts_dir / name
        if receipt_dir.is_dir():
            for child in receipt_dir.iterdir():
                child.unlink()
            receipt_dir.rmdir()
        legacy = receipts_dir / f"{name}.json"
        if legacy.exists():
            legacy.unlink()
    return removed


def existing_delivery_names(deliveries_dir: Path | None = None) -> set[str]:
    """Every delivery name already on disk.

    THE UNIQUENESS OF A DELIVERY NAME IS GLOBAL TO THE DIRECTORY, not
    to whatever produced it. Found the hard way, 2026-09-23: the two
    generators each kept their own set of taken names and wrote into
    one shared directory, so a Birth Registrations drop and a Child
    Protection drop both landed as `2026-08-corrected` - 60 arrivals
    became 59 directories, and two unrelated deliveries were silently
    merged into one. Seeding from disk is what makes the guarantee hold
    across every writer rather than within each one.
    """
    deliveries_dir = Path(deliveries_dir or DELIVERIES_DIR)
    if not deliveries_dir.is_dir():
        return set()
    return {p.name for p in deliveries_dir.iterdir() if p.is_dir()}


def validate_delivery_name(name: str) -> str:
    """A delivery name is arbitrary but must be a usable directory name.

    Arbitrary is the point - see the spec - so this rejects only what
    would break a checkout on a non-Linux filesystem, never a shape.
    """
    if not name or name.strip() != name:
        raise DeliveryFormatError(f"delivery name {name!r} is empty or has surrounding whitespace")
    if _UNSAFE_IN_PATH.search(name):
        raise DeliveryFormatError(
            f"delivery name {name!r} contains a character that is illegal or awkward in a path "
            f"on Windows or macOS. A name may be anything a supplier would call a drop, but it "
            f"still has to be a directory somebody can check out.")
    if name in (".", "..") or name.endswith("."):
        raise DeliveryFormatError(f"delivery name {name!r} is not a usable directory name")
    return name


def write_delivery(name: str, files: dict[str, str | bytes],
                    received_at: "datetime | Mapping[str, datetime] | None" = None,
                    deliveries_dir: Path | None = None,
                    receipts_dir: Path | None = None,
                    received_from: str | None = None,
                    stated_original: Mapping[str, str] | None = None,
                    filed_by: Mapping[str, str] | None = None) -> Path:
    """Writes one delivery and its receipt record, and returns the
    delivery's own directory.

    `stated_original` and `filed_by` are the two facts a hand-filed
    supply adds (REQ-PIPE-103 criterion 10, REQ-PIPE-147 criterion 6),
    written into each file's receipt so a rebuild from disk restores
    them. Omitted, the receipt says the delivery arrived automatically
    and records no stated original arrival.

    `received_at` IS WHEN OUR STORAGE TOOK THE OBJECT where storage
    reports that (REQ-PIPE-105 criterion 3) - S3's own `LastModified`,
    say. Omit it and this stamps our own clock instead, which is
    criterion 4's fallback, and the receipt says which of the two it
    holds. See RECEIVED_FROM_STORAGE above for why the distinction is
    recorded rather than assumed.

    `received_from` is stated by the caller where it knows, and defaults
    to STORAGE when an instant is supplied and OUR_CLOCK when one is
    not - which is the honest reading of each: an instant handed in came
    from somewhere outside this process, and one we take is ours.

    `files` maps a file name to its content. Content is written
    verbatim - a caller wanting a file that cannot be parsed as the
    format its name claims simply passes content that cannot be
    (criterion 10), and one matching no dataset pattern passes a name
    that does not match (criterion 9). Neither is a special case here.

    The receipt is written to a SEPARATE directory, which is what makes
    it ours. Passing a `receipts_dir` inside `deliveries_dir` is
    refused, because that would hand a supplier a path to our clock.

    ONE RECEIPT PER FILE (REQ-GEN-044 criterion 12; Keith, 2026-10-02),
    at `<receipts_dir>/<delivery>/<file>.json`, because storage gives
    every object its own instant. `received_at` may be ONE instant - every
    file at once, as if unpacked from an archive - or a mapping from each
    file name to its own. A mapping missing a file is refused rather than
    defaulted: a file with no instant has not been received.
    """
    deliveries_dir = deliveries_dir or DELIVERIES_DIR
    receipts_dir = receipts_dir or RECEIPTS_DIR
    if received_from is None:
        received_from = (RECEIVED_FROM_STORAGE if received_at is not None
                          else RECEIVED_FROM_OUR_CLOCK)
    if received_from not in RECEIPT_SOURCES:
        raise DeliveryFormatError(
            f"{received_from!r} is not a receipt source - one of "
            f"{', '.join(RECEIPT_SOURCES)}. There is no third answer and no "
            f"'unknown': a receipt that cannot say which clock stamped it cannot "
            f"be judged for lateness.")
    if received_at is None:
        received_at = asset_time.now()
    validate_delivery_name(name)
    if isinstance(received_at, Mapping):
        missing = sorted(set(files) - set(received_at))
        if missing:
            raise DeliveryFormatError(
                f"delivery {name!r}: no receipt instant for {', '.join(missing)} - a file "
                f"with no instant has not been received, so it is not written as if it had")
        instants = {f: received_at[f] for f in files}
    else:
        instants = {f: received_at for f in files}
    if not files:
        raise DeliveryFormatError(f"delivery {name!r} has no files - a delivery is an ARRIVAL, "
                                   f"and nothing arriving is not one")

    deliveries_dir, receipts_dir = Path(deliveries_dir), Path(receipts_dir)
    if receipts_dir == deliveries_dir or deliveries_dir in receipts_dir.parents:
        raise DeliveryFormatError(
            f"the receipts directory ({receipts_dir}) is inside the deliveries directory "
            f"({deliveries_dir}). The receipt record is ours and must live where a supplier "
            f"has no path to write it.")

    path = deliveries_dir / name
    if path.exists():
        raise DeliveryFormatError(
            f"delivery {name!r} already exists at {path}. Two arrivals sharing a directory would "
            f"silently merge deliveries that never arrived together - pass a name that is unique "
            f"across the whole deliveries directory, not just within one writer.")
    path.mkdir(parents=True, exist_ok=True)
    for filename, content in files.items():
        if "/" in filename or "\\" in filename:
            raise DeliveryFormatError(
                f"delivery {name!r}: file name {filename!r} contains a path separator - a "
                f"delivery is one flat drop, not a tree")
        mode, payload = ("wb", content) if isinstance(content, bytes) else ("w", content)
        with open(path / filename, mode) as f:
            f.write(payload)

    write_receipts(name, instants, receipts_dir, received_from=received_from,
                   stated_original=stated_original, filed_by=filed_by)
    return path


def write_receipts(name: str, received_at: "datetime | Mapping[str, datetime]",
                   receipts_dir: Path | None = None, *,
                   files=None, received_from: str = RECEIVED_FROM_STORAGE,
                   sequence: int | None = None,
                   stated_original: Mapping[str, str] | None = None,
                   filed_by: Mapping[str, str] | None = None) -> None:
    """Write one receipt per FILE for a delivery (REQ-GEN-044 criterion
    12), and nothing else - the one writer of the receipt format.

    `received_at` is one instant for every file in `files`, or a mapping
    from each file to its own. `sequence` is where the FIRST receipt
    falls in the write order; omitted, it continues from the highest
    already written. Public because a test that builds a delivery
    write_delivery() would refuse still needs receipts in the real
    format - four tests used to hand-copy it.
    """
    receipts_dir = Path(receipts_dir or RECEIPTS_DIR)
    instants = (dict(received_at) if isinstance(received_at, Mapping)
                else {f: received_at for f in (files or ())})
    receipt_dir = receipts_dir / name
    receipt_dir.mkdir(parents=True, exist_ok=True)
    if sequence is None:
        sequence = next_sequence(receipts_dir)
    # IN RECEIPT ORDER, so the sequence says which file storage took
    # first; the filename only breaks a tie between files taken at the
    # same instant, where the sequence is still total (REQ-PIPE-061).
    parsed = {f: asset_time.parse_instant(when, f"received_at for {name}/{f}")
              for f, when in instants.items()}
    stated_original = dict(stated_original or {})
    filed_by = dict(filed_by or AUTOMATED)
    for filename in sorted(parsed, key=lambda f: (parsed[f], f)):
        record = {"delivery": name, "file": filename,
                  "received_at": asset_time.isoformat(parsed[filename]),
                  # WHICH CLOCK STAMPED IT (REQ-PIPE-105 criterion 4).
                  "received_from": received_from,
                  # THE ORDER THIS RECORD WAS WRITTEN (REQ-PIPE-061
                  # criterion 3), and the only fact available for
                  # breaking a tie between two arrivals sharing a
                  # receipt instant. Ours, like the instant beside it.
                  "sequence": sequence,
                  # WHO FILED IT (REQ-PIPE-147 criterion 6).
                  "filed_by": filed_by}
        if filename in stated_original:
            # UNDER ITS OWN KEY, MARKED AS A PERSON'S STATEMENT
            # (REQ-PIPE-103 criterion 10) - never in `received_at`.
            record["originally_received"] = {"value": stated_original[filename],
                                             "stated_by": "person"}
        with open(receipt_dir / f"{filename}.json", "w") as f:
            json.dump(record, f, indent=2)
        sequence += 1


def next_sequence(receipts_dir: Path | None = None) -> int:
    """The sequence the next receipt written here should carry.

    ONE MORE THAN THE HIGHEST ALREADY WRITTEN, read from the receipts
    themselves rather than from a counter file. A counter is a second
    piece of state that can disagree with the records it describes, and
    the records are the thing that has to be right.

    WHY A SEQUENCE AND NOT A WRITE TIMESTAMP (Keith, 2026-09-25, choosing
    between exactly those two). A write instant is simpler and needs no
    read-modify-write, and it can still tie - at which point the order
    falls back to whatever the sort does, which is the non-determinism
    criterion 3 exists to remove. A sequence is total: two receipts can
    never share one.

    THE READ-MODIFY-WRITE IS REAL and is not defended here. Two writers
    racing would both read the same maximum and both claim it. In this
    PoC the receiving side is a single serial writer, and in a real
    deployment the ordering fact would come from the transport rather
    than be derived by reading a directory. Stated rather than hidden,
    because a future deployment inherits this function's behaviour and
    not this paragraph.
    """
    receipts_dir = Path(receipts_dir or RECEIPTS_DIR)
    if not receipts_dir.is_dir():
        return 1
    highest = 0
    for path in receipts_dir.rglob("*.json"):
        try:
            value = json.loads(path.read_text()).get("sequence")
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, int):
            highest = max(highest, value)
    return highest + 1


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
    receipts_dir = Path(receipts_dir or RECEIPTS_DIR)
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
    deliveries_dir = Path(deliveries_dir or DELIVERIES_DIR)
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
    receipt_dir = Path(receipts_dir or RECEIPTS_DIR) / name
    stated: dict[str, str] = {}
    filed_by: dict = dict(AUTOMATED)
    for filename in files:
        path = receipt_dir / f"{filename}.json"
        if not path.is_file():
            continue
        record = json.loads(path.read_text())
        if isinstance(record.get("filed_by"), dict) and record["filed_by"].get("kind"):
            filed_by = record["filed_by"]
        original = record.get("originally_received")
        if isinstance(original, dict) and original.get("value"):
            stated[filename] = original["value"]
    return stated, filed_by


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

    deliveries_dir = Path(deliveries_dir or DELIVERIES_DIR)
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
    file_arrival.py's own matcher legitimately survives: it matches
    whole S3 keys, which is the transport concern aws/'s handlers use.
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
