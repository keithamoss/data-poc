"""What a correction to the delivery agreement would change - computed,
never recorded (REQ-PIPE-169; the trial REQ-PIPE-170 confirms).

ONE IMPLEMENTATION FOR THE BOARD AND THE ASSET MANAGER (criterion 6): the
impact preview a change board approves and the trial the asset manager later
confirms are this one computation, so what is confirmed is what was approved
- re-computed against the recorded facts as they then stand, never stored
(criterion 10; Keith, 2026-10-07).

TWO STATES OF THE CONFIGURATION, ONE STATE OF THE RECORD. `base` is the
agreement the recorded facts were filed and judged under; `work` is the
corrected one. Everything here is a comparison of the two applied to the
same filings, receipts and verdicts:

- each slot's due, late-after, claim-opening and closing instants (c2);
- each period a dataset gains or loses an obligation in (c5);
- each recorded verdict the corrected agreement would change (c3) -
  REQ-PIPE-168's own re-judgement, not a second one;
- each supply the filing rule would put somewhere else, or hold (c4).

A MOVE IS PROPOSED ONLY WHERE THE RULE'S OWN ANSWER CHANGED (PROVISIONAL):
the rule is run at the supply's receipt under both agreements, and a supply
is proposed only where the two answers differ AND it is still where the base
answer put it. One a person re-filed, placed or kept is where a person put
it, and a calendar correction does not overrule a person - it is listed as
not proposed, so nobody reads its absence as an oversight.

CONFIGURATION AND RECORDED FACTS ONLY (criterion 8): qa.filing_current,
qa.supply_receipt, qa.verdict and the decision log - never a schema holding
supply rows.
"""
from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

#: The instants of a slot a correction can move, in the order a reader
#: thinks in, with the dashboard's words for them (NFR 1).
INSTANTS = (("due_at", "due"), ("late_after", "late after"),
            ("claim_opens_at", "claim window opens"), ("closes_at", "closes"))


@dataclass(frozen=True)
class FrozenChange:
    """One frozen item of the agreement that differs between the two."""

    key: str
    owner: tuple
    old: object
    new: object


@dataclass(frozen=True)
class SlotMove:
    dataset_id: str
    slot: str
    what: str
    old: datetime | None
    new: datetime | None


@dataclass(frozen=True)
class Obligation:
    """A period a dataset owes a supply in under one agreement and not the
    other."""

    dataset_id: str
    period: str
    period_date: date
    gained: bool


@dataclass(frozen=True)
class VerdictChange:
    dataset_id: str
    supply_id: str
    slot: str
    old: str | None
    new: str | None


@dataclass(frozen=True)
class Move:
    """One supply the corrected rule files elsewhere - or holds."""

    dataset_id: str
    supply_id: str
    from_period: str | None
    to_period: str | None
    #: Its verdict against the period it would end up in.
    verdict: str | None
    #: Why it cannot move without another decision first, or None.
    blocked: str | None = None
    #: Its recorded verdict now (delivery-critic on 169, F1) - criterion 3
    #: asks for old and new, and a move changes both period and verdict.
    old_verdict: str | None = None
    #: Its verdict if it is KEPT where it is, under the corrected agreement
    #: (delivery-critic on 170, D6) - shown before anyone chooses to keep it.
    if_kept: str | None = None

    @property
    def held(self) -> bool:
        return self.to_period is None

    @property
    def placing(self) -> bool:
        """A held supply is PLACED, not re-filed (REQ-PIPE-141; F3)."""
        return self.from_period is None and self.to_period is not None


@dataclass(frozen=True)
class NotProposed:
    """A supply the corrected rule would file elsewhere, left where a
    person put it."""

    dataset_id: str
    supply_id: str
    period: str | None
    rule_would: str | None


