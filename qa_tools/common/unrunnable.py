"""A check that could not read a table says so, and says why
(REQ-PIPE-105 criterion 13; REQ-PIPE-079 criteria 4 and 14 to 16).

ABSENT IS NOT SILENT. One file is one arrival, so a run reads its
siblings from its period - and a sibling that has not arrived yet, is
contested, or was filed elsewhere has no view. Every tool now leaves a
check over such a table OUT rather than erroring or reporting a false red
(REQ-PIPE-105's latent-defect fixes). Left there, the check simply does
not appear - which reads, to the dashboard, the promotion gate and the
tickets alike, exactly like a check that passed.

So each in-scope check that could not run gets ONE RECORD, and it is RED
WHATEVER THE REASON (REQ-PIPE-270, Keith 2026-10-21: "STRICT, not
relaxed. An absent partner stays could-not-run, which is red"). The
reason is kept beside the status as a structured code - not yet due (with
the instant it falls due), overdue, staged awaiting a decision, contested,
could not be loaded, held back with its package, rejected - because each
needs a different action, and a not-yet-due red clears by itself
(plans/running-thoughts.md #113). The reason never changes the status: a
not-yet-due partner used to read "no data", and decision 103 promoted a
supply on exactly that - a check nobody could run, read as green.

NOT IN THE AGREEMENT IS NOT ABSENT (criterion 9): a table whose dataset
owes nothing for the run's period - it joins the agreement later - and was
never supplied for it is no gap at all, so a check reading it is left OUT
of the run's scope for that period (out_of_agreement), recorded in
left_out with its reason, and records neither red nor a result.

WHICH CHECKS: exactly the run's scope (qa_results_writer._scope_to_run) -
its own dataset's checks, and checks declaring they read its table - so
nothing is recorded here that would be thrown away there. A HELD table is
left to held_blast_radius, which already reports it; reporting it twice
would be two reds for one cause.

THE STATE IS AS AT THE ARRIVAL, not as at "now": a bootstrap replays four
years of arrivals, and asking today's clock whether a 2023 table was
overdue would say yes to everything.
"""
from __future__ import annotations

from datetime import datetime

from qa_tools.common import check_id as check_id_mod
from qa_tools.common import period_schema, slot_state, supply_db

#: The pseudo-tool these are recorded under, beside `held`. Not in
#: EXPECTED_TOOLS, for the reason held_blast_radius.TOOL gives.
TOOL = "unrunnable"

LABEL = "Not evaluated - a table it reads is not available"

#: slot_state's vocabulary -> period_schema's absence reasons.
_STATE_TO_REASON = {
    slot_state.NOT_YET_DUE: period_schema.NOT_YET_DUE,
    slot_state.OVERDUE: period_schema.PAST_DUE,
    slot_state.NEVER_SUPPLIED: period_schema.PAST_DUE,
    slot_state.AWAITING_DECISION: period_schema.STAGED_AWAITING_DECISION,
    slot_state.RETURNED: period_schema.STAGED_AWAITING_DECISION,
    # A PERSON REJECTED THIS PERIOD'S FILE and none has replaced it
    # (REQ-PIPE-270 criterion 4 as amended by REQ-PIPE-211 criterion 9).
    slot_state.REJECTED: period_schema.REJECTED,
    # AN AMBER SUPPLY UNDER HOLD is staged and waiting for a person, as a
    # red one is; and a period a person accepted as not supplied is a slot
    # past due with nothing coming - neither may fall to the catch-all
    # (criterion 5).
    slot_state.AMBER_WAITING: period_schema.STAGED_AWAITING_DECISION,
    slot_state.NOT_SUPPLIED_ACCEPTED: period_schema.PAST_DUE,
}

#: The words for each code a record can carry (REQ-PIPE-270 criterion 5):
#: period_schema's reasons, and a trial's own. No code reaches a catch-all.
TRIAL_UNREADABLE = "not-readable-in-trial"
REASON_WORDS = {**period_schema.REASON_WORDS,
                # A table no reason could be read for: a schedule that could
                # not be built. Named, never left to a generic line.
                period_schema.MISSING_TABLE: "not available, and no reason could be read",
                TRIAL_UNREADABLE: "not readable in this trial"}


def words_for(code: str) -> str:
    """What a reason code means, in words - raising for a code nobody
    described, so a new reason cannot silently read as the catch-all."""
    return REASON_WORDS[code]


