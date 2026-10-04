"""REQ-PIPE-122: one amber setting, three values, nearest level wins,
effective-dated, frozen in the past; the gate honours it, records it, and a
person acknowledges what promote-and-acknowledge asks for.

The decision-log tests act on a REAL dataset (its table and agency are
real) and a period minted per test, because qa.decision is append-only and
shared by every module on a worker.
"""
from __future__ import annotations

import copy
import uuid
from datetime import date

import pytest
import yaml

from qa_tools.common import (amber_setting, decision_log as dl, filing_decisions as fd,
                             filing_queue, hierarchy, people, promotion, qa_store,
                             slot_state, supply_db)
from qa_tools.common.schemas import AMBER_SETTINGS, DataAsset

REAL_PERSON = "fpycnkgvmt@privaterelay.appleid.com"
WHEN = "2026-09-29T09:00:00+08:00"


def _version(start, value):
    return {"effective_from": start, "value": value, "changelog": [f"{start}: {value}"]}


def _doc(asset=("2023-01-01", "promote"), collection=None, dataset=None):
    doc = yaml.safe_load(hierarchy.DATA_ASSET_YAML.read_text())
    doc["amber_setting"] = {"versions": [_version(*asset)]} if asset else None
    if doc["amber_setting"] is None:
        del doc["amber_setting"]
    col = doc["hierarchy"]["agencies"][1]["collections"][0]
    if collection:
        col["amber_setting"] = {"versions": [_version(*v) for v in collection]}
    if dataset:
        ds = next(d for d in col["datasets"] if d["id"] == "cp-clients")
        ds["amber_setting"] = {"versions": [_version(*v) for v in dataset]}
    return doc


class TestTheValues:
    """Criteria 1 and 2."""

    def test_three_values_strictest_first(self):
        assert AMBER_SETTINGS == ("hold", "promote-and-acknowledge", "promote")

    def test_the_asset_file_lists_them_in_that_order(self):
        text = hierarchy.DATA_ASSET_YAML.read_text()
        positions = [text.index(f"#   {v} ") for v in AMBER_SETTINGS]
        assert positions == sorted(positions)

    def test_an_unknown_value_is_refused(self):
        doc = _doc(asset=("2023-01-01", "maybe"))
        with pytest.raises(Exception, match="hold"):
            DataAsset.model_validate(doc)

    def test_no_asset_level_value_is_refused_not_defaulted(self):
        """Criterion 9."""
        with pytest.raises(Exception, match="amber_setting"):
            DataAsset.model_validate(_doc(asset=None))

    def test_an_agency_is_not_a_level(self):
        """Criterion 20."""
        doc = _doc()
        doc["hierarchy"]["agencies"][0]["amber_setting"] = {"versions": [_version("2023-01-01", "hold")]}
        with pytest.raises(Exception, match="amber_setting"):
            DataAsset.model_validate(doc)

    def test_the_real_configuration_is_valid(self):
        DataAsset.model_validate(yaml.safe_load(hierarchy.DATA_ASSET_YAML.read_text()))


class TestResolving:
    """Criteria 3 and 4."""

    def test_the_asset_answers_when_nothing_nearer_does(self):
        got = amber_setting.resolve("cp-clients", WHEN, doc=_doc())
        assert (got.value, got.level) == ("promote", amber_setting.ASSET)

    def test_the_nearest_level_wins(self):
        doc = _doc(collection=[("2023-01-01", "hold")],
                   dataset=[("2023-01-01", "promote-and-acknowledge")])
        assert amber_setting.resolve("cp-clients", WHEN, doc=doc).level == amber_setting.DATASET
        assert amber_setting.resolve("cp-carers", WHEN, doc=doc).value == "hold"

    def test_the_version_in_effect_at_the_decisions_instant(self):
        doc = _doc(collection=[("2023-01-01", "promote"), ("2026-06-01", "hold")])
        assert amber_setting.resolve("cp-carers", "2026-05-31T12:00:00+08:00", doc=doc).value == "promote"
        got = amber_setting.resolve("cp-carers", "2026-06-01T00:30:00+08:00", doc=doc)
        assert (got.value, got.version) == ("hold", "2026-06-01")

    def test_a_level_with_only_future_versions_falls_through(self):
        doc = _doc(dataset=[("2030-01-01", "hold")])
        assert amber_setting.resolve("cp-clients", WHEN, doc=doc).level == amber_setting.ASSET

    def test_no_value_in_effect_is_an_error_not_a_default(self):
        doc = _doc(asset=("2030-01-01", "promote"))
        with pytest.raises(amber_setting.AmberSettingError, match="no default"):
            amber_setting.resolve("cp-clients", WHEN, doc=doc)


