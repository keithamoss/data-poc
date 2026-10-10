"""Each slot's due instant from the agreement in force on its own date
(REQ-PIPE-113).

Every test writes a copy of the real contract/calendar.yaml with ONE
change to Child Protection's participation and loads it as its own
agreement value, passed to the functions under test - which is what
REQ-PIPE-110's one loader exists for. The real file and every cache are
untouched.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from qa_tools.common import agreement, asset_time, in_force, period_overlap, schedule, slots

REAL = Path(__file__).resolve().parent.parent / "contract" / "calendar.yaml"


def _with(tmp_path, dataset_id="cp-clients", versions=None, first=None):
    """The real agreement with one dataset's participation versions
    replaced. `first` updates the existing single version in place;
    `versions` (each merged over the existing one) replaces the list."""
    doc = yaml.safe_load(REAL.read_text())
    entry = next(d for d in doc["datasets"] if d["id"] == dataset_id)
    base = entry["participation"]["versions"][0]
    if first is not None:
        entry["participation"]["versions"][0] = {**base, **first}
    if versions is not None:
        entry["participation"]["versions"] = [
            {**base, "changelog": [{"date": str(v["effective_from"]), "author": "a test",
                                    "change": "a test's version"}], **v}
            for v in versions]
    path = tmp_path / "calendar.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False))
    return agreement.load(path)


def _slot(dataset_id, name, agreement_value):
    return next(s for s in slots.slots_for_dataset(dataset_id, agreement=agreement_value)
                if s.name == name)


def _perth(*args):
    return datetime(*args, tzinfo=asset_time.zone_on(date(*args[:3])))


class TestEachSlotTakesTheVersionInForceOnItsOwnDate:
    """Criteria 2 and 3."""

    @pytest.fixture
    def two_eras(self, tmp_path):
        return _with(tmp_path, versions=[
            {"effective_from": "2023-01-01", "expected_time": "09:00", "grace": "8h"},
            {"effective_from": "2025-06-01", "expected_time": "14:00", "grace": "1h"}])

    def test_a_slot_before_the_change_keeps_the_old_due_time_and_grace(self, two_eras):
        slot = _slot("cp-clients", "2025-Q2", two_eras)  # 2025-05-01
        assert slot.due_at == _perth(2025, 5, 1, 9, 0)
        assert slot.grace == timedelta(hours=8)

    def test_a_slot_after_the_change_takes_the_new_one(self, two_eras):
        slot = _slot("cp-clients", "2025-Q3", two_eras)  # 2025-08-01
        assert slot.due_at == _perth(2025, 8, 1, 14, 0)
        assert slot.grace == timedelta(hours=1)

    def test_adding_the_later_version_moved_no_earlier_slot(self, two_eras):
        """Criterion 3, asserted against the real agreement directly: the
        due instant, grace and claim-opening instant of every earlier slot
        are unchanged. Its CLOSING instant is not in that list on purpose -
        the last slot before the boundary closes when the next period's
        window opens, from that period's own inputs (criterion 4)."""
        before = {s.name: s for s in slots.slots_for_dataset("cp-clients")}
        after = {s.name: s for s in slots.slots_for_dataset("cp-clients", agreement=two_eras)}
        for name, slot in before.items():
            if slot.date < date(2025, 6, 1):
                new = after[name]
                assert (new.due_at, new.grace, new.claim_opens_at) == \
                    (slot.due_at, slot.grace, slot.claim_opens_at), name
                if name != "2025-Q2":
                    assert new.closes_at == slot.closes_at, name

    def test_a_claim_window_override_is_taken_on_the_periods_own_date(self, tmp_path):
        later_only = _with(tmp_path, versions=[
            {"effective_from": "2023-01-01"},
            {"effective_from": "2025-06-01", "claim_window": "2d"}])
        old = _slot("cp-clients", "2025-Q2", later_only)
        new = _slot("cp-clients", "2025-Q3", later_only)
        assert old.claim_opens_at == old.due_at - timedelta(days=14)
        assert new.claim_opens_at == new.due_at - timedelta(days=2)


