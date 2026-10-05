"""A period schema holds exactly one version of each table, always
(REQ-PIPE-128). Against a real database; each test mints its own periods."""
from __future__ import annotations

import pytest

import test_supersession as _base
from qa_tools.common import (decision_log as dl, period_schema, promotion, substitution,
                             supersession, supply_db)
from test_supersession import DS, REAL_PERSON, TABLE, WHEN, _filed, _schema_of

conn = _base.conn
period = _base.period

AG, COL = "child-protection-family-support", "child-protection"


@pytest.fixture
def later():
    import uuid
    return f"2099-T{uuid.uuid4().hex[:6]}"


def _promote(conn, supply, table, period, *, kind=dl.RULE, actor="promotion rule", at=WHEN):
    return promotion.promote(conn, agency_id=AG, collection_id=COL, dataset_id=DS,
                             supply=supply, period=period, physical_tables=[table],
                             actor=actor if kind == dl.RULE else REAL_PERSON,
                             actor_kind=kind, effective_at=at, reason="because")


def _request(operation, period, supply=None, acknowledged=None, **kw):
    from qa_tools.common import filing_decisions as fd, people
    return fd.Request(operation=operation, dataset_id=DS,
                      actor=people.person_by_email(REAL_PERSON), reason="looked at both",
                      period=period, supply=supply, acknowledged=acknowledged, **kw)


class TestAPersonsPromotionSupersedesWhatWasThere:
    """Criteria 1 and 2: the previously promoted supply moves to the
    superseded state in the same decision and transaction."""

    def test_one_version_and_the_old_one_superseded(self, conn, period):
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period)
        b, b_table = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        _promote(conn, b, b_table, period, kind=dl.PERSON)
        assert _schema_of(conn, b_table) == [period_schema.period_schema(period)]
        assert _schema_of(conn, a_table) == [supersession.superseded_schema(period)]
        assert supersession.is_superseded(conn, DS, a)
        assert supersession.superseded_by(conn, DS, a) == b
        assert dl.promoted_into(conn, DS, period) == b


class TestNotWhileALaterPeriodStandsOnIt:
    """Criterion 3: refused, naming every blocking period and the command
    that unblocks it (NFR 4)."""

    def test_refused_naming_the_period_and_the_command(self, conn, period, later):
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period)
        substitution.substitute(conn, agency_id=AG, collection_id=COL, dataset_id=DS,
                                logical_table=TABLE, period=later, stands_on=period,
                                supply=a, actor=REAL_PERSON, reason="late", effective_at=WHEN)
        b, b_table = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        with pytest.raises(dl.DecisionRefused) as caught:
            _promote(conn, b, b_table, period, kind=dl.PERSON)
        assert later in str(caught.value)
        assert "mothman supply decide --operation de-substitute" in str(caught.value)
        assert _schema_of(conn, a_table) == [period_schema.period_schema(period)]
        assert _schema_of(conn, b_table) == [supply_db.STAGING_SCHEMA]


class TestIntoASubstitutedSlot:
    """Criterion 4: told the substitution goes, then a de-substitute and the
    promotion in one transaction."""

    def test_two_entries_one_transaction(self, conn, period, later):
        from qa_tools.common import filing_decisions as fd

        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period)
        substitution.substitute(conn, agency_id=AG, collection_id=COL, dataset_id=DS,
                                logical_table=TABLE, period=later, stands_on=period,
                                supply=a, actor=REAL_PERSON, reason="late", effective_at=WHEN)
        b, b_table = _filed(conn, later, "2026-08-02T01:00:00+00:00")
        found = fd.consequences(conn, _request(fd.PROMOTE, later, b))
        assert any("substitution" in line for line in found.lines)
        fd.apply(_request(fd.PROMOTE, later, b, acknowledged=found.key),
                 effective_at=WHEN, conn=conn)
        actions = [d["action"] for d in dl.decisions_for(conn, DS)
                   if later in (d.get("to_slot"), d.get("from_slot"))][-2:]
        assert actions == [dl.DE_SUBSTITUTE, dl.PROMOTE]
        assert dl.promoted_into(conn, DS, later) == b


class TestIntoAnInheritedSlot:
    """Criterion 5."""

    def test_refused_naming_un_inherit(self, conn, period):
        b, b_table = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        with dl.apply_decision(conn, dl.Decision(
                agency_id=AG, collection_id=COL, dataset_id=DS, action=dl.INHERIT,
                supply="cp-carers@older", actor="inheritance rule", actor_kind=dl.RULE,
                effective_at=WHEN, to_slot=period, stands_on="2098-Q1")):
            pass
        with pytest.raises(dl.DecisionRefused, match="un-inherit"):
            _promote(conn, b, b_table, period, kind=dl.PERSON)


