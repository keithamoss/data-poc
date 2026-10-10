"""A person can excuse a late supply, with a reason, without changing the
calendar it was judged against (REQ-PIPE-161).

Against a real database and the real cp-clients agreement: 2023-Q2 is due
2023-05-01 09:00 Perth, so a supply received 2023-07-25 and filed there is
LATE; filed to 2023-Q3 (due 2023-08-01) the same supply is EARLY. qa.decision
is append-only, so every test uses supplies of its own.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

import filing_support
from qa_tools.common import (assignment, decision_log as dl, excuse, filing,
                             filing_decisions as fd, people, qa_store, rejection, supply_db)

PERTH = timezone(timedelta(hours=8))
DATASET = "cp-clients"
LATE_SLOT, EARLY_SLOT = "2023-Q2", "2023-Q3"
RECEIVED = datetime(2023, 7, 25, 9, tzinfo=PERTH)
KEITH = "fpycnkgvmt@privaterelay.appleid.com"
AT = "2026-10-11T05:00:00+08:00"


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-excuse") as c:
        qa_store.ensure_schema(c)
        yield c


def _late(slot=LATE_SLOT, received=RECEIVED):
    supply = f"cp-clients@excuse-{uuid.uuid4().hex[:10]}"
    filing_support.file(assignment.Assignment(
        dataset_id=DATASET, supply_id=supply, slot=slot, branch=assignment.OPEN_UNFILLED,
        considered=(slot,), received_at=received))
    return supply


def _req(op, supply=None, period=LATE_SLOT, reason="the supplier's outage, agreed", **kw):
    return fd.Request(operation=op, dataset_id=DATASET, actor=people.person_by_email(KEITH),
                      reason=reason, period=period, supply=supply, **kw)


def _apply(conn, request, at=AT):
    return fd.apply(request, effective_at=at, conn=conn)


class TestAnExcuse:
    def test_it_is_one_entry_and_the_supply_still_reads_late(self, conn):
        """Criteria 2, 4 and 5."""
        supply = _late()
        before = filing.filing_for(DATASET, supply)
        out = _apply(conn, _req(fd.EXCUSE_LATENESS, supply))
        assert out.changed
        rows = conn.execute(
            f"SELECT action, supply, to_slot, actor_kind FROM {dl.TABLE} "
            "WHERE dataset_id = ? AND supply = ?", [DATASET, supply]).fetchall()
        assert rows == [(dl.EXCUSE_LATENESS, supply, LATE_SLOT, dl.PERSON)]
        assert filing.filing_for(DATASET, supply) == before
        assert before["classification"] == "late"
        got = excuse.in_force(conn, DATASET, supply)
        assert got.reason == "the supplier's outage, agreed" and got.slot == LATE_SLOT

    def test_it_changes_nothing_a_slot_holds(self, conn):
        """NFR 1: qa.slot_holds ignores it by construction."""
        supply = _late()
        _apply(conn, _req(fd.EXCUSE_LATENESS, supply))
        assert dl.held(conn, DATASET, LATE_SLOT) is None or \
            dl.held(conn, DATASET, LATE_SLOT).holder != supply

    def test_a_supply_that_is_not_late_is_refused_and_told_why(self, conn):
        """Criterion 3."""
        supply = _late(slot=EARLY_SLOT)
        with pytest.raises(dl.DecisionRefused, match="early for 2023-Q3, not late"):
            _apply(conn, _req(fd.EXCUSE_LATENESS, supply, period=EARLY_SLOT))

    def test_one_already_excused_is_refused(self, conn):
        supply = _late()
        _apply(conn, _req(fd.EXCUSE_LATENESS, supply))
        with pytest.raises(dl.DecisionRefused, match="already excused"):
            _apply(conn, _req(fd.EXCUSE_LATENESS, supply))

    def test_the_wrong_period_is_refused(self, conn):
        supply = _late()
        with pytest.raises(dl.DecisionRefused, match="filed to 2023-Q2, not 2023-Q3"):
            _apply(conn, _req(fd.EXCUSE_LATENESS, supply, period=EARLY_SLOT))

    def test_a_reason_is_required(self, conn):
        supply = _late()
        with pytest.raises(dl.DecisionRefused, match="needs a reason"):
            _apply(conn, _req(fd.EXCUSE_LATENESS, supply, reason=" "))

    def test_no_rule_may_excuse(self, conn):
        """Criterion 6."""
        supply = _late()
        with pytest.raises(dl.DecisionRefused, match="only a person"):
            with dl.apply_decision(conn, dl.Decision(
                    agency_id="child-protection-family-support",
                    collection_id="child-protection", dataset_id=DATASET,
                    action=dl.EXCUSE_LATENESS, supply=supply, actor="automated:rule",
                    actor_kind=dl.RULE, effective_at=AT, to_slot=LATE_SLOT, reason="r")):
                pass

    def test_it_does_not_bar_the_gate(self, conn):
        """Criterion 19: an excuse is about punctuality, not quality."""
        supply = _late()
        _apply(conn, _req(fd.EXCUSE_LATENESS, supply))
        assert not rejection.decided_by_a_person(conn, DATASET, supply)


class TestWithdrawal:
    def test_a_withdrawal_leaves_it_late_and_not_excused(self, conn):
        """Criterion 8."""
        supply = _late()
        _apply(conn, _req(fd.EXCUSE_LATENESS, supply))
        _apply(conn, _req(fd.WITHDRAW_EXCUSE, supply, reason="it was not the outage"),
               at="2026-10-11T06:00:00+08:00")
        assert excuse.in_force(conn, DATASET, supply) is None
        [e] = excuse.history(conn, DATASET, supply)
        assert e.withdrawn["reason"] == "it was not the outage"
        # and it can be excused again afterwards
        _apply(conn, _req(fd.EXCUSE_LATENESS, supply), at="2026-10-11T07:00:00+08:00")
        assert excuse.in_force(conn, DATASET, supply) is not None

    def test_nothing_to_withdraw_is_refused(self, conn):
        supply = _late()
        with pytest.raises(dl.DecisionRefused, match="no excuse in force"):
            _apply(conn, _req(fd.WITHDRAW_EXCUSE, supply))

    def test_withdrawal_does_not_bar_the_gate_either(self, conn):
        supply = _late()
        _apply(conn, _req(fd.EXCUSE_LATENESS, supply))
        _apply(conn, _req(fd.WITHDRAW_EXCUSE, supply), at="2026-10-11T06:00:00+08:00")
        assert not rejection.decided_by_a_person(conn, DATASET, supply)


class TestItLapses:
    def test_a_refile_lapses_it_and_does_not_carry_it(self, conn):
        """Criterion 7."""
        supply = _late()
        _apply(conn, _req(fd.EXCUSE_LATENESS, supply))
        filing.refile(conn, DATASET, supply, EARLY_SLOT, decision_id=1)
        assert excuse.in_force(conn, DATASET, supply) is None
        [e] = excuse.history(conn, DATASET, supply)
        assert e.lapsed == "re-filed to 2023-Q3" and e.slot == LATE_SLOT

    def test_as_at_before_it_was_recorded_there_is_none(self, conn):
        """REQ-DASH-162 criterion 5's input: an in-place-on date before it."""
        supply = _late()
        _apply(conn, _req(fd.EXCUSE_LATENESS, supply))
        assert excuse.in_force(conn, DATASET, supply, as_at="2026-10-10T00:00:00+08:00") is None
        assert excuse.in_force(conn, DATASET, supply, as_at=AT) is not None


