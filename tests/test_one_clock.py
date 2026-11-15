"""The real pipeline reads the time through one clock in asset_model/ and
announces neutral clock events that only an installed replay acts on
(REQ-PIPE-382, signed by Keith 2026-11-14; criterion 13's tests).

The pipeline never asks whether a replay is running: it asks asset_time for
the time, says what happened - an arrival received at R is being processed, a
file received at R is being staged, a decision takes effect at T - and asks
the clock when a decision takes effect. The wall clock and a pinned clock
ignore every event and answer that question with now; only the bootstrap's
replay clock (bootstrap/replay_clock.py) acts on them.
"""
from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from asset_model import asset_time
from bootstrap import correction_replay, replay_clock
from scenarios import promotion_lag

ROOT = Path(__file__).resolve().parent.parent
PERTH = timezone(timedelta(hours=8))
LONG_AGO = datetime(2023, 4, 3, 9, 0, tzinfo=PERTH)
PINNED = "2024-06-30T12:00:00+08:00"


class _FixedClock(asset_time.Clock):
    """A clock a test installs: one instant, every event ignored."""

    def __init__(self, at):
        self.at = at

    def now(self):
        return self.at


def _log_delivery(name: str, received_at: datetime):
    """One delivery recorded by the real writer; its recorded_at."""
    from asset_model import delivery as delivery_tree
    from qa_tools.common import delivery_log, qa_store, supply_db

    delivery_log.record(
        SimpleNamespace(name=name, files=[], anomalies=[], received_at=received_at,
                        received_from=delivery_tree.RECEIVED_FROM_OUR_CLOCK),
        SimpleNamespace(by_dataset={}, contested={}, collections=[]))
    with supply_db.connect(read_only=True, label="test-one-clock") as conn:
        return conn.execute(f'SELECT recorded_at FROM "{qa_store.SCHEMA}".delivery '
                            "WHERE name = ?", [name]).fetchall()[0][0]


def _arrival(received_at=LONG_AGO, run_id="cp_clients__probe"):
    return SimpleNamespace(received_at=received_at, run_id=run_id,
                           files_by_dataset={"cp-clients": "x"})


@pytest.fixture
def no_next_receipt(monkeypatch):
    from qa_tools.common import promotion

    monkeypatch.setattr(promotion, "next_receipt", lambda arrival: None)


class TestARecordIsStampedByTheOneClock:
    """Criteria 1, 2 and 5."""

    def test_a_real_pipeline_module_stamps_with_an_installed_clock(self, clean_delivery_log):
        at = datetime(2019, 1, 2, 3, 4, 5, tzinfo=PERTH)
        with asset_time.installed(_FixedClock(at)):
            recorded = _log_delivery("installed-clock", LONG_AGO)
        assert recorded == at

    def test_with_no_clock_installed_it_is_the_wall_clock(self, clean_delivery_log):
        before = datetime.now(timezone.utc)
        recorded = _log_delivery("wall-clock", LONG_AGO)
        assert before <= recorded <= datetime.now(timezone.utc)

    def test_a_replay_stamps_a_delivery_as_received(self, clean_delivery_log):
        """The delivery is recorded under the 'received at R' event, which the
        replay clock anchors on."""
        with replay_clock.replaying():
            recorded = _log_delivery("replayed", LONG_AGO)
        assert LONG_AGO <= recorded < LONG_AGO + timedelta(seconds=5)

    def test_every_reader_of_now_reads_the_installed_clock(self):
        at = datetime(2019, 1, 2, tzinfo=PERTH)
        with asset_time.installed(_FixedClock(at)):
            assert asset_time.now() == at
        assert asset_time.now() != at


