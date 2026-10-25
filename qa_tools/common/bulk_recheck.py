"""A bulk re-check (REQ-PIPE-177): every supply a fixed check judged under an
old definition, re-checked in one action, across every dataset and period the
check touches - and its trial (REQ-PIPE-178), the same re-check run on a few
of them with nothing kept.

WHICH SUPPLIES (criterion 2): every supply, in any dataset and period, that is
filed and waiting or promoted and whose NEWEST result for the check - among
the results about it, as supply_status.results_about answers that, last in
run_seq order - carries a definition fingerprint (REQ-QAC-176) different from
the check's current one, compared under the stored fingerprint's own scheme.
No other. A supply with no result for the check is never selected: a check
added after a supply was checked is not a fix to it.

ONE SHARED QUERY FOR THE SELECTION AND THE QUEUE NUDGE (NFR 3). It starts from
a LOOSE INDEX SCAN of the distinct (check, fingerprint) pairs ever recorded,
which visits a handful of index entries per check whatever the history's size,
so on the common day - nothing changed - it is over at once. Only a check that
some recorded result judged under another definition goes on to ask
results_about, and then only about the supplies a stale result is about.

NOTHING HERE IS A NEW EXECUTOR: each covered supply is one re-check decision
and one owed re-check, run by recheck.run like any other (criterion 8), and a
trial is that same run under a trial identity whose results nothing reads.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

from qa_tools.common import decision_log, qa_store, supply_db

TABLE = f'"{qa_store.SCHEMA}".bulk_recheck'

#: Above this many supplies the terminal warns first and offers the hand-off
#: (criterion 18, Keith 2026-10-10): a COUNT, which a person can check.
WARN_ABOVE = 10

#: About a minute of the four tools per supply (criterion 18, NFR 5) - shown
#: as information only.
MINUTES_PER_SUPPLY = 1


class Refused(decision_log.DecisionRefused):
    """A bulk re-check or a trial that cannot be raised, saying why. Nothing
    was recorded."""


@dataclass(frozen=True)
class Covered:
    """One supply a bulk re-check covers."""

    dataset_id: str
    supply: str
    period: str
    #: rechecking.WAITING or rechecking.PROMOTED
    state: str
    #: Its current verdict - green, amber, red - or None.
    status: str | None
    #: The fingerprint its newest result for the check carries.
    stale: str

    @property
    def key(self) -> tuple[str, str, str]:
        return self.dataset_id, self.period, self.supply


@dataclass(frozen=True)
class LeftOut:
    """A supply the old definition judged that the bulk re-check does not
    cover, and why."""

    dataset_id: str
    supply: str
    period: str | None
    #: 'rejected', 'superseded', 'open-pair', 'backstop' or 'already-owed'
    why: str
    files: tuple[str, ...] = ()


@dataclass
class Plan:
    """What one bulk re-check of `check` would cover - shown, confirmed and
    then recorded from the same answer."""

    check: object
    fingerprint: str
    changelog: dict | None
    covered: list[Covered] = field(default_factory=list)
    left_out: list[LeftOut] = field(default_factory=list)
    #: {dataset: agreement_drift.Refusal} for a dataset the backstop refuses
    refused: dict = field(default_factory=dict)

    @property
    def check_id(self) -> str:
        return self.check.check_id

    @property
    def key(self) -> str:
        """The acknowledgement key (criterion 12): over every covered supply
        and the check's current fingerprint, so it changes with either."""
        text = "\n".join([self.fingerprint, *("|".join(c.key) for c in self.covered)])
        return hashlib.sha1(text.encode()).hexdigest()[:10]

    @property
    def promoted(self) -> int:
        from qa_tools.common import rechecking

        return sum(1 for c in self.covered if c.state == rechecking.PROMOTED)

    def by_dataset_period(self) -> list[tuple[str, str, int]]:
        counts = Counter((c.dataset_id, c.period) for c in self.covered)
        return [(ds, p, n) for (ds, p), n in sorted(counts.items())]

    def by_collection(self) -> Counter:
        from qa_tools.common import hierarchy

        return Counter(hierarchy.dataset(c.dataset_id).collection_id for c in self.covered)

    def left_out_as(self, why: str) -> list[LeftOut]:
        return [x for x in self.left_out if x.why == why]


# ---- the check -------------------------------------------------------------------

def current_checks() -> dict:
    """{check id: CheckMetadata} for the working tree - collected, never a
    cache of a parse that may since have changed."""
    from qa_tools.common import validate_check_lifecycle as vcl

    return {c.check_id: c for c in vcl.collect_checks(None)}