@dataclass(frozen=True)
class Trial:
    changes: tuple[FrozenChange, ...] = ()
    slot_moves: tuple[SlotMove, ...] = ()
    obligations: tuple[Obligation, ...] = ()
    verdicts: tuple[VerdictChange, ...] = ()
    moves: tuple[Move, ...] = ()
    not_proposed: tuple[NotProposed, ...] = ()
    #: Datasets whose slots could not be built under one of the two, and why.
    unbuildable: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def nothing_frozen_changed(self) -> bool:
        return not self.changes

    def by_dataset(self) -> dict[str, dict[str, int]]:
        """Counts per dataset, for the summary that comes first (NFR 1)."""
        out: dict[str, dict[str, int]] = {}

        def bump(ds, what):
            out.setdefault(ds, {k: 0 for k in ("slots", "gained", "lost", "verdicts", "moves",
                                               "held", "blocked")})[what] += 1

        for s in {(m.dataset_id, m.slot) for m in self.slot_moves}:
            bump(s[0], "slots")
        for o in self.obligations:
            bump(o.dataset_id, "gained" if o.gained else "lost")
        for v in self.verdicts:
            bump(v.dataset_id, "verdicts")
        for m in self.moves:
            bump(m.dataset_id, "held" if m.held else "moves")
            if m.blocked:
                bump(m.dataset_id, "blocked")
            if m.verdict != m.old_verdict:
                bump(m.dataset_id, "verdicts")
        return dict(sorted(out.items()))


# ---- the two agreements --------------------------------------------------

@contextlib.contextmanager
def configured(cal_doc: dict, asset_doc: dict):
    """The agreement `cal_doc` describes, with `asset_doc`'s timezone
    versions standing in for the file's for the duration.

    THE TIMEZONE IS PART OF THE AGREEMENT (REQ-PIPE-112), and every slot and
    verdict resolves it through asset_time.timezone_versions(), which reads
    the file on disk. Comparing two states of the agreement with one of the
    files' zones would show a timezone correction as moving nothing. Scoped,
    and restored however the block ends; mothman is single-threaded.
    """
    from qa_tools.common import agreement, asset_time

    zones = asset_time.parse_timezone_versions(asset_doc or {})
    agr = agreement.from_doc(cal_doc)
    saved_zones, saved_current = asset_time.timezone_versions, agreement.current
    asset_time.timezone_versions = lambda: zones
    # AND THE AGREEMENT ITSELF (delivery-critic on 170, D9): a re-file, its
    # plan and a verdict resolve slots through agreement.current() - the
    # files on disk - so applying a correction outside this read every
    # merged correction at once.
    agreement.current = lambda: agr
    try:
        yield agr
    finally:
        asset_time.timezone_versions = saved_zones
        agreement.current = saved_current


def frozen_changes(base: tuple[dict, dict], work: tuple[dict, dict],
                   at: datetime | None = None) -> tuple[FrozenChange, ...]:
    """Every frozen item that differs (criterion 1), by the gate's own
    comparison (REQ-PIPE-111) - an appended date, or anything not yet
    frozen at `at`, is not a correction and is not listed."""
    from datetime import UTC

    from qa_tools.common import agreement_freeze

    at = at or datetime.now(UTC)
    out = []
    for key, (item, old, new, frozen_at) in sorted(
            agreement_freeze.changed(base[0], work[0], base[1], work[1]).items()):
        if frozen_at is None or at < frozen_at:
            continue
        out.append(FrozenChange(key, item.owner, old, new))
    return tuple(out)


# ---- the recorded facts --------------------------------------------------

def _filings(conn, dataset_id: str) -> list[tuple[str, str | None, datetime, bool]]:
    """(supply, current period or None, receipt instant, placed by a person)
    for every current filing of the dataset with a recorded receipt, oldest
    receipt first.

    WHO PUT IT THERE IS READ, NOT GUESSED (delivery-critic on 169, F2): a
    current filing with no `refiled_by` is the rule's own, and one whose
    re-file decision was the rule's (a schedule-ended or refusal hold drained
    by the rule) is the rule's too. Anything else a person decided."""
    from qa_tools.common import decision_log, filing

    rows = conn.execute(
        f"SELECT f.supply_id, f.slot, r.received_instant, f.refiled_by, d.actor_kind "
        f"FROM {filing.CURRENT} f "
        f"JOIN {filing.RECEIPT} r ON r.dataset_id = f.dataset_id AND r.supply_id = f.supply_id "
        f"LEFT JOIN {decision_log.TABLE} d ON d.id = f.refiled_by "
        "WHERE f.dataset_id = ? ORDER BY r.received_instant, f.supply_id",
        [dataset_id]).fetchall()
    return [(s, slot, at, by is not None and kind != decision_log.RULE)
            for s, slot, at, by, kind in rows]


