"""Synthetic history can play back scripted person decisions, through the
same decision path a person uses (REQ-GEN-135)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import test_supersession as _base
from qa_tools.common import decision_log as dl, people, scenario_map, scripted_decisions as sd
from qa_tools.common import validate_people
from test_supersession import DS, _filed

conn = _base.conn
period = _base.period

ROOT = Path(__file__).resolve().parent.parent
SYNTHETIC = "scripted-history@synthetic.invalid"


def _script(**kw):
    base = dict(scenario="TS-1", operation="promote", dataset_id=DS, reason="scripted",
                supply_index=0, after_hours=2)
    base.update(kw)
    return sd.Script(**base)


class TestTheScriptIsValidatedAgainstConfiguration:
    """Criterion 13."""

    def test_a_good_script_has_no_problems(self):
        assert sd.problems([_script()], registered={"TS-1"}) == []

    def test_each_kind_of_problem_is_named(self):
        found = sd.problems([_script(scenario="TS-NOPE", operation="bless", reason=" ",
                                     dataset_id="no-such")], registered={"TS-1"})
        assert len(found) == 4
        assert any("not in the register" in f for f in found)
        assert any("not a filing decision" in f for f in found)
        assert any("needs a reason" in f for f in found)
        assert any("no dataset" in f for f in found)

    def test_the_committed_script_holds(self):
        from qa_tools.common import scenarios

        registered = {s.id for s in scenarios.parse_register()}
        assert sd.problems(sd.load(), registered=registered) == []


class TestTheSyntheticActor:
    """Criteria 9, 10 and 11."""

    def test_it_is_in_people_and_refused_outside_playback(self):
        with pytest.raises(people.UnknownActor, match="played back"):
            people.person_by_email(SYNTHETIC)

    def test_inside_playback_it_acts(self):
        with people.playback():
            assert people.synthetic_actor()["email"] == SYNTHETIC

    def test_it_has_no_github_route(self):
        with pytest.raises(people.UnknownActor):
            people.person_by_github("")

    def test_the_gate_refuses_a_synthetic_entry_with_github_or_assignment(self, tmp_path):
        bad = tmp_path / "people.yaml"
        bad.write_text(
            "people:\n"
            "  - {email: s@x.invalid, name: S, roles: [qa], synthetic: true, github: s,"
            " placeholder: true}\n"
            "assignments:\n"
            "  - {agency: a, person: s@x.invalid, role: qa}\n")
        found = validate_people.problems(bad)
        assert any("GitHub username" in f for f in found)
        assert any("never assigned" in f for f in found)
        assert any("one or the other" in f for f in found)

    def test_the_real_file_passes(self):
        assert validate_people.problems() == []


class TestPlayback:
    """Criteria 2 to 6 and 8, against a real database."""

    def _player(self, scripts, supply_table):
        placements = {"TS-1": scenario_map.Placement(
            scenario_id="TS-1", dataset=DS, supplies=(supply_table,), period="p",
            in_place_on="2026-05-01")}
        return sd.Player("child-protection", scripts=scripts, placements=placements)

    def test_it_raises_a_persons_decision_at_its_instant_before_a_later_arrival(
            self, conn, period):
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        player = self._player([_script(after_hours=3)], a_table)
        later = SimpleNamespace(received_at=datetime.fromisoformat("2026-05-02T00:00:00+00:00"))
        assert player.before(later) == 1
        row = conn.execute(
            f"SELECT actor, actor_kind, reason, effective_at FROM {dl.TABLE} "
            "WHERE supply = ? AND action = 'promote'", [a]).fetchall()[0]
        assert row[:3] == (SYNTHETIC, dl.PERSON, "scripted")
        assert row[3] == datetime.fromisoformat("2026-05-01T01:00:00+00:00") + timedelta(hours=3)

    def test_it_waits_for_an_arrival_received_after_it(self, conn, period):
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        player = self._player([_script(after_hours=3)], a_table)
        sooner = SimpleNamespace(received_at=datetime.fromisoformat("2026-05-01T02:00:00+00:00"))
        assert player.before(sooner) == 0
        assert player.finish() == 1

    def test_a_refusal_stops_the_replay_naming_the_scenario(self, conn, period):
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        player = self._player([_script(operation="demote")], a_table)
        with pytest.raises(sd.ScriptRefused, match="TS-1"):
            player.finish()

    def test_never_on_an_asset_that_is_not_synthetic(self, monkeypatch, tmp_path):
        asset = tmp_path / "data-asset.yaml"
        asset.write_text("synthetic: false\n")
        monkeypatch.setattr("qa_tools.common.hierarchy.DATA_ASSET_YAML", asset)
        with pytest.raises(sd.ScriptRefused, match="synthetic"):
            sd.Player("child-protection", scripts=[_script()], placements={})


class TestNoBackDoor:
    """NFR 3: the decision log has one writer, so playback cannot have
    another."""

    def test_only_decision_log_inserts_into_the_decision_table(self):
        pattern = re.compile(r"INSERT INTO \{(?:decision_log|dl)\.TABLE\}|INSERT INTO[^\n]*\.decision\b")
        offenders = []
        for top in ("qa_tools", "pipeline", "cli", "generator", "dashboard"):
            for path in (ROOT / top).rglob("*.py"):
                if path.name in ("decision_log.py", "qa_store.py"):
                    continue
                if pattern.search(path.read_text()):
                    offenders.append(str(path.relative_to(ROOT)))
        assert offenders == []


class TestASupplyNotYetFiled:
    """Found by the first replay (2026-10-05): before its supply arrived, a
    script had no receipt instant and the player crashed with a TypeError
    on the very first arrival, taking the whole replay down."""

    def test_it_waits_and_only_the_end_of_the_replay_refuses(self, conn):
        placements = {"TS-1": scenario_map.Placement(
            scenario_id="TS-1", dataset=DS, supplies=("cp_carers__999999999999999999",),
            period="p", in_place_on="2026-05-01")}
        player = sd.Player("child-protection", scripts=[_script()], placements=placements)
        early = SimpleNamespace(received_at=datetime.fromisoformat("2026-05-02T00:00:00+00:00"))
        assert player.before(early) == 0
        with pytest.raises(sd.ScriptRefused, match="TS-1"):
            player.finish()
