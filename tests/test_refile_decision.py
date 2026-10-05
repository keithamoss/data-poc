"""Re-filing a supply returns it to staging under a new filing for its new
period, where it is checked and the gate decides (REQ-PIPE-141), confirmed
against a warning naming every consequence (REQ-GHUB-142). Against a real
database; each test mints its own periods."""
from __future__ import annotations

import uuid

import pytest

import test_supersession as _base
from qa_tools.common import (decision_log as dl, filing, promotion,
                             rejection, substitution, supersession, supply_db)
from test_supersession import DS, REAL_PERSON, TABLE, WHEN, _filed, _schema_of

conn = _base.conn
period = _base.period

AG, COL = "child-protection-family-support", "child-protection"


@pytest.fixture
def target():
    return f"2099-R{uuid.uuid4().hex[:6]}"


def _promote(conn, supply, table, period, *, kind=dl.RULE, at=WHEN):
    promotion.promote(conn, agency_id=AG, collection_id=COL, dataset_id=DS, supply=supply,
                      period=period, physical_tables=[table],
                      actor="promotion rule" if kind == dl.RULE else REAL_PERSON,
                      actor_kind=kind, effective_at=at, reason="because")


def _request(operation, period, supply=None, acknowledged=None, **kw):
    from qa_tools.common import filing_decisions as fd, people
    return fd.Request(operation=operation, dataset_id=DS,
                      actor=people.person_by_email(REAL_PERSON), reason="supplier said Q3",
                      period=period, supply=supply, acknowledged=acknowledged, **kw)


def _refile(conn, supply, period, to_period):
    from qa_tools.common import filing_decisions as fd

    request = _request(fd.REFILE, period, supply, to_period=to_period, confirmed=True)
    key = fd.consequences(conn, request).key
    return fd.apply(_request(fd.REFILE, period, supply, to_period=to_period, confirmed=True,
                             acknowledged=key or None), effective_at=WHEN, conn=conn)


def _current_slot(conn, supply):
    return conn.execute(f"SELECT slot FROM {filing.CURRENT} WHERE dataset_id = ? AND "
                        "supply_id = ?", [DS, supply]).fetchall()[0][0]


class TestANewFilingTheOldKept:
    """Criteria 1, 2 and 4."""

    def test_a_waiting_supply_is_filed_anew_and_stays_in_staging(self, conn, period, target):
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        got = _refile(conn, a, period, target)
        assert got.changed and got.owed
        assert _current_slot(conn, a) == target
        slots = [r[0] for r in conn.execute(
            f"SELECT slot FROM {filing.TABLE} WHERE dataset_id = ? AND supply_id = ? "
            "ORDER BY id", [DS, a]).fetchall()]
        assert slots == [period, target]
        assert _schema_of(conn, a_table) == [supply_db.STAGING_SCHEMA]

    def test_one_entry_naming_both_periods_and_a_recheck_owed(self, conn, period, target):
        from qa_tools.common import recheck

        a, _ = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        got = _refile(conn, a, period, target)
        (entry,) = [d for d in dl.decisions_for(conn, DS)
                    if d["action"] == dl.REFILE and d["supply"] == a]
        assert (entry["from_slot"], entry["to_slot"]) == (period, target)
        (owed,) = [o for o in recheck.owed(conn, DS) if o.id == got.owed]
        assert owed.supply_id == a and owed.caused_by_decision == entry["id"]


class TestAPromotedSupplyLeavesItsPeriod:
    """Criteria 3, 5 and 8."""

    def test_it_leaves_with_its_stamped_name_and_the_slot_unfilled(self, conn, period, target):
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period)
        _refile(conn, a, period, target)
        assert dl.promoted_into(conn, DS, period) is None
        assert _schema_of(conn, a_table) == [supply_db.STAGING_SCHEMA]
        assert dl.promoted_into(conn, DS, target) is None, "a re-file fills nothing"

    def test_refused_while_a_later_period_stands_on_it(self, conn, period, target):
        from qa_tools.common import filing_decisions as fd

        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period)
        later = f"2099-L{uuid.uuid4().hex[:6]}"
        substitution.substitute(conn, agency_id=AG, collection_id=COL, dataset_id=DS,
                                logical_table=TABLE, period=later, stands_on=period,
                                supply=a, actor=REAL_PERSON, reason="late", effective_at=WHEN)
        with pytest.raises(dl.DecisionRefused, match=later):
            fd.consequences(conn, _request(fd.REFILE, period, a, to_period=target))

    def test_a_refile_does_not_bar_the_rule(self, conn, period, target):
        a, _ = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _refile(conn, a, period, target)
        assert not rejection.decided_by_a_person(conn, DS, a)


