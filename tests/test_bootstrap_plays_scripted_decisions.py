"""Scripted decisions are played by the bootstrap through the player a replay
takes, and the real pipeline neither builds a player nor plays one
(REQ-PIPE-383, signed by Keith 2026-11-14; criterion 7's tests).

The daily asset: Birth Registrations' first two generated deliveries, with a
scripts file holding one real decision the cut-down corpus can play - reject
the first supply an hour after it arrived. `mothman pipeline run` processes
them and records no decision by the synthetic person; the bootstrap's replay
of the same corpus plays it.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import equiv_support
import synthetic_unread_support as support
from bootstrap import decision_player
from qa_tools.common import arrival_lifecycle
from qa_tools.tools import orchestrate

UTC = timezone.utc


class TestAReplayGivenNoPlayerPlaysNothing:
    """Criteria 1 and 2."""

    def test_the_pipeline_builds_no_player(self, monkeypatch):
        """orchestrate._begin's default of scripted_decisions.Player is gone:
        run_pipeline with no player hands the lifecycle none."""
        from asset_model import arrivals, delivery
        from qa_tools.common import in_flight_log

        seen = {}
        monkeypatch.setattr(arrivals, "arrivals_for", lambda cid, prefix: [])
        monkeypatch.setattr(delivery, "survey", lambda: SimpleNamespace(in_flight=[]))
        monkeypatch.setattr(in_flight_log, "record", lambda *a, **k: None)
        monkeypatch.setattr(orchestrate, "get_run_by", lambda: "t@example.org")
        monkeypatch.setattr(orchestrate, "_end", lambda run, record_deliveries: {})
        monkeypatch.setattr(arrival_lifecycle, "process_all",
                            lambda arrivals, **k: seen.update(k) or [])
        orchestrate.run_pipeline("civil-registration")
        assert "player" in seen and seen["player"] is None

    def test_no_player_means_nothing_is_played_between_arrivals(self, monkeypatch):
        processed = []
        monkeypatch.setattr(arrival_lifecycle, "process",
                            lambda arrival, **k: processed.append(arrival.run_id) or [])
        arrivals = [SimpleNamespace(run_id=f"r{n}", received_at=datetime(2024, 1, n, tzinfo=UTC),
                                    delivery_name=f"d{n}") for n in (1, 2)]
        assert arrival_lifecycle.process_all(arrivals, steps=None, run_by="t",
                                             player=None) == []
        assert processed == ["r1", "r2"]

    def test_the_caller_s_player_runs_before_each_arrival_and_after_the_last(self, monkeypatch):
        order = []
        monkeypatch.setattr(arrival_lifecycle, "process",
                            lambda arrival, **k: order.append(arrival.run_id) or [])

        class Player:
            def before(self, arrival):
                order.append(f"before {arrival.run_id}")

            def finish(self):
                order.append("finish")
        arrivals = [SimpleNamespace(run_id=f"r{n}", received_at=datetime(2024, 1, n, tzinfo=UTC),
                                    delivery_name=f"d{n}") for n in (1, 2)]
        arrival_lifecycle.process_all(arrivals, steps=None, run_by="t", player=Player())
        assert order == ["before r1", "r1", "before r2", "r2", "finish"]


class TestAStreamsPlayerSpansItsCollections:
    """Criterion 7's REQ-PIPE-262 criterion 4: a decision of one collection is
    played before an arrival of ANOTHER collection received after its
    instant."""

    def test_played_before_the_other_collections_later_arrival(self, monkeypatch):
        decided_at = datetime(2024, 1, 2, 12, tzinfo=UTC)
        order = []

        class Player:
            def __init__(self, name, at=None):
                self.name, self.at = name, at

            def before(self, arrival):
                if self.at is not None and self.at <= arrival.received_at:
                    order.append(f"{self.name} decides")
                    self.at = None
                return 0

            def finish(self):
                return 0
        monkeypatch.setattr(arrival_lifecycle, "process",
                            lambda arrival, **k: order.append(arrival.run_id) or [])
        cp = [SimpleNamespace(run_id="cp_1", received_at=datetime(2024, 1, 1, tzinfo=UTC),
                              delivery_name="c1", sequence=1)]
        ed = [SimpleNamespace(run_id="ed_1", received_at=datetime(2024, 1, 3, tzinfo=UTC),
                              delivery_name="e1", sequence=1)]
        player = decision_player.StreamPlayer([Player("cp", decided_at), Player("ed")])
        arrival_lifecycle.process_stream(
            orchestrate.merged_arrivals({"child-protection": cp, "emergency-department": ed}),
            {"child-protection": (cp, None, None, "t", None),
             "emergency-department": (ed, None, None, "t", None)},
            player=player, results={"child-protection": [], "emergency-department": []})
        assert order == ["cp_1", "cp decides", "ed_1"]


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    root = tmp_path_factory.mktemp("plays_scripted_corpus")
    entries = support.corpus(root, "civil-registration", "birth-registrations", 2)
    return root, support.scripted("birth-registrations", entries[0]["period"])


def _decisions(snap) -> list[tuple[str, str]]:
    return list(zip(support.column(snap, "qa.decision", "action"),
                    support.column(snap, "qa.decision", "actor_kind")))


@pytest.fixture(scope="module")
def pipeline_run(corpus, tmp_path_factory, worker_id):
    """`mothman pipeline run --collection bdm` over the corpus, its scripts
    file present where the resolver points, into a fresh database."""
    from click.testing import CliRunner

    import cli.pipeline as pipeline_cli
    from cli import dashboard as dashboard_cli
    from dashboard import snapshot_dashboard

    root, scripts = corpus
    tree = support.tree_copy(tmp_path_factory.mktemp("plays_pipeline_run"), root)
    # The file run_into_fresh_database points the scripts reader at.
    (tree / "no_scripted_decisions.yaml").write_text(scripts)
    out = {}

    def run():
        mp = pytest.MonkeyPatch()
        try:
            mp.setattr(dashboard_cli, "_build_data", lambda: None)
            mp.setattr(dashboard_cli, "_embed", lambda: None)
            mp.setattr(snapshot_dashboard, "sync_local_snapshots", lambda: [])
            got = CliRunner().invoke(pipeline_cli.pipeline_group,
                                     ["run", "--collection", "bdm", "--sequential"])
            out["output"], out["exit_code"] = got.output, got.exit_code
            out["exception"] = got.exception
        finally:
            mp.undo()

    snap = equiv_support.run_into_fresh_database(tree, f"plays_pipeline_run_{worker_id}", run)
    snap.update(out)
    return snap


@pytest.fixture(scope="module")
def bootstrap_replay(corpus, tmp_path_factory, worker_id):
    """The bootstrap's replay of the same corpus and scripts."""
    from bootstrap import bootstrap as boot

    root, scripts = corpus
    tree = support.tree_copy(tmp_path_factory.mktemp("plays_bootstrap"), root)
    (tree / "no_scripted_decisions.yaml").write_text(scripts)
    return equiv_support.run_into_fresh_database(
        tree, f"plays_bootstrap_{worker_id}",
        lambda: boot._run_collection("bdm", sequential=True, record_deliveries=True))


class TestOnlyTheBootstrapPlaysThem:
    """Criteria 4, 5 and 6."""

    def test_pipeline_run_records_no_decision_by_the_synthetic_person(self, pipeline_run):
        assert pipeline_run["exit_code"] == 0, (pipeline_run["output"],
                                                pipeline_run["exception"])
        decisions = _decisions(pipeline_run)
        assert ("promote", "rule") in decisions, "the run must have processed the corpus"
        assert [d for d in decisions if d[1] != "rule"] == []

    def test_pipeline_run_says_it_played_none(self, pipeline_run):
        flat = " ".join(pipeline_run["output"].split())
        assert ("Scripted decisions are played only by `mothman pipeline bootstrap` - "
                "this run played none.") in flat

    def test_the_bootstraps_replay_plays_it_through_the_decision_path(self, bootstrap_replay):
        """The same scripts, played by the bootstrap's player: the reject is
        recorded as a person's decision - so the test above could fail."""
        assert ("reject", "person") in _decisions(bootstrap_replay)


#: The data asset this module's tests act for (C11, Keith 2026-11-02).
pytestmark = pytest.mark.asset("daily")
