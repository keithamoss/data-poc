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
