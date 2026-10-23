"""Which results are about a supply, and which of two is newer, from what
each result recorded reading (REQ-PIPE-279 criteria 9, 21 and 22).

  - ONE FUNCTION, supply_status.results_about, answers "which results are
    about this supply" for the promotion gate (latest_results, status) and
    the dashboard build (red_promoted) alike, from qa.check_read and the
    run's own supply - never from a run-level record of physical names;
  - newer is the later-OPENED run (qa.run.run_seq), never the later
    effective time, receipt or run instant;
  - REQ-PIPE-265's siblings are the arrival runs whose supplies were filed
    from one delivery with one receipt instant, read from qa.filing and
    qa.delivery_file - never parsed out of run ids - and a check is carried
    from one only where its recorded reads name the supplies this run reads.

Against this worker's own database, written as the pipeline writes it:
record_results with the reads the writer works out, opened and completed.
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone

import pytest

import attempt_support
from qa_tools.common import carried, filing, promotion, qa_store, supply_db, supply_status

CHECK = "data-asset-1.child-protection-family-support.child-protection"
CLIENT_REF = f"{CHECK}.cp-notifications.cp_client_id.relationships_dbt"
CLIENTS_OWN = f"{CHECK}.cp-clients.cp_client_id.unique_dbt"
KEYS = {"agency_id": "child-protection-family-support", "collection_id": "child-protection"}


def _key() -> str:
    return "2099" + "".join(random.choice("0123456789") for _ in range(14))


@pytest.fixture(autouse=True)
def _real_checks():
    reads = promotion._declared_reads()
    assert reads.get(CLIENT_REF) == ["cp_clients"], "the Client reference check has moved"
    assert CLIENTS_OWN not in reads, "the Client Register's own check now reads another table"


@pytest.fixture
def conn(clean_qa_history):
    supply_db.ensure_schemas(clean_qa_history)
    yield clean_qa_history


def _result(check_id: str, dataset_id: str, status: str) -> dict:
    return {"check_id": check_id, "check_name": check_id.rsplit(".", 1)[-1],
            "dataset_id": dataset_id, "status": status}


def _run(conn, key: str, *, dataset_id: str, supply: str | None, at: str,
         scope: str = "arrival", own=(), cross=(), physical: dict | None = None,
         decision: int | None = None) -> str:
    """A completed run, opened when this is called: `own` its single-table
    results, `cross` (result, reads) pairs recorded under the cross-table
    scope, `physical` its run-level tables_read."""
    qa_store.record_run(conn, run_key=key, run_timestamp=at, run_by="t@x",
                        environment="test", **KEYS)
    qa_store.set_run_purpose(conn, key, dataset_id=dataset_id, supply_id=supply, scope=scope,
                             caused_by_decision=decision)
    if own:
        qa_store.record_results(conn, key, list(own), tool="dbt", **KEYS)
    if cross:
        qa_store.record_results(conn, key, [r for r, _ in cross], tool="dbt", **KEYS,
                                scope=qa_store.CROSS_TABLE_SCOPE,
                                reads=[reads for _, reads in cross])
    if physical:
        qa_store.record_tables_read(conn, key, {t: p for t, (p, _s) in physical.items()},
                                    {t: s for t, (_p, s) in physical.items() if s})
    attempt_support.opened(conn, key)
    qa_store.complete_run(conn, key)
    return key


def _read(table: str, supply: str | None, state: str = qa_store.READ) -> qa_store.CheckRead:
    return qa_store.CheckRead(table, state, supply)


def _newest(conn, dataset_id: str, supply: str, check: str) -> dict:
    (found,) = [r for r in supply_status.latest_results(conn, dataset_id, supply)
                if r["check_id"] == check]
    return found


class TestNewerIsTheLaterOpenedRun:
    """Criterion 9: run_seq, replacing the gate's effective-time order."""

    def test_the_later_opened_run_wins_over_a_later_receipt(self, conn):
        supply = f"cp-clients@{_key()}"
        table = {"cp_clients": (f"cp_clients__{supply.split('@')[1]}", supply)}
        first = _run(conn, f"pytest-ra-{uuid.uuid4().hex[:8]}", dataset_id="cp-clients",
                     supply=supply, at="2099-01-07T09:00:00+08:00", physical=table,
                     own=[_result(CLIENTS_OWN, "cp-clients", "fail")])
        second = _run(conn, f"pytest-ra-{uuid.uuid4().hex[:8]}", dataset_id="cp-clients",
                      supply=supply, at="2099-01-05T09:00:00+08:00", physical=table,
                      own=[_result(CLIENTS_OWN, "cp-clients", "pass")])
        assert _newest(conn, "cp-clients", supply, CLIENTS_OWN)["run_id"] == second != first

    def test_a_later_opened_re_check_wins_over_a_later_effective_decision(self, conn):
        """Test 16's shape: a decision recorded Wednesday with Monday's
        effective time, its re-check opened after a run whose cause took
        effect on Tuesday - the re-check is the newer result."""
        from qa_tools.common import decision_log as dl

        supply = f"cp-clients@{_key()}"
        ids = []
        for effective in ("2099-01-06T09:00:00+08:00", "2099-01-05T09:00:00+08:00"):
            with dl.apply_decision(conn, dl.Decision(
                    agency_id=KEYS["agency_id"], collection_id=KEYS["collection_id"],
                    dataset_id="cp-clients", action=dl.RECHECK, supply=supply, actor="k@x",
                    actor_kind=dl.PERSON, to_slot=f"2099-q{uuid.uuid4().hex[:6]}",
                    reason="pytest", effective_at=effective)):
                pass
            ids.append(conn.execute(f"SELECT max(id) FROM {dl.TABLE}").fetchone()[0])
        table = {"cp_clients": (f"cp_clients__{supply.split('@')[1]}", supply)}
        _run(conn, f"pytest-rb-{uuid.uuid4().hex[:8]}", dataset_id="cp-clients", supply=supply,
             at="2099-01-06T09:00:00+08:00", scope="full", decision=ids[0], physical=table,
             own=[_result(CLIENTS_OWN, "cp-clients", "pass")])
        wednesday = _run(conn, f"pytest-rb-{uuid.uuid4().hex[:8]}", dataset_id="cp-clients",
                         supply=supply, at="2099-01-07T09:00:00+08:00", scope="full",
                         decision=ids[1], physical=table,
                         own=[_result(CLIENTS_OWN, "cp-clients", "fail")])
        assert _newest(conn, "cp-clients", supply, CLIENTS_OWN)["run_id"] == wednesday


