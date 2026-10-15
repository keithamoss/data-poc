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

    from qa_tools.common import period_schema

    # UNTOUCHED BY ANY CHILD PROTECTION DATASET, and with nothing in its
    # period's schema: the pair's other five tables read their siblings from
    # the period, and a table another module left there of another shape
    # took a run down in CI (674399a, "column postcode does not exist").
    taken = {r[0] for r in conn.execute(
        "SELECT slot FROM qa.filing_current WHERE dataset_id LIKE 'cp-%'").fetchall()}
    populated = {r[0] for r in conn.execute(
        "SELECT DISTINCT table_schema FROM information_schema.tables").fetchall()}
    taken |= {s.name for s in slots.slots_for_dataset(DS, until=asset_time.local_date(
        asset_time.now()) + timedelta(days=400))
        if period_schema.period_schema(s.name) in populated}
    today = asset_time.local_date(asset_time.now())
    free = [s for s in slots.slots_for_dataset(DS, until=today + timedelta(days=400))
            if s.name not in taken and s.claim_opens_at < s.due_at
            # The re-file test files the second file to the NEXT period, so it
            # must exist and be as untouched as this one.
            and slots.relative_period(DS, s.name, 1) not in taken | {None}]
    assert free, "no free cp-clients quarter in this worker's database"
    return random.choice(free)


@pytest.fixture
def cp_pair(supply_dsn, cp_raw_dir, tmp_path, monkeypatch):
    yield from _make_pair(cp_raw_dir, tmp_path, monkeypatch)


@pytest.fixture(scope="module")
def cp_pair_shared(supply_dsn, cp_raw_dir, tmp_path_factory):
    """ONE PAIR FOR THE TESTS THAT ONLY READ IT. Each pair files into a quarter
    nothing else in this worker's database has used, and a CI worker running
    the whole suite ran out of them once every test built its own (CI,
    249926f) - so the read-only checks share one, and only the tests that
    settle or supersede a pair build their own."""
    with pytest.MonkeyPatch.context() as mp:
        yield from _make_pair(cp_raw_dir, tmp_path_factory.mktemp("cp_pair"), mp)


@pytest.fixture
def cp_pair_one_unloadable(supply_dsn, cp_raw_dir, tmp_path, monkeypatch):
    """The second file is not text the load can read (criterion 5's WHERE)."""
    yield from _make_pair(cp_raw_dir, tmp_path, monkeypatch, part2=b"\xff\xfe\x00bad\n")


