"""Each lettered sibling scenario's own in-place-on date, between two of
its placement's events (REQ-GEN-201).

Nothing here needs a database or a generated history: criterion 7 says a
link is validated from configuration and the calendar alone, so these
tests hold the resolver to exactly that.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pytest
from click.testing import CliRunner

from cli import scenarios as scenarios_cli
from generator import scenario_injection as si
from qa_tools.common import asset_time
from qa_tools.common import scripted_decisions as sd

DS = "cp-carers"
ANCHOR = date(2026, 8, 20)


@dataclass(frozen=True)
class _Period:
    name: str
    date: date


def _periods() -> list[_Period]:
    days = [ANCHOR + timedelta(days=i - 10) for i in range(20)]
    return [_Period(name=d.isoformat(), date=d) for d in days]


def _script(**kw) -> sd.Script:
    base = dict(scenario="TS-75a", operation="reject", dataset_id=DS, reason="scripted",
                supply_index=0, after_hours=48, name="reject-it")
    base.update(kw)
    return sd.Script(**base)


def _injection(*links, also=("TS-75b",)) -> si.Injection:
    # Anchor index 10 is ANCHOR; arrival 0 that day at 14:00, arrival 1
    # five days later at 09:00.
    return si.Injection("TS-75a", DS, 10, "test", arrivals=(
        si.ExtraArrival(0, "14:00"), si.ExtraArrival(5, "09:00")),
        also_demonstrates=also, links=tuple(links))


def _at(day: date, hhmm: str) -> datetime:
    return asset_time.wall_clock(day, hhmm)


class TestALinkIsDatedFromItsFirstEvent:
    """Criteria 1, 2 and 4."""

    def test_zero_is_the_first_events_own_day(self):
        inj = _injection(si.Link("TS-75a", 0, 0, 1))
        [d] = si.link_dates(inj, si.resolve(_injection(), _periods()), scripts=[])
        assert d.on == ANCHOR
        assert d.problem is None
        assert d.first == ("arrival 0", _at(ANCHOR, "14:00"))

    def test_a_named_decision_bounds_a_link(self):
        """Its instant is the one the replay plays it at: its supply's
        receipt plus after_hours."""
        inj = _injection(si.Link("TS-75b", 1, 0, "reject-it"))
        [d] = si.link_dates(inj, si.resolve(_injection(), _periods()), scripts=[_script()])
        assert d.on == ANCHOR + timedelta(days=1)
        assert d.second == ("decision 'reject-it'", _at(ANCHOR, "14:00") + timedelta(hours=48))

    def test_a_sibling_scenarios_decision_counts(self):
        """A decision belonging to ANY id the placement demonstrates."""
        inj = _injection(si.Link("TS-75b", 1, 0, "reject-it"))
        [d] = si.link_dates(inj, si.resolve(_injection(), _periods()),
                            scripts=[_script(scenario="TS-75b")])
        assert d.problem is None

    def test_a_period_scoped_decision_is_timed_from_the_period_due(self, monkeypatch):
        due = _at(ANCHOR, "12:00")
        monkeypatch.setattr(sd, "_due_at", lambda ds, period: due)
        inj = _injection(si.Link("TS-75b", 2, "sub", 1))
        script = _script(name="sub", operation="substitute", supply_index=None,
                         scope=sd.PERIOD, stands_on=-1, after_hours=3)
        [d] = si.link_dates(inj, si.resolve(_injection(), _periods()), scripts=[script])
        assert d.first[1] == due + timedelta(hours=3)
        assert d.on == ANCHOR + timedelta(days=2)
        assert d.problem is None


class TestTheDateMustFallBetweenItsEvents:
    """Criterion 7: the END of the date, strictly between the two."""

    def test_a_date_past_its_second_event_is_refused_naming_both(self):
        inj = _injection(si.Link("TS-75b", 2, 0, "reject-it"))
        [d] = si.link_dates(inj, si.resolve(_injection(), _periods()), scripts=[_script()])
        assert "TS-75a's link for TS-75b" in d.problem
        assert "arrival 0 at " + _at(ANCHOR, "14:00").isoformat() in d.problem
        assert "decision 'reject-it' at" in d.problem

    def test_the_end_of_the_day_is_what_is_compared(self):
        """A second event at 10:00 the next day is after that day's START
        and before its END - so a date read as its start would wrongly
        pass."""
        inj = _injection(si.Link("TS-75b", 1, 0, "reject-it"))
        [d] = si.link_dates(inj, si.resolve(_injection(), _periods()),
                            scripts=[_script(after_hours=20)])
        assert d.second[1] == _at(ANCHOR + timedelta(days=1), "10:00")
        assert d.problem is not None

    def test_a_date_before_its_first_event_is_refused(self):
        inj = _injection(si.Link("TS-75b", -1, 0, 1))
        [d] = si.link_dates(inj, si.resolve(_injection(), _periods()), scripts=[])
        assert d.problem is not None


class TestALinkNamingNothingIsRefused:
    """Criterion 8, each naming the link."""

    @pytest.mark.parametrize("link, scripts, says", [
        (si.Link("TS-99", 0, 0, 1), [], "TS-99 is not a scenario this placement demonstrates"),
        (si.Link("TS-75b", 0, 0, 7), [], "arrival 7 does not exist"),
        (si.Link("TS-75b", 0, 0, "nope"), [], "is named 'nope'"),
        (si.Link("TS-75b", 0, 0, "reject-it"), [_script(scenario="TS-12")],
         "is named 'reject-it'"),
    ])
    def test_refused(self, link, scripts, says):
        [d] = si.link_dates(_injection(link), si.resolve(_injection(), _periods()),
                            scripts=scripts)
        assert says in d.problem
        assert "TS-75a's link for" in d.problem


class TestADecisionNameIsUniqueWithinItsScenario:
    """Criterion 3."""

    def test_the_name_is_read_from_the_script(self, tmp_path):
        path = tmp_path / "s.yaml"
        path.write_text("decisions:\n  - scenario: TS-1\n    operation: reject\n"
                        "    dataset: cp-carers\n    supply: 0\n    reason: r\n"
                        "    name: reject-it\n")
        assert sd.load(path)[0].name == "reject-it"

    def test_two_decisions_of_one_scenario_with_one_name_are_refused_naming_both(self):
        found = sd.problems([_script(), _script(operation="promote")],
                            registered={"TS-75a"})
        assert any("decisions 1 and 2" in p and "'reject-it'" in p for p in found)

    def test_the_same_name_in_two_scenarios_is_fine(self):
        assert sd.problems([_script(), _script(scenario="TS-75b")],
                           registered={"TS-75a", "TS-75b"}) == []


class TestThePlacementFileCarriesEachLinkedDate:
    """Criteria 5, 6 and 9: the generator writes the date link_dates()
    resolves, and an unlinked id keeps the default."""

    def test_each_sibling_gets_its_own_date(self, tmp_path, monkeypatch):
        monkeypatch.setitem(si._ALSO, "TS-75a", ("TS-75b", "TS-75c"))
        inj = _injection(si.Link("TS-75a", 0, 0, 1), si.Link("TS-75b", 1, 0, "reject-it"),
                         also=("TS-75b", "TS-75c"))
        placed = si.resolve(inj, _periods(), scripts=[_script()])
        path = si.write_placements([placed], tmp_path / "p.json")
        by_id = {r["scenario_id"]: r for r in json.loads(path.read_text())["placements"]}
        assert by_id["TS-75a"]["in_place_on"] == ANCHOR.isoformat()
        assert by_id["TS-75b"]["in_place_on"] == (ANCHOR + timedelta(days=1)).isoformat()
        # No link: the latest day the placement has anything to show.
        assert by_id["TS-75c"]["in_place_on"] == (ANCHOR + timedelta(days=5)).isoformat()

    def test_a_placement_with_no_links_is_unchanged(self):
        placed = si.resolve(_injection(), _periods())
        assert placed.as_record()["in_place_on"] == (ANCHOR + timedelta(days=5)).isoformat()

    def test_the_generator_refuses_a_link_validate_would(self):
        inj = _injection(si.Link("TS-75b", 2, 0, "reject-it"))
        with pytest.raises(si.CannotPlace, match="TS-75a's link for TS-75b"):
            si.resolve(inj, _periods(), scripts=[_script()])

    def test_the_scenario_map_shows_each_siblings_date(self, tmp_path, monkeypatch):
        """Criterion 10: the map and the panel read each id's own record."""
        from qa_tools.common import scenario_map

        monkeypatch.setitem(si._ALSO, "TS-75a", ("TS-75b",))
        inj = _injection(si.Link("TS-75b", 1, 0, "reject-it"))
        placed = si.resolve(inj, _periods(), scripts=[_script()])
        back = scenario_map.read_placements(si.write_placements([placed], tmp_path / "p.json"))
        assert back["TS-75b"].in_place_on == (ANCHOR + timedelta(days=1)).isoformat()
        assert back["TS-75a"].in_place_on == (ANCHOR + timedelta(days=5)).isoformat()
        # The panel's feed is the map's data block, one entry per id.
        from qa_tools.common import scenarios as scenarios_mod

        register = [s for s in scenarios_mod.parse_register() if s.id in ("TS-1", "TS-4")]
        back = {"TS-1": back["TS-75b"], "TS-4": back["TS-75a"]}
        block = json.loads(scenario_map._data_block(register, back)
                           .split("\n", 1)[1].rsplit("\n", 1)[0])
        dates = {e["id"]: e["coordinates"]["inPlaceOn"] for e in block["scenarios"]}
        assert dates == {"TS-1": (ANCHOR + timedelta(days=1)).isoformat(),
                         "TS-4": (ANCHOR + timedelta(days=5)).isoformat()}


