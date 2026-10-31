"""The post-build critics' findings on sprint A2 and Keith's answers to them
(plans/post-build-review.md #267; REQ-PIPE-271, REQ-PIPE-280).

Each defect's test was written first and seen to fail against the tree the
critics reviewed (2cfe68c); each of Keith's answers (K1 to K8, 2026-10-24)
is pinned in the words he approved. Against this worker's own database, with
the quarter Case Workers sits out stated by carry_forward_support.
"""
from __future__ import annotations

import dataclasses
import re
import uuid
from datetime import datetime, timezone

import pytest
from click.testing import CliRunner

import carry_forward_support
import filing_support
from carry_forward_support import CASE_WORKERS, KEYS, NAME, entries, promote, view_reads
from qa_tools.common import (carry_forward, filing, hierarchy, inheritance, knock_on,
                             period_schema, people, promotion, recheck,
                             substitution, supply_db)
from qa_tools.common import decision_log as dl
from qa_tools.common import filing_decisions as fd

conn = carry_forward_support.conn
world = carry_forward_support.world

REAL_PERSON = "fpycnkgvmt@privaterelay.appleid.com"


@pytest.fixture
def actor():
    return people.person_by_email(REAL_PERSON)


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[│╭╮╰╯─]", " ", text))


def _open(conn, period, at="2099-08-01T09:00:00+08:00"):
    period_schema.open_period(conn, period, opened_by="pytest", effective_at=at)


def _stale(conn, world):
    """Q2's Case Workers promoted, Q4 opened on it, then Q3's promoted."""
    q2 = promote(conn, world.q2, "2099-04-02T09:00:00+08:00")
    _open(conn, world.q4)
    q3 = promote(conn, world.q3, "2099-09-02T09:00:00+08:00")
    return q2, q3


def _refused(conn, world):
    """Q4 opened with nothing earlier, then Q3's Case Workers promoted."""
    _open(conn, world.q4)
    return promote(conn, world.q3, "2099-09-02T09:00:00+08:00")


def _received_on(conn, supply: str, slot: str, at: datetime) -> None:
    """A real receipt for a supply the support module promoted: its delivery
    and filing, so received_at_of answers with a real instant."""
    name = f"pytest-cf-review-{supply}"
    filing_support.ensure_delivery(name, CASE_WORKERS, at)
    filing_support.place(conn, CASE_WORKERS, supply, slot, name)


def _request(actor, world, operation=fd.CARRY_FORWARD, **kw):
    kw.setdefault("reason", "the newer one is current")
    kw.setdefault("period", world.q4)
    return fd.Request(operation=operation, dataset_id=CASE_WORKERS, actor=actor,
                      confirmed=True, **kw)


def _apply(conn, actor, world, operation=fd.CARRY_FORWARD, **kw):
    request = _request(actor, world, operation, **kw)
    key = fd.consequences(conn, request).key
    return fd.apply(dataclasses.replace(request, acknowledged=key or None),
                    effective_at="2099-10-05T09:00:00+08:00", conn=conn)


# ---------------------------------------------------------------------------
# The functional critic's defects
# ---------------------------------------------------------------------------

class TestOneWarningPerPeriodOnTheDashboard:
    """D1: the page showed every recorded warning for a period, two at once."""

    def test_a_refused_period_warned_twice_shows_one_on_any_day(self, conn, world):
        _open(conn, world.q4)
        promote(conn, world.q2, "2099-08-10T09:00:00+08:00")
        q3 = promote(conn, world.q3, "2099-09-02T09:00:00+08:00")
        got = [w for w in carry_forward.for_dashboard(CASE_WORKERS, conn)
               if w["period"] == world.q4]
        assert got, "the build carries the warnings"
        standing = [w for w in got if w["until"] is None]
        assert len(standing) == 1 and standing[0]["supply"] == q3, \
            "one shown, the newest warned supply - as standing() reads it"
        days = sorted((w["from"], w["until"] or "9999-12-31") for w in got)
        for (_a, end), (start, _b) in zip(days, days[1:]):
            assert end <= start, f"two warnings for {world.q4} overlap: {days}"


class TestTheWordsAreWhatThePeriodHoldsNow:
    """D2 and Keith's K5: after an un-inherit the warning said the period
    still carried the old supply."""

    def test_an_un_inherit_is_said_as_carrying_nothing(self, conn, world):
        _q2, q3 = _stale(conn, world)
        inheritance.un_inherit(conn, dataset_id=CASE_WORKERS, period=world.q4,
                               actor=REAL_PERSON, reason="freeing a demote", confirmed=True,
                               effective_at="2099-09-10T09:00:00+08:00")
        (w,) = carry_forward.standing(conn, dataset_id=CASE_WORKERS, period=world.q4)
        said = carry_forward.lines(w, voice="page")
        received = carry_forward.received(CASE_WORKERS, q3)
        assert said[0] == (f"{world.q4} carries nothing forward for {NAME}. The one "
                           f"received {received}, promoted into {world.q3}, could be "
                           f"carried forward:")
        assert said[1] == carry_forward.command(w)
        assert not any("carries forward the supply received" in s for s in said)

    def test_the_page_says_the_stale_words_until_the_un_inherit_and_the_new_after(
            self, conn, world):
        _stale(conn, world)
        inheritance.un_inherit(conn, dataset_id=CASE_WORKERS, period=world.q4,
                               actor=REAL_PERSON, reason="freeing a demote", confirmed=True,
                               effective_at="2099-09-10T09:00:00+08:00")
        got = sorted((w for w in carry_forward.for_dashboard(CASE_WORKERS, conn)
                      if w["period"] == world.q4), key=lambda w: w["from"])
        assert [(w["from"], w["until"]) for w in got] == [
            ("2099-09-02", "2099-09-10"), ("2099-09-10", None)]
        assert "carries forward the supply received" in got[0]["sentences"][0]
        assert got[1]["sentences"][0].startswith(f"{world.q4} carries nothing forward for "
                                                 f"{NAME}. The one received ")
        assert got[0]["headline"] == got[1]["headline"]


