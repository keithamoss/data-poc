"""The dashboard build's half of REQ-PIPE-269, and post-build-review #262 R4:
which cross-table result counts toward the supply on show, on each date.

Driven through the real entry points - the writer records a small history,
the real rebuild writes the results file, and pipeline.build_dashboard_data
builds the pages from it - so what is asserted is what the page is given.
The page's lookup of these answers is tests-js/warehouse-counts.test.js.
"""
from __future__ import annotations

import uuid

import pytest

import rebuild_support
from pipeline import build_dashboard_data as bdd
from qa_tools.common import decision_log as dl, qa_results_writer, supply_db
from qa_tools.tools import results_history
from test_build_from_the_record import AGENCY, BY, CLIENT_REF, CP, _key, _record

KEYS = {"agency_id": AGENCY, "collection_id": CP}


@pytest.fixture
def build(clean_qa_history, tmp_path, monkeypatch):
    """Rebuild into tmp_path and build from there - never the real reports/."""
    monkeypatch.setattr(results_history, "ROOT", str(tmp_path))
    monkeypatch.setattr(bdd, "REPORTS", str(tmp_path / "reports"))

    def datasets():
        rebuild_support.rebuild(CP, tmp_path, monkeypatch)
        return {d["id"]: d for d in bdd.build_datasets(CP)}
    return datasets


def _run(run_id, *, dataset_id, supply, when, reads=None, results=(), scope="arrival",
         decision=None, period=None, stats=True):
    """One run opened, recorded and finished through the writer, at `when`.
    A readers-only re-check records no dataset_stats, as the knock-on's
    doesn't (`stats=False`)."""
    if reads is not None:
        with supply_db.connect(label="test-warehouse-counts") as conn:
            supply_db.ensure_schemas(conn)
            supply_db.record_resolution(conn, supply_db.Resolution(
                run_id=run_id, schema=supply_db.run_schema(run_id),
                resolved={t: f"{t}__x" for t in reads}, supply_of=dict(reads),
                source={t: "staging" for t in reads}))
    purpose = {"dataset_id": dataset_id, "supply_id": supply, "scope": scope,
               **({"caused_by_decision": decision} if decision else {}),
               **({"period": period, "reads_table": "cp_clients"} if scope == "readers" else {})}
    qa_results_writer.open_run(AGENCY, CP, run_id, when, BY, purpose=purpose)
    if stats:
        qa_results_writer.write_qa_result(
            AGENCY, CP, run_id, when, "dataset_stats",
            {"arrival_record": {"run_id": run_id, "received_at": when, "delivery": "d"},
             "row_counts": {}, "value_counts": {}, "check_aggregates": {}}, run_by=BY)
    if results:
        qa_results_writer.write_qa_result(AGENCY, CP, run_id, when, "dbt", {},
                                          verified=[dict(r, run_id=run_id) for r in results])
    qa_results_writer.finish_run(run_id)
    return run_id


def _decide(action, dataset_id, supply, period, at) -> int:
    with supply_db.connect(label="test-warehouse-counts") as conn:
        with dl.decision_transaction(conn):
            with dl.apply_decision(conn, dl.Decision(
                    **KEYS, dataset_id=dataset_id, action=action, supply=supply,
                    actor="promotion rule", actor_kind=dl.RULE, effective_at=at,
                    to_slot=period, reason="pytest", promoted_status="green")):
                pass
        return conn.execute(f"SELECT max(id) FROM {dl.TABLE}").fetchone()[0]


def _card(dataset: dict, check_id: str) -> dict:
    (card,) = [c for col in dataset["columns"] for c in col["checks"]
               if c.get("check_id") == check_id]
    return card


def _uid(prefix):
    return f"pytest_{prefix}_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def period():
    return f"2099-W{uuid.uuid4().hex[:6]}"