def _blocked(conn, dataset_id: str, supply: str, from_period: str | None,
             to_period: str | None) -> str | None:
    """Why a proposed move cannot happen without another decision first -
    the re-file rules REQ-PIPE-141 already applies (REQ-PIPE-170 c9) - or
    None."""
    from qa_tools.common import decision_log

    from qa_tools.common import refiling, supersession

    if "#" in supply.rsplit("@", 1)[-1]:
        return ("one file of a contested pair - say which file is the supply first, since "
                "the contest is per arrival")
    if supersession._rejected(conn, dataset_id, supply) and not refiling._since_unrejected(
            conn, dataset_id, supply):
        # delivery-critic on 169, F3: refiling.plan refuses this too.
        return (f"it was rejected - reverse the rejection first (promote it back into "
                f"{from_period or 'its period'}), then it can move")
    if to_period:
        h = decision_log.held(conn, dataset_id, to_period)
        if h and h.held_as == decision_log.INHERITED:
            return (f"nothing was expected for {to_period}: it is inherited - un-inherit it "
                    f"first")
    if from_period and decision_log.promoted_into(conn, dataset_id, from_period) == supply:
        try:
            decision_log.refuse_if_stood_on(conn, dataset_id, supply, decision_log.REFILE)
        except decision_log.DecisionRefused as exc:
            return str(exc)
    return None


def _slots(dataset_id: str, until: date, agr) -> list:
    from qa_tools.common import slots

    return slots.slots_for_dataset(dataset_id, until=until, agreement=agr)


def _instants(slot) -> dict[str, datetime | None]:
    return {"due_at": slot.due_at, "late_after": slot.due_at + slot.grace,
            "claim_opens_at": slot.claim_opens_at, "closes_at": slot.closes_at}


# ---- the trial -------------------------------------------------------------