def the_check(check_id: str, checks: dict | None = None):
    """The check a bulk re-check names, or Refused: unknown, retired
    (criterion 4) or a file check (criterion 5)."""
    from qa_tools.common import file_checks

    checks = checks if checks is not None else current_checks()
    check = checks.get(check_id)
    if check is None:
        raise Refused(f"No check has the id {check_id!r}. `mothman supply queue --collection "
                      f"<id>` lists the checks with supplies to re-check, each id written as "
                      f"it is pasted after --check. Nothing was recorded.")
    if check.retired_as_of:
        raise Refused(f"{check_id} is retired (as of {check.retired_as_of}), and a retired "
                      f"check's results no longer judge any supply, so there is nothing to "
                      f"re-check them for. Nothing was recorded.")
    if check.tool == file_checks.TOOL:
        # NO COMMAND TO PASTE (PROVISIONAL, coordinator for Keith, 2026-10-25,
        # Q2 = B): staging an unchanged delivery again records nothing, so the
        # only thing that runs a file check again is the supply being resent.
        raise Refused(f"{check_id} is a file check, and file checks run only when a supply's "
                      f"file arrives, so a re-check cannot run it. They run again only when "
                      f"the supply is resent. Nothing was recorded.")
    return check


def changelog_entry(check) -> dict | None:
    """The check's current changelog entry - its newest by date (criterion 7)."""
    entries = [e for e in (check.changelog or []) if isinstance(e, dict)]
    if not entries:
        return None
    return max(enumerate(entries), key=lambda ie: (str(ie[1].get("date") or ""), ie[0]))[1]


def changed_on(entry: dict | None) -> str:
    """The date a changelog entry gives, as a day, or 'an unrecorded date'."""
    if not entry or not entry.get("date"):
        return "an unrecorded date"
    return str(entry["date"])[:10]


def headline(entry: dict | None) -> str:
    text = " ".join(str((entry or {}).get("description") or "").split())
    return text or "no changelog entry"


def touched_datasets(check) -> list[str]:
    """Every dataset the check touches: the one it is filed under and each
    one whose table it declares it reads."""
    from qa_tools.common import check_id as check_id_mod
    from qa_tools.common import hierarchy

    out = set()
    parsed = check_id_mod.try_parse(check.check_id)
    if parsed is not None:
        out.add(parsed.dataset)
    for table in check.reads_tables or ():
        try:
            out.add(hierarchy.dataset_for_table(table).dataset_id)
        except Exception:  # noqa: BLE001 - a name the hierarchy gate already reports
            continue
    return sorted(out)


# ---- the shared query ------------------------------------------------------------

def stale_fingerprints(conn, checks: dict) -> dict[str, set[str]]:
    """{check id: the recorded fingerprints that differ from its current
    definition} - for every active, non-file check that has any.

    A LOOSE INDEX SCAN (REQ-QAC-176 NFR 2) over qa.check_result_fingerprint:
    each step jumps to the next distinct (check, fingerprint) pair, so it reads
    one index entry per pair - checks times definitions - and never the
    results themselves. A SUPERSET of what any supply's newest result carries:
    results_about decides that for each supply afterwards."""
    from qa_tools.common import check_fingerprint as fp
    from qa_tools.common import file_checks

    s = qa_store.SCHEMA
    rows = conn.execute(
        f'WITH RECURSIVE pairs AS ('
        f'  (SELECT check_id, definition_fingerprint FROM "{s}".check_result '
        "    ORDER BY check_id, definition_fingerprint LIMIT 1) "
        "  UNION ALL "
        "  SELECT n.check_id, n.definition_fingerprint FROM pairs p, LATERAL ("
        f'    SELECT check_id, definition_fingerprint FROM "{s}".check_result c '
        "    WHERE (c.check_id, c.definition_fingerprint) > (p.check_id, p.definition_fingerprint) "
        "    ORDER BY check_id, definition_fingerprint LIMIT 1) n) "
        "SELECT check_id, definition_fingerprint FROM pairs").fetchall()
    out: dict[str, set[str]] = {}
    for check_id, stored in rows:
        check = checks.get(check_id)
        if check is None or check.retired_as_of or check.tool == file_checks.TOOL:
            continue
        try:
            differs = fp.differs(stored, check)
        except fp.UnknownScheme:
            differs = True
        if differs:
            out.setdefault(check_id, set()).add(stored)
    return out