class TestAnUnopenedPeriodIsRefused:
    """D3: a carry-forward into an unopened period opened it, the opening's
    inheritance made it a no-op, and it still reported a change."""

    def test_refused_in_words_opening_nothing_and_recording_nothing(self, conn, world, actor):
        promote(conn, world.q2, "2099-04-02T09:00:00+08:00")
        assert not period_schema.opened(conn, world.q4)
        with pytest.raises(dl.DecisionRefused) as refused:
            _apply(conn, actor, world)
        assert str(refused.value) == (
            f"{world.q4} is not open yet, so there is nothing to carry forward into: it "
            f"inherits the newest promoted {NAME} when it opens, at its first filing. "
            f"Nothing was recorded.")
        assert not period_schema.opened(conn, world.q4)
        assert entries(conn, world.q4) == []


class TestAViewIsReplacedWhateverItsColumns:
    """D4: CREATE OR REPLACE VIEW failed raw where a column's type changed."""

    def _newer_with_text_ids(self, conn, world) -> str:
        e = hierarchy.dataset(CASE_WORKERS)
        key = "2099" + str(uuid.uuid4().int)[:16]
        supply, physical = f"{CASE_WORKERS}@{key}", f"{e.table}__{key}"
        conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" (id text)')
        promotion.promote(conn, **KEYS, dataset_id=CASE_WORKERS, supply=supply,
                          period=world.q3, physical_tables=[physical], actor="pytest",
                          actor_kind=dl.RULE, effective_at="2099-09-02T09:00:00+08:00")
        return supply

    def test_a_newer_supply_whose_column_changed_type_is_carried_forward(self, conn, world):
        promote(conn, world.q2, "2099-04-02T09:00:00+08:00")
        _open(conn, world.q4)
        q3 = self._newer_with_text_ids(conn, world)
        carry_forward.carry_forward(conn, dataset_id=CASE_WORKERS, period=world.q4,
                                    actor=REAL_PERSON, reason="current",
                                    effective_at="2099-10-05T09:00:00+08:00")
        assert inheritance.inherited(conn, CASE_WORKERS, world.q4).supply == q3
        assert period_schema.period_schema(world.q3) in view_reads(conn, world.q4)

    def test_refused_in_words_where_another_view_reads_it(self, conn, world):
        _q2, _q3 = _stale(conn, world)
        schema = period_schema.period_schema(world.q4)
        reader = f"pytest_reads_cw_{uuid.uuid4().hex[:8]}"
        conn.execute(f'CREATE VIEW public."{reader}" AS SELECT * FROM "{schema}".cp_case_workers')
        before = view_reads(conn, world.q4)
        try:
            with pytest.raises(dl.DecisionRefused) as refused:
                carry_forward.carry_forward(conn, dataset_id=CASE_WORKERS, period=world.q4,
                                            actor=REAL_PERSON, reason="current",
                                            effective_at="2099-10-05T09:00:00+08:00")
            assert f"public.{reader} reads {world.q4}'s cp_case_workers" in str(refused.value)
            assert str(refused.value).endswith("Nothing was recorded.")
            assert view_reads(conn, world.q4) == before
            assert not entries(conn, world.q4, dl.CARRY_FORWARD)
        finally:
            conn.execute(f'DROP VIEW IF EXISTS public."{reader}"')

    def test_the_view_and_its_entry_are_one_transaction(self, conn, world):
        """T2, at the level of the view itself: the period's view and the
        carry-forward entry carry the same creating transaction, so no
        committed state ever held one without the other - or neither."""
        _stale(conn, world)
        carry_forward.carry_forward(conn, dataset_id=CASE_WORKERS, period=world.q4,
                                    actor=REAL_PERSON, reason="current",
                                    effective_at="2099-10-05T09:00:00+08:00")
        (entry,) = entries(conn, world.q4, dl.CARRY_FORWARD)
        (view_xid,) = conn.execute(
            "SELECT xmin::text FROM pg_class WHERE oid = to_regclass(?)",
            [f'"{period_schema.period_schema(world.q4)}".cp_case_workers']).fetchone()
        (entry_xid,) = conn.execute(f"SELECT xmin::text FROM {dl.TABLE} WHERE id = ?",
                                    [entry["id"]]).fetchone()
        assert view_xid == entry_xid


class TestAFailedOpeningIsRetried:
    """S1: an opening that failed after the filing committed was never
    retried - every later pass took the 'already filed' skip."""

    def test_the_next_pass_opens_the_period(self, conn, world, monkeypatch):
        from types import SimpleNamespace

        from qa_tools.common import assignment as assign_mod

        promote(conn, world.q2, "2099-04-02T09:00:00+08:00")
        at = datetime(2099, 10, 2, 1, 0, tzinfo=timezone.utc)
        supply = f"cp-notifications@20991002{uuid.uuid4().int % 10**12:012d}"
        name = f"pytest-retry-{supply}"
        filing_support.ensure_delivery(name, "cp-notifications", at)
        arrival = SimpleNamespace(files_by_dataset={"cp-notifications": ["f"]},
                                  received_at=at, delivery_name=name, run_id=f"run-{supply}")
        monkeypatch.setattr(filing, "_supply_id_for", lambda arr, ds: supply)
        monkeypatch.setattr(assign_mod, "assign", lambda **kw: assign_mod.Assignment(
            dataset_id=kw["dataset_id"], supply_id=kw["supply_id"], slot=world.q4,
            branch="pytest", considered=(world.q4,), received_at=kw["at"]))
        real = period_schema.open_period

        def fails(*a, **k):
            raise RuntimeError("the database went away after the filing")
        monkeypatch.setattr(period_schema, "open_period", fails)
        with pytest.raises(RuntimeError, match="went away"):
            filing.file_arrivals([arrival])
        assert filing.filing_for("cp-notifications", supply)["slot"] == world.q4
        assert not period_schema.opened(conn, world.q4)

        monkeypatch.setattr(period_schema, "open_period", real)
        filing.file_arrivals([arrival])
        assert period_schema.opened(conn, world.q4)
        (opened_by,) = conn.execute('SELECT opened_by FROM "qa".period WHERE name = ?',
                                    [world.q4]).fetchone()
        assert opened_by.startswith(f"the filing of {supply}")


