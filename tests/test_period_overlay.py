"""A one-file arrival's run reads its period, not just itself
(REQ-PIPE-105 criteria 5, 6 and 8; REQ-PIPE-079 criteria 10-12).

Against this worker's own database, with filings written directly: what
is under test is what the overlay READS, and the assignment rule that
decides a filing has its own tests.
"""
from __future__ import annotations

import random
import uuid

import pytest

from qa_tools.common import filing, period_overlay, period_schema, qa_store, supply_db

TABLES = ["cp_clients", "cp_placements"]
DATASET = {"cp_clients": "cp-clients", "cp_placements": "cp-placements"}


def _key() -> str:
    return "".join(random.choice("0123456789") for _ in range(18))


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-period-overlay") as c:
        supply_db.ensure_schemas(c)
        qa_store.ensure_schema(c)
        yield c


@pytest.fixture
def world(conn):
    """Helpers to stage, file and promote, in one unique period."""
    period = f"2099-q{uuid.uuid4().hex[:6]}"
    made: list[str] = []
    runs: list[str] = []

    def stage(table: str, key: str, value: int = 1, period_to: str | None = period) -> str:
        physical = f"{table}__{key}"
        conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" (v int)')
        conn.execute(f'INSERT INTO "{supply_db.STAGING_SCHEMA}"."{physical}" VALUES (?)', [value])
        made.append(physical)
        if period_to is not None:
            import filing_support
            delivery = f"pytest-overlay-{key}"
            filing_support.ensure_delivery(delivery, DATASET[table], None,
                                           filename=f"{table}.csv")
            conn.execute(
                f"INSERT INTO {filing.TABLE} (dataset_id, supply_id, slot, branch, delivery) "
                "VALUES (?, ?, ?, 'test', ?)",
                [DATASET[table], f"{DATASET[table]}@{key}", period_to, delivery])
        return physical

    def promote(physical: str) -> None:
        from qa_tools.common import period_tables

        period_schema.ensure_period_schema(conn, period)
        # Through the one code path, under its plain base name (REQ-PIPE-129).
        period_tables.bring_in(conn, physical=physical,
                               source_schema=supply_db.STAGING_SCHEMA, period=period)

    def build(own_table: str, key: str, **kw):
        run_id = f"{own_table}__{key}"
        runs.append(run_id)
        return period_overlay.build(conn, run_id, period=period, own_table=own_table,
                                    arrival_key=key, tables=TABLES, loaded=None, **kw)

    def read(run_id: str, table: str) -> int:
        return conn.execute(
            f'SELECT v FROM "{supply_db.run_schema(run_id)}"."{table}"').fetchone()[0]

    yield type("W", (), {"period": period, "stage": staticmethod(stage),
                         "promote": staticmethod(promote), "build": staticmethod(build),
                         "read": staticmethod(read)})
    for run_id in runs:
        conn.execute(f'DROP SCHEMA IF EXISTS "{supply_db.run_schema(run_id)}" CASCADE')
    for physical in made:
        conn.execute(f'DROP TABLE IF EXISTS "{supply_db.STAGING_SCHEMA}"."{physical}" CASCADE')
    conn.execute(f'DROP SCHEMA IF EXISTS "{period_schema.period_schema(period)}" CASCADE')
    import filing_support

    filing_support.forget(conn, "slot = ?", [period])


class TestASiblingIsReadFromItsPeriod:
    """Criterion 5: the run triggered by a delivery's last file sees all
    of it, with nothing promoted."""

    def test_the_sibling_staged_for_the_period_is_read(self, world):
        k1, k2 = _key(), _key()
        world.stage("cp_clients", k1, value=7)
        world.stage("cp_placements", k2, value=3)
        out = world.build("cp_placements", k2)
        assert out.readable == ["cp_clients", "cp_placements"]
        assert out.source == {"cp_clients": period_schema.FROM_STAGING,
                              "cp_placements": period_schema.FROM_STAGING}
        assert world.read(f"cp_placements__{k2}", "cp_clients") == 7

    def test_a_sibling_staged_for_another_period_is_not(self, world):
        k1, k2 = _key(), _key()
        world.stage("cp_clients", k1, period_to="1999-q9-elsewhere")
        world.stage("cp_placements", k2)
        out = world.build("cp_placements", k2)
        assert out.resolution.absent == ["cp_clients"]

    def test_a_sibling_staged_but_never_filed_is_not_read(self, world):
        k1, k2 = _key(), _key()
        world.stage("cp_clients", k1, period_to=None)
        world.stage("cp_placements", k2)
        assert world.build("cp_placements", k2).resolution.absent == ["cp_clients"]

    def test_with_nothing_staged_the_promoted_version_answers(self, world):
        k1, k2 = _key(), _key()
        world.promote(world.stage("cp_clients", k1, value=5))
        world.stage("cp_placements", k2)
        out = world.build("cp_placements", k2)
        assert out.source["cp_clients"] == period_schema.FROM_PERIOD
        assert world.read(f"cp_placements__{k2}", "cp_clients") == 5