class TestTheClosingInstantUsesTheNextPeriodsOwnInputs:
    def test_a_version_change_takes_effect_at_its_own_boundary(self, tmp_path):
        """Criterion 4: Q2 closes when Q3's window opens, computed from
        Q3's own (new) expected time - so the change shows at the boundary
        and nowhere before it."""
        two = _with(tmp_path, versions=[
            {"effective_from": "2023-01-01", "expected_time": "09:00"},
            {"effective_from": "2025-06-01", "expected_time": "14:00"}])
        q2, q3 = _slot("cp-clients", "2025-Q2", two), _slot("cp-clients", "2025-Q3", two)
        assert q2.closes_at == q3.claim_opens_at
        assert q3.claim_opens_at == _perth(2025, 8, 1, 14, 0) - timedelta(days=14)


class TestDaysBefore:
    @pytest.fixture
    def evening_before(self, tmp_path):
        """Criterion 5's shape: a supply for the period due at 22:00 the
        evening before its date."""
        return _with(tmp_path, first={"expected_time": "22:00", "days_before": 1})

    def test_the_due_instant_is_the_evening_before(self, evening_before):
        slot = _slot("cp-clients", "2025-Q3", evening_before)  # period date 2025-08-01
        assert slot.due_at == _perth(2025, 7, 31, 22, 0)

    def test_the_claim_window_opens_from_the_earlier_due_instant(self, evening_before):
        slot = _slot("cp-clients", "2025-Q3", evening_before)
        assert slot.claim_opens_at == _perth(2025, 7, 31, 22, 0) - timedelta(days=14)

    def test_zero_unless_stated(self):
        slot = slots.slots_for_dataset("cp-clients")[0]
        assert slot.due_at.date() == slot.date

    def test_widening_the_claim_window_never_moves_the_due_instant(self, tmp_path):
        """Criterion 6."""
        wide = _with(tmp_path, first={"claim_window": "30d"})
        for real, widened in zip(slots.slots_for_dataset("cp-clients"),
                                 slots.slots_for_dataset("cp-clients", agreement=wide)):
            assert real.due_at == widened.due_at
            assert widened.claim_opens_at < real.claim_opens_at

    @pytest.mark.parametrize("value", [-1, 1.5, "1", True])
    def test_a_value_that_is_not_a_whole_number_of_days_is_refused(self, tmp_path, value):
        with pytest.raises(schedule.ScheduleConfigError, match="whole number"):
            _with(tmp_path, first={"days_before": value})


class TestEveryHorizonReachesPastTheLargestDaysBefore:
    """Criterion 11."""

    def test_the_claim_reach_adds_it(self, tmp_path):
        ninety = _with(tmp_path, first={"days_before": 90, "claim_window": "1d"})
        # The widest window the dataset ever had - the calendar's 14 days,
        # wider than this version's 1-day override - plus the 90.
        assert slots.claimable_until("cp-clients", date(2025, 5, 2), ninety) == \
            date(2025, 5, 2) + timedelta(days=14) + timedelta(days=90)

    def test_a_supply_due_ninety_days_ahead_finds_its_slot(self, tmp_path):
        ninety = _with(tmp_path, first={"days_before": 90, "claim_window": "1d"})
        arrived = date(2025, 5, 3)  # Q3 2025-08-01 is due 2025-05-03
        until = slots.claimable_until("cp-clients", arrived, ninety)
        found = [s.name for s in slots.slots_for_dataset("cp-clients", until=until,
                                                         agreement=ninety)]
        assert "2025-Q3" in found

    def test_the_overlap_horizon_adds_it(self, tmp_path, monkeypatch):
        ninety = _with(tmp_path, dataset_id="birth-registrations",
                       first={"days_before": 3})
        seen = []
        real = slots._calendar_periods
        monkeypatch.setattr(slots, "_calendar_periods",
                            lambda d, until, a=None: seen.append(until) or real(d, until, a))
        period_overlap.overlaps_for("birth-registrations", until=date(2026, 9, 1),
                                    agreement=ninety)
        assert seen == [date(2026, 9, 4)]


