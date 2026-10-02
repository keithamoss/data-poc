"""A slot whose claim window has opened is a slot a supply can claim
(post-build-review #73, fixing REQ-PIPE-057/REQ-PIPE-062).

THE CLAIM WINDOW IS WHAT MAKES `early` MEAN ANYTHING. A calendar
declares how long BEFORE a slot's due instant a supply may arrive and
still be recognised as that period's - 14 days for quarterly, 4 hours
for daily. Without it, everything arriving before the due date belongs
to no period at all.

THE BUG WAS A BOUND DOING TWO JOBS. `slots_for_dataset(until=...)`
passes `until` to `periods_for_dataset()`, where it means "stop
GENERATING at the period containing this date" - a bound a cadence-rule
calendar genuinely needs, because "every day" has no end of its own.
`filing.file_arrivals()` then used the arrival date as that bound, which
turned it into a SELECTION rule: a supply may only be filed to a period
that has already begun. That is the exact opposite of what the claim
window says.

WHY IT SURVIVED, AND WHY ONLY ONE FEED HAS IT. The bug bites only when
the window reaches back ACROSS a period boundary. Four hours never
leaves its own day, so Birth Registrations is immune; fourteen days
reaches a fortnight into the previous quarter, so Child Protection is
exposed for 14 days of every 91. The feed with 352 supplies behind it
is the one that works.

NOT EXERCISED BY THE REAL CORPUS: zero of its 150 supplies ever
arrived inside an excluded window, because the generator sends nothing
early. So this is written from the shape of the code rather than from a
wrong number on a page - and the reason it is worth fixing NOW is
REQ-GEN-044, whose job is to start generating early supplies. They
would have read LATE, by about a quarter, and the classifier would have
got the blame.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from qa_tools.common import assignment, slots as slots_mod


def _candidates(dataset_id: str, at: datetime):
    """The slots a FILING caller sees - the real pairing.

    The lookahead lives at the call site rather than inside
    `slots_for_dataset()` on purpose: that function also backs
    `mothman schedule show`, where quietly adding a quarter nobody
    asked for would be its own bug. So the thing under test is the
    pair, and the structural test below is what keeps the two real
    call sites using it.
    """
    return slots_mod.slots_for_dataset(
        dataset_id, until=slots_mod.claimable_until(dataset_id, at.date()))

PERTH = timezone(timedelta(hours=8))

QUARTERLY = "cp-clients"        # claim_window 14d - crosses the boundary
DAILY = "birth-registrations"   # claim_window 4h - never leaves its day

#: 2023-Q3 is due 2023-08-01 and its window opens 2023-07-18. This
#: instant is a week inside it, and in 2023-Q2 by the calendar.
A_WEEK_EARLY = datetime(2023, 7, 25, 9, tzinfo=PERTH)


class TestASlotIsOfferedOnceItsWindowOpens:

    def test_the_quarter_a_supply_is_early_for_is_among_its_candidates(self):
        """The whole bug in one assertion. 2023-Q3's window opened on
        the 18th, so a supply arriving on the 25th must be able to
        claim it."""
        offered = {s.period.name for s in _candidates(QUARTERLY, A_WEEK_EARLY)}
        assert "2023-Q3" in offered, (
            f"Q3's claim window opened 2023-07-18; a supply arriving "
            f"2023-07-25 was offered only {sorted(offered)}")

    def test_and_the_rule_files_it_there_rather_than_to_the_quarter_before(self):
        """Offered is not enough - `current_slot()` picks the newest
        slot whose window has opened, and that must now be Q3."""
        got = assignment.current_slot(_candidates(QUARTERLY, A_WEEK_EARLY),
                                      A_WEEK_EARLY)
        assert got is not None and got.period.name == "2023-Q3"

    def test_a_slot_whose_window_has_NOT_opened_is_still_withheld(self):
        """The negative case, and the one a careless fix breaks. Three
        weeks before Q3 is due, its window has not opened - offering it
        would let a supply claim forward into a slot nobody may claim
        yet, which is what the window exists to prevent."""
        too_soon = datetime(2023, 7, 10, 9, tzinfo=PERTH)
        offered = {s.period.name for s in _candidates(QUARTERLY, too_soon)}
        assert "2023-Q3" not in offered

    def test_the_daily_feed_is_unchanged(self):
        """It was never exposed - a 4h window never crosses a day - so
        the fix must not quietly add a day to its candidates either."""
        at = datetime(2026, 9, 5, 6, tzinfo=PERTH)
        offered = {s.period.name for s in _candidates(DAILY, at)}
        assert "2026-09-06" not in offered
        assert "2026-09-05" in offered


class TestEveryCandidateIsOneTheWindowAllows:
    """Asserted as the RULE rather than as these two dates, so a later
    change to either calendar cannot quietly reopen it."""

    def test_no_slot_with_an_open_window_is_ever_missing(self):
        for dataset, at in ((QUARTERLY, A_WEEK_EARLY),
                            (DAILY, datetime(2026, 9, 5, 6, tzinfo=PERTH))):
            names = {s.period.name for s in _candidates(dataset, at)}
            every = slots_mod.slots_for_dataset(
                dataset, until=at.date() + timedelta(days=400))
            missed = [s.period.name for s in every
                      if s.claim_opens_at <= at and s.period.name not in names]
            assert not missed, f"{dataset}: claimable but not offered: {missed}"

    def test_and_the_rule_never_PICKS_one_whose_window_is_shut(self):
        """The other direction, asserted where the design actually
        promises it. `slots_for_dataset()` has always returned the
        current period's slot before its window opens - the daily feed
        does it every morning - and `current_slot()` is what filters on
        claimability. So the invariant to protect is about the CHOICE,
        not about the list, and a fix that widens the list must not
        widen what the rule will claim."""
        for dataset, at in ((QUARTERLY, A_WEEK_EARLY),
                            (DAILY, datetime(2026, 9, 5, 6, tzinfo=PERTH))):
            got = assignment.current_slot(_candidates(dataset, at), at)
            assert got is None or got.claim_opens_at <= at, (
                f"{dataset}: picked {got.period.name}, whose window opens "
                f"{got.claim_opens_at}, for an arrival at {at}")


class TestTheSlotStaysVisibleOnceFilled:
    """The downstream half, found by enumerating consumers rather than
    by a failing page - CLAUDE.md's own shape-change rule.

    Fixing the filing side means a supply CAN now be promoted into a
    quarter that has not begun. `slot_state` lists slots up to NOW, so
    without the same lookahead that filled slot is simply absent from
    the dashboard: the early supply would be accepted, promoted, and
    then invisible.
    """

    def test_a_slot_whose_window_is_open_is_listed_today(self):
        offered = {s.period.name for s in _candidates(QUARTERLY, A_WEEK_EARLY)}
        assert "2023-Q3" in offered

    def test_BOTH_call_sites_use_the_lookahead(self):
        """Structural, because the two drifting apart is the defect
        rather than either value being wrong on its own."""
        import inspect

        from qa_tools.common import filing, slot_state

        for where in (filing.file_arrivals, slot_state.states_for):
            assert "claimable_until" in inspect.getsource(where), (
                f"{where.__qualname__} must take the same claim-window "
                f"lookahead, or the two drift and a slot filled early is "
                f"accepted by one and invisible to the other")
