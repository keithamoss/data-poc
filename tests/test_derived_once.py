"""The values derived from an agreement, worked out once (REQ-PIPE-400,
signed by Keith 2026-11-14 as speed-anchor v2).

Each test counts the real computations behind slots.slots_for_dataset,
schedule.periods_for_dataset, schedule.periods_for_calendar and
Agreement.standing_on - the functions the generator, the replay and the
dashboard build call - and asserts on what callers are answered.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from datetime import date
from pathlib import Path

import pytest

import asset_folders
from asset_model import agreement, asset_time, config_pin, config_yaml, derived, schedule, slots

pytestmark = pytest.mark.asset("daily")

DATASET = "birth-registrations"
WHEN = ('expected_time: "22:00"', 'expected_time: "21:00"')


def edit_in_place(path: Path, old: str, new: str) -> None:
    assert len(old) == len(new)
    before = os.stat(path)
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))


@pytest.fixture
def counted(monkeypatch):
    """Every real computation of the four, by (function, agreement, zones,
    arguments)."""
    seen: Counter = Counter()

    def counting(module, name, key_of):
        real = getattr(module, name)

        def wrapped(*args, **kwargs):
            agr, zones, args_key = key_of(*args, **kwargs)
            seen[(name, id(agr), id(zones), args_key)] += 1
            return real(*args, **kwargs)
        monkeypatch.setattr(module, name, wrapped)

    zones = lambda: asset_time.timezone_versions()  # noqa: E731
    counting(schedule, "compute_periods_for_calendar",
             lambda name, until, agr: (agr, zones(), (name, until)))
    counting(schedule, "compute_periods_for_dataset",
             lambda ds, until, agr: (agr, zones(), (ds, until)))
    counting(slots, "compute_slots_for_dataset",
             lambda ds, until, agr: (agr, zones(), (ds, until)))
    counting(agreement.Agreement, "compute_standing_on",
             lambda self, ds, on: (self, zones(), (ds, on)))
    derived.MEMO.clear()
    return seen


@pytest.fixture
def calendar(tmp_path) -> Path:
    pointed = tmp_path / "pointed"
    pointed.mkdir()
    real = asset_folders.real_folder()
    for name in ("calendar.yaml", "data-asset.yaml"):
        (pointed / name).write_text((real / name).read_text(encoding="utf-8"),
                                    encoding="utf-8")
    asset_folders.point(pointed)
    return pointed / "calendar.yaml"


class TestEachIsWorkedOutOncePerArgumentSet:
    """Criterion 1, in one pinned generation of a test asset."""

    def test_a_pinned_generation_works_each_out_once(self, counted, tmp_path):
        """ITS SUBJECT IS GENERATION ITSELF - what one pinned generation works
        out - so it generates (REQ-TEST-402 criterion 7)."""
        from generator import driver, output

        undo = output.redirect(tmp_path / "out")
        try:
            with config_pin.pinned():
                driver.generate("civil-registration")
        finally:
            undo()
        by_function = Counter(k[0] for k in counted)
        assert by_function["compute_slots_for_dataset"] > 0
        assert by_function["compute_standing_on"] > 0
        assert by_function["compute_periods_for_calendar"] > 0
        repeated = {k: n for k, n in counted.items() if n > 1}
        assert not repeated, f"worked out more than once: {list(repeated.items())[:5]}"

    def test_the_same_question_is_answered_without_working_it_out_again(self, counted):
        agr = agreement.current()
        first = slots.slots_for_dataset(DATASET, until=date(2026, 9, 1), agreement=agr)
        again = slots.slots_for_dataset(DATASET, until=date(2026, 9, 1))
        assert first == again and first is not again
        assert counted[("compute_slots_for_dataset", id(agr),
                        id(asset_time.timezone_versions()),
                        (DATASET, date(2026, 9, 1)))] == 1


class TestAStagedCorrectionGetsItsOwnValues:
    """Criterion 2: a staged calendar correction and a staged time-zone
    correction are each answered with values worked out under them."""

    def test_a_staged_calendar_correction(self, calendar, counted):
        from qa_tools.common import correction_trial

        until = date(2026, 9, 1)
        committed = slots.slots_for_dataset(DATASET, until=until)
        cal_doc = config_yaml.parse(calendar.read_text().replace(*WHEN, 1))
        asset_doc = config_yaml.load(calendar.parent / "data-asset.yaml")
        with config_pin.pinned():
            with correction_trial.configured(cal_doc, asset_doc):
                staged = slots.slots_for_dataset(DATASET, until=until)
            back = slots.slots_for_dataset(DATASET, until=until)
        assert staged[0].due_at != committed[0].due_at
        assert staged[0].due_at.hour == committed[0].due_at.hour - 1
        assert back == committed

    def test_a_staged_time_zone_correction(self, calendar, counted):
        from qa_tools.common import correction_trial

        until = date(2026, 9, 1)
        committed = slots.slots_for_dataset(DATASET, until=until)
        cal_doc = config_yaml.load(calendar)
        asset_doc = json.loads(json.dumps(config_yaml.load(calendar.parent / "data-asset.yaml")))
        asset_doc["timezone"]["versions"][0]["zone"] = "Australia/Eucla"
        with config_pin.pinned():
            with correction_trial.configured(cal_doc, asset_doc):
                staged = slots.slots_for_dataset(DATASET, until=until)
        assert staged[0].due_at != committed[0].due_at
        assert str(staged[0].due_at.tzinfo) == "Australia/Eucla"


class TestUnpinnedItReadsTheFileAsItIsNow:
    """Criteria 3: correct pinned or unpinned - an unpinned call sees an
    edited calendar."""

    def test_an_unpinned_call_sees_an_edited_calendar(self, calendar, counted):
        until = date(2026, 9, 1)
        before = slots.slots_for_dataset(DATASET, until=until)
        edit_in_place(calendar, *WHEN)
        after = slots.slots_for_dataset(DATASET, until=until)
        assert after[0].due_at.hour == before[0].due_at.hour - 1

    def test_what_it_remembers_is_bounded(self, counted):
        memo = derived.Memo(agreements=2)
        doc = config_yaml.load(agreement.calendar_yaml())
        made = [agreement.from_doc({**doc, "description": f"version {i}"}) for i in range(3)]
        assert len({id(a) for a in made}) == 3
        for agr in made:
            memo.get(agr, ("x",), lambda: 1)
        assert len(memo) == 2


class TestTheSameDocumentIsTheSameAgreement:
    """What makes criterion 1 hold across a generation's declared corrections:
    the agreement either side of a correction, built from the same document
    again and again, is one instance, so its derived values are remembered."""

    def test_from_doc_gives_one_instance_for_one_content(self):
        doc = config_yaml.load(agreement.calendar_yaml())
        import copy

        assert agreement.from_doc(doc) is agreement.from_doc(copy.deepcopy(doc))
        other = agreement.from_doc({**doc, "description": "another"})
        assert other is not agreement.from_doc(doc)

    def test_zones_from_one_block_are_one_value(self):
        doc = config_yaml.load(asset_time.data_asset_yaml())
        import copy

        assert asset_time.parse_timezone_versions(doc) is \
            asset_time.parse_timezone_versions(copy.deepcopy(doc))


class TestNothingSharedCanBeChanged:
    """Criterion 4: each caller's own list of frozen values."""

    def test_a_callers_change_does_not_reach_the_next_caller(self, counted):
        until = date(2026, 9, 1)
        mine = slots.slots_for_dataset(DATASET, until=until)
        mine.clear()
        assert slots.slots_for_dataset(DATASET, until=until)
        periods = schedule.periods_for_dataset(DATASET, until=until)
        periods.pop()
        assert len(schedule.periods_for_dataset(DATASET, until=until)) == len(periods) + 1


