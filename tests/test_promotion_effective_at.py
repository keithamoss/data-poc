"""When a promotion took effect (REQ-PIPE-081, supporting criteria 1-3).

THE PROBLEM THIS SOLVES is that as-at-T had no history to answer over.
A bootstrap replays four years of arrivals under one wall clock, so
every promotion took effect within the same few minutes - 91 decisions
across one distinct day, measured 2026-10-02 - and "what did we hold
as at 30 June 2024" resolved to nothing in place, for everything.

Meanwhile the ARRIVALS are backdated properly, across 2023-2026. So
the generator's fiction was internally inconsistent rather than
simply thin: the arrival said February 2023 and the promotion of that
same supply said today.

THE RULE IS NOT A REPLAY HACK, which matters because a flag saying
"we are pretending" would have to be plumbed through the orchestrators
and would be wrong the moment somebody forgot it. Two things are true
of any promotion, synthetic or real:

    it cannot have taken effect BEFORE the supply arrived, and
    it cannot have taken effect in the FUTURE.

so  effective_at = min(now, received_at + lag).

In production an arrival is minutes old, `received_at + lag` is ahead
of now, and the rule gives `now` - which is correct and unchanged. In
replay the arrival is years old, so it gives the backdated instant.
The same expression, no mode to get wrong.

THE LAG ITSELF IS INVENTED AND IS SAID TO BE, because Keith chose it
(2026-10-02) over promoting at the arrival instant, so that
REQ-PIPE-080's receipt-to-promotion interval shows a spread rather
than a column of zeros. It is seeded off the run id, so it is stable
across regenerations like everything else here - but nobody should
read a particular supply's "waited 14h" as a measurement of anything.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from qa_tools.common import promotion

PERTH = timezone(timedelta(hours=8))
LONG_AGO = datetime(2023, 2, 1, 9, tzinfo=PERTH)


class TestADecisionCannotPrecedeTheSupply:

    def test_a_historical_arrival_is_promoted_after_it_arrived(self):
        got = promotion.effective_at_for(LONG_AGO, now=datetime(2026, 10, 2, tzinfo=PERTH))
        assert got > LONG_AGO, "a promotion cannot take effect before the supply existed"

    def test_and_well_before_today(self):
        """The whole point: a replayed 2023 arrival must not be stamped
        with the instant the replay happened to run."""
        now = datetime(2026, 10, 2, tzinfo=PERTH)
        got = promotion.effective_at_for(LONG_AGO, now=now)
        assert got.year == 2023, f"still stamped at replay time: {got}"


class TestADecisionCannotBeTakenInTheFuture:

    def test_a_supply_that_just_arrived_is_promoted_now_not_later(self):
        """Production, where this must not change behaviour: an arrival
        minutes old plus a lag is AHEAD of now, and a decision log
        entry dated in the future is simply wrong."""
        now = datetime(2026, 10, 2, 12, tzinfo=PERTH)
        just_now = now - timedelta(minutes=5)
        assert promotion.effective_at_for(just_now, now=now) == now

    def test_the_boundary_holds_rather_than_overshooting(self):
        now = datetime(2026, 10, 2, 12, tzinfo=PERTH)
        for minutes_ago in (0, 1, 60, 60 * 24, 60 * 24 * 365):
            got = promotion.effective_at_for(now - timedelta(minutes=minutes_ago), now=now)
            assert got <= now, f"{minutes_ago}m ago produced a future decision: {got}"


class TestItIsSeededLikeEverythingElseHere:

    def test_the_same_arrival_always_gets_the_same_instant(self):
        now = datetime(2026, 10, 2, tzinfo=PERTH)
        first = promotion.effective_at_for(LONG_AGO, now=now, seed="cp_run_001")
        again = promotion.effective_at_for(LONG_AGO, now=now, seed="cp_run_001")
        assert first == again, "regenerating must reproduce the same history"

    def test_different_arrivals_get_different_lags(self):
        """Otherwise every supply shows an identical wait, which is a
        column of the same number rather than a spread - the thing
        promoting at the arrival instant would have given."""
        now = datetime(2026, 10, 2, tzinfo=PERTH)
        lags = {promotion.effective_at_for(LONG_AGO, now=now, seed=f"run_{i}")
                for i in range(12)}
        assert len(lags) > 6, f"only {len(lags)} distinct instants across 12 runs"

    def test_the_lag_is_plausible_rather_than_arbitrary(self):
        """Hours to a couple of days - long enough to be a person
        getting to it, short enough not to look like neglect."""
        now = datetime(2026, 10, 2, tzinfo=PERTH)
        for i in range(50):
            got = promotion.effective_at_for(LONG_AGO, now=now, seed=f"run_{i}")
            assert timedelta(hours=1) <= got - LONG_AGO <= timedelta(days=3), got - LONG_AGO


class TestTheLagNeverRunsPastTheNextArrival:
    """Keith, 2026-10-06 (post-build-review #117 D5): the invented lag could
    carry a promotion past the next arrival of the same dataset, so the asset
    timeline showed two versions waiting for days. It is capped just before
    the next arrival, and never earlier than its own."""

    def test_capped_before_the_next_arrival(self):
        nxt = LONG_AGO + timedelta(minutes=30)
        got = promotion.effective_at_for(LONG_AGO, now=datetime(2026, 10, 2, tzinfo=PERTH),
                                         seed="x", before=nxt)
        assert LONG_AGO <= got < nxt

    def test_no_next_arrival_leaves_the_lag_alone(self):
        now = datetime(2026, 10, 2, tzinfo=PERTH)
        assert promotion.effective_at_for(LONG_AGO, now=now, seed="x", before=None) == \
            promotion.effective_at_for(LONG_AGO, now=now, seed="x")

    def test_the_next_arrival_is_read_from_the_recorded_deliveries(self, supply_dsn):
        import uuid
        from types import SimpleNamespace

        from qa_tools.common import qa_store, supply_db

        ds = f"cp-{uuid.uuid4().hex[:10]}"
        with supply_db.connect(label="test-next-receipt") as conn:
            qa_store.ensure_schema(conn)
            for n, minutes in enumerate((0, 45, 90)):
                name = f"d-{ds}-{n}"
                at = (LONG_AGO + timedelta(minutes=minutes)).isoformat()
                conn.execute(f'INSERT INTO "{qa_store.SCHEMA}".delivery '
                             "(name, received_at, received_instant) VALUES (?, ?, ?)",
                             [name, at, at])
                conn.execute(f'INSERT INTO "{qa_store.SCHEMA}".delivery_file (delivery, '
                             "filename, dataset_id, received_at, received_instant, "
                             "received_from, receipt_sequence) VALUES (?, ?, ?, ?, ?, ?, ?)",
                             [name, "f.csv", ds, at, at, "our-clock", 1])
        arrival = SimpleNamespace(received_at=LONG_AGO, files_by_dataset={ds: ("f.csv",)})
        assert promotion.next_receipt(arrival) == LONG_AGO + timedelta(minutes=45)
        assert promotion.next_receipt(SimpleNamespace(received_at=None)) is None
