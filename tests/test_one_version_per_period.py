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


def _in_period(conn, period):
    return [r[0] for r in conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = ? "
        "AND table_type = 'BASE TABLE'", [period_schema.period_schema(period)]).fetchall()]


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
        # In the period under the plain base name; the displaced one leaves
        # under its stamped name, rebuilt from its supply (REQ-PIPE-129).
        assert _in_period(conn, period) == [TABLE]
        assert _schema_of(conn, b_table) == []
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
        assert _in_period(conn, period) == [TABLE]
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


    def test_the_printed_undo_works_when_pasted(self, conn, period, later):
        """#112 re-check, HIGH: the substitute command carried no --supply,
        so after the demote the slot's own (demoted) supply was taken and
        the substitution refused. Each printed step is applied as printed."""
        import shlex

        from qa_tools.common import filing_decisions as fd

        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period)
        substitution.substitute(conn, agency_id=AG, collection_id=COL, dataset_id=DS,
                                logical_table=TABLE, period=later, stands_on=period,
                                supply=a, actor=REAL_PERSON, reason="late", effective_at=WHEN)
        b, b_table = _filed(conn, later, "2026-08-02T01:00:00+00:00")
        found = fd.consequences(conn, _request(fd.PROMOTE, later, b))
        fd.apply(_request(fd.PROMOTE, later, b, acknowledged=found.key),
                 effective_at=WHEN, conn=conn)
        commands = [c.strip() for c in found.lines[0].split("\n")
                    if c.strip().startswith("mothman ")]
        for command in commands:
            argv = shlex.split(command)
            opts = {argv[i][2:]: argv[i + 1] for i in range(len(argv) - 1)
                    if argv[i].startswith("--") and not argv[i + 1].startswith("--")}
            fd.apply(_request(opts["operation"], opts["period"], supply=opts.get("supply"),
                              stands_on=opts.get("stands-on"), confirmed=True),
                     effective_at=WHEN, conn=conn)
        h = dl.held(conn, DS, later)
        assert (h.held_as, h.holder, h.stands_on) == (dl.SUBSTITUTED, a, period)


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

    def test_the_undo_is_both_steps_and_each_command_has_its_own_line(self, conn, period):
        """Keith, 2026-10-05: honest two-step wording (#112)."""
        from qa_tools.common import filing_decisions as fd

        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period)
        b, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        (line,) = fd.consequences(conn, _request(fd.PROMOTE, period, b)).lines
        commands = [c.strip() for c in line.split("\n") if c.strip().startswith("mothman ")]
        assert [c.split("--operation ")[1].split()[0] for c in commands] == [
            "un-supersede", "promote"]
        assert "returns to waiting" in line

    def test_a_wrong_key_is_not_blamed_on_a_change(self, conn, period):
        from qa_tools.common import filing_decisions as fd

        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period)
        b, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        with pytest.raises(fd.ConsequencesNotAcknowledged) as caught:
            fd.apply(_request(fd.PROMOTE, period, b, acknowledged="deadbeef00"),
                     effective_at=WHEN, conn=conn)
        message = str(caught.value)
        assert "deadbeef00 does not match" in message and "mistyped" in message
        assert f"--acknowledge {caught.value.key}" in message

    def test_the_success_message_says_what_else_was_done(self, conn, period):
        from qa_tools.common import filing_decisions as fd

        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period)
        b, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        key = fd.consequences(conn, _request(fd.PROMOTE, period, b)).key
        got = fd.apply(_request(fd.PROMOTE, period, b, acknowledged=key),
                       effective_at=WHEN, conn=conn)
        assert f"{a} moved to superseded." in got.message