class TestADecisionThatDoesNotStandOpensNothing:
    """S5: a re-file, a placement and a settlement opened their period before
    the decision was judged again under its lock - so one refused or rolled
    back there had opened it anyway."""

    def _fails_owing(self, monkeypatch):
        def owe(*a, **k):
            raise RuntimeError("the decision failed after its judgement")
        monkeypatch.setattr(recheck, "owe", owe)

    def test_a_failed_re_file_opens_nothing(self, conn, world, actor, monkeypatch):
        key = "2099" + str(uuid.uuid4().int)[:16]
        supply = f"cp-notifications@{key}"
        conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."cp_notifications__{key}" '
                     "(id integer)")
        filing_support.filed(conn, "cp-notifications", supply, world.q3)
        request = fd.Request(operation=fd.REFILE, dataset_id="cp-notifications", actor=actor,
                             reason="it is Q4's data", period=world.q3, to_period=world.q4,
                             supply=supply, confirmed=True)
        key_ = fd.consequences(conn, request).key
        self._fails_owing(monkeypatch)
        with pytest.raises(RuntimeError):
            fd.apply(dataclasses.replace(request, acknowledged=key_ or None),
                     effective_at="2099-10-03T09:00:00+08:00", conn=conn)
        assert not period_schema.opened(conn, world.q4)

    def _held(self, conn):
        import test_place_held_supply as place_support

        return place_support._held(conn, f"2099-H{uuid.uuid4().hex[:6]}")

    def test_a_placement_opens_its_period_once_it_stands(self, conn):
        import test_place_held_supply as place_support

        supply, _table = self._held(conn)
        target = f"2099-P{uuid.uuid4().hex[:6]}"
        assert not period_schema.opened(conn, target)
        assert place_support._place(conn, supply, target).changed
        assert period_schema.opened(conn, target)
        (opened_by,) = conn.execute('SELECT opened_by FROM "qa".period WHERE name = ?',
                                    [target]).fetchone()
        assert opened_by.startswith(f"the placement of {supply} ")

    def test_a_failed_placement_opens_nothing(self, conn, monkeypatch):
        import test_place_held_supply as place_support

        supply, _table = self._held(conn)
        target = f"2099-P{uuid.uuid4().hex[:6]}"
        self._fails_owing(monkeypatch)
        with pytest.raises(RuntimeError):
            place_support._place(conn, supply, target)
        assert not period_schema.opened(conn, target)

    def test_a_settlement_opens_the_period_it_files_into(self, conn, actor):
        from datetime import date, timedelta

        from pair_support import Pair, _at, free_day

        day = free_day(conn, date(2026, 11, 1))
        nxt = day + timedelta(days=1)
        p = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "13:30")),
                             (f"birth_registrations_{nxt}.csv", _at(day, "13:45"))])
        assert not period_schema.opened(conn, nxt.isoformat())
        one, two = (n for n, _ in p.files)
        p.settle(conn, actor, (one, "supply"), (two, "refile", nxt.isoformat()))
        assert period_schema.opened(conn, nxt.isoformat())

    def test_a_failed_settlement_opens_nothing(self, conn, actor, monkeypatch):
        from datetime import date, timedelta

        from pair_support import Pair, _at, free_day
        from qa_tools.common import supersession

        day = free_day(conn, date(2026, 11, 1))
        nxt = day + timedelta(days=1)
        p = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "13:30")),
                             (f"birth_registrations_{nxt}.csv", _at(day, "13:45"))])
        one, two = (n for n, _ in p.files)

        def fails(*a, **k):
            raise RuntimeError("the settlement failed after its judgement")
        monkeypatch.setattr(supersession, "drop_if_empty", fails)
        with pytest.raises(RuntimeError):
            p.settle(conn, actor, (one, "supply"), (two, "refile", nxt.isoformat()))
        assert not period_schema.opened(conn, nxt.isoformat())


class TestTheFollowUpBlamesOnlyItsOwnPeriod:
    """S6: the carry-forward's follow-up blamed the first failure the
    collection's follow-up returned, whichever period it was about."""

    def test_another_periods_failure_is_not_this_ones(self, conn, world, actor,
                                                     monkeypatch, capsys):
        from cli import filing_tui

        _stale(conn, world)
        monkeypatch.setattr(filing_tui, "_readers_of", lambda *a: [])

        def follow_up(*a, **k):
            with supply_db.connect(label="t") as c:
                mine = [o.id for o in recheck.owed(c) if o.period == world.q4]
            return ([recheck.Outcome(i, "k", True, "re-evaluated") for i in mine]
                    + [recheck.Outcome(-1, "", False, "another period's run broke")])
        monkeypatch.setattr(knock_on, "follow_up", follow_up)
        found = fd.consequences(conn, _request(actor, world))
        filing_tui.apply_decision(operation=fd.CARRY_FORWARD, dataset_id=CASE_WORKERS,
                                  period=world.q4, reason="current", actor=actor, yes=True,
                                  acknowledged=found.key)
        out = _flat(capsys.readouterr().out)
        assert "were not re-checked yet" not in out
        assert "another period's run broke" in out, "said, as any follow-up says one"