class TestThePastIsFrozen:
    """Criteria 6, 7 and 8."""

    TODAY = date(2026, 10, 5)

    def _check(self, old, new, synthetic=False):
        return amber_setting.past_change_problems(old, new, self.TODAY, synthetic=synthetic)

    def test_altering_a_past_version_is_refused_whatever_its_changelog(self):
        old = _doc()
        new = copy.deepcopy(old)
        new["amber_setting"]["versions"][0]["value"] = "hold"
        new["amber_setting"]["versions"][0]["changelog"].append("corrected")
        assert self._check(old, new)

    def test_removing_a_past_version_is_refused(self):
        old = _doc(collection=[("2024-01-01", "hold")])
        new = _doc()
        assert any("removed" in p for _, p in self._check(old, new))

    def test_a_new_version_dated_before_today_is_refused(self):
        old = _doc()
        new = copy.deepcopy(old)
        new["amber_setting"]["versions"].append(_version("2026-10-01", "hold"))
        assert any("before today" in p for _, p in self._check(old, new))

    def test_a_synthetic_asset_may_author_the_past_but_not_rewrite_it(self):
        old = _doc()
        added = copy.deepcopy(old)
        added["amber_setting"]["versions"].append(_version("2025-01-01", "hold"))
        assert self._check(old, added, synthetic=True) == []
        altered = copy.deepcopy(old)
        altered["amber_setting"]["versions"][0]["value"] = "hold"
        assert self._check(old, altered, synthetic=True)

    def test_today_and_the_future_are_fine(self):
        old = _doc()
        new = copy.deepcopy(old)
        new["amber_setting"]["versions"].append(_version("2026-10-05", "hold"))
        new["amber_setting"]["versions"].append(_version("2027-01-01", "promote"))
        assert self._check(old, new) == []


class TestTheGate:
    """Criteria 10 to 12 and 18, on the pure gate."""

    def _gate(self, setting, status="amber"):
        return promotion.should_promote(status=status, slot_filled=False,
                                        held_without_slot=False, has_active_checks=True,
                                        amber_setting=setting)

    def test_hold_never_promotes_amber_and_never_says_held(self):
        ok, why = self._gate("hold")
        assert not ok and "amber, waiting for a person" in why
        assert "held" not in why.replace("hold", "")

    def test_the_other_two_promote(self):
        assert self._gate("promote-and-acknowledge")[0]
        assert self._gate("promote")[0]

    def test_green_is_untouched_by_hold(self):
        assert self._gate("hold", status="green")[0]


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-amber-setting") as c:
        qa_store.ensure_schema(c)
        yield c


def _staged(conn, table="cp_carers"):
    arrival = uuid.uuid4().hex[:10]
    physical = f"{table}__{arrival}"
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')
    conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" (id integer)')
    return f"cp-carers@{arrival}", physical


def _period():
    return f"2099-A{uuid.uuid4().hex[:6]}"


def _promote(conn, setting, period):
    supply, physical = _staged(conn)
    amber = amber_setting.Resolved(setting, amber_setting.COLLECTION, "2023-01-01")
    promotion.promote(conn, agency_id="child-protection-family-support",
                      collection_id="child-protection", dataset_id="cp-carers",
                      supply=supply, period=period, physical_tables=[physical],
                      actor=promotion.RULE_ACTOR, actor_kind=dl.RULE, effective_at=WHEN,
                      reason=promotion.AUTOMATIC_REASON, amber=amber)
    return supply


def _ack(conn, supply, period, reason="looked at the drift; within the supplier's note"):
    request = fd.Request(operation=fd.ACKNOWLEDGE, dataset_id="cp-carers",
                         actor=people.person_by_email(REAL_PERSON), reason=reason,
                         period=period, supply=supply)
    return fd.apply(request, effective_at=WHEN, conn=conn)


