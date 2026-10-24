"""The dashboard build places and orders results by what was recorded,
never by what a run id, a day or a recording time suggests (REQ-PIPE-279
criteria 16 to 19 and 24, the build's half).

Two layers, each driven through its real entry point:

  - the results file (qa_tools/tools/results_history.build_results_from_history,
    the one path both the rebuild and the live batch write it by): for every
    run, its dataset, scope, supply, cause and a dense rank from run_seq
    within the collection - never run_seq itself - and, on each cross-table
    result, the reads qa.check_read recorded;
  - the build (pipeline/build_dashboard_data), which reads only that file:
    whose run a result was, what kind, which own run it read, where it is
    shared and which is newest - all from those facts.
"""
from __future__ import annotations

import json
import random
import uuid

import pytest

import rebuild_support
from pipeline import build_dashboard_data as bdd
from qa_tools import collections
from qa_tools.common import hierarchy, qa_results_writer, qa_store, supply_db
from qa_tools.tools import results_history

CP = "child-protection"
AGENCY = "child-protection-family-support"
CHECK = f"data-asset-1.{AGENCY}.{CP}"
CLIENT_REF = f"{CHECK}.cp-notifications.cp_client_id.relationships_dbt"
WORKER_REF = f"{CHECK}.cp-notifications.assigned_worker_id.relationships_dbt"
WHEN = "2026-09-26T10:00:00+08:00"
BY = "tests@example.gov.au"


def _key() -> str:
    return "2099" + "".join(random.choice("0123456789") for _ in range(14))


def _record(check_id: str, dataset_id: str, status: str = "pass", **extra) -> dict:
    return {"check_id": check_id, "check_name": "dbt:relationships", "dataset_id": dataset_id,
            "status": status, "engine": "dbt-core 1.12 + dbt-postgres", "column_name": "x",
            "metric_value": 0.0 if status == "pass" else 3.0, "unit": "rows",
            "warn_threshold": None, "fail_threshold": 0.0, "dimension": "consistency",
            "label": None, "row_count_total": 10, "row_count_invalid": 0, **extra}


def _run(run_id: str, *, dataset_id, supply, scope="arrival", decision=None, results=(),
         reads=None, absent=(), held=None, contested=None,
         received_at="2099-01-01T01:00:00+00:00", collection=CP, agency=AGENCY):
    """One run opened, recorded and finished through the writer - a resolution
    first where it records a cross-table result, as the overlay does: `reads`
    the tables it read, `absent` those it had none of, `held` {table: supply}."""
    if reads is not None:
        with supply_db.connect(label="test-build-record") as conn:
            supply_db.ensure_schemas(conn)
            supply_db.record_resolution(conn, supply_db.Resolution(
                run_id=run_id, schema=supply_db.run_schema(run_id),
                resolved={t: f"{t}__x" for t in reads},
                supply_of=dict(reads), source={t: "staging" for t in reads},
                absent=[*absent, *(contested or {})],
                ambiguous={t: list(files) for t, files in (contested or {}).items()},
                held={t: f"{t}__held" for t in (held or {})},
                held_supply=dict(held or {})))
    purpose = {"dataset_id": dataset_id, "supply_id": supply, "scope": scope,
               **({"caused_by_decision": decision} if decision else {})}
    qa_results_writer.open_run(agency, collection, run_id, WHEN, BY, purpose=purpose)
    qa_results_writer.write_qa_result(
        agency, collection, run_id, WHEN, "dataset_stats",
        {"arrival_record": {"run_id": run_id, "received_at": received_at, "delivery": "d"},
         "row_counts": {}, "value_counts": {}, "check_aggregates": {}}, run_by=BY)
    if results:
        qa_results_writer.write_qa_result(agency, collection, run_id, WHEN, "dbt", {},
                                          verified=[dict(r, run_id=run_id) for r in results])
    qa_results_writer.finish_run(run_id)
    return run_id


@pytest.fixture
def history(clean_qa_history, tmp_path, monkeypatch):
    """Rebuild into tmp_path and build from there - never the real reports/."""
    monkeypatch.setattr(results_history, "ROOT", str(tmp_path))
    monkeypatch.setattr(bdd, "REPORTS", str(tmp_path / "reports"))

    class History:
        conn = clean_qa_history

        @staticmethod
        def rebuild(collection_id=CP):
            return rebuild_support.rebuild(collection_id, tmp_path, monkeypatch)

        @staticmethod
        def datasets(collection_id=CP):
            rebuild_support.rebuild(collection_id, tmp_path, monkeypatch)
            return {d["id"]: d for d in bdd.build_datasets(collection_id)}

    return History


