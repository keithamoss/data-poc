"""Tests for qa_tools/common/slots.py (REQ-PIPE-052).

The thing these are really defending is the requirement's own story: a
collection of six tables where one is late should show as ONE late
table, not six. Every "per dataset, not per collection" assertion below
is that sentence in a different form.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

import agreement_split
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
        being true the moment somebody authors one.

        Checked against PARSED KEYS rather than the file's text. The
        first version of this grepped for "slots:" and started failing
        the moment REQ-PIPE-053 added `runway_warning_slots` - a
        substring match on a config file matches things that have
        nothing to do with what is being asserted.
        """
        import yaml
        from pathlib import Path

        doc = yaml.safe_load(Path("contract/data-asset.yaml").read_text())
        for agency in doc["hierarchy"]["agencies"]:
            for collection in agency["collections"]:
                assert "slots" not in collection
                for dataset in collection["datasets"]:
                    assert "slots" not in dataset, \
                        f"{dataset['id']} authors slots - they are derived from participation"

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


class TestTheClaimWindowOpensEarlyAndClosesWithTheNextPeriod:
    """Thread E's early window - the half that makes the forward cascade
    structurally impossible - and REQ-PIPE-131's close, which reversed
    Thread E's open end."""

    def test_it_opens_the_configured_interval_before_the_due_instant(self):
        slot = _cp_slots("cp-clients")[0]
        assert slot.claim_opens_at == slot.due_at - timedelta(days=14)

    def test_a_daily_feed_gets_its_calendars_own_much_shorter_window(self):
        slot = slots.slots_for_dataset("birth-registrations", until=BDM_UNTIL)[-1]
        assert slot.claim_opens_at == slot.due_at - timedelta(hours=4)

    def test_a_slot_closes_when_the_next_periods_claim_window_opens(self):
        """Criteria 1 and 2, against the real quarterly calendar."""
        sequence = _cp_slots("cp-clients")
        for here, there in zip(sequence, sequence[1:]):
            assert here.closes_at == there.claim_opens_at, here.name

    def test_a_daily_slot_closes_when_tomorrows_window_opens(self):
        sequence = slots.slots_for_dataset("birth-registrations", until=BDM_UNTIL)
        for here, there in zip(sequence, sequence[1:]):
            assert here.closes_at == there.claim_opens_at, here.name
        # And the LAST slot generated still knows when it closes - the
        # period after `until` is read for it.
        last = sequence[-1]
        assert last.closes_at == last.claim_opens_at + timedelta(days=1)

    def test_a_partial_dataset_closes_with_its_CALENDAR_period(self):
        """Keith's sign-off reversal: Case Workers, February and August on
        the quarterly calendar, closes February when MAY's window opens,
        not August's - and has no open slot between."""
        workers = _cp_slots("cp-case-workers")
        clients = {s.name: s for s in _cp_slots("cp-clients")}
        names = [s.name for s in workers]
        first = workers[0]
        following = [n for n in clients if clients[n].date > first.date][0]
        assert following not in names, "precondition: a period case workers skips"
        assert first.closes_at == clients[following].claim_opens_at
        gap = first.closes_at + timedelta(days=1)
        assert not any(slots.is_open(s, gap) for s in workers)

    def test_open_is_from_the_window_opening_until_the_close(self):
        slot = _cp_slots("cp-clients")[0]
        assert not slots.is_open(slot, slot.claim_opens_at - timedelta(seconds=1))
        assert slots.is_open(slot, slot.claim_opens_at)
        assert slots.is_open(slot, slot.closes_at - timedelta(seconds=1))
        assert not slots.is_open(slot, slot.closes_at)
        assert slots.is_closed(slot, slot.closes_at)
        assert not slots.is_closed(slot, slot.closes_at - timedelta(seconds=1))

    def test_a_naive_instant_is_refused_rather_than_read_as_utc(self):
        slot = _cp_slots("cp-clients")[0]
        with pytest.raises(Exception):
            slots.is_open(slot, datetime(2026, 2, 1, 9, 0))

    def test_a_participation_override_wins_over_the_calendar_default(self, tmp_path,
                                                                     monkeypatch):
        """Criterion 10. No dataset declares one today, so the wiring
        is what is under test - a default that could never be overridden
        would look identical until the day somebody needed it. The
        override moved from the ODCS contract to the dataset's
        participation in contract/calendar.yaml (REQ-PIPE-110 criterion 4)."""
        import yaml

        base = yaml.safe_load((agreement_split.REAL_CONTRACT_DIR / "calendar.yaml").read_text())
        entry = next(d for d in base["datasets"] if d["id"] == "cp-clients")
        entry["participation"]["versions"][0] = {
            **entry["participation"]["versions"][0], "claim_window": "2h"}
        agreement_split.repoint(monkeypatch, tmp_path / "contract",
                                agreement_split.merged_view(agreement_split.REAL_CONTRACT_DIR),
                                base=base)
        try:
            slot = slots.slots_for_dataset("cp-clients")[0]
            assert slot.claim_opens_at == slot.due_at - timedelta(hours=2)
        finally:
            agreement_split.clear_caches()
            hierarchy._load.cache_clear()