def newest_by_supply(conn, check) -> dict[tuple[str, str], str]:
    """{(dataset, supply): the fingerprint on the newest result for `check`
    about that supply} for every supply any visible, agreed result of it is
    about - supply_status.results_about's rule for a non-file result, in SET
    form (NFR 3): a single-table result is about its run's own supply, a
    cross-table one about each supply it recorded READING of a table, and the
    newest is the later-opened run's, then the later-recorded row. Held to
    results_about by tests/test_bulk_recheck.py::TestTheSetFormIsResultsAbout.

    ONE QUERY PER CHECK rather than results_about once per supply, which on a
    bootstrapped history cost about 0.12s a supply."""
    from qa_tools.common import hierarchy

    s = qa_store.SCHEMA
    rows = conn.execute(
        "SELECT DISTINCT ON (kind, ds, sup) kind, ds, sup, fp, run_seq, id FROM ("
        f"  SELECT 'own' AS kind, r.dataset_id AS ds, r.supply_id AS sup, r.run_seq, c.id, "
        f'  c.definition_fingerprint AS fp FROM "{s}".check_result c '
        f'  JOIN "{s}".run_visible r ON r.run_key = c.run_key '
        "  WHERE c.check_id = ? AND c.supply_state = ? AND c.scope NOT IN (?, ?) "
        "  AND r.supply_id IS NOT NULL "
        "  UNION ALL "
        f"  SELECT 'read', k.logical_table, k.supply_id, r.run_seq, c.id, c.definition_fingerprint "
        f'  FROM "{s}".check_result c JOIN "{s}".run_visible r ON r.run_key = c.run_key '
        f'  JOIN "{s}".check_read k ON k.check_result_id = c.id '
        "  WHERE c.check_id = ? AND c.supply_state = ? AND k.state = ? "
        "  AND k.supply_id IS NOT NULL) about "
        "ORDER BY kind, ds, sup, run_seq DESC, id DESC",
        [check.check_id, qa_store.AGREED, qa_store.CROSS_TABLE_SCOPE, qa_store.FILE_SCOPE,
         check.check_id, qa_store.AGREED, qa_store.READ]).fetchall()
    newest: dict[tuple[str, str], tuple] = {}
    for kind, where, sup, fp_, run_seq, row in rows:
        if kind == "read":
            try:
                where = hierarchy.dataset_for_table(where).dataset_id
            except Exception:  # noqa: BLE001 - a table the hierarchy no longer knows
                continue
        rank = (run_seq if run_seq is not None else -1, row)
        if (where, sup) not in newest or rank > newest[(where, sup)][0]:
            newest[(where, sup)] = (rank, fp_)
    return {key: fp_ for key, (_rank, fp_) in newest.items()}


def _open_contests(conn) -> dict[tuple[str, str], tuple[str, ...]]:
    """{(dataset, pair supply): its files} for every OPEN contested pair, by
    dataset_blockers' one judgement (REQ-PIPE-194 criteria 8 and 9) - read
    once for a plan rather than once per supply."""
    from qa_tools.common import dataset_blockers

    return {(b.dataset_id, b.supply): tuple(b.files)
            for b in dataset_blockers.contests(conn) if b.is_open}


def _where(conn, dataset_id: str, supply: str):
    """('covered', Standing) for a supply filed and waiting or promoted, or
    (why, period) for one that is not - 'rejected' and 'superseded' are told
    apart (criterion 33); anything else (held, unfiled, unloaded) is None."""
    from qa_tools.common import filing, rechecking, refiling, supersession

    rows = conn.execute(f"SELECT slot FROM {filing.CURRENT} WHERE dataset_id = ? "
                        "AND supply_id = ?", [dataset_id, supply]).fetchall()
    period = rows[0][0] if rows else None
    if period and supersession.is_superseded(conn, dataset_id, supply):
        return "superseded", period
    if period and (supersession.ever_rejected(conn, dataset_id, supply)
                   and not refiling.unrejected_since(conn, dataset_id, supply)):
        return "rejected", period
    try:
        return "covered", rechecking.standing(conn, dataset_id, supply)
    except decision_log.DecisionRefused:
        return None, period


def _owing_a_recheck(conn) -> set[tuple[str, str]]:
    """(dataset, supply) for every supply owing an uncleared re-check."""
    from qa_tools.common import recheck

    return {(ds, sup) for ds, sup in conn.execute(
        f"SELECT dataset_id, supply_id FROM {recheck.TABLE} WHERE kind = ? "
        "AND cleared_at IS NULL AND supply_id IS NOT NULL", [recheck.RECHECK]).fetchall()}


