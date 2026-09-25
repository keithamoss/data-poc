"""What a run observed in flight (REQ-PIPE-057 criteria 5 and 7).

THE SUBJECT OF THIS RECORD IS THE RUN, not the delivery, and that is
what made the problem solvable rather than a detail of phrasing.
Committing "delivery X is in flight" is a permanent record about
something we have not accepted, sitting in history beside records of
things that actually happened. Committing "the run at 14:32 observed
these deliveries in flight" is a record about the RUN, which genuinely
happened and genuinely saw that. The as-at framing is then honest
labelling rather than a caveat - and it is what this dashboard already
is, since CURRENT_AS_OF and the snapshot archive rest on the same
premise.

WHY IT HAD NOWHERE ELSE TO GO. A delivery is treated as received only
where our own receipt exists, and REQ-PIPE-069 writes a delivery's
committed file AT RECOGNITION - so an in-flight delivery, having no
receipt, is never recognised and leaves no committed trace at all.
Criterion 5 nonetheless requires it reported on every run, and the
dashboard is the only reader of committed history. The thing that had
to be reported had nowhere to land.

FILENAMES, NOT A COUNT. A count answers "is anything in flight"; the
question worth asking is "is anything STUCK", and three deliveries
flowing through look identical to the same three sitting there for a
week. A file list going 2, 4, 6 across runs reads as an upload
progressing; one stuck at 2 reads as one that died. Reading a directory
listing records no contents, which is the same line drawn everywhere
else here - the NAME is recorded so a person can act on it, and a
filename in a Birth Registrations or Child Protection context is itself
potentially identifying, which is why the line is stated rather than
assumed.

THESE RECORDS CHURN, which no other committed record here does. An
in-flight delivery is mid-upload by definition, so its file list
legitimately differs run to run - that difference IS the signal, and it
makes this the one committed record expected to change between
observations rather than written once and left alone.

NOTHING IS WRITTEN WHEN NOTHING IS IN FLIGHT. "The run saw nothing" is
the ordinary state of most runs, and a file per run saying so would be
churn carrying no signal. Criterion 7 asks for a record WHERE such a
delivery is present, which is exactly this.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OBSERVATIONS_DIR = ROOT / "observations" / "in_flight"

#: A run timestamp becomes a filename, so it is reduced to characters
#: that are a filename everywhere rather than trusted to be.
_UNSAFE = re.compile(r"[^0-9A-Za-z]+")


def _filename(collection_id: str, observed_at: str) -> str:
    return f"{_UNSAFE.sub('-', collection_id)}-{_UNSAFE.sub('', observed_at)}.json"


def record(collection_id: str, observed_at: str, in_flight,
            observations_dir: Path | None = None) -> Path | None:
    """Commit what this run saw in flight, or nothing at all.

    Returns the path written, or None where there was nothing to
    observe.
    """
    if not in_flight:
        return None
    directory = Path(observations_dir or OBSERVATIONS_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / _filename(collection_id, observed_at)
    payload = {
        "observed_at": observed_at,
        "observed_by": collection_id,
        "in_flight": [{"delivery": entry.name, "files": list(entry.files)}
                       for entry in sorted(in_flight, key=lambda e: e.name)],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def observations(observations_dir: Path | None = None) -> list[dict]:
    """Every committed observation, newest first.

    Read by the dashboard, which frames them as at the last
    regeneration. A malformed one is skipped rather than fatal: this is
    a report about something odd, and a report that cannot be rendered
    should not take the page down with it.
    """
    directory = Path(observations_dir or OBSERVATIONS_DIR)
    if not directory.is_dir():
        return []
    out = []
    for path in sorted(directory.glob("*.json")):
        try:
            out.append(json.loads(path.read_text()))
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(out, key=lambda r: r.get("observed_at", ""), reverse=True)
