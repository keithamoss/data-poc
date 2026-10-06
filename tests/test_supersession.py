"""One waiting version per table per period (REQ-PIPE-118).

Against a real database. Each test mints its own period, so nothing one
test files or decides can answer another's question on the same worker.
"""
from __future__ import annotations

import random
import uuid

import pytest

from qa_tools.common import (decision_log as dl, period_schema, promotion, qa_store,
                             supersession, supply_db)

DS, TABLE = "cp-carers", "cp_carers"
WHEN = "2026-10-05T09:00:00+08:00"
REAL_PERSON = "fpycnkgvmt@privaterelay.appleid.com"


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-supersession") as c:
        qa_store.ensure_schema(c)
        yield c


@pytest.fixture
def period():
    return f"2099-S{uuid.uuid4().hex[:6]}"


def _key():
    return "".join(random.choice("0123456789") for _ in range(18))


def _filed(conn, period, received, *, staged=True):
    """A supply of cp-carers filed to `period`, received at `received`,
    with its table in staging."""
    key = _key()
    supply, physical, delivery = f"{DS}@{key}", f"{TABLE}__{key}", f"pytest-sup-{key}"
    conn.execute("INSERT INTO qa.delivery (name, received_at, received_instant) "
                 "VALUES (?, ?, ?)", [delivery, received, received])
    conn.execute("INSERT INTO qa.delivery_file (delivery, filename, dataset_id, received_at, "
                 "received_instant, received_from, receipt_sequence) "
                 "VALUES (?, 'cp_carers.csv', ?, ?, ?, 'our-clock', 1)",
                 [delivery, DS, received, received])
    conn.execute("INSERT INTO qa.filing (dataset_id, supply_id, slot, branch, delivery) "
                 "VALUES (?, ?, ?, 'pytest', ?)", [DS, supply, period, delivery])
    if staged:
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')
        conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" (id integer)')
    return supply, physical


def _supersede(conn, period, newer):
    with conn.raw.transaction():
        return supersession.supersede_earlier(
            conn, agency_id="child-protection-family-support", collection_id="child-protection",
            dataset_id=DS, period=period, newer=newer, effective_at=WHEN)


def _schema_of(conn, physical):
    rows = conn.execute("SELECT table_schema FROM information_schema.tables "
                        "WHERE table_name = ?", [physical]).fetchall()
    return [r[0] for r in rows]


class TestANewerFileSupersedesEarlierWaitingVersions:
    """Criteria 1, 4, 9, 10 and 11."""

    def test_the_earlier_one_moves_to_its_periods_superseded_schema(self, conn, period):
        old, old_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        new, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        assert _supersede(conn, period, new) == [old]
        assert _schema_of(conn, old_table) == [supersession.superseded_schema(period)]
        assert supersession.superseded_schema(period) == period_schema.period_schema(period) + "_superseded"

    def test_it_is_recorded_by_the_rule_naming_both_and_is_not_a_rejection(self, conn, period):
        old, _ = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        new, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        _supersede(conn, period, new)
        rows = conn.execute(f"SELECT action, actor_kind, superseded_by, from_slot FROM {dl.TABLE} "
                            "WHERE supply = ?", [old]).fetchall()
        assert rows == [(dl.SUPERSEDE, dl.RULE, new, period)]
        assert supersession.superseded_by(conn, DS, old) == new
        assert supply_db.REJECTED_SCHEMA not in _schema_of(conn, f"{TABLE}__{old.split('@')[1]}")