class TestSeveralStagedVersionsAreContested:
    """Criteria 6 and 8: never chosen between, by arrival time or any
    other way."""

    def test_two_staged_siblings_fall_through_to_the_promoted_one(self, world):
        old, a, b, own = _key(), _key(), _key(), _key()
        world.promote(world.stage("cp_clients", old, value=1))
        world.stage("cp_clients", a, value=2)
        world.stage("cp_clients", b, value=3)
        world.stage("cp_placements", own)
        out = world.build("cp_placements", own)
        assert set(out.resolution.ambiguous["cp_clients"]) == {
            f"cp_clients__{a}", f"cp_clients__{b}"}
        assert world.read(f"cp_placements__{own}", "cp_clients") == 1

    def test_a_correction_beside_an_unpromoted_red_supply_reads_its_own(self, world):
        """Criterion 6 as amended 2026-10-02 evening (Keith): the run's
        own table is its own arrival's, whatever else is staged for the
        period. The first reading made this contested, which left the
        correction unchecked and unpromotable - TS-1/TS-4 broken."""
        red, fix = _key(), _key()
        world.stage("cp_clients", red, value=1)
        world.stage("cp_clients", fix, value=2)
        out = world.build("cp_clients", fix)
        assert not period_overlay.own_table_contested(out.resolution, "cp_clients")
        assert world.read(f"cp_clients__{fix}", "cp_clients") == 2

    def test_two_files_in_one_arrival_are_still_contested(self, world):
        """The one case criterion 6 keeps: nothing says which of two
        files in a single arrival is the supply."""
        key = _key()
        world.stage("cp_clients", f"{key}__1", period_to=None)
        world.stage("cp_clients", f"{key}__2", period_to=None)
        out = world.build("cp_clients", key)
        assert period_overlay.own_table_contested(out.resolution, "cp_clients")

    def test_a_resupply_into_a_promoted_period_is_not_contested(self, world):
        """Promotion MOVES the first supply, so the resupply is alone in
        staging - the common case resolves structurally."""
        first, again = _key(), _key()
        world.promote(world.stage("cp_clients", first, value=1))
        world.stage("cp_clients", again, value=2)
        out = world.build("cp_clients", again)
        assert not period_overlay.own_table_contested(out.resolution, "cp_clients")
        assert world.read(f"cp_clients__{again}", "cp_clients") == 2


class TestAHeldOwnTableIsWithheld:
    def test_held_own_table_gets_no_view_and_no_fallback(self, world):
        old, own = _key(), _key()
        world.promote(world.stage("cp_clients", old))
        world.stage("cp_clients", own)
        out = world.build("cp_clients", own, held={"cp_clients"})
        assert out.resolution.held == {"cp_clients": f"cp_clients__{own}"}
        assert "cp_clients" not in out.resolution.resolved
        assert "cp_clients" not in out.resolution.absent


class TestThePromotionGateSeesOnlyTheArrivalsOwnContest:
    """Criterion 6 at the promotion gate, as amended 2026-10-02 evening:
    filing.supplies_of() reports CONTESTED only where one arrival carried
    two files for a dataset - never because another arrival's supply is
    staged for the same period."""

    def test_a_correction_beside_an_unpromoted_red_supply_is_not_contested(self, conn, world):
        """Criterion 6 as amended 2026-10-02 evening: the correction is
        its own supply and may be promoted on its own verdict."""
        from datetime import datetime, timedelta, timezone
        from types import SimpleNamespace

        from qa_tools.common import asset_time

        base = datetime(2099, 1, 1, 1, tzinfo=timezone.utc) + timedelta(
            seconds=random.randint(0, 10**7))
        red, fix = base, base + timedelta(hours=1)
        world.stage("cp_clients", asset_time.arrival_key(red))
        world.stage("cp_clients", asset_time.arrival_key(fix))
        arrival = SimpleNamespace(received_at=fix, contested=frozenset(),
                                  files_by_dataset={"cp-clients": ["cp_clients.csv"]})

        (supply,) = filing.supplies_of(conn, arrival)

        assert supply["period"] == world.period
        assert supply["physical_tables"] == [f"cp_clients__{asset_time.arrival_key(fix)}"]
        assert supply["contested"] is False

    def test_a_supply_alone_in_its_period_is_not(self, conn, world):
        from datetime import datetime, timedelta, timezone
        from types import SimpleNamespace

        from qa_tools.common import asset_time

        at = datetime(2099, 6, 1, 1, tzinfo=timezone.utc) + timedelta(
            seconds=random.randint(0, 10**7))
        world.stage("cp_clients", asset_time.arrival_key(at))
        arrival = SimpleNamespace(received_at=at, contested=frozenset(),
                                  files_by_dataset={"cp-clients": ["cp_clients.csv"]})
        (supply,) = filing.supplies_of(conn, arrival)
        assert supply["contested"] is False


