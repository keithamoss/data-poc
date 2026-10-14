"""Supplies held because their dataset's schedule ran out (REQ-PIPE-154).

A supply received after the last authored slot of its dataset's calendar
has closed has no date to be filed to, so the filing rule holds it - and
the hold says so as a field, `schedule_ended`, with the file and command
that fix it (supply_holds.reason_for). That much happens at filing.

THIS MODULE IS THE OTHER HALF: what a processing pass does about those
holds.

- It COUNTS the ones its own runs raised, so the pass's summary can say
  how many supplies across how many datasets a schedule stopped, apart
  from every other kind of hold (criterion 6).
- Once somebody has added dates, it RE-FILES them by the rule - each into
  the slot that was open at its receipt, oldest receipt first, as a rule
  `refile` decision whose filing replaces the held one. The decision ends
  the hold in its own transaction (decision_log.apply_decision), so the
  hold names the decision behind the new filing, and a re-check is owed,
  whose run applies the promotion gate (criterion 7; Keith, 2026-10-06:
  at thirty datasets, a person placing each one by hand does not scale).

A HOLD WHOSE DATES STILL DO NOT COVER IT STAYS EXACTLY AS IT IS. Nothing
is re-filed into a period its receipt was not open for, and a gap the new
dates leave is a gap - the same rule that held it in the first place.
"""
from __future__ import annotations

from qa_tools.common import supply_db, supply_holds

#: Who re-files a supply once dates exist - the filing rule, not a person.
ACTOR = "filing rule"


def raised_by_runs(conn, run_ids) -> tuple[int, int]:
    """(datasets, supplies) held because their schedule ended, by these runs.

    One aggregate, never a fetch of the supplies (NFR: at thirty datasets the
    summary is a count, not a list)."""
    return _labelled_by_runs(conn, run_ids).get("schedule ended", (0, 0))


def turned_off_by_runs(conn, run_ids) -> tuple[int, int]:
    """(datasets, supplies) these runs held while their dataset was turned off
    (REQ-PIPE-179 criterion 26)."""
    return _labelled_by_runs(conn, run_ids).get("turned off", (0, 0))


def _labelled_by_runs(conn, run_ids) -> dict[str, tuple[int, int]]:
    """The holds these runs raised, counted by the label worked out from
    configuration as it stands (REQ-PIPE-179 criterion 18, amending
    REQ-PIPE-154 criterion 6)."""
    ids = list(run_ids)
    if not ids:
        return {}
    rows = conn.execute(
        f"SELECT {supply_holds._COLUMNS} FROM {supply_holds._from()} "
        f"WHERE h.raised_by IN ({', '.join('?' for _ in ids)})", ids).fetchall()
    return supply_holds.label_counts(supply_holds._held_from(r) for r in rows)


def turned_off_pass_line(counts: tuple[int, int]) -> str | None:
    """The pass summary's line for REQ-PIPE-179 criterion 26, or None."""
    datasets, supplies = counts
    if not supplies:
        return None
    return (f"{supplies} {'supply' if supplies == 1 else 'supplies'} across {datasets} "
            f"{'dataset' if datasets == 1 else 'datasets'} received while turned off - "
            f"held, not needing a person; place, reject, or change effective_to/"
            f"effective_from in {supply_holds.SCHEDULE_FILE} if the period should be owed.")


def pass_line(counts: tuple[int, int]) -> str | None:
    """The pass summary's line for criterion 6, or None where there is none."""
    datasets, supplies = counts
    if not supplies:
        return None
    return (f"{supplies} {'supply' if supplies == 1 else 'supplies'} across {datasets} "
            f"{'dataset' if datasets == 1 else 'datasets'} held because the dataset's "
            f"schedule has ended - add dates in {supply_holds.SCHEDULE_FILE}; the next "
            f"pass files them.")


def _on_calendar(dataset_id: str, period: str) -> bool:
    from qa_tools.common import refiling
    return refiling._on_calendar(dataset_id, period)


def _covering_slot(dataset_id: str, received_at):
    """The slot open at this receipt under the dataset's calendar as it
    stands now, or None."""
    from qa_tools.common import assignment
    from qa_tools.common import slots as slots_mod

    try:
        found = slots_mod.slots_for_dataset(
            dataset_id, until=slots_mod.claimable_until(dataset_id, received_at.date()))
    except (ValueError, KeyError, FileNotFoundError):
        return None
    slot = assignment.open_slot(found, received_at)
    if slot is None or not _on_calendar(dataset_id, slot.name):
        return None
    return slot