class TestRecordedOnTheDecision:
    """Criteria 5, 11 and 19."""

    def test_an_amber_promotion_records_value_level_and_version(self, conn):
        period = _period()
        supply = _promote(conn, "promote-and-acknowledge", period)
        row = conn.execute(
            f"SELECT amber_setting, amber_level, amber_version, acknowledgement_owed "
            f"FROM {dl.TABLE} WHERE supply = ? AND action = 'promote'", [supply]).fetchall()[0]
        assert row == ("promote-and-acknowledge", "collection", "2023-01-01", True)

    def test_promote_owes_nothing(self, conn):
        period = _period()
        supply = _promote(conn, "promote", period)
        assert conn.execute(f"SELECT acknowledgement_owed FROM {dl.TABLE} WHERE supply = ? "
                            "AND action = 'promote'", [supply]).fetchall()[0][0] is False


class TestAcknowledging:
    """Criteria 13 to 16."""

    def test_an_owed_acknowledgement_is_recorded_and_changes_nothing(self, conn):
        from qa_tools.common import acknowledgement

        period = _period()
        supply = _promote(conn, "promote-and-acknowledge", period)
        before = dl.held(conn, "cp-carers", period)
        assert acknowledgement.owed(conn, "cp-carers", period) == supply
        outcome = _ack(conn, supply, period)
        assert outcome.changed
        assert acknowledgement.owed(conn, "cp-carers", period) is None
        after = dl.held(conn, "cp-carers", period)
        assert (after.holder, after.held_as, after.decision_id) == (
            before.holder, before.held_as, before.decision_id)

    @pytest.mark.parametrize("setting", ["promote"])
    def test_one_not_owed_is_refused_with_why(self, conn, setting):
        period = _period()
        supply = _promote(conn, setting, period)
        with pytest.raises(dl.DecisionRefused, match="asks for none"):
            _ack(conn, supply, period)

    def test_twice_is_refused(self, conn):
        period = _period()
        supply = _promote(conn, "promote-and-acknowledge", period)
        _ack(conn, supply, period)
        with pytest.raises(dl.DecisionRefused, match="already acknowledged"):
            _ack(conn, supply, period)

    def test_a_supply_not_promoted_is_refused(self, conn):
        supply, _ = _staged(conn)
        with pytest.raises(dl.DecisionRefused, match="not the supply promoted"):
            _ack(conn, supply, _period())

    def test_no_reason_is_refused(self, conn):
        period = _period()
        supply = _promote(conn, "promote-and-acknowledge", period)
        with pytest.raises(dl.DecisionRefused, match="reason"):
            _ack(conn, supply, period, reason="")

    def test_it_lapses_when_the_supply_leaves_its_period(self, conn):
        from qa_tools.common import acknowledgement, rejection

        period = _period()
        supply = _promote(conn, "promote-and-acknowledge", period)
        physical = f"cp_carers__{supply.split('@')[1]}"
        rejection.demote(conn, agency_id="child-protection-family-support",
                         collection_id="child-protection", dataset_id="cp-carers",
                         supply=supply, from_slot=period, physical_tables=[physical],
                         actor=REAL_PERSON, reason="taking it back out", effective_at=WHEN)
        assert acknowledgement.owed(conn, "cp-carers", period) is None
        with pytest.raises(dl.DecisionRefused, match="not the supply promoted"):
            _ack(conn, supply, period)