class TestWhatIsAboutASupplyIsWhatItRecordedReading:
    """Criterion 21: qa.check_read, not the run's record of physical names."""

    def _clients(self, conn) -> tuple[str, str]:
        supply = f"cp-clients@{_key()}"
        return supply, f"cp_clients__{supply.split('@')[1]}"

    def test_a_cross_table_result_that_read_the_supply_is_about_it(self, conn):
        supply, _ = self._clients(conn)
        notifications = f"cp-notifications@{_key()}"
        key = _run(conn, f"pytest-n-{uuid.uuid4().hex[:8]}", dataset_id="cp-notifications",
                   supply=notifications, at="2099-02-01T09:00:00+08:00",
                   cross=[(_result(CLIENT_REF, "cp-notifications", "fail"),
                           (_read("cp_clients", supply),
                            _read("cp_notifications", notifications)))])
        assert [r["run_id"] for r in supply_status.results_about(conn, "cp-clients", supply)] \
            == [key]

    def test_a_result_that_read_another_supply_of_the_table_is_not(self, conn):
        supply, physical = self._clients(conn)
        other = f"cp-clients@{_key()}"
        notifications = f"cp-notifications@{_key()}"
        _run(conn, f"pytest-n-{uuid.uuid4().hex[:8]}", dataset_id="cp-notifications",
             supply=notifications, at="2099-02-01T09:00:00+08:00",
             physical={"cp_clients": (physical, None)},
             cross=[(_result(CLIENT_REF, "cp-notifications", "fail"),
                     (_read("cp_clients", other), _read("cp_notifications", notifications)))])
        assert supply_status.results_about(conn, "cp-clients", supply) == []

    def test_a_result_that_read_no_supply_of_the_table_is_not(self, conn):
        """K2 = A's recorded half: ABSENT is about no supply of the table,
        whatever physical name the run-level record happens to carry."""
        supply, physical = self._clients(conn)
        notifications = f"cp-notifications@{_key()}"
        _run(conn, f"pytest-n-{uuid.uuid4().hex[:8]}", dataset_id="cp-notifications",
             supply=notifications, at="2099-02-01T09:00:00+08:00",
             physical={"cp_clients": (physical, None)},
             cross=[(_result(CLIENT_REF, "cp-notifications", "fail"),
                     (_read("cp_clients", None, qa_store.ABSENT),
                      _read("cp_notifications", notifications)))])
        assert supply_status.results_about(conn, "cp-clients", supply) == []

    def test_its_own_runs_single_table_results_are_about_it(self, conn):
        supply, _ = self._clients(conn)
        key = _run(conn, f"pytest-c-{uuid.uuid4().hex[:8]}", dataset_id="cp-clients",
                   supply=supply, at="2099-02-01T09:00:00+08:00",
                   own=[_result(CLIENTS_OWN, "cp-clients", "pass")])
        assert [(r["run_id"], r["check_id"])
                for r in supply_status.results_about(conn, "cp-clients", supply)] == [
                    (key, CLIENTS_OWN)]

    def test_another_supplys_own_results_are_not(self, conn):
        supply, physical = self._clients(conn)
        _run(conn, f"pytest-c-{uuid.uuid4().hex[:8]}", dataset_id="cp-clients",
             supply=f"cp-clients@{_key()}", at="2099-02-01T09:00:00+08:00",
             physical={"cp_clients": (physical, None)},
             own=[_result(CLIENTS_OWN, "cp-clients", "pass")])
        assert supply_status.results_about(conn, "cp-clients", supply) == []


