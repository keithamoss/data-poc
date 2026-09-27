"""Placing the register's scenarios into the generated history
(REQ-GEN-044).

WHAT THESE TESTS ARE FOR, given the requirement's own point is that a
passing test is NOT the evidence: they cover the placement rule - where
a scenario lands, that it lands in the same place every time, and that a
history which cannot host one is refused rather than emitted. The
scenario itself being visible on the real dashboard is the deliverable,
and no test can stand in for it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pytest

from generator import scenario_injection as si


@dataclass(frozen=True)
class _Period:
    """The two fields resolve() reads off a real schedule.Period."""

    name: str
    date: date


def _daily(n: int, start: date = date(2026, 8, 24)) -> list[_Period]:
    days = [start + timedelta(days=i) for i in range(n)]
    return [_Period(name=d.isoformat(), date=d) for d in days]


@dataclass(frozen=True)
class _Recognised:
    """The three fields the two read-back helpers use."""

    run_id: str
    delivery_name: str
    received_at: str | None = None


class TestAScenarioLandsWhereItsAnchorSays:
    """Criteria 1 and 3."""

    def test_a_negative_anchor_counts_from_the_recent_end(self):
        periods = _daily(30)
        placed = si.resolve(si.Injection("TS-x", "d", -3, "cfg"), periods)
        assert placed.period == periods[-3].name

    def test_the_same_configuration_places_it_in_the_same_period(self):
        """Criterion 3, and the reason there is no seed in this module:
        the placement is an index, so determinism is a property of the
        design rather than something a fixed draw has to preserve."""
        injection = si.Injection("TS-x", "d", -8, "cfg")
        first = si.resolve(injection, _daily(30))
        second = si.resolve(injection, _daily(30))
        assert first == second

    def test_the_arrivals_are_dated_from_the_anchor(self):
        placed = si.resolve(si.Injection(
            "TS-x", "d", -5, "cfg",
            arrivals=(si.ExtraArrival(0, "14:00"), si.ExtraArrival(2, "09:00"))),
            _daily(30))
        assert [a["date"] for a in placed.arrivals] == [
            placed.period_date.isoformat(),
            (placed.period_date + timedelta(days=2)).isoformat()]

    def test_the_as_of_date_reaches_the_latest_arrival(self):
        """A reader sets the dashboard to this date, so an as-of before
        the scenario's own last arrival would hide the thing it is
        about."""
        placed = si.resolve(si.Injection(
            "TS-x", "d", -5, "cfg", arrivals=(si.ExtraArrival(3, "09:00"),)), _daily(30))
        assert placed.as_record()["as_of"] == (
            placed.period_date + timedelta(days=3)).isoformat()


class TestAHistoryThatCannotHostOneIsRefused:
    """Criterion 4 - loud, naming the scenario, and never a quiet skip."""

    def test_an_anchor_past_the_end_of_the_history_raises(self):
        with pytest.raises(si.CannotPlace) as exc:
            si.resolve(si.Injection("TS-x", "d", 99, "cfg"), _daily(30))
        assert "TS-x" in str(exc.value)

    def test_it_says_why_rather_than_only_that(self):
        """A refusal nobody can act on costs as much as a silent skip."""
        with pytest.raises(si.CannotPlace) as exc:
            si.resolve(si.Injection("TS-x", "d", 99, "cfg"), _daily(30))
        assert "outside" in str(exc.value)
        assert "not safe to place it somewhere else" in str(exc.value)

    def test_an_empty_history_raises_rather_than_indexing(self):
        with pytest.raises(si.CannotPlace):
            si.resolve(si.Injection("TS-x", "d", -1, "cfg"), [])

    def test_a_suppressed_period_outside_the_history_raises(self):
        with pytest.raises(si.CannotPlace) as exc:
            si.resolve(si.Injection("TS-x", "d", 0, "cfg", suppress=(-1,)), _daily(30))
        assert "carry no supply" in str(exc.value)

    def test_two_scenarios_in_one_period_are_refused(self):
        """Criterion 11 one level down: each one's outcome would depend
        on the other's arrivals, and whichever is read first looks
        right."""
        both = [si.Injection("TS-a", "d", -5, "cfg"), si.Injection("TS-b", "d", -5, "cfg")]
        with pytest.raises(si.CannotPlace) as exc:
            si.no_two_scenarios_share_a_period(both, {"d": _daily(30)})
        assert "TS-a" in str(exc.value) and "TS-b" in str(exc.value)

    def test_a_scenario_may_not_suppress_another_s_period(self):
        both = [si.Injection("TS-a", "d", -5, "cfg"),
                si.Injection("TS-b", "d", -3, "cfg", suppress=(-2,))]
        with pytest.raises(si.CannotPlace):
            si.no_two_scenarios_share_a_period(both, {"d": _daily(30)})

    def test_one_scenario_alone_is_fine(self):
        si.no_two_scenarios_share_a_period(
            [si.Injection("TS-a", "d", -5, "cfg", suppress=(-1,))], {"d": _daily(30)})


class TestADayMeantToBeEmptyMustBeEmpty:
    """Criterion 4 again, against the case that actually happened.

    Suppressing a period stops that period's own chain and does nothing
    about a RESUPPLY of an earlier one landing the same day, because the
    delay is drawn at random. TS-2's whole claim is that two days stay
    unfilled.
    """

    def test_an_arrival_on_a_suppressed_day_is_refused(self):
        placed = si.resolve(
            si.Injection("TS-2", "d", -1, "cfg", suppress=(-2,)), _daily(30))
        stray = _Recognised("run_009", "some-delivery",
                            f"{placed.suppressed[0]} 05:00:00+00:00")
        with pytest.raises(si.CannotPlace) as exc:
            si.check_suppressed_days_are_empty([placed], [stray])
        assert "TS-2" in str(exc.value) and "run_009" in str(exc.value)

    def test_an_empty_day_passes(self):
        placed = si.resolve(
            si.Injection("TS-2", "d", -1, "cfg", suppress=(-2,)), _daily(30))
        si.check_suppressed_days_are_empty(
            [placed], [_Recognised("run_009", "x", "2026-01-01 05:00:00+00:00")])

    def test_an_arrival_with_no_receipt_instant_is_not_read_as_landing(self):
        """An in-flight delivery has no receipt yet, and treating its
        absence as a landing on every day would refuse every history."""
        placed = si.resolve(
            si.Injection("TS-2", "d", -1, "cfg", suppress=(-2,)), _daily(30))
        si.check_suppressed_days_are_empty([placed], [_Recognised("run_009", "x", None)])


class TestTheRunIdsComeFromRecognition:
    """The correction that cost the first real run.

    Run identity is RECEIPT ORDER over recognised deliveries, not the
    generator's manifest numbering, and suppressing two periods makes
    the two disagree by exactly the slots removed.
    """

    def test_a_delivery_name_resolves_to_its_recognised_run_id(self):
        placed = si.resolve(si.Injection(
            "TS-x", "d", -5, "cfg", arrivals=(si.ExtraArrival(0, "14:00"),)), _daily(30))
        placed.arrivals[0]["delivery"] = "some-supplier-folder"
        si.resolve_run_ids([placed], [_Recognised("run_034", "some-supplier-folder")])
        assert placed.as_record()["supplies"] == ["run_034"]

    def test_an_unrecognised_delivery_contributes_no_supply(self):
        """Better an incomplete coordinate than one pointing at
        somebody else's data - which is exactly what the bug did."""
        placed = si.resolve(si.Injection(
            "TS-x", "d", -5, "cfg", arrivals=(si.ExtraArrival(0, "14:00"),)), _daily(30))
        placed.arrivals[0]["delivery"] = "never-recognised"
        si.resolve_run_ids([placed], [_Recognised("run_034", "something-else")])
        assert placed.as_record()["supplies"] == []


