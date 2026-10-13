"""A settled pair's supply is CHECKED by the real tools (REQ-PIPE-193
criteria 13, 14 and 21): a real two-file Birth Registrations delivery,
recognised, recorded, staged, filed and run by the same per-arrival
lifecycle every arrival goes through - its run 'could not run', because two
files claim the table - then settled, and the QA run the settlement owed
runs dbt-core, Soda Core, datacontract-cli and Evidently over the chosen
file alone, recorded under a run of that supply's own.

Real tools, so slower than the rest of the settlement's tests (about 20
seconds); REQ-GEN-196's planted pairs prove the same end to end on a
bootstrapped history (criterion 28).
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone

import pytest

from qa_tools.common import qa_store, recheck, settlement, supply_db, supply_files
from qa_tools.common import filing_decisions as fd

DS = "birth-registrations"
REAL_PERSON = "fpycnkgvmt@privaterelay.appleid.com"


@pytest.fixture
def pair(supply_dsn, tmp_path, monkeypatch):
    from generator.daily_batch import generate_daily_batch
    from qa_tools.bdm import build_per_run_warehouses, orchestrate_bdm
    from qa_tools.common import arrivals, delivery, delivery_log, promotion

    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "pytest@example.org")
    monkeypatch.setattr(promotion, "report", lambda outcome: None)
    # INSIDE THE CALENDAR'S REACH (it starts 2026-08-14) and the coming year.
    from pair_support import free_day

    with supply_db.connect(label="test-choose-file-runs") as conn:
        qa_store.ensure_schema(conn)
        day = free_day(conn, date(2026, 8, 20))
    received = datetime(day.year, day.month, day.day, 4, tzinfo=timezone.utc) + timedelta(
        seconds=random.randrange(1, 3000), microseconds=random.randrange(1, 999_999))
    chosen, spare = f"birth_registrations_{day}.csv", f"birth_registrations_{day}-1.csv"
    rows = generate_daily_batch(day, seed=91001, n_rows=600).to_csv(index=False)
    deliveries, receipts = tmp_path / "deliveries", tmp_path / "receipts"
    name = f"pytest-pair-{random.randrange(10**9)}"
    delivery.write_delivery(name, {chosen: rows, spare: rows},
                            received_at={chosen: received, spare: received + timedelta(
                                minutes=10)},
                            deliveries_dir=deliveries, receipts_dir=receipts)
    for d in delivery.list_deliveries(deliveries, receipts):
        delivery_log.record(d, arrivals.recognise(d))
    (arrival,) = [a for a in arrivals.arrivals_for("civil-registration", "run_",
                                                   deliveries, receipts)
                  if a.delivery_name == name]
    build_per_run_warehouses.stage_arrival(arrival)
    orchestrate_bdm.run_arrivals([arrival], "pytest@example.org")
    pair_id = f"{DS}@{supply_db.arrival_segment(arrival.received_at)}#1"
    return pair_id, day.isoformat(), chosen, spare


def test_each_settled_supply_is_checked_on_its_own_file(pair):
    """TS-69's shape - file two re-filed to the next day - so BOTH files stay
    in staging: each supply's run must read its own file and only it, which
    a run resolving the arrival's tables by key alone cannot do."""
    from qa_tools.common import people, slots

    supply, period, chosen, spare = pair
    nxt = slots.relative_period(DS, period, 1)
    with supply_db.connect(label="test-choose-file-runs") as conn:
        qa_store.ensure_schema(conn)
        assert supply_files.open_contest(conn, DS, supply) is not None, (
            "precondition: the arrival left an open pair")

        def ask(key=None):
            return fd.Request(
                operation=fd.CHOOSE_FILE, dataset_id=DS,
                actor=people.person_by_email(REAL_PERSON), reason="the next day's file",
                period=period, supply=supply, confirmed=True, acknowledged=key,
                file_outcomes=(settlement.Answer(chosen, settlement.SUPPLY),
                               settlement.Answer(spare, settlement.REFILE, nxt)))
        key = fd.consequences(conn, ask()).key or None
        got = fd.apply(ask(key), effective_at=(datetime.fromisoformat(period + "T12:00:00")
                                               .replace(tzinfo=timezone.utc)
                                               + timedelta(days=1)).isoformat(), conn=conn)
        second = supply_files.pair_supply(supply)[:-1] + "2"
        own = {s: supply_files.resolve(conn, DS, s).tables for s in (supply, second)}
    assert len(got.owed) == 2
    for owed_id, which, where in zip(got.owed, (supply, second), (period, nxt)):
        done = recheck.run(owed_id, run_by="pytest@example.org")
        assert done.completed, done.message
        with supply_db.connect(label="test-choose-file-runs") as conn:
            (run_supply, run_period), = conn.execute(
                f'SELECT supply_id, period FROM "{qa_store.SCHEMA}".run WHERE run_key = ?',
                [done.run_key]).fetchall()
            read = {r[0] for r in conn.execute(
                f'SELECT physical_table FROM "{qa_store.SCHEMA}".tables_read '
                "WHERE run_key = ? AND logical_table = 'birth_registrations'",
                [done.run_key]).fetchall()}
            results = conn.execute(
                f'SELECT count(*) FROM "{qa_store.SCHEMA}".check_result WHERE run_key = ?',
                [done.run_key]).fetchall()[0][0]
        assert (run_supply, run_period) == (which, where)
        assert done.run_key.startswith(supply_files.run_id_of(DS, which) + "__r")
        assert read == set(own[which]), (which, read, own)
        assert results > 0
