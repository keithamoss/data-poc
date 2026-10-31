"""Turning a dataset, or a whole collection, off (REQ-PIPE-179).

Written before the code, as the requirement's TEST FIRST NFR asks: a
turn-off that hides an owed period looks exactly like one that works, so
each case here was seen to fail first.

Two halves, as tests/test_collection_defaults.py is: what the one helper
answers for a dataset on a date, and the schedule gate's refusals, each
broken in ONE way against a copy of the real configuration.

Child Protection is quarterly - periods dated 1 February, May, August and
November - and takes its due time and grace from the collection, so a turn
off at 31 March 2025 leaves 2025-Q2 (1 February) owed and 2025-Q3 (1 May)
owing nothing.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

import shutil

import yaml

from qa_tools.common import agreement, schedule
from qa_tools.common.validate_schedule import Source, validate
from tests.test_collection_defaults import (
    CP, LOG, REAL_CONTRACT_DIR, _collection, _defaults, _doc, _lift, _per_dataset, _text,
    _unshare, _versions)


@pytest.fixture
def broken(tmp_path):
    """The real configuration, copied, changed by `mutate` and gated - as
    tests/test_collection_defaults.py's own fixture does."""
    contract_dir = tmp_path / "contract"
    shutil.copytree(REAL_CONTRACT_DIR, contract_dir)
    src = Source(contract_dir / "data-asset.yaml", contract_dir)

    def apply(mutate):
        path = contract_dir / "calendar.yaml"
        from tests import before_growth

        doc = _per_dataset(_unshare(before_growth.calendar(yaml.safe_load(path.read_text()))))
        mutate(doc)
        path.write_text(yaml.safe_dump(doc, sort_keys=False))
        return validate(src)

    return apply

OFF_LOG = [{"date": "2026-10-14", "author": "a test", "change": "turned off",
            "turns_off": True}]


def _turn_off(version: dict, to: str = "2025-03-31", reason: str = "supplier paused",
              log=None) -> dict:
    version.update(effective_to=to, turned_off_reason=reason)
    version["changelog"] = list(version.get("changelog") or []) + (log or OFF_LOG)
    return version


def _back_on(doc, dataset_id: str, on: str, **values) -> dict:
    """A later version of a dataset's own, restating what the first did."""
    first = {k: v for k, v in _versions(doc, dataset_id)[0].items()
             if k not in ("effective_to", "turned_off_reason", "changelog")}
    version = {**first, "effective_from": on, **values, "changelog": LOG}
    _versions(doc, dataset_id).append(version)
    return version


def _defaults_version(doc) -> dict:
    """Child Protection's one defaults version - put back as the real file
    has it (the shared helpers start from each dataset stating its own)."""
    block = _collection(doc).get("participation_defaults")
    if not block:
        _lift(doc, *CP)
        _defaults(doc, {"effective_from": "2023-01-01", "expected_time": "09:00",
                        "grace": "8h", "changelog": LOG})
        block = _collection(doc)["participation_defaults"]
    return block["versions"][0]


# ---- the one helper (criteria 1, 3, 5, 6, 7, 27) ----------------------

class TestADatasetTurnedOff:
    def test_it_owes_until_its_effective_to_and_nothing_after(self):
        doc = _unshare(_doc())
        _turn_off(_versions(doc, "cp-clients")[0])
        agr = agreement.from_doc(doc)
        on = agr.standing_on("cp-clients", date(2025, 2, 1))
        off = agr.standing_on("cp-clients", date(2025, 5, 1))
        assert on.state == agreement.OWING and on.turned_off is None
        assert off.state == agreement.TURNED_OFF
        assert (off.turned_off.effective_to, off.turned_off.reason, off.turned_off.level) \
            == (date(2025, 3, 31), "supplier paused", agreement.DATASET)

    def test_effective_to_is_inclusive(self):
        doc = _unshare(_doc())
        _turn_off(_versions(doc, "cp-clients")[0])
        agr = agreement.from_doc(doc)
        assert agr.standing_on("cp-clients", date(2025, 3, 31)).state == agreement.OWING
        assert agr.standing_on("cp-clients", date(2025, 4, 1)).state == agreement.TURNED_OFF

    def test_with_no_later_version_it_is_off_for_good(self):
        """Criterion 5."""
        doc = _unshare(_doc())
        _turn_off(_versions(doc, "cp-clients")[0])
        agr = agreement.from_doc(doc)
        off = agr.standing_on("cp-clients", date(2040, 1, 1))
        assert off.state == agreement.TURNED_OFF and off.turned_off.until is None

    def test_a_later_version_turns_it_back_on(self):
        doc = _unshare(_doc())
        _turn_off(_versions(doc, "cp-clients")[0])
        _back_on(doc, "cp-clients", "2026-01-01")
        agr = agreement.from_doc(doc)
        off = agr.standing_on("cp-clients", date(2025, 11, 1))
        assert off.turned_off.until == date(2026, 1, 1)
        assert agr.standing_on("cp-clients", date(2026, 2, 1)).state == agreement.OWING

    def test_the_turn_off_carries_the_last_versions_timing(self):
        """Criterion 27: 'the last applying version's resolved timing' -
        here the collection's due time, which the dataset took while on."""
        doc = _unshare(_doc())
        _turn_off(_versions(doc, "cp-clients")[0])
        off = agreement.from_doc(doc).standing_on("cp-clients", date(2025, 5, 1))
        assert (off.values.expected_time, off.values.grace) == ("09:00", timedelta(hours=8))

    def test_not_yet_owing_is_said_before_turned_off(self):
        doc = _unshare(_doc())
        _versions(doc, "cp-clients")[0]["effective_from"] = "2024-01-01"
        _turn_off(_versions(doc, "cp-clients")[0], to="2024-03-31")
        agr = agreement.from_doc(doc)
        assert agr.standing_on("cp-clients", date(2023, 6, 1)).state == agreement.NOT_YET_OWING

    def test_its_off_periods_are_not_periods_it_owes(self):
        """Criteria 4 and 13: no period, so no slot."""
        doc = _unshare(_doc())
        _turn_off(_versions(doc, "cp-clients")[0])
        _back_on(doc, "cp-clients", "2026-01-01")
        names = [p.period.name for p in
                 schedule.periods_for_dataset("cp-clients", agreement=agreement.from_doc(doc))]
        assert "2025-Q2" in names and "2026-Q2" in names
        assert not {"2025-Q3", "2025-Q4", "2026-Q1"} & set(names)


