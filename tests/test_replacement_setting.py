"""Whether a resupply may replace an already-promoted supply automatically
(REQ-PIPE-123). The setting against configuration documents; the gate
against a real database, each test minting its own period."""
from __future__ import annotations

import copy
import uuid
from datetime import date

import pytest
import yaml

import test_supersession as _base
from qa_tools.common import (amber_setting, decision_log as dl, promotion, replacement_setting,
                             substitution, supersession)
from qa_tools.common.hierarchy import DATA_ASSET_YAML
from test_supersession import DS, REAL_PERSON, TABLE, WHEN, _filed

conn = _base.conn
period = _base.period

AG, COL = "child-protection-family-support", "child-protection"


def _doc():
    return yaml.safe_load(DATA_ASSET_YAML.read_text())


def _version(value, start="2023-01-01"):
    return {"versions": [{"effective_from": start, "value": value, "changelog": ["x"]}]}


class TestTheSettingIsReadLikeTheAmberSetting:
    """Criterion 1."""

    def test_the_asset_says_never(self):
        r = replacement_setting.resolve(DS, "2026-10-05T00:00:00+08:00")
        assert (r.value, r.level) == ("never", amber_setting.ASSET)

    def test_nearest_level_wins(self):
        doc = _doc()
        for agency in doc["hierarchy"]["agencies"]:
            for collection in agency["collections"]:
                for d in collection["datasets"]:
                    if d["id"] == DS:
                        d["replacement_setting"] = _version("green")
        r = replacement_setting.resolve(DS, "2026-10-05T00:00:00+08:00", doc=doc)
        assert (r.value, r.level) == ("green", amber_setting.DATASET)

    def test_no_asset_level_value_is_refused(self):
        doc = _doc()
        del doc["replacement_setting"]
        with pytest.raises(amber_setting.AmberSettingError, match="replacement setting"):
            replacement_setting.resolve(DS, "2026-10-05T00:00:00+08:00", doc=doc)

    def test_its_past_is_frozen(self):
        old, new = _doc(), _doc()
        new["replacement_setting"]["versions"][0]["value"] = "green"
        problems = replacement_setting.past_change_problems(
            old, new, date(2026, 10, 5), synthetic=False)
        assert problems and "altered" in problems[0][1]


class TestTheOneConflictIsRefused:
    """Criterion 11 - on any date the two overlap, not only today."""

    def test_green_or_amber_with_amber_hold(self):
        doc = _doc()
        doc["replacement_setting"] = _version("green-or-amber")
        doc["amber_setting"] = _version("hold")
        assert replacement_setting.conflicts(doc)

    def test_with_promote_and_acknowledge_it_is_consistent(self):
        doc = _doc()
        doc["replacement_setting"] = _version("green-or-amber")
        doc["amber_setting"] = _version("promote-and-acknowledge")
        assert replacement_setting.conflicts(doc) == []

    def test_an_overlap_in_the_past_alone_is_still_refused(self):
        doc = _doc()
        doc["replacement_setting"] = _version("green-or-amber")
        doc["amber_setting"] = {"versions": [
            {"effective_from": "2023-01-01", "value": "hold", "changelog": ["x"]},
            {"effective_from": "2024-01-01", "value": "promote", "changelog": ["x"]}]}
        assert replacement_setting.conflicts(doc)

    def test_the_real_configuration_has_none(self):
        assert replacement_setting.conflicts(_doc()) == []


def _green():
    return [{"dataset_id": DS, "check_id": "pytest-check", "status": "pass"}]


def _amber():
    return [{"dataset_id": DS, "check_id": "pytest-check", "status": "warn"}]


def _run(conn, supply, table, period, results, *, contested=False):
    return promotion.after_run(
        conn, agency_id=AG, collection_id=COL,
        supplies=[{"dataset_id": DS, "supply": supply, "period": period,
                   "physical_tables": [table], "contested": contested}],
        results=results, reads={}, actor=promotion.RULE_ACTOR, actor_kind=dl.RULE,
        effective_at=WHEN)


def _setting(monkeypatch, value):
    resolved = amber_setting.Resolved(value=value, level=amber_setting.ASSET,
                                      version="2023-01-01")
    monkeypatch.setattr(replacement_setting, "resolve", lambda *a, **k: resolved)


def _promoted(conn, period, *, kind=dl.RULE):
    a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
    promotion.promote(conn, agency_id=AG, collection_id=COL, dataset_id=DS, supply=a,
                      period=period, physical_tables=[a_table],
                      actor="promotion rule" if kind == dl.RULE else REAL_PERSON,
                      actor_kind=kind, effective_at=WHEN, reason="first", status="green")
    return a