class TestAWarningNeverRefusesItsPromotion:
    """S7: the warning's words opened a connection per receipt inside the
    promotion's transaction, so a connection that could not be had refused
    the promotion."""

    def test_the_words_are_read_through_the_promotions_connection(self, conn, world,
                                                                  monkeypatch):
        promote(conn, world.q2, "2099-04-02T09:00:00+08:00")
        _open(conn, world.q4)
        real = filing._connect
        inside = []

        def refuses(label):
            if inside:
                raise supply_db.SupplyDbError("no second connection to be had")
            return real(label)
        monkeypatch.setattr(filing, "_connect", refuses)
        real_warn = carry_forward.warn_after_promotion

        def warn(*a, **k):
            inside.append(True)
            try:
                return real_warn(*a, **k)
            finally:
                inside.clear()
        monkeypatch.setattr(carry_forward, "warn_after_promotion", warn)
        q3 = promote(conn, world.q3, "2099-09-02T09:00:00+08:00")
        assert dl.promoted_into(conn, CASE_WORKERS, world.q3) == q3
        (recorded,) = entries(conn, world.q4, dl.CARRY_FORWARD_WARNING)
        assert recorded["reason"].startswith(f"A newer {NAME} could be carried forward")


# ---------------------------------------------------------------------------
# Keith's answers, 2026-10-24
# ---------------------------------------------------------------------------

class TestKeithsAnswers:

    def test_k1_datasets_by_name_and_the_id_in_the_command_only(self, conn, world, actor):
        _stale(conn, world)
        (w,) = carry_forward.standing(conn, dataset_id=CASE_WORKERS, period=world.q4)
        for voice in ("page", "terminal"):
            said = carry_forward.lines(w, voice=voice)
            prose = [s for s in said if not s.startswith("mothman ")]
            assert all(CASE_WORKERS not in s for s in prose), prose
            assert any(NAME in s for s in prose)
            assert f"--dataset {CASE_WORKERS}" in carry_forward.command(w)
        found = fd.consequences(conn, _request(actor, world))
        assert all(CASE_WORKERS not in line.split("mothman")[0] for line in found.lines)
        assert any(f"the {NAME} received" in line for line in found.lines)

    def test_k2_the_refused_cases_undo_line(self, conn, world, actor):
        _refused(conn, world)
        found = fd.consequences(conn, _request(actor, world))
        assert ("To carry nothing again, un-inherit — its readers are left with no "
                "table.") in found.lines

    def test_k3_the_queue_offers_one_item_that_opens_the_door(self, conn, world,
                                                             monkeypatch, capsys):
        from cli import common, filing_tui

        _stale(conn, world)
        asked = []

        def select(message, choices, **kw):
            asked.append((message, list(choices)))
            if message == "Which one?":
                # The queue's item, then - where other tests on this worker left
                # warnings of their own - this world's period among them.
                return next((c for c in choices if c.startswith("Could be carried forward (")),
                            next((c for c in choices if c.endswith(f"into {world.q4}.")), None))
            return None   # stop at the door's own choice
        monkeypatch.setattr(common, "select", select)
        filing_tui.queue_flow("child-protection")
        out = capsys.readouterr().out
        queue = asked[0][1]
        items = [c for c in queue if c.startswith("Could be carried forward (")]
        assert len(items) == 1 and re.fullmatch(r"Could be carried forward \(\d+\)", items[0])
        message, offered = asked[-1]
        assert world.q4 in message and any(c.startswith("carry forward") for c in offered)
        assert f"{world.q4} carries forward the {NAME} received" in _flat(out)

    def test_k4_a_promotion_that_raises_a_warning_says_so(self, conn, world, actor,
                                                          monkeypatch, capsys):
        from cli import filing_tui

        q2 = promote(conn, world.q2, "2099-04-02T09:00:00+08:00")
        _open(conn, world.q4)
        e = hierarchy.dataset(CASE_WORKERS)
        key = "2099" + str(uuid.uuid4().int)[:16]
        supply = f"{CASE_WORKERS}@{key}"
        conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{e.table}__{key}" (id int)')
        filing_support.filed(conn, CASE_WORKERS, supply, world.q3)
        monkeypatch.setattr(knock_on, "follow_up", lambda *a, **k: [])
        monkeypatch.setattr(filing_tui, "actor_at_the_keyboard", lambda: actor)
        found = fd.consequences(conn, fd.Request(
            operation=fd.PROMOTE, dataset_id=CASE_WORKERS, actor=actor, reason="good",
            period=world.q3, supply=supply))
        outcome = filing_tui.apply_decision(
            operation=fd.PROMOTE, dataset_id=CASE_WORKERS, period=world.q3, supply=supply,
            reason="good", actor=actor, yes=True, acknowledged=found.key or None,
            flag_route=True)
        assert outcome is not None and outcome.changed
        assert dl.held(conn, CASE_WORKERS, world.q4).holder == q2
        assert (f"This makes a newer {NAME} available to carry forward into {world.q4}. "
                f"Carry it forward from the {world.q4} door, or:") in outcome.message
        command = (f"mothman supply decide --operation carry-forward --dataset "
                   f"{CASE_WORKERS} --period {world.q4} --reason '<why>'")
        assert command in capsys.readouterr().out.splitlines(), "below the panel, whole"

    def test_k6_an_opening_inherits_as_at_its_receipt_and_warns(self, conn, world,
                                                                monkeypatch):
        """A promotion processed before the filing, taking effect after the
        filing's receipt, is not what the opening carries - it is warned."""
        from test_period_opening import _file

        q2 = promote(conn, world.q2, "2099-04-02T09:00:00+08:00")
        q3 = promote(conn, world.q3, "2099-10-03T09:00:00+08:00")
        _supply, arrival = _file(monkeypatch, world, world.q4)
        assert arrival.received_at < datetime(2099, 10, 3, 1, 0, tzinfo=timezone.utc)
        assert dl.held(conn, CASE_WORKERS, world.q4).holder == q2, "as at the receipt"
        (w,) = carry_forward.standing(conn, dataset_id=CASE_WORKERS, period=world.q4)
        assert (w.supply, w.carried, w.promoted_into) == (q3, q2, world.q3)
        (recorded,) = entries(conn, world.q4, dl.CARRY_FORWARD_WARNING)
        (caused, at) = conn.execute(f"SELECT caused_by_decision, effective_at FROM {dl.TABLE} "
                                    "WHERE id = ?", [recorded["id"]]).fetchone()
        (promoted,) = [e for e in dl.decisions_for(conn, CASE_WORKERS)
                       if e["action"] == dl.PROMOTE and e["supply"] == q3]
        assert (caused, at) == (promoted["id"], promoted["effective_at"]), \
            "caused by that promotion, dated when it took effect"

    def test_k6_an_opening_carrying_the_newest_warns_nothing(self, conn, world, monkeypatch):
        from test_period_opening import _file

        promote(conn, world.q2, "2099-04-02T09:00:00+08:00")
        q3 = promote(conn, world.q3, "2099-09-03T09:00:00+08:00")
        _file(monkeypatch, world, world.q4)
        assert dl.held(conn, CASE_WORKERS, world.q4).holder == q3
        assert not entries(conn, world.q4, dl.CARRY_FORWARD_WARNING)

    def test_k7_one_headline_for_both_cases(self, conn, world):
        _refused(conn, world)
        (w,) = carry_forward.standing(conn, dataset_id=CASE_WORKERS, period=world.q4)
        assert carry_forward.headline(w) == (f"A newer {NAME} could be carried forward "
                                             f"into {world.q4}.")
        (shown,) = [x for x in carry_forward.for_dashboard(CASE_WORKERS, conn)
                    if x["period"] == world.q4]
        assert shown["headline"] == carry_forward.headline(w)

    def test_k8_a_substitution_clears_it_and_is_never_warned(self, conn, world):
        q2 = promote(conn, world.q2, "2099-08-10T09:00:00+08:00")
        _open(conn, world.q4)
        # Opened before Q2's promotion took effect, so refused - and warned (K6).
        (w,) = carry_forward.standing(conn, dataset_id=CASE_WORKERS, period=world.q4)
        assert (w.supply, w.carried) == (q2, None)
        substitution.substitute(conn, **KEYS, dataset_id=CASE_WORKERS,
                                logical_table="cp_case_workers", period=world.q4,
                                stands_on=world.q2, supply=q2, actor=REAL_PERSON,
                                reason="a person chose it",
                                effective_at="2099-08-20T09:00:00+08:00")
        assert carry_forward.standing(conn, dataset_id=CASE_WORKERS, period=world.q4) == []
        promote(conn, world.q3, "2099-09-02T09:00:00+08:00")
        assert carry_forward.standing(conn, dataset_id=CASE_WORKERS, period=world.q4) == []

    def test_an_unknown_date_does_not_clear(self, conn, world, monkeypatch):
        """Polish: `_newer` read an unreadable date as 'carries the newer one'."""
        q2, _q3 = _stale(conn, world)
        (w,) = carry_forward.standing(conn, dataset_id=CASE_WORKERS, period=world.q4)
        real = carry_forward._date
        monkeypatch.setattr(carry_forward, "_date",
                            lambda p, ds: None if p == world.q2 else real(p, ds))
        assert not carry_forward._cleared_as_at(conn, w, "2099-09-03T09:00:00+08:00")


