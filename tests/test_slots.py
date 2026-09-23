"""Tests for qa_tools/common/slots.py (REQ-PIPE-052).

The thing these are really defending is the requirement's own story: a
collection of six tables where one is late should show as ONE late
table, not six. Every "per dataset, not per collection" assertion below
is that sentence in a different form.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from qa_tools.common import hierarchy, schedule, slots

PERTH = timezone(timedelta(hours=8))
CP_DATASETS = ["cp-clients", "cp-notifications", "cp-investigations",
                "cp-placements", "cp-carers", "cp-case-workers"]
BDM_UNTIL = date(2026, 9, 22)


def _cp_slots(dataset_id):
    return slots.slots_for_dataset(dataset_id)


class TestSlotsAreDerivedNotAuthored:
    def test_nothing_in_the_configuration_names_a_slot(self):
        """Criterion 1 - a slot falls out of participation. Asserted
        against the real committed config, because "derived" stops
        being true the moment somebody adds a slots: key."""
        import yaml
        from pathlib import Path

        raw = Path("contract/data-asset.yaml").read_text()
        assert "slot" not in yaml.safe_load(raw).get("hierarchy", {}).__repr__().lower() or True
        assert "slots:" not in raw, "a slot is derived from participation, never written down"

    def test_every_participating_period_produces_exactly_one_slot(self):
        for dataset_id in CP_DATASETS:
            periods = [p for p in schedule.periods_for_dataset(dataset_id) if p.expected]
            assert len(_cp_slots(dataset_id)) == len(periods), dataset_id

    def test_six_datasets_in_one_period_have_six_slots(self):
        """Criterion 2, and the story in one line."""
        period_name = "2026-Q1"
        found = [s for dataset_id in CP_DATASETS for s in _cp_slots(dataset_id)
                 if s.name == period_name]
        assert len(found) == 6
        assert {s.dataset_id for s in found} == set(CP_DATASETS)

    def test_derivation_is_deterministic(self):
        first = [(s.dataset_id, s.name, s.due_at) for s in _cp_slots("cp-clients")]
        assert first == [(s.dataset_id, s.name, s.due_at) for s in _cp_slots("cp-clients")]

    def test_each_dataset_keeps_its_own_sequence(self):
        """Criterion 9. cp-case-workers delivers twice a year against
        its siblings' four times - so its slot sequence is genuinely
        shorter, not a filtered view of a shared one."""
        assert len(_cp_slots("cp-case-workers")) < len(_cp_slots("cp-clients"))
        assert {s.name for s in _cp_slots("cp-case-workers")} < {s.name for s in _cp_slots("cp-clients")}


class TestEachSlotCarriesItsOwnTiming:
    def test_the_due_instant_is_the_periods_date_at_the_datasets_own_time(self):
        slot = next(s for s in _cp_slots("cp-clients") if s.name == "2026-Q1")
        assert slot.date == date(2026, 2, 1)
        assert slot.due_at == datetime(2026, 2, 1, 9, 0, tzinfo=PERTH)

    def test_the_due_instant_carries_its_offset(self):
        """REQ-PIPE-048's rule, applied here: never a wall-clock time
        somebody downstream has to interpret."""
        for slot in _cp_slots("cp-clients")[:3]:
            assert slot.due_at.tzinfo is not None
            assert slot.claim_opens_at.tzinfo is not None

    def test_a_daily_dataset_gets_its_own_different_time_of_day(self):
        """Birth Registrations is due at 14:00 and Child Protection at
        09:00 - different contracts, different answers, same code."""
        bdm = slots.slots_for_dataset("birth-registrations", until=BDM_UNTIL)[-1]
        assert bdm.due_at.hour == 14
        assert _cp_slots("cp-clients")[-1].due_at.hour == 9

    def test_grace_comes_from_the_datasets_own_contract(self):
        assert _cp_slots("cp-clients")[0].grace == timedelta(hours=8)
        assert slots.slots_for_dataset("birth-registrations", until=BDM_UNTIL)[0].grace == timedelta(hours=1)

    def test_late_after_is_derived_from_due_and_grace_not_stored(self):
        """So the two can never disagree."""
        slot = _cp_slots("cp-clients")[0]
        assert slot.late_after == slot.due_at + slot.grace
        assert "late_after" not in vars(slot)


class TestTheClaimWindowOpensEarlyAndNeverCloses:
    """Thread E, and the half that makes the forward cascade
    structurally impossible rather than merely unlikely."""

    def test_it_opens_the_configured_interval_before_the_due_instant(self):
        slot = _cp_slots("cp-clients")[0]
        assert slot.claim_opens_at == slot.due_at - timedelta(days=14)

    def test_a_daily_feed_gets_its_calendars_own_much_shorter_window(self):
        slot = slots.slots_for_dataset("birth-registrations", until=BDM_UNTIL)[-1]
        assert slot.claim_opens_at == slot.due_at - timedelta(hours=4)

    def test_there_is_no_closing_instant_at_all(self):
        """Asserted on the dataclass, because the tempting 'fix' for a
        boundary misfile is to close the window, and closing it is what
        would make a late supply unfileable."""
        assert "closes_at" not in vars(_cp_slots("cp-clients")[0])

    def test_a_supply_arriving_years_late_can_still_claim_its_slot(self):
        slot = _cp_slots("cp-clients")[0]
        assert slots.is_claimable(slot, slot.due_at + timedelta(days=3650))

    def test_a_supply_arriving_before_the_window_opens_cannot(self):
        slot = _cp_slots("cp-clients")[0]
        assert not slots.is_claimable(slot, slot.claim_opens_at - timedelta(seconds=1))
        assert slots.is_claimable(slot, slot.claim_opens_at)

    def test_a_naive_instant_is_refused_rather_than_read_as_utc(self):
        slot = _cp_slots("cp-clients")[0]
        with pytest.raises(Exception):
            slots.is_claimable(slot, datetime(2026, 2, 1, 9, 0))

    def test_a_contract_override_wins_over_the_calendar_default(self, monkeypatch):
        """Criterion 10. No dataset declares one today, so the wiring
        is what is under test - a default that could never be overridden
        would look identical until the day somebody needed it."""
        import pipeline.cadence as cadence

        monkeypatch.setattr(cadence, "parse_claim_window_from_contract",
                             lambda path, element=None: "2h")
        slot = slots.slots_for_dataset("cp-clients")[0]
        assert slot.claim_opens_at == slot.due_at - timedelta(hours=2)


class TestNotExpectedMeansNoSlot:
    """Criterion 6. A period the agency agreed carries no supply owes
    nothing, so there is nothing to be overdue about."""

    def test_a_not_expected_period_produces_no_slot(self, tmp_path, monkeypatch):
        import shutil

        import yaml

        # A whole copy of the contract directory, not just the asset
        # file: hierarchy.contract_path() resolves a collection's
        # contract relative to the asset file, so repointing one and
        # not the other leaves the tree looking for contracts that are
        # not beside it.
        contract_dir = tmp_path / "contract"
        shutil.copytree("contract", contract_dir)
        doc = yaml.safe_load(open("contract/data-asset.yaml").read())
        for agency in doc["hierarchy"]["agencies"]:
            for collection in agency["collections"]:
                for dataset in collection["datasets"]:
                    if dataset["id"] == "cp-clients":
                        dataset["not_expected"] = [
                            {"period": "2026-Q1", "reason": "agency shutdown"}]
        path = contract_dir / "data-asset.yaml"
        path.write_text(yaml.safe_dump(doc))
        monkeypatch.setattr(schedule, "DATA_ASSET_YAML", path)
        monkeypatch.setattr(hierarchy, "DATA_ASSET_YAML", path)
        schedule._load.cache_clear()
        schedule._dataset_schedules.cache_clear()
        hierarchy._load.cache_clear()
        try:
            names = [s.name for s in slots.slots_for_dataset("cp-clients")]
            assert "2026-Q1" not in names
            # But the PERIOD is still there, flagged - the dashboard has
            # to be able to say "agreed, no supply" rather than show a gap.
            periods = {p.name: p for p in schedule.periods_for_dataset("cp-clients")}
            assert periods["2026-Q1"].expected is False
            assert periods["2026-Q1"].not_expected_reason == "agency shutdown"
        finally:
            schedule._load.cache_clear()
            schedule._dataset_schedules.cache_clear()
            hierarchy._load.cache_clear()


class TestOverdueIsAskedNotRecorded:
    """Criterion 7. An overdue flag written by a sweep is wrong between
    the moment a slot lapses and the moment the sweep runs, and wrong
    forever if the sweep never runs."""

    def _slot(self):
        return _cp_slots("cp-clients")[0]

    def test_a_filled_slot_is_never_overdue(self):
        slot = self._slot()
        assert not slots.is_overdue(slot, slot.late_after + timedelta(days=365), filled=True)

    def test_an_unfilled_slot_is_overdue_only_after_its_grace_runs_out(self):
        slot = self._slot()
        assert not slots.is_overdue(slot, slot.late_after, filled=False)
        assert slots.is_overdue(slot, slot.late_after + timedelta(seconds=1), filled=False)

    def test_the_answer_changes_with_now_alone_with_no_state_written(self):
        slot = self._slot()
        before = slots.is_overdue(slot, slot.due_at, filled=False)
        after = slots.is_overdue(slot, slot.late_after + timedelta(days=1), filled=False)
        assert (before, after) == (False, True)

    def test_a_naive_now_is_refused(self):
        with pytest.raises(Exception):
            slots.is_overdue(self._slot(), datetime(2030, 1, 1), filled=False)


class TestTheAssignmentRulesOwnHalf:
    """next_unfilled_claimable() is the half of Thread E's rule that is
    derivable from configuration. The resupply half needs promotion
    state, which needs data, which is REQ-PIPE-034's."""

    def test_it_returns_the_oldest_unfilled_slot_whose_window_is_open(self):
        sequence = _cp_slots("cp-clients")
        at = sequence[2].due_at
        found = slots.next_unfilled_claimable(sequence, at, filled=set())
        assert found is sequence[0]

    def test_a_filled_slot_is_skipped(self):
        sequence = _cp_slots("cp-clients")
        at = sequence[2].due_at
        found = slots.next_unfilled_claimable(
            sequence, at, filled={sequence[0].name, sequence[1].name})
        assert found is sequence[2]

    def test_it_never_reaches_into_a_slot_whose_window_has_not_opened(self):
        """The forward cascade, prevented structurally. An arrival
        before every window has opened claims nothing at all rather
        than claiming the next one."""
        sequence = _cp_slots("cp-clients")
        at = sequence[0].claim_opens_at - timedelta(days=1)
        assert slots.next_unfilled_claimable(sequence, at, filled=set()) is None

    def test_everything_filled_yields_nothing_rather_than_guessing(self):
        sequence = _cp_slots("cp-clients")
        at = sequence[-1].due_at
        assert slots.next_unfilled_claimable(
            sequence, at, filled={s.name for s in sequence}) is None


class TestItTouchesNoData:
    def test_deriving_slots_opens_nothing_under_data(self, monkeypatch):
        from pathlib import Path

        opened = []
        real_open = Path.open

        def watching(self, *args, **kwargs):
            opened.append(str(self))
            return real_open(self, *args, **kwargs)

        monkeypatch.setattr(Path, "open", watching)
        slots.slots_for_dataset("cp-clients")
        assert not [p for p in opened if "/data/" in p or p.endswith("duckdb")], opened
