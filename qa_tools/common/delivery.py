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
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from qa_tools.common import arrival_patterns, asset_time

ROOT = Path(__file__).resolve().parent.parent.parent
DELIVERIES_DIR = ROOT / "data" / "deliveries"
RECEIPTS_DIR = ROOT / "data" / "receipts"
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

    @property
    def file_paths(self) -> tuple[Path, ...]:
        return tuple(self.path / name for name in self.files)


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
        receipt = receipts_dir / f"{name}.json"
        if receipt.exists():
            receipt.unlink()
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


def write_delivery(name: str, files: dict[str, str | bytes], received_at: datetime,
                    deliveries_dir: Path | None = None,
                    receipts_dir: Path | None = None) -> Path:
    """Writes one delivery and its receipt record, and returns the
    delivery's own directory.

    `files` maps a file name to its content. Content is written
    verbatim - a caller wanting a file that cannot be parsed as the
    format its name claims simply passes content that cannot be
    (criterion 10), and one matching no dataset pattern passes a name
    that does not match (criterion 9). Neither is a special case here.

    The receipt is written to a SEPARATE directory, which is what makes
    it ours. Passing a `receipts_dir` inside `deliveries_dir` is
    refused, because that would hand a supplier a path to our clock.
    """
    deliveries_dir = deliveries_dir or DELIVERIES_DIR
    receipts_dir = receipts_dir or RECEIPTS_DIR
    validate_delivery_name(name)
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

    receipts_dir.mkdir(parents=True, exist_ok=True)
    with open(receipts_dir / f"{name}.json", "w") as f:
        json.dump({"delivery": name,
                   "received_at": asset_time.isoformat(
                       asset_time.parse_instant(received_at, f"received_at for delivery {name!r}"))},
                   f, indent=2)
    return path


def read_receipt(name: str, receipts_dir: Path | None = None) -> datetime:
    """Our recorded receipt instant for one delivery.

    A missing receipt is a hard error, not a fallback to a file's mtime:
    an arrival we have no record of receiving is a gap to notice, and
    inventing a time for it would hide exactly the thing worth seeing.
    """
    receipts_dir = Path(receipts_dir or RECEIPTS_DIR)
    path = receipts_dir / f"{name}.json"
    if not path.exists():
        raise DeliveryFormatError(
            f"delivery {name!r} has no receipt record at {path}. The receipt is written by the "
            f"receiving side; an arrival with none is a gap to investigate, and this will not "
            f"fall back to a file modification time.")
    with open(path) as f:
        record = json.load(f)
    return asset_time.parse_instant(record["received_at"], f"received_at in {path}")


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

    return Delivery(name=name, path=path,
                     received_at=read_receipt(name, receipts_dir),
                     files=tuple(files), anomalies=tuple(anomalies))


def list_deliveries(deliveries_dir: Path | None = None,
                     receipts_dir: Path | None = None) -> list[Delivery]:
    """Every delivery on disk, OLDEST RECEIPT FIRST.

    Ordered by our own receipt instant, never by directory name -
    a delivery name is arbitrary and means nothing, so sorting by it
    would be inventing an order out of a supplier's naming habits.
    """
    deliveries_dir = Path(deliveries_dir or DELIVERIES_DIR)
    if not deliveries_dir.is_dir():
        return []
    out = [read_delivery(p.name, deliveries_dir, receipts_dir)
           for p in sorted(deliveries_dir.iterdir()) if p.is_dir()]
    return sorted(out, key=lambda d: d.received_at)


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