# ---------------------------------------------------------------------------
# The CLI UX critic's findings
# ---------------------------------------------------------------------------

class TestTheTerminal:

    @pytest.fixture
    def keyboard(self, monkeypatch, actor):
        from cli import filing_tui
        monkeypatch.setattr(filing_tui, "actor_at_the_keyboard", lambda: actor)
        monkeypatch.setattr(knock_on, "follow_up", lambda *a, **k: [])

    def _decide(self, *args):
        from cli.supply import supply_group
        return CliRunner().invoke(supply_group, ["decide", *args], env={"COLUMNS": "200"})

    def test_s4_a_period_not_on_the_calendar_is_said_as_one(self, conn, world, keyboard):
        for operation in ("carry-forward", "inherit"):
            got = self._decide("--operation", operation, "--dataset", CASE_WORKERS,
                               "--period", "2024-Q9", "--reason", "r", "--yes")
            assert got.exit_code == 1, got.output
            flat = _flat(got.output)
            assert "2024-Q9 is not a period on the quarterly calendar." in flat, flat
            assert "takes part in" not in flat and "DOES participate" not in flat

    def test_s5_a_mistyped_dataset_is_said_never_a_traceback(self, keyboard):
        got = self._decide("--operation", "carry-forward", "--dataset", "cp-case-workerz",
                           "--period", "2024-Q4", "--reason", "r", "--yes")
        assert got.exit_code == 1
        assert "'cp-case-workerz' is not a dataset" in got.output
        assert got.exception is None or isinstance(got.exception, SystemExit)

    def test_m2_nothing_newer_is_said_on_the_choice_and_asks_no_reason(
            self, conn, world, keyboard, monkeypatch, capsys):
        from cli import common, filing_tui

        promote(conn, world.q2, "2099-04-02T09:00:00+08:00")
        _open(conn, world.q4)   # inherits Q2's, the newest: nothing newer
        asked = []

        def select(message, choices, **kw):
            if message == "Which dataset?":
                return CASE_WORKERS
            if message.startswith("Which period"):
                return next(c for c in choices if c.startswith(world.q4))
            asked.append(list(choices))
            return next(c for c in choices if c.startswith("carry forward"))
        monkeypatch.setattr(common, "select", select)
        prompted = []
        monkeypatch.setattr(common, "text_prompt", lambda *a, **k: prompted.append(a) or "r")
        filing_tui.period_flow("child-protection")
        assert "carry forward (nothing newer to carry forward)" in asked[-1]
        assert not prompted, "no reason asked for a decision that does nothing"
        assert "Already so" in capsys.readouterr().out

    def test_m3_un_inherits_note_only_where_something_newer_exists(self, conn, world, actor):
        promote(conn, world.q2, "2099-04-02T09:00:00+08:00")
        _open(conn, world.q4)
        found = fd.consequences(conn, _request(actor, world, fd.UN_INHERIT))
        assert not any("carry-forward" in n for n in found.notes)
        promote(conn, world.q3, "2099-09-02T09:00:00+08:00")
        found = fd.consequences(conn, _request(actor, world, fd.UN_INHERIT))
        assert any(n.startswith(f"A newer {NAME} could be carried forward into {world.q4}.")
                   for n in found.notes)

    def test_m3_the_wizard_sends_the_person_back_to_the_door(self, conn, world, actor,
                                                             keyboard, monkeypatch, capsys):
        from cli import common, filing_tui

        _stale(conn, world)
        monkeypatch.setattr(common, "confirm_change", lambda *a, **k: False)
        filing_tui.apply_decision(operation=fd.UN_INHERIT, dataset_id=CASE_WORKERS,
                                  period=world.q4, reason="r", actor=actor)
        out = capsys.readouterr().out
        assert "Instead" in out and "What this does" not in out
        assert "choose carry forward from the period's door" in _flat(out)
        assert not any(line.startswith("mothman ") for line in out.splitlines())

    def test_m4_the_prose_wraps_between_words_and_the_command_never(
            self, conn, world, monkeypatch, capsys):
        from rich.console import Console

        from cli import filing_tui

        _stale(conn, world)
        monkeypatch.setattr(filing_tui, "console", Console(width=60, force_terminal=False))
        (w,) = carry_forward.standing(conn, dataset_id=CASE_WORKERS, period=world.q4)
        filing_tui.say_carry_forward_warnings([w])
        out = capsys.readouterr().out.splitlines()
        assert carry_forward.command(w) in out, "the command whole, on its own line"
        heading = ("Could be carried forward (1) - a newer supply was promoted after this "
                   "period opened")
        words = set(" ".join(carry_forward.lines(w, voice="terminal") + [heading]).split())
        prose = [line for line in out if line.strip() and not line.startswith("mothman ")]
        assert len(prose) > 3, "the prose wrapped at 60 columns"
        for line in prose:
            assert len(line) <= 60, line
            assert all(word in words for word in line.split()), \
                f"a word broken across lines: {line!r}"

    def test_m5_one_period_is_said_as_one_and_the_door_does_not_send_you_there(
            self, conn, world, capsys):
        from cli import filing_tui

        _stale(conn, world)
        (w,) = carry_forward.standing(conn, dataset_id=CASE_WORKERS, period=world.q4)
        filing_tui.say_carry_forward_warnings([w], in_door=True)
        out = _flat(capsys.readouterr().out)
        assert "Could be carried forward (1)" in out and "this period opened" in out
        assert "these periods" not in out
        assert f"or from the {world.q4} door." not in out

    def test_minors_labels_say_what_the_period_carries(self, conn, world):
        from cli import filing_tui

        _stale(conn, world)
        inherited, = [s for s in carry_forward.carried_periods(conn, CASE_WORKERS)
                      if s.period == world.q4]
        label = filing_tui._label(inherited)
        assert "carries forward the one received" in label and "arrived" not in label
        nothing = dataclasses.replace(inherited, state="carries-nothing-forward", supply=None)
        assert filing_tui._label(nothing).endswith("owes nothing, carries nothing forward")
        assert "nothing arrived" not in filing_tui._label(nothing)

    def test_minors_queue_help_mentions_the_warnings(self):
        from cli.supply import supply_group
        got = CliRunner().invoke(supply_group, ["queue", "--help"])
        assert "carried forward" in _flat(got.output)

    def test_minors_the_carry_forward_choice_fits_80_columns(self):
        from cli import filing_tui
        assert len(filing_tui._WHAT_IT_DOES[fd.CARRY_FORWARD]) + 3 <= 80