class TestTheBuildAndTheGateAgree:
    """Criterion 21's one function, read by both: the build's red-promoted
    timeline ends on the result the gate calls newest."""

    def test_the_last_step_is_the_later_opened_runs(self, conn):
        from pipeline import red_promoted
        from qa_tools.common import decision_log as dl

        supply = f"cp-clients@{_key()}"
        with dl.apply_decision(conn, dl.Decision(
                **KEYS, dataset_id="cp-clients", action=dl.PROMOTE, supply=supply,
                actor="k@x", actor_kind=dl.PERSON, to_slot=f"2099-q{uuid.uuid4().hex[:6]}",
                promoted_status="green", effective_at="2099-03-01T09:00:00+08:00")):
            pass
        table = {"cp_clients": (f"cp_clients__{supply.split('@')[1]}", supply)}
        _run(conn, f"pytest-p-{uuid.uuid4().hex[:8]}", dataset_id="cp-clients", supply=supply,
             at="2099-03-03T09:00:00+08:00", physical=table,
             own=[_result(CLIENTS_OWN, "cp-clients", "fail")])
        last = _run(conn, f"pytest-p-{uuid.uuid4().hex[:8]}", dataset_id="cp-clients",
                    supply=supply, at="2099-03-02T09:00:00+08:00", physical=table,
                    own=[_result(CLIENTS_OWN, "cp-clients", "pass")])
        gate = supply_status.status(conn, "cp-clients", supply)
        health = red_promoted.for_dataset("cp-clients", conn=conn)[last]
        assert health["timeline"][-1]["status"] == gate == "green"


# ---------------------------------------------------------------------------
# REQ-PIPE-265's siblings, from the record (criterion 22)
# ---------------------------------------------------------------------------

def _filed(conn, dataset_id: str, supply: str, delivery: str, at: datetime) -> None:
    import filing_support

    filing_support.ensure_delivery(delivery, dataset_id, at, filename=f"{dataset_id}.csv")
    conn.execute(f"INSERT INTO {filing.TABLE} (dataset_id, supply_id, slot, branch, delivery) "
                 "VALUES (?, ?, ?, 'test', ?)",
                 [dataset_id, supply, f"2099-q{uuid.uuid4().hex[:6]}", delivery])


def _arrival(conn, key: str, dataset_id: str, delivery: str, at: datetime, **kw) -> str:
    supply = f"{dataset_id}@{_key()}"
    _filed(conn, dataset_id, supply, delivery, at)
    return _run(conn, key, dataset_id=dataset_id, supply=supply, at=at.isoformat(), **kw)


@pytest.fixture
def instant():
    return datetime(2099, 4, 1, 1, tzinfo=timezone.utc) + timedelta(
        seconds=random.randint(0, 10**7))