def plan(conn, check_id: str, *, checks: dict | None = None,
         stale: dict[str, set[str]] | None = None, backstop: dict | None = None,
         with_status: bool = True) -> Plan:
    """What a bulk re-check of `check_id` would cover, and what it leaves
    out and why - Refused for a check that cannot be re-checked in bulk.
    Writes nothing."""
    from qa_tools.common import agreement_drift, supply_status

    checks = checks if checks is not None else current_checks()
    check = the_check(check_id, checks)
    stale = stale if stale is not None else stale_fingerprints(conn, checks)
    found = Plan(check=check, fingerprint=check.config_hash, changelog=changelog_entry(check))
    mine = stale.get(check_id)
    if not mine:
        return found
    if backstop is None:
        try:
            backstop = agreement_drift.refusals(conn, touched_datasets(check))
        except Exception:  # noqa: BLE001 - an unevaluable backstop refuses nothing
            backstop = {}
    from qa_tools.common import supply_files as _files

    pairs = None
    owing = _owing_a_recheck(conn)
    for (dataset_id, supply), got in sorted(newest_by_supply(conn, check).items()):
        if got not in mine:
            continue
        how, where = _where(conn, dataset_id, supply)
        if how is None:
            continue
        if how != "covered":
            found.left_out.append(LeftOut(dataset_id, supply, where, how))
            continue
        if pairs is None:
            pairs = _open_contests(conn)
        files = pairs.get((dataset_id, _files.pair_supply(supply)))
        if files is not None:
            found.left_out.append(LeftOut(dataset_id, supply, where.period, "open-pair", files))
            continue
        if (dataset_id, supply) in owing:
            # ALREADY OWED (PROVISIONAL, coordinator for Keith, 2026-10-25, Q1 =
            # A): its re-check is recorded and waits to run - a handed-off bulk
            # re-check's, or a person's single one - so a second bulk re-check
            # would only record it twice, and the nudge would never go quiet.
            found.left_out.append(LeftOut(dataset_id, supply, where.period, "already-owed"))
            continue
        if dataset_id in backstop:
            found.refused[dataset_id] = backstop[dataset_id]
            found.left_out.append(LeftOut(dataset_id, supply, where.period, "backstop"))
            continue
        status = None
        if with_status:
            try:
                status = supply_status.status(conn, dataset_id, supply)
            except Exception:  # noqa: BLE001 - shown as no verdict; the run decides
                status = None
        found.covered.append(Covered(dataset_id, supply, where.period, where.state, status, got))
    found.covered.sort(key=lambda c: c.key)
    return found


@dataclass(frozen=True)
class Nudge:
    """One check with supplies a bulk re-check would cover (criteria 13, 19, 20)."""

    check_id: str
    total: int
    by_collection: dict
    changed: str
    headline: str


#: nudges() worked out once while nothing it reads has changed (Q4, below).
_NUDGES: dict[tuple, list] = {}


def _state_token(conn) -> tuple:
    """What a nudge depends on in the database, as one cheap row: the newest
    run opened, decision taken, owed item recorded or cleared, and filing."""
    from qa_tools.common import filing

    s = qa_store.SCHEMA
    return tuple(conn.execute(
        f'SELECT (SELECT max(run_seq) FROM "{s}".run), '
        f'(SELECT count(*) FROM "{s}".run WHERE completed_at IS NOT NULL), '
        f"(SELECT max(id) FROM {decision_log.TABLE}), "
        f'(SELECT max(id) FROM "{s}".owed_run), '
        f'(SELECT count(*) FROM "{s}".owed_run WHERE cleared_at IS NOT NULL), '
        f"(SELECT max(id) FROM {filing.TABLE})").fetchone())


def nudges(conn) -> list[Nudge]:
    """Every check with supplies a bulk re-check would cover, by check id -
    the one shared query, read once and grouped by check (NFR 3). A supply of
    a dataset the backstop refuses stays in the count (criterion 28).

    BOUNDED (PROVISIONAL, coordinator for Keith, 2026-10-25, Q4 = A): the
    answer is kept for this process while neither the check sources
    (validate_check_lifecycle.sources_fingerprint) nor the database's state
    token moves, so reopening the queue costs two cheap reads however many
    checks have ever been fixed; any run, decision, owed item or filing
    recomputes it."""
    from qa_tools.common import validate_check_lifecycle as vcl

    key = (supply_db.supply_db_dsn(), vcl.sources_fingerprint(), _state_token(conn))
    hit = _NUDGES.get(key)
    if hit is not None:
        return list(hit)
    got = _nudges(conn)
    _NUDGES.clear()
    _NUDGES[key] = got
    return list(got)


def _nudges(conn) -> list[Nudge]:
    checks = current_checks()
    stale = stale_fingerprints(conn, checks)
    out = []
    for check_id in sorted(stale):
        try:
            p = plan(conn, check_id, checks=checks, stale=stale, with_status=False)
        except Refused:
            continue
        counts = p.by_collection()
        from qa_tools.common import hierarchy

        for x in p.left_out_as("backstop"):
            counts[hierarchy.dataset(x.dataset_id).collection_id] += 1
        total = sum(counts.values())
        if total:
            out.append(Nudge(check_id, total, dict(counts), changed_on(p.changelog),
                             headline(p.changelog)))
    return out