# ---------------------------------------------------------------------------
# Test weaknesses T1, T3, T4, T5, T6
# ---------------------------------------------------------------------------

class TestTheWarningIsShownForBothCases:
    """T1: the queue showing the item, not counted, and the dashboard's data,
    for the stale case and the refused one."""

    @pytest.mark.parametrize("case", ["stale", "refused"])
    def test_the_queue_shows_it_uncounted(self, conn, world, case, monkeypatch, capsys):
        from cli import common, filing_tui

        (_stale if case == "stale" else _refused)(conn, world)
        asked = []
        monkeypatch.setattr(common, "select",
                            lambda message, choices, **kw: asked.append(list(choices)))
        filing_tui.queue_flow("child-protection")
        out = capsys.readouterr().out
        (w,) = carry_forward.standing(conn, dataset_id=CASE_WORKERS, period=world.q4)
        assert carry_forward.command(w) in out.splitlines()
        counted = re.findall(r"(\d+) (?:supply|supplies) waiting on a decision", out)
        assert not counted or all(world.q4 not in line for line in out.splitlines()
                                  if "waiting on a decision" in line)
        assert any(c.startswith("Could be carried forward (") for c in asked[0])

    @pytest.mark.parametrize("case", ["stale", "refused"])
    def test_the_dashboard_data_carries_its_words(self, conn, world, case):
        newer = (_stale(conn, world)[1] if case == "stale" else _refused(conn, world))
        (shown,) = [x for x in carry_forward.for_dashboard(CASE_WORKERS, conn)
                    if x["period"] == world.q4]
        assert shown["supply"] == newer and shown["until"] is None
        first = shown["sentences"][0]
        assert first.startswith(f"A newer {NAME}" if case == "stale"
                                else f"{world.q4} carries nothing forward for {NAME}: ")
        assert shown["door"] == f"or from the {world.q4} door."


