"""A table arriving in or leaving a period re-checks the supplies in that
period that read it, and re-applies the gate - through one mechanism
(REQ-PIPE-121). Owing against a real database; the run's logic with its
collaborators stood in; one end-to-end pass on the real Child Protection
fixture."""
from __future__ import annotations

import pytest

import test_supersession as _base
from qa_tools.common import (decision_log as dl, knock_on, promotion, qa_store, recheck,
                             rejection, supply_db)
from test_supersession import DS, REAL_PERSON, TABLE, WHEN, _filed

conn = _base.conn
period = _base.period

AG, COL = "child-protection-family-support", "child-protection"


def _owed_for(conn, period):
    return [o for o in recheck.owed(conn) if o.kind == recheck.REEVALUATE and o.period == period]


def _promote(conn, supply, table, period, *, kind=dl.RULE):
    promotion.promote(conn, agency_id=AG, collection_id=COL, dataset_id=DS, supply=supply,
                      period=period, physical_tables=[table],
                      actor="promotion rule" if kind == dl.RULE else REAL_PERSON,
                      actor_kind=kind, effective_at=WHEN, reason="because", status="green")


class TestWhatIsOwed:
    """Criteria 1, 8, 9 and 15."""

    def test_a_promotion_owes_one_re_evaluation_of_its_period(self, conn, period):
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period)
        (owed,) = _owed_for(conn, period)
        promote_id = conn.execute(f"SELECT id FROM {dl.TABLE} WHERE supply = ? AND action = "
                                  "'promote'", [a]).fetchall()[0][0]
        assert (owed.tables, owed.caused_by_decision) == ([TABLE], promote_id)

    def test_a_displacing_promotion_owes_one_not_two(self, conn, period):
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period)
        b, b_table = _filed(conn, period, "2026-06-01T01:00:00+00:00")
        _promote(conn, b, b_table, period, kind=dl.PERSON)
        latest = conn.execute(f"SELECT id FROM {dl.TABLE} WHERE supply = ? AND action = "
                              "'promote'", [b]).fetchall()[0][0]
        assert [o.caused_by_decision for o in _owed_for(conn, period)][-1] == latest
        assert len(_owed_for(conn, period)) == 2  # the first promotion's, and this one

    def test_a_departure_owes_too(self, conn, period):
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period)
        rejection.demote(conn, agency_id=AG, collection_id=COL, dataset_id=DS, supply=a,
                         from_slot=period, physical_tables=[TABLE], actor=REAL_PERSON,
                         effective_at=WHEN, reason="not yet")
        assert len(_owed_for(conn, period)) == 2

    def test_a_decision_that_moves_nothing_owes_nothing(self, conn, period):
        a, _ = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        with conn.raw.transaction():
            dl.record_automatic(conn, dl.Decision(
                agency_id=AG, collection_id=COL, dataset_id=DS,
                action=dl.PROMOTION_WITHHELD, supply=a, actor="rule",
                actor_kind=dl.RULE, effective_at=WHEN, to_slot=period, reason="r"))
        assert _owed_for(conn, period) == []

    def test_a_refused_decision_owes_nothing(self, conn, period):
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        with pytest.raises(Exception):
            with dl.decision_transaction(conn):
                with dl.apply_decision(conn, dl.Decision(
                        agency_id=AG, collection_id=COL, dataset_id=DS, action=dl.PROMOTE,
                        supply=a, actor=REAL_PERSON, actor_kind=dl.PERSON,
                        effective_at=WHEN, to_slot=period, reason="r")):
                    raise RuntimeError("the move failed")
        assert _owed_for(conn, period) == []


class FakeItem:
    id, period, tables, caused_by_decision, dataset_id, run_key = 1, "P", ["cp_carers"], 7, DS, None


class TestTheRun:
    """Criteria 2, 3, 6, 12 and 14, the collaborators stood in."""

    def _wire(self, monkeypatch, readers, *, refused=None, boom=False):
        ran, gated, cleared, failed, shouted = [], [], [], [], []
        monkeypatch.setattr(knock_on, "readers", lambda *a, **k: readers)
        monkeypatch.setattr(recheck, "mint_run_id", lambda *a, **k: "r__1")

        def execute(**kw):
            if boom:
                raise RuntimeError("tools fell over")
            ran.append(kw)
        monkeypatch.setattr(recheck, "execute", execute)

        def after_run(conn, **kw):
            item = kw["supplies"][0]
            gated.append(item["supply"])
            why = (refused or {}).get(item["supply"])
            return promotion.AfterRun(promoted=() if why else (item["dataset_id"],),
                                      refused={item["dataset_id"]: why} if why else {},
                                      failed={})
        monkeypatch.setattr(promotion, "after_run", after_run)
        monkeypatch.setattr(promotion, "report", lambda o: None)
        monkeypatch.setattr(recheck, "clear", lambda i, k: cleared.append(i))
        monkeypatch.setattr(recheck, "fail", lambda i, m: failed.append(m))
        monkeypatch.setattr(knock_on, "_shout", lambda conn, item, p, f, **k: shouted.append(f))
        return ran, gated, cleared, failed, shouted

    def test_only_stale_readers_run_and_only_waiting_ones_are_gated(self, monkeypatch, conn):
        rs = [knock_on.Reader("cp-placements", "cp-placements@1", True, {"cp_carers"}, True),
              knock_on.Reader("cp-clients", "cp-clients@1", True, {"cp_carers"}, False),
              knock_on.Reader("cp-notifications", "cp-notifications@1", False, {"cp_carers"},
                              True)]
        ran, gated, cleared, _f, shouted = self._wire(monkeypatch, rs)
        out = knock_on.complete(FakeItem())
        assert [r["supply_id"] for r in ran] == ["cp-placements@1", "cp-notifications@1"]
        assert all(r["purpose"]["scope"] == "readers" and r["purpose"]["caused_by_decision"] == 7
                   for r in ran)
        assert gated == ["cp-placements@1", "cp-clients@1"]
        assert cleared == [1] and out.completed and shouted == []

    def test_one_shout_for_every_waiting_supply_still_failing(self, monkeypatch, conn):
        rs = [knock_on.Reader("cp-placements", "cp-placements@1", True, {"cp_carers"}),
              knock_on.Reader("cp-clients", "cp-clients@1", True, {"cp_carers"})]
        red = "this supply's status is red rather than green or amber, so it waits for a person"
        _r, _g, _c, _f, shouted = self._wire(
            monkeypatch, rs, refused={"cp-placements@1": red, "cp-clients@1": red})
        knock_on.complete(FakeItem())
        assert len(shouted) == 1 and [s for _d, s, _w in shouted[0]] == [
            "cp-placements@1", "cp-clients@1"]

    def test_a_filled_slot_is_not_a_failure_to_shout_about(self, monkeypatch, conn):
        rs = [knock_on.Reader("cp-placements", "cp-placements@1", True, {"cp_carers"})]
        _r, _g, _c, _f, shouted = self._wire(
            monkeypatch, rs, refused={"cp-placements@1": "this supply's slot is already "
                                                         "filled by a promoted supply"})
        knock_on.complete(FakeItem())
        assert shouted == []

    def test_a_run_that_breaks_stays_owed_and_gates_nothing(self, monkeypatch, conn):
        rs = [knock_on.Reader("cp-placements", "cp-placements@1", True, {"cp_carers"}, True)]
        _r, gated, cleared, failed, _s = self._wire(monkeypatch, rs, boom=True)
        out = knock_on.complete(FakeItem())
        assert not out.completed and failed and cleared == [] and gated == []
        assert "still owed" in out.message