def trial(conn, base: tuple[dict, dict], work: tuple[dict, dict], *,
          at: datetime | None = None, dataset_ids=None) -> Trial:
    """What changing the agreement from `base` to `work` would change, for
    every dataset (or `dataset_ids`), against the recorded facts `conn`
    reads. Computed and returned; nothing is written (criterion 10)."""
    from datetime import UTC

    from qa_tools.common import assignment, asset_time, hierarchy, verdict

    at = at or datetime.now(UTC)
    changes = frozen_changes(base, work, at)
    if not changes:
        return Trial()
    ids = list(dataset_ids or [d.dataset_id for d in hierarchy.all_datasets()])
    slot_moves, obligations, verdicts, moves, skipped, unbuildable = [], [], [], [], [], []
    for ds in ids:
        # Recorded facts that cannot be read are not a footnote (F8): they
        # propagate, and the command refuses rather than report a partial
        # impact (criterion 9).
        filed = _filings(conn, ds)
        latest = max([asset_time.local_date(r) for _, _, r, _ in filed]
                     or [asset_time.local_date(at)])
        until = max(latest, asset_time.local_date(at)) + timedelta(days=400)
        try:
            with configured(*base) as agr:
                old_slots = _slots(ds, until, agr)
            with configured(*work) as agr:
                new_slots = _slots(ds, until, agr)
                rejudged = verdict.rejudged(conn, ds, agr)
                in_place = {r.supply_id: r.new.classification for r in rejudged}
                proposed = []
                for supply, period, received, by_person in filed:
                    was = assignment.open_slot(old_slots, received)
                    now = assignment.open_slot(new_slots, received)
                    was_name, now_name = (was.name if was else None), (now.name if now else None)
                    # ONLY WHAT THIS CORRECTION CHANGES: the rule's answer
                    # under the two agreements differs, and the supply is
                    # not already there.
                    if was_name == now_name or period == now_name:
                        continue
                    if by_person:
                        skipped.append(NotProposed(ds, supply, period, now_name))
                        continue
                    judged = verdict.judge(ds, now, received, agr) if now else None
                    held_now = verdict.current(conn, ds, supply)
                    was_said = (held_now or {}).get("classification")
                    proposed.append(Move(ds, supply, period, now_name,
                                         judged.classification if judged else None,
                                         old_verdict=was_said,
                                         if_kept=in_place.get(supply, was_said)))
        except (ValueError, KeyError, LookupError) as exc:
            # One dataset's schedule that cannot be built is said, not fatal
            # - ScheduleConfigError and a missing timezone version are both
            # ValueErrors. A database error is not caught here (F8).
            unbuildable.append((ds, f"{type(exc).__name__}: {exc}"))
            continue
        old_by = {s.name: s for s in old_slots}
        new_by = {s.name: s for s in new_slots}
        for name in sorted(set(old_by) | set(new_by),
                           key=lambda n: (old_by.get(n) or new_by[n]).date):
            if name not in new_by:
                obligations.append(Obligation(ds, name, old_by[name].date, gained=False))
            elif name not in old_by:
                obligations.append(Obligation(ds, name, new_by[name].date, gained=True))
            else:
                before, after = _instants(old_by[name]), _instants(new_by[name])
                slot_moves += [SlotMove(ds, name, label, before[k], after[k])
                               for k, label in INSTANTS if before[k] != after[k]]
        moving = {m.supply_id for m in proposed}
        verdicts += [VerdictChange(ds, r.supply_id, r.slot, r.old.get("classification"),
                                   r.new.classification)
                     for r in rejudged if r.supply_id not in moving]
        moves += [Move(m.dataset_id, m.supply_id, m.from_period, m.to_period, m.verdict,
                       _blocked(conn, ds, m.supply_id, m.from_period, m.to_period),
                       m.old_verdict, m.if_kept)
                  for m in proposed]
    return Trial(changes, tuple(slot_moves), tuple(obligations), tuple(verdicts),
                 tuple(moves), tuple(skipped), tuple(unbuildable))


# ---- the report ------------------------------------------------------------

def _when(value: datetime | None) -> str:
    from qa_tools.common import asset_time

    if value is None:
        return "never"
    local = asset_time.localise(value)
    return f"{local:%-d %b %Y %H:%M} ({local.tzname()})"


def _said(classification: str | None) -> str:
    return (classification or "not judged").replace("_", " ").capitalize()


def database_label() -> str:
    """Which database the preview read, without its connection string
    (criterion 7) - only the name and where it is."""
    from psycopg import conninfo

    from qa_tools.common import supply_db

    try:
        info = conninfo.conninfo_to_dict(supply_db.supply_db_dsn())
    except Exception:  # noqa: BLE001 - an unparseable DSN may hold its password anywhere
        return "the configured database"
    return f"{info.get('dbname') or '(default)'} on {info.get('host') or 'localhost'}"