@pytest.mark.usefixtures("no_next_receipt")
class TestWhenAPromotionTakesEffect:
    """Criteria 3 and 4, and the two reversals (criterion 14)."""

    def test_on_the_wall_clock_it_is_now(self):
        from qa_tools.tools import orchestrate

        before = asset_time.now()
        got = datetime.fromisoformat(orchestrate.effective_at_of("child-protection",
                                                                 _arrival()))
        assert before <= got <= asset_time.now()

    def test_on_a_pinned_clock_it_is_the_pinned_instant(self, monkeypatch):
        from qa_tools.tools import orchestrate

        monkeypatch.setenv(asset_time.PINNED_NOW_VARIABLE, PINNED)
        got = orchestrate.effective_at_of("child-protection", _arrival())
        assert datetime.fromisoformat(got) == datetime.fromisoformat(PINNED)

    def test_a_retried_package_gate_on_a_real_asset_takes_effect_at_the_retry(
            self, monkeypatch):
        """REVERSAL 2 (Keith, 2026-11-14): the retry is the instant the
        decision is actually made, not its first attempt's."""
        from qa_tools.tools import orchestrate

        monkeypatch.setenv(asset_time.PINNED_NOW_VARIABLE, PINNED)
        first = orchestrate.effective_at_of("child-protection", _arrival())
        monkeypatch.setenv(asset_time.PINNED_NOW_VARIABLE, "2024-07-01T09:30:00+08:00")
        retry = orchestrate.effective_at_of("child-protection", _arrival())
        assert first == datetime.fromisoformat(PINNED).isoformat()
        assert retry == "2024-07-01T09:30:00+08:00"

    def test_a_replayed_promotion_takes_receipt_plus_the_seeded_lag(self):
        window = timedelta(hours=4)
        nxt = LONG_AGO + timedelta(days=1)
        with replay_clock.replaying():
            replay_clock.anchor(LONG_AGO)
            lags = []
            for n in range(40):
                got = asset_time.when_effective(LONG_AGO, run_id=f"run_{n}", next_receipt=nxt,
                                                claim_window=window)
                assert got == promotion_lag.effective_at(LONG_AGO, seed=f"run_{n}",
                                                         before=nxt, within=window)
                lags.append(got - LONG_AGO)
            # THE REPLAY CLOCK READS ITS OWN SIMULATED INSTANT meanwhile.
            assert LONG_AGO <= asset_time.now() < LONG_AGO + timedelta(seconds=5)
        assert all(timedelta(hours=1) <= lag <= window for lag in lags)
        assert len(set(lags)) > 30, "spread across the claim window"

    def test_a_replayed_promotion_lands_before_the_next_receipt(self):
        nxt = LONG_AGO + timedelta(seconds=30)
        with replay_clock.replaying():
            got = asset_time.when_effective(LONG_AGO, run_id="run_lag_probe",
                                            next_receipt=nxt)
        assert LONG_AGO <= got < nxt

    def test_no_replayed_decision_takes_effect_after_the_real_present(self):
        received = asset_time.real_now() - timedelta(minutes=2)
        with replay_clock.replaying():
            got = asset_time.when_effective(received, run_id="run_lag_probe")
        assert received <= got <= asset_time.real_now()

    def test_a_replayed_retried_package_gate_takes_effect_when_its_first_attempt_did(self):
        """post-build-review #274 D1, kept for a replay: the answer comes from
        the arrival that completed the package, whenever it is asked."""
        from qa_tools.tools import orchestrate

        with replay_clock.replaying():
            replay_clock.anchor(LONG_AGO + timedelta(hours=1))
            first = orchestrate.effective_at_of("child-protection", _arrival())
            replay_clock.anchor(LONG_AGO + timedelta(days=5))
            retry = orchestrate.effective_at_of("child-protection", _arrival())
        assert first == retry
        assert datetime.fromisoformat(first) > LONG_AGO


class TestTheEvents:
    """Criteria 8 and 9."""

    def test_the_wall_clock_ignores_every_event(self):
        before = asset_time.now()
        with asset_time.processing_arrival(LONG_AGO):
            asset_time.receiving(LONG_AGO)
            asset_time.taking_effect(LONG_AGO)
            assert asset_time.now() >= before
        assert asset_time.now() >= before

    def test_a_pinned_clock_ignores_every_event(self, monkeypatch):
        monkeypatch.setenv(asset_time.PINNED_NOW_VARIABLE, PINNED)
        with asset_time.processing_arrival(LONG_AGO):
            asset_time.receiving(LONG_AGO)
            asset_time.taking_effect("2030-01-01T00:00:00+08:00")
            assert asset_time.now() == datetime.fromisoformat(PINNED)

    def test_an_installed_replay_clock_acts_on_each(self):
        later = LONG_AGO + timedelta(days=2)
        with replay_clock.replaying():
            with asset_time.processing_arrival(LONG_AGO):
                assert LONG_AGO <= asset_time.now() < LONG_AGO + timedelta(seconds=5)
            asset_time.receiving(later)
            assert later <= asset_time.now() < later + timedelta(seconds=5)
            asset_time.taking_effect(later + timedelta(hours=3))
            assert asset_time.now() >= later + timedelta(hours=3)
            asset_time.taking_effect(LONG_AGO)
            assert asset_time.now() >= later + timedelta(hours=3), "never backwards"

    def test_a_replay_reads_the_pinned_instant_until_its_first_event(self, monkeypatch):
        """Criterion 12."""
        monkeypatch.setenv(asset_time.PINNED_NOW_VARIABLE, PINNED)
        with replay_clock.replaying():
            assert asset_time.now() == datetime.fromisoformat(PINNED)
            asset_time.receiving(LONG_AGO)
            assert LONG_AGO <= asset_time.now() < LONG_AGO + timedelta(seconds=5)

    def test_the_pipeline_announces_without_asking_whether_a_replay_runs(self):
        """Criterion 11: no real pipeline module reads replay_clock at all -
        an architecture rule with no behaviour to observe beyond the imports
        gate, so read from the source (rule 1's exception)."""
        found = []
        for top in ("qa_tools", "pipeline", "dashboard", "aws"):
            for path in (ROOT / top).rglob("*.py"):
                text = path.read_text()
                if "replay_clock" in text or "on_replay_clock" in text:
                    found.append(str(path.relative_to(ROOT)))
        assert (ROOT / "qa_tools").is_dir()
        assert found == []