class TestTheRecordShapes:
    """T3: each constraint clause broken alone, for a carry-forward and for
    its warning (schema 47)."""

    _BASE = {"carry-forward": {"actor_kind": "person", "to_slot": "p", "stands_on": "q",
                               "reason": "r", "caused_by_decision": None},
             "carry-forward-warning": {"actor_kind": "rule", "to_slot": "p",
                                       "stands_on": "q", "reason": None,
                                       "caused_by_decision": 1}}

    def _insert(self, conn, action, **fields):
        conn.execute(
            f"INSERT INTO {dl.TABLE} (agency_id, collection_id, dataset_id, action, supply, "
            "to_slot, stands_on, reason, actor, actor_kind, caused_by_decision, effective_at, "
            "recorded_at) VALUES (?, ?, ?, ?, 's', ?, ?, ?, 'a', ?, ?, now(), now())",
            [KEYS["agency_id"], KEYS["collection_id"], CASE_WORKERS, action,
             fields["to_slot"], fields["stands_on"], fields["reason"], fields["actor_kind"],
             fields["caused_by_decision"]])

    @pytest.mark.parametrize("action,broken", [
        ("carry-forward", {"actor_kind": "rule"}),
        ("carry-forward", {"to_slot": None}),
        ("carry-forward", {"stands_on": None}),
        ("carry-forward", {"reason": None}),
        ("carry-forward-warning", {"actor_kind": "person"}),
        ("carry-forward-warning", {"to_slot": None}),
        ("carry-forward-warning", {"stands_on": None}),
        ("carry-forward-warning", {"caused_by_decision": None}),
    ])
    def test_each_clause_is_held(self, conn, action, broken):
        import psycopg

        (anchor,) = conn.execute(f"SELECT max(id) FROM {dl.TABLE}").fetchone()
        base = dict(self._BASE[action], caused_by_decision=(
            anchor if self._BASE[action]["caused_by_decision"] else None))
        # The unbroken record is accepted, so the refusal below is the clause's.
        with pytest.raises(_RolledBack):
            with conn.raw.transaction():
                self._insert(conn, action, **base)
                raise _RolledBack
        with pytest.raises(psycopg.errors.CheckViolation):
            with conn.raw.transaction():
                self._insert(conn, action, **{**base, **broken})


class _RolledBack(Exception):
    pass


class TestTheWordsWithARealInstant:
    """T4: a rendering test where every <instant> is a real receipt."""

    def test_the_stale_warning_names_both_receipts(self, conn, world):
        q2, q3 = _stale(conn, world)
        _received_on(conn, q2, world.q2, datetime(2099, 4, 1, 1, 0, tzinfo=timezone.utc))
        _received_on(conn, q3, world.q3, datetime(2099, 9, 1, 1, 0, tzinfo=timezone.utc))
        (w,) = carry_forward.standing(conn, dataset_id=CASE_WORKERS, period=world.q4)
        assert carry_forward.lines(w, voice="page")[0] == (
            f"A newer {NAME} could be carried forward into {world.q4}. {world.q4} carries "
            f"forward the supply received 9:00am Wednesday, 1 April 2099; the one received "
            f"9:00am Tuesday, 1 September 2099 has been promoted into {world.q3} since.")