def report(t: Trial, *, as_at: datetime, database: str, against: str,
           title: str = "Impact of the correction", applied: bool = False) -> str:
    """The preview as Markdown, summary first (criterion 7, NFR 1) - in the
    dashboard's words, for a reader who does not know the file. `applied`
    words the same layout as what WAS done (REQ-PIPE-170 criterion 22;
    delivery-critic on 170, D8) rather than what would be."""
    intro = (f"Applied against {against}, as at {_when(as_at)}, and recorded in the database "
             f"{database}." if applied else
             f"Compared the working copy against `{against}`, as at {_when(as_at)}, reading "
             f"recorded facts from the database {database}. Nothing was recorded.")
    lines = [f"# {title}", "", intro, ""]
    if t.nothing_frozen_changed:
        lines.append("Nothing frozen changed, so nothing would be re-judged or moved.")
        return "\n".join(lines) + "\n"
    lines += ["## Summary", "",
              "| Dataset | Slots moved | Periods gained / lost | Verdicts changed "
              "| Supplies moved | Supplies held | Blocked |",
              "|---|---|---|---|---|---|---|"]
    counts = t.by_dataset()
    for ds, c in counts.items():
        lines.append(f"| {ds} | {c['slots']} | {c['gained']} / {c['lost']} | {c['verdicts']} | "
                     f"{c['moves']} | {c['held']} | {c['blocked']} |")
    if not counts:
        lines.append("| (none) | 0 | 0 / 0 | 0 | 0 | 0 | 0 |")
    lines += ["", "## What changed in the agreement", ""]
    from qa_tools.common import agreement_freeze

    for c in t.changes:
        lines.append(f"- {c.key}: {agreement_freeze._value_text(c.old)} -> "
                     f"{agreement_freeze._value_text(c.new)}")
    if t.unbuildable:
        lines += ["", "## Datasets that could not be compared", ""]
        lines += [f"- {ds}: {why}" for ds, why in t.unbuildable]
    if t.moves:
        lines += ["", "## Supplies moved or held" if applied
                  else "## Supplies that would move or be held", ""]
        for m in t.moves:
            if m.held:
                to = "held - no period would take it"
            elif m.placing:
                to = f"placed into {m.to_period}, {_said(m.verdict).lower()}"
            else:
                to = f"{m.to_period}, {_said(m.verdict).lower()}"
            was = (f"{m.from_period} ({_said(m.old_verdict)})" if m.from_period else "held")
            line = f"- {m.dataset_id} `{m.supply_id}`: {was} -> {to}"
            if not applied and m.from_period and m.if_kept != m.old_verdict:
                line += f" (if kept in {m.from_period}: {_said(m.if_kept).lower()})"
            if m.blocked:
                # Indented, so a multi-line reason stays inside its bullet (F5).
                line += ". BLOCKED: " + m.blocked.replace("\n", "\n  ")
            lines.append(line)
    if t.verdicts:
        lines += ["", "## Verdicts changed, in the same period" if applied
                  else "## Verdicts that would change, in the same period", ""]
        lines += [f"- {v.dataset_id} `{v.supply_id}` in {v.slot}: {_said(v.old)} -> "
                  f"{_said(v.new)}" for v in t.verdicts]
    if t.obligations:
        lines += ["", "## Periods that gain or lose an obligation", ""]
        lines += [f"- {o.dataset_id} {o.period} ({o.period_date:%-d %b %Y}): "
                  f"{'now owes a supply' if o.gained else 'no longer owes a supply'}"
                  for o in t.obligations]
    if t.slot_moves:
        lines += ["", "## Slots whose times move", ""]
        lines += [f"- {s.dataset_id} {s.slot}, {s.what}: {_when(s.old)} -> {_when(s.new)}"
                  for s in t.slot_moves]
    if t.not_proposed:
        lines += ["", "## Not proposed - a person put these where they are", ""]
        lines += [f"- {n.dataset_id} `{n.supply_id}` in {n.period or 'no period'}: the "
                  f"corrected rule would file it to {n.rule_would or 'no period'}"
                  for n in t.not_proposed]
    return "\n".join(lines) + "\n"


# ---- the two states, from disk and from git --------------------------------

class Unreadable(ValueError):
    """A state of the configuration that could not be read."""


def _working_docs() -> tuple[dict, dict]:
    from qa_tools.common import agreement_drift

    return agreement_drift._load_docs()


def _readable(docs: tuple[dict, dict], what: str) -> tuple[dict, dict]:
    """The two documents, or Unreadable naming what is wrong (delivery-
    critic on 169, F4): a working copy part-way through an edit is the state
    the Calendar entry is most used in, and it must be said in words - never
    a traceback, never a "nothing to declare"."""
    from qa_tools.common import agreement, asset_time

    try:
        agreement.from_doc(docs[0])
        asset_time.parse_timezone_versions(docs[1] or {})
    except Exception as exc:  # noqa: BLE001 - every way a document can be wrong
        raise Unreadable(f"{what} cannot be read, so nothing was compared: {exc}") from exc
    return docs


