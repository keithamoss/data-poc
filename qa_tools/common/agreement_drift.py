"""The pipeline refuses a dataset whose judged past changed without a
declared correction (REQ-PIPE-173).

THE RUNTIME HALF OF REQ-PIPE-111's COMMIT-TIME GATE, for exactly the paths
that gate cannot see - a force-push, an out-of-band edit, a shallow clone
where git cannot say what changed (NFR 3). The database remembers what
judged each recorded verdict (REQ-PIPE-168): the slot's resolved inputs and
a fingerprint of the versions they came from. This compares that with what
the configuration resolves NOW, for the same slot name, and needs no git.

WHAT IS COMPARED (criterion 1): each slot's date and version fingerprint -
never anything a legitimate future append changes. Appending a date moves
neither; the fingerprint leaves the calendar's dates out on purpose.

ACCOUNTED FOR (criterion 2, PROVISIONAL): a difference is accounted for
where a declared correction in the configuration names one of that slot's
input items - its participation version, its calendar version or date, its
own date, its membership, its timezone version, a not_expected entry - with
the value the configuration now holds. That is also how a merged correction
still awaiting the asset manager refuses nothing (REQ-PIPE-170 criterion
22): once applied, the re-judged verdict carries the new fingerprint and
there is no difference left.

REFUSE THE DATASET, NOT RE-JUDGE IT, AND NEVER THE RUN (criterion 3, NFR 1):
an undeclared change has no approver and no reference, so applying it would
be the silent re-judgement this exists to prevent; and at thirty datasets
one broken agreement must not stop the other twenty-nine.

CONFIGURATION AND RECORDED FACTS ONLY (criterion 6): qa.filing_current,
qa.verdict and qa.supply_receipt, never a schema holding supply rows.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

#: Input fields named when they differ, in the order a reader thinks in.
_FIELDS = ("period_date", "due_date", "expected_time", "days_before", "grace_seconds",
           "claim_window_seconds", "timezone")


@dataclass(frozen=True)
class Drift:
    """One slot of one dataset whose recorded judgement no longer matches
    the configuration, and why."""

    dataset_id: str
    slot: str
    #: (item, recorded value, current value) for each input that differs.
    changes: tuple[tuple[str, object, object], ...]
    #: How many recorded verdicts were judged under the old terms.
    supplies: int = 1

    def describe(self) -> str:
        if not self.changes:
            return f"{self.slot}: no longer judged the way it was"
        said = "; ".join(item if old is None and new is None
                         else f"{item} was {old!r}, is now {new!r}"
                         for item, old, new in self.changes)
        return f"{self.slot}: {said}"

    def as_record(self) -> dict:
        return {"datasetId": self.dataset_id, "slot": self.slot, "supplies": self.supplies,
                "changes": [{"item": i, "recorded": o, "current": n}
                            for i, o, n in self.changes]}


@dataclass(frozen=True)
class Refusal:
    """A dataset the processing pass will not process, and every slot why."""

    dataset_id: str
    drifts: tuple[Drift, ...] = field(default_factory=tuple)
    synthetic: bool = False

    @property
    def remedy(self) -> str:
        """Criteria 2 and 8: restore the value or declare the correction - or,
        on a synthetic asset, regenerate its history."""
        base = ("restore the recorded value in contract/calendar.yaml (or "
                "contract/data-asset.yaml for the timezone), or declare the change as a "
                "correction (REQ-PIPE-111) - the schedule gate's refusal prints the entry to "
                "paste")
        if self.synthetic:
            return (base + "; on this synthetic asset you can also regenerate its history: "
                    "`mothman env reset-synthetic`, then `mothman pipeline bootstrap`")
        return base

    def message(self) -> str:
        lines = [f"{self.dataset_id} is refused: its recorded judgements no longer match "
                 f"the delivery agreement, and no declared correction accounts for it. "
                 f"This is a configuration problem on our side, not the supplier's."]
        lines += [f"  {d.describe()}" for d in self.drifts]
        lines.append(f"  To fix: {self.remedy}.")
        return "\n".join(lines)

    def as_record(self) -> dict:
        return {"datasetId": self.dataset_id, "remedy": self.remedy,
                "drifts": [d.as_record() for d in self.drifts]}


def _sources(dataset_id: str, slot: str, period_date, agreement, asset_doc) -> set[str]:
    """The freeze gate's item keys (agreement_freeze.flatten) a slot's inputs
    come from, under the configuration given."""
    from qa_tools.common import asset_time, in_force, schedule, slots

    keys = {f"dataset {dataset_id} calendar", f"dataset {dataset_id} not_expected {slot}",
            f"dataset {dataset_id} dates period {slot}"}
    try:
        version = slots._participation_for(dataset_id, period_date, agreement)
        keys.add(f"dataset {dataset_id} participation {version.effective_from.isoformat()}")
    except Exception:  # noqa: BLE001
        pass
    entry = agreement.dataset(dataset_id)
    if entry is not None and entry.own_dates is not None:
        for v in getattr(entry.own_dates, "versions", ()):
            keys.add(f"dataset {dataset_id} dates version {v.effective_from.isoformat()}")
    try:
        cal = schedule.calendar_for_dataset(dataset_id, agreement)
        cal_version = schedule._version_in_force(cal, period_date)
        keys.add(f"calendar {cal.name} version {cal_version.effective_from.isoformat()}")
        keys.add(f"calendar {cal.name} period {slot}")
    except Exception:  # noqa: BLE001
        pass
    versions = asset_time.parse_timezone_versions(asset_doc) if asset_doc else \
        asset_time.timezone_versions()
    zone = in_force.version_on(versions, period_date)
    if zone is not None:
        keys.add(f"timezone version {zone.effective_from.isoformat()}")
    return keys


def _kind(key: str) -> str | None:
    """Which kind of slot input a freeze-gate item key names."""
    parts = key.split()
    if parts[:2] == ["timezone", "version"]:
        return "tz_version"
    if parts and parts[0] == "calendar" and len(parts) >= 3:
        return {"version": "cal_version", "period": "cal_date"}.get(parts[2])
    if parts and parts[0] == "dataset" and len(parts) >= 3:
        if parts[2] == "calendar":
            return "membership"
        if parts[2] == "participation":
            return "participation"
        if parts[2] == "not_expected":
            return "not_expected"
        if parts[2] == "dates":
            return "own_date"
    return None


#: Which kinds of declared correction can account for each input that
#: differs (delivery-critic on 173, #1). A grace change is a participation
#: change and nothing else; a timezone change is a timezone version's.
_KINDS_FOR = {
    "period_date": {"cal_date", "own_date", "membership", "participation", "cal_version"},
    "due_date": {"cal_date", "own_date", "membership", "participation", "cal_version"},
    "expected_time": {"participation"},
    "days_before": {"participation"},
    "grace_seconds": {"participation"},
    "claim_window_seconds": {"participation", "cal_version"},
    "timezone": {"tz_version"},
}
#: A version's own settings changed with no input moving.
_FINGERPRINT_KINDS = {"participation", "cal_version", "tz_version", "membership"}
#: The slot is no longer a period of the dataset's schedule.
_MISSING_KINDS = {"cal_date", "own_date", "membership", "not_expected", "cal_version",
                  "participation"}


def _declared(cal_doc: dict, asset_doc: dict) -> dict[str, list[tuple[object, date | None]]]:
    """Every declared correction change's (new value, correction date), by
    item key."""
    from qa_tools.common import agreement_freeze

    out: dict[str, list] = {}
    for entries in agreement_freeze._corrections_by_owner(cal_doc, asset_doc).values():
        for corr in entries:
            corr = corr or {}
            when = corr.get("date")
            try:
                when = when if isinstance(when, date) else date.fromisoformat(str(when))
            except ValueError:
                when = None
            for change in corr.get("changes") or []:
                change = change or {}
                out.setdefault(str(change.get("item")), []).append((change.get("new"), when))
    return out


def _accounted(sources: set[str], declared: dict, items, kinds: set[str],
               judged_on: date | None) -> bool:
    """Whether a declared correction accounts for one differing input
    (criterion 2, tightened by delivery-critic on 173, #1, PROVISIONAL).

    It must name one of the slot's own input items, OF A KIND that can move
    this input; carry the value the configuration now holds (or, for a
    declared removal, the item must be gone); and be dated ON OR AFTER the
    asset date the verdict was recorded - corrections are append-only, so
    one already declared then was part of the terms it was judged under."""
    from qa_tools.common import agreement_freeze

    for key in sources & set(declared):
        if _kind(key) not in kinds:
            continue
        now = items.get(key)
        for new, when in declared[key]:
            if when is None or (judged_on is not None and when < judged_on):
                continue
            if now is None and new is None:
                return True
            if now is not None and new is not None \
                    and agreement_freeze._norm(new) == now.norm:
                return True
    return False


def _load_docs():
    from qa_tools.common import agreement, config_yaml
    from qa_tools.common.asset_time import DATA_ASSET_YAML

    with open(agreement.CALENDAR_YAML) as f:
        cal_doc = config_yaml.parse(f) or {}
    with open(DATA_ASSET_YAML) as f:
        asset_doc = config_yaml.parse(f) or {}
    return cal_doc, asset_doc


def refusal_for(conn, dataset_id: str, *, cal_doc: dict | None = None,
                asset_doc: dict | None = None) -> Refusal | None:
    """This dataset's refusal, or None where every recorded judgement still
    matches or is accounted for by a declared correction.

    `cal_doc`/`asset_doc` are the two configuration files as parsed; the
    committed ones by default. Compared BY SLOT, so a daily feed's years of
    history cost one resolution per slot (NFR 2 asks for per version; per
    slot is what REQ-PIPE-168's comparison already does, measured at 15ms
    for Birth Registrations' whole history).
    """
    from qa_tools.common import agreement, agreement_freeze, asset_time, verdict

    if cal_doc is None or asset_doc is None:
        cal_doc, asset_doc = _load_docs()
    agr = agreement.from_doc(cal_doc)
    items = agreement_freeze.flatten(cal_doc, asset_doc)
    declared = _declared(cal_doc, asset_doc)
    by_slot: dict[str, Drift] = {}
    sources: dict[str, set[str]] = {}
    for c in verdict.compared(conn, dataset_id, agr):
        if not c.moved:
            continue
        if c.now is None:
            changes = ((f"no longer a period of its schedule (it was dated "
                        f"{c.inputs.get('period_date')})", None, None),)
            needed = [_MISSING_KINDS]
        else:
            changes = tuple((f, c.inputs.get(f), c.now[0].get(f)) for f in _FIELDS
                            if c.inputs.get(f) != c.now[0].get(f))
            needed = [_KINDS_FOR[f] for f, _, _ in changes]
            if not changes:
                changes = (("the participation, calendar or timezone version's own "
                            "settings (e.g. which months it owes, or when it took effect)",
                            "as recorded", "changed"),)
                needed = [_FINGERPRINT_KINDS]
        if c.slot not in sources:
            when = c.now[3] if c.now else date.fromisoformat(c.inputs["period_date"])
            sources[c.slot] = _sources(dataset_id, c.slot, when, agr, asset_doc)
        judged_on = asset_time.local_date(c.recorded_at) if c.recorded_at else None
        # EVERY differing input must be accounted for, not any one of them.
        if all(_accounted(sources[c.slot], declared, items, kinds, judged_on)
               for kinds in needed):
            continue
        if c.slot in by_slot:
            d = by_slot[c.slot]
            by_slot[c.slot] = Drift(d.dataset_id, d.slot, d.changes, d.supplies + 1)
            continue
        by_slot[c.slot] = Drift(dataset_id, c.slot, changes)
    if not by_slot:
        return None
    return Refusal(dataset_id, tuple(by_slot[s] for s in sorted(by_slot)),
                   synthetic=bool((asset_doc or {}).get("synthetic")))


def refusals(conn=None, dataset_ids=None, *, errors: list | None = None) -> dict[str, Refusal]:
    """Every refused dataset of the asset, by id (criterion 3: each alone).

    A dataset that cannot be EVALUATED is not refused - one dataset's broken
    configuration is not another's refusal - but it is not silently passed
    either (delivery-critic on 173, #9): each is appended to `errors`, where
    given, as (dataset_id, exception), for the caller to report."""
    from qa_tools.common import hierarchy, supply_db

    if conn is None:
        with supply_db.connect(read_only=True, label="mothman:agreement-drift") as opened:
            return refusals(opened, dataset_ids, errors=errors)
    cal_doc, asset_doc = _load_docs()
    ids = dataset_ids or [d.dataset_id for d in hierarchy.all_datasets()]
    out = {}
    for ds in ids:
        try:
            found = refusal_for(conn, ds, cal_doc=cal_doc, asset_doc=asset_doc)
        except Exception as exc:  # noqa: BLE001 - one dataset's failure is not another's refusal
            if errors is not None:
                errors.append((ds, exc))
            continue
        if found is not None:
            out[ds] = found
    return out


def pass_line(found: dict[str, Refusal]) -> str | None:
    """The pass summary's line (criterion 4), or None."""
    if not found:
        return None
    return (f"{len(found)} {'dataset' if len(found) == 1 else 'datasets'} refused - their "
            f"recorded judgements no longer match the delivery agreement and no declared "
            f"correction accounts for it: {', '.join(sorted(found))}. Their supplies are "
            f"held until it is fixed; `mothman schedule check-agreement` names each change.")


def refile_cleared(*, say=print) -> list[tuple[str, str, str]]:
    """Re-file, by the rule, every supply held because its dataset was
    refused whose dataset is no longer refused - the agreement was restored
    or the change declared. The same loop drains a schedule-ended hold."""
    from qa_tools.common import schedule_ended, supply_holds

    def select(conn):
        held = [h for h in supply_holds.outstanding(conn) if h.agreement_refused]
        if not held:
            return []
        still = refusals(conn, sorted({h.dataset_id for h in held}))
        return [h for h in held if h.dataset_id not in still]

    return schedule_ended.refile_holds(
        select,
        lambda h, slot: (f"Held because {h.dataset_id} was refused - its recorded "
                         f"judgements no longer matched the agreement. They match again, "
                         f"so the rule files it to {slot}."),
        lambda h, slot: (f"{h.supply_id}: {h.dataset_id} is no longer refused, so it is "
                         f"filed to {slot} and owed a re-check"),
        say=say)