class TestARange:
    """Criteria 9, 16 and 17."""

    def _range(self, first, last, **kw):
        return fd.Request(operation=fd.EXCUSE_LATENESS, dataset_id="cp-carers",
                          actor=people.person_by_email(KEITH), reason="the outage",
                          period=first, through_period=last, **kw)

    def _file(self, slot, received):
        supply = f"cp-carers@range-{uuid.uuid4().hex[:10]}"
        filing_support.file(assignment.Assignment(
            dataset_id="cp-carers", supply_id=supply, slot=slot,
            branch=assignment.OPEN_UNFILLED, considered=(slot,), received_at=received))
        return supply

    def test_it_shows_what_it_excuses_and_skips_then_records_one_entry_each(self, conn):
        late_a = self._file("2024-Q1", datetime(2024, 3, 1, 9, tzinfo=PERTH))
        late_b = self._file("2024-Q2", datetime(2024, 6, 1, 9, tzinfo=PERTH))
        early = self._file("2024-Q3", datetime(2024, 7, 25, 9, tzinfo=PERTH))
        request = self._range("2024-Q1", "2024-Q3")
        found = fd.consequences(conn, request)
        text = "\n".join(found.lines)
        assert f"excuse {late_a} (2024-Q1)" in text and f"excuse {late_b} (2024-Q2)" in text
        assert f"skip {early} (2024-Q3)" in text and "early" in text
        with pytest.raises(fd.ConsequencesNotAcknowledged):
            _apply(conn, request)
        _apply(conn, self._range("2024-Q1", "2024-Q3", acknowledged=found.key))
        for supply in (late_a, late_b):
            assert excuse.in_force(conn, "cp-carers", supply) is not None
        assert excuse.in_force(conn, "cp-carers", early) is None

    def test_a_range_that_excuses_nothing_is_refused(self, conn):
        self._file("2025-Q3", datetime(2025, 7, 25, 9, tzinfo=PERTH))
        with pytest.raises(dl.DecisionRefused, match="nothing in 2025-Q3 to 2025-Q3"):
            fd.consequences(conn, self._range("2025-Q3", "2025-Q3"))

    def test_a_backwards_range_is_refused(self, conn):
        with pytest.raises(dl.DecisionRefused, match="runs backwards"):
            fd.consequences(conn, self._range("2025-Q3", "2025-Q1"))