class TestTheTargetPeriod:
    """Criteria 6, 9 and 16."""

    def test_every_waiting_version_there_is_superseded_whatever_its_receipt(
            self, conn, period, target):
        a, _ = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        newer, newer_table = _filed(conn, target, "2026-06-01T01:00:00+00:00")
        _refile(conn, a, period, target)
        assert supersession.is_superseded(conn, DS, newer)
        assert supersession.superseded_by(conn, DS, newer) == a
        assert _schema_of(conn, newer_table) == [supersession.superseded_schema(target)]
        rule_entries = [d for d in dl.decisions_for(conn, DS)
                        if d["action"] == dl.SUPERSEDE and d["supply"] == newer]
        assert rule_entries and rule_entries[-1]["actor_kind"] == dl.RULE

    def test_a_promoted_version_there_stays_promoted(self, conn, period, target):
        a, _ = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        held, held_table = _filed(conn, target, "2026-06-01T01:00:00+00:00")
        _promote(conn, held, held_table, target)
        _refile(conn, a, period, target)
        assert dl.promoted_into(conn, DS, target) == held


class TestRefusedWithWhatComesFirst:
    """Criteria 10, 11 and 12."""

    def test_a_rejected_supply(self, conn, period, target):
        from qa_tools.common import filing_decisions as fd

        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        rejection.reject(conn, agency_id=AG, collection_id=COL, dataset_id=DS, supply=a,
                         physical_tables=[a_table], actor=REAL_PERSON, effective_at=WHEN,
                         reason="bad", from_slot=period)
        with pytest.raises(dl.DecisionRefused, match="Reverse the rejection"):
            fd.consequences(conn, _request(fd.REFILE, period, a, to_period=target))

    def test_one_file_of_a_contested_pair(self, conn, period, target):
        from qa_tools.common import refiling

        a, _ = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        conn.execute(f"INSERT INTO {filing.TABLE} (dataset_id, supply_id, slot, branch, "
                     "delivery) SELECT dataset_id, supply_id || '#1', slot, branch, delivery "
                     f"FROM {filing.CURRENT} WHERE supply_id = ?", [a])
        with pytest.raises(dl.DecisionRefused, match="contested pair"):
            refiling.plan(conn, dataset_id=DS, supply=a + "#1", to_period=target)

    def test_into_an_inherited_period(self, conn, period, target, monkeypatch):
        from qa_tools.common import refiling

        a, _ = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        real_held = dl.held

        class Inherited:
            held_as, holder, stands_on = dl.INHERITED, "x", period

        monkeypatch.setattr(dl, "held", lambda c, d, p, **k: Inherited() if p == target
                            else real_held(c, d, p, **k))
        with pytest.raises(dl.DecisionRefused, match="un-inherit"):
            refiling.plan(conn, dataset_id=DS, supply=a, to_period=target)


class TestTheWarning:
    """REQ-GHUB-142: every consequence, plainly, from the same plan."""

    def test_it_names_each_consequence_and_no_supply_id_in_its_prose(
            self, conn, period, target):
        from qa_tools.common import filing_decisions as fd

        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period)
        newer, _ = _filed(conn, target, "2026-06-01T01:00:00+00:00")
        lines = fd.consequences(conn, _request(fd.REFILE, period, a, to_period=target)).lines
        assert any(f"removes {period}'s accepted" in line for line in lines)
        assert any(f"supersedes {target}'s waiting" in line and "1 June 2026" in line
                   for line in lines)
        for line in lines:
            prose = [part for part in line.split("\n")
                     if not part.strip().startswith("mothman ")]
            assert not any("@" in part for part in prose), prose

    def test_nothing_displaced_means_no_panel(self, conn, period, target):
        from qa_tools.common import filing_decisions as fd

        a, _ = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        assert fd.consequences(conn, _request(fd.REFILE, period, a, to_period=target)).lines == ()

    def test_unconfirmed_it_is_refused_and_nothing_moves(self, conn, period, target):
        from qa_tools.common import filing_decisions as fd

        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period)
        with pytest.raises(fd.ConsequencesNotAcknowledged):
            fd.apply(_request(fd.REFILE, period, a, to_period=target, confirmed=True),
                     effective_at=WHEN, conn=conn)
        assert dl.promoted_into(conn, DS, period) == a

    def test_both_routes_show_the_same_warning(self, conn, period, target, monkeypatch):
        """NFR 1: one implementation for both routes - the GitHub route posts
        consequences() as the terminal shows it."""
        from qa_tools.common import filing_decisions as fd, filing_from_github as gh, people

        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period, at="2026-05-02T01:00:00+00:00")
        monkeypatch.setattr(people, "person_by_github",
                            lambda who: people.person_by_email(REAL_PERSON))
        posted = []

        class Service:
            def comment(self, ticket, body):
                posted.append(body)

        gh.handle(gh.Comment(body=f"/refile supply: {a} to: {target} confirm: yes\nsupplier said",
                             author="keith-on-github", slot_key=f"{DS}/{period}"),
                  collection_id=COL, effective_at=WHEN, service=Service(), ticket=1)
        terminal = fd.consequences(conn, _request(fd.REFILE, period, a, to_period=target))
        assert posted and all(line.split("\n")[0] in posted[-1] for line in terminal.lines)


