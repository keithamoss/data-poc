"""The DECLARED CORRECTIONS, read from committed configuration
(REQ-PIPE-170; gathered into asset_model/ by REQ-PIPE-380 criterion 2): the
corrections each owner in calendar.yaml and data-asset.yaml declares, one
pending correction per change reference, the configuration as it stood
before a correction (revert) or at an instant (docs_at), and the working copy
those are read from.

WHY HERE. The generator's correction claims and scenario injection read
these exactly as the pipeline does (generator/correction_claims.py,
generator/scenario_injection.py), and they are configuration: nothing here
opens a connection or runs git.

THE OTHER HALVES, and why each cut sits where it does:
- qa_tools/common/correction_apply.py - which declared corrections are
  APPLIED, confirming and parking them: it reads and writes the database.
- qa_tools/common/correction_trial.py - trialling a correction against the
  recorded filings, and reading the configuration AT A GIT REF (at_ref):
  the database and git.
- qa_tools/common/correction_replay.py - the player half (staged,
  for_arrival, confirm_due, history_end), which reads the database; it goes
  to the bootstrap with REQ-GEN-381.
- qa_tools/common/agreement_freeze.py - the schedule gate, which compares
  the agreement between git refs and so runs git (architect B4): only its
  pure correction readers moved here.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date, datetime

from asset_model import agreement, asset_time, assets, config_yaml


SKIPPED_KEYS = ("changelog", "corrections")
#: A turn-off is ITS OWN ITEM (REQ-PIPE-179 criteria 11 and 12, amending
#: REQ-PIPE-111 criterion 2): it freezes when the periods it flips start to
#: matter, not when its version took effect.
TURN_OFF_KEYS = ("effective_to", "turned_off_reason")



def corrections_by_owner(cal_doc: dict, asset_doc: dict) -> dict[tuple, list]:
    out: dict[tuple, list] = {}
    for cal in (cal_doc or {}).get("calendars") or []:
        out[("calendar", str((cal or {}).get("name")))] = list((cal or {}).get("corrections") or [])
    for entry in (cal_doc or {}).get("datasets") or []:
        out[("dataset", str((entry or {}).get("id")))] = list((entry or {}).get("corrections") or [])
    for coll in (cal_doc or {}).get("collections") or []:
        out[("collection", str((coll or {}).get("id")))] = list((coll or {}).get("corrections") or [])
    tz = (asset_doc or {}).get("timezone") or {}
    if isinstance(tz, dict):
        out[("timezone",)] = list(tz.get("corrections") or [])
    return out


def owner_label(owner: tuple) -> str:
    if owner[0] == "timezone":
        return f"the timezone in {assets.config_dir()}/data-asset.yaml"
    return f"{owner[0]} {owner[1]!r} in {assets.config_dir()}/calendar.yaml"


# ---- putting a declared correction back (REQ-PIPE-170) ---------------------

def _own(container: dict, key: str, default):
    """`container[key]`, a copy of its own - the file shares participation
    versions between datasets through YAML anchors, and deepcopy keeps that
    sharing, so an edit to one would reach every dataset sharing it."""
    container[key] = copy.deepcopy(container.get(key) if container.get(key) is not None
                                   else default)
    return container[key]


def _version(versions: list, eff: str) -> dict | None:
    return next((v for v in versions if str((v or {}).get("effective_from")) == eff), None)


def _set_settings(versions: list, eff: str, old, *, keep: tuple) -> None:
    """A versioned item's settings back to `old`: removed where `old` is
    None (it was added), restored where it was removed, else replaced -
    keeping the keys an item does not hold (its dates, changelog)."""
    found = _version(versions, eff)
    if old is None:
        if found is not None:
            versions.remove(found)
        return
    if found is None:
        versions.append({"effective_from": eff, **copy.deepcopy(old)})
        versions.sort(key=lambda v: str(v.get("effective_from")))
        return
    for k in [k for k in found if k not in keep and k != "effective_from"]:
        del found[k]
    found.update(copy.deepcopy(old))


def _set_period(versions: list, period: str, old) -> None:
    """A dated period back to `old`: removed where `old` is None, else moved
    or restored - into the version whose window holds the old date."""
    for v in versions:
        v["dates"] = [d for d in (v.get("dates") or []) if str((d or {}).get("period")) != period]
    if old is None:
        return
    when = str(old)
    holder = None
    for v in sorted(versions, key=lambda v: str(v.get("effective_from"))):
        if str(v.get("effective_from")) <= when:
            holder = v
    holder = holder or versions[0]
    holder.setdefault("dates", []).append({"period": period, "date": when})
    holder["dates"].sort(key=lambda d: str(d.get("date")))


def revert(cal_doc: dict, asset_doc: dict,
           changes: list[tuple[str, object, object]]) -> tuple[dict, dict]:
    """The two files as they stood before `changes` - each (item key, old,
    new), as a declared correction lists them - copies, never the documents
    given. Raises ValueError for an item key it does not know, rather than
    leave a change silently in place.

    Versions before their dates and periods: a removed version comes back
    first, so its restored dates have somewhere to go."""
    cal, asset = copy.deepcopy(cal_doc), copy.deepcopy(asset_doc)
    calendars = {str((c or {}).get("name")): c for c in cal.get("calendars") or []}
    entries = {str((e or {}).get("id")): e for e in cal.setdefault("datasets", [])}

    def entry(ds: str) -> dict:
        if ds not in entries:
            entries[ds] = {"id": ds}
            cal["datasets"].append(entries[ds])
        return entries[ds]

    def order(change):
        parts = change[0].split()
        return 0 if "version" in parts else 1

    for key, old, _new in sorted(changes, key=order):
        p = key.split()
        if len(p) == 4 and p[0] == "calendar" and p[2] in ("version", "period") \
                and p[1] in calendars:
            versions = _own(calendars[p[1]], "versions", [])
            if p[2] == "version":
                _set_settings(versions, p[3], old, keep=("dates",) + SKIPPED_KEYS)
            else:
                _set_period(versions, p[3], old)
        elif len(p) == 4 and p[0] == "dataset" and p[2] == "participation":
            part = _own(entry(p[1]), "participation", {})
            _set_settings(part.setdefault("versions", []), p[3], old,
                          keep=SKIPPED_KEYS + TURN_OFF_KEYS)
        elif len(p) == 4 and p[0] == "collection" and p[2] == "participation_defaults":
            coll = next((c for c in cal.get("collections") or [] if str((c or {}).get("id")) == p[1]),
                        None)
            if coll is None:
                raise ValueError(f"{key!r} names a collection the file does not hold.")
            part = _own(coll, "participation_defaults", {})
            _set_settings(part.setdefault("versions", []), p[3], old,
                          keep=SKIPPED_KEYS + TURN_OFF_KEYS)
        elif len(p) == 5 and p[4] == "effective_to" and (
                (p[0] == "dataset" and p[2] == "participation")
                or (p[0] == "collection" and p[2] == "participation_defaults")):
            # A TURN-OFF (REQ-PIPE-179): its two keys on the one version.
            if p[0] == "dataset":
                block = _own(entry(p[1]), "participation", {})
            else:
                coll = next((c for c in cal.get("collections") or []
                             if str((c or {}).get("id")) == p[1]), None)
                if coll is None:
                    raise ValueError(f"{key!r} names a collection the file does not hold.")
                block = _own(coll, "participation_defaults", {})
            found = _version(block.setdefault("versions", []), p[3])
            if found is None:
                raise ValueError(f"{key!r} names a version the file does not hold.")
            for k in TURN_OFF_KEYS:
                found.pop(k, None)
            found.update(copy.deepcopy(old or {}))
        elif len(p) == 4 and p[0] == "dataset" and p[2] == "not_expected":
            listed = [n for n in _own(entry(p[1]), "not_expected", [])
                      if str((n or {}).get("period")) != p[3]]
            if old is not None:
                listed.append({"period": p[3], "reason": old})
            entry(p[1])["not_expected"] = listed
        elif len(p) == 3 and p[0] == "dataset" and p[2] == "calendar":
            # A CALENDAR NAME REVERTS TO BEING ON THE BASELINE (REQ-PIPE-345):
            # nothing names a calendar, so a dataset that was on one is on the
            # asset's baseline, and only a no-calendar declaration is written.
            text = "" if old is None else str(old)
            baseline = next((str((c or {}).get("name")) for c in cal.get("calendars") or []), None)
            is_none = text.startswith("no calendar (") and text.endswith(")")
            if old is not None and not is_none and text != baseline:
                raise ValueError(
                    f"{key!r} was on calendar {text!r}, which is not this asset's baseline "
                    f"{baseline!r} - nothing names a calendar (REQ-PIPE-345), so the "
                    f"agreement before this correction cannot be rebuilt")
            e = entry(p[1])
            e.pop("calendar", None)
            e.pop("no_calendar", None)
            if is_none:
                e["no_calendar"] = text[len("no calendar ("):-1]
        elif len(p) == 3 and p[:2] == ["timezone", "version"]:
            tz = asset.setdefault("timezone", {})
            versions = tz.setdefault("versions", [])
            _set_settings(versions, p[2], None if old is None else {"zone": old},
                          keep=SKIPPED_KEYS)
        else:
            raise ValueError(f"{key!r} cannot be reverted - it is not an item the schedule gate "
                             f"names, so the agreement before this correction cannot be rebuilt")
    return cal, asset


@dataclass(frozen=True)
class Pending:
    """One declared correction with no applied record."""

    reference: str
    owner: tuple
    label: str
    date: str
    reason: str
    approver: str
    changes: tuple[tuple[str, object, object], ...]


def pending_corrections(cal: dict, asset: dict) -> list[Pending]:
    """Every declared correction, ONE PER CHANGE REFERENCE (delivery-critic on
    170, D1): the gate makes each changed item be declared on its own owner,
    so one correction - a collection moved to another calendar, a date and a
    grace changed together - is several entries sharing a reference, and is
    trialled, listed and applied as one."""
    by_ref: dict[str, Pending] = {}
    for owner, entries in corrections_by_owner(cal, asset).items():
        for corr in entries:
            corr = corr or {}
            ref = str(corr.get("change_reference") or "")
            changes = tuple((str((c or {}).get("item")), (c or {}).get("old"),
                             (c or {}).get("new")) for c in corr.get("changes") or [])
            label = owner_label(owner)
            if ref in by_ref:
                was = by_ref[ref]
                by_ref[ref] = Pending(ref, was.owner, f"{was.label}; {label}", was.date,
                                      was.reason, was.approver, was.changes + changes)
                continue
            by_ref[ref] = Pending(
                reference=ref, owner=owner, label=label, date=str(corr.get("date") or ""),
                reason=str(corr.get("reason") or ""), approver=str(corr.get("approver") or ""),
                changes=changes)
    # BY DATE; a tie keeps the order the files are read in - calendars, then
    # datasets, then the timezone - not the order they were written (J4).
    return sorted(by_ref.values(), key=lambda p: p.date)


class Unreadable(ValueError):
    """A state of the configuration that could not be read."""


def load_docs() -> tuple[dict, dict]:
    """The asset's calendar.yaml and data-asset.yaml as they read on disk,
    parsed - it was agreement_drift._load_docs (REQ-PIPE-380 criterion 2)."""
    with open(agreement.calendar_yaml()) as f:
        cal_doc = config_yaml.parse(f) or {}
    with open(asset_time.data_asset_yaml()) as f:
        asset_doc = config_yaml.parse(f) or {}
    return cal_doc, asset_doc


def readable(docs: tuple[dict, dict], what: str) -> tuple[dict, dict]:
    """The two documents, or Unreadable naming what is wrong (delivery-
    critic on 169, F4): a working copy part-way through an edit is the state
    the Calendar entry is most used in, and it must be said in words - never
    a traceback, never a "nothing to declare"."""
    try:
        agreement.from_doc(docs[0])
        asset_time.parse_timezone_versions(docs[1] or {})
    except Exception as exc:  # noqa: BLE001 - every way a document can be wrong
        raise Unreadable(f"{what} cannot be read, so nothing was compared: {exc}") from exc
    return docs


def working() -> tuple[dict, dict]:
    """The configuration on disk - the working copy being corrected."""
    try:
        docs = load_docs()
    except Exception as exc:  # noqa: BLE001 - a YAML slip, or a missing file
        raise Unreadable(f"the working copy cannot be read, so nothing was compared: "
                         f"{exc}") from exc
    return readable(docs, f"the working copy of {assets.config_dir()}/calendar.yaml or "
                           f"{assets.config_dir()}/data-asset.yaml")


def merge_instant(p: Pending) -> datetime:
    """The first instant of the correction's date, on the asset's clock."""
    return asset_time.start_of_day(date.fromisoformat(p.date[:10]))


def docs_at(instant: datetime, docs: tuple[dict, dict] | None = None) -> tuple[dict, dict]:
    """The configuration as it stood at `instant`: every declared correction
    merged after it reverted, the latest first."""
    cal, asset = docs or working()
    for p in reversed(pending_corrections(cal, asset)):
        if merge_instant(p) > instant:
            cal, asset = revert(cal, asset, list(p.changes))
    return cal, asset