def nudge_line(nudges_: list[Nudge], collection_id: str) -> str | None:
    """Criterion 19's line for one collection, or None where none of its
    supplies would be covered."""
    mine = [n for n in nudges_ if n.by_collection.get(collection_id)]
    if not mine:
        return None
    here = sum(n.by_collection[collection_id] for n in mine)
    elsewhere = sum(n.total for n in nudges_) - here
    # THIS COLLECTION'S CHECKS (critic D3, 2026-10-25): K counts the checks
    # with supplies here, never the asset's - the other collections' are the
    # count in brackets.
    subject = mine[0].check_id if len(mine) == 1 else f"{len(mine)} checks"
    line = (f"{here} supplies were checked before {subject} changed" if here != 1
            else f"1 supply was checked before {subject} changed")
    if elsewhere:
        line += f" ({elsewhere} more in other collections)"
    return line


# ---- recording (criterion 7) -------------------------------------------------------

@dataclass(frozen=True)
class Recorded:
    bulk_id: int
    owed: tuple[int, ...]
    covered: tuple[Covered, ...]


def record(conn, check_id: str, *, actor: dict, reason: str, effective_at: str,
           acknowledged: str, handed_off: bool = False, shown: "Plan | None" = None) -> Recorded:
    """Record a bulk re-check in ONE transaction, before any of it runs: its
    own row, then one re-check decision and one owed re-check per covered
    supply, each naming the check, its changelog entry and the reason, in
    sorted slot order. Refused where what it covers is not what was shown -
    `acknowledged` is the key the person confirmed (criterion 12). The re-plan
    inside the transaction reads no verdicts (the key does not depend on them);
    each covered supply's verdict is carried over from `shown`, the plan the
    person confirmed."""
    from qa_tools.common import hierarchy, people, recheck

    reason = (reason or "").strip()
    if not reason:
        raise Refused("A bulk re-check needs a reason - it is published on the dashboard "
                      "against every supply it covers. Nothing was recorded.")
    name = people.actor_name(actor) if isinstance(actor, dict) else str(actor)
    with decision_log.decision_transaction(conn):
        p = plan(conn, check_id, with_status=False)
        if not p.covered:
            raise Refused(nothing_to_cover(p))
        if p.key != acknowledged:
            raise Refused(f"What this bulk re-check covers has changed since it was shown "
                          f"(its key is now {p.key}, not {acknowledged}) - look at it again. "
                          f"Nothing was recorded.")
        entry = p.changelog or {}
        (bulk_id,), = conn.execute(
            f"INSERT INTO {TABLE} (check_id, fingerprint, changelog_date, changelog_note, "
            "reason, actor, raised_at, supplies, handed_off) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "RETURNING id",
            [p.check_id, p.fingerprint, entry.get("date") and str(entry["date"]),
             entry.get("description"), reason, name, effective_at, len(p.covered),
             handed_off]).fetchall()
        owed = []
        for c in p.covered:
            ds = hierarchy.dataset(c.dataset_id)
            with decision_log.apply_decision(conn, decision_log.Decision(
                    agency_id=ds.agency_id, collection_id=ds.collection_id,
                    dataset_id=c.dataset_id, action=decision_log.RECHECK, supply=c.supply,
                    actor=name, actor_kind=decision_log.PERSON, effective_at=effective_at,
                    to_slot=c.period, reason=reason, bulk_recheck=bulk_id,
                    check_id=p.check_id,
                    check_changelog_date=entry.get("date") and str(entry["date"]),
                    check_changelog_note=entry.get("description"))) as decision_id:
                owed.append(recheck.owe(conn, dataset_id=c.dataset_id, supply_id=c.supply,
                                        decision_id=decision_id))
    was = {c.key: c.status for c in (shown.covered if shown is not None else ())}
    covered = tuple(Covered(c.dataset_id, c.supply, c.period, c.state, was.get(c.key), c.stale)
                    for c in p.covered)
    return Recorded(int(bulk_id), tuple(owed), covered)


def nothing_to_cover(p: Plan) -> str:
    """Criterion 3's refusal - and, where every supply judged under the old
    definition was LEFT OUT (critic D2), a refusal saying that instead, since
    'already checked under its current definition' would then be false."""
    if p.left_out:
        return (f"None of the {len(p.left_out)} supplies {p.check_id}'s old definition "
                f"judged can be re-checked in bulk now - each is left out, as the panel "
                f"says. Nothing was recorded.")
    return (f"Every supply {p.check_id} touches was already checked under its current "
            f"definition, so a bulk re-check would cover no supply. Nothing was recorded.")


# ---- the owed list (criterion 29) -----------------------------------------------------

@dataclass(frozen=True)
class OwedGroup:
    bulk_id: int
    check_id: str
    raised: str
    owed: int
    total: int