def working() -> tuple[dict, dict]:
    """The configuration on disk - the working copy being corrected."""
    try:
        docs = _working_docs()
    except Exception as exc:  # noqa: BLE001 - a YAML slip, or a missing file
        raise Unreadable(f"the working copy cannot be read, so nothing was compared: "
                         f"{exc}") from exc
    return _readable(docs, "the working copy of contract/calendar.yaml or "
                           "contract/data-asset.yaml")


def at_ref(ref: str) -> tuple[dict, dict]:
    """The configuration at a git ref, as REQ-PIPE-111's gate reads it."""
    from qa_tools.common import agreement_freeze, config_yaml
    from qa_tools.common.validate_schedule import _content_at

    docs = []
    for rel in (agreement_freeze.CALENDAR_REL, agreement_freeze.ASSET_REL):
        text = _content_at(rel, ref)
        if text is None:
            raise Unreadable(f"{rel} could not be read at {ref!r} - is it a ref this "
                             f"checkout has?")
        try:
            docs.append(config_yaml.parse(text) or {})
        except Exception as exc:  # noqa: BLE001 - a YAML slip at that ref
            raise Unreadable(f"{rel} at {ref!r} cannot be read: {exc}") from exc
    return _readable((docs[0], docs[1]), f"the configuration at {ref!r}")


def preview(ref: str | None = None, *, at: datetime | None = None) -> str:
    """The impact preview of the working copy against `ref` (by default the
    base REQ-PIPE-111's gate compares against) - one function for the
    command and the terminal's Calendar entry. Raises Unreadable where a
    state cannot be read, and supply_db.SupplyDbError where the recorded
    facts cannot be reached (criterion 9): an impact computed from
    configuration alone is not complete, so none is offered."""
    from datetime import UTC

    from qa_tools.common import supply_db
    from qa_tools.common.diff_base import diff_base

    ref = ref or diff_base()
    at = at or datetime.now(UTC)
    base, work = at_ref(ref), working()
    with supply_db.connect(read_only=True, label="mothman:correction-preview") as conn:
        t = trial(conn, base, work, at=at)
    return report(t, as_at=at, database=database_label(), against=ref)


def draft(ref: str | None = None, **given) -> list[str]:
    """The correction entries to paste for every undeclared frozen change in
    the working copy (REQ-PIPE-169 criterion 14) - the gate's own refusal
    text, with whatever the person gave filled in."""
    from datetime import UTC

    from qa_tools.common import agreement_freeze, asset_time, config_yaml
    from qa_tools.common.diff_base import diff_base
    from qa_tools.common.validate_schedule import _content_at

    ref = ref or diff_base()
    base, work = at_ref(ref), working()
    people = config_yaml.parse(_content_at(agreement_freeze.PEOPLE_REL, ref) or "") or {}
    return agreement_freeze.drafts(
        base[0], work[0], base[1], work[1], people,
        base_codeowners=_content_at(agreement_freeze.CODEOWNERS_REL, ref),
        today=asset_time.local_date(datetime.now(UTC)), **given)


def may_approve(ref: str | None = None) -> list[str]:
    """Who the gate will accept as approver of a calendar correction, at the
    base - offered when the terminal asks (criterion 14)."""
    from qa_tools.common import agreement_freeze, config_yaml
    from qa_tools.common.diff_base import diff_base
    from qa_tools.common.validate_schedule import _content_at

    ref = ref or diff_base()
    people = config_yaml.parse(_content_at(agreement_freeze.PEOPLE_REL, ref) or "") or {}
    owners = agreement_freeze.code_owners(_content_at(agreement_freeze.CODEOWNERS_REL, ref),
                                          agreement_freeze.CALENDAR_REL)
    return [p.get("email") for p in agreement_freeze.approvers(people)
            if str(p.get("github", "")).lower() in owners and p.get("email")]


