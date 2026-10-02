"""A one-file arrival's run reads its period, not just itself
(REQ-PIPE-105 criteria 5, 6 and 8; REQ-PIPE-079 criteria 10-12).

Against this worker's own database, with filings written directly: what
is under test is what the overlay READS, and the assignment rule that
decides a filing has its own tests.
"""
from __future__ import annotations

import json
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
            conn.execute(
                f"INSERT INTO {filing.TABLE} (dataset_id, supply_id, slot, branch, record) "
                "VALUES (?, ?, ?, 'test', ?)",
                [DATASET[table], f"{DATASET[table]}@{key}", period_to,
                 json.dumps({"supply_id": f"{DATASET[table]}@{key}", "slot": period_to})])
        return physical

    def promote(physical: str) -> None:
        schema = period_schema.ensure_period_schema(conn, period)
        supply_db.move_table(conn, physical, supply_db.STAGING_SCHEMA, schema)

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
    conn.execute(f"DELETE FROM {filing.TABLE} WHERE slot = ?", [period])


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
        arrival = SimpleNamespace(received_at=fix, held=frozenset(),
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
        arrival = SimpleNamespace(received_at=at, held=frozenset(),
                                  files_by_dataset={"cp-clients": ["cp_clients.csv"]})
        (supply,) = filing.supplies_of(conn, arrival)
        assert supply["contested"] is False
