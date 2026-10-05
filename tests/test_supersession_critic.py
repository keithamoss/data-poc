"""Defects the delivery critic found in REQ-PIPE-118 and REQ-PIPE-120
(post-build-review #109), each reproduced here before it was fixed.
"""
from __future__ import annotations

import pytest

from qa_tools.common import decision_log as dl, promotion, slot_state, supersession, supply_db
import test_supersession as _base
from test_supersession import DS, REAL_PERSON, WHEN, _filed, _schema_of, _supersede

# The base module's fixtures, re-exported so pytest finds them here.
conn = _base.conn
period = _base.period


def _apply(conn, operation, supply, period, reason="looked at both"):
    from qa_tools.common import filing_decisions as fd
    from qa_tools.common import people

    return fd.apply(fd.Request(operation=operation, dataset_id=DS,
                               actor=people.person_by_email(REAL_PERSON), reason=reason,
                               period=period, supply=supply), effective_at=WHEN, conn=conn)


class TestAPersonsSupersessionIsASupersession:
    """F1, CRITICAL: a person's supersession recorded no `superseded_by`, so
    is_superseded() read the column, found NULL and said no - the supply's
    tables were set aside and nothing knew."""

    def test_it_is_seen_listed_and_can_come_back(self, conn, period):
        from qa_tools.common import filing_decisions as fd

        supply, table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _apply(conn, fd.SUPERSEDE, supply, period)
        assert supersession.is_superseded(conn, DS, supply)
        assert [v["supply"] for v in supersession.superseded_in(conn, DS, period)] == [supply]
        assert supply not in supersession.waiting_in(conn, DS, period)
        with pytest.raises(dl.DecisionRefused, match="superseded by a person"):
            _apply(conn, fd.PROMOTE, supply, period)
        _apply(conn, fd.UN_SUPERSEDE, supply, period)
        assert _schema_of(conn, table) == [supply_db.STAGING_SCHEMA]


class TestTheSchemaChangeReachesAnExistingDatabase:
    """F2: the relaxed constraint shipped without a schema-version bump, so
    a database already at 22 kept the old one and a person's supersede
    crashed with a CheckViolation."""

    def test_the_version_moved_past_22(self):
        from qa_tools.common import qa_store

        assert qa_store.SCHEMA_VERSION >= 23


class TestTheSlotShowsTheSupplyThatIsWaiting:
    """F3 and F4: slot_state read the LATEST filing whatever had happened to
    it, so after an un-supersede the slot showed the rejected newer supply
    and hid the one now waiting; and a superseded latest filing still read
    'awaiting a decision'."""

    def test_after_un_supersede_the_waiting_supply_is_the_one_shown(self, conn, period):
        from qa_tools.common import filing, filing_decisions as fd

        old, _ = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        new, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        _supersede(conn, period, new)
        _apply(conn, fd.REJECT, new, period)
        _apply(conn, fd.UN_SUPERSEDE, old, period)
        filings = slot_state.filings_by_period(conn, DS, filing.filings_of(DS))
        assert filings[period]["supply_id"] == old


class TestADisplacedPromotedSupplyIsNotSuperseded:
    """F6: a supply once promoted into the period and since displaced by a
    person's promotion of another still has its tables in the period
    schema - the rule recorded it superseded and moved nothing."""

    def test_it_is_left_alone(self, conn, period):
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        promotion.promote(conn, agency_id="child-protection-family-support",
                          collection_id="child-protection", dataset_id=DS, supply=a,
                          period=period, physical_tables=[a_table], actor="promotion rule",
                          actor_kind=dl.RULE, effective_at=WHEN, reason="green")
        b, b_table = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        promotion.promote(conn, agency_id="child-protection-family-support",
                          collection_id="child-protection", dataset_id=DS, supply=b,
                          period=period, physical_tables=[b_table], actor=REAL_PERSON,
                          actor_kind=dl.PERSON, effective_at=WHEN, reason="better")
        c, _ = _filed(conn, period, "2026-05-03T01:00:00+00:00")
        assert a not in _supersede(conn, period, c)


