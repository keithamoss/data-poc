"""A supply arriving after its dataset's schedule has ended is held as
schedule-ended and says what to edit (REQ-PIPE-154, signed by Keith
2026-10-06)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from qa_tools.common import assignment, qa_store, schedule, slots, supply_db, supply_holds

UTC = timezone.utc


def _slot(name: str, opens: datetime, closes: datetime | None) -> slots.Slot:
    return slots.Slot(dataset_id="cp-carers", period=schedule.Period(name=name, date=opens.date()),
                      due_at=opens, grace=timedelta(0), claim_opens_at=opens, closes_at=closes)


SLOTS = [_slot("2027-Q3", datetime(2027, 7, 1, tzinfo=UTC), datetime(2027, 10, 1, tzinfo=UTC)),
         # The calendar's LAST period: it closes as long after it opened as
         # the one before it stayed open (REQ-PIPE-131 criterion 16).
         _slot("2027-Q4", datetime(2027, 10, 1, tzinfo=UTC), datetime(2027, 12, 31, tzinfo=UTC))]
AFTER = datetime(2030, 3, 1, tzinfo=UTC)


class TestTheRuleKnowsTheScheduleEnded:

    def test_after_the_last_slot_closes_it_is_held_as_schedule_ended(self):
        decided = assignment.assign("cp-carers", "cp-carers@x", AFTER, SLOTS, frozenset(), final_period="2027-Q4")
        assert decided.is_held
        assert decided.schedule_ended
        assert decided.last_period == "2027-Q4"

    def test_the_reason_never_claims_a_next_period_opened(self):
        """Criterion 4: an exhausted calendar has no next period."""
        decided = assignment.assign("cp-carers", "cp-carers@x", AFTER, SLOTS, frozenset(), final_period="2027-Q4")
        said = " ".join(why for _, why in decided.unavailable)
        assert "next period's claim window" not in said
        assert "2027-Q4" in [name for name, _ in decided.unavailable]

    def test_a_gap_inside_the_calendar_is_not_schedule_ended(self):
        early = datetime(2027, 6, 1, tzinfo=UTC)
        decided = assignment.assign("cp-carers", "cp-carers@x", early, SLOTS, frozenset(), final_period="2027-Q4")
        assert decided.is_held and not decided.schedule_ended

    def test_a_last_slot_that_never_closes_is_never_ended(self):
        one = [_slot("2027-Q4", datetime(2027, 10, 1, tzinfo=UTC), None)]
        decided = assignment.assign("cp-carers", "cp-carers@x", AFTER, one, frozenset(), final_period="2027-Q4")
        assert not decided.is_held and not decided.schedule_ended


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-schedule-ended") as c:
        qa_store.ensure_schema(c)
        c.execute(f"DELETE FROM {supply_holds.TABLE}")
        yield c


class TestTheHoldSaysWhatToEdit:

    def _held(self, conn, supply="cp-carers@20300301"):
        decided = assignment.assign("cp-carers", supply, AFTER, SLOTS, frozenset(), final_period="2027-Q4")
        supply_holds.raise_hold(conn, dataset_id="cp-carers", supply_id=supply,
                                kind=supply_holds.ASSIGNMENT_RULE,
                                reason=supply_holds.reason_for(decided),
                                raised_by="run_x", delivery="d")
        return supply_holds.hold_on(conn, "cp-carers", supply)

    def test_schedule_ended_is_a_structured_field(self, conn):
        """Criterion 2: no reader parses prose to tell."""
        held = self._held(conn)
        assert held.reason["schedule_ended"] is True
        assert held.reason["last_period"] == "2027-Q4"
        assert held.schedule_ended

    def test_it_names_the_file_and_the_command(self, conn):
        """Criterion 3."""
        said = self._held(conn).describe()
        assert "contract/data-asset.yaml" in said
        assert "mothman schedule candidate-dates" in said
        assert "2027-Q4" in said
        assert "next period's claim window" not in said

    def test_the_tally_counts_them_apart(self, conn):
        """Criterion 6's count, read as one aggregate."""
        self._held(conn, "cp-carers@a")
        self._held(conn, "cp-carers@b")
        counted = supply_holds.tally(conn)
        assert counted.schedule_ended == (1, 2)   # datasets, supplies