class TestRefusedBeforeTheConfirmation:
    """Keith, 2026-10-05 (#112): a promotion certain to be refused is
    refused while the warning is worked out, before anyone is asked."""

    def test_a_displaced_supply_a_later_period_stands_on(self, conn, period, later):
        from qa_tools.common import filing_decisions as fd

        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period)
        substitution.substitute(conn, agency_id=AG, collection_id=COL, dataset_id=DS,
                                logical_table=TABLE, period=later, stands_on=period,
                                supply=a, actor=REAL_PERSON, reason="late", effective_at=WHEN)
        b, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        with pytest.raises(dl.DecisionRefused, match=later):
            fd.consequences(conn, _request(fd.PROMOTE, period, b))

    def test_an_inherited_slot(self, conn, period, later, monkeypatch):
        from qa_tools.common import filing_decisions as fd

        class Held:
            held_as, holder, stands_on = dl.INHERITED, "x", period
        monkeypatch.setattr(dl, "held", lambda *_a, **_k: Held())
        b, _ = _filed(conn, later, "2026-05-02T01:00:00+00:00")
        with pytest.raises(dl.DecisionRefused, match="un-inherit"):
            fd.consequences(conn, _request(fd.PROMOTE, later, b))


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


class TestNoRouteLeavesTwoVersionsInAPeriod:
    """Criterion 1 under the three paths the post-build critic found
    (plans/post-build-review.md #112): a race, a promoted supply rejected,
    and a promotion with no tables."""

    def test_two_promotions_at_once_leave_one_version(self, conn, period):
        import threading

        b, b_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        c, c_table = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        period_schema.open_period(conn, period, opened_by="rule", effective_at=WHEN)
        errors = []
        started = threading.Event()

        def second():
            try:
                with supply_db.connect(label="test-race") as other:
                    started.set()
                    _promote(other, c, c_table, period, kind=dl.PERSON)
            except Exception as exc:  # noqa: BLE001 - reported below
                errors.append(exc)

        with conn.raw.transaction():
            _promote(conn, b, b_table, period, kind=dl.PERSON)
            worker = threading.Thread(target=second)
            worker.start()
            started.wait(5)
            # Long enough for the other promotion to reach the lock.
            import time
            time.sleep(1.0)
        worker.join(30)
        assert not errors, errors
        assert _in_period(conn, period) == [TABLE]
        assert dl.promoted_into(conn, DS, period) == c
        assert supersession.is_superseded(conn, DS, b)
        assert _schema_of(conn, b_table) == [supersession.superseded_schema(period)]

    def test_rejecting_a_promoted_supply_takes_its_table_out(self, conn, period):
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period)
        from qa_tools.common import filing_decisions as fd
        fd.apply(_request(fd.REJECT, period, supply=a), effective_at=WHEN, conn=conn)
        assert _in_period(conn, period) == []
        assert _schema_of(conn, a_table) == [supply_db.REJECTED_SCHEMA]
        b, b_table = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        _promote(conn, b, b_table, period)
        assert _in_period(conn, period) == [TABLE]

    def test_a_promotion_with_no_tables_is_refused(self, conn, period):
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period)
        with pytest.raises(dl.DecisionRefused, match="no tables"):
            promotion.promote(conn, agency_id=AG, collection_id=COL, dataset_id=DS,
                              supply=f"{DS}@999999999999999999", period=period,
                              physical_tables=[], actor=REAL_PERSON,
                              actor_kind=dl.PERSON, effective_at=WHEN, reason="typo")
        assert dl.promoted_into(conn, DS, period) == a
        assert not supersession.is_superseded(conn, DS, a)
        assert _in_period(conn, period) == [TABLE]

    def test_a_rule_never_displaces_what_a_person_promoted(self, conn, period):
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period, kind=dl.PERSON)
        b, b_table = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        with pytest.raises(dl.DecisionRefused, match="no automatic rule displaces"):
            _promote(conn, b, b_table, period)
        assert dl.promoted_into(conn, DS, period) == a
        assert _schema_of(conn, b_table) == [supply_db.STAGING_SCHEMA]