class TestACollectionTurnedOff:
    def test_every_dataset_taking_its_defaults_is_off(self):
        """Criterion 3, second half - one edit however many datasets."""
        doc = _unshare(_doc())
        _turn_off(_defaults_version(doc))
        agr = agreement.from_doc(doc)
        for ds in ("cp-clients", "cp-carers", "cp-placements"):
            off = agr.standing_on(ds, date(2025, 5, 1))
            assert off.state == agreement.TURNED_OFF, ds
            assert off.turned_off.level == agreement.COLLECTION

    def test_a_datasets_own_version_inside_the_gap_brings_it_alone_back(self):
        """Criterion 6."""
        doc = _unshare(_doc())
        _turn_off(_defaults_version(doc))
        _back_on(doc, "cp-carers", "2025-07-01", expected_time="11:00", grace="2h")
        agr = agreement.from_doc(doc)
        assert agr.standing_on("cp-carers", date(2025, 5, 1)).state == agreement.TURNED_OFF
        back = agr.standing_on("cp-carers", date(2025, 8, 1))
        assert back.state == agreement.OWING and back.brought_back is True
        assert agr.standing_on("cp-clients", date(2025, 8, 1)).state == agreement.TURNED_OFF

    def test_a_later_collection_version_does_not_end_a_datasets_own_turn_off(self):
        """Criterion 6, last clause."""
        doc = _unshare(_doc())
        _turn_off(_versions(doc, "cp-clients")[0])
        _defaults_version(doc)
        _collection(doc)["participation_defaults"]["versions"].append(
            {**{k: v for k, v in _defaults_version(doc).items() if k != "changelog"},
             "effective_from": "2025-07-01", "changelog": LOG})
        agr = agreement.from_doc(doc)
        assert agr.standing_on("cp-clients", date(2025, 8, 1)).state == agreement.TURNED_OFF
        assert agr.standing_on("cp-carers", date(2025, 8, 1)).state == agreement.OWING

    def test_a_dataset_back_on_takes_none_of_its_collections_values(self):
        """Criterion 7: while the collection is off, nothing comes from it."""
        doc = _unshare(_doc())
        _defaults_version(doc)["claim_window"] = "10d"
        _turn_off(_defaults_version(doc))
        _back_on(doc, "cp-carers", "2025-07-01", expected_time="11:00", grace="2h")
        back = agreement.from_doc(doc).participation_on("cp-carers", date(2025, 8, 1))
        assert (back.expected_time, back.grace) == ("11:00", timedelta(hours=2))
        assert back.claim_window is None
        assert back.sources["claim_window"] == (agreement.FALLBACK, None)


class TestWhenItWasTurnedOff:
    def test_the_newest_turns_off_changelog_entry_dates_it(self):
        """Criterion 41, without a correction: the newest entry carrying
        turns_off: true."""
        doc = _unshare(_doc())
        _turn_off(_versions(doc, "cp-clients")[0], log=[
            {"date": "2026-09-01", "author": "a", "change": "off", "turns_off": True},
            {"date": "2026-10-02", "author": "a", "change": "moved", "turns_off": True},
            {"date": "2026-10-09", "author": "a", "change": "typo"}])
        off = agreement.from_doc(doc).standing_on("cp-clients", date(2025, 5, 1))
        assert off.turned_off.authored_on == date(2026, 10, 2)


# ---- the gate ------------------------------------------------------------

def _clean(errors, *words):
    """The errors naming every one of `words` - the gate reports the whole
    file, so a case looks only at what its one break produced."""
    return [e for e in errors if all(w in str(e) for w in words)]


class TestTheGateAcceptsATurnOff:
    def test_a_permanent_turn_off(self, broken):
        def mutate(doc):
            _turn_off(_versions(doc, "cp-clients")[0])
        assert broken(mutate) == []

    def test_a_temporary_one_with_no_restating_of_its_own_keys(self, broken):
        """Criterion 10: effective_to and turned_off_reason belong to the one
        version that states them, so the next version need not restate them."""
        def mutate(doc):
            _turn_off(_versions(doc, "cp-clients")[0])
            _back_on(doc, "cp-clients", "2026-01-01")
        assert broken(mutate) == []

    def test_a_permanent_one_after_the_calendars_last_period(self, broken):
        """Criterion 9, last clause."""
        def mutate(doc):
            _turn_off(_versions(doc, "cp-clients")[0], to="2030-12-31")
        assert broken(mutate) == []


class TestTheKeysComeTogether:
    """Criterion 2."""

    def test_effective_to_without_a_reason(self, broken):
        def mutate(doc):
            _turn_off(_versions(doc, "cp-clients")[0]).pop("turned_off_reason")
        got = _text(broken(mutate))
        assert "effective_to" in got and "turned_off_reason" in got and "cp-clients" in got

    def test_a_reason_without_effective_to(self, broken):
        def mutate(doc):
            _turn_off(_versions(doc, "cp-clients")[0]).pop("effective_to")
        got = _text(broken(mutate))
        assert "turned_off_reason" in got and "effective_to" in got

    def test_reason_in_place_of_turned_off_reason_is_named(self, broken):
        def mutate(doc):
            v = _turn_off(_versions(doc, "cp-clients")[0])
            v["reason"] = v.pop("turned_off_reason")
        got = _text(broken(mutate))
        assert "turned_off_reason is the key" in got
        assert "only some periods" in got


class TestTheChangelogSaysItTurnsOff:
    """Criterion 40."""

    def test_no_turns_off_entry_prints_one_to_paste(self, broken):
        def mutate(doc):
            _turn_off(_versions(doc, "cp-clients")[0],
                      log=[{"date": "2026-10-14", "author": "a", "change": "off"}])
        errors = broken(mutate)
        got = _text(errors)
        assert "cp-clients" in got and "2023-01-01" in got
        assert "\n      turns_off: true" in got
        assert "\n    - date: " in got

    @pytest.mark.parametrize("value", [False, "yes", 1])
    def test_turns_off_accepts_only_true(self, broken, value):
        def mutate(doc):
            _turn_off(_versions(doc, "cp-clients")[0], log=[
                {"date": "2026-10-14", "author": "a", "change": "off", "turns_off": value}])
        assert "turns_off" in _text(broken(mutate))

    def test_on_a_collection_version_too(self, broken):
        def mutate(doc):
            _turn_off(_defaults_version(doc),
                      log=[{"date": "2026-10-14", "author": "a", "change": "off"}])
        got = _text(broken(mutate))
        assert "child-protection" in got and "turns_off: true" in got


class TestEffectiveToFits:
    """Criterion 9."""

    def test_before_its_own_effective_from(self, broken):
        def mutate(doc):
            _turn_off(_versions(doc, "cp-clients")[0], to="2022-12-31")
        got = _text(broken(mutate))
        assert "before" in got and "2022-12-31" in got and "cp-clients" in got

    def test_on_or_after_the_next_versions_effective_from(self, broken):
        def mutate(doc):
            _turn_off(_versions(doc, "cp-clients")[0], to="2026-01-01")
            _back_on(doc, "cp-clients", "2026-01-01")
        got = _text(broken(mutate))
        assert "2026-01-01" in got and "next version" in got

    def test_a_gap_holding_no_period(self, broken):
        """31 March to 1 April 2025 - no Child Protection period between."""
        def mutate(doc):
            _turn_off(_versions(doc, "cp-clients")[0], to="2025-03-31")
            _back_on(doc, "cp-clients", "2025-04-15")
        got = _text(broken(mutate))
        assert "no period" in got and "2025-03-31" in got


class TestNotInheritable:
    """Criterion 10."""

    def test_turned_off_reason_inherit_is_refused(self, broken):
        def mutate(doc):
            _turn_off(_versions(doc, "cp-clients")[0], reason="inherit")
        assert "turned_off_reason" in _text(broken(mutate))

    def test_effective_to_inherit_is_refused(self, broken):
        def mutate(doc):
            _turn_off(_versions(doc, "cp-clients")[0], to="inherit")
        assert "effective_to" in _text(broken(mutate))