class TestAReadersOnlyReCheckIsPlaced:
    """A DEFECT FOUND BUILDING THIS (post-build-review #264): a readers-only
    re-check - the knock-on's - records no dataset_stats, so it was never in
    the results file's runs, and the build placed none of its results: a
    page went on showing the verdict the re-check had replaced."""

    def test_its_result_is_in_the_readers_page_history(self, build, period):
        c1, n1 = f"cp-clients@{_key()}", f"cp-notifications@{_key()}"
        _run(_uid("c"), dataset_id="cp-clients", supply=c1, when="2099-01-01T09:00:00+08:00")
        _run(_uid("n"), dataset_id="cp-notifications", supply=n1,
             when="2099-01-01T09:00:00+08:00",
             reads={"cp_clients": c1, "cp_notifications": n1},
             results=[_record(CLIENT_REF, "cp-notifications", "fail")])
        cause = _decide(dl.PROMOTE, "cp-clients", c1, period, "2099-01-02T09:00:00+08:00")
        recheck = _run(_uid("r"), dataset_id="cp-notifications", supply=n1,
                       when="2099-01-02T10:00:00+08:00", scope="readers", decision=cause,
                       period=period, stats=False,
                       reads={"cp_clients": c1, "cp_notifications": n1},
                       results=[_record(CLIENT_REF, "cp-notifications", "pass")])
        pages = build()
        for ds in ("cp-clients", "cp-notifications"):
            assert recheck in [h["run_id"] for h in _card(pages[ds], CLIENT_REF)["history"]], ds