def _history_of(dataset: dict, check_id: str) -> list[dict]:
    (card,) = [c for col in dataset["columns"] for c in col["checks"]
               if c.get("check_id") == check_id]
    return card["history"]


class TestTheResultsFileCarriesTheRecord:
    """Criterion 16's source: what the build reads, written from qa.run."""

    def test_each_run_says_its_dataset_scope_supply_and_dense_rank(self, history):
        supply = f"cp-clients@{_key()}"
        a = _run(f"pytest_a_{uuid.uuid4().hex[:8]}", dataset_id="cp-clients", supply=supply)
        b = _run(f"pytest_b_{uuid.uuid4().hex[:8]}", dataset_id="cp-clients", supply=supply,
                 scope="full", decision=7)
        facts = history.rebuild()["run_facts"]
        assert facts[a] == {"dataset_id": "cp-clients", "scope": "arrival", "supply_id": supply,
                            "rank": 1, "cause": f"arrival:{a}"}
        assert facts[b] == {"dataset_id": "cp-clients", "scope": "full", "supply_id": supply,
                            "rank": 2, "cause": "decision:7"}
        assert "run_seq" not in json.dumps(history.rebuild())

    def test_a_cross_table_result_carries_what_it_read(self, history):
        clients, notifications = f"cp-clients@{_key()}", f"cp-notifications@{_key()}"
        run_id = _run(f"cp_notifications__{_key()}", dataset_id="cp-notifications",
                      supply=notifications, results=[_record(CLIENT_REF, "cp-notifications")],
                      reads={"cp_clients": clients, "cp_notifications": notifications})
        (got,) = [r for r in history.rebuild()["results"] if r["run_id"] == run_id]
        assert got["reads"] == {
            "cp_clients": {"state": qa_store.READ, "supply_id": clients, "contested": False,
                           "contested_files": []},
            "cp_notifications": {"state": qa_store.READ, "supply_id": notifications,
                                 "contested": False, "contested_files": []}}

    def test_the_runs_come_in_rank_order_not_run_index(self, history):
        first = _run(f"pytest_z_{uuid.uuid4().hex[:8]}", dataset_id="cp-clients",
                     supply=f"cp-clients@{_key()}")
        second = _run(f"pytest_a_{uuid.uuid4().hex[:8]}", dataset_id="cp-clients",
                      supply=f"cp-clients@{_key()}")
        with supply_db.connect(label="test-build-record") as conn:
            # The arrival records disagree with the order the runs were opened.
            for run_id, index in ((first, 2), (second, 1)):
                conn.execute(
                    f'UPDATE "{qa_store.SCHEMA}".dataset_stats SET stats = jsonb_set(stats, '
                    "'{arrival_record,run_index}', to_jsonb(?::int)) WHERE run_key = ?",
                    [index, run_id])
        assert [r["run_id"] for r in history.rebuild()["runs"]] == [first, second]


class TestWhoseRunAndWhatKindComeFromTheRun:
    """Criterion 17: qa.run's dataset_id and scope, never the run id."""

    def test_a_run_is_its_recorded_datasets_whatever_its_id_says(self, history):
        supply = f"cp-notifications@{_key()}"
        # Named for cp_clients, recorded for cp-notifications.
        run_id = _run(f"cp_clients__{_key()}", dataset_id="cp-notifications", supply=supply,
                      results=[_record(f"{CHECK}.cp-notifications.notification_id.not_null_dbt",
                                       "cp-notifications")])
        pages = history.datasets()
        assert run_id in {r["run_id"] for r in pages["cp-notifications"]["runs"]}
        assert run_id not in {r["run_id"] for r in pages["cp-clients"]["runs"]}

    def test_another_tables_run_is_named_by_its_dataset_and_kind_from_the_record(self, history):
        clients, notifications = f"cp-clients@{_key()}", f"cp-notifications@{_key()}"
        _run(f"cp_notifications__{_key()}", dataset_id="cp-notifications",
             supply=notifications, results=[_record(CLIENT_REF, "cp-notifications", "fail")],
             reads={"cp_clients": clients, "cp_notifications": notifications})
        # A re-check whose id names the Client Register's table and carries no
        # rerun mark, recorded as a re-check of a Case Workers supply.
        recheck = _run(f"cp_clients__{_key()}", dataset_id="cp-case-workers",
                       supply=f"cp-case-workers@{_key()}", scope="full", decision=9,
                       results=[_record(CLIENT_REF, "cp-notifications")],
                       reads={"cp_clients": clients, "cp_notifications": notifications})
        entry = {h["run_id"]: h for h in _history_of(history.datasets()["cp-notifications"],
                                                     CLIENT_REF)}[recheck]
        assert (entry["recorded_by"], entry["recorded_in"]) == ("cp-case-workers", "re-check")