class TestSiblingsAreReadFromTheRecord:

    def test_one_delivery_at_one_instant_is_siblings_whatever_the_run_ids_say(
            self, conn, instant):
        delivery = f"pytest-zip-{uuid.uuid4().hex[:8]}"
        a = _arrival(conn, f"pytest-a-{uuid.uuid4().hex[:8]}", "cp-clients", delivery, instant)
        b = _arrival(conn, f"pytest-b-{uuid.uuid4().hex[:8]}", "cp-notifications", delivery,
                     instant)
        assert carried.siblings(conn, b) == [a]
        assert carried.siblings(conn, a) == [b]

    def test_ids_sharing_an_instant_from_two_deliveries_are_not(self, conn, instant):
        key = _key()
        a = _arrival(conn, f"cp_clients__{key}", "cp-clients",
                     f"pytest-one-{uuid.uuid4().hex[:8]}", instant)
        b = _arrival(conn, f"cp_notifications__{key}", "cp-notifications",
                     f"pytest-two-{uuid.uuid4().hex[:8]}", instant)
        assert carried.siblings(conn, a) == [] == carried.siblings(conn, b)

    def test_a_staggered_file_of_one_delivery_is_not(self, conn, instant):
        delivery = f"pytest-zip-{uuid.uuid4().hex[:8]}"
        a = _arrival(conn, f"pytest-a-{uuid.uuid4().hex[:8]}", "cp-clients", delivery, instant)
        later = instant + timedelta(minutes=5)
        import filing_support

        filing_support.ensure_delivery(delivery, "cp-notifications", later,
                                       filename="cp-notifications-late.csv")
        supply = f"cp-notifications@{_key()}"
        conn.execute(f"INSERT INTO {filing.TABLE} (dataset_id, supply_id, slot, branch, "
                     "delivery) VALUES (?, ?, '2099-qlate', 'test', ?)",
                     ["cp-notifications", supply, delivery])
        conn.execute(f'UPDATE "{qa_store.SCHEMA}".delivery_file SET received_instant = ? '
                     "WHERE delivery = ? AND dataset_id = ?", [later, delivery, "cp-notifications"])
        b = _run(conn, f"pytest-b-{uuid.uuid4().hex[:8]}", dataset_id="cp-notifications",
                 supply=supply, at=later.isoformat())
        assert carried.siblings(conn, a) == [] == carried.siblings(conn, b)

    def test_a_re_check_has_none(self, conn, instant):
        delivery = f"pytest-zip-{uuid.uuid4().hex[:8]}"
        _arrival(conn, f"pytest-a-{uuid.uuid4().hex[:8]}", "cp-clients", delivery, instant)
        b = _arrival(conn, f"pytest-b-{uuid.uuid4().hex[:8]}", "cp-notifications", delivery,
                     instant, scope="full", decision=1)
        assert carried.siblings(conn, b) == []

    def test_a_run_with_no_supply_has_none(self, conn):
        key = _run(conn, f"pytest-t-{uuid.uuid4().hex[:8]}", dataset_id=None, supply=None,
                   at="2099-04-01T09:00:00+08:00")
        assert carried.siblings(conn, key) == []

    def test_they_come_in_the_order_they_were_opened(self, conn, instant):
        delivery = f"pytest-zip-{uuid.uuid4().hex[:8]}"
        z = _arrival(conn, f"pytest-z-{uuid.uuid4().hex[:8]}", "cp-placements", delivery, instant)
        a = _arrival(conn, f"pytest-a-{uuid.uuid4().hex[:8]}", "cp-carers", delivery, instant)
        me = _arrival(conn, f"pytest-m-{uuid.uuid4().hex[:8]}", "cp-clients", delivery, instant)
        assert carried.siblings(conn, me) == [z, a]