class TestOneImplementation:
    def test_the_overlap_gate_and_filing_compute_the_same_instants(self, tmp_path):
        """Criterion 10: the gate asks the one function filing does."""
        two = _with(tmp_path, versions=[
            {"effective_from": "2023-01-01"},
            {"effective_from": "2025-06-01", "expected_time": "14:00", "days_before": 1}])
        for slot in slots.slots_for_dataset("cp-clients", agreement=two):
            instants = slots.slot_instants("cp-clients", slot.date, two)
            assert (instants.due_at, instants.grace, instants.claim_opens_at) == \
                (slot.due_at, slot.grace, slot.claim_opens_at)

    def test_in_force_is_the_last_version_on_or_before(self):
        """NFR 2's one helper."""
        class V:
            def __init__(self, d):
                self.effective_from = d
        versions = [V(date(2023, 1, 1)), V(date(2025, 6, 1))]
        assert in_force.version_on(versions, date(2022, 12, 31)) is None
        assert in_force.version_on(versions, date(2023, 1, 1)) is versions[0]
        assert in_force.version_on(versions, date(2025, 5, 31)) is versions[0]
        assert in_force.version_on(versions, date(2025, 6, 1)) is versions[1]


class TestConfigurationOnly:
    def test_computing_instants_opens_nothing_under_data(self, monkeypatch, tmp_path):
        """Criterion 8."""
        import builtins

        two = _with(tmp_path, first={"days_before": 1})
        opened = []
        real_open = builtins.open

        def watching(file, *args, **kwargs):
            opened.append(str(file))
            return real_open(file, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", watching)
        slots.slots_for_dataset("cp-clients", agreement=two)
        period_overlap.overlaps_for("cp-clients", agreement=two)
        assert not [p for p in opened if "/data/" in p], opened


class TestCriticFindingsOn113:
    """delivery-critic, 2026-10-11, on REQ-PIPE-113 as built (70bdbe2).
    Each test failed before its fix."""

    def test_the_claim_reach_uses_the_widest_window_any_version_had(self, tmp_path):
        """A window narrowed later must not shrink the reach for history
        replayed under the wider one: a supply on 2023-07-05 is inside
        2023-Q3's 30-day window (opened 2023-07-02) and must find it."""
        narrowed = _with(tmp_path, versions=[
            {"effective_from": "2023-01-01", "claim_window": "30d"},
            {"effective_from": "2025-01-01", "claim_window": "14d"}])
        until = slots.claimable_until("cp-clients", date(2023, 7, 5), narrowed)
        names = [s.name for s in slots.slots_for_dataset("cp-clients", until=until,
                                                         agreement=narrowed)]
        assert "2023-Q3" in names

    def test_a_sub_day_window_crossing_midnight_still_reaches_tomorrows_slot(self, tmp_path):
        """01:00 due with a 4-hour window opens at 21:00 the day before; a
        supply arriving that evening must be offered tomorrow's slot."""
        early = _with(tmp_path, dataset_id="birth-registrations",
                      first={"expected_time": "01:00"})
        until = slots.claimable_until("birth-registrations", date(2026, 9, 30), early)
        assert until >= date(2026, 10, 1)

    def test_a_period_before_the_first_version_takes_its_override_too(self, tmp_path):
        """The PROVISIONAL rule is 'the first version's inputs' - all of
        them, the claim-window override included."""
        late = _with(tmp_path, first={"effective_from": "2025-01-01", "claim_window": "2d"})
        instants = slots.slot_instants("cp-clients", date(2024, 8, 1), late)
        assert instants.claim_opens_at == instants.due_at - timedelta(days=2)

    def test_the_daylight_saving_gate_checks_every_period_slots_compute(self, monkeypatch):
        """Owed or not: the slot path computes a non-owed period's instants
        too (it closes the slot before it), so a due day that daylight
        saving breaks there must be a gate error, not a traceback."""
        import dataclasses
        from zoneinfo import ZoneInfo

        from qa_tools.common import validate_schedule as vs

        sydney = (asset_time.ZoneVersion(date(1970, 1, 1), ZoneInfo("Australia/Sydney")),)
        monkeypatch.setattr(asset_time, "timezone_versions", lambda: sydney)
        real = slots._participation_for

        def due_0230_days_before(d, on, a):
            v = real(d, on, a)
            if d != "cp-case-workers":
                return v
            return dataclasses.replace(v, expected_time="02:30", days_before=28)
        monkeypatch.setattr(slots, "_participation_for", due_0230_days_before)
        # The NON-OWED 2026-Q4 (2026-11-01), 28 days back, is due 2026-10-04 -
        # Sydney's spring-forward day, when 02:30 does not exist. The owed
        # February and August periods land on 4 January and 4 July: fine.
        errors = vs._daylight_saving_errors(vs.Source.default())
        assert any("cp-case-workers" in (e.scope or "") for e in errors), \
            [e.problem for e in errors][:3]