class TestWhichOwnRunAResultReadIsItsRecordedSupply:
    """Criterion 19: read_run's stamp inference goes; the own run is the one
    whose supply the result recorded reading."""

    def test_a_result_is_placed_on_the_own_run_of_the_supply_it_read(self, history):
        older, newer = f"cp-clients@{_key()}", f"cp-clients@{_key()}"
        notifications = f"cp-notifications@{_key()}"
        key = _key()
        read = _run(f"cp_clients__{key}", dataset_id="cp-clients", supply=older)
        # Same instant in its id as a later Clients run that is NOT the one read.
        _run(f"cp_clients__{key}__1", dataset_id="cp-clients", supply=newer)
        elsewhere = _run(f"cp_notifications__{key}", dataset_id="cp-notifications",
                         supply=notifications,
                         results=[_record(CLIENT_REF, "cp-notifications", "fail")],
                         reads={"cp_clients": older, "cp_notifications": notifications})
        entry = {h["run_id"]: h for h in _history_of(history.datasets()["cp-clients"],
                                                     CLIENT_REF)}[elsewhere]
        assert entry["read_run"] == read
        assert entry["supply_id"] == older


class TestTheNewestIsTheHighestRank:
    """Criteria 16 and 19: entries in rank order, the current value the
    highest rank's - never the latest recording time."""

    def test_a_later_opened_result_recorded_earlier_is_current_and_last(self, history):
        clients, notifications = f"cp-clients@{_key()}", f"cp-notifications@{_key()}"
        own = _run(f"cp_notifications__{_key()}", dataset_id="cp-notifications",
                   supply=notifications, results=[_record(CLIENT_REF, "cp-notifications", "fail")],
                   reads={"cp_clients": clients, "cp_notifications": notifications})
        later = _run(f"cp_clients__{_key()}", dataset_id="cp-clients", supply=clients,
                     results=[_record(CLIENT_REF, "cp-notifications")],
                     reads={"cp_clients": clients, "cp_notifications": notifications})
        with supply_db.connect(label="test-build-record") as conn:
            # Recorded EARLIER than the own run, by its timestamp.
            conn.execute(f'UPDATE "{qa_store.SCHEMA}".run SET run_timestamp = ? '
                         "WHERE run_key = ?", ["2026-01-01T00:00:00+08:00", later])
        pages = history.datasets()
        (card,) = [c for col in pages["cp-notifications"]["columns"] for c in col["checks"]
                   if c.get("check_id") == CLIENT_REF]
        assert [h["run_id"] for h in card["history"]] == [own, later]
        assert [h["rank"] for h in card["history"]] == sorted(h["rank"] for h in card["history"])
        assert card["current_status"] == "green"


class TestEachRunOnThePageCarriesItsRank:
    """post-build-review #262 F5: the supply history orders a dataset's runs
    by rank, so each run the page is given says its rank."""

    def test_each_run_says_its_rank(self, history):
        first = _run(f"cp_clients__{_key()}", dataset_id="cp-clients",
                     supply=f"cp-clients@{_key()}")
        second = _run(f"cp_clients__{_key()}", dataset_id="cp-clients",
                      supply=f"cp-clients@{_key()}")
        runs = {r["run_id"]: r for r in history.datasets()["cp-clients"]["runs"]}
        assert runs[first]["rank"] < runs[second]["rank"]