class TestBackOnInsideTheCollectionsGap:
    """Criterion 7, the gate half."""

    def test_a_value_the_collection_supplied_must_be_stated(self, broken):
        def mutate(doc):
            _turn_off(_defaults_version(doc))
            _back_on(doc, "cp-carers", "2025-07-01", expected_time="11:00")
        got = _text(broken(mutate))
        assert "cp-carers" in got and "grace" in got and "8h" in got

    def test_stating_them_all_is_accepted(self, broken):
        def mutate(doc):
            _turn_off(_defaults_version(doc))
            _back_on(doc, "cp-carers", "2025-07-01", expected_time="11:00", grace="2h")
        assert broken(mutate) == []


class TestNotExpectedInsideAGap:
    """Criterion 21."""

    def test_its_own_gap(self, broken):
        def mutate(doc):
            _turn_off(_versions(doc, "cp-clients")[0])
            next(d for d in doc["datasets"] if d["id"] == "cp-clients")["not_expected"] = [
                {"period": "2025-Q4", "reason": "no file"}]
        got = _text(broken(mutate))
        assert "2025-Q4" in got and "not_expected" in got and "supplier paused" in got
        assert "for good" in got

    def test_its_collections_gap(self, broken):
        def mutate(doc):
            _turn_off(_defaults_version(doc), reason="whole collection paused")
            next(d for d in doc["datasets"] if d["id"] == "cp-clients")["not_expected"] = [
                {"period": "2025-Q4", "reason": "no file"}]
        got = _text(broken(mutate))
        assert "2025-Q4" in got and "whole collection paused" in got


# ---- slots, filing and holds (criteria 13-20, 22) ---------------------------

from datetime import datetime  # noqa: E402

from qa_tools.common import asset_time, slots, turned_off  # noqa: E402


def _at(day: str, hhmm: str = "09:00") -> datetime:
    return asset_time.wall_clock(date.fromisoformat(day), hhmm)


def _off_for_a_while(doc=None, *, back: str = "2026-01-01") -> dict:
    """cp-clients turned off after 31 March 2025, back on from `back`."""
    doc = doc or _unshare(_doc())
    _turn_off(_versions(doc, "cp-clients")[0])
    _back_on(doc, "cp-clients", back)
    return doc


@pytest.fixture
def using(monkeypatch, tmp_path):
    """Point every reader of the committed agreement at `doc`."""
    def apply(doc):
        path = tmp_path / "calendar.yaml"
        path.write_text(yaml.safe_dump(doc, sort_keys=False))
        monkeypatch.setattr(agreement, "CALENDAR_YAML", path)
        return agreement.current()
    yield apply


class TestTheLastOwedSlotBeforeAGap:
    """Criterion 14 - test first, because a slot that closed early would
    hold a late supply that was owed."""

    def test_closes_when_the_gaps_first_period_would_have_opened(self):
        agr = agreement.from_doc(_off_for_a_while())
        real = agreement.from_doc(_unshare(_doc()))
        [q1] = [s for s in slots.slots_for_dataset("cp-clients", agreement=agr)
                if s.name == "2025-Q2"]
        [real_q1] = [s for s in slots.slots_for_dataset("cp-clients", agreement=real)
                     if s.name == "2025-Q2"]
        assert q1.closes_at == real_q1.closes_at
        assert q1.closes_at == _at("2025-05-01") - timedelta(days=14)

    def test_with_a_collections_values_resolved_as_if_never_off(self):
        """The gap's first period takes the collection's inputs even though
        the collection gives nothing while it is off (criterion 7)."""
        doc = _unshare(_doc())
        _defaults_version(doc)["expected_time"] = "13:00"
        _turn_off(_defaults_version(doc))
        agr = agreement.from_doc(doc)
        [q1] = [s for s in slots.slots_for_dataset("cp-clients", agreement=agr)
                if s.name == "2025-Q2"]
        assert q1.closes_at == _at("2025-05-01", "13:00") - timedelta(days=14)


    def test_inputs_are_those_of_the_gaps_own_date_not_the_last_day_on(self):
        """A collection version taking effect inside a dataset's own gap
        moves the due time from 09:00 to 13:00. The gap's first period
        would have had 13:00 - not the dataset's last day on, 09:00."""
        doc = _unshare(_doc())
        first = _defaults_version(doc)
        _collection(doc)["participation_defaults"]["versions"].append(
            {**{k: v for k, v in first.items() if k != "changelog"},
             "effective_from": "2025-04-15", "expected_time": "13:00", "changelog": LOG})
        _turn_off(_versions(doc, "cp-clients")[0])
        agr = agreement.from_doc(doc)
        [q1] = [s for s in slots.slots_for_dataset("cp-clients", agreement=agr)
                if s.name == "2025-Q2"]
        assert q1.closes_at == _at("2025-05-01", "13:00") - timedelta(days=14)


    def test_the_claim_window_too(self):
        """The same, for a collection version widening the window inside the
        gap: 2025-Q2 closes when 2025-Q3 would have opened under 20 days."""
        doc = _unshare(_doc())
        first = _defaults_version(doc)
        _collection(doc)["participation_defaults"]["versions"].append(
            {**{k: v for k, v in first.items() if k != "changelog"},
             "effective_from": "2025-04-01", "claim_window": "20d", "changelog": LOG})
        _turn_off(_versions(doc, "cp-clients")[0])
        agr = agreement.from_doc(doc)
        [q1] = [s for s in slots.slots_for_dataset("cp-clients", agreement=agr)
                if s.name == "2025-Q2"]
        assert q1.closes_at == _at("2025-05-01") - timedelta(days=20)


class TestWhatAReceiptFallsIn:
    """Criteria 15, 16 and 17."""

    def test_an_owed_slot_still_open_takes_it_whatever_the_date(self):
        """Criterion 15: turned off on 10 April, and 2025-Q2 still open."""
        agr = agreement.from_doc(_off_for_a_while())
        got = turned_off.label_at("cp-clients", _at("2025-04-10"), agr)
        assert got.covered_by == "2025-Q2" and got.label == turned_off.PLAIN

    def test_once_it_closes_the_supply_is_held_as_turned_off(self):
        agr = agreement.from_doc(_off_for_a_while())
        got = turned_off.label_at("cp-clients", _at("2025-06-01"), agr)
        assert got.label == turned_off.TURNED_OFF and got.covered_by is None
        assert (got.turned_off.effective_to, got.turned_off.reason, got.turned_off.level) \
            == (date(2025, 3, 31), "supplier paused", agreement.DATASET)

    def test_turned_off_outranks_schedule_ended(self):
        """Criterion 17: off for good, so its last owed slot is its last."""
        doc = _unshare(_doc())
        _turn_off(_versions(doc, "cp-clients")[0])
        agr = agreement.from_doc(doc)
        assert turned_off.final_period("cp-clients", agr) == "2025-Q2"
        assert turned_off.label_at("cp-clients", _at("2025-06-01"), agr).label \
            == turned_off.TURNED_OFF

    def test_back_on_its_owed_slot_takes_it(self):
        agr = agreement.from_doc(_off_for_a_while())
        assert turned_off.label_at("cp-clients", _at("2026-01-25"), agr).covered_by == "2026-Q2"

    def test_the_real_configuration_holds_nothing_as_turned_off(self):
        assert turned_off.gap_at("cp-clients", _at("2025-06-01")) is None