class TestNotExpectedMeansNoSlot:
    """Criterion 6. A period the agency agreed carries no supply owes
    nothing, so there is nothing to be overdue about."""

    def test_a_not_expected_period_produces_no_slot(self, tmp_path, monkeypatch):
        import shutil


        # A whole copy of the contract directory, not just the asset
        # file: hierarchy.contract_path() resolves a collection's
        # contract relative to the asset file, so repointing one and
        # not the other leaves the tree looking for contracts that are
        # not beside it.
        contract_dir = tmp_path / "contract"
        shutil.copytree("contract", contract_dir)
        doc = agreement_split.merged_view(contract_dir)
        for agency in doc["hierarchy"]["agencies"]:
            for collection in agency["collections"]:
                for dataset in collection["datasets"]:
                    if dataset["id"] == "cp-clients":
                        dataset["not_expected"] = [
                            {"period": "2026-Q1", "reason": "agency shutdown"}]
        agreement_split.repoint(monkeypatch, contract_dir, doc)
        try:
            names = [s.name for s in slots.slots_for_dataset("cp-clients")]
            assert "2026-Q1" not in names
            # But the PERIOD is still there, flagged - the dashboard has
            # to be able to say "agreed, no supply" rather than show a gap.
            periods = {p.name: p for p in schedule.periods_for_dataset("cp-clients")}
            assert periods["2026-Q1"].expected is False
            assert periods["2026-Q1"].not_expected_reason == "agency shutdown"
        finally:
            agreement_split.clear_caches()
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


class TestTheClaimWindowIsEffectiveDated:
    """post-build-review #42. `claim_window()` read `calendar.current`
    and `slots_for_dataset` applied that one value to every slot,
    including slots for periods years in the past. Author a version
    changing 14d to 7d and every historical slot's `claim_opens_at`
    moved.

    That is exactly the retroactivity `REQ-PIPE-051` built
    `_effect_windows()` to prevent for period DATES, arriving through
    the other half of the same config:
    `periods_for_calendar()` got it right and `claim_window()` did not.

    It matters more than a display detail because the assignment rule
    files to the slot whose claim window is OPEN (REQ-PIPE-131) - so a
    window that moves retroactively means re-deriving a past
    assignment can give a different answer than the one history was
    actually filed under.
    """

    def _two_windows(self):
        """Same shape as test_schedule.py's own two-version fixture,
        except that what differs between the versions is the CLAIM
        WINDOW rather than the dates."""
        return {"data_asset_id": "data-asset-1",
                "calendars": [{"name": "c", "versions": [
                    {"effective_from": "2023-01-01", "changelog": ["initial"],
                     "claim_window": "14d",
                     "dates": [{"period": "2024-Q1", "date": "2024-02-01"}]},
                    {"effective_from": "2027-01-01",
                     "changelog": ["2027-01-01: window shortened to 7 days"],
                     "claim_window": "7d",
                     "dates": [{"period": "2027-Q1", "date": "2027-02-01"}]},
                ]}],
                "hierarchy": {"agencies": [{"id": "a", "name": "A", "collections": [
                    {"id": "col", "name": "Col", "contract": "c.yaml", "datasets": [
                        {"id": "d", "name": "D", "table": "t", "calendar": "c"}]}]}]}}

    def _repoint(self, tmp_path, monkeypatch, base=None):
        import shutil

        contract_dir = tmp_path / "contract"
        shutil.copytree("contract", contract_dir)
        # The participation is a stand-in - 09:00, no grace, no override -
        # because the timing that matters here comes from the calendar.
        agreement_split.repoint(monkeypatch, contract_dir, self._two_windows(),
                                base=base if base is not None else {})

    def test_a_past_slot_keeps_the_window_that_was_in_force_on_its_own_date(
            self, tmp_path, monkeypatch):
        self._repoint(tmp_path, monkeypatch)
        try:
            by_period = {s.name: s for s in slots.slots_for_dataset("d")}
            old = by_period["2024-Q1"]
            assert old.claim_opens_at == old.due_at - timedelta(days=14), (
                "the 2024 slot took the 2027 version's 7-day window - authoring a new "
                "calendar version moved a claim window that history was filed under")
        finally:
            agreement_split.clear_caches()
            hierarchy._load.cache_clear()

    def test_a_current_slot_takes_the_current_version(self, tmp_path, monkeypatch):
        """The other half - effective-dating must not freeze the window
        at the oldest version either."""
        self._repoint(tmp_path, monkeypatch)
        try:
            by_period = {s.name: s for s in slots.slots_for_dataset("d")}
            new = by_period["2027-Q1"]
            assert new.claim_opens_at == new.due_at - timedelta(days=7)
        finally:
            agreement_split.clear_caches()
            hierarchy._load.cache_clear()

    def test_a_participation_override_wins_at_every_date(self, tmp_path, monkeypatch):
        """Criterion 10's override, on the dataset's participation version
        since REQ-PIPE-110 - in force over every calendar version it
        overlaps."""
        self._repoint(tmp_path, monkeypatch,
                      base=agreement_split.participation("d", claim_window="2h"))
        try:
            for slot in slots.slots_for_dataset("d"):
                assert slot.claim_opens_at == slot.due_at - timedelta(hours=2)
        finally:
            agreement_split.clear_caches()
            hierarchy._load.cache_clear()
