"""An S3 object, recorded as a delivery and nothing else (REQ-PIPE-152).

THE OBJECT IS THE DELIVERY (criterion 1). Nothing is copied: what a handler
writes is REQ-PIPE-144's rows - one qa.delivery and one qa.delivery_file
naming the object's storage URI (criterion 2) - and the processing pass
builds the arrival from those rows and fetches the object when it comes to
stage it (criterion 6). There is no delivery directory and no receipt file.

ITS RECEIPT IS STORAGE'S (criterion 3): the object's own LastModified, which
is when the bucket took it, never the handler's clock. A handler invoked
minutes or a retry later still files the supply against the moment it
landed.

RECOGNITION IS THE ONE EVERY ROUTE USES (criterion 4): the dataset comes
from its declared pattern through arrivals.recognise(), exactly as for a
delivery on disk, and the run identity from recognition - never from the
object's key.

IDEMPOTENT (criterion 7): the delivery's name is built from the bucket, the
key and the object's own LastModified, so a retry of the same object names
the same delivery and records nothing twice (qa.delivery is write-once by
name), while a NEW object under the same key - a supplier re-sending a file -
is a new delivery, as it is on disk.
"""
from __future__ import annotations

import os
import re
import tempfile
import dataclasses
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

#: How a storage URI names where a recorded file lives (qa.delivery_file.
#: storage_uri, qa schema 33). A file on disk is named relative to the
#: deliveries directory, so a database restored on another machine still
#: finds it under that machine's own tree.
S3_SCHEME = "s3://"
LOCAL_SCHEME = "local:"


@dataclass(frozen=True)
class RecordedObject:
    delivery_name: str
    filename: str
    #: None where no dataset's pattern claimed it, or more than one did -
    #: unplaceable, reported on REQ-PIPE-057's terms (criterion 9).
    dataset_id: str | None
    #: False where a retry found it already recorded (criterion 7).
    newly_recorded: bool


def s3_uri(bucket: str, key: str) -> str:
    return f"{S3_SCHEME}{bucket}/{key}"


def split_s3_uri(uri: str) -> tuple[str, str]:
    bucket, _, key = uri[len(S3_SCHEME):].partition("/")
    return bucket, key


def delivery_name_for(bucket: str, key: str, received_at: datetime) -> str:
    """`s3-<bucket>-<key>-<receipt key>`, safe as a path segment."""
    from qa_tools.common import asset_time

    flat = re.sub(r"[^A-Za-z0-9._-]+", "-", f"{bucket}-{key}").strip("-")
    return f"s3-{flat}-{asset_time.arrival_key(received_at)}"


def receipt_of(s3_client, bucket: str, key: str) -> tuple[datetime, str]:
    """(instant, which clock) - the object's own LastModified where storage
    gives one (criterion 3), else ours, said so."""
    from qa_tools.common import asset_time, delivery

    head = s3_client.head_object(Bucket=bucket, Key=key)
    stamped = head.get("LastModified") if isinstance(head, dict) else None
    if isinstance(stamped, datetime) and stamped.tzinfo is not None:
        return stamped, delivery.RECEIVED_FROM_STORAGE
    return asset_time.now(), delivery.RECEIVED_FROM_OUR_CLOCK


def record_object(s3_client, bucket: str, key: str, *, conn=None) -> RecordedObject:
    """Record one arriving object as a delivery of one file, received
    automatically (criterion 10), and nothing else."""
    from qa_tools.common import arrivals, delivery, delivery_log, qa_store, supply_db

    filename = os.path.basename(key.rstrip("/"))
    received_at, source = receipt_of(s3_client, bucket, key)
    name = delivery_name_for(bucket, key, received_at)

    def _record(db) -> RecordedObject:
        qa_store.ensure_schema(db)
        # THE NEXT RECEIPT IN THE ORDER RECEIPTS WERE WRITTEN, the tiebreak
        # for two arrivals sharing an instant (REQ-PIPE-061 criterion 3).
        sequence = int(db.execute(
            f'SELECT COALESCE(MAX(receipt_sequence), 0) + 1 FROM "{qa_store.SCHEMA}".delivery_file'
        ).fetchone()[0])
        d = delivery.Delivery(
            name=name, path=Path(name), received_at=received_at, files=(filename,),
            anomalies=(), sequence=sequence, received_from=source,
            file_receipts={filename: (received_at, sequence, source)},
            filed_by=dict(delivery.AUTOMATED))
        found = arrivals.recognise(d)
        written = delivery_log.record(d, found, conn=db,
                                      storage_uris={filename: s3_uri(bucket, key)})
        claimed = [ds for ds, names in found.by_dataset.items() if filename in names]
        return RecordedObject(delivery_name=name, filename=filename,
                              dataset_id=claimed[0] if len(claimed) == 1 else None,
                              newly_recorded=written is not None)

    if conn is not None:
        return _record(conn)
    with supply_db.connect(label="mothman:s3-record") as db:
        return _record(db)