class TestTheRestOfTheOperation:
    """T5: the lines of carry_forward.py and filing_decisions._failed_against
    no test reached."""

    def test_a_reason_is_required(self, conn, world):
        _stale(conn, world)
        with pytest.raises(carry_forward.CarryForwardRefused, match="needs a reason"):
            carry_forward.carry_forward(conn, dataset_id=CASE_WORKERS, period=world.q4,
                                        actor=REAL_PERSON, reason=" ",
                                        effective_at="2099-10-05T09:00:00+08:00")

    def test_a_substituted_period_is_refused(self, conn, world):
        q2 = promote(conn, world.q2, "2099-08-10T09:00:00+08:00")
        _open(conn, world.q4)
        substitution.substitute(conn, **KEYS, dataset_id=CASE_WORKERS,
                                logical_table="cp_case_workers", period=world.q4,
                                stands_on=world.q2, supply=q2, actor=REAL_PERSON,
                                reason="chosen", effective_at="2099-08-20T09:00:00+08:00")
        with pytest.raises(carry_forward.CarryForwardRefused, match="de-substitute it first"):
            carry_forward.plan(conn, CASE_WORKERS, world.q4)

    def test_nothing_earlier_is_refused(self, conn, world):
        _open(conn, world.q4)
        with pytest.raises(carry_forward.CarryForwardRefused,
                           match=f"no earlier promoted {NAME} supply"):
            carry_forward.plan(conn, CASE_WORKERS, world.q4)

    def test_a_change_under_the_lock_refuses_it(self, conn, world, monkeypatch):
        _stale(conn, world)
        real, calls = carry_forward.plan, []

        def changed(*a, **k):
            calls.append(1)
            p = real(*a, **k)
            return p if len(calls) == 1 else dataclasses.replace(p, supply="someone-else")
        monkeypatch.setattr(carry_forward, "plan", changed)
        with pytest.raises(carry_forward.CarryForwardRefused, match="has changed"):
            carry_forward.carry_forward(conn, dataset_id=CASE_WORKERS, period=world.q4,
                                        actor=REAL_PERSON, reason="r",
                                        effective_at="2099-10-05T09:00:00+08:00")
        assert not entries(conn, world.q4, dl.CARRY_FORWARD)

    def test_a_carried_supply_is_not_warned_again(self, conn, world):
        q2, q3 = _stale(conn, world)
        assert carry_forward.warn_after_promotion(
            conn, dataset_id=CASE_WORKERS, supply=q3, period=world.q3,
            effective_at="2099-09-02T10:00:00+08:00", promotion_id=1) == []

    def test_an_already_standing_warning_is_not_recorded_twice(self, conn, world):
        """warn_at_opening's dedupe and its no-newer return."""
        q2, q3 = _stale(conn, world)
        assert carry_forward.warn_at_opening(
            conn, dataset_id=CASE_WORKERS, period=world.q4, carried=(world.q2, q2),
            effective_at="2099-09-03T09:00:00+08:00") is None
        assert carry_forward.warn_at_opening(
            conn, dataset_id=CASE_WORKERS, period=world.q4, carried=(world.q3, q3),
            effective_at="2099-09-03T09:00:00+08:00") is None

    def test_a_supply_of_its_own_clears_it(self, conn, world):
        _stale(conn, world)
        inheritance.un_inherit(conn, dataset_id=CASE_WORKERS, period=world.q4,
                               actor=REAL_PERSON, reason="its own is coming", confirmed=True,
                               effective_at="2099-09-10T09:00:00+08:00")
        assert carry_forward.standing(conn, dataset_id=CASE_WORKERS, period=world.q4)
        promote(conn, world.q4, "2099-10-02T09:00:00+08:00")
        assert carry_forward.standing(conn, dataset_id=CASE_WORKERS, period=world.q4) == []

    def test_as_at_a_day_before_it_was_raised_nothing_stands(self, conn, world):
        _stale(conn, world)
        assert carry_forward.standing(conn, dataset_id=CASE_WORKERS, period=world.q4,
                                      as_at="2099-09-01T09:00:00+08:00") == []
        assert carry_forward.standing(conn, dataset_id=CASE_WORKERS, period=world.q4,
                                      as_at="2099-09-02T09:00:00+08:00")

    def test_a_carried_forward_period_stands_in_on_the_newer_supply(self, conn, world):
        """promotion_state.standing_in read inherit and substitute only, so a
        period carried forward named the supply it no longer stood on."""
        from qa_tools.common import promotion_state

        _q2, q3 = _stale(conn, world)
        carry_forward.carry_forward(conn, dataset_id=CASE_WORKERS, period=world.q4,
                                    actor=REAL_PERSON, reason="current",
                                    effective_at="2099-10-05T09:00:00+08:00")
        got = promotion_state.standing_in(conn, CASE_WORKERS, period=world.q4)
        assert (got.kind, got.supply, got.stands_on) == (promotion_state.INHERITED, q3,
                                                         world.q3)

    def test_failed_against_reads_what_each_check_read(self, conn, world):
        from carry_forward_support import ASSIGNED_WORKER
        from test_results_about import _read, _result, _run

        q2 = promote(conn, world.q2, "2099-04-02T09:00:00+08:00")
        n = promote(conn, world.q4, "2099-08-02T10:00:00+08:00", dataset_id="cp-notifications")
        q3 = promote(conn, world.q3, "2099-09-02T09:00:00+08:00")
        _run(conn, f"pytest-fa-{uuid.uuid4().hex[:8]}", dataset_id="cp-notifications",
             supply=n, at="2099-09-03T09:00:00+08:00",
             cross=[(_result(ASSIGNED_WORKER, "cp-notifications", "fail"),
                     (_read("cp_case_workers", q3), _read("cp_notifications", n)))])
        reader = [r for r in knock_on.readers(conn, world.q4, ["cp_case_workers"],
                                              promotion._declared_reads())
                  if r.dataset_id == "cp-notifications"][0]
        assert fd._failed_against(conn, reader, "cp_case_workers", q3)
        assert not fd._failed_against(conn, reader, "cp_case_workers", q2)


class TestASharedCalendar:
    """T6, criterion 4: a quarter Emergency Department and Child Protection
    share is opened by whichever collection files to it first, named."""

    def test_an_emergency_department_filing_opens_a_child_protection_quarter(
            self, conn, world, monkeypatch):
        from test_period_opening import _file

        from qa_tools.common import inheritance

        # AT ONE OFFSET (REQ-PIPE-323 criterion 4): where the two collections'
        # files go into a period at different files_go_to_period values, each
        # group makes its own inheritances - tests/test_offset_group_inheritance.py.
        monkeypatch.setattr(inheritance, "offset_group", lambda ds, period: 0)
        q2 = promote(conn, world.q2, "2099-04-02T09:00:00+08:00")
        supply, _ = _file(monkeypatch, world, world.q4, dataset_id="ed-presentations",
                          collection_id="emergency-department")
        (opened_by,) = conn.execute('SELECT opened_by FROM "qa".period WHERE name = ?',
                                    [world.q4]).fetchone()
        ed = hierarchy.dataset("ed-presentations").collection_id
        assert opened_by == f"the filing of {supply} ({ed})"
        (made,) = entries(conn, world.q4, dl.INHERIT)
        assert made["supply"] == q2
        (caused,) = conn.execute(f"SELECT caused_by_supply FROM {dl.TABLE} WHERE id = ?",
                                 [made["id"]]).fetchone()
        assert caused == supply

