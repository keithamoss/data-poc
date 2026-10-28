"""REQ-DASH-272 criterion 21 as Keith settled it on 2026-10-29 (open question 1,
option b): a dataset page's verdict line is worded 'Being checked with its
delivery', 'Checked, waiting for the rest of its delivery' or 'Checked, being
gated' only where its package's gate genuinely did not finish - a pass that
stopped part-way, a contended period lock, a crash - and never through the
synthetic replay's seeded promotion lag, which reads as a person taking their
time ('Awaiting a decision').

Driven through the real per-arrival lifecycle (tests/gate_support.py), then
read by the build's own reader."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

import pytest

from gate_support import Scenario, install_fake_tools, pin_replacement_setting
from test_package_gate import empty_but_workers

CP = "child-protection"
AT = "2024-11-01T09:00:00+08:00"


@pytest.fixture
def sc(private_supply_dsn, cp_raw_dir, tmp_path, monkeypatch):
    scenario = Scenario(root=tmp_path, raw_dir=Path(cp_raw_dir))
    install_fake_tools(monkeypatch, scenario)
    pin_replacement_setting(monkeypatch)
    return scenario


def _read() -> dict:
    from pipeline import package_gating
    from qa_tools.common import supply_db

    with supply_db.connect(read_only=True, label="test-package-gating") as conn:
        return package_gating.for_collection(conn, CP)


def _now(monkeypatch, instant: str) -> None:
    """Now is `instant`, so every record is stamped on the scenario's own
    clock and the reader's days are the scenario's."""
    from qa_tools.common import asset_time

    monkeypatch.setenv(asset_time.PINNED_NOW_VARIABLE, instant)


def _lagged(monkeypatch, days: int = 5) -> None:
    """Every arrival's rule decisions take effect `days` after receipt, as the
    replay's seeded promotion lag does."""
    from qa_tools.tools import orchestrate

    monkeypatch.setattr(orchestrate, "effective_at_of",
                        lambda collection_id, arrival: (arrival.received_at
                                                        + timedelta(days=days)).isoformat())


class TestTheReplaysLagIsAPersonTakingTheirTime:

    def test_a_package_gated_after_a_seeded_lag_shows_no_form(self, sc, monkeypatch):
        """The whole package checked and gated in one pass, its decisions
        taking effect five days later: no form on any day of the lag."""
        _lagged(monkeypatch)
        _now(monkeypatch, "2024-10-25T10:30:00+08:00")
        empty_but_workers(sc)
        _now(monkeypatch, "2024-11-01T09:30:00+08:00")
        got = sc.deliver(AT, {"cp_clients": "C2", "cp_notifications": "N2"})
        sc.process()
        assert sc.owed("gate") == [], "precondition: the gate was applied in the pass"
        assert sc.actions(got["C2"]), "precondition: the gate decided about it"
        assert _read() == {}


class TestAGateThatGenuinelyDidNotFinish:

    def test_a_pass_that_stopped_part_way_reads_waiting_for_the_rest(self, sc, monkeypatch):
        """A time budget stopped the pass after one file of the delivery: its
        checked file reads 'Checked, waiting for the rest of its delivery'."""
        _now(monkeypatch, "2024-10-25T10:30:00+08:00")
        empty_but_workers(sc)
        _now(monkeypatch, "2024-11-01T09:30:00+08:00")
        got = sc.deliver(AT, {"cp_clients": "C2", "cp_notifications": "N2"})
        sc.process(stop_before="N2")
        found = _read()
        (point,) = [p for p in found["cp-clients"][got["C2"]] if p["form"]]
        assert point["form"] == "waiting" and point["lead"] == \
            "Checked, waiting for the rest of its delivery", point
        words = "".join(w.get("text", "") for w in point["words"])
        assert ": 1 of 2 files checked. Nothing needs deciding yet." in words, words
        assert found["cp-notifications"][got["N2"]][0]["form"] == "unchecked"

    def test_a_contended_lock_reads_being_gated_until_it_is_applied(self, sc, monkeypatch):
        """The gate found its period lock held: 'Checked, being gated' from
        then until the next pass applies it, and nothing after."""
        from qa_tools.common import gate

        _lagged(monkeypatch, days=3)
        _now(monkeypatch, "2024-10-25T10:30:00+08:00")
        empty_but_workers(sc)
        _now(monkeypatch, "2024-11-01T09:30:00+08:00")
        real = gate.period_lock
        held = {"once": True}

        @contextmanager
        def contended(collection_id, period):
            if held.pop("once", False):
                yield False
                return
            with real(collection_id, period) as mine:
                yield mine
        monkeypatch.setattr(gate, "period_lock", contended)
        got = sc.deliver(AT, {"cp_clients": "C2"})
        sc.process()
        assert sc.owed("gate"), "precondition: the contended gate was left owed"
        points = _read()["cp-clients"][got["C2"]]
        assert [(p["on"], p["form"]) for p in points] == [("2024-11-01", "gating")], points
        assert points[0]["lead"] == "Checked, being gated"
        _now(monkeypatch, "2024-11-02T10:00:00+08:00")
        sc.run_owed()
        assert sc.owed("gate") == []
        points = _read()["cp-clients"][got["C2"]]
        assert [(p["on"], p["form"]) for p in points] == \
            [("2024-11-01", "gating"), ("2024-11-02", None)], points