class TestAddingDatesFilesWhatWasHeld:
    """Criterion 7 (Keith, 2026-10-06): once dates cover a held supply's
    receipt, the next processing pass re-files it by the rule, in receipt
    order, and resolves its hold naming the filing that replaced it."""

    def _held(self, conn, supply, at):
        import filing_support
        decided = assignment.assign("cp-carers", supply, at, SLOTS, frozenset(), final_period="2027-Q4")
        assert decided.schedule_ended
        filing_support.file(decided)
        supply_holds.raise_hold(conn, dataset_id="cp-carers", supply_id=supply,
                                kind=supply_holds.ASSIGNMENT_RULE,
                                reason=supply_holds.reason_for(decided),
                                raised_by="run_x", delivery=f"pytest-cp-carers-{supply}")

    def test_dates_added_files_it_and_ends_the_hold(self, conn, monkeypatch):
        from qa_tools.common import filing, recheck, schedule_ended

        supply = f"cp-carers@{AFTER:%Y%m%d}a"
        self._held(conn, supply, AFTER)
        # DATES ADDED: the calendar now runs to a 2030 period covering it.
        later = SLOTS + [_slot("2030-Q1", datetime(2030, 1, 1, tzinfo=UTC),
                               datetime(2030, 4, 1, tzinfo=UTC))]
        monkeypatch.setattr(slots, "slots_for_dataset", lambda dataset_id, until=None: later)
        monkeypatch.setattr(schedule_ended, "_on_calendar", lambda dataset_id, period: True)

        done = schedule_ended.refile_covered(say=lambda line: None)

        assert [(d, s, slot) for d, s, slot in done] == [("cp-carers", supply, "2030-Q1")]
        current = filing.filing_for("cp-carers", supply)
        assert current["slot"] == "2030-Q1"
        assert supply_holds.hold_on(conn, "cp-carers", supply) is None
        [(resolved_by,)] = conn.execute(
            f"SELECT resolved_by FROM {supply_holds.TABLE} WHERE supply_id = ?",
            [supply]).fetchall()
        [(refiled_by,)] = conn.execute(
            f"SELECT refiled_by FROM {filing.TABLE} WHERE supply_id = ? AND slot = '2030-Q1'",
            [supply]).fetchall()
        assert resolved_by == refiled_by, "the hold names the decision behind the new filing"
        assert [o for o in recheck.owed(conn, "cp-carers") if o.supply_id == supply], \
            "a re-filed supply is owed its re-check, which applies the gate"

    def test_without_dates_nothing_moves(self, conn, monkeypatch):
        from qa_tools.common import schedule_ended

        supply = f"cp-carers@{AFTER:%Y%m%d}b"
        self._held(conn, supply, AFTER)
        monkeypatch.setattr(slots, "slots_for_dataset", lambda dataset_id, until=None: SLOTS)
        assert schedule_ended.refile_covered(say=lambda line: None) == []
        assert supply_holds.hold_on(conn, "cp-carers", supply) is not None

    def test_oldest_receipt_first(self, conn, monkeypatch):
        from qa_tools.common import schedule_ended

        first = f"cp-carers@{AFTER:%Y%m%d}c"
        second = f"cp-carers@{AFTER:%Y%m%d}d"
        self._held(conn, second, AFTER + timedelta(days=2))
        self._held(conn, first, AFTER)
        later = SLOTS + [_slot("2030-Q1", datetime(2030, 1, 1, tzinfo=UTC),
                               datetime(2030, 4, 1, tzinfo=UTC))]
        monkeypatch.setattr(slots, "slots_for_dataset", lambda dataset_id, until=None: later)
        monkeypatch.setattr(schedule_ended, "_on_calendar", lambda dataset_id, period: True)
        done = schedule_ended.refile_covered(say=lambda line: None)
        assert [s for _, s, _ in done] == [first, second]


class TestThePassSaysSo:
    """Criterion 6: a pass that holds supplies because a schedule ended says
    how many, across how many datasets, apart from any other hold."""

    def test_counted_from_the_runs_this_pass_made(self, conn):
        from qa_tools.common import schedule_ended

        for supply, run in (("cp-carers@e1", "run_a"), ("cp-carers@e2", "run_b"),
                            ("cp-carers@e3", "run_old")):
            decided = assignment.assign("cp-carers", supply, AFTER, SLOTS, frozenset(), final_period="2027-Q4")
            supply_holds.raise_hold(conn, dataset_id="cp-carers", supply_id=supply,
                                    kind=supply_holds.ASSIGNMENT_RULE,
                                    reason=supply_holds.reason_for(decided),
                                    raised_by=run, delivery="d")
        assert schedule_ended.raised_by_runs(conn, ["run_a", "run_b"]) == (1, 2)
        line = schedule_ended.pass_line((1, 2))
        assert "2 supplies" in line and "1 dataset" in line and "schedule" in line
        assert schedule_ended.pass_line((0, 0)) is None

    def test_the_terminal_summary_prints_it_apart(self, capsys):
        from cli import pipeline
        from qa_tools.common import processing_pass

        pipeline._say_pass(processing_pass.PassReport(processed=["r1"], schedule_ended=(1, 2),
                                                      refiled=[("cp-carers", "s", "2030-Q1")]))
        out = capsys.readouterr().out
        assert "2 supplies across 1 dataset held because the dataset's schedule has ended" in out
        assert "1 supply/supplies held for an ended schedule were filed" in out