class TestTheRoutes:
    """Criteria 10, 14, 15 and 18."""

    @pytest.fixture
    def cli(self, monkeypatch):
        from click.testing import CliRunner

        from cli import filing_tui, supply
        monkeypatch.setattr(filing_tui, "actor_at_the_keyboard",
                            lambda: people.person_by_email(KEITH))
        monkeypatch.setattr(fd, "reconcile_after", lambda *a, **k: None)
        return lambda argv: CliRunner().invoke(supply.supply_group, argv)

    def test_the_operations_are_named_excuse_lateness_and_withdraw_excuse(self):
        assert {"excuse-lateness", "withdraw-excuse"} <= set(fd.OPERATIONS)

    def test_one_supply_through_supply_decide(self, conn, cli):
        supply = _late()
        got = cli(["decide", "--operation", "excuse-lateness", "--dataset", DATASET,
                   "--period", LATE_SLOT, "--supply", supply, "--reason", "outage", "--yes"])
        assert got.exit_code == 0, got.output
        assert excuse.in_force(conn, DATASET, supply).reason == "outage"

    def test_a_range_through_the_shared_pair_needs_the_key(self, conn, cli):
        a = f"cp-carers@cli-{uuid.uuid4().hex[:10]}"
        filing_support.file(assignment.Assignment(
            dataset_id="cp-carers", supply_id=a, slot="2025-Q1",
            branch=assignment.OPEN_UNFILLED, considered=("2025-Q1",),
            received_at=datetime(2025, 3, 1, 9, tzinfo=PERTH)))
        argv = ["decide", "--operation", "excuse-lateness", "--dataset", "cp-carers",
                "--from-period", "2025-Q1", "--through-period", "2025-Q1",
                "--reason", "outage", "--yes"]
        first = cli(argv)
        assert first.exit_code != 0 and a in first.output
        key = fd.consequences(conn, fd.Request(
            operation=fd.EXCUSE_LATENESS, dataset_id="cp-carers",
            actor=people.person_by_email(KEITH), reason="r", period="2025-Q1",
            through_period="2025-Q1")).key
        assert key in first.output
        second = cli([*argv, "--acknowledge", key])
        assert second.exit_code == 0, second.output
        assert excuse.in_force(conn, "cp-carers", a) is not None

    def test_the_range_flags_are_for_excuse_only_and_never_to_period(self, cli):
        got = cli(["decide", "--operation", "promote", "--dataset", DATASET,
                   "--from-period", "2024-Q1", "--through-period", "2024-Q2",
                   "--reason", "r", "--yes"])
        assert got.exit_code != 0 and "excuse-lateness only" in got.output

    def test_the_terminal_offers_it_on_a_late_supply_and_withdrawal_once_excused(self, conn):
        from qa_tools.common import filing_queue, slot_state

        supply = _late()
        state = slot_state.SlotState(dataset_id=DATASET, period=LATE_SLOT,
                                     state=slot_state.AWAITING_DECISION, supply=supply)
        assert filing_queue.excuse_offers(conn, state) == (fd.EXCUSE_LATENESS,)
        _apply(conn, _req(fd.EXCUSE_LATENESS, supply))
        assert filing_queue.excuse_offers(conn, state) == (fd.WITHDRAW_EXCUSE,)
        on_time = slot_state.SlotState(dataset_id=DATASET, period=EARLY_SLOT,
                                       state=slot_state.AWAITING_DECISION,
                                       supply=_late(slot=EARLY_SLOT))
        assert filing_queue.excuse_offers(conn, on_time) == ()

    def test_the_reason_prompt_says_it_is_published(self, monkeypatch):
        from cli import common, filing_tui

        asked = []
        monkeypatch.setattr(filing_tui, "actor_at_the_keyboard",
                            lambda: people.person_by_email(KEITH))
        monkeypatch.setattr(filing_tui, "_consequences", lambda r: fd.Consequences(lines=()))
        monkeypatch.setattr(common, "text_prompt", lambda q, **k: asked.append(q) or None)
        filing_tui.apply_decision(operation=fd.EXCUSE_LATENESS, dataset_id=DATASET,
                                  period=LATE_SLOT, supply="s")
        assert "published beside the supply on the dashboard" in asked[0]

    def test_supply_decisions_lists_it(self, conn):
        """Criterion 12: the log's own listing reads every action."""
        supply = _late()
        _apply(conn, _req(fd.EXCUSE_LATENESS, supply))
        actions = [r[0] for r in conn.execute(
            f"SELECT action FROM {dl.TABLE} WHERE supply = ?", [supply]).fetchall()]
        assert actions == [dl.EXCUSE_LATENESS]