class TestACheckIsCarriedOnlyOverTheSuppliesItRecordedReading:
    """Criterion 21's carried.decide: _same_supplies compares recorded
    supply ids - this run's resolution against the sibling's qa.check_read."""

    def _pair(self, conn, instant, *, read_clients: str | None = None,
              clients_state: str = qa_store.READ):
        delivery = f"pytest-zip-{uuid.uuid4().hex[:8]}"
        clients, notifications = f"cp-clients@{_key()}", f"cp-notifications@{_key()}"
        _filed(conn, "cp-clients", clients, delivery, instant)
        _filed(conn, "cp-notifications", notifications, delivery, instant)
        sibling = _run(
            conn, f"pytest_sc_{uuid.uuid4().hex[:8]}", dataset_id="cp-clients", supply=clients,
            at=instant.isoformat(),
            cross=[(_result(CLIENT_REF, "cp-notifications", "fail"),
                    (_read("cp_clients", clients),
                     _read("cp_notifications", notifications)))])
        here = f"pytest_sn_{uuid.uuid4().hex[:8]}"
        qa_store.record_run(conn, run_key=here, run_timestamp=instant.isoformat(), **KEYS)
        qa_store.set_run_purpose(conn, here, dataset_id="cp-notifications",
                                 supply_id=notifications)
        res = supply_db.Resolution(run_id=here, schema=supply_db.run_schema(here),
                                   resolved={"cp_notifications": "n__1"},
                                   supply_of={"cp_notifications": notifications})
        if clients_state == qa_store.HELD:
            res.held["cp_clients"] = "c__1"
            res.held_supply["cp_clients"] = read_clients or clients
        else:
            res.resolved["cp_clients"] = "cp_clients"
            res.supply_of["cp_clients"] = read_clients or clients
        supply_db.record_resolution(conn, res)
        return here, sibling

    def _decide(self, conn, run_id):
        return carried.decide(conn, run_id, lambda c: c == CLIENT_REF,
                              promotion._declared_reads())

    def test_the_same_supplies_carry(self, conn, instant):
        here, sibling = self._pair(conn, instant)
        assert self._decide(conn, here) == {CLIENT_REF: sibling}

    def test_another_supply_of_a_table_does_not(self, conn, instant):
        here, _ = self._pair(conn, instant, read_clients=f"cp-clients@{_key()}")
        assert self._decide(conn, here) == {}

    def test_a_held_table_never_does(self, conn, instant):
        here, _ = self._pair(conn, instant, clients_state=qa_store.HELD)
        assert self._decide(conn, here) == {}


class TestAPairsFileChecksAreAboutTheFileEachSupplyIs:
    """post-build-review #262 D2. A pair's arrival run is shared by both its
    supplies, and its file checks - one set per file - are recorded under
    it, with the file each is about. Which supply a file IS changes when
    the pair is settled (qa.decision_file), so a file check is about the
    supply whose file it names, read from that record - never the one
    supply the shared run happens to carry."""

    def _pair(self, conn, received, *, settle: bool):
        import test_supply_files as sf

        key = sf._key(received)
        delivery = sf._delivery(conn, received, [(sf.LATER, received),
                                                 (sf.EARLIER, received + timedelta(minutes=10))])
        one, two = f"{sf.DATASET}@{key}#1", f"{sf.DATASET}@{key}#2"
        sf.filing_support.place(conn, sf.DATASET, one, "2031-Q2", delivery)
        if settle:
            sf.filing_support.place(conn, sf.DATASET, two, "2031-Q2", delivery)
            sf._settle(conn, "2031-Q2", [(sf.LATER, one, "supply", None),
                                         (sf.EARLIER, two, "superseded", None)])
        run = f"{sf.LOGICAL}__{key}"
        qa_store.record_run(conn, run_key=run, run_timestamp=received.isoformat(),
                            run_by="t@x", environment="test", **KEYS)
        for n, filename in enumerate((sf.LATER, sf.EARLIER)):
            qa_store.record_file_results(
                conn, run, [_result(f"{CHECK}.{sf.DATASET}.{filename.rsplit('.', 1)[0]}.encoding_file",
                                    sf.DATASET, "pass")],
                **KEYS, supply_state=qa_store.AGREED, load_attempt=-n - 1,
                delivery=delivery, filename=filename)
        # As the pipeline records it at the arrival: the open pair's #1.
        qa_store.set_run_purpose(conn, run, dataset_id=sf.DATASET, supply_id=one,
                                 scope="arrival")
        attempt_support.opened(conn, run)
        qa_store.complete_run(conn, run)
        return sf, one, two

    @staticmethod
    def _files(conn, dataset_id, supply):
        return sorted(r["check_id"].rsplit(".", 2)[-2]
                      for r in supply_status.results_about(conn, dataset_id, supply))

    @pytest.fixture
    def received(self):
        return datetime(2031, 5, 6, tzinfo=timezone.utc) + timedelta(
            seconds=uuid.uuid4().int % 10_000_000)

    def test_a_settled_pairs_supplies_each_have_their_own_files_checks(self, conn, received):
        sf, one, two = self._pair(conn, received, settle=True)
        assert self._files(conn, sf.DATASET, two) == [sf.EARLIER.rsplit(".", 1)[0]]
        assert self._files(conn, sf.DATASET, one) == [sf.LATER.rsplit(".", 1)[0]]

    def test_an_open_pairs_first_supply_has_both(self, conn, received):
        sf, one, _two = self._pair(conn, received, settle=False)
        assert self._files(conn, sf.DATASET, one) == sorted(
            f.rsplit(".", 1)[0] for f in (sf.LATER, sf.EARLIER))