class TestTheNoticeReadsHoldRecords:
    """REQ-DASH-155 criteria 1-4: the figures come from hold records, carried
    as receipt and resolution instants so the page can answer as at any
    in-place-on date - never from supply rows."""

    def test_each_schedule_ended_hold_with_its_receipt_and_resolution(self, conn):
        import filing_support
        from qa_tools.common import schedule_ended

        decided = assignment.assign("cp-carers", "cp-carers@n1", AFTER, SLOTS, frozenset(), final_period="2027-Q4")
        filing_support.file(decided)
        supply_holds.raise_hold(conn, dataset_id="cp-carers", supply_id="cp-carers@n1",
                                kind=supply_holds.ASSIGNMENT_RULE,
                                reason=supply_holds.reason_for(decided), raised_by="r",
                                delivery="pytest-cp-carers-cp-carers@n1")
        got = schedule_ended.for_dataset("cp-carers", conn=conn)
        from qa_tools.common import asset_time
        assert len(got) == 1 and got[0]["resolvedAt"] is None
        assert asset_time.parse_instant(got[0]["receivedAt"], "x") == AFTER


class TestExhaustedFromWhenTheLastSlotCloses:
    """REQ-DASH-155 criterion 6 (Keith, 2026-10-06): the page and the
    pipeline agree on the day - not from the last period's date, which is
    about a period early."""

    def test_not_exhausted_while_the_last_slot_is_still_open(self):
        from qa_tools.common import asset_time, runway, schedule, slots as slots_mod
        from qa_tools.common import hierarchy

        checked = 0
        for entry in hierarchy.all_datasets():
            try:
                cal = schedule.calendar_for_dataset(entry.dataset_id)
            except schedule.NoCalendarAgreed:
                continue
            if cal.current.is_cadence_rule:
                continue
            last = slots_mod.slots_for_dataset(entry.dataset_id)[-1]
            if last.closes_at is None:
                continue
            between = last.period.date + timedelta(days=1)
            closed = asset_time.localise(last.closes_at).date()
            assert between < closed, "the test needs a gap to look into"
            assert entry.dataset_id not in runway.exhausted_datasets(between), \
                f"{entry.dataset_id} read exhausted while {last.name} was still open"
            assert entry.dataset_id in runway.exhausted_datasets(closed)
            checked += 1
        assert checked, "no authored calendar to check against"


class TestATruncatedSlotListIsNotAnEndedSchedule:
    """DEFECT, 2026-10-06, caught by REQ-PIPE-156's whole-history comparison:
    filing hands assign() the slots up to the arrival's claim horizon, not the
    whole calendar, so for a dataset that skips quarters the last slot in the
    list is not the calendar's last - and two 2023 Case Workers supplies were
    labelled schedule-ended with a 2027 calendar ahead of them."""

    def test_a_case_workers_supply_in_2023_is_not_schedule_ended(self):
        from datetime import date

        from qa_tools.common import filing

        dataset = "cp-case-workers"
        at = datetime(2023, 5, 1, 1, 0, tzinfo=UTC)
        truncated = slots.slots_for_dataset(
            dataset, until=slots.claimable_until(dataset, date(2023, 5, 1)))
        decided = assignment.assign(dataset, f"{dataset}@x", at, truncated, frozenset(),
                                    final_period=filing.final_period_for(dataset))
        assert not decided.schedule_ended, decided.unavailable
        said = " ".join(why for _, why in decided.unavailable)
        assert "last period this dataset's schedule has" not in said

    def test_after_the_real_last_slot_it_still_is(self):
        decided = assignment.assign("cp-carers", "cp-carers@y", AFTER, SLOTS, frozenset(),
                                    final_period="2027-Q4")
        assert decided.schedule_ended and decided.last_period == "2027-Q4"

    def test_a_calendar_with_no_final_period_never_ends(self):
        decided = assignment.assign("cp-carers", "cp-carers@z", AFTER, SLOTS, frozenset(),
                                    final_period=None)
        assert decided.is_held and not decided.schedule_ended