def owed_groups(conn, owed_items) -> tuple[list[OwedGroup], list]:
    """The owed items of each bulk re-check as one group, and every other
    owed item as it was - so a 400-supply hand-off is one line."""
    by_decision = {o.caused_by_decision: o for o in owed_items if o.caused_by_decision}
    if not by_decision:
        return [], list(owed_items)
    rows = conn.execute(
        f"SELECT d.id, b.id, b.check_id, b.raised_at, b.supplies FROM {decision_log.TABLE} d "
        f"JOIN {TABLE} b ON b.id = d.bulk_recheck WHERE d.id = ANY(?)",
        [sorted(by_decision)]).fetchall()
    bulk_of = {did: (bid, check, raised, total) for did, bid, check, raised, total in rows}
    groups: dict[int, list] = {}
    rest = []
    for o in owed_items:
        found = bulk_of.get(o.caused_by_decision)
        if found is None:
            rest.append(o)
        else:
            groups.setdefault(found[0], []).append(o)
    out = []
    for bid, items in sorted(groups.items()):
        _bid, check, raised, total = next(v for v in bulk_of.values() if v[0] == bid)
        day = raised.date().isoformat() if hasattr(raised, "date") else str(raised)[:10]
        out.append(OwedGroup(bid, check, day, len(items), int(total)))
    return out, rest


def owed_line(g: OwedGroup) -> str:
    return f"{g.owed} of {g.total} re-checks for {g.check_id} still owed (raised {g.raised})"


# ---- running ------------------------------------------------------------------------

@dataclass(frozen=True)
class Ran:
    """One covered supply's re-check as it finished."""

    covered: Covered
    outcome: object
    #: The checks whose newest result about the supply changed status.
    checks_changed: tuple[str, ...] = ()

    @property
    def completed(self) -> bool:
        return bool(getattr(self.outcome, "completed", False))

    @property
    def now(self) -> str | None:
        return getattr(self.outcome, "status", None)

    @property
    def elsewhere(self) -> bool:
        """Another runner had already finished it (recheck.ALREADY_RUN): done,
        with no verdict of this run's to compare (critic D1)."""
        from qa_tools.common import recheck

        return self.completed and getattr(self.outcome, "message", None) == recheck.ALREADY_RUN

    @property
    def changed(self) -> bool:
        return self.completed and not self.elsewhere and self.now != self.covered.status

    @property
    def worse_promoted(self) -> bool:
        from qa_tools.common import rechecking

        return (self.completed and self.covered.state == rechecking.PROMOTED
                and rechecking.is_worse(self.covered.status, self.now))


def statuses(conn, dataset_id: str, supply: str) -> dict[str, str]:
    """{check: status} of the newest result per check about this supply."""
    from qa_tools.common import supply_status

    shown = supply_status.results_about(conn, dataset_id, supply, view=supply_status.View()).shown
    return {r["check_id"]: r.get("status") for r in supply_status.newest_per_check(shown)}


def run_one(covered: Covered, owed_id: int, *, run_by: str | None = None,
            on_step=None) -> Ran:
    """Run one covered supply's owed re-check (recheck.run - claimed, gated or
    kept promoted exactly as a single re-check is) and say what changed."""
    from qa_tools.common import recheck

    with supply_db.connect(read_only=True, label="mothman:bulk-recheck") as conn:
        before = statuses(conn, covered.dataset_id, covered.supply)
    try:
        outcome = recheck.run(owed_id, run_by=run_by, on_step=on_step)
    except recheck.RecheckRefused as exc:
        recheck.fail(owed_id, str(exc))
        outcome = recheck.Outcome(owed_id, "", False, str(exc))
    changed: tuple[str, ...] = ()
    if getattr(outcome, "completed", False):
        with supply_db.connect(read_only=True, label="mothman:bulk-recheck") as conn:
            after = statuses(conn, covered.dataset_id, covered.supply)
        changed = tuple(sorted(c for c in set(before) | set(after)
                               if before.get(c) != after.get(c)))
    return Ran(covered, outcome, changed)


@dataclass
class Summary:
    ran: list[Ran] = field(default_factory=list)
    #: Covered supplies whose re-check is still owed.
    owed: int = 0

    @property
    def changed(self) -> list[Ran]:
        return [r for r in self.ran if r.changed]

    @property
    def same(self) -> int:
        return sum(1 for r in self.ran if r.completed and not r.changed and not r.elsewhere)

    @property
    def elsewhere(self) -> int:
        return sum(1 for r in self.ran if r.elsewhere)

    @property
    def still_owed(self) -> int:
        return self.owed + sum(1 for r in self.ran if not r.completed)


