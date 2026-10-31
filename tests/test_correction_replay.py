"""A replay stages a declared correction: reverted until its merge date, then
confirmed as the asset manager would (REQ-PIPE-170 criterion 23; Keith,
2026-10-11, answer (n) and its two follow-ups).

Each arrival is filed against the agreement as it stood at its receipt - a
correction dated D counts from the START of D on the asset's clock - and the
bootstrap confirms each due correction once both collections' replays have
finished, through the same confirm() a person uses, as the synthetic actor
during playback. Each test failed before the change.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import pytest

import filing_support
from conftest import drop_qa_schema
from qa_tools.common import (agreement_freeze, asset_time, assignment, correction_apply,
                             correction_replay, people, qa_store, schedule, supply_db)
from test_correction_apply import _docs, _grace, _move_q3

PERTH = timezone(timedelta(hours=8))


def _declare(docs, change, reference, day):
    """`docs` with `change` made and declared as a correction `reference`
    dated `day`, on each owner it touches - as a merged correction is."""
    base_cal, base_asset = docs
    cal, asset = copy.deepcopy(base_cal), copy.deepcopy(base_asset)
    change(cal, asset)
    found = agreement_freeze.changed(base_cal, cal, base_asset, asset)
    by_owner: dict = {}
    for key, (item, old, new, _f) in found.items():
        by_owner.setdefault(item.owner, []).append({"item": key, "old": old, "new": new})
    for owner, changes in by_owner.items():
        entry = {"change_reference": reference, "date": day, "author": "a", "approver": "b",
                 "reason": "the agreement was wrong", "changes": changes}
        if owner[0] == "calendar":
            target = next(c for c in cal["calendars"] if str(c["name"]) == owner[1])
        else:
            target = next(d for d in cal["datasets"] if str(d["id"]) == owner[1])
        target["corrections"] = list(target.get("corrections") or []) + [entry]
    return cal, asset


def _q3_date(agr=None) -> date:
    return next(p.date for p in schedule.periods_for_calendar(
        "quarterly", until=date(2024, 1, 1)) if p.name == "2023-Q3")


@pytest.fixture
def two(monkeypatch):
    """CAB-1 moves the 2023-Q3 round (cp-clients' 2023-Q4) to 20 October, merged 2026-01-10; CAB-2 shortens
    cp-clients' grace, merged 2026-02-10."""
    from qa_tools.common import correction_trial

    docs = _declare(_docs(), _move_q3, "CAB-1", "2026-01-10")
    docs = _declare(docs, _grace, "CAB-2", "2026-02-10")
    monkeypatch.setattr(correction_trial, "working", lambda: docs)
    return docs


class TestTheAgreementAsItStood:
    def test_a_correction_counts_from_the_start_of_its_date(self, two):
        [cab1] = [p for p in correction_apply._declared(*two) if p.reference == "CAB-1"]
        assert correction_replay.merge_instant(cab1) == asset_time.start_of_day(
            date(2026, 1, 10))

    def test_before_its_merge_date_it_is_reverted(self, two):
        from qa_tools.common import correction_trial

        before = asset_time.start_of_day(date(2026, 1, 10)) - timedelta(seconds=1)
        with correction_trial.configured(*correction_replay.docs_at(before)):
            assert _q3_date() != date(2023, 10, 20)
        with correction_trial.configured(*correction_replay.docs_at(
                asset_time.start_of_day(date(2026, 1, 10)))):
            assert _q3_date() == date(2023, 10, 20)

    def test_nothing_is_staged_once_every_correction_is_merged(self, two):
        assert correction_replay.staged(datetime(2026, 3, 1, tzinfo=PERTH)) is None


@dataclass(frozen=True)
class _Arrival:
    run_id: str
    received_at: datetime
    delivery_name: str = "d"


class TestEachArrivalIsFiledAsItStood:
    def test_the_replay_processes_each_arrival_under_its_own_agreement(
            self, two, monkeypatch):
        from qa_tools.common import arrival_lifecycle, replay_clock

        seen = {}

        def process(arrival, **_k):
            seen[arrival.run_id] = _q3_date()
            return []
        monkeypatch.setattr(arrival_lifecycle, "process", process)
        arrivals = [_Arrival("early", datetime(2026, 1, 9, 12, tzinfo=PERTH), "d1"),
                    _Arrival("late", datetime(2026, 1, 11, 12, tzinfo=PERTH), "d2")]
        with replay_clock.replaying():
            arrival_lifecycle.process_all(arrivals, steps=None, run_by="me")
        assert seen["early"] != date(2023, 10, 20)
        assert seen["late"] == date(2023, 10, 20)

    def test_outside_a_replay_nothing_is_reverted(self, two, monkeypatch):
        """The processing pass files against the agreement on disk - a real
        asset's history is never re-staged."""
        from qa_tools.common import arrival_lifecycle

        def staged(_arrival):
            raise AssertionError("staged outside a replay")
        monkeypatch.setattr(correction_replay, "for_arrival", staged)
        monkeypatch.setattr(arrival_lifecycle, "process", lambda arrival, **_k: [])
        arrival_lifecycle.process_all([_Arrival("x", datetime(2025, 1, 1, tzinfo=PERTH))],
                                      steps=None, run_by="me")


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-correction-replay") as c:
        # FROM NOTHING: the decision log is append-only, and the history's
        # end reads it, so an earlier test's decisions would move it.
        drop_qa_schema(c)
        qa_store.ensure_schema(c)
        c.execute(f'TRUNCATE "{qa_store.SCHEMA}".filing CASCADE')
        c.execute(f'TRUNCATE "{qa_store.SCHEMA}".correction_applied')
        c.execute(f'TRUNCATE "{qa_store.SCHEMA}".correction_parked CASCADE')
        filing_support.file(assignment.Assignment(
            dataset_id="cp-clients", supply_id="replay-s", slot="2023-Q4",
            branch=assignment.OPEN_UNFILLED, considered=("2023-Q4",),
            received_at=datetime(2023, 8, 1, 12, tzinfo=PERTH)))
        yield c
        c.execute(f'TRUNCATE "{qa_store.SCHEMA}".correction_applied')


class TestConfirmedAsTheManagerWould:
    def test_each_due_correction_is_confirmed_oldest_first_and_later_ones_wait(
            self, two, conn):
        done = correction_replay.confirm_due(
            conn, until=asset_time.start_of_day(date(2026, 2, 1)),
            effective_at="2026-02-01T00:00:00+08:00", say=lambda _m: None)
        assert done == ["CAB-1"]
        assert [p.reference for p in correction_apply.pending(conn)] == ["CAB-2"]
        actor = conn.execute(f"SELECT actor FROM {correction_apply.APPLIED}").fetchall()[0][0]
        with people.playback():
            assert actor == people.synthetic_actor()["email"]

    def test_by_default_every_correction_dated_up_to_now_is_confirmed(self, two, conn):
        done = correction_replay.confirm_due(conn, effective_at="2026-10-11T00:00:00+08:00",
                                             say=lambda _m: None)
        assert done == ["CAB-1", "CAB-2"]
        assert correction_apply.pending(conn) == []

    def test_it_moves_what_was_filed_before_the_merge(self, two, conn):
        from qa_tools.common import filing

        correction_replay.confirm_due(conn, effective_at="2026-10-11T00:00:00+08:00",
                                      say=lambda _m: None)
        assert filing.filing_for("cp-clients", "replay-s")["slot"] != "2023-Q4"


def _applied_at(conn) -> dict[str, datetime]:
    return {ref: at for ref, at in conn.execute(
        f"SELECT change_reference, applied_at FROM {correction_apply.APPLIED}").fetchall()}


class TestStampedWhereTheHistoryEnds:
    """post-build-review #177 (Keith, 2026-10-14, option b): a replay confirms
    each correction at the later of the replayed history's end and the start
    of the correction's own date - the same on every bootstrap, and never
    before the correction existed. It used to be the wall clock."""

    def test_a_correction_dated_after_the_history_is_stamped_on_its_own_date(self, two, conn):
        end = datetime(2025, 12, 1, 9, tzinfo=PERTH)
        correction_replay.confirm_due(conn, history_end=end, say=lambda _m: None)
        at = _applied_at(conn)
        assert at["CAB-1"] == asset_time.start_of_day(date(2026, 1, 10))
        assert at["CAB-2"] == asset_time.start_of_day(date(2026, 2, 10))

    def test_a_correction_dated_inside_the_history_is_stamped_at_its_end(self, two, conn):
        end = datetime(2026, 3, 1, 14, 30, tzinfo=PERTH)
        correction_replay.confirm_due(conn, history_end=end, say=lambda _m: None)
        assert set(_applied_at(conn).values()) == {end}

    def test_the_history_ends_at_the_last_instant_it_recorded(self, conn):
        assert correction_replay.history_end(conn) == datetime(2023, 8, 1, 12, tzinfo=PERTH)

    def test_a_bootstrap_never_stamps_the_wall_clock(self, two, conn, monkeypatch):
        from qa_tools.common import bootstrap

        monkeypatch.setattr(bootstrap, "_rebuild_results", lambda _short: None)
        # The fixture's supply has no staged table to re-check (REQ-GEN-205
        # criterion 8 runs what a confirmation owes; this is about the stamp).
        monkeypatch.setattr(bootstrap, "_run_what_the_confirmations_owe", lambda say: None)
        monkeypatch.setattr(asset_time, "now", lambda: datetime(2031, 1, 1, tzinfo=PERTH))
        bootstrap._confirm_corrections(say=lambda _m: None)
        at = _applied_at(conn)
        assert at["CAB-1"] == asset_time.start_of_day(date(2026, 1, 10))
        assert at["CAB-2"] == asset_time.start_of_day(date(2026, 2, 10))