def _make_pair(cp_raw_dir, tmp_path, monkeypatch, part2=None):
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
    files["cp_clients_part2.csv"] = files["cp_clients.csv"] if part2 is None else part2
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
           "deliveries": deliveries, "receipts": receipts,
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

    def test_recognised_as_one_contested_arrival(self, cp_pair_shared):
        clients = cp_pair_shared["clients"]
        assert clients.contested == {DS}
        assert clients.files_by_dataset[DS] == ("cp_clients.csv", "cp_clients_part2.csv")
        others = [a for a in cp_pair_shared["arrivals"] if a is not clients]
        assert len(others) == 5 and not any(a.contested for a in others)

    def test_the_outstanding_item_names_both_files(self, cp_pair_shared):
        with supply_db.connect(label="test-cp-pair") as conn:
            contest = supply_files.open_contest(conn, DS, cp_pair_shared["pair"])
        assert contest is not None
        assert contest.files == ("cp_clients.csv", "cp_clients_part2.csv")

    def test_each_reader_records_its_cp_clients_check_once_as_contested(self, cp_pair_shared):
        """Criterion 4: in the runs of the arrival's other tables, each
        cross-table check that reads cp_clients is recorded once, not
        evaluated, its reason contested."""
        others = {a.run_id for a in cp_pair_shared["arrivals"] if a is not cp_pair_shared["clients"]}
        with supply_db.connect(label="test-cp-pair") as conn:
            rows = _cross_table(conn, others)
        contested = [(r[0], r[1]) for r in rows
                     if (r[3] or {}).get("unrunnable_code") == "contested"
                     and (r[3] or {}).get("unrunnable_table") == "cp_clients"]
        assert contested, "no reader recorded its cp_clients check as contested"
        assert len(contested) == len(set(contested)), "a check recorded more than once"
        # EACH reader, not any one of them (post-build-review #203 F1b).
        dataset_of = {a.run_id: next(iter(a.files_by_dataset)) for a in cp_pair_shared["arrivals"]}
        assert {dataset_of[run] for run, _ in contested} == {
            "cp-investigations", "cp-notifications", "cp-placements"}

    def test_both_files_staged_and_neither_checked(self, cp_pair_shared):
        """Criterion 3 (post-build-review #203 F1c): two staged tables, and the
        arrival's own run holds file checks only - no tool ran over either."""
        key = supply_db.arrival_segment(cp_pair_shared["clients"].received_at)
        with supply_db.connect(label="test-cp-pair") as conn:
            staged = {r[0] for r in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'staging' AND table_name LIKE ?",
                [f"cp_clients__{key}__%"]).fetchall()}
            tools = {r[0] for r in conn.execute(
                "SELECT DISTINCT tool FROM qa.check_result_visible WHERE run_key = ? "
                "AND filename IS NULL", [cp_pair_shared["clients"].run_id]).fetchall()}
        assert staged == {f"cp_clients__{key}__1", f"cp_clients__{key}__2"}
        assert tools == set(), f"tools ran over a contested table: {tools}"

    def test_the_queue_item_names_both_files(self, cp_pair_shared):
        """Criterion 4's outstanding item itself (post-build-review #203 F1e)."""
        from qa_tools.common import outstanding

        with supply_db.connect(label="test-cp-pair") as conn:
            items = [i for i in outstanding.survey(conn).items
                     if i.dataset_id == DS and i.kind == "contested-table"]
        from qa_tools.common import display_time

        # THIS PAIR'S ITEM, not the first one: another module on the same
        # worker may leave its own contested Client Register (CI, 674399a),
        # so it is found by this pair's own receipt.
        when = display_time.format_instant(cp_pair_shared["clients"].received_at)
        mine = [i for i in items if f"cp_clients.csv, received {when}" in i.detail]
        assert len(mine) == 1 and mine[0].blocking
        said = mine[0].headline + " " + mine[0].detail
        assert "cp_clients.csv" in said and "cp_clients_part2.csv" in said

    def test_the_real_picker_marks_it(self, cp_pair_shared, monkeypatch):
        """Criterion 13 through the real load_manifest (post-build-review #203
        F1a), not a hand-built entry."""
        import cli.cp as cp
        from qa_tools.common import arrivals

        real = arrivals.arrivals_for
        monkeypatch.setattr(arrivals, "arrivals_for", lambda c, p: real(
            c, p, cp_pair_shared["deliveries"], cp_pair_shared["receipts"]))
        manifest = cp.load_manifest()
        (entry,) = [e for e in manifest if e["run_id"] == cp_pair_shared["clients"].run_id]
        assert entry["contested"] == {DS: ["cp_clients.csv", "cp_clients_part2.csv"]}
        others = [e for e in manifest if e is not entry]
        assert others and not any(e["contested"] for e in others)
        marked = [c for c in cp.picker_choices(manifest) if "two files for one table" in c]
        assert [cp.run_id_from_choice(c) for c in marked] == [cp_pair_shared["clients"].run_id]

    def test_the_file_checks_run_on_each_file_under_its_own_name(self, cp_pair_shared):
        """Criterion 5."""
        with supply_db.connect(label="test-cp-pair") as conn:
            names = {r[0] for r in conn.execute(
                "SELECT filename FROM qa.check_result_visible WHERE run_key = ? "
                "AND filename IS NOT NULL", [cp_pair_shared["clients"].run_id]).fetchall()}
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


def test_a_partner_the_load_refuses_keeps_the_pair_contested(cp_pair_one_unloadable):
    """Criterion 5's WHERE (post-build-review #203 F1d): the file that loads is
    not taken as the supply - the pair stays contested, naming the refusal."""
    pair = cp_pair_one_unloadable
    with supply_db.connect(label="test-cp-pair") as conn:
        contest = supply_files.open_contest(conn, DS, pair["pair"])
        assert contest is not None
        assert contest.files == ("cp_clients.csv", "cp_clients_part2.csv")
        names = {r[0] for r in conn.execute(
            "SELECT filename FROM qa.check_result_visible WHERE run_key = ? "
            "AND filename IS NOT NULL", [pair["clients"].run_id]).fetchall()}
    assert {"cp_clients.csv", "cp_clients_part2.csv"} <= names