class TestSharedToTheTablesItRecordedReading:
    """Criterion 18: not the checkout's current declarations."""

    def test_a_result_reaches_the_pages_of_the_tables_it_read(self, history, monkeypatch):
        workers, notifications = f"cp-case-workers@{_key()}", f"cp-notifications@{_key()}"
        run_id = _run(f"cp_notifications__{_key()}", dataset_id="cp-notifications",
                      supply=notifications,
                      results=[_record(WORKER_REF, "cp-notifications", "fail")],
                      reads={"cp_case_workers": workers, "cp_notifications": notifications})
        history.rebuild()
        # A LATER CHECKOUT says the check reads the Client Register instead.
        from qa_tools.common import tables_read

        real = tables_read.declared_by_check_id

        def edited(checks):
            got = real(checks)
            got[WORKER_REF] = ["cp_clients"]
            return got

        monkeypatch.setattr(tables_read, "declared_by_check_id", edited)
        pages = {d["id"]: d for d in bdd.build_datasets(CP)}
        assert run_id in {h["run_id"] for h in _history_of(pages["cp-case-workers"], WORKER_REF)}
        assert not [c for col in pages["cp-clients"]["columns"] for c in col["checks"]
                    if c.get("check_id") == WORKER_REF]


class TestEveryHistoryEntryHasARank:
    """Criterion 16: "a dense rank for every point and every history entry" -
    the placeholder history of a column with no rule included. Found by the
    gate (TestColumnsNotGreenMatchesTheDatasetPage, 2026-10-23): unranked
    placeholder entries among ranked ones scrambled the page's point order."""

    def test_a_column_with_no_rule_has_ranked_entries_too(self, history):
        _run(f"cp_notifications__{_key()}", dataset_id="cp-notifications",
             supply=f"cp-notifications@{_key()}",
             results=[_record(f"{CHECK}.cp-notifications.notification_id.not_null_dbt",
                              "cp-notifications", column_name="notification_id")])
        page = history.datasets()["cp-notifications"]
        placeholders = [h for col in page["columns"] for c in col["checks"]
                        if c["key"] == "no_rule_defined" for h in c["history"]]
        assert placeholders, "precondition: a column of Notifications has no rule"
        assert all(isinstance(h.get("rank"), int) and h.get("supply_id") and h.get("cause")
                   for h in placeholders), placeholders[:2]


class TestAResultThatReadNoSupplyOfATableIsNotOnItsPage:
    """Criterion 14 (K2 = A), decided where a result is shared to a page."""

    def test_absent_clients_keeps_it_off_the_client_registers_page(self, history):
        notifications = f"cp-notifications@{_key()}"
        run_id = _run(f"cp_notifications__{_key()}", dataset_id="cp-notifications",
                      supply=notifications, results=[_record(CLIENT_REF, "cp-notifications", "fail")],
                      reads={"cp_notifications": notifications}, absent=("cp_clients",))
        pages = history.datasets()
        assert run_id in {h["run_id"] for h in _history_of(pages["cp-notifications"], CLIENT_REF)}
        assert not [c for col in pages["cp-clients"]["columns"] for c in col["checks"]
                    if c.get("check_id") == CLIENT_REF]


