"""A replay of a synthetic history stages each declared correction: reverted
until its merge date, then confirmed as the asset manager would (REQ-PIPE-170
criterion 23; Keith, 2026-10-11, answer (n)).

WHY. A correction is merged part way through a real history: arrivals before
it are filed and judged against the agreement WITHOUT it, and its
confirmation then moves and re-judges them. A replay that read the
configuration on disk for every arrival would file the whole history as
though the correction had always been there, so its confirmation would have
nothing to do - and the history would never show one.

WHEN IT IS MERGED (Keith): from the START of its date on the asset's clock,
so every arrival received that day is filed under the corrected agreement.

WHEN IT IS CONFIRMED (Keith): once BOTH collections' replays have finished.
They replay side by side, in processes of their own, and a correction is
asset-wide - one confirmation, moving supplies in both - so the bootstrap
confirms each due correction after both, stamped at the end of the replay
rather than on its merge date. Rejected: replaying the collections one after
the other, or as one merged stream, either of which costs the parallel
replay.

AS THE MANAGER WOULD: through correction_apply.confirm(), the one path a
person's confirmation takes, as the synthetic actor - who holds the asset
manager role during playback only, on an asset that declares itself
synthetic (people.require_role). Nothing here writes a move of its own.

Only during a replay (`replay_clock.active()`): the processing pass files
against the agreement on disk, as a real asset always does.
"""
from __future__ import annotations

import contextlib
from datetime import date, datetime

from qa_tools.common import asset_time, correction_apply, correction_trial


def merge_instant(p: correction_apply.Pending) -> datetime:
    """The first instant of the correction's date, on the asset's clock."""
    return asset_time.start_of_day(date.fromisoformat(p.date[:10]))


def _declared(docs) -> list[correction_apply.Pending]:
    return correction_apply._declared(*docs)


def docs_at(instant: datetime, docs: tuple[dict, dict] | None = None) -> tuple[dict, dict]:
    """The configuration as it stood at `instant`: every declared correction
    merged after it reverted, the latest first."""
    from qa_tools.common import agreement_freeze

    cal, asset = docs or correction_trial.working()
    for p in reversed(_declared((cal, asset))):
        if merge_instant(p) > instant:
            cal, asset = agreement_freeze.revert(cal, asset, list(p.changes))
    return cal, asset


def staged(instant: datetime):
    """A context in which the agreement is as it stood at `instant`, or None
    where every declared correction was already merged by then - the common
    case, which then costs nothing."""
    docs = correction_trial.working()
    if not any(merge_instant(p) > instant for p in _declared(docs)):
        return None
    return correction_trial.configured(*docs_at(instant, docs))


def for_arrival(arrival):
    """`staged()` for an arrival's receipt, as a context that is always
    enterable - for arrival_lifecycle.process_all."""
    return staged(arrival.received_at) or contextlib.nullcontext()


def history_end(conn) -> datetime | None:
    """The last instant the replayed history recorded: its latest receipt or
    decision taking effect. None for an empty history."""
    from qa_tools.common import qa_store

    qa_store.ensure_schema(conn)
    row = conn.execute(
        f'SELECT max(t) FROM (SELECT received_instant AS t FROM "{_qa()}".supply_receipt '
        f'UNION ALL SELECT effective_at FROM "{_qa()}".decision) AS instants').fetchone()
    return row[0] if row else None


def _qa() -> str:
    from qa_tools.common import qa_store

    return qa_store.SCHEMA


def confirm_due(conn=None, *, until: datetime | None = None, effective_at: str | None = None,
                history_end: datetime | None = None, say=print) -> list[str]:
    """Confirm every pending correction merged by `until` (default now), the
    oldest first, as the asset manager during playback. Returns the
    references confirmed. A refusal stops here, loudly: a history silently
    missing a confirmation is what REQ-GEN-044 exists to prevent.

    STAMPED WHERE THE HISTORY ENDS (post-build-review #177; Keith,
    2026-10-14, option b): given `history_end`, each correction is
    confirmed at the later of it and the start of the correction's own
    date - the same on every bootstrap, and never before the correction
    existed. Rejected: the wall clock (a different stamp every run), and the
    history's end alone (it confirmed REQ-PIPE-181, dated 2026-10-11, on
    2026-09-22)."""
    from qa_tools.common import people, replay_clock, supply_db

    until = until or asset_time.now()
    at = effective_at or (replay_clock.now() if replay_clock.active()
                          else asset_time.now()).isoformat()
    owned = conn is None
    ctx = supply_db.connect(label="mothman:correction-replay") if owned \
        else contextlib.nullcontext(conn)
    done: list[str] = []
    with ctx as db, people.playback():
        from qa_tools.common import qa_store

        qa_store.ensure_schema(db)
        actor = people.synthetic_actor()
        for p in correction_apply.pending(db):
            if merge_instant(p) > until:
                continue
            stamp = at if history_end is None or effective_at else \
                max(history_end, merge_instant(p)).isoformat()
            applied = correction_apply.confirm(db, p.reference, actor=actor, effective_at=stamp)
            done.append(p.reference)
            say(f"Confirmed correction {p.reference} as the data asset's manager: "
                f"{len(applied.moved)} moved, {len(applied.placed)} placed, "
                f"{len(applied.held)} held, {len(applied.parked)} parked, "
                f"{len(applied.rejudged)} re-judged in place.")
    return done
