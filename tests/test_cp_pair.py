"""A contested Child Protection pair, through the real pipeline (REQ-PIPE-202
criteria 3 to 7): a real delivery carrying the six tables plus a second
Client Register file, recognised, recorded, staged and run by the same
per-arrival lifecycle every arrival goes through - then settled, as a Birth
Registrations pair is settled.

Real tools over the conftest's small real population, so slower than most.
"""
from __future__ import annotations

import random
import shutil
from datetime import timedelta
from pathlib import Path

import pytest

from qa_tools.common import qa_store, supply_db, supply_files

DS = "cp-clients"
REAL_PERSON = "fpycnkgvmt@privaterelay.appleid.com"


def _free_quarter(conn):
    """A cp-clients quarter nothing in this worker's database has filed to."""
    from qa_tools.common import asset_time, slots

    taken = {r[0] for r in conn.execute(
        "SELECT slot FROM qa.filing_current WHERE dataset_id = ?", [DS]).fetchall()}
    today = asset_time.local_date(asset_time.now())
    free = [s for s in slots.slots_for_dataset(DS, until=today + timedelta(days=400))
            if s.name not in taken and s.claim_opens_at < s.due_at
            # The re-file test files the second file to the NEXT period.
            and slots.relative_period(DS, s.name, 1)]
    assert free, "no free cp-clients quarter in this worker's database"
    return random.choice(free)


@pytest.fixture
def cp_pair(supply_dsn, cp_raw_dir, tmp_path, monkeypatch):
    import fixture_ids
    from qa_tools.common import arrivals, delivery, delivery_log, promotion
    from qa_tools.cp import build_cp_warehouses, orchestrate_cp

    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "pytest@example.org")
    monkeypatch.setattr(promotion, "report", lambda outcome: None)
    with supply_db.connect(label="test-cp-pair") as conn:
        qa_store.ensure_schema(conn)
        slot = _free_quarter(conn)
    received = slot.due_at - timedelta(days=2, seconds=random.randrange(1, 3000))
    source = Path(cp_raw_dir) / fixture_ids.CP_REF_RUN_ID
    files = {p.name: p.read_text() for p in sorted(source.glob("*.csv"))}
    files["cp_clients_part2.csv"] = files["cp_clients.csv"]
    deliveries, receipts = tmp_path / "deliveries", tmp_path / "receipts"
    name = f"pytest-cp-pair-{random.randrange(10**9)}"
    delivery.write_delivery(name, files,
                            received_at={n: received + timedelta(minutes=i)
                                         for i, n in enumerate(sorted(files))},
                            deliveries_dir=deliveries, receipts_dir=receipts)
    for d in delivery.list_deliveries(deliveries, receipts):
        delivery_log.record(d, arrivals.recognise(d))
    found = [a for a in arrivals.arrivals_for("child-protection", "cp_run_", deliveries,
                                              receipts) if a.delivery_name == name]
    for arrival in found:
        build_cp_warehouses.stage_arrival(arrival)
    orchestrate_cp.run_arrivals(found, "pytest@example.org")
    (clients,) = [a for a in found if DS in a.files_by_dataset]
    yield {"slot": slot, "arrivals": found, "clients": clients,
           "pair": f"{DS}@{supply_db.arrival_segment(clients.received_at)}#1"}
    shutil.rmtree(deliveries, ignore_errors=True)


def _cross_table(conn, run_keys):
    return conn.execute(
        "SELECT run_key, check_id, status, extra FROM qa.check_result_visible "
        "WHERE run_key = ANY(?) AND scope = ?", [list(run_keys), qa_store.CROSS_TABLE_SCOPE]
    ).fetchall()


