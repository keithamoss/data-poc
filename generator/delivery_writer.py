"""The GENERATOR'S delivery writer (REQ-GEN-386 criterion 7, v6 Q1 SETTLED by
Keith 2026-11-14): writing a synthetic delivery's files and receipts in the
layout docs/delivery-format.md specifies - the layout the real pipeline's
writer (qa_tools/common/delivery.py, which hand filing calls) writes and
asset_model/delivery.py reads - and the generator-only functions beside it:
clearing what the generator wrote last time, the names already taken, and its
bookkeeping file.

A SECOND WRITER, ACCEPTED, HELD TO THE FIRST BY A TEST: the generator may not
import the real pipeline (REQ-TEST-384), and the pipeline keeps its writer for
hand filing, so the format has two writers and one reader.
tests/test_delivery_writers_agree.py writes the same deliveries through both
into two empty trees and fails on a single differing byte, or where the one
reader reads either back differently.

ONLY WHAT A GENERATOR WRITES: an automated delivery, stamped by storage or
our clock. A person's filing - its route, who filed it and a stated original
arrival - is the real pipeline's alone.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from asset_model import asset_time, assets
from asset_model import delivery as tree


#: The generator's bookkeeping file's name - named here and only here (it left
#: qa_tools/common/delivery.py with REQ-GEN-386 criterion 7) (REQ-GEN-043 criterion 7, tests/test_arrivals.py).
BOOKKEEPING_FILE = "generator_bookkeeping.json"


def bookkeeping_path() -> Path:
    """The selected asset's generator bookkeeping, at call time."""
    return assets.data_path(BOOKKEEPING_FILE)

# Characters that are illegal or awkward in a path on Windows and
# macOS. A delivery name is arbitrary, not unconstrained - this repo
# gets run on other people's machines.
_UNSAFE_IN_PATH = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


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
                   received_from: str | None = None) -> Path:
    """Writes one synthetic delivery and one receipt per file, and returns
    the delivery's own directory - refused as the pipeline's writer refuses:
    a receipt source outside the closed set, a file with no instant, an empty
    delivery, receipts inside the deliveries, a name already taken, or a file
    name carrying a path separator."""
    deliveries_dir = deliveries_dir or tree.default_deliveries_dir()
    receipts_dir = receipts_dir or tree.default_receipts_dir()
    if received_from is None:
        received_from = (tree.RECEIVED_FROM_STORAGE if received_at is not None
                         else tree.RECEIVED_FROM_OUR_CLOCK)
    if received_from not in tree.RECEIPT_SOURCES:
        raise tree.DeliveryFormatError(
            f"{received_from!r} is not a receipt source - one of "
            f"{', '.join(tree.RECEIPT_SOURCES)}.")
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
            f"({deliveries_dir}) - the receipt record is ours")
    path = deliveries_dir / name
    if path.exists():
        raise tree.DeliveryFormatError(
            f"delivery {name!r} already exists at {path} - a name must be unique across the "
            f"whole deliveries directory")
    path.mkdir(parents=True, exist_ok=True)
    for filename, content in files.items():
        if "/" in filename or "\\" in filename:
            raise tree.DeliveryFormatError(
                f"delivery {name!r}: file name {filename!r} contains a path separator - a "
                f"delivery is one flat drop, not a tree")
        mode, payload = ("wb", content) if isinstance(content, bytes) else ("w", content)
        with open(path / filename, mode) as f:
            f.write(payload)
    write_receipts(name, instants, receipts_dir, received_from=received_from)
    return path


def write_receipts(name: str, received_at: "datetime | Mapping[str, datetime]",
                   receipts_dir: Path | None = None, *, files=None,
                   received_from: str = tree.RECEIVED_FROM_STORAGE,
                   sequence: int | None = None) -> None:
    """One receipt per file of an automated delivery, in receipt order, each
    carrying the next sequence - the receipt format of docs/delivery-format.md."""
    receipts_dir = Path(receipts_dir or tree.default_receipts_dir())
    instants = (dict(received_at) if isinstance(received_at, Mapping)
                else {f: received_at for f in (files or ())})
    receipt_dir = receipts_dir / name
    receipt_dir.mkdir(parents=True, exist_ok=True)
    if sequence is None:
        sequence = next_sequence(receipts_dir)
    parsed = {f: asset_time.parse_instant(when, f"received_at for {name}/{f}")
              for f, when in instants.items()}
    for filename in sorted(parsed, key=lambda f: (parsed[f], f)):
        record = {"delivery": name, "file": filename,
                  "received_at": asset_time.isoformat(parsed[filename]),
                  "received_from": received_from,
                  "sequence": sequence,
                  "filed_by": dict(tree.AUTOMATED)}
        with open(receipt_dir / f"{filename}.json", "w") as f:
            json.dump(record, f, indent=2)
        sequence += 1


def next_sequence(receipts_dir: Path | None = None) -> int:
    """One more than the highest sequence already written here, read from the
    receipts themselves."""
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
    deliveries_dir = Path(deliveries_dir or tree.default_deliveries_dir())
    receipts_dir = Path(receipts_dir or tree.default_receipts_dir())
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
    deliveries_dir = Path(deliveries_dir or tree.default_deliveries_dir())
    if not deliveries_dir.is_dir():
        return set()
    return {p.name for p in deliveries_dir.iterdir() if p.is_dir()}