class TestTheWarningPanel:
    """Criteria 6, 7 and 9."""

    def test_no_consequences_no_panel(self, conn, period):
        from qa_tools.common import filing_decisions as fd

        b, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        assert fd.consequences(conn, _request(fd.PROMOTE, period, b)).lines == ()

    def test_a_displacing_promotion_says_how_it_is_undone(self, conn, period):
        from qa_tools.common import filing_decisions as fd

        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period)
        b, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        lines = fd.consequences(conn, _request(fd.PROMOTE, period, b)).lines
        assert any(a in line and "superseded" in line and "un-supersede" in line
                   for line in lines)

    def test_unacknowledged_is_refused_and_a_changed_warning_is_refused(self, conn, period):
        from qa_tools.common import filing_decisions as fd

        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period)
        b, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        with pytest.raises(fd.ConsequencesNotAcknowledged) as caught:
            fd.apply(_request(fd.PROMOTE, period, b), effective_at=WHEN, conn=conn)
        assert caught.value.key and caught.value.lines
        with pytest.raises(fd.ConsequencesNotAcknowledged, match="changed"):
            fd.apply(_request(fd.PROMOTE, period, b, acknowledged="stale-key"),
                     effective_at=WHEN, conn=conn)
        fd.apply(_request(fd.PROMOTE, period, b, acknowledged=caught.value.key),
                 effective_at=WHEN, conn=conn)
        assert dl.promoted_into(conn, DS, period) == b


class TestTwoVersionsFailLoudly:
    """Criterion 12."""

    def test_a_period_holding_two_versions_is_refused(self, conn, period):
        schema = period_schema.period_schema(period)
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        for key in ("000000000000000001", "000000000000000002"):
            conn.execute(f'CREATE TABLE "{schema}"."{TABLE}__{key}" (id integer)')
        with pytest.raises(period_schema.MoreThanOneVersion, match=TABLE):
            period_schema.the_one_in(conn, period, TABLE)


class TestBothRoutesConfirmOnce:
    """Criteria 6 and 9 on the terminal and on GitHub."""

    def _displacing(self, conn, period):
        # IN THE PAST: the routes decide as at NOW, and a promotion dated
        # after that would still hold the slot by effective time.
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period, at="2026-05-02T01:00:00+00:00")
        b, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        return a, b

    def test_the_flag_form_needs_the_key_with_yes(self, conn, period, monkeypatch):
        from click.testing import CliRunner

        from cli import filing_tui, supply
        from qa_tools.common import filing_decisions as fd, people

        a, b = self._displacing(conn, period)
        monkeypatch.setattr(filing_tui, "actor_at_the_keyboard",
                            lambda: people.person_by_email(REAL_PERSON))
        monkeypatch.setattr(fd, "reconcile_after", lambda *a, **k: None)
        argv = ["decide", "--operation", "promote", "--dataset", DS, "--period", period,
                "--supply", b, "--reason", "better", "--yes"]
        first = CliRunner().invoke(supply.supply_group, argv)
        assert first.exit_code != 0
        key = fd.consequences(conn, _request(fd.PROMOTE, period, b)).key
        assert key in first.output
        second = CliRunner().invoke(supply.supply_group, [*argv, "--acknowledge", key])
        assert second.exit_code == 0, second.output
        assert dl.promoted_into(conn, DS, period) == b

    def test_github_takes_a_second_comment(self, conn, period, monkeypatch):
        from qa_tools.common import filing_decisions as fd, filing_from_github as gh, people

        a, b = self._displacing(conn, period)
        login = "keith-on-github"
        monkeypatch.setattr(people, "person_by_github",
                            lambda who: people.person_by_email(REAL_PERSON))
        monkeypatch.setattr(fd, "reconcile_after", lambda *a, **k: None)
        posted = []

        class Service:
            def comment(self, ticket, body):
                posted.append(body)

        slot = f"{DS}/{period}"
        first = gh.handle(gh.Comment(body=f"/promote supply: {b}\nbetter file", author=login,
                                     slot_key=slot),
                          collection_id=COL, effective_at=WHEN, service=Service(), ticket=1)
        assert first is None and posted
        key = fd.consequences(conn, _request(fd.PROMOTE, period, b)).key
        assert f"acknowledge: {key}" in posted[-1]
        second = gh.handle(gh.Comment(body=f"/promote supply: {b} acknowledge: {key}\nbetter",
                                      author=login, slot_key=slot),
                           collection_id=COL, effective_at=WHEN, service=Service(), ticket=1)
        assert second is not None and second.changed