class TestATurnedOffPeriodIsNotParticipated:
    """Criterion 22: inheritance stands the last promoted supply in it."""

    def test_inheritance_reads_it_as_owing_nothing(self, using):
        from qa_tools.common import inheritance

        using(_off_for_a_while())
        skipped, why = inheritance._does_not_participate("cp-clients", "2025-Q4")
        assert skipped and "turned off" in why and "supplier paused" in why
        assert inheritance._does_not_participate("cp-clients", "2026-Q2") == (False, "")


class TestNothingIsPlacedIntoAGap:
    """Criterion 20: one refusal, naming the gap and how a period becomes
    owed - in place of 'not a period it owes'."""

    def test_placing(self, using):
        from qa_tools.common import placing

        using(_off_for_a_while())
        why = placing.period_problem("cp-clients", "2025-Q4")
        assert "turned off" in why and "supplier paused" in why
        assert "effective_to" in why and "contract/calendar.yaml" in why
        assert "does not participate" not in why

    def test_an_owed_period_is_still_fine(self, using):
        from qa_tools.common import placing

        using(_off_for_a_while())
        assert placing.period_problem("cp-clients", "2026-Q2") is None

    def test_refiling_gives_the_same_refusal(self, using):
        from qa_tools.common import refiling

        using(_off_for_a_while())
        why = refiling.gap_problem("cp-clients", "2025-Q4")
        assert why == turned_off.refusal("cp-clients", "2025-Q4")
        assert "supplier paused" in why


# ---- holds, recorded and read (criteria 16, 18, 19, 34) --------------------

from qa_tools.common import qa_store, supply_db, supply_holds  # noqa: E402

GAP = _at("2025-06-01")


@pytest.fixture
def conn(supply_dsn):
    """This worker's database, forgetting the filings and holds each test
    makes - they sit in slots of a changed agreement, and left behind the
    agreement backstop would read them as moved."""
    import filing_support
    from qa_tools.common import filing

    with supply_db.connect(label="test-turn-off") as c:
        qa_store.ensure_schema(c)
        c.execute(f"DELETE FROM {supply_holds.TABLE} WHERE dataset_id = 'cp-clients'")
        (before,) = c.execute(f"SELECT coalesce(max(id), 0) FROM {filing.TABLE}").fetchone()
        try:
            yield c
        finally:
            c.execute(f"DELETE FROM {supply_holds.TABLE} WHERE dataset_id = 'cp-clients'")
            filing_support.forget(c, "dataset_id = 'cp-clients' AND id > ?", [before])


def _hold(conn, supply: str, at: datetime):
    """File and hold a supply received at `at`, as the pipeline does."""
    import filing_support
    from qa_tools.common import filing

    decided = filing.assignment_at("cp-clients", supply, at)
    filing_support.file(decided)
    supply_holds.raise_hold(conn, dataset_id="cp-clients", supply_id=supply,
                            kind=supply_holds.ASSIGNMENT_RULE,
                            reason=supply_holds.reason_for(decided), raised_by="run_x",
                            delivery=f"pytest-cp-clients-{supply}")
    return decided


class TestHeldWhileTurnedOff:
    def test_the_rule_records_the_turn_off_as_history(self, conn, using):
        """Criterion 16."""
        using(_off_for_a_while())
        decided = _hold(conn, "cp-clients@to1", GAP)
        assert decided.is_held and not decided.schedule_ended
        recorded = supply_holds.hold_on(conn, "cp-clients", "cp-clients@to1").reason
        assert recorded["turned_off"] == {"effective_to": "2025-03-31", "reason": "supplier paused",
                                          "level": "dataset", "version_from": "2023-01-01"}

    def test_it_says_what_to_do(self, conn, using):
        """Criterion 34's sentence and three responses."""
        using(_off_for_a_while())
        _hold(conn, "cp-clients@to2", GAP)
        held = supply_holds.hold_on(conn, "cp-clients", "cp-clients@to2")
        assert held.turned_off and not held.schedule_ended
        assert held.describe() == (
            "Received while Client Register is turned off (supplier paused, set for Client "
            "Register). Place it into a period it still owes, reject it, or change "
            "effective_to/effective_from in contract/calendar.yaml if this period should be "
            "owed.")
        place, reject, change = held.responses
        assert "mothman supply decide --operation place" in place
        assert reject == "reject the supply" and "effective_to/effective_from" in change

    def test_off_for_good_is_turned_off_not_schedule_ended(self, conn, using):
        """Criterion 17, at filing."""
        doc = _unshare(_doc())
        _turn_off(_versions(doc, "cp-clients")[0])
        using(doc)
        decided = _hold(conn, "cp-clients@to3", GAP)
        assert decided.turned_off and not decided.schedule_ended


class TestTheLabelIsReadFromConfigurationNow:
    """Criterion 18: the recorded reason is history only."""

    def test_a_turn_off_added_since_relabels_an_old_hold(self, conn, using):
        """Held plainly (a recorded reason with no turn-off in it), then
        the dataset is turned off over its receipt."""
        using(_off_for_a_while())
        supply_holds.raise_hold(conn, dataset_id="cp-clients", supply_id="cp-clients@to4",
                                kind=supply_holds.ASSIGNMENT_RULE, reason={"unavailable": []},
                                raised_by="run_x")
        import filing_support
        from qa_tools.common import filing
        filing_support.file(filing.assignment_at("cp-clients", "cp-clients@to4", GAP))
        held = supply_holds.hold_on(conn, "cp-clients", "cp-clients@to4")
        assert held.turned_off

    def test_a_turn_off_removed_since_is_no_longer_one(self, conn, using):
        using(_off_for_a_while())
        _hold(conn, "cp-clients@to5", GAP)
        using(_unshare(_doc()))
        held = supply_holds.hold_on(conn, "cp-clients", "cp-clients@to5")
        assert not held.turned_off
        assert held.label.covered_by == "2025-Q3"
        assert held.reason["turned_off"]["reason"] == "supplier paused", "history stays"


class TestCoveredHoldsFileThemselves:
    """Criterion 19: whatever its label, a hold whose receipt now has an
    open owed slot is filed by the rule on the next pass."""

    def test_a_turned_off_hold_files_once_the_period_is_owed(self, conn, using):
        from qa_tools.common import filing, schedule_ended

        using(_off_for_a_while())
        _hold(conn, "cp-clients@to6", GAP)
        assert schedule_ended.refile_covered(say=lambda line: None) == []
        using(_unshare(_doc()))
        done = schedule_ended.refile_covered(say=lambda line: None)
        assert ("cp-clients", "cp-clients@to6", "2025-Q3") in done
        assert filing.filing_for("cp-clients", "cp-clients@to6")["slot"] == "2025-Q3"
        assert supply_holds.hold_on(conn, "cp-clients", "cp-clients@to6") is None


# ---- the freeze (criteria 11, 12 and 30) -------------------------------------

import copy as _copy  # noqa: E402

from qa_tools.common import agreement_freeze as freeze  # noqa: E402
from tests.test_agreement_freeze import CODEOWNERS, KEITH, _correction, _load  # noqa: E402

PERTH = asset_time.wall_clock(date(2026, 10, 14), "23:00").tzinfo
TONIGHT = datetime(2026, 10, 14, 23, 0, tzinfo=PERTH)
CLIENTS_KEY = "dataset cp-clients participation 2023-01-01 effective_to"