class TestTheDashboardEmbed:
    """REQ-DASH-162 criteria 6 and 7: from recorded decisions only, beside
    the classification, the person by name."""

    def test_it_embeds_the_excuse_by_run_with_the_person_named(self, conn, monkeypatch):
        from pipeline import excuses, slot_timeline

        supply = _late()
        _apply(conn, _req(fd.EXCUSE_LATENESS, supply))
        monkeypatch.setattr(slot_timeline, "_run_for",
                            lambda c, ds, s: "run-x" if s == supply else None)
        got = excuses.for_dataset(DATASET, conn)
        [entry] = got["run-x"]
        assert entry["reason"] == "the supplier's outage, agreed"
        assert entry["actor"] != KEITH and "@" not in entry["actor"]
        assert entry["withdrawn"] is None and entry["lapsed"] is None

    def test_a_lapse_carries_its_instant(self, conn):
        supply = _late()
        _apply(conn, _req(fd.EXCUSE_LATENESS, supply))
        with dl.apply_decision(conn, dl.Decision(
                agency_id="child-protection-family-support", collection_id="child-protection",
                dataset_id=DATASET, action=dl.REFILE, supply=supply, actor=KEITH,
                actor_kind=dl.PERSON, effective_at="2026-10-11T06:00:00+08:00",
                from_slot=LATE_SLOT, to_slot=EARLY_SLOT, reason="wrong period")) as decided:
            filing.refile(conn, DATASET, supply, EARLY_SLOT, decision_id=decided)
        [e] = excuse.history(conn, DATASET, supply)
        assert e.lapsed == "re-filed to 2023-Q3"
        assert e.lapsed_at.startswith("2026-10-10T22:00")
