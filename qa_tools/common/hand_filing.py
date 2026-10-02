"""Filing a supply somebody received by hand (REQ-PIPE-103).

THE WHOLE POINT IS THAT THERE IS NO SECOND MECHANISM. A supply
emailed to an analyst, or fetched from S3 by hand, is an arrival like
any other: it gets a delivery directory, a receipt written by our own
clock, and a run id from recognition. What this module adds is not a
side channel but the two or three lines that turn "a path the
operator typed" into exactly the shape `data/deliveries/` already
holds.

A NAME THAT RECOGNITION CANNOT PLACE IS REFUSED, and this was the one
real fork in the design (Keith, 2026-09-27). Recognition reads a
file's own NAME against its dataset's arrival pattern, and a file
somebody was emailed is often called something else - `Births
Jan.csv`, `extract (3).csv`. Three things were possible and two were
worse:

  RENAME IT to match the pattern, since the command already says which
  dataset it is. Keeping would always work, and the delivery tree
  would stop being a faithful copy of what actually arrived - it would
  hold a file the supplier never sent.

  FILE IT ANYWAY and let it sit unplaceable. Honest about the arrival,
  and it splits the check from the arrival: a QA run attributed to
  nothing, which is the exact failure the supply model exists to
  close.

  REFUSE, which is what this does. `check()` says precisely which file
  could not be placed and what the pattern wants, nothing is filed,
  and the operator can rename the file or run it as a TRIAL instead
  (qa_tools/common/trial.py) - a trial needs no recognition, because
  the command already says which dataset is being checked.

THE OPERATOR'S OWN FILENAME BECOMES PUBLIC (this requirement's first
non-functional constraint). This repository is public and the
delivery log records real names; generated names entered that with
eyes open, and this is the first route by which a name we did not
choose gets there. The caller prompts with that consequence visible -
see cli/common.py's own confirmation - rather than this module
deciding quietly on somebody's behalf.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from qa_tools.common import arrivals, asset_time, delivery, delivery_log

#: What a hand-filed delivery's directory is called.
#:
#: NOT THE OPERATOR'S FILE NAME, and not because of the privacy point
#: above - the FILES inside carry that either way, since recognition
#: reads them. It is because a directory name has to be unique across
#: the whole tree for ever (delivery.write_delivery refuses a
#: collision), and two people checking their own copy of
#: `birth_registrations_2026-09-20.csv` on different days is an
#: ordinary Tuesday. The instant is what makes it unique; the prefix
#: is what makes it recognisable in a listing as something a person
#: filed rather than something that arrived on its own.
HAND_FILED_PREFIX = "handfiled"


class CannotFile(Exception):
    """Raised where filing would record something untrue - a file no
    dataset's pattern claims, or one two datasets both claim. Carries
    the operator-facing explanation, because the caller's job is to
    print it and offer a trial rather than to re-derive why."""


def delivery_name(received_at: datetime) -> str:
    return f"{HAND_FILED_PREFIX}-{asset_time.isoformat(received_at)[:19]}".replace(":", "")


def check(paths) -> None:
    """Refuse, with a usable explanation, anything recognition could
    not place. Silent where every file is placeable.

    BEFORE ANYTHING IS WRITTEN. Filing and then discovering the
    problem would leave a delivery directory and a receipt behind for
    somebody to clean up, and a receipt is a claim about when we
    received something - not a thing to write speculatively.
    """
    problems = []
    for path in paths:
        name = Path(path).name
        dataset = delivery.dataset_for_filename(name)
        if dataset is None:
            problems.append(
                f"  {name}\n"
                f"      matches no dataset's arrival pattern, so filing it would "
                f"record an arrival nothing can read")
    if problems:
        raise CannotFile(
            "these files cannot be filed as a delivery:\n"
            + "\n".join(problems)
            + "\n\n  A delivery's run identity comes from recognising its files by "
              "name, so a file we cannot place has no run to be. Rename it to match "
              "the dataset's pattern and try again, or run the check as a TRIAL - "
              "the same four tools against the same rows, recorded nowhere.")


@dataclass(frozen=True)
class Filed:
    """What a filed supply is, once it is one.

    `paths` ARE THE DELIVERY'S OWN COPIES, not the ones the operator
    typed, and that is the point rather than a detail: from here on
    this supply is read the same way a delivery that arrived on its
    own is read, from the tree that holds what arrived. Staging the
    operator's original would leave the check reading one file and
    the record describing another.
    """

    delivery_name: str
    run_id: str
    paths: tuple[str, ...]
    received_at: datetime | None


def file_supply(paths, collection_id: str, run_id_prefix: str,
                 received_at: datetime | None = None,
                 deliveries_dir=None, receipts_dir=None) -> Filed:
    """File these files as one real delivery.

    ONE DELIVERY, however many files - a folder the operator handed us
    arrived together, and a delivery is the transport unit. Splitting
    it into one delivery per file would invent arrivals that never
    happened.

    `received_at` IS OUR OWN CLOCK and defaults to now, which is the
    only honest reading: we know when WE received it, never when it
    was sent. Filing renumbers nothing already recorded - this
    requirement's second non-functional constraint - because a run id
    is the staged table's spelling at its receipt instant rather than a
    position (REQ-PIPE-105, 2026-10-02).

    ONE DELIVERY IS STILL SEVERAL ARRIVALS where it holds several files;
    `Filed.run_id` is the first, and arrivals_of() gives all of them.
    """
    check(paths)
    received_at = received_at or asset_time.now()
    name = delivery_name(received_at)
    files = {}
    for path in paths:
        p = Path(path)
        # BYTES, NOT TEXT. A delivery holds what the supplier sent, and
        # decoding-then-re-encoding would quietly normalise a BOM, a
        # line ending or an encoding we were meant to notice.
        files[p.name] = p.read_bytes()
    # OUR CLOCK, SAID OUT LOUD (REQ-PIPE-105 criterion 4). An operator
    # hands us a folder; nothing recorded when storage took it, because
    # storage did not take it - we did. The alternative available here is
    # the files' own mtimes, which is exactly what criterion 3 rules out:
    # an mtime survives a copy, so it can be a timestamp the SUPPLIER set.
    directory = delivery.write_delivery(
        name, files, received_at=received_at,
        deliveries_dir=deliveries_dir, receipts_dir=receipts_dir,
        received_from=delivery.RECEIVED_FROM_OUR_CLOCK)

    # THE RUN ID COMES BACK FROM RECOGNITION, never from the caller
    # (criterion 1). Asking for it rather than computing it is what
    # makes a hand-filed supply indistinguishable downstream from one
    # that arrived on its own.
    # AND IT GOES IN THE DELIVERY LOG NOW, not at the next pipeline
    # run. The log is what the dashboard's arrival history is built
    # from, and "only automated deliveries get a delivery log entry"
    # is the observation this whole requirement started from - a
    # hand-received supply that has to wait for an unrelated command
    # to become visible is the same gap one step smaller. Recording
    # it here is also safe against the prune: `mothman pipeline run`
    # prunes the log against the deliveries actually on disk, and
    # this one is.
    for d in delivery.list_deliveries(deliveries_dir, receipts_dir):
        if d.name == name:
            delivery_log.record(d, arrivals.recognise(d))
            break

    for arrival in arrivals.arrivals_for(collection_id, run_id_prefix,
                                          deliveries_dir=deliveries_dir,
                                          receipts_dir=receipts_dir):
        if arrival.delivery_name == name:
            return Filed(delivery_name=name, run_id=arrival.run_id,
                         paths=tuple(str(directory / f) for f in files),
                         received_at=received_at)
    raise CannotFile(
        f"filed delivery {name!r} but recognition did not place it in "
        f"collection {collection_id!r} - nothing in it belongs to that "
        f"collection. The delivery is on disk; no run was started.")


def arrivals_of(filed: Filed, collection_id: str, run_id_prefix: str,
                deliveries_dir=None, receipts_dir=None) -> list:
    """Every arrival a filed delivery became, in processing order.

    ONE DELIVERY, SEVERAL ARRIVALS (REQ-PIPE-105 criterion 1): the
    delivery is the transport unit and a FILE is the arrival, so a
    six-file folder is six runs. `Filed.run_id` names the first of them
    and is kept for the one-file case, where it is the whole answer.
    """
    return [a for a in arrivals.arrivals_for(collection_id, run_id_prefix,
                                              deliveries_dir=deliveries_dir,
                                              receipts_dir=receipts_dir)
            if a.delivery_name == filed.delivery_name]