class TestTheCountedPoints:

    def test_s4_the_clients_page_counts_the_verdict_beside_it_in_the_warehouse(self, build,
                                                                               period):
        """S4 on the page: Notifications v2's red, about Clients v1, is shown
        on Clients' page and never counted toward it - Notifications v2 was
        held back - so Clients v1's Client reference stays Notifications v1's
        green from the hold-back on."""
        c1, n1, n2 = (f"cp-clients@{_key()}", f"cp-notifications@{_key()}",
                      f"cp-notifications@{_key()}")
        _run(_uid("c"), dataset_id="cp-clients", supply=c1, when="2099-01-01T09:00:00+08:00")
        green = _run(_uid("n"), dataset_id="cp-notifications", supply=n1,
                     when="2099-01-01T09:00:00+08:00",
                     reads={"cp_clients": c1, "cp_notifications": n1},
                     results=[_record(CLIENT_REF, "cp-notifications", "pass")])
        _decide(dl.PROMOTE, "cp-clients", c1, period, "2099-01-01T10:00:00+08:00")
        _decide(dl.PROMOTE, "cp-notifications", n1, period, "2099-01-01T10:00:00+08:00")
        red = _run(_uid("n"), dataset_id="cp-notifications", supply=n2,
                   when="2099-01-05T09:00:00+08:00",
                   reads={"cp_clients": c1, "cp_notifications": n2},
                   results=[_record(CLIENT_REF, "cp-notifications", "fail")])
        card = _card(build()["cp-clients"], CLIENT_REF)
        ranks = {h["run_id"]: h["rank"] for h in card["history"]}
        assert red in ranks, "shown on the supply it describes"
        points = card["counted"][c1]
        assert ranks[red] not in [p["rank"] for p in points]
        assert [p for p in points if p["on"] <= "2099-01-06"][-1]["rank"] == ranks[green]

    def test_r4_a_late_reader_of_an_older_supply_never_counts_toward_the_newer(self, build,
                                                                               period):
        """R4's exact case, the build's half: Clients v2 replaces Clients v1
        in the warehouse; a Notifications run checked later read Clients v1.
        On Clients' page it is about v1 only - v2's answers never name it."""
        c1, c2 = f"cp-clients@{_key()}", f"cp-clients@{_key()}"
        n1, n_late = f"cp-notifications@{_key()}", f"cp-notifications@{_key()}"
        _run(_uid("c"), dataset_id="cp-clients", supply=c1, when="2099-02-01T09:00:00+08:00")
        _run(_uid("n"), dataset_id="cp-notifications", supply=n1,
             when="2099-02-01T09:00:00+08:00",
             reads={"cp_clients": c1, "cp_notifications": n1},
             results=[_record(CLIENT_REF, "cp-notifications", "pass")])
        _decide(dl.PROMOTE, "cp-clients", c1, period, "2099-02-01T10:00:00+08:00")
        _decide(dl.PROMOTE, "cp-notifications", n1, period, "2099-02-01T10:00:00+08:00")
        _run(_uid("c"), dataset_id="cp-clients", supply=c2, when="2099-02-10T09:00:00+08:00")
        beside = _run(_uid("n"), dataset_id="cp-clients", supply=c2,
                      when="2099-02-10T09:00:00+08:00",
                      reads={"cp_clients": c2, "cp_notifications": n1},
                      results=[_record(CLIENT_REF, "cp-notifications", "pass")])
        with supply_db.connect(label="test-warehouse-counts") as conn:
            with dl.decision_transaction(conn):
                with dl.apply_decision(conn, dl.Decision(
                        **KEYS, dataset_id="cp-clients", action=dl.PROMOTE, supply=c2,
                        actor="k@x", actor_kind=dl.PERSON, effective_at="2099-02-10T10:00:00+08:00",
                        to_slot=period, reason="the newer one", promoted_status="green")):
                    pass
        late = _run(_uid("n"), dataset_id="cp-notifications", supply=n_late,
                    when="2099-02-15T09:00:00+08:00",
                    reads={"cp_clients": c1, "cp_notifications": n_late},
                    results=[_record(CLIENT_REF, "cp-notifications", "fail")])
        card = _card(build()["cp-clients"], CLIENT_REF)
        ranks = {h["run_id"]: h["rank"] for h in card["history"]}
        assert {late, beside} <= set(ranks)
        assert ranks[late] not in [p["rank"] for p in card["counted"][c2]]
        assert card["counted"][c2][-1]["rank"] == ranks[beside]

    def test_a_late_reader_of_the_newer_supply_beside_a_waiting_partner_does_not_count(
            self, build, period):
        """R4 able to fail on the counting itself, not only on which supply an
        entry is grouped under (post-build-review #266 T6): a later result
        that DID read Clients v2 - beside a Notifications that is waiting,
        not in the warehouse - is the newest about v2 and is grouped under
        v2, so the R4 behaviour (the newest recorded result is the card's
        current) would show it. Counted, it is not: v2's current stays the
        verdict beside the Notifications in the warehouse."""
        c2, n1, n_waiting = (f"cp-clients@{_key()}", f"cp-notifications@{_key()}",
                             f"cp-notifications@{_key()}")
        _run(_uid("n"), dataset_id="cp-notifications", supply=n1,
             when="2099-03-01T09:00:00+08:00")
        _decide(dl.PROMOTE, "cp-notifications", n1, period, "2099-03-01T10:00:00+08:00")
        _run(_uid("c"), dataset_id="cp-clients", supply=c2, when="2099-03-02T09:00:00+08:00")
        beside = _run(_uid("c"), dataset_id="cp-clients", supply=c2,
                      when="2099-03-02T09:00:00+08:00",
                      reads={"cp_clients": c2, "cp_notifications": n1},
                      results=[_record(CLIENT_REF, "cp-notifications", "pass")])
        _decide(dl.PROMOTE, "cp-clients", c2, period, "2099-03-02T10:00:00+08:00")
        late = _run(_uid("n"), dataset_id="cp-notifications", supply=n_waiting,
                    when="2099-03-05T09:00:00+08:00",
                    reads={"cp_clients": c2, "cp_notifications": n_waiting},
                    results=[_record(CLIENT_REF, "cp-notifications", "fail")])
        card = _card(build()["cp-clients"], CLIENT_REF)
        by_run = {h["run_id"]: h for h in card["history"]}
        assert by_run[late]["supply_id"] == by_run[beside]["supply_id"] == c2
        assert by_run[late]["rank"] > by_run[beside]["rank"], "the late one is the newest"
        on_6th = [p for p in card["counted"][c2] if p["on"] <= "2099-03-06"][-1]
        assert on_6th["rank"] == by_run[beside]["rank"]


# ---------------------------------------------------------------------------
# The points themselves (post-build-review #266 T1), through points()
# ---------------------------------------------------------------------------

def _entry(run_id, rank, *, supply, reads, at, status="pass", not_evaluated=None):
    from qa_tools.common import qa_store
    return {"run_id": run_id, "rank": rank, "supply_id": supply, "read_state": qa_store.READ,
            "recorded_at": at, "status": status, "not_evaluated": not_evaluated,
            "reads": {t: {"state": qa_store.READ if s else qa_store.ABSENT, "supply_id": s}
                      for t, s in reads.items()}}


def _held(slot, holder, at, ds, held_as="promoted"):
    return {"at": at, "slot": slot, "held_as": held_as, "holder": holder, "_ds": ds}


