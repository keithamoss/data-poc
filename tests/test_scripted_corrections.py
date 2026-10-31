"""Scripted correction confirmations (REQ-GEN-205 criteria 4-7): a top-level
`corrections:` list in contract/scripted_decisions.yaml says how the asset
manager confirms a declared correction during a replay - keeping named
supplies, with one reason, or leaving it pending - read only by
correction_replay.confirm_due. Written first and seen to fail.
"""
from __future__ import annotations

from datetime import timedelta, timezone

import pytest

from qa_tools.common import (correction_apply, correction_replay, decision_log, scenario_map,
                             scripted_corrections, scripted_decisions)
import test_correction_replay as _replay

#: The replay tests' fixtures: CAB-1 and CAB-2 declared, one supply filed.
two, conn = _replay.two, _replay.conn

PERTH = timezone(timedelta(hours=8))
SC = scripted_corrections.Confirmation
KEEP = scripted_corrections.Keep


def _write(tmp_path, body: str):
    path = tmp_path / "scripted_decisions.yaml"
    path.write_text(body)
    return path


class TestTheFileDeclaresThem:
    def test_a_corrections_list_is_read_beside_the_decisions(self, tmp_path):
        path = _write(tmp_path, """
decisions: []
corrections:
  - change_reference: CAB-1
    keep: [{scenario: TS-59, dataset: ed-presentations, supply: 0}]
    keep_reason: "It belongs where it was filed."
  - change_reference: CAB-2
    pending: true
""")
        got = scripted_corrections.load(path)
        assert got == [SC("CAB-1", keep=(KEEP("TS-59", "ed-presentations", 0),),
                          keep_reason="It belongs where it was filed."),
                       SC("CAB-2", pending=True)]
        assert scripted_decisions.load(path) == [], "the Player never sees a confirmation"

    def test_the_file_header_describes_the_entry(self):
        head = scripted_decisions.SCRIPT_PATH.read_text().split("\ndecisions:")[0]
        assert "corrections:" in head and "keep_reason" in head and "pending" in head


class _Inj:
    def __init__(self, sid, dataset, n=1):
        self.scenario_id, self.dataset_id, self.also_demonstrates = sid, dataset, ()
        self.arrivals = tuple(range(n))


INJ = [_Inj("TS-59", "ed-presentations"), _Inj("TS-1", "cp-clients", n=3)]


def _problems(*confs, declared=frozenset({"CAB-1", "CAB-2"})):
    return scripted_corrections.problems(list(confs), declared=set(declared), injections=INJ)


def _keep(sid="TS-59", ds="ed-presentations", n=0):
    return (KEEP(sid, ds, n),)


class TestValidationRefusesEachFault:
    """Criterion 5: each refusal names the entry and the fault."""

    def test_a_good_entry_passes(self):
        assert _problems(SC("CAB-1", keep=_keep(), keep_reason="why"),
                         SC("CAB-2", pending=True)) == []

    @pytest.mark.parametrize("conf, fault", [
        (SC("CAB-9", pending=True), "not a declared correction"),
        (SC("CAB-1", keep=_keep(sid="TS-404"), keep_reason="w"), "not placed by the generator"),
        (SC("CAB-1", keep=_keep(sid="TS-1", ds="cp-clients", n=3), keep_reason="w"),
         "indexed 0 to 2"),
        (SC("CAB-1", keep=_keep(ds="cp-clients"), keep_reason="w"), "does not carry"),
        (SC("CAB-1", keep=_keep()), "no `keep_reason:`"),
        (SC("CAB-1", keep_reason="w"), "keeps nothing"),
        (SC("CAB-1", keep=_keep(), keep_reason="w", pending=True), "both `pending: true`"),
        (SC("CAB-1"), "says nothing the default does not"),
        (SC("CAB-2", pending=True, timing=("after_hours",)), "`after_hours:` means nothing"),
    ])
    def test_it_refuses(self, conf, fault):
        found = _problems(conf)
        assert any(fault in p and f"correction 1 ({conf.change_reference})" in p
                   for p in found), found

    def test_a_reference_named_twice_is_refused(self):
        found = _problems(SC("CAB-2", pending=True), SC("CAB-2", pending=True))
        assert any("correction 1 already names 'CAB-2'" in p for p in found), found

    def test_the_committed_file_passes(self):
        from qa_tools.common import correction_trial

        declared = {p.reference for p in correction_apply._declared(*correction_trial.working())}
        from generator import scenario_injection

        assert scripted_corrections.problems(scripted_corrections.load(), declared=declared,
                                             injections=scenario_injection.INJECTIONS) == []