def refile_covered(*, say=print, skip=frozenset()) -> list[tuple[str, str, str]]:
    """Re-file every assignment-rule hold whose receipt the configuration
    now gives an open owed slot - WHATEVER ITS LABEL (REQ-PIPE-179 criterion
    19, generalising REQ-PIPE-154's schedule-ended re-file rather than
    adding a second re-filer) - oldest receipt first. Returns (dataset,
    supply, period) for each. Every other hold is left for a person.

    `skip` names datasets not to touch - a refused one (REQ-PIPE-173), whose
    holds its own drain re-files."""
    return refile_holds(
        lambda conn: [h for h in supply_holds.outstanding(conn)
                      if h.kind == supply_holds.ASSIGNMENT_RULE and not h.agreement_refused
                      and h.dataset_id not in skip and h.label.covered_by],
        lambda h, slot: (f"Held because {h.reason_words()}; the configuration now covers "
                         f"its receipt, so the rule files it to {slot}."),
        lambda h, slot: (f"{h.supply_id}: the configuration now has {slot} open at its "
                         f"receipt, so it is filed there and owed a re-check"),
        say=say)


def refile_holds(select, reason, said, *, say=print) -> list[tuple[str, str, str]]:
    """Re-file the holds `select(conn)` returns into the slot open at each
    one's receipt, oldest receipt first, as a rule re-file owing a re-check -
    the one loop both a schedule-ended hold (REQ-PIPE-154) and a hold on a
    refused dataset (REQ-PIPE-173) are drained by once their cause is gone."""
    from qa_tools.common import (decision_log, filing, hierarchy, placing, qa_store,
                                 replay_clock, supply_files)

    done: list[tuple[str, str, str]] = []
    with supply_db.connect(label="mothman:refile-holds") as conn:
        qa_store.ensure_schema(conn)
        held = select(conn)
        if not held:
            return done
        received = {}
        for h in held:
            rows = conn.execute(
                f"SELECT received_instant FROM {filing.RECEIPT} "
                "WHERE dataset_id = ? AND supply_id = ?", [h.dataset_id, h.supply_id]).fetchall()
            if rows and rows[0][0] is not None:
                received[(h.dataset_id, h.supply_id)] = rows[0][0]
        # RECEIPT ORDER (criterion 7), so a backlog drains as it would have
        # filed had the dates been there all along.
        for h in sorted((h for h in held if (h.dataset_id, h.supply_id) in received),
                        key=lambda h: (received[(h.dataset_id, h.supply_id)], h.supply_id)):
            at = received[(h.dataset_id, h.supply_id)]
            slot = _covering_slot(h.dataset_id, at)
            if slot is None:
                continue
            entry = hierarchy.dataset(h.dataset_id)
            # ONE FILE OF A HELD CONTESTED PAIR goes with its partner, still
            # contested, and neither is checked until the pair is settled
            # (REQ-PIPE-179 criterion 19, REQ-PIPE-163 criterion 37). Both
            # files share the receipt, so both are covered by the same slot
            # and both are re-filed in this same pass.
            contested = supply_files.open_contest(conn, h.dataset_id, h.supply_id) is not None
            # THE ONE PLACER (REQ-PIPE-163 criterion 40).
            placing.place(
                conn, agency_id=entry.agency_id, collection_id=entry.collection_id,
                dataset_id=h.dataset_id, supply=h.supply_id, to_period=slot.name,
                actor=ACTOR, actor_kind=decision_log.RULE,
                effective_at=replay_clock.now().isoformat(), reason=reason(h, slot.name),
                owe=not contested)
            say(said(h, slot.name))
            done.append((h.dataset_id, h.supply_id, slot.name))
    return done


def for_dataset(dataset_id: str, conn=None) -> list[dict]:
    """Every hold raised because this dataset's schedule ended, resolved or
    not, as its receipt and resolution instants (REQ-DASH-155 criteria 1-4).

    FROM HOLD RECORDS ONLY - recorded QA metadata, never a supply row - and
    with both instants, so the page can say what was held AS AT whatever
    date it is showing. One query; held supplies are few by construction."""
    from qa_tools.common import filing

    if conn is None:
        with supply_db.connect(read_only=True, label="mothman:schedule-ended") as opened:
            return for_dataset(dataset_id, conn=opened)
    rows = conn.execute(
        f"SELECT r.received_instant, h.resolved_at FROM {supply_holds.TABLE} h "
        f"JOIN {filing.RECEIPT} r ON r.dataset_id = h.dataset_id AND r.supply_id = h.supply_id "
        "WHERE h.dataset_id = ? AND (h.reason->>'schedule_ended')::boolean IS TRUE "
        "ORDER BY r.received_instant", [dataset_id]).fetchall()
    return [{"receivedAt": received.isoformat(),
             "resolvedAt": resolved.isoformat() if resolved else None}
            for received, resolved in rows]
