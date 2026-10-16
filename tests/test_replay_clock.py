"""A replay of a synthetic history stamps its records with the replay's own
time (REQ-PIPE-081 criteria 27-31, Keith 2026-10-06)."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta

import pytest

import equiv_support
from qa_tools.common import asset_time, replay_clock

FIRST_TWO = ("run_001", "run_002")


@pytest.fixture(autouse=True)
def _clock_off():
    replay_clock.stop()
    yield
    replay_clock.stop()


class TestTheClock:

    def test_outside_a_replay_it_is_the_wall_clock(self):
        before = asset_time.now()
        assert before <= replay_clock.now() <= asset_time.now()
        replay_clock.anchor("2024-01-01T00:00:00+08:00")
        assert replay_clock.now() >= before, "an anchor outside a replay changes nothing"

    def test_in_a_replay_it_runs_on_from_its_anchor(self):
        replay_clock.start()
        replay_clock.anchor("2024-01-01T00:00:00+08:00")
        first, second = replay_clock.now(), replay_clock.now()
        assert datetime.fromisoformat("2024-01-01T00:00:00+08:00") <= first < second
        assert second - first < timedelta(seconds=5)

    def test_advance_never_goes_backwards(self):
        replay_clock.start()
        replay_clock.anchor("2024-01-02T00:00:00+08:00")
        replay_clock.advance_to("2024-01-01T00:00:00+08:00")
        assert replay_clock.now() >= datetime.fromisoformat("2024-01-02T00:00:00+08:00")
        replay_clock.advance_to("2024-01-03T00:00:00+08:00")
        assert replay_clock.now() >= datetime.fromisoformat("2024-01-03T00:00:00+08:00")

    def test_refused_on_an_asset_that_is_not_synthetic(self, monkeypatch):
        monkeypatch.setattr(replay_clock, "_is_synthetic", lambda: False)
        with pytest.raises(replay_clock.SimulatedClockRefused):
            replay_clock.start()
        assert not replay_clock.active()

    def test_a_real_assets_replay_keeps_the_wall_clock(self, monkeypatch):
        monkeypatch.setattr(replay_clock, "_is_synthetic", lambda: False)
        with replay_clock.replaying() as simulated:
            assert simulated is False
            replay_clock.anchor("2024-01-01T00:00:00+08:00")
            assert replay_clock.now().year == asset_time.now().year


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    """The real Birth Registrations generator's first two deliveries."""
    import generator_isolation
    from generator import generate_runs

    root = tmp_path_factory.mktemp("replay_clock")
    undo = generator_isolation.redirect(generate_runs, root)
    try:
        generate_runs.main()
    finally:
        undo()
    book = json.loads((root / "generator_bookkeeping.json").read_text())
    keep = {e["delivery"]: e for e in book["birth-registrations"] if e["run_id"] in FIRST_TWO}
    for tree in ("deliveries", "receipts"):
        for d in (root / tree).iterdir():
            if d.name not in keep:
                shutil.rmtree(d)
    latest = max(asset_time.parse_instant(e["received_at"], "bookkeeping") for e in keep.values())
    return root, latest


def _stamps(dsn: str) -> dict:
    """Every instant the replay wrote into the qa schema, by table.column."""
    import psycopg
    out = {}
    with psycopg.connect(dsn) as conn:
        cols = conn.execute(
            "SELECT c.table_name, c.column_name, c.data_type FROM information_schema.columns c "
            "JOIN information_schema.tables t USING (table_schema, table_name) "
            "WHERE c.table_schema = 'qa' AND t.table_type = 'BASE TABLE' "
            "AND (c.data_type = 'timestamp with time zone' "
            "     OR c.column_name IN ('recorded_at', 'run_timestamp')) "
            "AND c.table_name <> 'identity'").fetchall()
        for table, column, kind in cols:
            values = [r[0] for r in conn.execute(
                f'SELECT "{column}" FROM qa."{table}" WHERE "{column}" IS NOT NULL')]
            if kind != "timestamp with time zone":
                values = [asset_time.parse_instant(v, f"{table}.{column}") for v in values]
            if values:
                out[f"{table}.{column}"] = values
        decisions = conn.execute(
            "SELECT action, effective_at, recorded_at FROM qa.decision").fetchall()
    return {"stamps": out, "decisions": decisions}


@pytest.fixture(scope="module")
def replayed(corpus, worker_id):
    from qa_tools.bdm import orchestrate_bdm

    root, latest = corpus
    snap = equiv_support.run_into_fresh_database(
        root, f"replay_clock_{worker_id}",
        lambda: orchestrate_bdm.run_pipeline(sequential=True), inspect=_stamps)
    return snap["inspected"], latest


class TestAReplayStampsItsOwnTime:

    def test_every_stamp_is_the_replays_time_not_today(self, replayed):
        got, latest = replayed
        # The promotion lag is at most three days (promotion.effective_at_for).
        bound = latest + timedelta(days=4)
        assert bound < asset_time.now() - timedelta(days=7), "the corpus is too recent to tell"
        late = {k: max(v) for k, v in got["stamps"].items() if max(v) > bound}
        assert late == {}, f"stamped with the wall clock, not the replay's: {late}"
        for expected in ("run.created_at", "run.completed_at", "run.run_instant",
                         "filing.recorded_at", "decision.recorded_at",
                         "load_outcome.recorded_at", "delivery.recorded_at"):
            assert expected in got["stamps"], f"nothing written to {expected} at all"

    def test_a_rule_decision_is_recorded_as_it_takes_effect(self, replayed):
        got, _ = replayed
        assert got["decisions"], "the replay made no decision"
        for action, effective, recorded in got["decisions"]:
            assert effective <= recorded < effective + timedelta(minutes=5), \
                (action, effective, recorded)