class TestCriticFindingsOnSprintNine:
    """post-build-review #114: what the delivery critic found in the first
    build of the re-file, each reproduced here before it was fixed."""

    def test_a_superseded_supply_refiled_waits_in_its_new_period(self, conn, period, target):
        """D1: re-filing a superseded supply moved its tables to staging and
        left it superseded - unpromotable by anyone, and superseding what
        waited in the target in favour of a supply that could not win."""
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        supersession.supersede(conn, agency_id=AG, collection_id=COL, dataset_id=DS,
                               supply=a, period=period, actor=REAL_PERSON,
                               reason="not this one", effective_at=WHEN)
        assert supersession.is_superseded(conn, DS, a)
        _refile(conn, a, period, target)
        assert not supersession.is_superseded(conn, DS, a)
        assert supersession.waiting_in(conn, DS, target) == [a]
        assert _schema_of(conn, a_table) == [supply_db.STAGING_SCHEMA]

    def test_the_warning_says_a_promoted_target_keeps_its_version(self, conn, period, target):
        """D3: the warning said the target 'reads the re-filed one from this
        decision on' when a promoted version there stays (criterion 9), and
        even an empty target only has the re-filed one WAITING."""
        from qa_tools.common import filing_decisions as fd

        a, _ = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        held, held_table = _filed(conn, target, "2026-06-01T01:00:00+00:00")
        _promote(conn, held, held_table, target)
        _filed(conn, target, "2026-07-01T01:00:00+00:00")
        lines = fd.consequences(conn, _request(fd.REFILE, period, a, to_period=target)).lines
        assert lines and not any("reads the re-filed one" in line for line in lines)
        assert any(f"{target} keeps its accepted" in line for line in lines), lines

    def test_a_refusal_comes_before_the_request_to_confirm(self, conn, period, target):
        """D5: on the GitHub route a rejected supply was first told to
        confirm, and only after confirming told it could not be re-filed."""
        from qa_tools.common import filing_decisions as fd

        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        rejection.reject(conn, agency_id=AG, collection_id=COL, dataset_id=DS, supply=a,
                         physical_tables=[a_table], actor=REAL_PERSON, effective_at=WHEN,
                         reason="bad", from_slot=period)
        with pytest.raises(dl.DecisionRefused, match="Reverse the rejection"):
            fd.apply(_request(fd.REFILE, period, a, to_period=target), effective_at=WHEN,
                     conn=conn)

    def test_a_plan_overtaken_before_the_lock_is_refused(self, conn, period, target):
        """D4: the plan was judged before the slot lock, so a version filed
        into the target in between was neither superseded nor named."""
        from qa_tools.common import refiling

        a, _ = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        stale = refiling.plan(conn, dataset_id=DS, supply=a, to_period=target)
        late, late_table = _filed(conn, target, "2026-06-01T01:00:00+00:00")
        with pytest.raises(dl.DecisionRefused, match="changed"):
            refiling.apply(conn, stale, agency_id=AG, collection_id=COL, actor=REAL_PERSON,
                           reason="r", effective_at=WHEN)
        assert _current_slot(conn, a) == period
        assert _schema_of(conn, late_table) == [supply_db.STAGING_SCHEMA]

    def test_a_held_supply_is_told_to_be_placed(self, conn, period, target):
        """#114 minor: a supply filed to no period got an empty warning,
        then a refusal about two slots."""
        from qa_tools.common import refiling

        a, _ = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        import filing_support

        (delivery,) = conn.execute(f"SELECT delivery FROM {filing.CURRENT} WHERE "
                                   "supply_id = ?", [a]).fetchall()[0]
        filing_support.place(conn, DS, a, None, delivery)
        with pytest.raises(dl.DecisionRefused, match="filed to no period"):
            refiling.plan(conn, dataset_id=DS, supply=a, to_period=target)