class TestWhatIsNotSuperseded:
    """Criteria 2, 3 and 12."""

    def test_a_version_received_later_is_not_superseded_by_an_earlier_one(self, conn, period):
        early, _ = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        late, late_table = _filed(conn, period, "2026-05-03T01:00:00+00:00")
        assert _supersede(conn, period, early) == []
        assert _schema_of(conn, late_table) == [supply_db.STAGING_SCHEMA]

    def test_a_rejected_one_is_left_alone(self, conn, period):
        old, _ = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        with dl.apply_decision(conn, dl.Decision(
                agency_id="a", collection_id="c", dataset_id=DS, action=dl.REJECT,
                supply=old, actor=REAL_PERSON, actor_kind=dl.PERSON, effective_at=WHEN,
                from_slot=period, reason="bad")):
            pass
        new, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        assert _supersede(conn, period, new) == []

    def test_a_promoted_one_is_left_alone(self, conn, period):
        old, old_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        promotion.promote(conn, agency_id="child-protection-family-support",
                          collection_id="child-protection", dataset_id=DS, supply=old,
                          period=period, physical_tables=[old_table], actor="promotion rule",
                          actor_kind=dl.RULE, effective_at=WHEN, reason="green")
        new, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        assert _supersede(conn, period, new) == []

    def test_a_file_refused_at_load_supersedes_nothing(self, conn, period):
        """REAL DEFECT (post-build-review #124 D2): an unloadable file
        superseded a real waiting supply, leaving the period with nothing
        checkable. Keith: a refused file supersedes nothing."""
        from qa_tools.common import load_log

        old, old_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        new, new_table = _filed(conn, period, "2026-05-02T01:00:00+00:00", staged=False)
        load_log.record("pytest-refused", DS, new_table, load_log.FAILED,
                        "2026-05-02T01:00:00+00:00", reason="ragged row", conn=conn)
        assert _supersede(conn, period, new) == []
        assert _schema_of(conn, old_table) == [supply_db.STAGING_SCHEMA]

    def test_one_a_person_demoted_is_superseded_like_any_other(self, conn, period):
        """Decision 13: a supply a person returned is unaccepted too."""
        from qa_tools.common import rejection

        old, old_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        promotion.promote(conn, agency_id="child-protection-family-support",
                          collection_id="child-protection", dataset_id=DS, supply=old,
                          period=period, physical_tables=[old_table], actor="promotion rule",
                          actor_kind=dl.RULE, effective_at=WHEN, reason="green")
        rejection.demote(conn, agency_id="child-protection-family-support",
                         collection_id="child-protection", dataset_id=DS, supply=old,
                         from_slot=period, physical_tables=[old_table], actor=REAL_PERSON,
                         reason="not yet", effective_at=WHEN)
        new, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        assert _supersede(conn, period, new) == [old]


class TestTheSupersededSchema:
    """Criteria 5 to 8."""

    def test_created_on_demand_and_dropped_when_empty(self, conn, period):
        target = supersession.superseded_schema(period)
        assert not supersession.drop_if_empty(conn, period)
        old, old_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        new, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        _supersede(conn, period, new)
        assert not supersession.drop_if_empty(conn, period), "not while a table is in it"
        conn.execute(f'DROP TABLE "{target}"."{old_table}"')
        assert supersession.drop_if_empty(conn, period)
        assert not conn.execute("SELECT 1 FROM information_schema.schemata "
                                "WHERE schema_name = ?", [target]).fetchall()

    def test_it_is_never_read_back_as_a_period(self, conn, period):
        target = supersession.superseded_schema(period)
        assert period_schema.period_of(target) is None
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{target}"')
        try:
            assert all(not p.endswith("_superseded") for p in period_schema.period_schemas(conn))
        finally:
            conn.execute(f'DROP SCHEMA IF EXISTS "{target}"')

    def test_a_period_name_that_would_collide_is_refused(self):
        assert "period_2026_q2_superseded" in period_schema.collisions_in(
            ["2026-Q2", "2026-Q2 superseded"])


class TestNoRuleBringsItBack:
    """Criterion 14: the promotion gate refuses a superseded supply."""

    def test_the_gate_refuses_naming_the_newer_one(self, conn, period):
        old, old_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        new, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        _supersede(conn, period, new)
        got = promotion.after_run(
            conn, agency_id="child-protection-family-support", collection_id="child-protection",
            supplies=[{"dataset_id": DS, "supply": old, "period": period,
                       "physical_tables": [old_table]}],
            results=[], reads={}, actor="promotion rule", actor_kind=dl.RULE, effective_at=WHEN)
        assert got.promoted == () and new in got.refused[DS]

    def test_a_superseded_supply_is_not_waiting(self, conn, period):
        from qa_tools.common import slot_state

        old, _ = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        new, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        _supersede(conn, period, new)
        assert slot_state._rejected(conn, DS, old)
        assert not slot_state._rejected(conn, DS, new)


