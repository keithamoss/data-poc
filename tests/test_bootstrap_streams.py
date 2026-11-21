"""A bootstrap replays the collections that share a calendar as ONE
receipt-ordered stream, as the live pass does (REQ-PIPE-262).

The fast half: how streams are formed (criteria 1, 2, 9), the order a
stream's arrivals are processed in (criterion 3) and every collection's
scripted decisions played across the whole stream (criterion 4). Nothing
here runs a real bootstrap: criteria 13 and 14, which only
tests/test_bootstrap_equivalence.py proved, were retired with it
(REQ-TEST-393, Keith 2026-11-15) after its corpus fixture had failed since
the asset split.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from bootstrap import bootstrap
from asset_model import schedule
from qa_tools.common import streams as streams_mod


@dataclass(frozen=True)
class _DS:
    dataset_id: str


def _config(monkeypatch, layout: dict[str, dict[str, str | None | Exception]]):
    """A registry of collections -> {dataset: calendar name, None for "no
    calendar", or an exception to raise} - so the grouping is seen to come
    from configuration rather than from names it knows."""
    # THE GROUPING IS THE PIPELINE'S since REQ-GEN-381 criterion 5
    # (qa_tools/common/streams.py); the bootstrap asks it.
    monkeypatch.setattr(streams_mod, "_collection_datasets",
                        lambda short: [_DS(d) for d in layout[short]])

    def calendar_of(dataset_id):
        for datasets in layout.values():
            if dataset_id in datasets:
                value = datasets[dataset_id]
                if value is None:
                    raise schedule.NoCalendarAgreed(dataset_id, "a one-off extraction")
                if isinstance(value, Exception):
                    raise value
                return value
        raise AssertionError(dataset_id)

    monkeypatch.setattr(streams_mod, "_calendar_name", calendar_of)


class TestStreamsComeFromConfiguration:
    """Criteria 1, 2 and 9."""

    @pytest.mark.parametrize("shorts, expected", [
        # Each asset's own collections (the asset split): the quarterly three
        # share a calendar and are one stream; Birth Registrations is alone.
        pytest.param(["cp", "ed", "lp"], [["cp", "ed", "lp"]], marks=pytest.mark.asset("quarterly"),
                     id="quarterly"),
        pytest.param(["bdm"], [["bdm"]], marks=pytest.mark.asset("daily"), id="daily")])
    def test_the_real_configuration_puts_cp_and_ed_together_and_bdm_alone(self, shorts,
                                                                            expected):
        assert bootstrap.streams(shorts) == expected

    def test_moving_a_collection_to_another_calendar_moves_it_to_another_stream(
            self, monkeypatch):
        _config(monkeypatch, {"a": {"a1": "daily"}, "b": {"b1": "quarterly"},
                              "c": {"c1": "daily"}})
        assert bootstrap.streams(["a", "b", "c"]) == [["a", "c"], ["b"]]

    def test_sharing_is_transitive(self, monkeypatch):
        """a shares monthly with b, b shares quarterly with c: one stream."""
        _config(monkeypatch, {"a": {"a1": "monthly"},
                              "b": {"b1": "monthly", "b2": "quarterly"},
                              "c": {"c1": "quarterly"}, "d": {"d1": "daily"}})
        assert bootstrap.streams(["a", "b", "c", "d"]) == [["a", "b", "c"], ["d"]]

    def test_a_dataset_with_no_calendar_joins_nothing(self, monkeypatch):
        _config(monkeypatch, {"a": {"a1": "quarterly"}, "x": {"x1": None},
                              "b": {"b1": "quarterly", "b2": None}})
        assert bootstrap.streams(["a", "x", "b"]) == [["a", "b"], ["x"]]

    def test_an_unresolvable_calendar_is_refused_naming_collection_and_dataset(
            self, monkeypatch):
        _config(monkeypatch, {"a": {"a1": "quarterly"},
                              "b": {"b1": schedule.ScheduleConfigError("no such calendar")}})
        with pytest.raises(bootstrap.StreamRefused, match=r"'b'.*b1|b1.*'b'"):
            bootstrap.streams(["a", "b"])

    def test_the_refusal_comes_before_anything_is_generated(self, monkeypatch):
        _config(monkeypatch, {"a": {"a1": schedule.ScheduleConfigError("nope")}})
        generated = []
        monkeypatch.setattr(bootstrap, "_shorts", lambda: ["a"])
        monkeypatch.setattr(bootstrap, "_adapter", lambda short: object())
        # The fake collection reads nothing (REQ-PIPE-336 criterion 7's step
        # resolves real registry names, which 'a' is not).
        monkeypatch.setattr(bootstrap, "with_what_it_reads", lambda names, say=None: names)
        monkeypatch.setattr(bootstrap, "_generate", lambda *a, **k: generated.append(a))
        result = bootstrap.bootstrap(force=True)
        assert result.refused and "a1" in result.reason
        assert generated == []


@dataclass(frozen=True)
class _Arrival:
    run_id: str
    received_at: datetime
    sequence: int = 0


def _at(day, hour=9):
    return datetime(2015, 11, day, hour, tzinfo=timezone.utc)


class TestAStreamIsProcessedInTheLivePassesOrder:
    """Criteria 3 and 4."""

    def test_arrivals_interleave_by_receipt_then_sequence_then_run_id(self):
        from qa_tools.tools import orchestrate

        cp = [_Arrival("cp_run_1", _at(1)), _Arrival("cp_run_2", _at(3))]
        ed = [_Arrival("ed_run_1", _at(2)), _Arrival("ed_run_2", _at(3)),
              _Arrival("ed_run_0", _at(1), sequence=1)]
        merged = orchestrate.merged_arrivals({"child-protection": cp,
                                              "emergency-department": ed})
        assert [(c, a.run_id) for c, a in merged] == [
            ("child-protection", "cp_run_1"), ("emergency-department", "ed_run_0"),
            ("emergency-department", "ed_run_1"), ("child-protection", "cp_run_2"),
            ("emergency-department", "ed_run_2")]

    def test_every_collections_decisions_play_before_any_later_arrival(self):
        from bootstrap import decision_player

        played = []

        class Player:
            def __init__(self, name):
                self.name = name

            def before(self, arrival):
                played.append((self.name, arrival.run_id))

            def finish(self):
                played.append((self.name, "finish"))

        both = decision_player.StreamPlayer([Player("cp"), Player("ed")])
        both.before(_Arrival("ed_run_1", _at(2)))
        both.finish()
        assert played == [("cp", "ed_run_1"), ("ed", "ed_run_1"),
                          ("cp", "finish"), ("ed", "finish")]


class TestAStreamRunsOnTheReplayClock:
    """A stream is a replay like a one-collection run (REQ-PIPE-262 criterion
    3): on a synthetic asset it runs on the replay clock, so each arrival is
    filed under the agreement as it stood at its receipt (REQ-PIPE-170
    criterion 23) and stamped then. Found when a full bootstrap's correction
    proposed no moves: every merged arrival had been filed under the
    corrected calendar, on the wall clock."""

    def test_the_replay_clock_is_running_while_a_stream_is_processed(self, monkeypatch):
        """INSTALLED BY THE BOOTSTRAP AROUND ITS OWN CALL (REQ-PIPE-382
        criterion 11), with the stream's one combined player passed in
        (REQ-PIPE-383 criterion 2) - the pipeline installs and builds
        neither."""
        from bootstrap import decision_player, replay_clock
        from qa_tools.tools import orchestrate

        seen = []
        monkeypatch.setattr(decision_player, "Player", lambda cid: ("player of", cid))
        monkeypatch.setattr(orchestrate, "run_stream",
                            lambda ids, **k: seen.append((replay_clock.active(), ids,
                                                          k["player"].players)))
        bootstrap._run_stream("cp+ed", sequential=True)
        assert seen == [(True, ["child-protection", "emergency-department"],
                         [("player of", "child-protection"),
                          ("player of", "emergency-department")])]
        assert not replay_clock.active()


#: The data asset this module's tests act for, unless a test says otherwise
#: (C11, Keith 2026-11-02: every test module names its asset).
pytestmark = pytest.mark.asset("quarterly")