def _timeline(*entries):
    from qa_tools.common import supply_status
    by_ds: dict = {}
    for e in entries:
        by_ds.setdefault(e.pop("_ds"), []).append(e)
    return supply_status.HoldingsTimeline(by_ds)


class TestThePointsThemselves:

    def test_a_could_not_run_counts_only_toward_the_table_that_asks(self):
        """Criterion 4 in the build: Placements' Client reference, recorded
        not evaluated for want of a Placements, read Clients v2 - on the
        Clients page it counts toward nothing, so its point says so."""
        from pipeline import warehouse_counts
        placements_ref = CLIENT_REF.replace(".cp-notifications.", ".cp-placements.")
        c2 = "cp-clients@1"
        history = [_entry("r1", 0, supply=c2, at="2099-03-01T09:00:00+08:00", status="fail",
                          not_evaluated="no Placements supply this run may read",
                          reads={"cp_clients": c2, "cp_placements": None})]
        got = warehouse_counts.points("cp-clients", placements_ref, history,
                                      warehouse=_timeline(), owed=None)
        assert got == {c2: [{"rank": None, "reason": warehouse_counts.NOT_COUNTED,
                             "on": "2099-03-01"}]}

    def test_owed_points_say_no_current_result_then_recheck_owed(self):
        """Clients v2's only Client reference read a Notifications that is
        never in the warehouse. Waiting, it counts (criterion 3); promoted
        beside Notifications v1 nothing counts and the owed check reads
        'no-current-result'; once Notifications v2's promotion owes a
        re-check that has not run, 'recheck-owed' naming it."""
        from pipeline import warehouse_counts
        from qa_tools.common import supply_status
        c2, n0 = "cp-clients@2", "cp-notifications@0"
        n1, n2 = "cp-notifications@1", "cp-notifications@2"
        history = [_entry("r1", 0, supply=c2, at="2099-03-01T09:00:00+08:00",
                          reads={"cp_clients": c2, "cp_notifications": n0})]
        warehouse = _timeline(
            _held("P", n1, "2099-02-01T10:00:00+08:00", "cp-notifications"),
            _held("P", c2, "2099-03-02T10:00:00+08:00", "cp-clients"),
            _held("P", n2, "2099-03-04T10:00:00+08:00", "cp-notifications"))
        cause_at = supply_status.instant("2099-03-04T10:00:00+08:00")
        owed = supply_status.Owing([("P", frozenset({"cp_notifications"}), 99, cause_at,
                                     None)])
        got = warehouse_counts.points("cp-clients", CLIENT_REF, history,
                                      warehouse=warehouse, owed=owed)
        assert got == {c2: [
            {"rank": 0, "reason": None, "on": "2099-03-01"},
            {"rank": None, "reason": supply_status.NO_CURRENT_RESULT, "owedBy": None,
             "owedSince": None, "on": "2099-03-02"},
            {"rank": None, "reason": supply_status.RECHECK_OWED, "owedBy": 99,
             "owedSince": cause_at.isoformat(), "on": "2099-03-04"}]}

    def test_a_later_green_in_one_period_does_not_hide_a_red_in_another(self):
        """Keith, Q3 = A (post-build-review #266 S5): Clients c1 is promoted
        into Q1 and inherited into Q2. Q2's Notifications read it red; a later
        result about Q1's Notifications reads it green. Counted per period,
        the card takes the worst - Q2's red stays the card's current."""
        from pipeline import warehouse_counts
        c1, n1, n2 = "cp-clients@1", "cp-notifications@1", "cp-notifications@2"
        history = [
            _entry("r_red", 0, supply=c1, at="2099-04-02T09:00:00+08:00", status="fail",
                   reads={"cp_clients": c1, "cp_notifications": n2}),
            _entry("r_green", 1, supply=c1, at="2099-04-03T09:00:00+08:00",
                   reads={"cp_clients": c1, "cp_notifications": n1})]
        warehouse = _timeline(
            _held("Q1", c1, "2099-04-01T10:00:00+08:00", "cp-clients"),
            _held("Q1", n1, "2099-04-01T10:00:00+08:00", "cp-notifications"),
            _held("Q2", c1, "2099-04-02T08:00:00+08:00", "cp-clients", held_as="inherited"),
            _held("Q2", n2, "2099-04-02T10:00:00+08:00", "cp-notifications"))
        got = warehouse_counts.points("cp-clients", CLIENT_REF, history,
                                      warehouse=warehouse, owed=None)
        assert got[c1][-1]["rank"] == 0, got