def _clients_version(doc) -> dict:
    """cp-clients' own first version, unshared from the anchor the real file
    gives all six Child Protection datasets."""
    entry = next(d for d in doc["datasets"] if d["id"] == "cp-clients")
    entry["participation"]["versions"] = [dict(v) for v in entry["participation"]["versions"]]
    return entry["participation"]["versions"][0]


def _freeze_check(old_cal, change, at=TONIGHT):
    asset, people = _load("data-asset.yaml"), _load("people.yaml")
    new_cal = _copy.deepcopy(old_cal)
    change(new_cal)
    return freeze.check(old_cal, new_cal, asset, _copy.deepcopy(asset), people,
                        instant_of=lambda key: at, today=at.date(), base_codeowners=CODEOWNERS)


def _findings_text(found):
    return "\n".join(f"{f.scope} | {f.problem} | {f.fix}" for f in found)


class TestATurnOffFreezesWhenItsPeriodsDo:
    def test_turning_off_from_a_period_not_yet_open_is_an_ordinary_edit(self):
        """2027-Q2's window opens 18 January 2027 - nothing it flips has
        started to matter."""
        assert _freeze_check(_load("calendar.yaml"), lambda doc: _turn_off(
            _clients_version(doc), to="2026-12-31")) == []

    def test_turning_off_a_past_period_needs_a_correction(self):
        found = _freeze_check(_load("calendar.yaml"),
                              lambda doc: _turn_off(_clients_version(doc)))
        got = _findings_text(found)
        assert CLIENTS_KEY in got
        assert "cp-clients 2025-Q3" in got and "2025-04-17T09:00" in got
        assert "\n  mothman schedule draft-correction" in got
        assert "mark-not-supplied" in got

    def test_moving_a_future_turn_off_later_is_an_ordinary_edit(self):
        old = _load("calendar.yaml")
        _turn_off(_clients_version(old), to="2026-12-31")
        assert _freeze_check(old, lambda doc: _clients_version(doc).update(
            effective_to="2027-06-30")) == []

    def test_its_reason_freezes_with_it(self):
        """Criterion 12: a change of wording after the freeze, too."""
        old = _load("calendar.yaml")
        _turn_off(_clients_version(old))
        found = _freeze_check(old, lambda doc: _clients_version(doc).update(
            turned_off_reason="supplier paused while it rebuilt its system"))
        assert CLIENTS_KEY in _findings_text(found)

    def test_a_declared_correction_is_accepted(self):
        def change(doc):
            _turn_off(_clients_version(doc))
            entry = next(d for d in doc["datasets"] if d["id"] == "cp-clients")
            _correction(entry, (CLIENTS_KEY, None, {"effective_to": "2025-03-31",
                                                    "turned_off_reason": "supplier paused"}),
                        approver=KEITH)
        assert _freeze_check(_load("calendar.yaml"), change) == []

    def test_the_rest_of_the_version_is_not_reopened(self):
        """The version's other values are frozen from 2023 as before."""
        found = _freeze_check(_load("calendar.yaml"), lambda doc: _clients_version(doc).update(
            claim_window="10d"))
        assert "dataset cp-clients participation 2023-01-01" in _findings_text(found)


class TestACorrectionOfATurnOffReverts:
    """What the impact preview and the correction trial rebuild (REQ-PIPE-169)."""

    def test_reverting_puts_the_old_turn_off_back(self):
        new = _load("calendar.yaml")
        _turn_off(_clients_version(new), to="2025-06-30")
        cal, _asset = freeze.revert(new, _load("data-asset.yaml"), [
            (CLIENTS_KEY, {"effective_to": "2025-03-31", "turned_off_reason": "was"}, None)])
        v = _clients_version(cal)
        assert (v["effective_to"], v["turned_off_reason"]) == ("2025-03-31", "was")

    def test_reverting_an_added_one_removes_it(self):
        new = _load("calendar.yaml")
        _turn_off(_clients_version(new))
        cal, _asset = freeze.revert(new, _load("data-asset.yaml"), [(CLIENTS_KEY, None, {})])
        assert "effective_to" not in _clients_version(cal)

    def test_reverting_the_version_keeps_its_turn_off(self):
        new = _load("calendar.yaml")
        _turn_off(_clients_version(new))
        cal, _asset = freeze.revert(new, _load("data-asset.yaml"), [
            ("dataset cp-clients participation 2023-01-01", {}, {"claim_window": "10d"})])
        assert _clients_version(cal)["effective_to"] == "2025-03-31"


# ---- runway and the overlap gate (criteria 25 and 31) -----------------------

class TestRunway:
    def test_off_for_good_is_not_an_exhausted_schedule(self, using):
        from qa_tools.common import runway

        doc = _unshare(_doc())
        _turn_off(_versions(doc, "cp-clients")[0])
        using(doc)
        assert runway.off_for_good("cp-clients", date(2026, 10, 14))
        assert "cp-clients" not in runway.exhausted_datasets(date(2026, 10, 14))
        assert runway.calendar_runway("quarterly", date(2026, 10, 14)).driving_dataset \
            != "cp-clients"

    def test_a_temporary_gap_counts_only_what_is_owed_once_back_on(self, using):
        from qa_tools.common import runway

        doc = _unshare(_doc())
        # Back on from the August 2027 round: its files fill 2027-Q4, and the
        # November round's would fill 2028-Q1, which the calendar gives no date
        # (REQ-PIPE-321 criterion 8) - so one slot is owed once back on.
        _turn_off(_versions(doc, "cp-clients")[0], to="2026-10-31")
        _back_on(doc, "cp-clients", "2027-07-15")
        using(doc)
        assert not runway.off_for_good("cp-clients", date(2026, 10, 14))
        got = runway.calendar_runway("quarterly", date(2026, 10, 14))
        assert (got.driving_dataset, got.remaining) == ("cp-clients", 1)


class TestTheOverlapGate:
    """Criterion 31, all three clauses (the requirement's 'amendments
    nobody else states' NFR)."""

    def _overlaps(self, **back):
        from qa_tools.common import period_overlap

        doc = _off_for_a_while()
        _versions(doc, "cp-clients")[-1].update(back)
        return period_overlap.overlaps_for("cp-clients", agreement=agreement.from_doc(doc))

    def test_a_gap_alone_overlaps_nothing(self):
        assert self._overlaps() == []

    def test_the_first_owed_slot_after_a_gap_is_checked_against_the_last_before(self):
        """Back on with a 300-day window, 2026-Q2 opens 7 April 2025 -
        before 2025-Q2 closes on 17 April."""
        found = self._overlaps(claim_window="300d")
        pairs = {(o.earlier, o.later) for o in found}
        assert ("2025-Q2", "2026-Q2") in pairs
        assert not any(o.earlier in ("2025-Q3", "2025-Q4", "2026-Q1") for o in found), \
            "a pair inside one gap is skipped"
        [o] = [o for o in found if o.later == "2026-Q2"]
        assert o.on_time_until == _at("2025-05-01") - timedelta(days=14)


