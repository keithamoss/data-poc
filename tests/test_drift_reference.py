"""What drift and volume measure against (REQ-QAC-108 criteria 2-6).

Each test here is named for a WRONG answer the rule has to refuse,
because every one of them is a green check that asked nothing - which is
the dangerous direction and the reason this module exists at all.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from qa_tools.common import decision_log as dl
from qa_tools.common import (drift_reference, inheritance, promotion,
                             qa_store, rejection, schedule, substitution,
                             supply_db)

AGENCY = "child-protection-family-support"
COLLECTION = "child-protection"
DATASET = "cp-carers"
WHEN = "2026-09-29T09:00:00+08:00"


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-drift-reference") as c:
        qa_store.ensure_schema(c)
        yield c


@pytest.fixture
def dataset():
    return f"cp-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def calendar(monkeypatch):
    """Five periods of this test's own, oldest first and two months
    apart, so "walk back until a real supply" has somewhere to walk.
    Two rather than three because five quarters do not fit in a year."""
    tag = uuid.uuid4().hex[:6]
    names = [f"2099-{n}{tag}" for n in "ABCDE"]
    dates = {name: date(2099, 1 + i * 2, 1) for i, name in enumerate(names)}
    monkeypatch.setattr(drift_reference.schedule, "date_of",
                        lambda name, ds: dates.get(name))
    monkeypatch.setattr(schedule, "date_of", lambda name, ds: dates.get(name))
    return names


def _promote(conn, dataset_id, period):
    """A promoted supply, whose ID and TABLE are different strings - as
    they are in the real system, and as a test that conflated them
    hid for an hour on 2026-09-29."""
    arrival = uuid.uuid4().hex[:10]
    physical, supply = f"carers__{arrival}", f"{dataset_id}@{arrival}"
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')
    conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" (id integer)')
    promotion.promote(
        conn, agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset_id,
        supply=supply, period=period, physical_tables=[physical],
        actor="tester", actor_kind=dl.PERSON, effective_at=WHEN)
    return supply


class TestItIsTheMostRecentEARLIERPromotedPeriod:
    """Criteria 2 and 3."""

    def test_it_walks_back_past_periods_nothing_was_promoted_into(
            self, conn, dataset, calendar):
        a, _b, _c, _d, e = calendar
        first = _promote(conn, dataset, a)
        got = drift_reference.reference_for(conn, dataset, e)
        assert (got.period, got.supply) == (a, first)

    def test_the_nearest_earlier_one_wins(self, conn, dataset, calendar):
        a, _b, c, _d, e = calendar
        _promote(conn, dataset, a)
        nearer = _promote(conn, dataset, c)
        got = drift_reference.reference_for(conn, dataset, e)
        assert (got.period, got.supply) == (c, nearer)

    def test_the_current_periods_own_supply_is_never_the_reference(
            self, conn, dataset, calendar):
        """Criterion 3, and the failure it stops: a resupply correcting a
        bad file would be measured against the file it is correcting, so
        the bigger the correction the louder the alarm."""
        a, _b, c, _d, _e = calendar
        earlier = _promote(conn, dataset, a)
        _promote(conn, dataset, c)
        got = drift_reference.reference_for(conn, dataset, c)
        assert (got.period, got.supply) == (a, earlier)

    def test_a_later_period_is_never_the_reference(self, conn, dataset, calendar):
        a, _b, c, _d, _e = calendar
        earlier = _promote(conn, dataset, a)
        _promote(conn, dataset, calendar[4])
        got = drift_reference.reference_for(conn, dataset, c)
        assert got.supply == earlier


class TestItSkipsAPeriodHoldingOnlyAView:
    """Criterion 6, and the subtlest of the wrong answers: a period
    holding a view holds no supply of its own, so measuring against it
    compares a supply with ITSELF one hop away - identical
    distributions, zero drift, a green check that asked nothing."""

    def test_it_skips_a_SUBSTITUTED_period(self, conn, dataset, calendar):
        a, _b, c, _d, e = calendar
        real = _promote(conn, dataset, a)
        substitution.substitute(
            conn, agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset,
            logical_table="carers", period=c, stands_on=a, supply=real,
            actor="Keith", reason="the supplier confirmed none is coming",
            effective_at=WHEN)
        got = drift_reference.reference_for(conn, dataset, e)
        assert got.period == a, "the substituted period holds a view, not a supply"

    def test_it_skips_an_INHERITED_period(self, conn, dataset, calendar,
                                           monkeypatch):
        a, _b, c, _d, e = calendar
        real = _promote(conn, dataset, a)
        # An inheritance recorded the way inherit_into() records one.
        entry = type("E", (), {"agency_id": AGENCY, "collection_id": COLLECTION,
                                "dataset_id": dataset})()
        inheritance._record(conn, entry, action=dl.INHERIT, supply=real, period=c,
                             stands_on=a, reason="not due this quarter",
                             effective_at=WHEN)
        got = drift_reference.reference_for(conn, dataset, e)
        assert got.period == a

    def test_it_skips_a_period_a_person_emptied(self, conn, dataset, calendar):
        """A rejection or a demotion leaves the period holding nothing,
        and nothing is not a reference either."""
        a, _b, c, _d, e = calendar
        first = _promote(conn, dataset, a)
        _promote(conn, dataset, c)
        rejection.demote(
            conn, agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset,
            supply=dl.promoted_into(conn, dataset, c), physical_tables=[],
            actor="Keith", reason="wrong file", effective_at=WHEN, from_slot=c)
        got = drift_reference.reference_for(conn, dataset, e)
        assert got.supply == first


class TestNoReferenceIsNotAPass:
    """Criterion 5, and it is an exception rather than a None on
    purpose: a caller that forgets to handle a None writes a GREEN
    result, where one that forgets to handle this writes nothing, and
    an absent result is visibly absent."""

    def test_it_raises_where_no_earlier_period_holds_one(self, conn, dataset,
                                                          calendar):
        _a, _b, _c, _d, e = calendar
        with pytest.raises(drift_reference.NoReference, match="not a check that passed"):
            drift_reference.reference_for(conn, dataset, e)

    def test_the_very_first_supply_has_no_reference(self, conn, dataset, calendar):
        a = calendar[0]
        _promote(conn, dataset, a)
        with pytest.raises(drift_reference.NoReference):
            drift_reference.reference_for(conn, dataset, a)

    def test_a_period_the_calendar_does_not_know_says_so(self, conn, dataset,
                                                          calendar):
        with pytest.raises(drift_reference.NoReference, match="not a period"):
            drift_reference.reference_for(conn, dataset, "not-a-period")


class TestWhichRunCheckedASupply:
    """The mapping that was written up as a fork needing a decision, and
    turned out to be recorded all along.

    A supply is `cp-carers@202608010100000000`; the table it staged into
    is `cp_carers__202608010100000000`. The same ARRIVAL KEY, recorded
    on one side by qa.filing and on the other by qa.tables_read. Nothing
    had to be added - the question had to be asked of the right column.
    """

    def _run_reading(self, conn, run_key, logical, physical, when):
        from qa_tools.common import qa_store
        conn.execute(
            f'INSERT INTO "{qa_store.SCHEMA}".run '
            "(run_key, agency_id, collection_id, run_timestamp, run_instant) "
            "VALUES (?, ?, ?, ?, ?)",
            [run_key, AGENCY, COLLECTION, when, when])
        conn.execute(
            f'INSERT INTO "{qa_store.SCHEMA}".tables_read '
            "(run_key, logical_table, physical_table) VALUES (?, ?, ?)",
            [run_key, logical, physical])

    def test_it_finds_the_run_by_the_arrival_key_in_the_table_name(self, conn):
        self._run_reading(conn, f"r_{uuid.uuid4().hex[:8]}", "cp_carers",
                           "cp_carers__209901010100000000",
                           "2099-01-01T09:00:00+08:00")
        got = drift_reference.run_for(conn, "cp-carers",
                                       "cp-carers@209901010100000000")
        assert got is not None

    def test_a_supply_nothing_ever_read_has_no_run(self, conn):
        assert drift_reference.run_for(
            conn, "cp-carers", "cp-carers@209912310100000000") is None

    def test_a_supply_id_of_the_wrong_shape_is_not_an_error(self, conn):
        """A caller with a malformed id gets None rather than a
        traceback: the reference is a comparison, and a comparison that
        cannot be made is a check with no reference."""
        assert drift_reference.run_for(conn, "cp-carers", "no-at-sign") is None
        assert drift_reference.run_for(conn, "cp-carers", "") is None

    def test_a_dataset_the_tree_does_not_know_has_no_run(self, conn):
        assert drift_reference.run_for(
            conn, "not-a-dataset", "not-a-dataset@209901010100000000") is None

    def test_the_EARLIEST_run_wins_where_several_read_it(self, conn):
        """A run reads a table it did not stage when it BORROWS one, and
        a borrow always happens after the staging - so the first run to
        read a physical table is the one that brought it."""
        arrival = "209902020100000000"
        physical = f"cp_carers__{arrival}"
        first, second = f"r_{uuid.uuid4().hex[:8]}", f"r_{uuid.uuid4().hex[:8]}"
        self._run_reading(conn, second, "cp_carers", physical,
                           "2099-02-05T09:00:00+08:00")
        self._run_reading(conn, first, "cp_carers", physical,
                           "2099-02-02T09:00:00+08:00")
        assert drift_reference.run_for(
            conn, "cp-carers", f"cp-carers@{arrival}") == first


class TestTheOrchestratorsEntryPoint:
    """reference_run_for_arrival() - REQ-QAC-108 criterion 4's second
    half, which is where the rule above actually reaches the pipeline.

    THE HALF THAT WAS MISSING UNTIL 2026-09-29 was not the rule but its
    CALLER: both orchestrators passed `manifest[0]["run_id"]` down to
    every run in the batch, so a correct reference_for() sat beside a
    batch measuring every supply against the beginning of history.
    """

    def test_an_arrival_nothing_was_filed_for_has_no_reference(
            self, supply_dsn, dataset):
        """None rather than an exception, and rather than a guess. A
        supply with no confident slot is filed nowhere (REQ-PIPE-059),
        so there is no period to walk back from - which the caller
        reports as a check with no reference."""
        assert drift_reference.reference_run_for_arrival(
            dataset, "2026-09-29T09:00:00+08:00") is None

    def test_it_asks_filing_for_the_period_rather_than_deriving_one(
            self, monkeypatch, supply_dsn, dataset):
        """The arrival instant is not the period. Deriving one here
        would be a second naming scheme beside filing's own - the thing
        filing._supply_id_for()'s docstring exists to prevent - and it
        would get the held supply's `#1` suffix wrong.
        """
        from qa_tools.common import filing

        asked = {}

        def _period_of(dataset_id, received_at):
            asked.update(dataset_id=dataset_id, received_at=received_at)
            return None

        monkeypatch.setattr(filing, "period_of", _period_of)
        drift_reference.reference_run_for_arrival(dataset, "2026-09-29T09:00:00+08:00")
        assert asked == {"dataset_id": dataset,
                          "received_at": "2026-09-29T09:00:00+08:00"}

    def test_a_first_period_has_no_reference_rather_than_an_error(
            self, monkeypatch, supply_dsn, dataset, calendar):
        """NoReference is reference_for()'s contract and the wrong
        thing to hand an orchestrator: a dataset's first supply is an
        ordinary event, for ever, and a QA run should not abort on one.
        """
        from qa_tools.common import filing

        a, *_ = calendar
        monkeypatch.setattr(filing, "period_of", lambda ds, at: a)
        assert drift_reference.reference_run_for_arrival(
            dataset, "2026-09-29T09:00:00+08:00") is None


class TestAnEntryAboutAnotherSupplyDoesNotHideTheReference:
    """post-build-review #85 - the third copy of #84's rule. The walk
    accepted a period only if the LAST entry naming it was a promotion,
    so a reject of a different supply filed there, or a withheld note,
    made it skip a period that still holds a promoted supply - and under
    REQ-QAC-108's amendment that skip is a false red ("no accepted
    earlier supply"). Now read from qa.slot_holds (REQ-PIPE-130)."""

    def test_rejecting_an_unpromoted_resupply_of_the_reference_period(
            self, conn, dataset, calendar):
        a, _b, c, _d, _e = calendar
        real = _promote(conn, dataset, a)
        rejection.reject(
            conn, agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset,
            supply=f"{dataset}@resupply", physical_tables=[], actor="Keith",
            reason="a bad file", effective_at="2026-09-29T10:00:00+08:00",
            from_slot=a)
        got = drift_reference.reference_for(conn, dataset, c)
        assert (got.period, got.supply) == (a, real)

    def test_a_withheld_note_on_the_reference_period(self, conn, dataset, calendar):
        a, _b, c, _d, _e = calendar
        real = _promote(conn, dataset, a)
        with dl.apply_decision(conn, dl.Decision(
                agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset,
                action=dl.PROMOTION_WITHHELD, supply=f"{dataset}@offcycle",
                actor="promotion rule", actor_kind=dl.RULE,
                effective_at="2026-09-29T10:00:00+08:00", to_slot=a,
                reason="arrived off-cycle")):
            pass
        got = drift_reference.reference_for(conn, dataset, c)
        assert (got.period, got.supply) == (a, real)