class TestValidateRefusesABadLink:
    """Criteria 7 and 8 through `mothman scenarios validate`, with no
    database and no generated history."""

    def test_it_fails_naming_the_link(self, monkeypatch):
        monkeypatch.setattr(si, "INJECTIONS", [_injection(si.Link("TS-75b", 0, 0, 9))])
        monkeypatch.setattr(si, "generated_periods", lambda ds: _periods())
        result = CliRunner().invoke(scenarios_cli.scenarios_group, ["validate"])
        assert result.exit_code != 0
        assert "TS-75a's link for TS-75b" in result.output
        assert "arrival 9 does not exist" in result.output

    def test_the_committed_configuration_passes(self):
        result = CliRunner().invoke(scenarios_cli.scenarios_group, ["validate"])
        assert result.exit_code == 0, result.output


class TestAnIndexPastAnUnrecognisedArrivalIsRefused:
    """post-build-review #169 finding 1 (Keith: refuse at generation): a
    script's `supply N` indexes the placement's RECORDED supplies, which
    skip an arrival recognition did not match, so every later index would
    name a different file than the link's `arrival N`."""

    def _placed(self, recognised_runs):
        placed = si.resolve(_injection(), _periods())
        for arrival, run in zip(placed.arrivals, recognised_runs):
            if run:
                arrival["run_id"] = run
        return placed

    def test_a_script_past_the_gap_is_refused_naming_the_scenario(self):
        placed = self._placed([None, "run_2"])
        with pytest.raises(si.CannotPlace, match="TS-75a.*arrival 0"):
            si.check_every_index_has_its_supply(
                [placed], injections=[_injection()], scripts=[_script(supply_index=1)])

    def test_a_link_past_the_gap_is_refused(self):
        placed = self._placed(["run_1", None])
        with pytest.raises(si.CannotPlace, match="TS-75a.*arrival 1"):
            si.check_every_index_has_its_supply(
                [placed], injections=[_injection(si.Link("TS-75a", 0, 0, 1))], scripts=[])

    def test_nothing_indexing_past_the_gap_is_fine(self):
        placed = self._placed(["run_1", None])
        si.check_every_index_has_its_supply(
            [placed], injections=[_injection()], scripts=[_script(supply_index=0)])

    def test_every_arrival_recognised_is_fine(self):
        placed = self._placed(["run_1", "run_2"])
        si.check_every_index_has_its_supply(
            [placed], injections=[_injection(si.Link("TS-75a", 0, 0, 1))],
            scripts=[_script(supply_index=1)])