class TestShownApart:
    """Criteria 17 and 18: the queue offers acknowledge, and each waiting
    state is its own, never called held."""

    def test_the_two_new_states_need_a_person_and_are_in_the_queue(self):
        for state in (slot_state.AMBER_WAITING, slot_state.AWAITING_ACKNOWLEDGEMENT):
            assert state in slot_state.NEEDS_ACTION
            assert state in filing_queue.WITH_A_SUPPLY
            assert state != slot_state.HELD and "held" not in state

    def test_acknowledge_is_offered_on_a_promotion_owing_one(self):
        state = slot_state.SlotState(dataset_id="d", period="p", supply="d@k",
                                     state=slot_state.AWAITING_ACKNOWLEDGEMENT)
        supply_scoped, _ = filing_queue.operations_for(state)
        assert supply_scoped[0] == fd.ACKNOWLEDGE

    def test_the_withheld_note_under_hold_reads_as_amber_waiting(self, conn):
        supply, _ = _staged(conn)
        period = _period()
        amber = amber_setting.Resolved("hold", amber_setting.ASSET, "2023-01-01")
        promotion._record_amber_waiting(
            conn, agency_id="child-protection-family-support", collection_id="child-protection",
            dataset_id="cp-carers", supply=supply, period=period, amber=amber, effective_at=WHEN)
        promotion._record_amber_waiting(
            conn, agency_id="child-protection-family-support", collection_id="child-protection",
            dataset_id="cp-carers", supply=supply, period=period, amber=amber, effective_at=WHEN)
        rows = conn.execute(f"SELECT amber_setting, amber_level FROM {dl.TABLE} "
                            "WHERE supply = ? AND action = ?",
                            [supply, dl.PROMOTION_WITHHELD]).fetchall()
        assert rows == [("hold", "data asset")], "recorded once, with what it acted under"
        assert slot_state._amber_waiting(conn, "cp-carers", supply)


class TestAmberWaitingAfterAnEmptiedSlot:
    """delivery-critic on REQ-PIPE-122, F1 (2026-10-05): an amber supply
    waiting under hold read AWAITING_DECISION - the red supply's state -
    where an earlier decision had emptied its slot, because only the
    no-decision branch of state_of asked for the hold."""

    def test_it_still_reads_amber_waiting(self, conn):
        from datetime import datetime, timedelta, timezone

        from qa_tools.common import slots

        period = "2024-Q2"
        rejected, _ = _staged(conn)
        with dl.apply_decision(conn, dl.Decision(
                agency_id="a", collection_id="c", dataset_id="cp-carers", action=dl.REJECT,
                supply=rejected, actor=REAL_PERSON, actor_kind=dl.PERSON, effective_at=WHEN,
                from_slot=period, reason="bad file")):
            pass
        amber_one, _ = _staged(conn)
        promotion._record_amber_waiting(
            conn, agency_id="child-protection-family-support", collection_id="child-protection",
            dataset_id="cp-carers", supply=amber_one, period=period,
            amber=amber_setting.Resolved("hold", amber_setting.ASSET, "2023-01-01"),
            effective_at=WHEN)
        at = datetime(2027, 12, 1, tzinfo=timezone(timedelta(hours=8)))
        slot = next(s for s in slots.slots_for_dataset("cp-carers", until=at.date())
                    if s.name == period)
        got = slot_state.state_of(conn, dataset_id="cp-carers", slot=slot, now=at,
                                  filings={period: {"supply_id": amber_one}},
                                  ever_delivered=True)
        assert got.state == slot_state.AMBER_WAITING


class TestTheConfigurationAsItStands:
    """delivery-critic on REQ-PIPE-122, F4 and F5."""

    TODAY = date(2026, 10, 5)

    def test_an_asset_level_with_only_future_versions_is_refused(self):
        doc = _doc(asset=("2030-01-01", "promote"))
        assert any("in effect today" in p
                   for _, p in amber_setting.standing_problems(doc, self.TODAY))

    def test_two_versions_sharing_a_date_are_refused(self):
        doc = _doc(collection=[("2027-01-01", "hold"), ("2027-01-01", "promote")])
        assert any("share the date" in p
                   for _, p in amber_setting.standing_problems(doc, self.TODAY))

    def test_the_real_configuration_has_no_standing_problem(self):
        doc = yaml.safe_load(hierarchy.DATA_ASSET_YAML.read_text())
        assert amber_setting.standing_problems(doc, self.TODAY) == []


class TestRefusalsNameTheNextCommand:
    """CLI UX critic on REQ-PIPE-122 (#107): the case a lead is likeliest to
    hit - acknowledging an amber supply waiting under hold - names promote."""

    def test_acknowledging_a_supply_under_hold_points_at_promote(self, conn):
        supply, _ = _staged(conn)
        period = _period()
        promotion._record_amber_waiting(
            conn, agency_id="child-protection-family-support", collection_id="child-protection",
            dataset_id="cp-carers", supply=supply, period=period,
            amber=amber_setting.Resolved("hold", amber_setting.ASSET, "2023-01-01"),
            effective_at=WHEN)
        with pytest.raises(dl.DecisionRefused, match="--operation promote"):
            _ack(conn, supply, period)
