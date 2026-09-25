"""One committed file per delivery, written once at recognition
(REQ-PIPE-069).

WHAT ARRIVED, AND WHAT WE THOUGHT IT WAS. Nothing else. The record of an
arrival has to outlive the warehouse that held it and be readable
without one, which is why it is committed rather than a table.

RECOGNITION HAPPENS BEFORE LOADING, and that ordering was got wrong once
already: a file written at recognition cannot carry load outcomes,
because none exist yet. So there are two files at two moments and
neither is ever rewritten - this one holds RECOGNITION facts, and
REQ-PIPE-060's processing log holds LOAD facts. Attribution ("this file
is cp_clients") is a recognition fact, decided by a pattern match before
any load is attempted. The physical table it became
("staging.cp_clients__run_003") is a load fact and belongs over there.

Two reasons attribution stays here beyond that. NOT EVERYTHING
ATTRIBUTED REACHES A LOAD - a file two datasets both claim is held and
attributed to neither, an unloadable file gets no table at all - so a
supply recognised but never loaded would otherwise have no record of
what we thought it was. And REQ-PIPE-058's collision gate wants PAIRS of
filename and dataset: keeping both here makes that one read rather than
a join across two logs.

EVERY FILE BY THE NAME IT ARRIVED UNDER, not every table (Keith,
2026-09-24). The drafted wording said "every table it carried", which
fails twice. Attribution reads a file's NAME, not a logical table name,
so the gate needs names. And a JUNK FILE - a Word document, a PDF,
somebody's test PNG - is not a table and has no dataset, so it would
never have been recorded at all. That second half is the sharper one:
REQ-PIPE-057 requires every artefact we declined to act on be recorded
"alongside the delivery it came in, so that a supplier changing their
extract is visible rather than silent", and THIS FILE is what
"alongside the delivery" means. Without it the warning fires once at
recognition and the durable record loses it, so a supplier drifting
over time is invisible unless somebody happened to be watching that
run.

PRIVACY, entered with eyes open rather than discovered later. This repo
is public, so a recorded filename becomes a published string. A
systematic extract name like `birth_registrations_2026-08-28.csv` is
impersonal; a stray `notes_for_jenny_re_case_4471.docx` is not, and it
is exactly the kind of file that lands in a delivery by accident.
Contents are still never read and never recorded - the NAME is, and it
is now durably committed rather than fleeting. Keith accepted that
knowingly on 2026-09-24; redaction was raised as an alternative and not
taken. Today's filenames are synthetic, and the real-deployment
judgement should be made on real-deployment terms rather than inherited
from this PoC.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from qa_tools.common import asset_time
from qa_tools.common import holds

ROOT = Path(__file__).resolve().parent.parent.parent

#: Its own tree, beside the QA results rather than inside them: a
#: delivery spans datasets and is not a QA result, and qa_results/ is
#: keyed by agency and collection while a delivery may be for several
#: (criterion 2).
DELIVERY_LOG_DIR = ROOT / "delivery_log"

#: A delivery's name is supplier-controlled and becomes a filename. The
#: PoC's own names already contain spaces, so this is a real transform
#: rather than a defensive formality.
_UNSAFE = re.compile(r"[^0-9A-Za-z._-]+")


class DeliveryLogError(RuntimeError):
    """Something that would corrupt the record rather than merely fail
    to write it."""


def path_for(delivery, log_dir: Path | None = None) -> Path:
    """This delivery's committed record.

    THE NAME CARRIES THE RECEIPT INSTANT, and that is a performance
    contract rather than decoration (REQ-PIPE-034's own non-functional
    constraint). Answering "when did this dataset last arrive" must not
    cost a walk of every arrival ever received - and with names that
    sort arbitrarily, the only way to find the newest delivery holding
    one dataset is to open all of them. Sorting by name here IS sorting
    by receipt, so that walk runs newest-first and stops at the first
    hit, bounded by deliveries since that dataset last supplied.

    IT CARRIES THE INSTANT AND NOT THE RECEIPT SEQUENCE, and the
    difference is a real defect this had for one evening. The sequence
    is re-issued when the synthetic data is regenerated - the same
    delivery, the same instant, a different number - so a filename
    built from it produced a SECOND record for every delivery, and the
    write-once guard below never fired because it only asked whether
    THAT path existed. Measured: 120 records for 60 deliveries, and
    every dataset's arrival history exactly doubled.

    THE GENERAL RULE, because this will be reachable for again: a
    write-once record whose filename encodes a MUTABLE value is not
    write-once. The instant is a fact about the arrival; the sequence
    is a fact about the receipt WE wrote, and only the first is stable.
    Ordering ties are broken by the receipt's own sequence at the point
    ordering is decided, which does not need it to be in this name.

    Takes a Delivery rather than a name, because a name alone cannot
    produce this filename.
    """
    directory = Path(log_dir or DELIVERY_LOG_DIR)
    safe = _UNSAFE.sub("_", delivery.name).strip("._") or "unnamed"
    return directory / f"{asset_time.arrival_key(delivery.received_at)}--{safe}.json"


def _existing_record(delivery_name: str, log_dir: Path | None = None) -> Path | None:
    """This delivery's committed record under ANY filename.

    Globbed on the delivery's own safe name rather than on a full path,
    so a change to how records are named can never again defeat the
    write-once rule silently.
    """
    directory = Path(log_dir or DELIVERY_LOG_DIR)
    if not directory.is_dir():
        return None
    safe = _UNSAFE.sub("_", delivery_name).strip("._") or "unnamed"
    for path in sorted(directory.glob(f"*--{safe}.json")):
        return path
    legacy = directory / f"{safe}.json"
    return legacy if legacy.is_file() else None


def record(delivery, recognition, log_dir: Path | None = None) -> Path | None:
    """Commit what this delivery was, once.

    WRITTEN ONCE AND NEVER REWRITTEN (criterion 1). A delivery already
    logged is left exactly as it was: what a later run would write is
    the same recognition of the same files, and a record that can be
    rewritten is one nobody can trust to be what was seen at the time.
    A delivery spanning collections is recognised by both orchestrators,
    so the second call being a no-op is the ordinary case rather than a
    guard against a bug.

    Returns the path written, or None where one already existed.
    """
    path = path_for(delivery, log_dir)
    # WRITE-ONCE BY DELIVERY, not by path. Asking only whether this
    # exact filename exists is what let a re-issued receipt sequence
    # write a second record for a delivery already logged, so the guard
    # now asks the question the criterion actually asks.
    if _existing_record(delivery.name, log_dir) is not None:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)

    attributed = {name: dataset_id
                  for dataset_id, names in recognition.by_dataset.items()
                  for name in names}
    contested = {name: list(claimants)
                 for name, claimants in recognition.contested.items()}

    payload = {
        "delivery": delivery.name,
        # THE OFFSET IS PRESERVED (criterion 5). asset_time already
        # refuses a naive instant, and isoformat() carries the offset
        # it was recorded with - normalising to UTC here would throw
        # away which clock the receiving side was on, which is the
        # whole point of REQ-PIPE-048.
        "received_at": delivery.received_at.isoformat(),
        "collections": list(recognition.collections),
        "files": [
            {"filename": name,
             "dataset_id": attributed.get(name),
             # A file two datasets both claim is attributed to NEITHER,
             # and saying which two is the difference between a record
             # somebody can act on and one that just says "no".
             "contested_by": contested.get(name)}
            for name in sorted(delivery.files)
        ],
        # HELD SUPPLIES (REQ-PIPE-059 criterion 4). Derivable from
        # `files` - two entries carrying one dataset_id - and stated
        # anyway, because the question a person opens this with is
        # "what was held and what could it not choose between", and
        # making them compute it from a file list is how a queue stops
        # being drained.
        "held": [{"dataset_id": h.dataset_id, "files": list(h.files)}
                  for h in holds.holds_in(recognition)],
        # Recorded, never read. A receipt lookalike or a supplier's own
        # manifest is excluded from `files` on purpose, so this is the
        # only place their presence survives.
        "anomalies": list(delivery.anomalies),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")
    return path


def prune(present: set[str] | frozenset[str], log_dir: Path | None = None) -> list[str]:
    """Remove records for deliveries that no longer exist.

    Criterion 6 asks that the log never describe a history that no
    longer exists, and says so as "regenerate from scratch, under the
    same delete-and-regenerate rule". THIS PRUNES INSTEAD OF WIPING,
    and the narrowing is deliberate rather than a shortcut.

    A wipe is destructive between the delete and the rewrite, and that
    is not theoretical: the first version cleared the whole log at the
    top of `mothman pipeline run`, and the test suite - which invokes
    that command with the real work stubbed out - deleted sixty
    committed records on the next gate run. Nothing rewrote them,
    because the thing that would have was the part being stubbed.

    Pruning reaches the same end state for every case that can actually
    arise. Records are write-once by criterion 1, so a record for a
    delivery still present is BY DEFINITION what a regeneration would
    write again; the only records a wipe removes and a rebuild does not
    restore are exactly the ones for deliveries that are gone, which is
    what this removes.

    Returns the names removed, because a silent delete of committed
    files is the wrong shape even when it is correct.
    """
    directory = Path(log_dir or DELIVERY_LOG_DIR)
    if not directory.is_dir():
        return []
    gone = []
    for path in sorted(directory.glob("*.json")):
        try:
            name = json.loads(path.read_text()).get("delivery")
        except (OSError, json.JSONDecodeError):
            # Unreadable AND unattributable to a delivery: it cannot be
            # checked against what is present, and it fails the gate
            # that reads this log. Removing it is the only outcome that
            # leaves the log in a state anything can use.
            path.unlink()
            gone.append(path.name)
            continue
        if name not in present:
            path.unlink()
            gone.append(name)
    return gone


def records(log_dir: Path | None = None) -> list[dict]:
    """Every committed delivery record, oldest receipt first.

    A malformed one RAISES rather than being skipped, unlike the
    in-flight observations: this is the corpus REQ-PIPE-058's collision
    gate reads, and a gate that quietly ignores what it cannot parse is
    a gate that passes for the wrong reason.
    """
    directory = Path(log_dir or DELIVERY_LOG_DIR)
    if not directory.is_dir():
        return []
    out = []
    for path in sorted(directory.glob("*.json")):
        try:
            out.append(json.loads(path.read_text()))
        except (OSError, json.JSONDecodeError) as exc:
            raise DeliveryLogError(
                f"{path} is in the delivery log and cannot be read ({exc}). This is "
                f"REQ-PIPE-058's collision corpus, so a record that cannot be parsed "
                f"is not something to pass over.") from exc
    return sorted(out, key=lambda r: r.get("received_at", ""))


def sql(log_dir: Path | None = None) -> str:
    """A SELECT over the committed files themselves (criterion 4).

    DuckDB reads the JSON straight off disk, so the log is queryable
    and joinable against the staging and period schemas with NOTHING
    SYNCED and nothing duplicated. A second copy in the warehouse was
    rejected as two records that can drift, for no gain.

    Returns SQL rather than running it, because running it would mean
    opening a database, and the committed-history path may not.
    """
    directory = Path(log_dir or DELIVERY_LOG_DIR)
    return (f"SELECT delivery, received_at, collections, files, anomalies "
            f"FROM read_json_auto('{directory}/*.json')")