class TestANameIsUniqueAcrossAPlacement:
    """post-build-review #169 finding 2 (Keith: unique per placement): a
    link looks names up across every sibling, so validate refuses one name
    on two siblings' decisions rather than letting a link find two."""

    def test_two_siblings_with_one_name_are_refused_naming_both(self):
        found = sd.problems([_script(), _script(scenario="TS-75b")],
                            registered={"TS-75a", "TS-75b"},
                            placement_of={"TS-75a": "TS-75a", "TS-75b": "TS-75a"})
        assert any("decisions 1 and 2" in p and "'reject-it'" in p
                   and "share a placement" in p for p in found), found

    def test_the_committed_placements_group_siblings(self):
        groups = si.placement_of()
        for injection in si.INJECTIONS:
            for also in injection.also_demonstrates:
                assert groups[also] == groups[injection.scenario_id]

    def test_a_link_still_refuses_an_ambiguous_name(self):
        inj = _injection(si.Link("TS-75b", 1, 0, "reject-it"))
        [d] = si.link_dates(inj, si.resolve(_injection(), _periods()),
                            scripts=[_script(), _script(scenario="TS-75b")])
        assert "named 'reject-it'" in d.problem and "rename one" in d.problem


class TestALinkIsWellFormed:
    """post-build-review #169 findings 3 and 4."""

    def test_a_fractional_day_count_is_refused(self):
        [d] = si.link_dates(_injection(si.Link("TS-75a", 0.9, 0, 1)),
                            si.resolve(_injection(), _periods()), scripts=[])
        assert "whole number of asset days" in d.problem

    def test_a_bool_event_is_refused_as_neither_kind(self):
        [d] = si.link_dates(_injection(si.Link("TS-75a", 0, True, 1)),
                            si.resolve(_injection(), _periods()), scripts=[])
        assert "an arrival index or a decision name" in d.problem

    def test_an_out_of_window_refusal_says_what_to_change(self):
        inj = _injection(si.Link("TS-75b", 2, 0, "reject-it"))
        [d] = si.link_dates(inj, si.resolve(_injection(), _periods()), scripts=[_script()])
        assert "move the link's date" in d.problem

    def test_a_decision_that_cannot_be_timed_is_refused(self, monkeypatch):
        monkeypatch.setattr(sd, "_due_at", lambda ds, period: None)
        inj = _injection(si.Link("TS-75b", 0, 0, "sub"))
        script = _script(name="sub", operation="substitute", supply_index=None,
                         scope=sd.PERIOD, stands_on=-1)
        [d] = si.link_dates(inj, si.resolve(_injection(), _periods()), scripts=[script])
        assert "cannot be timed" in d.problem