class TestARejectedSupplyStaysRejected:
    """F7: a superseded supply could be rejected and then brought back into
    staging still rejected, where the overlay would read it."""

    def test_un_supersede_refuses_a_rejected_supply(self, conn, period):
        from qa_tools.common import filing_decisions as fd

        old, _ = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        new, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        _supersede(conn, period, new)
        with pytest.raises(dl.DecisionRefused, match="superseded"):
            _apply(conn, fd.REJECT, old, period)


class TestOnlyASupplyFiledToThePeriod:
    """F10: supersede accepted a supply that does not exist, or a real one
    named against the wrong period - moving its tables into that period's
    superseded schema."""

    def test_a_supply_not_filed_to_the_period_is_refused(self, conn, period):
        from qa_tools.common import filing_decisions as fd

        with pytest.raises(dl.DecisionRefused, match="not filed to"):
            _apply(conn, fd.SUPERSEDE, f"{DS}@000000000000000001", period)


class TestARepeatChangesNothing:
    """F14: a repeated supersede was a refusal where every other filing
    decision reports a repeat as done already (REQ-GHUB-082 c26)."""

    def test_a_second_supersede_is_already_so(self, conn, period):
        from qa_tools.common import filing_decisions as fd

        supply, _ = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _apply(conn, fd.SUPERSEDE, supply, period)
        assert not _apply(conn, fd.SUPERSEDE, supply, period).changed


class TestASetAsideSupplyIsNotAwaiting:
    """F5: a superseded supply's recorded arrival still said its wait was
    running, so it read as somebody's to decide on."""

    def test_a_superseded_supply_is_not_awaiting(self, conn, period):
        from qa_tools.common import filing

        old, _ = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        new, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        _supersede(conn, period, new)
        assert not filing.recorded_arrival(DS, old).awaiting
        assert filing.recorded_arrival(DS, old).waited is None
        assert filing.recorded_arrival(DS, new).awaiting


class TestAResetTakesThePeriodSchemas:
    """F12: schemas_to_drop() added period NAMES ('2099-Q1'), not schema
    names, so a reset left every period schema behind - and with REQ-PIPE-118
    every period's superseded schema too."""

    def test_both_are_dropped(self, private_supply_dsn):
        from qa_tools.common import period_schema, synthetic_reset

        with supply_db.connect(label="test-reset-periods") as c:
            plain = period_schema.period_schema("2099-Q1")
            aside = supersession.superseded_schema("2099-Q1")
            for name in (plain, aside):
                c.execute(f'CREATE SCHEMA IF NOT EXISTS "{name}"')
            dropping = synthetic_reset.schemas_to_drop(c)
        assert plain in dropping and aside in dropping


class TestADemoteBesideANewerWaitingVersionIsRefused:
    """REQ-PIPE-118 criterion 17 (Keith, 2026-10-05; #109 F8): demoting a
    promoted supply into a period where a newer version is waiting would
    leave two waiting versions of one table, so it is refused."""

    def test_refused_naming_the_waiting_version(self, conn, period):
        from qa_tools.common import filing_decisions as fd

        old, old_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        promotion.promote(conn, agency_id="child-protection-family-support",
                          collection_id="child-protection", dataset_id=DS, supply=old,
                          period=period, physical_tables=[old_table], actor="promotion rule",
                          actor_kind=dl.RULE, effective_at=WHEN, reason="green")
        new, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        with pytest.raises(dl.DecisionRefused, match=new):
            _apply(conn, fd.DEMOTE, old, period)
        assert _schema_of(conn, old_table) != [supply_db.STAGING_SCHEMA]

    def test_allowed_once_the_newer_one_is_dealt_with(self, conn, period):
        from qa_tools.common import filing_decisions as fd

        old, old_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        promotion.promote(conn, agency_id="child-protection-family-support",
                          collection_id="child-protection", dataset_id=DS, supply=old,
                          period=period, physical_tables=[old_table], actor="promotion rule",
                          actor_kind=dl.RULE, effective_at=WHEN, reason="green")
        new, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        _apply(conn, fd.SUPERSEDE, new, period)
        _apply(conn, fd.DEMOTE, old, period)
        assert _schema_of(conn, old_table) == [supply_db.STAGING_SCHEMA]