def _say():
    lines: list[str] = []
    return lines, lines.append


@pytest.fixture
def placed(monkeypatch):
    """TS-X's supply 0 is the fixture's replay-s."""
    monkeypatch.setattr(scenario_map, "read_placements", lambda *a, **k: {
        "TS-X": scenario_map.Placement(scenario_id="TS-X", dataset="cp-clients",
                                       supplies=("replay-s",), period="2023-Q3",
                                       in_place_on="2023-08-01")})
    monkeypatch.setattr(scripted_decisions, "_supply_of", lambda d, r: r)


class TestTheReplayConfirmsAsScripted:
    """Criteria 6 and 7, through confirm_due against a real decision log."""

    def test_a_scripted_keep_is_recorded_as_keep_with_the_reason(self, two, conn, placed):
        script = [SC("CAB-1", keep=(KEEP("TS-X", "cp-clients", 0),),
                     keep_reason="The supplier says it is Q3's.")]
        done = correction_replay.confirm_due(conn, effective_at="2026-10-11T00:00:00+08:00",
                                             say=lambda _m: None, scripts=script)
        assert "CAB-1" in done
        rows = conn.execute(f"SELECT action, supply, reason FROM {decision_log.TABLE} "
                            "WHERE supply = 'replay-s' AND action = ?",
                            [decision_log.KEEP]).fetchall()
        assert rows and "CAB-1" in rows[0][2] and "The supplier says it is Q3's." in rows[0][2]
        from qa_tools.common import filing

        assert filing.filing_for("cp-clients", "replay-s")["slot"] == "2023-Q4"

    def test_a_correction_scripted_pending_stays_pending(self, two, conn, placed):
        lines, say = _say()
        done = correction_replay.confirm_due(conn, effective_at="2026-10-11T00:00:00+08:00",
                                             say=say, scripts=[SC("CAB-2", pending=True)])
        assert done == ["CAB-1"]
        assert [p.reference for p in correction_apply.pending(conn)] == ["CAB-2"]
        assert any("CAB-2" in line and "pending" in line for line in lines)

    def test_a_correction_with_no_script_is_confirmed_as_before(self, two, conn, placed):
        from qa_tools.common import filing

        correction_replay.confirm_due(conn, effective_at="2026-10-11T00:00:00+08:00",
                                      say=lambda _m: None, scripts=[])
        assert filing.filing_for("cp-clients", "replay-s")["slot"] != "2023-Q4"

    def test_a_keep_of_a_supply_not_proposed_stops_the_replay_naming_it(
            self, two, conn, placed, monkeypatch):
        monkeypatch.setattr(scenario_map, "read_placements", lambda *a, **k: {
            "TS-X": scenario_map.Placement(scenario_id="TS-X", dataset="cp-clients",
                                           supplies=("replay-s",), period="2023-Q3",
                                           in_place_on="2023-08-01"),
            "TS-Y": scenario_map.Placement(scenario_id="TS-Y", dataset="cp-clients",
                                           supplies=("never-filed",), period="2023-Q4",
                                           in_place_on="2023-11-01")})
        script = [SC("CAB-1", keep=(KEEP("TS-Y", "cp-clients", 0),), keep_reason="w")]
        with pytest.raises(scripted_decisions.ScriptRefused) as e:
            correction_replay.confirm_due(conn, effective_at="2026-10-11T00:00:00+08:00",
                                          say=lambda _m: None, scripts=script)
        msg = str(e.value)
        assert "TS-Y" in msg and "CAB-1" in msg
        assert "TS-X cp-clients supply 0" in msg, "the proposed moves, by scenario"
        assert [p.reference for p in correction_apply.pending(conn)][0] == "CAB-1", \
            "never confirmed without the keep"


