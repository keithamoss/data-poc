"""The on-disk delivery format's WRITER (REQ-GEN-043; split by REQ-PIPE-380
criterion 2, v6 Q1 SETTLED by Keith 2026-11-14): writing a delivery and its
receipts, the next receipt sequence, and the names a person's filing
records. Clearing a generator's deliveries, the names already taken and the
generator's bookkeeping moved to the generator's own writer,
generator/delivery_writer.py (REQ-GEN-386 criterion 7).

READ docs/delivery-format.md FIRST - it is the normative specification.

THE READER IS asset_model/delivery.py, and the cut sits at writing: reading
the delivery tree is shared configuration-and-tree reading, which the
generator's placement checks need through arrival recognition, but writing
the tree is the real pipeline's (hand filing calls this; the generator has a
writer of its own, REQ-GEN-386 criterion 7), so asset_model/ reads the tree
and writes it nowhere (REQ-PIPE-380 criterion 18).

"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from asset_model import asset_time
from asset_model import delivery as tree


# Characters that are illegal or awkward in a path on Windows and
# macOS. A delivery name is arbitrary, not unconstrained - this repo
# gets run on other people's machines.
_UNSAFE_IN_PATH = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


#: A stated original arrival a person said they do not know
#: (REQ-PIPE-103 criterion 13) - recorded as such, never as a time.
NOT_KNOWN = "not-known"

#: The four routes by which a person supplies a file (REQ-PIPE-103
#: criterion 7, REQ-PIPE-147 criterion 2) - a closed set.
HAND_FILING_ROUTES = ("file", "folder", "table", "s3")


def filed_by_person(route: str, who: str) -> dict:
    if route not in HAND_FILING_ROUTES:
        raise tree.DeliveryFormatError(f"{route!r} is not a hand-filing route - one of "
                                  f"{', '.join(HAND_FILING_ROUTES)}.")
    if not who:
        raise tree.DeliveryFormatError("a delivery a person filed must say who filed it.")
    return {"kind": "person", "route": route, "who": who}


def validate_delivery_name(name: str) -> str:
    """A delivery name is arbitrary but must be a usable directory name.

    Arbitrary is the point - see the spec - so this rejects only what
    would break a checkout on a non-Linux filesystem, never a shape.
    """
    if not name or name.strip() != name:
        raise tree.DeliveryFormatError(f"delivery name {name!r} is empty or has surrounding whitespace")
    if _UNSAFE_IN_PATH.search(name):
        raise tree.DeliveryFormatError(
            f"delivery name {name!r} contains a character that is illegal or awkward in a path "
            f"on Windows or macOS. A name may be anything a supplier would call a drop, but it "
            f"still has to be a directory somebody can check out.")
    if name in (".", "..") or name.endswith("."):
        raise tree.DeliveryFormatError(f"delivery name {name!r} is not a usable directory name")
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
    holds. See tree.RECEIVED_FROM_STORAGE above for why the distinction is
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
    deliveries_dir = deliveries_dir or tree.default_deliveries_dir()
    receipts_dir = receipts_dir or tree.default_receipts_dir()
    if received_from is None:
        received_from = (tree.RECEIVED_FROM_STORAGE if received_at is not None
                          else tree.RECEIVED_FROM_OUR_CLOCK)
    if received_from not in tree.RECEIPT_SOURCES:
        raise tree.DeliveryFormatError(
            f"{received_from!r} is not a receipt source - one of "
            f"{', '.join(tree.RECEIPT_SOURCES)}. There is no third answer and no "
            f"'unknown': a receipt that cannot say which clock stamped it cannot "
            f"be judged for lateness.")
    if received_at is None:
        received_at = asset_time.now()
    validate_delivery_name(name)
    if isinstance(received_at, Mapping):
        missing = sorted(set(files) - set(received_at))
        if missing:
            raise tree.DeliveryFormatError(
                f"delivery {name!r}: no receipt instant for {', '.join(missing)} - a file "
                f"with no instant has not been received, so it is not written as if it had")
        instants = {f: received_at[f] for f in files}
    else:
        instants = {f: received_at for f in files}
    if not files:
        raise tree.DeliveryFormatError(f"delivery {name!r} has no files - a delivery is an ARRIVAL, "
                                   f"and nothing arriving is not one")

    deliveries_dir, receipts_dir = Path(deliveries_dir), Path(receipts_dir)
    if receipts_dir == deliveries_dir or deliveries_dir in receipts_dir.parents:
        raise tree.DeliveryFormatError(
            f"the receipts directory ({receipts_dir}) is inside the deliveries directory "
            f"({deliveries_dir}). The receipt record is ours and must live where a supplier "
            f"has no path to write it.")

    path = deliveries_dir / name
    if path.exists():
        raise tree.DeliveryFormatError(
            f"delivery {name!r} already exists at {path}. Two arrivals sharing a directory would "
            f"silently merge deliveries that never arrived together - pass a name that is unique "
            f"across the whole deliveries directory, not just within one writer.")
    path.mkdir(parents=True, exist_ok=True)
    for filename, content in files.items():
        if "/" in filename or "\\" in filename:
            raise tree.DeliveryFormatError(
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
                   files=None, received_from: str = tree.RECEIVED_FROM_STORAGE,
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
    receipts_dir = Path(receipts_dir or tree.default_receipts_dir())
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
    filed_by = dict(filed_by or tree.AUTOMATED)
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
    receipts_dir = Path(receipts_dir or tree.default_receipts_dir())
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
