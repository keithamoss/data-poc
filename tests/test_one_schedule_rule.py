"""REQ-PIPE-377 criterion 6: one function per schedule rule, walked over every
dataset's rounds in both assets.

Each rule #137 found written more than once is answered once in asset_model -
the period a round's files fill (schedule.period_filled_by and its index form
filled_index), whether a dataset supplies in a round (supplies_in_round) and
which participation version gives a slot its inputs (slots.slot_version). The
sites that used to carry their own copies now call those; this walks every
round of every dataset of each asset and holds what the schedule produces to
the one answer. That walk compares schedule's own functions with each other,
so the sites outside it are driven at the bottom with filled_index recorded:
a site answering from a copy of its own records no call (the post-build
critic, 2026-11-18, found two in files_go).
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from asset_model import asset_time, hierarchy, schedule, slots


def _walk():
    agr = schedule.agreement_to_read(None)
    datasets = [d.dataset_id for d in hierarchy.all_datasets()
                if (e := agr.dataset(d.dataset_id)) is not None and e.participation]
    assert datasets, "test precondition - the asset has datasets with participation"
    horizon = asset_time.now().date() + timedelta(days=365)
    for did in datasets:
        cal = schedule.calendar_for_dataset(did, agr)
        sequence = schedule.periods_for_calendar(cal.name, until=horizon, agreement=agr)
        assert sequence, f"test precondition - {did} has rounds"
        yield agr, did, sequence, horizon


def _every_rule_is_answered_once():
    walked = 0
    for agr, did, sequence, horizon in _walk():
        # THE PERIOD A ROUND FILLS: the index form and the named form agree.
        for i, rnd in enumerate(sequence):
            j = schedule.filled_index(did, sequence, i, agr)
            named = schedule.period_filled_by(did, rnd, agr)
            assert (named is None) == (j is None) or named is rnd, (did, rnd.name)
            if j is not None and named is not None:
                assert named.name == sequence[j].name, (did, rnd.name)
            walked += 1
        # WHAT THE SCHEDULE OWES: every owed period is filled by a round the
        # dataset supplies in, by the one rule, and round_of names that round.
        owed = schedule.periods_for_dataset(did, until=horizon, agreement=agr)
        for dp in owed:
            assert schedule.supplies_in_round(did, dp.round.date, agr), (did, dp.round.name)
            filled = schedule.period_filled_by(did, dp.round, agr)
            assert filled is not None and filled.name == dp.period.name, (did, dp.period.name)
            assert schedule.round_of(dp.period.name, did, agr) == dp.round.date, \
                (did, dp.period.name)
        # THE SLOT'S VERSION: the slot instants, the claim window and the
        # recorded verdict inputs all read slots.slot_version.
        for rnd in sequence[-20:]:
            version = slots.slot_version(did, rnd.date, agr)
            assert version is not None, (did, rnd.name)
            try:
                checked = slots.participation_for(did, rnd.date, agr)
            except schedule.ScheduleConfigError:
                continue
            assert checked == version, (did, rnd.name)
            if version.claim_window is not None:
                assert schedule.claim_window(did, on=rnd.date, agreement=agr) \
                    == version.claim_window, (did, rnd.name)
    assert walked, "test precondition - some round was walked"


@pytest.mark.asset("quarterly")
def test_every_quarterly_round_answers_each_rule_once():
    _every_rule_is_answered_once()


@pytest.mark.asset("daily")
def test_every_daily_round_answers_each_rule_once():
    _every_rule_is_answered_once()


# EACH FOLDED SITE GOES THROUGH THE ONE RULE (the post-build critic,
# 2026-11-18): the walk above compares schedule's own functions with each
# other, which a site keeping a copy of `i + files_go_to_period` would never
# disturb. Each site below is driven through its real entry point while
# filled_index records the calls; a site answering from a copy of its own
# records none. An architecture rule observed by behaviour, so it names the
# function rather than reading any source.
DATASET = "cp-case-workers"   # owes February and August at files_go_to_period 1


@pytest.fixture
def recorded(monkeypatch):
    calls = []
    real = schedule.filled_index

    def recording(dataset_id, sequence, i, agreement=None):
        calls.append(dataset_id)
        return real(dataset_id, sequence, i, agreement)

    monkeypatch.setattr(schedule, "filled_index", recording)
    return calls


def _sites():
    from pipeline import owed_nothing, period_slots
    from qa_tools.common import files_go

    on = asset_time.now().date()
    yield "files_go.rounds_fill", lambda: files_go.rounds_fill(DATASET, {2, 8}, on - timedelta(days=900))
    yield "files_go.fall_rounds", lambda: files_go.fall_rounds(DATASET)
    yield "period_slots.for_dataset", lambda: period_slots.for_dataset(DATASET)
    yield "owed_nothing.for_dataset", lambda: owed_nothing.for_dataset(DATASET, on)
    # participation_view, inheritance's grouping and assignment.fall_hold read
    # the rule too, but only on a turned-off gap, a merged arrival stream and a
    # collection whose files_go_to_period has changed - driven by
    # tests/test_turn_off.py, the period-opening tests and the fall tests
    # (REQ-PIPE-322), not by a plain call on today's configuration.


@pytest.mark.asset("quarterly")
@pytest.mark.parametrize("name", [n for n, _ in _sites()])
def test_each_folded_site_goes_through_the_one_rule(recorded, name):
    call = dict(_sites())[name]
    call()
    assert recorded, f"{name} answered which period a round fills without schedule.filled_index"


#: The data asset this module's tests act for, unless a test says otherwise
#: (C11, Keith 2026-11-02: every test module names its asset) - each test
#: above names its own.
pytestmark = pytest.mark.asset("quarterly")