def summary_lines(s: Summary) -> list[str]:
    """Criterion 15's summary - never the words rejected or refused for a
    gate outcome."""
    lines = [f"{len(s.changed)} verdict(s) changed, {s.same} stayed the same, "
             f"{s.still_owed} still owed."
             + (f" {s.elsewhere} already run elsewhere." if s.elsewhere else "")]
    for r in s.changed:
        c = r.covered
        what = ", ".join(r.checks_changed) or "no single check's result"
        lines.append(f"  {c.dataset_id} {c.period} ({c.supply}): now {r.now or 'no verdict'}, "
                     f"was {c.status or 'no verdict'} - checks whose results changed: {what}")
    worse = [r for r in s.ran if r.worse_promoted]
    for r in worse:
        c = r.covered
        lines.append(f"  Promoted, then re-checked {r.now}: {c.dataset_id} {c.period} "
                     f"({c.supply}) - it stays promoted; demote it to take it out, or "
                     f"acknowledge its new verdict.")
    return lines


def estimate(n: int) -> str:
    """'roughly N minutes' or 'roughly N hours' at about a minute a supply."""
    minutes = n * MINUTES_PER_SUPPLY
    if minutes < 90:
        return f"roughly {minutes} minute{'s' if minutes != 1 else ''}"
    hours = round(minutes / 60)
    return f"roughly {hours} hour{'s' if hours != 1 else ''}"


def now_iso() -> str:
    from qa_tools.common import asset_time

    return asset_time.now().isoformat()


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


# ---- the trial (REQ-PIPE-178) ------------------------------------------------------

#: The re-check trials this process is running, {run id: (dataset, table)} -
#: what qa_results_writer.run_owner answers for one, since its id, unlike a
#: real re-check's, does not name its table. The tools, the scope rule and
#: the writer all run in this process (the tools in threads), so a registry
#: here is seen by every reader of the run's owner.
_TRIAL_OWNERS: dict[str, tuple[str, str]] = {}


def trial_owner(run_id: str) -> tuple[str, str] | None:
    return _TRIAL_OWNERS.get(run_id)


def trial_run_id() -> str:
    """A re-check trial's run id: `trial_rc_<UTC stamp>` - a trial, so every
    schema it makes is its own and is dropped when it ends (REQ-PIPE-178 NFR
    4), and a re-check trial, so it reads real supplies where they lie."""
    return supply_db.normalise_ident_part(
        f"{supply_db.RECHECK_TRIAL_PREFIX}{_utc_stamp()}")


@dataclass(frozen=True)
class Tried:
    """One supply's trial, after its run was discarded."""

    covered: Covered
    #: The verdict the trial's run reached - green, amber, red - or None.
    status: str | None = None
    #: What the promotion gate would do with a waiting supply, or that a
    #: promoted one stays promoted - never 'rejected' or 'refused' (criterion 4).
    prediction: str = ""
    error: str | None = None

    @property
    def ran(self) -> bool:
        return self.error is None


def choose(p: Plan, *, supplies=(), dataset_id: str | None = None,
           from_period: str | None = None, through_period: str | None = None) -> list[Covered]:
    """The covered supplies a trial runs (criterion 1): those named, or one
    dataset's in a period range, from among only what the real bulk re-check
    would cover. Refused for anything outside that."""
    if not p.covered:
        raise Refused(nothing_to_cover(p) + " There is nothing to try either.")
    if not supplies and dataset_id is None and from_period is None and through_period is None:
        raise Refused(f"A trial takes the supplies to try: --supply, repeated (`mothman supply "
                      f"recheck --check {p.check_id} --list` lists them), or --dataset with "
                      f"--from-period and --through-period. Nothing was run.")
    if supplies:
        wanted = list(dict.fromkeys(supplies))
        known = {c.supply: c for c in p.covered}
        missing = [s for s in wanted if s not in known]
        if missing:
            raise Refused(f"{', '.join(missing)} {'is' if len(missing) == 1 else 'are'} not "
                          f"among the {len(p.covered)} supplies the bulk re-check of "
                          f"{p.check_id} would cover, so a trial of "
                          f"{'it' if len(missing) == 1 else 'them'} previews nothing. "
                          f"`mothman supply recheck --check {p.check_id} --list` lists them. "
                          f"Nothing was run.")
        return [known[s] for s in wanted]
    datasets = sorted({c.dataset_id for c in p.covered})
    if dataset_id is None:
        raise Refused(f"A trial over a period range needs --dataset, since one check's "
                      f"periods are named by each dataset's own calendar. The real run covers "
                      f"{', '.join(datasets)}. Nothing was run.")
    if from_period is None or through_period is None:
        raise Refused("A trial over a range takes both --from-period and --through-period. "
                      "Nothing was run.")
    picked = [c for c in p.covered if c.dataset_id == dataset_id
              and from_period <= c.period <= through_period]
    if not picked:
        raise Refused(f"None of the supplies the bulk re-check of {p.check_id} would cover is "
                      f"in {dataset_id} from {from_period} through {through_period}. The real "
                      f"run covers {', '.join(datasets)}. Nothing was run.")
    return picked