def _request(operation, supply, period, reason="looked at both"):
    from qa_tools.common import filing_decisions as fd
    from qa_tools.common import people

    return fd.Request(operation=operation, dataset_id=DS,
                      actor=people.person_by_email(REAL_PERSON), reason=reason,
                      period=period, supply=supply)


class TestAPersonSupersedesAndBringsBack:
    """REQ-PIPE-120 criteria 1 to 8."""

    def test_a_person_supersedes_a_waiting_supply(self, conn, period):
        from qa_tools.common import filing_decisions as fd

        supply, table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        fd.apply(_request(fd.SUPERSEDE, supply, period), effective_at=WHEN, conn=conn)
        assert _schema_of(conn, table) == [supersession.superseded_schema(period)]
        rows = conn.execute(f"SELECT actor_kind FROM {dl.TABLE} WHERE supply = ? "
                            "AND action = ?", [supply, dl.SUPERSEDE]).fetchall()
        assert rows == [(dl.PERSON,)]

    def test_un_supersede_returns_it_to_staging_and_the_gate_may_promote(self, conn, period):
        from qa_tools.common import filing_decisions as fd
        from qa_tools.common import rejection

        old, old_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        new, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        _supersede(conn, period, new)
        fd.apply(_request(fd.REJECT, new, period), effective_at=WHEN, conn=conn)
        fd.apply(_request(fd.UN_SUPERSEDE, old, period), effective_at=WHEN, conn=conn)
        assert _schema_of(conn, old_table) == [supply_db.STAGING_SCHEMA]
        assert not supersession.is_superseded(conn, DS, old)
        assert not rejection.decided_by_a_person(conn, DS, old), \
            "criterion 4: un-supersede does not bar the gate"
        assert not conn.execute("SELECT 1 FROM information_schema.schemata WHERE schema_name = ?",
                                [supersession.superseded_schema(period)]).fetchall(), \
            "and the emptied superseded schema is dropped"

    def test_un_supersede_beside_a_waiting_version_is_refused_naming_it(self, conn, period):
        from qa_tools.common import filing_decisions as fd

        old, _ = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        new, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        _supersede(conn, period, new)
        with pytest.raises(dl.DecisionRefused, match=f"{new} is waiting.*supersede"):
            fd.apply(_request(fd.UN_SUPERSEDE, old, period), effective_at=WHEN, conn=conn)

    def test_promoting_a_superseded_supply_is_refused_naming_un_supersede(self, conn, period):
        from qa_tools.common import filing_decisions as fd

        old, _ = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        new, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        _supersede(conn, period, new)
        with pytest.raises(dl.DecisionRefused, match=f"(?s)superseded by {new}.*un-supersede"):
            fd.apply(_request(fd.PROMOTE, old, period), effective_at=WHEN, conn=conn)

    def test_un_supersede_names_its_version(self, conn, period):
        with pytest.raises(dl.DecisionRefused, match="names which superseded version"):
            supersession.un_supersede(
                conn, agency_id="a", collection_id="c", dataset_id=DS, supply="",
                period=period, actor=REAL_PERSON, reason="r", effective_at=WHEN)

    def test_the_listing_finds_them(self, conn, period):
        old, _ = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        new, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        _supersede(conn, period, new)
        assert [(v["supply"], v["superseded_by"]) for v in
                supersession.superseded_in(conn, DS, period)] == [(old, new)]


def test_mothman_supply_superseded_lists_them(supply_dsn, monkeypatch):
    """REQ-PIPE-120 criterion 7, through the real command."""

    from click.testing import CliRunner as ClickRunner

    from cli.supply import supply_group

    with supply_db.connect(label="test-supersession") as conn:
        qa_store.ensure_schema(conn)
        period = f"2099-S{uuid.uuid4().hex[:6]}"
        old, _ = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        new, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        _supersede(conn, period, new)
    result = ClickRunner().invoke(supply_group, ["superseded", "--collection", "child-protection",
                                                 "--dataset", DS, "--period", period])
    assert result.exit_code == 0, result.output
    assert f"{old}  superseded by {new}" in result.output