class TestTheBootstrapRunsWhatTheConfirmationsOwe:
    """Criterion 8: every run the confirmations owe, through
    recheck.run_all_owed, under the replay clock, said before it starts, and
    a run that does not complete stops the bootstrap naming it."""

    @pytest.fixture
    def owing(self, monkeypatch):
        from qa_tools.common import bootstrap, recheck, replay_clock

        calls: dict = {"rebuilt": []}
        monkeypatch.setattr(correction_replay, "confirm_due", lambda **k: ["CAB-1"])
        monkeypatch.setattr(correction_replay, "history_end", lambda conn: None)
        def one(kind):
            return recheck.Owed(**{c: (kind if c == "kind" else None)
                                   for c in recheck._OWED_COLUMNS})
        monkeypatch.setattr(recheck, "owed", lambda conn, dataset_id=None: [
            one(recheck.RECHECK), one(recheck.REEVALUATE)])

        def run_all(**kwargs):
            calls["kinds"] = kwargs.get("kinds")
            calls["clock"] = replay_clock.active()
            return calls.get("outcomes", [recheck.Outcome(1, "cp_run_001", True, "ok")])
        monkeypatch.setattr(recheck, "run_all_owed", run_all)
        monkeypatch.setattr(bootstrap, "_rebuild_results", calls["rebuilt"].append)
        return calls

    def test_the_owed_runs_are_run_and_announced(self, owing, supply_dsn):
        from qa_tools.common import bootstrap, recheck

        lines, say = _say()
        bootstrap._confirm_corrections(say)
        assert set(owing["kinds"]) == {recheck.RECHECK, recheck.REEVALUATE}
        assert owing["clock"], "under the replay clock"
        assert any("2 run(s)" in line and "about a minute" in line for line in lines), lines
        assert owing["rebuilt"], "results rebuilt after"

    def test_a_run_that_does_not_complete_stops_the_bootstrap(self, owing, supply_dsn):
        from qa_tools.common import bootstrap, recheck

        owing["outcomes"] = [recheck.Outcome(7, "cp_run_042", False, "it broke")]
        with pytest.raises(scripted_decisions.ScriptRefused, match="cp_run_042"):
            bootstrap._confirm_corrections(lambda _m: None)
        assert not owing["rebuilt"]

    def test_a_run_the_backstop_froze_is_not_a_failure(self, owing, supply_dsn):
        from qa_tools.common import bootstrap, recheck

        owing["outcomes"] = [recheck.Outcome(7, "cp_run_042", False, "frozen", frozen=True)]
        bootstrap._confirm_corrections(lambda _m: None)
        assert owing["rebuilt"]


class TestAResumeConfirmsAsABootstrapDoes:
    """Criterion 19: a resumed bootstrap confirms the due corrections and
    runs what they owe, inside its own pass lock, before its results."""

    def test_it_confirms(self, monkeypatch):
        import contextlib
        from types import SimpleNamespace

        import cli.pipeline
        from qa_tools.common import (bootstrap, checkpoints, processing_pass,
                                     replay_inputs)

        order: list[str] = []
        cp = SimpleNamespace(name="ck", collection_id="child-protection", before=3,
                             pending_scripts=[], recorded=SimpleNamespace(
                                 readable=True, arrivals=[SimpleNamespace(run_id="r")]))
        monkeypatch.setattr(checkpoints, "require_synthetic", lambda: None)
        monkeypatch.setattr(checkpoints, "find", lambda name: cp)
        monkeypatch.setattr(checkpoints, "copy_for_resume",
                            lambda c: "postgresql://u:p@localhost:5432/resumed")
        monkeypatch.setattr(replay_inputs, "first_affected",
                            lambda rec: replay_inputs.FirstAffected(4, "changed from 4"))
        monkeypatch.setattr(cli.pipeline, "generated_collections", lambda: [])

        @contextlib.contextmanager
        def lock(_name):
            order.append("lock")
            yield
            order.append("unlock")
        monkeypatch.setattr(processing_pass, "pass_lock", lock)
        monkeypatch.setattr(bootstrap, "_run_collection", lambda *a, **k: order.append("run"))
        monkeypatch.setattr(bootstrap, "_confirm_corrections",
                            lambda say: order.append("confirm"))
        monkeypatch.setattr(bootstrap, "_rebuild_results", lambda s: order.append("rebuild"))
        monkeypatch.setattr(bootstrap, "targets_agree", lambda names: ())
        got = bootstrap.resume("ck")
        assert got.replayed
        assert order[:4] == ["lock", "run", "confirm", "unlock"], order