def supply_state(conn, dataset_id: str, period: str, as_at: datetime) -> str | None:
    """Why this dataset has nothing readable for this period, as at the
    arrival - one of period_schema's reasons, or None for the catch-all.

    A dataset with no slot named for this period (it does not participate
    in it, or its schedule cannot be built) has no reason to give, and
    falls through to the catch-all rather than being guessed at.
    """
    from qa_tools.common import filing
    from qa_tools.common import slots as slots_mod

    try:
        dataset_slots = slots_mod.slots_for_dataset(
            dataset_id, until=slots_mod.claimable_until(dataset_id, as_at.date()))
    except (ValueError, KeyError, FileNotFoundError):
        return None
    slot = next((s for s in dataset_slots if s.name == period), None)
    if slot is None:
        return None
    filings = slot_state.filings_by_period(
        conn, dataset_id, [r for r in filing.filings_of(dataset_id) if r.get("slot") == period])
    state = slot_state.state_of(conn, dataset_id=dataset_id, slot=slot, now=as_at,
                                filings=filings, ever_delivered=True)
    return _STATE_TO_REASON.get(state.state)


def _slot_of(dataset_id: str, period: str, as_at: datetime):
    """The dataset's slot named `period`, as at the arrival - or None where
    it owes nothing for that period; raises where its schedule cannot be
    built."""
    from qa_tools.common import slots as slots_mod

    dataset_slots = slots_mod.slots_for_dataset(
        dataset_id, until=slots_mod.claimable_until(dataset_id, as_at.date()))
    return next((s for s in dataset_slots if s.name == period), None)


def due_at_of(dataset_id: str, period: str, as_at: datetime) -> datetime | None:
    """When this dataset's supply for `period` falls due, or None where that
    cannot be said (REQ-PIPE-270 criterion 4: a not-yet-due red carries it)."""
    try:
        slot = _slot_of(dataset_id, period, as_at)
    except (ValueError, KeyError, FileNotFoundError):
        return None
    return slot.due_at if slot is not None else None


#: How far past the run's own instant to look for the period's slot when
#: asking whether the dataset is part of the agreement for it: a run re-filed
#: into a later period (or a re-check of one) is about a period its receipt
#: could not yet claim, and its slot exists all the same.
_AGREEMENT_REACH_DAYS = 400


def in_agreement(conn, dataset_id: str, period: str, as_at: datetime) -> bool:
    """Whether this dataset is part of the collection's agreement for
    `period` - or has been supplied for it all the same (REQ-PIPE-270
    criterion 9). False only where it owes nothing for that period AND
    nothing of it was ever filed there: a dataset that joins the agreement
    in a later period. A schedule that cannot be built answers True, so
    the check falls to the ordinary could-not-run red rather than out of
    scope."""
    from datetime import timedelta

    from qa_tools.common import filing
    from qa_tools.common import slots as slots_mod

    try:
        # THE AGREEMENT, NOT WHAT THIS RECEIPT COULD CLAIM: generated far
        # enough ahead to hold a later period the run is about (a re-file's).
        dataset_slots = slots_mod.slots_for_dataset(
            dataset_id, until=slots_mod.claimable_until(
                dataset_id, as_at.date() + timedelta(days=_AGREEMENT_REACH_DAYS)))
    except (ValueError, KeyError, FileNotFoundError):
        return True
    if any(s.name == period for s in dataset_slots):
        return True
    rows = conn.execute(f"SELECT 1 FROM {filing.CURRENT} WHERE dataset_id = ? AND slot = ? "
                        "LIMIT 1", [dataset_id, period]).fetchall() if conn is not None else []
    return bool(rows)