class TestTheRecordTheScenarioMapReads:
    """Criterion 7, against the reader rather than against this module."""

    def test_it_round_trips_through_the_scenario_map(self, tmp_path):
        from qa_tools.common import scenario_map

        placed = si.resolve(si.Injection(
            "TS-1", "birth-registrations", -8, "daily, due 14:00",
            arrivals=(si.ExtraArrival(0, "14:00"),)), _daily(30))
        placed.arrivals[0]["delivery"] = "d"
        si.resolve_run_ids([placed], [_Recognised("run_028", "d")])
        path = si.write_placements([placed], tmp_path / "placements.json")

        back = scenario_map.read_placements(path)
        assert back["TS-1"].dataset == "birth-registrations"
        assert back["TS-1"].supplies == ("run_028",)
        assert back["TS-1"].is_complete

    def test_a_shared_placement_is_recorded_under_both_scenarios(self):
        """TS-1's third file IS TS-4's arrival into a filled slot.
        Recording one placement under both is honest; generating a
        second identical arrival would be padding."""
        import json

        assert "TS-4" in si._ALSO.get("TS-1", ())
        recorded = json.loads(si.PLACEMENTS_PATH.read_text())["placements"] \
            if si.PLACEMENTS_PATH.exists() else []
        if recorded:
            by_id = {r["scenario_id"]: r for r in recorded}
            assert by_id["TS-4"]["supplies"] == by_id["TS-1"]["supplies"]

    def test_the_config_is_recorded_beside_the_placement(self):
        """Criterion 2. An outcome without its config is meaningless -
        Keith's own finding, which invalidated two expected results as
        first written."""
        placed = si.resolve(
            si.Injection("TS-x", "d", -5, "daily, due 14:00, 4-hour window"), _daily(30))
        assert placed.as_record()["config"] == "daily, due 14:00, 4-hour window"

    def test_every_injection_states_one(self):
        for injection in si.INJECTIONS:
            assert injection.config.strip(), injection.scenario_id


