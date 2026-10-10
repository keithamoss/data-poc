"""An arrival verdict as a recorded fact, naming the agreement that judged
it (REQ-PIPE-168).

A supply's verdict - early, on time, late - has been recorded once per
filing since REQ-PIPE-080 (`qa.filing.classification`). What that record
lacked is WHY: which inputs the slot was built from. So a later change to
the agreement could change what a re-computation says without anything
showing that the recorded answer was reached under different terms.

This module records each verdict with:

- the slot's RESOLVED INPUTS (criterion 1) - period date, due date,
  expected time, days before, grace, claim window, timezone - and the
  due, late-after and claim-opening instants they produce;
- a FINGERPRINT of the version-level part those inputs came from: the
  participation version, the calendar version's own settings and the
  timezone version. Deliberately NOT the calendar version's dates and NOT
  the slot's closing instant (delivery-architect, B3): appending a future
  date changes the first and authoring the next period changes the
  second, and either recorded here would make REQ-PIPE-173's backstop
  refuse every dataset after every legitimate append.

Verdicts are APPEND-ONLY (criterion 2; the trigger on `qa.verdict`). A
re-judgement by a declared correction is a new row naming the correction's
change reference and changelog entry and the verdict it supersedes
(criterion 4); the current verdict is the newest for the supply's CURRENT
filing (criterion 6), which `qa.filing_current` reads so every existing
reader of "the" classification sees it without being changed.

APPLYING a correction - when, by whom, exactly once - is REQ-PIPE-170's
(criteria 3 and 5 here wait on it). This module offers the computation
(`rejudged`) and the record (`record_rejudgement`); it moves nothing
(criterion 7) and reads only recorded receipt instants and configuration,
never supply rows (criterion 8).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from qa_tools.common import qa_store

TABLE = f'"{qa_store.SCHEMA}".verdict'


@dataclass(frozen=True)
class Judged:
    """A verdict and what it was judged against, ready to record."""

    classification: str | None
    #: The resolved inputs and derived instants, or None where there was
    #: no slot to judge against (held, unknown slot, no receipt).
    inputs: dict | None
    fingerprint: str | None


def _seconds(value: timedelta | None) -> int | None:
    return None if value is None else int(value.total_seconds())


def _fingerprint(parts: dict) -> str:
    canonical = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def resolved(dataset_id: str, period_date: date, agreement=None) -> tuple[dict, str]:
    """The inputs a slot for `period_date` is built from, and the
    fingerprint of the version-level part they came from (criterion 1).

    THE SAME RESOLUTION slots.slot_instants() makes - the participation
    version in force on the period's own date (the first, before it
    begins), the calendar version in force that day, the timezone version
    on the due date - so what is recorded is what the slot was judged by.
    Raises where the slot cannot be built; the caller decides what that
    means.
    """
    from qa_tools.common import asset_time, in_force, schedule, slots

    agreement = schedule._agreement(agreement)
    instants = slots.slot_instants(dataset_id, period_date, agreement)
    version = slots._participation_for(dataset_id, period_date, agreement)
    window = schedule.claim_window(dataset_id, on=period_date, agreement=agreement)
    cal = schedule.calendar_for_dataset(dataset_id, agreement)
    cal_version = schedule._version_in_force(cal, period_date)
    due_date = period_date - timedelta(days=version.days_before)
    zone = in_force.version_on(asset_time.timezone_versions(), due_date)
    inputs = {
        "period_date": period_date.isoformat(),
        "due_date": due_date.isoformat(),
        "expected_time": version.expected_time,
        "days_before": version.days_before,
        "grace_seconds": _seconds(version.grace),
        "claim_window_seconds": _seconds(window),
        "timezone": instants.due_at.tzinfo.key if hasattr(instants.due_at.tzinfo, "key")
        else str(instants.due_at.tzinfo),
        "due_at": instants.due_at.isoformat(),
        "late_after": (instants.due_at + instants.grace).isoformat(),
        "claim_opens_at": instants.claim_opens_at.isoformat(),
    }
    fingerprint = _fingerprint({
        "participation": {
            "effective_from": version.effective_from,
            "participates": list(version.participates) if version.participates else None,
            "expected_time": version.expected_time,
            "grace": _seconds(version.grace),
            "claim_window": _seconds(version.claim_window),
            "days_before": version.days_before,
        },
        # The calendar version's OWN settings, never its dates (B3).
        "calendar": {
            "name": cal.name,
            "effective_from": cal_version.effective_from,
            "claim_window": _seconds(cal_version.claim_window),
            "cadence_rule": cal_version.cadence_rule,
        },
        "timezone": {"effective_from": zone.effective_from if zone else None,
                     "zone": zone.zone.key if zone else None},
    })
    return inputs, fingerprint


def judge(dataset_id: str, slot, received_at: datetime | None, agreement=None) -> Judged:
    """This supply's verdict against `slot`, with what judged it.

    IT NEVER RAISES, for the reason filing._judged_for() gives: a
    filing worth recording must not be taken down by a presentational
    field. Where the inputs cannot be resolved the verdict is still
    recorded, with no inputs.
    """
    from qa_tools.common import arrival_classification

    if received_at is None:
        return Judged(None, None, None)
    if slot is None:
        return Judged(arrival_classification.UNFILED, None, None)
    try:
        classification = arrival_classification.classify(received_at, slot)
    except Exception:  # noqa: BLE001 - see the docstring
        return Judged(None, None, None)
    try:
        inputs, fingerprint = resolved(dataset_id, slot.period.date, agreement)
    except Exception:  # noqa: BLE001
        return Judged(classification, None, None)
    return Judged(classification, inputs, fingerprint)


def record(conn, filing_id: int, dataset_id: str, supply_id: str, judged: Judged, *,
           recorded_at, correction_ref: str | None = None,
           correction_changelog: str | None = None, supersedes: int | None = None) -> int:
    """Append one verdict for a filing; returns its id (criterion 2)."""
    rows = conn.execute(
        f"INSERT INTO {TABLE} (filing_id, dataset_id, supply_id, classification, inputs, "
        "fingerprint, correction_ref, correction_changelog, supersedes, recorded_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
        [filing_id, dataset_id, supply_id, judged.classification,
         json.dumps(judged.inputs) if judged.inputs is not None else None,
         judged.fingerprint, correction_ref, correction_changelog, supersedes,
         recorded_at]).fetchall()
    return rows[0][0]


def current(conn, dataset_id: str, supply_id: str) -> dict | None:
    """The supply's verdict: the newest for its CURRENT filing (criterion
    6), or None where it has none recorded."""
    rows = conn.execute(
        f"SELECT v.id, v.filing_id, v.classification, v.inputs, v.fingerprint, "
        f"v.correction_ref, v.correction_changelog, v.supersedes, v.recorded_at "
        f'FROM "{qa_store.SCHEMA}".filing_current f JOIN {TABLE} v ON v.filing_id = f.id '
        "WHERE f.dataset_id = ? AND f.supply_id = ? ORDER BY v.id DESC LIMIT 1",
        [dataset_id, supply_id]).fetchall()
    return _as_dict(rows[0]) if rows else None


def history(conn, dataset_id: str, supply_id: str) -> list[dict]:
    """Every verdict this supply has had, across every filing, oldest first
    - the record criterion 6 keeps readable."""
    rows = conn.execute(
        f"SELECT id, filing_id, classification, inputs, fingerprint, correction_ref, "
        f"correction_changelog, supersedes, recorded_at FROM {TABLE} "
        "WHERE dataset_id = ? AND supply_id = ? ORDER BY id",
        [dataset_id, supply_id]).fetchall()
    return [_as_dict(r) for r in rows]


_FIELDS = ("id", "filing_id", "classification", "inputs", "fingerprint", "correction_ref",
           "correction_changelog", "supersedes", "recorded_at")


def _as_dict(row) -> dict:
    out = dict(zip(_FIELDS, row))
    if isinstance(out["inputs"], str):
        out["inputs"] = json.loads(out["inputs"])
    return out


@dataclass(frozen=True)
class Rejudgement:
    """One supply whose verdict the configuration now in force would
    change, computed and not recorded."""

    dataset_id: str
    supply_id: str
    slot: str
    old: dict
    new: Judged


def rejudged(conn, dataset_id: str, agreement=None) -> list[Rejudgement]:
    """Every supply of a dataset whose recorded verdict the given
    configuration would CHANGE - computed, never written.

    THE SLOT IS FOUND BY NAME UNDER THE GIVEN AGREEMENT (delivery-critic on
    168, H1, post-build-review #143): a correction can move a period's DATE,
    which the fingerprint deliberately leaves out, so resolving the old
    recorded date compared an unchanged fingerprint and skipped exactly the
    correction REQ-PIPE-111 exists for. Each slot name is looked up in the
    configuration's own periods, and both its date and its fingerprint are
    compared with what was recorded. A slot name the configuration no longer
    has is not judged here - where the supply goes then is REQ-PIPE-170's.

    ONLY A CHANGED VERDICT IS LISTED (H1's sibling, M1): a correction that
    moves an input without changing the answer re-judges nothing.

    FROM RECORDED INPUTS BY VERSION, NOT A REPLAY (NFR 2). The configuration
    is resolved ONCE per slot, and a supply is judged only where its slot's
    date or fingerprint moved.

    RECEIPT INSTANTS AND CONFIGURATION ONLY (criterion 8): the receipt is
    read from qa.supply_receipt, the slot is rebuilt from configuration.
    A supply whose verdict was recorded with no inputs is not judged here:
    there is nothing to say what changed.
    """
    from qa_tools.common import arrival_classification, schedule, slots

    out = []
    for c in compared(conn, dataset_id, agreement):
        if not c.moved or c.now is None or c.received is None:
            continue
        new_inputs, new_fingerprint, instants, when = c.now
        slot = slots.Slot(dataset_id=dataset_id,
                          period=schedule.Period(name=c.slot, date=when),
                          due_at=instants.due_at, grace=instants.grace,
                          claim_opens_at=instants.claim_opens_at)
        new_class = arrival_classification.classify(c.received, slot)
        if new_class == c.classification:
            continue
        new = Judged(new_class, new_inputs, new_fingerprint)
        old = {"id": c.verdict_id, "classification": c.classification, "inputs": c.inputs,
               "fingerprint": c.fingerprint}
        out.append(Rejudgement(dataset_id, c.supply_id, c.slot, old, new))
    return out


@dataclass(frozen=True)
class Compared:
    """One supply's recorded verdict beside what the configuration now
    resolves for its slot. `now` is (inputs, fingerprint, instants, date),
    or None where the configuration has no such slot, or cannot build it."""

    supply_id: str
    slot: str
    verdict_id: int
    classification: str | None
    inputs: dict
    fingerprint: str
    received: object
    now: tuple | None
    #: Why `now` is None - the slot is gone, or could not be built.
    missing: str | None = None
    #: When the verdict was recorded - a correction declared before it was
    #: part of the terms it was judged under (REQ-PIPE-173).
    recorded_at: object = None

    @property
    def moved(self) -> bool:
        """Whether the slot's date or version-level inputs differ from what
        was recorded - a missing slot counts as moved."""
        if self.now is None:
            return True
        return (self.now[1] != self.fingerprint
                or self.now[0]["period_date"] != self.inputs.get("period_date"))


def compared(conn, dataset_id: str, agreement=None) -> list[Compared]:
    """Every current verdict with recorded inputs, beside what the given
    configuration resolves for the same slot NAME - the one comparison both
    re-judgement (REQ-PIPE-168) and the backstop (REQ-PIPE-173) make.

    By NAME under the agreement given (post-build-review #143, H1): a
    correction can move a period's date, which the fingerprint leaves out.
    Resolved once per slot (NFR 2). Recorded metadata and configuration only.
    """
    from qa_tools.common import schedule, slots

    agreement = schedule._agreement(agreement)
    rows = conn.execute(
        f"SELECT f.supply_id, f.slot, v.id, v.classification, v.inputs, v.fingerprint, "
        f"r.received_instant, v.recorded_at "
        f'FROM "{qa_store.SCHEMA}".filing_current f '
        f"JOIN LATERAL (SELECT w.id, w.classification, w.inputs, w.fingerprint, "
        f"w.recorded_at "
        f"FROM {TABLE} w WHERE w.filing_id = f.id ORDER BY w.id DESC LIMIT 1) v ON true "
        f'LEFT JOIN "{qa_store.SCHEMA}".supply_receipt r '
        f"ON r.dataset_id = f.dataset_id AND r.supply_id = f.supply_id "
        "WHERE f.dataset_id = ? AND v.fingerprint IS NOT NULL "
        "ORDER BY f.supply_id",
        [dataset_id]).fetchall()
    if not rows:
        return []
    parsed = [(s, name, vid, cls, json.loads(i) if isinstance(i, str) else i, fp, rec, at)
              for s, name, vid, cls, i, fp, rec, at in rows]
    # Where each slot name falls under THIS configuration - generated to a
    # year past the latest recorded period, which a cadence rule needs.
    horizon = max(date.fromisoformat(i["period_date"]) for *_, i, _, _, _ in parsed) \
        + timedelta(days=400)
    try:
        dated = {p.name: p.date for p in
                 schedule.periods_for_dataset(dataset_id, until=horizon, agreement=agreement)}
    except Exception as exc:  # noqa: BLE001 - no schedule now: every slot is missing
        dated, no_schedule = {}, f"the dataset has no schedule now ({exc})"
    else:
        no_schedule = None
    by_slot: dict[str, tuple] = {}
    out = []
    for supply_id, slot_name, vid, classification, inputs, fingerprint, received, at in parsed:
        if slot_name not in by_slot:
            when = dated.get(slot_name)
            if when is None:
                by_slot[slot_name] = (None, no_schedule or
                                      f"{slot_name} is no longer a period of its schedule")
            else:
                try:
                    by_slot[slot_name] = ((*resolved(dataset_id, when, agreement),
                                           slots.slot_instants(dataset_id, when, agreement),
                                           when), None)
                except Exception as exc:  # noqa: BLE001
                    by_slot[slot_name] = (None, f"{slot_name} cannot be built now ({exc})")
        now, missing = by_slot[slot_name]
        out.append(Compared(supply_id, slot_name, vid, classification, inputs, fingerprint,
                            received, now, missing, at))
    return out


def record_rejudgement(conn, rejudgement: Rejudgement, *, correction_ref: str,
                       correction_changelog: str, recorded_at) -> int:
    """Record one re-judgement as a new verdict naming the correction's
    change reference and changelog entry and the verdict it supersedes
    (criterion 4) - in the caller's transaction.

    The filing is the supply's CURRENT one, read again rather than taken
    from the computation: a verdict belongs to a filing, and nothing here
    changes which filing that is (criterion 7). Refuses where the supply's
    current verdict is no longer the one the computation superseded - a
    re-judgement recorded over a verdict it never saw would erase the one
    in between from the account of what changed.
    """
    if not correction_ref or not correction_changelog:
        raise ValueError("a re-judgement names its correction's change reference and "
                         "changelog entry (REQ-PIPE-168 criterion 4)")
    now = current(conn, rejudgement.dataset_id, rejudgement.supply_id)
    if now is None or now["id"] != rejudgement.old["id"]:
        raise ValueError(
            f"{rejudgement.supply_id} ({rejudgement.dataset_id}): its verdict has changed "
            f"since this re-judgement was computed; compute it again.")
    return record(conn, now["filing_id"], rejudgement.dataset_id, rejudgement.supply_id,
                  rejudgement.new, recorded_at=recorded_at, correction_ref=correction_ref,
                  correction_changelog=correction_changelog, supersedes=now["id"])