class TestOneClockForTheCardAndTheBadge:
    """Keith, Q4 = A (post-build-review #266 D2): a re-check's result counts
    from its run's recorded instant, and a re-check owed by a decision is
    owed from that decision until the run that cleared it - so a re-check
    that fails and is retried later reads 'recheck-owed' in between, on the
    card and on the red-promoted badge alike."""

    def test_a_failed_recheck_retried_later_is_owed_in_between(self, build, period):
        from pipeline import red_promoted
        from qa_tools.common import recheck, supply_status

        c1, c2, n1 = f"cp-clients@{_key()}", f"cp-clients@{_key()}", f"cp-notifications@{_key()}"
        _run(_uid("c"), dataset_id="cp-clients", supply=c1, when="2099-06-01T09:00:00+08:00")
        first = _run(_uid("n"), dataset_id="cp-notifications", supply=n1,
                     when="2099-06-01T09:00:00+08:00",
                     reads={"cp_clients": c1, "cp_notifications": n1},
                     results=[_record(CLIENT_REF, "cp-notifications", "pass")])
        _decide(dl.PROMOTE, "cp-clients", c1, period, "2099-06-01T10:00:00+08:00")
        _decide(dl.PROMOTE, "cp-notifications", n1, period, "2099-06-01T10:00:00+08:00")
        with supply_db.connect(label="test-warehouse-counts") as conn:
            earlier = [o.id for o in recheck.owed(conn) if o.period == period]
        for owed_id in earlier:
            recheck.clear(owed_id, "pytest/earlier")
        _run(_uid("c"), dataset_id="cp-clients", supply=c2, when="2099-06-03T09:00:00+08:00")
        with supply_db.connect(label="test-warehouse-counts") as conn:
            with dl.decision_transaction(conn):
                with dl.apply_decision(conn, dl.Decision(
                        **KEYS, dataset_id="cp-clients", action=dl.PROMOTE, supply=c2,
                        actor="k@x", actor_kind=dl.PERSON,
                        effective_at="2099-06-03T10:00:00+08:00", to_slot=period,
                        reason="the newer one", promoted_status="green")):
                    pass
            cause = conn.execute(f"SELECT max(id) FROM {dl.TABLE}").fetchone()[0]
            (owed,) = [o for o in recheck.owed(conn) if o.period == period]
        recheck.fail(owed.id, "RuntimeError: made to fail")
        retry = _run(_uid("r"), dataset_id="cp-notifications", supply=n1,
                     when="2099-06-06T10:00:00+08:00", scope="readers", decision=cause,
                     period=period, stats=False,
                     reads={"cp_clients": c2, "cp_notifications": n1},
                     results=[_record(CLIENT_REF, "cp-notifications", "pass")])
        recheck.clear(owed.id, retry)

        card = _card(build()["cp-notifications"], CLIENT_REF)
        ranks = {h["run_id"]: h["rank"] for h in card["history"]}
        points = card["counted"][n1]

        def card_on(day):
            p = [p for p in points if p["on"] <= day][-1]
            if p["rank"] is None:
                return p["reason"]
            return {ranks[first]: "first", ranks[retry]: "retry"}[p["rank"]]

        assert [card_on(f"2099-06-0{d}") for d in range(1, 8)] == [
            "first", "first", supply_status.RECHECK_OWED, supply_status.RECHECK_OWED,
            supply_status.RECHECK_OWED, "retry", "retry"]
        health = red_promoted.for_dataset("cp-notifications")
        (n1_run,) = [run for run in health if run == first]
        badge = [red_promoted.status_on(health[n1_run], f"2099-06-0{d}") for d in range(1, 8)]
        card = ["green" if c in ("first", "retry") else "red"
                for c in (card_on(f"2099-06-0{d}") for d in range(1, 8))]
        assert badge == card