class TestNotAStateNeedingAPerson:
    """Criteria 24 and 26: counted apart, one line per label, and never
    among what needs a person."""

    def test_the_tally(self, conn, using):
        using(_off_for_a_while())
        _hold(conn, "cp-clients@tc1", GAP)
        counted = supply_holds.tally(conn)
        assert counted.turned_off == (1, 1)
        assert counted.needing_a_person == counted.total - 1
        assert "received while turned off - not counted as needing a person" \
            in counted.summary()

    def test_d12_a_dataset_held_only_while_off_is_not_listed_as_needing_a_person(
            self, conn, using):
        """post-build-review #190 D12."""
        using(_off_for_a_while())
        _hold(conn, "cp-clients@d12", GAP)
        counted = supply_holds.tally(conn)
        assert "cp-clients" not in counted.datasets_needing
        assert "cp-clients" not in counted.summary().split(" received while")[0]

    def test_d12_holds_lists_no_quiet_row(self, conn, using, monkeypatch):
        """`mothman supply holds` lists only what needs a person; the quiet
        ones are the summary's count."""
        from click.testing import CliRunner

        from cli import supply as supply_cli

        using(_off_for_a_while())
        _hold(conn, "cp-clients@d12b", GAP)
        # A HOLD THAT DOES NEED A PERSON, so the rows are listed at all.
        supply_holds.raise_hold(conn, dataset_id="cp-clients", supply_id="cp-clients@d12p",
                                kind=supply_holds.ASSIGNMENT_RULE,
                                reason={"unavailable": [], "considered": []}, raised_by="run_x")
        got = CliRunner().invoke(supply_cli.supply_group, ["holds"])
        assert got.exit_code == 0, got.output
        assert "cp-clients@d12p" in got.output
        assert "cp-clients@d12b" not in got.output

    def test_the_pass_counts_them_apart(self, conn, using):
        from qa_tools.common import schedule_ended

        using(_off_for_a_while())
        _hold(conn, "cp-clients@tc2", GAP)
        assert schedule_ended.turned_off_by_runs(conn, ["run_x"]) == (1, 1)
        assert schedule_ended.raised_by_runs(conn, ["run_x"]) == (0, 0)
        assert "received while turned off" in schedule_ended.turned_off_pass_line((1, 1))

    def test_the_outstanding_list_shows_it_quietly(self, conn, using):
        from qa_tools.common import outstanding

        using(_off_for_a_while())
        _hold(conn, "cp-clients@tc3", GAP)
        [item] = [i for i in outstanding._from_holds(conn) if i.dataset_id == "cp-clients"]
        assert item.severity == outstanding.INFORMATIONAL and not item.blocking

    def test_the_page_is_told_it_is_this_kind(self, conn, using):
        from qa_tools.common import dataset_blockers

        using(_off_for_a_while())
        _hold(conn, "cp-clients@tc4", GAP)
        [b] = [b for b in dataset_blockers._holds(conn) if b.supply == "cp-clients@tc4"]
        assert b.as_record()["turnedOff"] is True and b.as_record()["scheduleEnded"] is False

    def test_a_resolved_one_says_how_it_ended(self, conn, using):
        """REQ-DASH-180 criterion 14 as amended 2026-10-15 (post-build-review
        #196 F2): the section lists every supply held while off, and a
        resolved one says how it ended - so the page is told the decision
        that ended it: its action, whether a person or the rule, who, when
        and the period it went to."""
        from qa_tools.common import dataset_blockers
        from qa_tools.common import decision_log as dl

        using(_off_for_a_while())
        _hold(conn, "cp-clients@tc5", GAP)
        with conn.raw.transaction():
            with dl.apply_decision(conn, dl.Decision(
                    agency_id="child-protection-family-support", collection_id="child-protection",
                    dataset_id="cp-clients", action=dl.REFILE, supply="cp-clients@tc5",
                    actor="schedule drain", actor_kind=dl.RULE,
                    effective_at="2026-02-03T01:00:00+00:00", from_slot=None, to_slot="2026-Q2",
                    reason="owed again")) as decision_id:
                supply_holds.resolve(conn, dataset_id="cp-clients", supply_id="cp-clients@tc5",
                                     decision_id=decision_id)
        [b] = [b for b in dataset_blockers._holds(conn) if b.supply == "cp-clients@tc5"]
        ended = b.as_record()["ended"]
        assert ended["action"] == dl.REFILE and ended["actorKind"] == dl.RULE
        assert ended["toPeriod"] == "2026-Q2" and ended["at"].startswith("2026-02-03")

    def test_an_open_one_has_no_ending(self, conn, using):
        from qa_tools.common import dataset_blockers

        using(_off_for_a_while())
        _hold(conn, "cp-clients@tc6", GAP)
        [b] = [b for b in dataset_blockers._holds(conn) if b.supply == "cp-clients@tc6"]
        assert b.as_record()["ended"] is None


class TestTheQuietGroup:
    """Criterion 34: one row per dataset, opening to its supplies."""

    @staticmethod
    def _row(ds, supply, day, off=True):
        from qa_tools.common import filing_queue

        return filing_queue.HeldRow(
            dataset_id=ds, dataset_name=ds, supply=supply, received_at=_at(day),
            received_text=day, why="", schedule_ended=False, turned_off=off)

    def test_one_row_per_dataset_counting_supplies_and_naming_the_earliest(self):
        from qa_tools.common import filing_queue

        rows = [self._row("cp-clients", f"cp-clients@{d}", f"2025-06-0{d}") for d in (3, 1, 2)]
        rows += [self._row("cp-carers", "cp-carers@1", "2025-07-01"),
                 self._row("cp-carers", "cp-carers@plain", "2025-07-02", off=False)]
        groups = filing_queue.turned_off_groups(rows)
        assert [g.line for g in groups] == [
            "cp-carers - 1 received while turned off, earliest 1 July 2025",
            "cp-clients - 3 received while turned off, earliest 1 June 2025"]

    def test_the_queue_lists_them_last_and_apart(self, conn, using, monkeypatch):
        from cli import filing_tui

        using(_off_for_a_while())
        _hold(conn, "cp-clients@tq1", GAP)
        printed = []
        monkeypatch.setattr(filing_tui.console, "print",
                            lambda *a, **k: printed.append(" ".join(str(x) for x in a)))
        monkeypatch.setattr(filing_tui.common, "select", lambda *a, **k: None)
        filing_tui.queue_flow("child-protection")
        text = "\n".join(printed)
        assert "Received while turned off (1)" in text
        assert "cp-clients - 1 received while turned off, earliest 1 June 2025" in text
        assert "cp-clients (the supply" not in text.split("Received while turned off")[0], \
            "not listed in the held group above it"


# ---- what a person reads (criteria 28 and 29) --------------------------------