class TestAContestedClientRegister:
    """Criteria 3, 4 and 5 - through the recognition, staging and lifecycle
    Birth Registrations' pairs use, with nothing specific to Child Protection."""

    def test_recognised_as_one_contested_arrival(self, cp_pair):
        clients = cp_pair["clients"]
        assert clients.contested == {DS}
        assert clients.files_by_dataset[DS] == ("cp_clients.csv", "cp_clients_part2.csv")
        others = [a for a in cp_pair["arrivals"] if a is not clients]
        assert len(others) == 5 and not any(a.contested for a in others)

    def test_the_outstanding_item_names_both_files(self, cp_pair):
        with supply_db.connect(label="test-cp-pair") as conn:
            contest = supply_files.open_contest(conn, DS, cp_pair["pair"])
        assert contest is not None
        assert contest.files == ("cp_clients.csv", "cp_clients_part2.csv")

    def test_each_reader_records_its_cp_clients_check_once_as_contested(self, cp_pair):
        """Criterion 4: in the runs of the arrival's other tables, each
        cross-table check that reads cp_clients is recorded once, not
        evaluated, its reason contested."""
        others = {a.run_id for a in cp_pair["arrivals"] if a is not cp_pair["clients"]}
        with supply_db.connect(label="test-cp-pair") as conn:
            rows = _cross_table(conn, others)
        contested = [(r[0], r[1]) for r in rows
                     if (r[3] or {}).get("unrunnable_code") == "contested"
                     and (r[3] or {}).get("unrunnable_table") == "cp_clients"]
        assert contested, "no reader recorded its cp_clients check as contested"
        assert len(contested) == len(set(contested)), "a check recorded more than once"

    def test_the_file_checks_run_on_each_file_under_its_own_name(self, cp_pair):
        """Criterion 5."""
        with supply_db.connect(label="test-cp-pair") as conn:
            names = {r[0] for r in conn.execute(
                "SELECT filename FROM qa.check_result_visible WHERE run_key = ? "
                "AND filename IS NOT NULL", [cp_pair["clients"].run_id]).fetchall()}
        assert {"cp_clients.csv", "cp_clients_part2.csv"} <= names


def _settle(conn, cp_pair, outcomes, when_days=1):
    from datetime import timezone

    from qa_tools.common import people, settlement
    from qa_tools.common import filing_decisions as fd

    period = cp_pair["slot"].name

    def ask(key=None):
        return fd.Request(
            operation=fd.CHOOSE_FILE, dataset_id=DS,
            actor=people.person_by_email(REAL_PERSON), reason="settling the pair",
            period=period, supply=cp_pair["pair"], confirmed=True, acknowledged=key,
            file_outcomes=tuple(settlement.Answer(*o) for o in outcomes))
    key = fd.consequences(conn, ask()).key or None
    at = (cp_pair["clients"].received_at + timedelta(days=when_days)).astimezone(timezone.utc)
    return fd.apply(ask(key), effective_at=at.isoformat(), conn=conn)


class TestAPersonSettlesIt:
    """Criterion 7 - choose-file on exactly a Birth Registrations pair's terms,
    driving the real Child Protection orchestrator."""

    def _run_owed(self, got):
        from qa_tools.common import recheck

        out = []
        for owed_id in got.owed:
            done = recheck.run(owed_id, run_by="pytest@example.org")
            assert done.completed, done.message
            out.append(done)
        return out

    def _run_of(self, conn, run_key):
        (row,) = conn.execute("SELECT supply_id, period FROM qa.run WHERE run_key = ?",
                              [run_key]).fetchall()
        return row

    def test_this_periods_supply_plus_a_spare_copy(self, cp_pair):
        from qa_tools.common import knock_on, settlement

        period = cp_pair["slot"].name
        with supply_db.connect(label="test-cp-pair") as conn:
            got = _settle(conn, cp_pair, [("cp_clients.csv", settlement.SUPPLY),
                                          ("cp_clients_part2.csv", settlement.SUPERSEDE)])
        (done,) = self._run_owed(got)
        knock_on.follow_up("child-protection", run_by="pytest@example.org")
        with supply_db.connect(label="test-cp-pair") as conn:
            assert self._run_of(conn, done.run_key) == (cp_pair["pair"], period)
            assert done.run_key.startswith(supply_files.run_id_of(DS, cp_pair["pair"]) + "__r")
            self._readers_now_read_the_supply(conn, cp_pair)

    def test_this_periods_supply_plus_a_refile(self, cp_pair):
        from qa_tools.common import knock_on, settlement, slots

        period = cp_pair["slot"].name
        nxt = slots.relative_period(DS, period, 1)
        with supply_db.connect(label="test-cp-pair") as conn:
            got = _settle(conn, cp_pair, [("cp_clients.csv", settlement.SUPPLY),
                                          ("cp_clients_part2.csv", settlement.REFILE, nxt)])
        second = supply_files.pair_supply(cp_pair["pair"])[:-1] + "2"
        runs = self._run_owed(got)
        knock_on.follow_up("child-protection", run_by="pytest@example.org")
        with supply_db.connect(label="test-cp-pair") as conn:
            got_runs = {self._run_of(conn, r.run_key) for r in runs}
            assert got_runs == {(cp_pair["pair"], period), (second, nxt)}
            self._readers_now_read_the_supply(conn, cp_pair)

    def _readers_now_read_the_supply(self, conn, cp_pair):
        _readers_now_read(conn, cp_pair, cp_pair["pair"])