# ---- the terminal's Calendar entry (criterion 13) --------------------------

@dataclass(frozen=True)
class InForce:
    """The delivery agreement in force for one dataset on one date."""

    dataset_id: str
    on: date
    calendar: str
    owes: str
    #: The next period owed on or after `on`, and its resolved inputs.
    next_period: str | None
    next_date: date | None
    inputs: dict | None
    #: Periods it owes nothing in, by name, with the agreed reason.
    not_expected: tuple[tuple[str, str], ...]
    zone: str


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def in_force(dataset_id: str, on: date, agreement=None) -> InForce:
    """What a dataset is agreed to deliver as at `on`, from configuration
    alone: its calendar, which periods it owes and why not the others, and
    - for the next period owed - its due date and time, grace, claim window
    and days before, as resolved (REQ-PIPE-168's own resolution)."""
    from qa_tools.common import asset_time, schedule, slots, verdict

    agreement = schedule._agreement(agreement)
    cal = schedule.calendar_for_dataset(dataset_id, agreement)
    version = slots._participation_for(dataset_id, on, agreement)
    entry = agreement.dataset(dataset_id)
    begins = [cal.versions[0].effective_from]
    if entry and entry.participation:
        begins.append(entry.participation[0].effective_from)
    starts = max(begins)
    if on < starts:
        # delivery-critic on 169, F9: the first version stands in for the
        # periods before it, but nothing was owed then.
        owes = f"nothing yet - its delivery agreement starts {starts:%-d %b %Y}"
    elif version.participates:
        owes = (f"periods dated in {', '.join(_MONTHS[m - 1] for m in version.participates)}"
                + (f" - {version.reason}" if version.reason else ""))
    else:
        owes = "every period"
    upcoming = [s for s in slots.slots_for_dataset(dataset_id, until=on + timedelta(days=400),
                                                   agreement=agreement) if s.date >= on]
    nxt = upcoming[0] if upcoming else None
    inputs = None
    if nxt is not None:
        try:
            inputs, _ = verdict.resolved(dataset_id, nxt.date, agreement)
        except Exception:  # noqa: BLE001 - shown as unresolvable, not fatal
            inputs = None
    skipped = tuple(sorted((entry.not_expected or {}).items())) if entry else ()
    return InForce(dataset_id, on, cal.name, owes, nxt.name if nxt else None,
                   nxt.date if nxt else None, inputs, skipped,
                   asset_time.zone_on(on).key)


@dataclass(frozen=True)
class Declared:
    """One declared correction and whether it has been applied."""

    owner: str
    reference: str
    date: str
    reason: str
    items: tuple[str, ...]
    applied: bool


def declared(conn=None, cal_doc: dict | None = None,
             asset_doc: dict | None = None) -> list[Declared]:
    """Every correction declared in the configuration, newest first, each
    marked applied where a recorded verdict names its reference (REQ-PIPE-168)
    - pending otherwise, which is what REQ-PIPE-170's confirmation settles.
    Without `conn`, nothing can be known applied, so all read pending."""
    from qa_tools.common import agreement_freeze, verdict

    if cal_doc is None or asset_doc is None:
        cal_doc, asset_doc = working()
    applied: set[str] = set()
    if conn is not None:
        applied = {r[0] for r in conn.execute(
            f"SELECT DISTINCT correction_ref FROM {verdict.TABLE} "
            "WHERE correction_ref IS NOT NULL").fetchall()}
    out = []
    for owner, entries in agreement_freeze._corrections_by_owner(cal_doc, asset_doc).items():
        for corr in entries:
            corr = corr or {}
            ref = str(corr.get("change_reference") or "")
            out.append(Declared(agreement_freeze._owner_label(owner), ref,
                                str(corr.get("date") or ""), str(corr.get("reason") or ""),
                                tuple(str((c or {}).get("item")) for c in corr.get("changes")
                                      or []), ref in applied))
    return sorted(out, key=lambda d: (d.date, d.reference), reverse=True)