class TestTheShoutIsOneRecordNamingTheCause:
    """Criterion 12, against the real log."""

    def test_it(self, conn, period):
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period)
        cause = conn.execute(f"SELECT id FROM {dl.TABLE} WHERE supply = ? AND action = "
                             "'promote'", [a]).fetchall()[0][0]

        class Item:
            caused_by_decision, dataset_id = cause, DS
        with conn.raw.transaction():
            knock_on._shout(conn, Item(), period,
                            [("cp-placements", "cp-placements@1", "red"),
                             ("cp-clients", "cp-clients@1", "red")], effective_at=WHEN)
        (row,) = conn.execute(
            f"SELECT actor_kind, caused_by_decision, reason FROM {dl.TABLE} WHERE action = ? "
            "AND to_slot = ?", [dl.STILL_FAILING, period]).fetchall()
        assert row[:2] == (dl.RULE, cause)
        assert "2 waiting" in row[2] and "cp-placements@1" in row[2] and "cp-clients@1" in row[2]


class TestReadersOnlyRunsKeepOnlyTheReadingChecks:
    """Criterion 2, in the writer."""

    def test_the_scope(self, monkeypatch):
        from qa_tools.common import qa_results_writer as w

        monkeypatch.setattr(w, "_readers_scope", lambda run_id: ["cp_carers"])
        monkeypatch.setattr(w, "_readers_of", lambda tables, ds, run_id: {"keep-me"})
        in_scope = w.scope_of_run("cp_placements__202604010600000000__r1")
        assert in_scope("keep-me") and not in_scope("an-own-column-check")


class TestEndToEndOnTheRealFixture:
    """Criteria 1, 3 and 4: promoting carers re-gates the waiting placements
    supply that read it - without running its tools again, because the
    reading checks already read the very supply now promoted (NFR 4)."""

    def test_it(self, cp_duckdb_dir, monkeypatch):
        from fixture_ids import CP_DIRTY_RUN_ID
        from qa_tools.common import filing

        monkeypatch.setenv("GIT_AUTHOR_EMAIL", "pytest@example.org")
        monkeypatch.setattr(promotion, "report", lambda outcome: None)
        key = CP_DIRTY_RUN_ID.split("__")[1]
        placements = f"cp-placements@{key}"
        carers = f"cp-carers@{key}"
        with supply_db.connect(label="test-knock-on") as c:
            qa_store.ensure_schema(c)
            with c.raw.transaction():
                cause = dl.record_automatic(c, dl.Decision(
                    agency_id=AG, collection_id=COL, dataset_id="cp-placements",
                    action=dl.PROMOTION_WITHHELD, supply=placements, actor="pytest",
                    actor_kind=dl.RULE, effective_at=WHEN, to_slot="2026-Q2", reason="r"))
                owed_id = recheck.owe(c, dataset_id="cp-placements", supply_id=placements,
                                      decision_id=cause)
        assert recheck.run(owed_id, run_by="pytest@example.org").completed
        period = filing.period_of("cp-carers", filing.received_at_of("cp-carers", carers))
        with supply_db.connect(label="test-knock-on") as c:
            promotion.promote(c, agency_id=AG, collection_id=COL, dataset_id="cp-carers",
                              supply=carers, period=period,
                              physical_tables=[recheck.first_run_id("cp-carers", carers)],
                              actor=REAL_PERSON, actor_kind=dl.PERSON, effective_at=WHEN,
                              reason="in")
            touched = knock_on.readers(c, period, ["cp_carers"],
                                       promotion._declared_reads())
        mine = [r for r in touched if r.supply == placements]
        assert mine and not mine[0].stale
        done = knock_on.follow_up(COL, run_by="pytest@example.org")
        assert done and all(o.completed for o in done)
        with supply_db.connect(label="test-knock-on") as c:
            assert _owed_for(c, period) == []