class TestAContestedPairsReadsReachItsPage:
    """REQ-DASH-264 criterion 3's "held or contested", kept where REQ-PIPE-279
    criteria 14 and 15 left a gap (PROVISIONAL, 2026-10-23, for Keith): a
    reader's ABSENT read of a table two files claim is about that pair, so it
    reaches the pair's page - apart from the history, for the page to show
    only while that pair blocks it. Every other ABSENT read stays off."""

    def test_it_is_on_the_tables_page_as_a_contested_read_not_in_the_history(self, history):
        notifications = f"cp-notifications@{_key()}"
        pair = [f"cp_clients__{_key()}__1", f"cp_clients__{_key()}__2"]
        # AN EARLIER QUARTER'S READ, as TS-80's rows have: the card is there.
        earlier = _run(f"cp_notifications__{_key()}", dataset_id="cp-notifications",
                       supply=f"cp-notifications@{_key()}",
                       results=[_record(CLIENT_REF, "cp-notifications")],
                       reads={"cp_notifications": f"cp-notifications@{_key()}",
                              "cp_clients": f"cp-clients@{_key()}"})
        run_id = _run(f"cp_notifications__{_key()}", dataset_id="cp-notifications",
                      supply=notifications, results=[_record(CLIENT_REF, "cp-notifications", "fail")],
                      reads={"cp_notifications": notifications}, contested={"cp_clients": pair})
        (card,) = [c for col in history.datasets()["cp-clients"]["columns"] for c in col["checks"]
                   if c.get("check_id") == CLIENT_REF]
        assert [h["run_id"] for h in card["history"]] == [earlier]
        (read,) = card["contested_reads"]
        assert (read["run_id"], read["contested_files"], read["status"]) == (
            run_id, sorted(pair), "red")


    def test_a_check_whose_only_result_there_is_a_contested_read_still_gets_a_card(self, history):
        """Keith, 2026-10-24, reversing provisional #22: its red shows on the
        blocked row rather than the card being dropped. The card sits in its
        column's `contested_only`, never `checks`, so no count, status or
        history ever holds it (criterion 14)."""
        notifications = f"cp-notifications@{_key()}"
        pair = [f"cp_clients__{_key()}__1", f"cp_clients__{_key()}__2"]
        run_id = _run(f"cp_notifications__{_key()}", dataset_id="cp-notifications",
                      supply=notifications, results=[_record(CLIENT_REF, "cp-notifications", "fail")],
                      reads={"cp_notifications": notifications}, contested={"cp_clients": pair})
        columns = history.datasets()["cp-clients"]["columns"]
        assert not [c for col in columns for c in col["checks"] if c.get("check_id") == CLIENT_REF]
        (card,) = [c for col in columns for c in col.get("contested_only", [])
                   if c.get("check_id") == CLIENT_REF]
        assert card["history"] == []
        (read,) = card["contested_reads"]
        assert (read["run_id"], read["contested_files"], read["status"]) == (
            run_id, sorted(pair), "red")


class TestAHeldReadNamesTheHeldSupply:
    """Criterion 15: the page matches a held table's rows on the held supply."""

    def test_the_entry_carries_the_held_supply_and_its_state(self, history):
        held, notifications = f"cp-clients@{_key()}", f"cp-notifications@{_key()}"
        run_id = _run(f"cp_notifications__{_key()}", dataset_id="cp-notifications",
                      supply=notifications, results=[_record(CLIENT_REF, "cp-notifications", "fail")],
                      reads={"cp_notifications": notifications}, held={"cp_clients": held})
        (entry,) = [h for h in _history_of(history.datasets()["cp-clients"], CLIENT_REF)
                    if h["run_id"] == run_id]
        assert (entry["supply_id"], entry["read_state"]) == (held, qa_store.HELD)


class TestTheSameHistoryBuildsTheSameBytes:
    """Criterion 24: another collection's runs interleaved differently move
    run_seq and nothing the build emits."""

    def _build(self, history, interleave: bool, keys: dict) -> str:
        coll = collections.by_id("civil-registration")
        if interleave:
            _run(f"pytest_bdm_{uuid.uuid4().hex[:8]}", dataset_id=None, supply=None,
                 collection=coll.id, agency=coll.agency_id)
        for name in ("one", "two"):
            _run(keys[name], dataset_id="cp-clients", supply=keys[f"{name}_supply"],
                 results=[_record(f"{CHECK}.cp-clients.cp_client_id.unique_dbt", "cp-clients",
                                  column_name="cp_client_id")])
            if interleave:
                _run(f"pytest_bdm_{uuid.uuid4().hex[:8]}", dataset_id=None, supply=None,
                     collection=coll.id, agency=coll.agency_id)
        datasets = history.datasets()
        return json.dumps(datasets["cp-clients"], sort_keys=True, default=str)

    def test_interleaving_another_collection_changes_no_byte(self, history):
        keys = {"one": f"pytest_one_{uuid.uuid4().hex[:8]}",
                "two": f"pytest_two_{uuid.uuid4().hex[:8]}",
                "one_supply": f"cp-clients@{_key()}", "two_supply": f"cp-clients@{_key()}"}
        plain = self._build(history, False, keys)
        assert '"rank": 1' in plain and '"rank": 2' in plain, "no rank was emitted"
        with supply_db.connect(label="test-build-record") as conn:
            conn.execute(f'TRUNCATE "{qa_store.SCHEMA}".run, "{qa_store.SCHEMA}".run_attempt '
                         "CASCADE")
        assert self._build(history, True, keys) == plain


def test_hierarchy_knows_the_tables_these_use():
    for table in ("cp_clients", "cp_notifications", "cp_case_workers"):
        hierarchy.dataset_for_table(table)
