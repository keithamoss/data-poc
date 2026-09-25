"""A recognition change must never quietly re-key committed QA history
(REQ-PIPE-057 criterion 19).

THE FRAGILITY THIS GUARDS. A run id is assigned from a delivery's
POSITION in the receipt-ordered, collection-filtered list that
recognition produces - `run_001`, `run_002`, and so on. Every committed
path under `qa_results/<agency>/<collection>/<run_id>/` is keyed by that
number. So anything that changes what is in that list renames committed
history: a delivery that starts being skipped shifts every later run
down one, and a delivery that starts being recognised shifts every later
run up one.

REQ-PIPE-057 does both. A receipt-less delivery becomes skipped where it
used to take the whole run down with it, and a delivery spanning
collections now joins two sequences instead of raising. Neither change
mentions `qa_results/` anywhere, which is exactly why the
delivery-architect called this the likeliest "we found out when CI went
red" item in the batch: the change looks local to recognition and the
breakage is in paths nothing in the requirement names.

SO IT FAILS, LOUDLY, NAMING THE RUNS. Re-keying committed history is
REQ-PIPE-038's job, under its own delete-and-regenerate rule and Keith's
one-off regeneration exception - not something recognition may do as a
side effect while nobody is looking.

WHAT THIS IS NOT. It is not criterion 18, which asks for the derivation
to stop being positional in the first place. That has no replacement
named anywhere in the requirement, and Keith's call on 2026-09-25 was
that a run's durable identity belongs with REQ-PIPE-069's delivery log -
where a delivery gets a committed record of its own - rather than a
mapping built here that 069 would absorb almost immediately. So the
fragile derivation survives three more requirements and this guard is
what makes that survivable: the failure mode it leaves behind is a named
error rather than a silent rename.

IT LIVES IN THE PIPELINE RUN, NOT IN `mothman check`. Reading it needs
`data/deliveries/`, and no gate CI runs may open anything under `data/`.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
QA_RESULTS_DIR = ROOT / "qa_results"


class RunIdWouldChangeError(RuntimeError):
    """A committed run id no longer means what it meant. Names every
    affected run, because "history would be re-keyed" sends somebody
    diffing directory listings."""


def committed_deliveries(agency_id: str, collection_id: str,
                          results_dir: Path | None = None) -> dict[str, str]:
    """{run_id: delivery name} for every run already in committed
    history.

    Read from each run's own `dataset_stats.json`, which records the
    arrival it came from. A run with no such record is skipped rather
    than guessed at - an unknown provenance cannot be compared against
    anything, and inventing one is how a guard starts reporting
    confidently on nothing.
    """
    base = Path(results_dir or QA_RESULTS_DIR) / agency_id / collection_id
    if not base.is_dir():
        return {}
    out: dict[str, str] = {}
    for run_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        stats = run_dir / "dataset_stats.json"
        if not stats.is_file():
            continue
        try:
            record = json.loads(stats.read_text()).get("raw_output", {})
        except (OSError, json.JSONDecodeError):
            continue
        delivery_name = (record.get("arrival_record") or {}).get("delivery")
        if delivery_name:
            out[run_dir.name] = delivery_name
    return out


def check(agency_id: str, collection_id: str, arrivals: list,
           results_dir: Path | None = None) -> None:
    """Raise if recognition now assigns a committed run id to a
    different delivery, or drops one entirely.

    A run id appearing for the FIRST time is not a problem - that is
    simply a new arrival, which is the ordinary case. What is a problem
    is an id that already means something changing what it means.
    """
    was = committed_deliveries(agency_id, collection_id, results_dir)
    if not was:
        return
    now = {a.run_id: a.delivery_name for a in arrivals}

    moved = sorted((run_id, old, now[run_id])
                   for run_id, old in was.items()
                   if run_id in now and now[run_id] != old)
    dropped = sorted(run_id for run_id in was if run_id not in now)

    if not moved and not dropped:
        return

    lines = [f"recognition would re-key committed QA history for "
             f"{agency_id}/{collection_id}."]
    for run_id, old, new in moved:
        lines.append(f"  {run_id} was delivery {old!r} and would become {new!r}")
    for run_id in dropped:
        lines.append(f"  {run_id} was delivery {was[run_id]!r} and would no longer exist")
    lines.append(
        "Committed results are keyed by these ids, so this would rename them. "
        "Re-keying committed history belongs to REQ-PIPE-038's delete-and-regenerate "
        "rule, not to a recognition change - so this is a failure rather than "
        "something done quietly.")
    raise RunIdWouldChangeError("\n".join(lines))