def out_of_agreement(conn, *, own_table: str, own_dataset: str, period: str,
                     resolution: supply_db.Resolution, reads: dict[str, list[str]],
                     as_at: datetime, decided_by: datetime | None = None) -> dict[str, str]:
    """{check id: why it is out of this run's scope} for every in-scope
    check that reads a table not part of the agreement for `period` and
    never supplied for it (criterion 9) - left out, never red, no result.

    `decided_by`: the instant a person's not-supplied mark is read as at -
    the run's own, so that a re-run a later mark owes sees it (REQ-PIPE-332
    criterion 9); `as_at`, the receipt, where not given."""
    from qa_tools.common import hierarchy

    missing = ((set(resolution.absent) | set(resolution.ambiguous)) - set(resolution.held)
               - set(resolution.resolved))
    if not missing or not reads:
        return {}
    from qa_tools.common import not_supplied

    outside: dict[str, dict | None] = {}
    out: dict[str, dict] = {}
    for check, tables in sorted(reads.items()):
        parsed = check_id_mod.try_parse(check)
        if parsed is None:
            continue
        if not (parsed.dataset == own_dataset or own_table in tables):
            continue
        for table in sorted(set(tables) & missing):
            if table not in outside:
                try:
                    dataset_id = hierarchy.dataset_for_table(table).dataset_id
                except Exception:  # noqa: BLE001 - not one of ours
                    outside[table] = None
                    continue
                outside[table] = None
                # A PERSON'S DECISION FIRST (REQ-PIPE-332 criterion 7): marked
                # not supplied for the period, the check is out of scope -
                # whichever collection declares it, a sibling included.
                if conn is not None and not_supplied.marked(
                        conn, dataset_id, period,
                        as_at=max(as_at, decided_by or as_at).isoformat()) is not None:
                    outside[table] = left_out_entry(NOT_SUPPLIED_BY_DECISION, period,
                                                    dataset_id)
                elif not in_agreement(conn, dataset_id, period, as_at):
                    outside[table] = left_out_entry(NOT_IN_AGREEMENT, period, dataset_id)
            if outside[table] is not None:
                out[check] = outside[table]
                break
    return out


#: THE STRUCTURED REASON CODES a left_out entry carries (REQ-PIPE-332
#: criterion 10), so the page words each from its code, never its text.
NOT_IN_AGREEMENT = "not_in_agreement"
NOT_SUPPLIED_BY_DECISION = "not_supplied_by_decision"
CALENDAR_DIFFERS = "calendar_differs"
_REASONS = {NOT_IN_AGREEMENT: "not part of the agreement for {period}",
            NOT_SUPPLIED_BY_DECISION: "not supplied for {period}, by decision",
            CALENDAR_DIFFERS: "not checked: {dataset} was on another calendar for {period}"}


def left_out_entry(code: str, period: str, dataset_id: str) -> dict:
    """One recorded left_out entry: its code, its reason in words, and the
    period and dataset it is about."""
    return {"code": code, "reason": _REASONS[code].format(period=period, dataset=dataset_id),
            "period": period, "dataset": dataset_id}


def as_entry(value) -> dict:
    """A recorded entry as a dict - one recorded before the codes existed is
    a bare reason, which was only ever not_in_agreement's."""
    if isinstance(value, dict):
        return value
    return {"code": NOT_IN_AGREEMENT, "reason": str(value)}


def _refused_with(conn, run_id: str) -> frozenset[str]:
    """The logical tables whose load FAILED for this run's own arrival -
    the same arrival key as the run's own staged table."""
    parts = supply_db.split_staged(run_id)
    if not parts:
        return frozenset()
    from qa_tools.common import load_log

    try:
        failed = [r for r in load_log.latest_by_table(conn=conn).values() if not r.loaded]
    except Exception:  # noqa: BLE001 - no load record means nothing refused
        return frozenset()
    return frozenset(p[0] for p in (supply_db.split_staged(r.physical) for r in failed)
                     if p and p[1] == parts[1])