class TestTheAgreementAsItStood:
    """Criterion 10: staged only within an arrival's event context."""

    def test_staged_for_the_span_of_the_context_in_a_replay(self, monkeypatch):
        seen = []

        @contextlib.contextmanager
        def staged_ctx():
            seen.append("staged")
            yield
            seen.append("restored")
        monkeypatch.setattr(correction_replay, "staged", lambda instant: staged_ctx())
        with replay_clock.replaying():
            with asset_time.processing_arrival(LONG_AGO):
                assert seen == ["staged"]
            assert seen == ["staged", "restored"]

    def test_the_wall_clock_stages_nothing(self, monkeypatch):
        def never(_instant):
            raise AssertionError("the wall clock staged a correction")
        monkeypatch.setattr(correction_replay, "staged", never)
        with asset_time.processing_arrival(LONG_AGO):
            pass

    def test_arrival_lifecycle_imports_nothing_of_correction_replay(self):
        text = (ROOT / "qa_tools" / "common" / "arrival_lifecycle.py").read_text()
        assert "correction_replay" not in text and "processing_arrival" in text


_REFUSED_WITHOUT_THE_BOOTSTRAP = textwrap.dedent("""
    import importlib.abc
    import os
    import sys
    from pathlib import Path


    class Blocked(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] in ("bootstrap", "scenarios", "generator"):
                raise ImportError(f"{name} is not part of this deployment")
            return None


    sys.meta_path.insert(0, Blocked())
    from asset_model import asset_time, assets

    assets.use_folder(Path(sys.argv[1]))
    assert not asset_time.declared_synthetic()
    try:
        import bootstrap  # noqa: F401
    except ImportError:
        pass
    else:
        raise SystemExit("the bootstrap package was importable")
    try:
        with asset_time.installed(asset_time.Clock()):
            raise SystemExit("installed on a real asset")
    except asset_time.ClockInstallRefused as exc:
        print("refused:", exc)
    os.environ[asset_time.PINNED_NOW_VARIABLE] = "2024-06-30T12:00:00+08:00"
    try:
        asset_time.now()
        raise SystemExit("pinned on a real asset")
    except asset_time.PinnedClockRefused as exc:
        print("pinned refused:", exc)
""")


class TestTheInstallationIsRefusedOnARealAsset:
    """Criteria 6 and 12."""

    def test_refused_in_a_process_where_the_bootstrap_cannot_be_imported(self, tmp_path):
        import asset_folders
        import yaml

        folder = tmp_path / "real-asset"
        folder.mkdir()
        from asset_model import assets

        doc = yaml.safe_load(assets.selected().data_asset_yaml.read_text())
        assert doc.get("synthetic") is True, "precondition: the real asset is synthetic"
        doc.pop("synthetic")
        (folder / "data-asset.yaml").write_text(yaml.safe_dump(doc, sort_keys=False))
        asset_folders.complete(folder)
        script = tmp_path / "probe.py"
        script.write_text(_REFUSED_WITHOUT_THE_BOOTSTRAP)
        env = {k: v for k, v in os.environ.items() if k != asset_time.PINNED_NOW_VARIABLE}
        env["PYTHONPATH"] = str(ROOT)
        got = subprocess.run([sys.executable, str(script), str(folder)], cwd=tmp_path,
                             env=env, capture_output=True, text=True, timeout=120)
        assert got.returncode == 0, got.stdout + got.stderr
        assert "refused:" in got.stdout and "synthetic: true" in got.stdout
        assert "pinned refused:" in got.stdout

    def test_a_replay_refused_in_process_too(self, monkeypatch):
        monkeypatch.setattr(asset_time, "declared_synthetic", lambda: False)
        with pytest.raises(asset_time.ClockInstallRefused, match="synthetic: true"):
            with replay_clock.replaying():
                pass
        assert not replay_clock.active()


class TestOneReaderOfTheDeclaration:
    """Criterion 7: the reset's and the clock's readers ask the one reader."""

    @pytest.mark.parametrize("value", [True, False])
    def test_each_reader_follows_it(self, monkeypatch, value):
        from bootstrap import checkpoints, synthetic_reset

        monkeypatch.setattr(asset_time, "declared_synthetic", lambda: value)
        assert synthetic_reset.is_synthetic() is value
        if value:
            checkpoints.require_synthetic()
        else:
            with pytest.raises(checkpoints.CheckpointRefused):
                checkpoints.require_synthetic()


#: The data asset this module's tests act for (C11, Keith 2026-11-02).
pytestmark = pytest.mark.asset("quarterly")