class TestTheGate:
    """Criteria 2 to 5 and 8 to 10."""

    def test_never_leaves_it_waiting(self, conn, period, monkeypatch):
        _setting(monkeypatch, "never")
        a = _promoted(conn, period)
        b, b_table = _filed(conn, period, "2026-06-01T01:00:00+00:00")
        out = _run(conn, b, b_table, period, _green())
        assert out.refused.get(DS) and "already filled" in out.refused[DS]
        assert dl.promoted_into(conn, DS, period) == a

    def test_green_replaces_and_the_replaced_one_is_superseded(self, conn, period, monkeypatch):
        _setting(monkeypatch, "green")
        a = _promoted(conn, period)
        b, b_table = _filed(conn, period, "2026-06-01T01:00:00+00:00")
        out = _run(conn, b, b_table, period, _green())
        assert DS in out.promoted
        assert dl.promoted_into(conn, DS, period) == b
        assert supersession.is_superseded(conn, DS, a)
        (row,) = conn.execute(
            f"SELECT actor_kind, replaces, replacement_setting, replacement_level, "
            f"replacement_version, reason FROM {dl.TABLE} WHERE dataset_id = ? AND supply = ? "
            "AND action = 'promote'", [DS, b]).fetchall()
        assert row[:5] == (dl.RULE, a, "green", amber_setting.ASSET, "2023-01-01")
        assert "replacement setting 'green'" in row[5]

    def test_green_does_not_replace_with_amber(self, conn, period, monkeypatch):
        _setting(monkeypatch, "green")
        a = _promoted(conn, period)
        b, b_table = _filed(conn, period, "2026-06-01T01:00:00+00:00")
        _run(conn, b, b_table, period, _amber())
        assert dl.promoted_into(conn, DS, period) == a

    def test_a_person_promoted_supply_is_replaced_too(self, conn, period, monkeypatch):
        _setting(monkeypatch, "green")
        a = _promoted(conn, period, kind=dl.PERSON)
        b, b_table = _filed(conn, period, "2026-06-01T01:00:00+00:00")
        _run(conn, b, b_table, period, _green())
        assert dl.promoted_into(conn, DS, period) == b
        assert supersession.is_superseded(conn, DS, a)

    def test_not_while_a_later_period_stands_on_it_and_why_is_recorded(
            self, conn, period, monkeypatch):
        _setting(monkeypatch, "green")
        a = _promoted(conn, period)
        later = f"2099-L{uuid.uuid4().hex[:6]}"
        substitution.substitute(conn, agency_id=AG, collection_id=COL, dataset_id=DS,
                                logical_table=TABLE, period=later, stands_on=period,
                                supply=a, actor=REAL_PERSON, reason="late", effective_at=WHEN)
        b, b_table = _filed(conn, period, "2026-06-01T01:00:00+00:00")
        out = _run(conn, b, b_table, period, _green())
        assert dl.promoted_into(conn, DS, period) == a
        assert later in out.refused[DS]
        assert conn.execute(
            f"SELECT 1 FROM {dl.TABLE} WHERE dataset_id = ? AND supply = ? AND action = ?",
            [DS, b, dl.PROMOTION_WITHHELD]).fetchall()

    def test_a_substituted_slot_is_never_replaced(self, conn, period, monkeypatch):
        _setting(monkeypatch, "green")
        a = _promoted(conn, period)
        later = f"2099-L{uuid.uuid4().hex[:6]}"
        substitution.substitute(conn, agency_id=AG, collection_id=COL, dataset_id=DS,
                                logical_table=TABLE, period=later, stands_on=period,
                                supply=a, actor=REAL_PERSON, reason="late", effective_at=WHEN)
        b, b_table = _filed(conn, later, "2026-06-01T01:00:00+00:00")
        _run(conn, b, b_table, later, _green())
        assert dl.held(conn, DS, later).held_as == dl.SUBSTITUTED

    def test_every_other_refusal_comes_first(self, conn, period, monkeypatch):
        _setting(monkeypatch, "green")
        a = _promoted(conn, period)
        b, b_table = _filed(conn, period, "2026-06-01T01:00:00+00:00")
        out = _run(conn, b, b_table, period, _green(), contested=True)
        assert "several files claim" in out.refused[DS]
        assert dl.promoted_into(conn, DS, period) == a


class TestTheRequirementsItAmends:
    """Criterion 12: REQ-PIPE-075 criterion 4 and REQ-PIPE-065 criterion 9
    say a filled slot blocks automatic promotion EXCEPT under this setting."""

    def test_both_name_the_exception(self):
        from pathlib import Path

        reqs = {r["id"]: r for r in yaml.safe_load(
            (Path(__file__).resolve().parent.parent / "requirements.yaml").read_text()
        )["requirements"]}
        assert "REQ-PIPE-123" in reqs["REQ-PIPE-075"]["acceptance_criteria"][3]
        assert "REQ-PIPE-123" in reqs["REQ-PIPE-065"]["acceptance_criteria"][8]


def test_the_shipped_document_is_unchanged_by_these_tests():
    """The tests above edit copies; the real file is read fresh each time."""
    assert copy.deepcopy(_doc()) == _doc()