class TestTheTerminalSaysItBeforeAsking:
    """#112: refused before the prompt, commands printed whole and outside
    the panel, and a decision changed twice never exits silently."""

    def _patch(self, monkeypatch):
        from cli import filing_tui
        from qa_tools.common import filing_decisions as fd, people

        monkeypatch.setattr(filing_tui, "actor_at_the_keyboard",
                            lambda: people.person_by_email(REAL_PERSON))
        monkeypatch.setattr(fd, "reconcile_after", lambda *a, **k: None)
        asked = []
        monkeypatch.setattr(filing_tui.common, "confirm",
                            lambda *a, **k: asked.append(a) or True)
        return filing_tui, asked

    def test_refused_without_asking_and_the_command_is_one_unbroken_line(
            self, conn, period, later, monkeypatch, capsys):
        filing_tui, asked = self._patch(monkeypatch)
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period, at="2026-05-02T01:00:00+00:00")
        substitution.substitute(conn, agency_id=AG, collection_id=COL, dataset_id=DS,
                                logical_table=TABLE, period=later, stands_on=period,
                                supply=a, actor=REAL_PERSON, reason="late",
                                effective_at="2026-05-02T02:00:00+00:00")
        b, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        out = filing_tui.apply_decision(operation="promote", dataset_id=DS, period=period,
                                        supply=b, reason="better")
        assert out is None and asked == []
        printed = capsys.readouterr().out
        command = (f"mothman supply decide --operation de-substitute --dataset {DS} "
                   f"--period {later} --reason '<why>' --yes")
        assert command in printed.splitlines()

    def test_refused_before_the_reason_is_asked_for(self, conn, period, later,
                                                    monkeypatch, capsys):
        """#113: a reason typed for a decision about to be refused is wasted."""
        filing_tui, asked = self._patch(monkeypatch)
        prompted = []
        monkeypatch.setattr(filing_tui.common, "text_prompt",
                            lambda *a, **k: prompted.append(a) or "x")
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period, at="2026-05-02T01:00:00+00:00")
        substitution.substitute(conn, agency_id=AG, collection_id=COL, dataset_id=DS,
                                logical_table=TABLE, period=later, stands_on=period,
                                supply=a, actor=REAL_PERSON, reason="late",
                                effective_at="2026-05-02T02:00:00+00:00")
        b, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        out = filing_tui.apply_decision(operation="promote", dataset_id=DS, period=period,
                                        supply=b)
        assert out is None and prompted == [] and asked == []

    def test_changed_twice_is_said(self, conn, period, monkeypatch, capsys):
        from qa_tools.common import filing_decisions as fd

        filing_tui, _ = self._patch(monkeypatch)
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period, at="2026-05-02T01:00:00+00:00")
        b, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        found = fd.consequences(conn, _request(fd.PROMOTE, period, b))

        def never_matches(request, **_k):
            raise fd.ConsequencesNotAcknowledged(found, given=request.acknowledged)
        monkeypatch.setattr(fd, "apply", never_matches)
        out = filing_tui.apply_decision(operation="promote", dataset_id=DS, period=period,
                                        supply=b, reason="better")
        assert out is None
        assert "kept changing" in capsys.readouterr().out


class TestPromoteOverIsReachableInTheWizard:
    """Keith, 2026-10-05 (#112): a version waiting in a promoted period is
    in the queue and the period door, offering promote."""

    def test_listed_and_offered(self, conn, period, monkeypatch):
        from qa_tools.common import filing_queue, slot_state

        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period, at="2026-05-02T01:00:00+00:00")
        b, _ = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        holder = slot_state.SlotState(dataset_id=DS, period=period,
                                      state=slot_state.PROMOTED, supply=a)
        (item,) = filing_queue.waiting_over_promoted(conn, [holder])
        assert item.supply == b and item.state == filing_queue.ANOTHER_VERSION_WAITING
        assert a in item.reason
        supply_scoped, _ = filing_queue.operations_for(item)
        assert supply_scoped[0] == "promote"


class TestAnUnsupersededSupplyWaitsAgain:
    """#113 (CLI re-check): the undo says un-supersede returns the displaced
    supply to waiting - so it must be in the queue, waiting, afterwards."""

    def test_it_is_listed_as_waiting(self, conn, period):
        from qa_tools.common import filing_decisions as fd

        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period)
        b, b_table = _filed(conn, period, "2026-05-02T01:00:00+00:00")
        key = fd.consequences(conn, _request(fd.PROMOTE, period, b)).key
        fd.apply(_request(fd.PROMOTE, period, b, acknowledged=key), effective_at=WHEN,
                 conn=conn)
        fd.apply(_request(fd.UN_SUPERSEDE, period, a), effective_at=WHEN, conn=conn)
        assert supersession.waiting_in(conn, DS, period, besides=b) == [a]