class TestScheduleShowSaysSo:
    def _view(self, doc, on):
        from qa_tools.common import participation_view

        return participation_view.view("cp-clients", on, agreement.from_doc(doc))

    def test_turned_off_and_nothing_due(self):
        v = self._view(_off_for_a_while(), date(2025, 9, 1))
        assert v.headline == "Turned off - nothing due"
        labels = {x.label: x.text for x in v.values}
        assert labels["Owes"] == "nothing - turned off"
        assert labels["Due time (when last on)"] == "09:00"
        said = "\n".join(v.turn_off)
        assert "Turned off after 31 Mar 2025 (supplier paused), set for Client Register, " \
               "until 1 Jan 2026." in said
        assert "Owes nothing in 2025-Q3 to 2026-Q1." in said
        assert "declared correction" in said

    def test_still_owing_its_last_slot(self):
        """2025-Q2's slot is open until 17 April - turned off on the date
        asked about, and the slot still owed."""
        v = self._view(_off_for_a_while(), date(2025, 4, 10))
        assert v.headline is None
        assert "Still owes 2025-Q2: its slot stays open until 17 Apr 2025 09:00." \
            in v.turn_off

    def test_turning_off_with_nothing_more_owed(self):
        """Owing until 31 July; its last owed period, 2025-Q3, closed on 18
        July when 2025-Q4's window would have opened."""
        doc = _unshare(_doc())
        _turn_off(_versions(doc, "cp-clients")[0], to="2025-07-31",
                  log=[{"date": "2025-07-01", "author": "a test", "change": "off",
                        "turns_off": True}])
        v = self._view(doc, date(2025, 7, 25))
        assert v.headline == "Turning off after 31 Jul 2025 - nothing more owed"

    def test_199_f12_the_headline_waits_for_the_authored_date(self):
        """post-build-review #199 F12 (Keith, 2026-10-15): one meaning across
        surfaces - like the page's marker (REQ-DASH-180 c25), the terminal's
        headline waits until the turn-off has been written down."""
        doc = _unshare(_doc())
        _turn_off(_versions(doc, "cp-clients")[0], to="2025-07-31",
                  log=[{"date": "2025-07-28", "author": "a test", "change": "off",
                        "turns_off": True}])
        assert self._view(doc, date(2025, 7, 25)).headline is None
        assert self._view(doc, date(2025, 7, 29)).headline == (
            "Turning off after 31 Jul 2025 - nothing more owed")

    def test_a_turn_off_ahead_is_shown_with_its_ordinary_edit_window(self):
        doc = _unshare(_doc())
        _turn_off(_versions(doc, "cp-clients")[0], to="2027-03-31")
        said = "\n".join(self._view(doc, date(2026, 10, 14)).turn_off)
        # REQ-PIPE-179 c28 AS AMENDED 2026-10-15 (Keith, morning report 5 Q10).
        assert "for good" in said and ("Edit calendar.yaml to change this until 17 Apr 2027 09:00, "
                                       "when the first period's claim window opens. After that it "
                                       "needs a declared correction.") in said

    def test_back_on_inside_its_collections_gap(self):
        doc = _unshare(_doc())
        _turn_off(_defaults_version(doc))
        _back_on(doc, "cp-carers", "2025-07-01", expected_time="11:00", grace="2h")
        from qa_tools.common import participation_view

        v = participation_view.view("cp-carers", date(2025, 8, 1), agreement.from_doc(doc))
        assert v.turn_off[0].startswith("Back on by a version of its own")


class TestTheBuildCarriesIt:
    """Criterion 41."""

    def test_each_turn_off_with_when_it_was_authored(self):
        doc = _off_for_a_while()
        got = turned_off.timeline("cp-clients", agreement.from_doc(doc),
                                  docs=(doc, _load("data-asset.yaml")))
        last = got[0].pop("lastOwed")
        assert got == [{"effectiveTo": "2025-03-31", "until": "2026-01-01",
                        "reason": "supplier paused", "level": "dataset",
                        "versionFrom": "2023-01-01", "authoredOn": "2026-10-14",
                        "authoredBy": "changelog", "collection": "Child Protection"}]
        # THE LAST OWED SLOT BEFORE THE GAP (REQ-DASH-180 criteria 4, 16 and
        # 25): 2025-Q2, closing when 2025-Q3's window would have opened.
        assert last["period"] == "2025-Q2"
        agr = agreement.from_doc(doc)
        slot = next(s for s in slots.slots_for_dataset("cp-clients", until=date(2025, 3, 31),
                                                        agreement=agr) if s.name == "2025-Q2")
        assert last["dueAt"] == slot.due_at.isoformat()
        assert last["closesAt"] == slot.closes_at.isoformat()

    def test_a_declared_correction_dates_it_instead(self):
        doc = _off_for_a_while()
        entry = next(d for d in doc["datasets"] if d["id"] == "cp-clients")
        entry.setdefault("corrections", []).append({
            "change_reference": "CAB-7", "date": "2026-10-20", "author": "a", "approver": "b",
            "reason": "r", "changes": [{"item": CLIENTS_KEY, "old": None,
                                         "new": {"effective_to": "2025-03-31"}}]})
        [got] = turned_off.timeline("cp-clients", agreement.from_doc(doc),
                                    docs=(doc, _load("data-asset.yaml")))
        assert (got["authoredOn"], got["authoredBy"]) == ("2026-10-20", "correction")

    def test_a_dataset_never_turned_off_carries_nothing(self):
        assert turned_off.timeline("cp-clients") == []


class TestAnOwedPeriodStillCounts:
    """Criterion 23 (the 'no false quiet' line): a period owed before the
    turn-off keeps its slot and its state until resolved; the periods inside
    the gap have none."""

    def test_the_queue_still_reads_the_last_owed_period(self, conn, using):
        from qa_tools.common import slot_state

        using(_off_for_a_while())
        states = {s.period for s in slot_state.states_for(conn, "child-protection",
                                                          now=_at("2025-09-01"))
                  if s.dataset_id == "cp-clients"}
        assert "2025-Q2" in states
        assert not {"2025-Q3", "2025-Q4", "2026-Q1"} & states