def predict(conn, covered: Covered, results: list[dict]) -> tuple[str | None, str]:
    """(the trial's verdict, what the gate would do) - computed by the
    promotion gate's own plan step, promotion.judge with record=False, which
    is split from the step that applies a judgement and writes nothing
    (criterion 5). From the trial run's own results, which nothing else reads."""
    from qa_tools.common import agreement_drift, filing, hierarchy, promotion, rechecking
    from qa_tools.common import supply_status

    reads = promotion.declared_reads()
    newest = supply_status.newest_per_check([r for r in results if r.get("check_id")])
    try:
        status = promotion.status_of(covered.dataset_id, newest, reads=reads)
    except promotion.UnreadableVerdictError as exc:
        return None, f"its verdict could not be read ({exc})"
    if covered.state == rechecking.PROMOTED:
        return status, f"it would stay promoted - {covered.period} keeps it"
    ds = hierarchy.dataset(covered.dataset_id)
    item = filing.supply_item(conn, covered.dataset_id, covered.supply)
    if item is None:
        return status, "it would wait for a person" + PARTNERS
    try:
        barred = agreement_drift.refusals(conn, [covered.dataset_id])
    except Exception:  # noqa: BLE001 - an unevaluable backstop refuses nothing
        barred = {}
    judged = promotion.judge(conn, item, status, results=newest, reads=reads,
                             effective_at=now_iso(), barred=barred, agency_id=ds.agency_id,
                             collection_id=ds.collection_id, record=False)
    if judged.work is not None:
        return status, f"the gate would promote it into {covered.period}" + PARTNERS
    return status, f"it would wait for a person - {judged.why or 'not promoted'}" + PARTNERS


#: Said of every waiting supply's prediction (PROVISIONAL, coordinator for
#: Keith, 2026-10-25, Q3 = A): the trial judges the supply alone.
PARTNERS = (". The real gate judges it with its package partners, so it may decide "
            "differently")


def try_one(covered: Covered, *, run_by: str | None = None, on_step=None) -> Tried:
    """Run one covered supply's QA as the real re-check does - recheck.execute,
    the one executor - under a re-check trial's run identity (criterion 3):
    its own table read where it now lies through the one resolver, every
    table beside it read-only through the run's views, its resolution record
    and dbt scratch in schemas of its own, and its run - recorded as a trial,
    with no supply and the arrival scope, so nothing reads it (criterion 7) -
    discarded with them when it ends, Ctrl-C included (NFR 4)."""
    from qa_tools.common import hierarchy, recheck
    from qa_tools.tools import orchestrate

    run_id = trial_run_id()
    _TRIAL_OWNERS[run_id] = (covered.dataset_id, hierarchy.dataset(covered.dataset_id).table)
    try:
        # ITS OWN SCHEMA for the record of what it read - a trial's staging
        # schema, which holds no table and is dropped with the rest.
        with supply_db.connect(label="mothman:recheck-trial") as conn:
            conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.staging_schema_for(run_id)}"')
        _arrival, results = recheck.execute(
            dataset_id=covered.dataset_id, supply_id=covered.supply, run_key=run_id,
            purpose={"supply_id": None, "scope": "arrival", "trial": True},
            run_by=run_by, on_step=on_step)
        with supply_db.connect(read_only=True, label="mothman:recheck-trial") as conn:
            status, prediction = predict(conn, covered, results)
        return Tried(covered, status, prediction)
    except Exception as exc:  # noqa: BLE001 - a trial reports, it never records
        return Tried(covered, error=f"{type(exc).__name__}: {exc}")
    finally:
        # A RUN THAT NEVER REACHED ITS OWN TIDY-UP - an overlay that broke, a
        # Ctrl-C between steps - is discarded here too, so nothing survives.
        orchestrate.discard_run_schemas(run_id)
        _TRIAL_OWNERS.pop(run_id, None)


def trial_lines(tried: list[Tried]) -> list[str]:
    """Each finished supply's trial verdict beside its current one, and what
    the gate would do (criteria 4 and 10)."""
    out = []
    for t in tried:
        c = t.covered
        where = f"{c.dataset_id} {c.period} ({c.supply})"
        if not t.ran:
            out.append(f"  {where}: the trial did not finish ({t.error})")
            continue
        out.append(f"  {where}: {t.status or 'no verdict'} in the trial, "
                   f"{c.status or 'no verdict'} now - {t.prediction}")
    out.append("These verdicts come from runs that have been discarded - nothing was "
               "recorded. The real run may differ if the data changes before it runs.")
    return out