def results_for(conn, *, run_id: str, run_timestamp: str, own_table: str,
                own_dataset: str, period: str, resolution: supply_db.Resolution,
                reads: dict[str, list[str]], as_at: datetime,
                checks_by_id: dict | None = None,
                held_back: frozenset[str] = frozenset(),
                outside: dict[str, str] | None = None) -> list[dict]:
    """One record per in-scope check that reads an unreadable table,
    naming every such table - red, with each table's reason kept as a code.

    `held_back` are the tables a gate application's re-check reads from the
    warehouse because their supply is not promoting with it (REQ-PIPE-267
    criterion 6): where the period holds none, the reason is "held back with
    its package". `outside` is out_of_agreement()'s answer, whose checks
    are out of scope and get no record."""
    from qa_tools.common import hierarchy

    missing = ((set(resolution.absent) | set(resolution.ambiguous)) - set(resolution.held)
               - set(resolution.resolved))
    if not missing or not reads:
        return []
    if own_table in resolution.ambiguous or own_table in resolution.held:
        # NOTHING UNDER THE RUN OF A SUPPLY NOBODY HAS PLACED OR CHOSEN
        # (REQ-PIPE-115 criteria 6 and 16). Its own checks are not run,
        # and a sibling's check reading its table is that sibling's run's
        # to record.
        return []
    contested_own = own_table in resolution.ambiguous
    refused = _refused_with(conn, run_id)
    outside = outside or {}
    due: dict[str, datetime | None] = {}
    wrapped = period_schema.PeriodResolution(period=period, resolution=resolution)
    states: dict[str, str] = {}
    out: list[dict] = []
    checks_by_id = checks_by_id or {}
    for check, tables in sorted(reads.items()):
        parsed = check_id_mod.try_parse(check)
        if parsed is None:
            continue
        own = parsed.dataset == own_dataset
        # THE RUN'S SCOPE, and nothing wider - see the module docstring.
        if not ((own and not contested_own) or own_table in tables):
            continue
        try:
            home = hierarchy.dataset(parsed.dataset).table
        except Exception:  # noqa: BLE001 - not one of ours, nothing to say
            continue
        # ONE RECORD PER CHECK (a run holds one result per check). A
        # check that reads a HELD table is held_blast_radius's to record,
        # so it is left out here entirely rather than explained twice -
        # found on the first bootstrap under REQ-PIPE-131, the first to
        # produce real holds. Where several of its tables are unreadable,
        # the one record names them all (criterion 2 as amended).
        if (set(tables) | {home}) & set(resolution.held):
            continue
        if check in outside:
            continue  # criterion 9: out of the run's scope, no record
        found = []
        for table in sorted((set(tables) | {home}) & missing):
            if table not in states and table in refused:
                # COULD NOT BE LOADED WINS THE REASON (REQ-DASH-148
                # criterion 6): it came in this arrival and failed.
                states[table] = period_schema.COULD_NOT_LOAD
            if table not in states and table in held_back:
                # HELD BACK WITH ITS PACKAGE (REQ-PIPE-267 criterion 8): the
                # application this re-check runs in is not promoting the
                # supply staged for it, and the period holds none.
                states[table] = period_schema.HELD_BACK_WITH_PACKAGE
            if table not in states and table in resolution.ambiguous:
                # CONTESTED WINS THE REASON (REQ-PIPE-115 criteria 14 and
                # 15): the file is here, twice, and a slot reason would
                # send somebody after a supplier who has already sent it.
                states[table] = period_schema.CONTESTED
            if table not in states:
                try:
                    dataset_id = hierarchy.dataset_for_table(table).dataset_id
                    states[table] = supply_state(conn, dataset_id, period, as_at) or ""
                    if states[table] == period_schema.NOT_YET_DUE:
                        due[table] = due_at_of(dataset_id, period, as_at)
                except Exception:  # noqa: BLE001 - the catch-all covers it
                    states[table] = ""
            verdict = period_schema.check_readiness(
                [table], wrapped,
                supply_states={table: states[table]} if states[table] else {},
                due_at={table: due.get(table)})
            if verdict is not None:
                found.append((table, verdict))
        if not found:
            continue
        # ONE RECORD NAMING EVERY UNREADABLE TABLE (REQ-PIPE-115 criterion
        # 2 as amended 2026-10-05, Keith) - it used to name only the first.
        # RED WHATEVER THE REASONS (REQ-PIPE-270 criterion 1); the code the
        # record carries is the most specific of them, by the same
        # precedence check_readiness applies to one table.
        rank = {code: i for i, code in enumerate(period_schema._MISSING_PRECEDENCE)}
        first_table, first = min(found, key=lambda tv: (rank.get(tv[1].reason, len(rank)),
                                                         tv[0]))
        meta = checks_by_id.get(check)
        out.append({
            "agency_id": parsed.agency,
            "collection_id": parsed.collection,
            "dataset_id": parsed.dataset,
            "check_id": check,
            "check_name": getattr(meta, "name", None) or parsed.check_name,
            "column_name": first_table,
            "dimension": "completeness",
            "label": LABEL,
            "run_id": run_id,
            "run_timestamp": run_timestamp,
            "status": "fail",
            "metric_value": None,
            "unit": None,
            "warn_threshold": None,
            "fail_threshold": None,
            "row_count_total": None,
            "row_count_invalid": None,
            "on_fail_action": "flag",
            "engine": getattr(meta, "tool", None) or parsed.tool,
            "unrunnable_table": first_table,
            "unrunnable_tables": [t for t, _ in found],
            "unrunnable_code": first.reason,
            # EACH TABLE'S OWN REASON, structured (criterion 4), and the
            # instant a not-yet-due one falls due.
            "unrunnable_codes": {t: v.reason for t, v in found},
            **({"unrunnable_due_at": first.due_at.isoformat()}
               if first.due_at is not None else {}),
            "unrunnable_reason": ("; ".join(v.describe() for _, v in found)
                                  + ". This check did not fail - it could not be evaluated."),
        })
    return out