class TestCriticFindingsOn190:
    """delivery-critic on REQ-PIPE-179 (post-build-review #190). Each failed
    before its fix."""

    def test_d1_a_turn_off_for_good_not_yet_started_still_warns(self, using):
        """Off for good after 2028-12-31, but the calendar ends at 2028-Q1:
        on 1 March 2028 its schedule has ended and it still owes - so it is
        exhausted, not quiet."""
        from qa_tools.common import runway

        doc = _unshare(_doc())
        _turn_off(_versions(doc, "cp-clients")[0], to="2028-12-31")
        using(doc)
        assert not runway.off_for_good("cp-clients", date(2028, 3, 1))
        assert "cp-clients" in runway.exhausted_datasets(date(2028, 3, 1))

    def test_each_gap_is_sent_for_the_page(self, using):
        """REQ-DASH-180 criteria 17 and 20: the page judges 'off for good' on
        the date on show, so the build sends the day it starts."""
        from qa_tools.common import runway

        doc = _unshare(_doc())
        _turn_off(_versions(doc, "cp-clients")[0], to="2028-12-31")
        using(doc)
        # WITH ITS EFFECTIVE_TO AND WHEN IT WAS AUTHORED (REQ-DASH-180
        # criterion 17 as amended 2026-10-15, Q24): the runway line words a
        # for-good turn-off once it is written down.
        [gap] = runway.off_gaps("cp-clients")
        assert (gap["from"], gap["until"], gap["effectiveTo"]) == ("2029-01-01", None, "2028-12-31")
        assert "authoredOn" in gap
        assert runway.off_gaps("cp-carers") == []
        using(_off_for_a_while())
        [gap] = runway.off_gaps("cp-clients")
        assert (gap["from"], gap["until"]) == ("2025-04-01", "2026-01-01")

    def test_199_f7_an_authored_turn_off_stops_driving_the_minimum(self, using):
        """post-build-review #199 F7 (Keith, 2026-10-15): an authored for-good
        turn-off stops driving the runway minimum, as a started one does - so
        while another dataset on the calendar still owes, the minimum is that
        dataset's and the line asks for dates."""
        from qa_tools.common import runway

        doc = _unshare(_doc())
        _turn_off(_versions(doc, "cp-case-workers")[0], to="2027-03-31",
                  log=[{"date": "2026-09-01", "author": "a test", "change": "off",
                        "turns_off": True}])
        using(doc)
        on = date(2026, 9, 23)
        cal = runway.schedule.calendar_for_dataset("cp-case-workers").name
        found = runway.calendar_runway(cal, on)
        assert found.driving_dataset not in (None, "cp-case-workers")
        for line in runway.warning_lines(on):
            assert "no more dates are needed" not in line

    def test_the_gate_says_no_more_dates_are_needed_once_authored(self, using):
        """REQ-DASH-180 criterion 17 as amended 2026-10-15 (Keith, morning
        report 5 Q24): 'the gate's warning likewise' - the line for a
        calendar that runs out first for a dataset with a for-good turn-off
        authored by then says no more dates are needed for it, and does not
        ask for dates. Every Child Protection dataset turns off here: since
        #199 F7 a turning-off dataset drives the minimum only where none on
        its calendar still owes - so every OTHER dataset on Child Protection's
        calendar (Emergency Department's, since REQ-QAC-231) turns off for
        good on the same terms, or it would still owe and drive the minimum."""
        from qa_tools import collections
        from qa_tools.common import runway

        doc = _unshare(_doc())
        log = [{"date": "2026-09-01", "author": "a test", "change": "off", "turns_off": True}]
        _turn_off(_defaults_version(doc), to="2027-03-31", log=log)
        cp_calendar = _collection(doc)["calendar"]
        others = [e["id"] for e in doc["datasets"]
                  if not e["id"].startswith("cp-") and e.get("participation")
                  and _collection(doc, collections.collection_of(e["id"]).id).get("calendar")
                  == cp_calendar]
        for ds in others:
            _turn_off(_versions(doc, ds)[0], to="2027-03-31", log=log)
        using(doc)
        before = runway.warning_lines(date(2026, 8, 1))
        assert before and "candidate-dates" in before[0]
        [line] = runway.warning_lines(date(2026, 9, 23))
        assert ("runs out first for 'cp-case-workers', which turns off for good after "
                "2027-03-31 - no more dates are needed for it") in line
        assert "candidate-dates" not in line and "not failing the build" in line

    def test_d1_a_calendar_whose_datasets_are_all_off_is_not_exhausted(self, using):
        """Every Child Protection dataset off for good: no dataset to count,
        so nothing to say - never 'NO future dates left ... 0 datasets'."""
        from qa_tools.common import runway

        doc = _unshare(_doc())
        _turn_off(_defaults_version(doc))
        using(doc)
        assert not [r for r in runway.low_runway(date(2026, 10, 14))
                    if r.calendar_name == "quarterly"]
        assert not any("0 datasets" in line for line in runway.warning_lines(date(2026, 10, 14)))

    def test_d3_the_backlog_line_reads_the_label_as_it_stands(self, conn, using):
        """A hold recorded as turned off whose turn-off has since gone, after
        the calendar's last period closed, is schedule ended now - and the
        dashboard's backlog line must count it (criterion 18)."""
        import filing_support
        from qa_tools.common import filing, schedule_ended

        late = _at("2029-01-10")
        doc = _unshare(_doc())
        _turn_off(_versions(doc, "cp-clients")[0], to="2027-08-31")
        using(doc)
        decided = filing.assignment_at("cp-clients", "cp-clients@d3", late)
        assert decided.turned_off
        filing_support.file(decided)
        supply_holds.raise_hold(conn, dataset_id="cp-clients", supply_id="cp-clients@d3",
                                kind=supply_holds.ASSIGNMENT_RULE,
                                reason=supply_holds.reason_for(decided), raised_by="run_x")
        assert schedule_ended.for_dataset("cp-clients", conn=conn) == []
        using(_unshare(_doc()))
        assert [asset_time.parse_instant(h["receivedAt"], "x")
                for h in schedule_ended.for_dataset("cp-clients", conn=conn)] == [late]

    def test_d4_a_dataset_brought_back_inside_its_collections_gap_is_not_off_for_good(self):
        """The collection turned off for good; cp-carers came back by a
        version of its own on 1 July 2025. The build must say when it came
        back, not 'for good' - the page reads until=None as never."""
        doc = _unshare(_doc())
        _turn_off(_defaults_version(doc))
        _back_on(doc, "cp-carers", "2025-07-01", expected_time="11:00", grace="2h")
        [got] = turned_off.timeline("cp-carers", agreement.from_doc(doc),
                                    docs=(doc, _load("data-asset.yaml")))
        assert (got["level"], got["until"]) == ("collection", "2025-07-01")

    def test_d7_every_flipped_period_already_open_is_named(self):
        """Off after 31 March 2025, introduced 14 October 2026: every
        quarter from 2025-Q3 to 2026-Q4 had opened, and each is named. A
        quarter whose window opens after the change was introduced is not."""
        got = _findings_text(_freeze_check(_load("calendar.yaml"),
                                           lambda doc: _turn_off(_clients_version(doc))))
        for period in ("2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2", "2026-Q3", "2026-Q4"):
            assert f"cp-clients {period}," in got, period
        assert "cp-clients 2027-Q2" not in got

    def test_d9a_a_slot_still_open_is_not_called_nothing_owed(self):
        """10 April 2025: turned off, but 2025-Q2's slot is open until 17
        April - so 'Owes' must not read 'nothing', nor the timing 'when last
        on'."""
        from qa_tools.common import participation_view

        v = participation_view.view("cp-clients", date(2025, 4, 10),
                                    agreement.from_doc(_off_for_a_while()))
        labels = {x.label: x.text for x in v.values}
        assert labels.get("Owes") != "nothing - turned off"
        assert "Due time" in labels and "Due time (when last on)" not in labels

    def test_d9b_back_on_names_the_collections_turn_off(self):
        from qa_tools.common import participation_view

        doc = _unshare(_doc())
        _turn_off(_defaults_version(doc), to="2025-03-31", reason="collection paused")
        _back_on(doc, "cp-carers", "2025-07-01", expected_time="11:00", grace="2h")
        v = participation_view.view("cp-carers", date(2025, 8, 1), agreement.from_doc(doc))
        assert "31 Mar 2025" in v.turn_off[0] and "collection paused" in v.turn_off[0]
        assert "1 Jul 2025" in v.turn_off[0]

    def test_d10_a_turns_off_that_is_not_true_names_its_version_and_prints_the_fix(
            self, broken):
        def mutate(doc):
            _turn_off(_versions(doc, "cp-clients")[0], log=[
                {"date": "2026-10-13", "author": "a", "change": "off", "turns_off": True},
                {"date": "2026-10-14", "author": "a", "change": "moved", "turns_off": "yes"}])
        errors = broken(mutate)
        assert len(errors) == 1, _text(errors)
        got = _text(errors)
        assert "2023-01-01" in got
        assert "\n      turns_off: true" in got