def _readers_now_read(conn, cp_pair, expected):
    """THE KNOCK-ON'S OWN TERMS (REQ-PIPE-121): every reader in the period
    whose cross-table checks read cp_clients now has its latest result for
    each of them reading the settled supply, and none is left stale - the
    arrival's own runs could read nothing, recorded as contested."""
    from qa_tools.common import knock_on, promotion, reevaluation, supply_status

    period, reads = cp_pair["slot"].name, promotion._declared_reads()
    holds = knock_on._now_holds(conn, "cp_clients", period)
    assert holds == expected
    found = knock_on.readers(conn, period, ["cp_clients"], reads)
    assert {r.dataset_id for r in found} >= {"cp-investigations", "cp-notifications"}
    checks = reevaluation.reading_checks(table="cp_clients", period=period, reads=reads)
    for reader in found:
        assert not reader.stale, reader
        mine = {c for c in checks
                if reader.dataset_id in reevaluation.counts_toward(c, table="cp_clients",
                                                                   reads=reads)}
        latest = [r for r in supply_status.latest_results(conn, reader.dataset_id,
                                                          reader.supply)
                  if r.get("check_id") in mine]
        assert latest, reader
        assert {knock_on._read_as(conn, r["run_id"], "cp_clients") for r in latest} == {
            holds}
        assert not any((r.get("extra") or {}).get("unrunnable_code") == "contested"
                       for r in latest)


def test_a_later_file_supersedes_both_and_resolves_the_contest(cp_pair, cp_raw_dir, tmp_path):
    """Criterion 6 (REQ-PIPE-118 criteria 1 and 13, REQ-PIPE-194 criterion 9):
    a later arrival's cp_clients file filed to the pair's period supersedes
    both files, and the contest is resolved."""
    import fixture_ids
    from qa_tools.common import arrivals, delivery, delivery_log, knock_on, supersession
    from qa_tools.cp import build_cp_warehouses, orchestrate_cp

    later_at = cp_pair["clients"].received_at + timedelta(hours=6)
    source = Path(cp_raw_dir) / fixture_ids.CP_REF_RUN_ID
    deliveries, receipts = tmp_path / "later_d", tmp_path / "later_r"
    name = f"pytest-cp-later-{random.randrange(10**9)}"
    delivery.write_delivery(name, {"cp_clients.csv": (source / "cp_clients.csv").read_text()},
                            received_at=later_at, deliveries_dir=deliveries,
                            receipts_dir=receipts)
    for d in delivery.list_deliveries(deliveries, receipts):
        delivery_log.record(d, arrivals.recognise(d))
    found = [a for a in arrivals.arrivals_for("child-protection", "cp_run_", deliveries,
                                              receipts) if a.delivery_name == name]
    for arrival in found:
        build_cp_warehouses.stage_arrival(arrival)
    orchestrate_cp.run_arrivals(found, "pytest@example.org")
    # An open pair is ONE filed supply - its '#1' - so superseding that
    # supply is the supersession of both files (REQ-PIPE-194 criterion 9).
    with supply_db.connect(label="test-cp-pair") as conn:
        assert supply_files.open_contest(conn, DS, cp_pair["pair"]) is None
        assert supersession.is_superseded(conn, DS, cp_pair["pair"])
        later = knock_on._now_holds(conn, "cp_clients", cp_pair["slot"].name)
        assert later and later != cp_pair["pair"]
    # Promoted, so the readers waiting in the period are re-evaluated through
    # the one knock-on handler (REQ-PIPE-121).
    knock_on.follow_up("child-protection", run_by="pytest@example.org")
    with supply_db.connect(label="test-cp-pair") as conn:
        _readers_now_read(conn, cp_pair, later)