class TestAnInheritedTableIsRead:
    """REAL DEFECT, 2026-10-02. A period that owes a dataset nothing
    INHERITS it (REQ-PIPE-098): a view in the period's schema named just
    the logical table, standing on an earlier period's promoted supply.
    period_schema.newest() rightly refuses to order a name with no arrival
    key - so the overlay found the inherited view and then read nothing,
    and every check reading Case Workers in a quarter it is not delivered
    in went red as missing."""

    def test_the_overlay_reads_the_inherited_view(self, conn, world):
        old, own = _key(), _key()
        source = f"period_inherit_{uuid.uuid4().hex[:6]}"
        conn.execute(f'CREATE SCHEMA "{source}"')
        try:
            conn.execute(f'CREATE TABLE "{source}"."cp_clients__{old}" (v int)')
            conn.execute(f'INSERT INTO "{source}"."cp_clients__{old}" VALUES (9)')
            schema = period_schema.ensure_period_schema(conn, world.period)
            conn.execute(f'CREATE VIEW "{schema}"."cp_clients" AS '
                         f'SELECT * FROM "{source}"."cp_clients__{old}"')
            world.stage("cp_placements", own)
            out = world.build("cp_placements", own)
            assert out.source.get("cp_clients") == period_schema.FROM_PERIOD
            assert world.read(f"cp_placements__{own}", "cp_clients") == 9
        finally:
            # The period's view first: a cascade that takes it as a side
            # effect is refused by the database guard (REQ-PIPE-129).
            conn.execute(f'DROP VIEW IF EXISTS '
                         f'"{period_schema.period_schema(world.period)}"."cp_clients" CASCADE')
            conn.execute(f'DROP SCHEMA IF EXISTS "{source}" CASCADE')


class TestARunReadsExactlyOnePeriod:
    """REQ-PIPE-079 criteria 1 and 2, as they now hold: by construction.

    They were demonstrated by period_schema.fan_out() - one run per period
    a multi-period delivery claimed. Under REQ-PIPE-105 an arrival is one
    file, so one dataset, so one period, and fan_out() had no caller left;
    it was deleted 2026-10-04. These tests carry the criteria instead, at
    the point where a run's period is actually chosen.
    """

    @staticmethod
    def _calls(monkeypatch, files_by_dataset):
        from datetime import datetime, timezone
        from types import SimpleNamespace

        from qa_tools.common import filing, load_log, supply_holds, trial

        built: list[str] = []
        monkeypatch.setattr(filing, "period_of", lambda dataset_id, at: "2026-Q2")
        monkeypatch.setattr(trial, "scope_for", lambda run_id: None)
        monkeypatch.setattr(load_log, "loaded_tables", lambda scope: frozenset())
        monkeypatch.setattr(supply_holds, "held_tables", lambda conn, **kw: ())
        monkeypatch.setattr(supply_db, "connect", lambda **kw: type(
            "C", (), {"close": lambda self: None})())
        monkeypatch.setattr(period_overlay, "build",
                            lambda conn, run_id, *, period, **kw: built.append(period))
        arrival = SimpleNamespace(
            run_id="cp_clients__202605010100000000",
            received_at=datetime(2026, 5, 1, 1, tzinfo=timezone.utc),
            files_by_dataset=files_by_dataset)
        try:
            period_overlay.rebuild_for_arrival(arrival, tables=["cp_clients"])
        except Exception:  # noqa: BLE001 - recording/sample steps are not under test
            pass
        return built

    def test_a_run_is_built_over_exactly_one_period(self, monkeypatch):
        assert self._calls(monkeypatch, {"cp-clients": ["cp_clients.csv"]}) == ["2026-Q2"]

    def test_an_arrival_spanning_two_datasets_is_refused_rather_than_split(self, monkeypatch):
        """No arrival can span periods, because none can carry two
        datasets - so there is nothing left to fan out."""
        with pytest.raises(ValueError):
            from datetime import datetime, timezone
            from types import SimpleNamespace

            period_overlay.rebuild_for_arrival(SimpleNamespace(
                run_id="x", received_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                files_by_dataset={"cp-clients": ["a.csv"], "cp-carers": ["b.csv"]}),
                tables=["cp_clients"])

    def test_nothing_fans_out_any_more(self):
        assert not hasattr(period_schema, "fan_out")