class TestTheBuildAgreesWithResultsAboutOnTheDeployment:
    """REQ-PIPE-269 criterion 7 as Keith agreed it (post-build-review #266
    S1, Q2 = A): the dashboard build shares the counting RULE
    (supply_status.count), not results_about's query, so the two are held to
    one answer here on the deployment's real history - a deterministic
    sample of Child Protection's cross-table cards and supplies, at each
    date the build says the answer changed and the day before the first.

    WITH NO EXCEPTIONS. It left one case out until Keith's answer A
    (post-build-review #266, 2026-10-24): a page carried each supply's
    CURRENT run only, so between an arrival and its full re-check
    results_about counted the arrival's result while the card had nothing.
    The card now carries its superseded runs' entries (`superseded`), which
    the build counts from and the page shows while they are current."""

    def test_a_sample_of_supplies_and_dates(self, deployment_history, tmp_path, monkeypatch):
        import random
        from datetime import date, timedelta

        from pipeline import warehouse_counts
        from qa_tools.common import asset_time, supply_status

        monkeypatch.setattr(results_history, "ROOT", str(tmp_path))
        monkeypatch.setattr(bdd, "REPORTS", str(tmp_path / "reports"))
        results_history.build_results_from_history(CP)
        pages = bdd.build_datasets(CP)
        pairs = [(page["id"], card, supply)
                 for page in pages for col in page["columns"] for card in col["checks"]
                 for supply in sorted(card.get("counted") or {})]
        assert len(pairs) > 100, "precondition: the deployment has counted cross-table cards"
        sample = random.Random(266).sample(pairs, 120)
        compared = 0
        with supply_db.connect(read_only=True, label="test-warehouse-counts") as conn:
            for dataset_id, card, supply in sample:
                points = card["counted"][supply]
                by_rank = {h["rank"]: h for h in [*card["history"], *card.get("superseded", [])]}
                days = [p["on"] for p in points]
                days = sorted({(date.fromisoformat(days[0]) - timedelta(days=1)).isoformat(),
                               *random.Random(supply).sample(days, min(4, len(days)))})
                for day in days:
                    built = [p for p in points if p["on"] <= day]
                    view = supply_status.View(
                        as_at=asset_time.end_of_day(date.fromisoformat(day)))
                    mine = [r for r in supply_status.results_about(
                        conn, dataset_id, supply, view=view).counted
                        if r["check_id"] == card["check_id"]]
                    where = f"{card['check_id']} toward {supply} on {day}"
                    if not built or built[-1]["reason"] == warehouse_counts.NOT_COUNTED:
                        assert not mine, where
                    elif built[-1]["rank"] is None:
                        assert mine and (mine[-1].get("warehouse_reason"),
                                         mine[-1].get("owed_by_decision")) == (
                            built[-1]["reason"], built[-1].get("owedBy")), where
                    else:
                        assert mine and not mine[-1].get("warehouse_reason"), where
                        assert mine[-1]["run_id"] == by_rank[built[-1]["rank"]]["run_id"], where
                    compared += 1
        assert compared >= 250, compared


class TestOwedEndsAtTheClearingRun:

    def test_a_clearing_run_that_recorded_nothing_here_still_ends_the_owed_red(self):
        """Found by the agreement test on the deployment (post-build-review
        #266): the run that clears a re-check need record nothing on this
        card, and the card asked only at results and warehouse changes - so
        it read 'recheck-owed' past the clearing while results_about read
        'no-current-result'."""
        from pipeline import warehouse_counts
        from qa_tools.common import supply_status
        c2, n0, n1 = "cp-clients@2", "cp-notifications@0", "cp-notifications@1"
        history = [_entry("r1", 0, supply=c2, at="2099-07-01T09:00:00+08:00",
                          reads={"cp_clients": c2, "cp_notifications": n0})]
        warehouse = _timeline(
            _held("P", n1, "2099-06-01T10:00:00+08:00", "cp-notifications"),
            _held("P", c2, "2099-07-02T10:00:00+08:00", "cp-clients"))
        cause = supply_status.instant("2099-07-02T10:00:00+08:00")
        cleared = supply_status.instant("2099-07-04T10:00:00+08:00")
        owed = supply_status.Owing([("P", frozenset({"cp_clients"}), 7, cause, cleared)],
                                   ["elsewhere"])
        got = warehouse_counts.points("cp-clients", CLIENT_REF, history,
                                      warehouse=warehouse, owed=owed)
        assert [(p["on"], p["reason"]) for p in got[c2]] == [
            ("2099-07-01", None), ("2099-07-02", supply_status.RECHECK_OWED),
            ("2099-07-04", supply_status.NO_CURRENT_RESULT)]