class TestTheGeneratedPeriodsAreEachGenerators:
    """post-build-review #169 finding 5, and the real routing every CLI
    test above monkeypatches."""

    def test_each_collection_gets_its_own_generators_periods(self):
        from generator.collections import child_protection as cp_provider
        from generator.collections import civil_registration as generate_runs

        assert si.generated_periods("cp-carers") == cp_provider.generated_periods()
        assert si.generated_periods("birth-registrations") == generate_runs.generated_periods()
        assert si.generated_periods("cp-carers") != si.generated_periods("birth-registrations")

    def test_a_dataset_no_generator_writes_is_refused(self):
        with pytest.raises(si.CannotPlace, match="no generator"):
            si.generated_periods("no-such-dataset")


class TestALinkTimesADecisionWhereTheReplayPlaysIt:
    """Criterion 9's parity, held against the replay's own timing for a
    period-scoped decision (the critic matched supply-scoped ones against
    the real history)."""

    def test_period_scoped(self, monkeypatch):
        from types import SimpleNamespace

        due = _at(ANCHOR, "12:00")
        monkeypatch.setattr(sd, "_due_at", lambda ds, period: due)
        monkeypatch.setattr("qa_tools.common.slots.relative_period", lambda *a, **k: "P-1")
        script = _script(name="sub", operation="substitute", supply_index=None,
                         scope=sd.PERIOD, stands_on=-1, after_hours=7)
        placed = si.resolve(_injection(), _periods())
        [d] = si.link_dates(_injection(si.Link("TS-75b", 0, "sub", 1)), placed,
                            scripts=[script])
        timed, _ = sd._timed_by_period(script, SimpleNamespace(period=placed.period))
        assert d.first[1] == timed.at