def results_for_trial(*, run_id: str, run_timestamp: str, resolution: supply_db.Resolution,
                      reads: dict[str, list[str]], checks_by_id: dict | None = None,
                      left_out_ids=()) -> list[dict]:
    """The not-evaluated records for a TRIAL - one per check reading a
    table the trial could not read, naming every such table (criteria 2
    and 17 as amended 2026-10-05; delivery critic on 8a942e7, H2).

    A trial checks whatever files it was handed and is filed to no period,
    so the reason is simply that the table was not readable in this trial -
    not among its files, or its file could not be loaded. No data rather
    than red: a trial decides nothing.
    """
    missing = ((set(resolution.absent) | set(resolution.ambiguous)) - set(resolution.held)
               - set(resolution.resolved))
    if not missing:
        return []
    from qa_tools.common import hierarchy

    checks_by_id = checks_by_id or {}
    out: list[dict] = []
    # EVERY CHECK THAT READS AN UNREADABLE TABLE: what it declares it reads,
    # and - for a check the tools LEFT OUT - its own dataset's table. A
    # left-out check nothing unreadable explains gets no record here, so
    # the reconciliation still refuses it.
    candidates = {c: list(t) for c, t in reads.items()}
    for check in left_out_ids:
        candidates.setdefault(check, [])
    for check, declared in sorted(candidates.items()):
        parsed = check_id_mod.try_parse(check)
        if parsed is None:
            continue
        tables = set(declared)
        if check in left_out_ids:
            try:
                tables.add(hierarchy.dataset(parsed.dataset).table)
            except Exception:  # noqa: BLE001 - not one of ours, nothing to say
                pass
        unreadable = sorted(tables & missing)
        if not unreadable:
            continue
        meta = checks_by_id.get(check)
        out.append({
            "agency_id": parsed.agency, "collection_id": parsed.collection,
            "dataset_id": parsed.dataset, "check_id": check,
            "check_name": getattr(meta, "name", None) or parsed.check_name,
            "column_name": unreadable[0], "dimension": "completeness", "label": LABEL,
            "run_id": run_id, "run_timestamp": run_timestamp, "status": "nodata",
            "metric_value": None, "unit": None, "warn_threshold": None,
            "fail_threshold": None, "row_count_total": None, "row_count_invalid": None,
            "on_fail_action": "flag", "engine": getattr(meta, "tool", None) or parsed.tool,
            "unrunnable_table": unreadable[0], "unrunnable_tables": unreadable,
            "unrunnable_code": TRIAL_UNREADABLE,
            "unrunnable_reason": (f"{', '.join(unreadable)} could not be read in this trial - "
                                  f"not among its files, or the file could not be loaded. "
                                  f"This check did not fail - it could not be evaluated."),
        })
    return out


def describe(results) -> str:
    """One line for the terminal, never one per result."""
    if not results:
        return ""
    by_code: dict[str, set[str]] = {}
    for r in results:
        # EVERY TABLE THE RECORD NAMES, not the first (delivery critic on
        # 8a942e7) - the record carries them all since criterion 2's
        # amendment - EACH UNDER ITS OWN REASON (REQ-PIPE-270 criterion 4).
        codes = r.get("unrunnable_codes") or {}
        for table in r.get("unrunnable_tables") or [r["unrunnable_table"]]:
            by_code.setdefault(codes.get(table) or r["unrunnable_code"], set()).add(table)
    # IN WORDS, NEVER A CATCH-ALL (criterion 5): words_for raises for a code
    # nobody described.
    parts = "; ".join(f"{words_for(code)}: {', '.join(sorted(t))}"
                      for code, t in sorted(by_code.items()))
    return (f"{len(results)} check(s) could not be evaluated for want of a table - "
            f"{parts}. None of them is a verdict on anybody's data.")