@pytest.mark.asset("quarterly")
class TestAHierarchyEditIsSeenUnpinned:
    """post-build-review #393: the memo was keyed on the agreement and the
    zones only, but a dataset's collection - and so its collection's
    participation defaults - is the hierarchy's, read from data-asset.yaml
    outside its timezone block. An unpinned process kept answering slots
    worked out under the old hierarchy."""

    @pytest.fixture
    def hierarchy_file(self, tmp_path) -> Path:
        pointed = tmp_path / "pointed"
        pointed.mkdir()
        real = asset_folders.real_folder()
        for name in ("calendar.yaml", "data-asset.yaml"):
            (pointed / name).write_text((real / name).read_text(encoding="utf-8"),
                                        encoding="utf-8")
        asset_folders.point(pointed)
        return pointed / "data-asset.yaml"

    def test_a_swap_of_two_collections_is_seen(self, hierarchy_file):
        until = date(2024, 1, 1)
        before = slots.slots_for_dataset("cp-clients", until=until)
        text = hierarchy_file.read_text(encoding="utf-8")
        swapped = (text.replace("- id: child-protection\n", "- id: SWAP-A\n", 1)
                   .replace("- id: emergency-department\n", "- id: child-protection\n", 1)
                   .replace("- id: SWAP-A\n", "- id: emergency-department\n", 1))
        assert swapped != text
        hierarchy_file.write_text(swapped, encoding="utf-8")
        derived.MEMO.clear()
        fresh = slots.slots_for_dataset("cp-clients", until=until)
        assert fresh != before, "precondition - the swap changes cp-clients' slots"
        hierarchy_file.write_text(text, encoding="utf-8")
        assert slots.slots_for_dataset("cp-clients", until=until) == before
        hierarchy_file.write_text(swapped, encoding="utf-8")
        assert slots.slots_for_dataset("cp-clients", until=until) == fresh

    def test_an_unknown_dataset_is_refused_after_a_hit(self, hierarchy_file):
        from asset_model import hierarchy

        until = date(2024, 1, 1)
        slots.slots_for_dataset("cp-clients", until=until)
        text = hierarchy_file.read_text(encoding="utf-8")
        hierarchy_file.write_text(text.replace("id: cp-clients\n", "id: cp-clientz\n", 1),
                                  encoding="utf-8")
        with pytest.raises(hierarchy.UnknownDatasetError):
            slots.slots_for_dataset("cp-clients", until=until)
