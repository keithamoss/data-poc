"""A bootstrap replays the collections that share a calendar as ONE
receipt-ordered stream, as the live pass does (REQ-PIPE-262).

The fast half: how streams are formed (criteria 1, 2, 9), the order a
stream's arrivals are processed in (criterion 3) and every collection's
scripted decisions played across the whole stream (criterion 4). The
history it produces is tests/test_bootstrap_equivalence.py's (criteria 12
to 14), which runs real bootstraps.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from qa_tools.common import bootstrap, schedule


@dataclass(frozen=True)
class _DS:
    dataset_id: str


def _config(monkeypatch, layout: dict[str, dict[str, str | None | Exception]]):
    """A registry of collections -> {dataset: calendar name, None for "no
    calendar", or an exception to raise} - so the grouping is seen to come
    from configuration rather than from names it knows."""
    monkeypatch.setattr(bootstrap, "_collection_datasets",
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

    monkeypatch.setattr(bootstrap, "_calendar_name", calendar_of)


class TestStreamsComeFromConfiguration:
    """Criteria 1, 2 and 9."""

    def test_the_real_configuration_puts_cp_and_ed_together_and_bdm_alone(self):
        assert bootstrap.streams(["bdm", "cp", "ed"]) == [["bdm"], ["cp", "ed"]]

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
        from qa_tools.tools import orchestrate

        played = []

        class Player:
            def __init__(self, name):
                self.name = name

            def before(self, arrival):
                played.append((self.name, arrival.run_id))

            def finish(self):
                played.append((self.name, "finish"))

        both = orchestrate.StreamPlayer([Player("cp"), Player("ed")])
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
        from qa_tools.common import arrival_lifecycle, replay_clock
        from qa_tools.tools import orchestrate

        seen = []
        monkeypatch.setattr(replay_clock, "_is_synthetic", lambda: True)
        monkeypatch.setattr(orchestrate, "_begin",
                            lambda cid, player=None: orchestrate._CollectionRun(
                                coll=cid, arrivals=[], manifest=[], steps=None,
                                prepare=None, player=type("P", (), {
                                    "before": lambda s, a: 0, "finish": lambda s: 0})(),
                                run_by="t", run_timestamp="t"))
        monkeypatch.setattr(orchestrate, "_end", lambda run, record_deliveries: {})
        monkeypatch.setattr(arrival_lifecycle, "process_stream",
                            lambda *a, **k: seen.append(replay_clock.active()))
        orchestrate.run_stream(["child-protection", "emergency-department"],
                               record_deliveries=False)
        assert seen == [True]