def materialise(arrival, *, s3_client=None, root: Path | None = None):
    """The arrival with its files on local disk, for the loaders - an S3
    object fetched through its recorded URI (criterion 6), a local one left
    exactly where it is. Returns the arrival unchanged where nothing is in
    S3."""
    from qa_tools.common import s3_source

    remote = {name: uri for name, uri in (getattr(arrival, "sources", ()) or ())
              if uri.startswith(S3_SCHEME)}
    if not remote:
        return arrival
    base = Path(root or tempfile.gettempdir()) / "mothman-arrivals" / arrival.delivery_name
    base.mkdir(parents=True, exist_ok=True)
    for name, uri in sorted(remote.items()):
        bucket, key = split_s3_uri(uri)
        target = base / name
        if not target.exists():
            s3_source.download_key(bucket, key, str(base), s3_client=s3_client)
    return dataclasses.replace(arrival, path=base)


#: How long a handler's pass may go on TAKING arrivals (criterion 12, Keith
#: 2026-10-06): a Lambda stops at fifteen minutes, and this leaves the
#: arrival in progress room to finish. A pass from the terminal or a
#: scheduler has no such budget.
HANDLER_BUDGET_SECONDS = 600


def handle_event(event: dict, s3_client, *, prefix: str, say=print,
                 budget_seconds: int = HANDLER_BUDGET_SECONDS) -> dict:
    """The whole of a handler (criteria 1-13): record every object the event
    carries under this handler's prefix, then run the processing pass - which
    stages, files, checks and gates in global receipt order. The handler
    itself does none of that (criterion 5), and never calls run_single
    (criterion 8).

    A PASS REFUSED FOR THE LOCK FAILS THE INVOCATION (criterion 13), after
    the recording, so the platform's retry finds the delivery recorded and
    the scheduled pass stays the backstop.
    """
    import json
    import time

    from qa_tools.common import processing_pass

    from urllib.parse import unquote_plus

    started = time.monotonic()
    summary = {"recorded": 0, "already_recorded": 0, "unplaceable": 0, "skipped": 0}
    not_recorded: list[str] = []
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        # S3 EVENT NOTIFICATIONS URL-ENCODE THE KEY (spaces as "+"), so a
        # name with a space or a bracket would fail on every retry read raw
        # (post-build-review #131 D2).
        key = unquote_plus(record["s3"]["object"]["key"])
        if not key.startswith(prefix):
            # WHICH OBJECTS ARE THIS HANDLER'S AT ALL is a transport concern
            # (REQ-PIPE-152's decision on whole-key matching); which DATASET
            # one belongs to is recognition's.
            say(f"{key!r} is outside {prefix!r} - not this handler's")
            summary["skipped"] += 1
            continue
        try:
            got = record_object(s3_client, bucket, key)
        except Exception as exc:  # noqa: BLE001 - named below, and the invocation fails
            # ONE OBJECT THAT CANNOT BE READ DOES NOT STOP THE REST (#131 D2):
            # they are recorded and passed, and the invocation still fails at
            # the end so the platform retries - a retry records nothing twice.
            say(f"{key!r} could not be recorded: {_redact_error(exc)}")
            not_recorded.append(key)
            continue
        summary["recorded" if got.newly_recorded else "already_recorded"] += 1
        if got.dataset_id is None:
            # UNPLACEABLE, ON THE PIPELINE'S OWN TERMS (criterion 9): recorded
            # with no dataset, which the outstanding queue reports, and the
            # event's other objects carry on.
            summary["unplaceable"] += 1
            say(f"{key!r}: no single dataset's pattern claims {got.filename!r} - recorded "
                f"as delivery {got.delivery_name} and reported, not processed")
    deadline = started + budget_seconds
    with processing_pass.pass_lock("lambda"):
        report = processing_pass.run_pass(run_by="automated:lambda", say=say,
                                          deadline=deadline, s3_client=s3_client)
    summary.update(processed=len(report.processed), gated_only=len(report.gated_only),
                   left_for_next_pass=len(report.left_for_budget),
                   failures=len(report.failures), exit_status=report.exit_status)
    if not_recorded:
        raise ObjectsNotRecorded(
            f"{len(not_recorded)} object(s) could not be recorded and will be tried again: "
            + ", ".join(repr(k) for k in not_recorded))
    return {"statusCode": 200, "body": json.dumps(summary)}


def _redact_error(exc: BaseException) -> str:
    """An error for a log line, without the database password should one have
    found its way into the message."""
    from qa_tools.common import supply_db

    text = f"{type(exc).__name__}: {exc}"
    try:
        password = supply_db.connection_fields().get("password")
    except Exception:  # noqa: BLE001 - no DSN configured, nothing to hide
        password = None
    return text.replace(password, "***") if password else text


class ObjectsNotRecorded(RuntimeError):
    """Some of an event's objects could not be recorded; the rest were, and
    the pass ran. Raised so the invocation fails and the platform retries."""