class TestTheInjectedSetItself:
    """What is actually wired up, held against the register."""

    def test_every_injection_names_a_scenario_the_register_marks_for_injection(self):
        from qa_tools.common import scenarios

        marked = {s.id for s in scenarios.injected()}
        for injection in si.INJECTIONS:
            assert injection.scenario_id in marked, injection.scenario_id
            for also in injection.also_demonstrates:
                assert also in marked, also

    def test_it_generates_no_verdict(self):
        """Criterion 6. `severity` is what the generator injects into the
        ROWS - the same lever the ordinary chain pulls - and the QA tools
        still decide whether a supply is red. Nothing here names a
        status, a slot or a lateness."""
        for injection in si.INJECTIONS:
            for arrival in injection.arrivals:
                assert arrival.severity in (None, "amber", "red"), arrival


class TestNothingSaysScenarioOnTheDashboard:
    """Criterion 5, and the decision behind it.

    Keith turned down a scenario label on the injected runs - "this is
    still just a proof of concept remember" - against a first draft that
    argued for one to stop the dashboard growing permanent red that
    looks like a defect. For a PoC that is over-building: the red IS the
    point, the audience knows the data is synthetic, and SCENARIOS.md
    carries the which-one-is-this information instead.

    ASSERTED AGAINST THE DATA THE PAGE RENDERS, not against the built
    HTML, and the difference matters: the Plans tab embeds this repo's
    own plans/*.md, which contains the register itself, so every
    scenario id appears in the page by design. What must not happen is a
    SUPPLY carrying one.
    """

    def test_no_supply_or_dataset_record_carries_a_scenario_id(self):
        import re
        from pathlib import Path

        from qa_tools.common import scenarios

        ids = {s.id for s in scenarios.parse_register()}
        pattern = re.compile(r"\bTS-[0-9]+[a-z]?\b")
        root = Path(__file__).resolve().parent.parent
        for name in ("birth_registrations_dashboard.json",
                     "child_protection_dashboard.json"):
            path = root / "reports" / name
            if not path.is_file():
                pytest.skip(f"{name} not built - run `mothman dashboard build-data`")
            found = {m for m in pattern.findall(path.read_text()) if m in ids}
            assert not found, (
                f"{name} carries scenario id(s) {sorted(found)} - an injected "
                f"scenario must not be marked as one in what the dashboard renders")
