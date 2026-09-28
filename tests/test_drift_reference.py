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
    physical = f"tbl__{uuid.uuid4().hex[:10]}"
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')
    conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" (id integer)')
    promotion.promote(
        conn, agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset_id,
        supply=physical, period=period, physical_tables=[physical],
        actor="tester", actor_kind=dl.PERSON, effective_at=WHEN)
    return physical


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
