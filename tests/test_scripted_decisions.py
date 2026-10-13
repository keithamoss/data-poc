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

    def test_a_decision_at_an_arrivals_instant_plays_before_it(self, conn, period):
        """Criterion 3's "at or after": a decision timed exactly at an
        arrival's receipt is applied before that arrival (sprint 11 critic,
        defect 4 - it used to wait until after)."""
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        player = self._player([_script(after_hours=3)], a_table)
        same = SimpleNamespace(received_at=datetime.fromisoformat("2026-05-01T04:00:00+00:00"))
        assert player.before(same) == 1

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


class TestTheDecisionPathItselfRefuses:
    """Sprint 11 critic, defect 3: the "playback only" lock lived in the
    person LOOKUP, so a caller holding the synthetic person's record could
    call filing_decisions.apply() directly and have it accepted as a
    person's decision. The one decision path now refuses it on its own
    (NFR 2: each lock refuses on its own)."""

    def test_outside_playback(self):
        from qa_tools.common import filing_decisions as fd

        config = people.parse_people_config()
        actor = next(p for p in config["people"].values() if people.is_synthetic(p))
        request = fd.Request(operation="mark-not-supplied", dataset_id=DS, actor=actor,
                             reason="no", period="2026-09-09", confirmed=True)
        with pytest.raises(people.UnknownActor, match="played back"):
            fd.apply(request, effective_at="2026-09-09T00:00:00+00:00")


class TestThePageShowsAName:
    """Sprint 11 critic, defect 1 (REQ-GEN-135 criterion 12): the dataset
    page printed a decision's actor as recorded - an email - so a scripted
    decision read 'scripted-history@synthetic.invalid'. A decision's actor is
    SHOWN by name, as REQ-PIPE-147 criterion 7 already does for who filed a
    delivery, for every person alike."""

    def test_a_mark_and_a_rejection_name_the_person(self):
        from pipeline import closed_slots

        shown = closed_slots._decision_entry("2026-09-08T05:00:00+00:00", SYNTHETIC, "why")
        assert shown["actor"] != SYNTHETIC and "synthetic" not in shown["actor"]

    def test_an_acknowledgement_names_the_person(self):
        from pipeline import acknowledgements

        shown = acknowledgements._acknowledged((SYNTHETIC, "looked", None))
        assert shown["actor"] != SYNTHETIC and "synthetic" not in shown["actor"]


class TestRecordedAtItsOwnInstant:
    """post-build-review #156, finding 3: in a replay the clock is anchored
    at the NEXT arrival before scripted decisions are played, so a person's
    decision was recorded as made the next day and the page said so.
    REQ-PIPE-081 criterion 28: recorded at the instant it takes effect."""

    def test_a_played_decision_is_recorded_when_it_took_effect(self, conn, period):
        from qa_tools.common import replay_clock

        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        player = TestPlayback()._player([_script(after_hours=3)], a_table)
        later = datetime.fromisoformat("2026-05-02T05:17:00+00:00")
        replay_clock._active = True
        try:
            replay_clock.anchor(later)
            assert player.before(SimpleNamespace(received_at=later)) == 1
        finally:
            replay_clock.stop()
        effective, recorded = conn.execute(
            f"SELECT effective_at, recorded_at FROM {dl.TABLE} "
            "WHERE supply = ? AND action = 'promote'", [a]).fetchall()[0]
        # The replay clock runs on from its anchor at real speed, so a few
        # milliseconds pass; before the fix this was a day.
        assert timedelta(0) <= recorded - effective < timedelta(seconds=5)


class TestAScriptedDecisionsReCheckIsRun:
    """post-build-review #161: a scripted decision that owes a re-check
    (TS-67's re-files) left it owed, because playback discarded what
    filing_decisions.apply returned and nothing in the replay drains a
    re-check. So the re-filed supplies were never checked nor gated in
    their new period. Keith, 2026-10-13: playback runs every scripted
    decision's owed re-check at the decision's own instant."""

    def test_no_re_check_a_scripted_decision_owed_is_left_open(self, deployment_history):
        from qa_tools.common import supply_db

        with supply_db.connect(read_only=True, label="test-161") as conn:
            scripted = conn.execute(
                f"SELECT count(*) FROM {dl.TABLE} WHERE actor = ?", [SYNTHETIC]).fetchone()[0]
            assert scripted, "the history holds no scripted decision to check"
            owed = conn.execute(
                "SELECT o.dataset_id, o.supply_id FROM qa.owed_run o "
                f"JOIN {dl.TABLE} d ON d.id = o.caused_by_decision "
                "WHERE o.kind = 'recheck' AND o.cleared_at IS NULL AND d.actor = ?",
                [SYNTHETIC]).fetchall()
        assert owed == [], f"scripted decisions left these re-checks owed: {owed}"

    def test_every_run_records_its_place_in_the_history(self, deployment_history):
        """post-build-review #161: a re-check run was recorded without the
        run_index its arrival carries, and the results rebuild sorts every
        current run by it - so the first history holding a re-check that
        ran crashed the Child Protection build (KeyError: 'run_index')."""
        from qa_tools.common import supply_db

        with supply_db.connect(read_only=True, label="test-161") as conn:
            rows = conn.execute(
                "SELECT run_key FROM qa.dataset_stats "
                "WHERE NOT (stats -> 'arrival_record') ? 'run_index'").fetchall()
            total = conn.execute("SELECT count(*) FROM qa.dataset_stats").fetchone()[0]
        assert total, "the history records no run"
        assert rows == [], f"runs recorded without run_index: {[r[0] for r in rows]}"


# ---------------------------------------------------------------------------
# REQ-GEN-200: a scripted decision about a PERIOD that received no supply.
# ---------------------------------------------------------------------------

AGENCY, COLLECTION = "child-protection-family-support", "child-protection"


def _period_script(**kw):
    base = dict(scenario="TS-1", operation="substitute", dataset_id=DS, reason="scripted",
                supply_index=None, after_hours=6, scope=sd.PERIOD, stands_on=-1)
    base.update(kw)
    return sd.Script(**base)


class TestAPeriodScopedScriptIsValidated:
    """Criteria 8 and 9, from configuration alone."""

    def test_a_good_period_scoped_substitution_has_no_problems(self):
        assert sd.problems([_period_script()], registered={"TS-1"}) == []

    @pytest.mark.parametrize("kw,says", [
        (dict(scope=None, stands_on=None, operation="promote"), "names neither a supply nor a period"),
        (dict(supply_index=0), "names both a supply and `scope: period`"),
        (dict(operation="promote", stands_on=None), "cannot be period-scoped"),
        (dict(stands_on=None), "needs `stands_on:`"),
        (dict(operation="de-substitute"), "only for a substitution"),
        (dict(stands_on=0), "not before the period it fills"),
        (dict(stands_on=2), "not before the period it fills"),
        (dict(scope="slot"), "scope must be `period`"),
        # post-build-review #168: a supply-scoped substitution passed and
        # then lost its stands_on at play time.
        (dict(scope=None, supply_index=0), "a substitution is about a period"),
        (dict(scope=None, supply_index=0, stands_on=None), "a substitution is about a period"),
        (dict(after_hours=-500), "`after_hours: -500` is before"),
        (dict(to_period="2024-Q1"), "`to_period:` means nothing on a period-scoped"),
        (dict(period_from="placement"), "`period_from:` means nothing on a period-scoped"),
        (dict(names_supply=False), "`names_supply:` means nothing on a period-scoped"),
    ])
    def test_each_refusal_names_the_entry_and_what_to_change(self, kw, says):
        found = sd.problems([_period_script(**kw)], registered={"TS-1"})
        assert any(says in f and "decision 1 (TS-1)" in f for f in found), found

    def test_an_absent_supply_is_not_read_as_supply_zero(self, tmp_path):
        script = tmp_path / "s.yaml"
        script.write_text("decisions:\n  - {scenario: TS-1, operation: promote, "
                          f"dataset: {DS}, reason: r, after_hours: 1}}\n")
        loaded = sd.load(script)
        assert loaded[0].supply_index is None
        assert any("names neither" in f for f in sd.problems(loaded, registered={"TS-1"}))

    def test_every_existing_script_still_names_its_supply(self):
        """Criterion 10: the nine committed scripts play unedited."""
        loaded = sd.load()
        assert loaded, "precondition: the committed script has entries"
        assert all(s.supply_index is not None and s.scope is None for s in loaded)


class TestThePeriodsDueInstantIsTheCalendars:
    """Criterion 1 against the REAL calendar (post-build-review #168): every
    playback test pins _due_at, so nothing computed it."""

    def test_due_at_is_the_slots_due_instant_not_its_claim_opening(self):
        from qa_tools.common import schedule, slots

        on = schedule.date_of("2024-Q3", "cp-placements")
        due = sd._due_at("cp-placements", "2024-Q3")
        assert due == slots.slot_instants("cp-placements", on).due_at
        assert due.isoformat() == "2024-08-01T09:00:00+08:00"

    def test_a_period_scoped_script_is_timed_from_it(self):
        from types import SimpleNamespace

        script = _period_script(dataset_id="cp-placements", after_hours=5)
        timed, why = sd._timed_by_period(script, SimpleNamespace(period="2024-Q3"))
        assert why == ""
        assert timed.at.isoformat() == "2024-08-01T14:00:00+08:00"
        assert timed.stands_on == "2024-Q2"

    def test_before_plays_it_once_the_replay_reaches_its_instant(self, monkeypatch):
        from types import SimpleNamespace

        played = []
        monkeypatch.setattr(sd, "_apply", lambda t: played.append(t.script.operation))
        monkeypatch.setattr(sd, "_refuse_unless_synthetic", lambda: None)
        player = sd.Player("child-protection", placements={"TS-1": SimpleNamespace(
            period="2024-Q3", supplies=())}, scripts=[
            _period_script(dataset_id="cp-placements"),
            _period_script(dataset_id="cp-placements", operation="mark-not-supplied",
                           stands_on=None)])
        at = lambda iso: SimpleNamespace(received_at=datetime.fromisoformat(iso))
        assert player.before(at("2024-07-01T00:00:00+08:00")) == 0
        assert player.before(at("2024-09-01T00:00:00+08:00")) == 2
        assert played == ["substitute", "mark-not-supplied"]


class TestAMalformedScriptStopsTheReplayByName:
    """post-build-review #168: a script naming neither a supply nor a period
    scope reached the Player as a bare TypeError, naming no scenario."""

    def test_it_is_refused_naming_the_scenario(self, monkeypatch):
        from types import SimpleNamespace

        monkeypatch.setattr(sd, "_refuse_unless_synthetic", lambda: None)
        player = sd.Player("child-protection", placements={"TS-1": SimpleNamespace(
            period="2024-Q3", supplies=("run_001",))},
            scripts=[_period_script(scope=None, stands_on=None, operation="promote",
                                    dataset_id="cp-placements")])
        with pytest.raises(sd.ScriptRefused, match="TS-1.*names neither a supply"):
            player.finish()


class TestTheRelativePeriodCountsTheDatasetsOwnPeriods:
    """Criteria 3 and 4 (Keith, 2026-10-13): one resolver, the dataset's own
    sequence - case-workers is delivered in February and August only."""

    def test_case_workers_skips_the_quarter_it_owes_nothing_for(self):
        from qa_tools.common import slots
        assert slots.relative_period("cp-case-workers", "2024-Q3", -1) == "2024-Q1"
        assert slots.relative_period("cp-clients", "2024-Q3", -1) == "2024-Q2"

    def test_none_before_the_first_period_or_for_an_unknown_one(self):
        from qa_tools.common import slots
        first = slots.slots_for_dataset("cp-clients")[0].name
        assert slots.relative_period("cp-clients", first, -1) is None
        assert slots.relative_period("cp-clients", "no-such-period", -1) is None


class TestAPeriodScopedDecisionIsPlayed:
    """Criteria 1, 3, 5, 6, 7 and 11, against a real database. The calendar's
    two lookups are pinned so the periods can be this test's own."""

    DUE = datetime.fromisoformat("2026-05-01T01:00:00+00:00")

    @pytest.fixture
    def pinned(self, monkeypatch, period):
        earlier = period + "-before"
        monkeypatch.setattr(sd, "_due_at", lambda ds, p: self.DUE if p == period else None)
        monkeypatch.setattr("qa_tools.common.slots.relative_period",
                            lambda ds, p, off: earlier if (p, off) == (period, -1) else None)
        return period, earlier

    def _promoted(self, conn, period, received):
        from qa_tools.common import promotion
        supply, physical = _filed(conn, period, received)
        promotion.promote(conn, agency_id=AGENCY, collection_id=COLLECTION, dataset_id=DS,
                          supply=supply, period=period, physical_tables=[physical],
                          actor="tester", actor_kind=dl.PERSON, effective_at=received)
        return supply

    def _player(self, scripts, period):
        placements = {"TS-1": scenario_map.Placement(
            scenario_id="TS-1", dataset=DS, supplies=(), period=period,
            in_place_on="2026-05-02")}
        return sd.Player("child-protection", scripts=scripts, placements=placements)

    def test_a_substitution_is_timed_from_the_period_due_and_stands_on_its_supply(
            self, conn, pinned):
        period, earlier = pinned
        stood = self._promoted(conn, earlier, "2026-02-01T01:00:00+00:00")
        assert self._player([_period_script(after_hours=6)], period).finish() == 1
        row = conn.execute(
            f"SELECT action, to_slot, stands_on, supply, actor_kind, effective_at FROM {dl.TABLE} "
            "WHERE dataset_id = ? AND to_slot = ? AND action = 'substitute'",
            [DS, period]).fetchall()
        assert len(row) == 1
        action, to_slot, stands_on, supply, kind, at = row[0]
        assert (stands_on, supply, kind) == (earlier, stood, dl.PERSON)
        assert at == self.DUE + timedelta(hours=6)

    def test_decisions_at_one_instant_play_in_the_order_listed(self, conn, pinned):
        """Criterion 5. A de-substitution played BEFORE the substitution it
        removes would be refused, so this fails if the order is not kept."""
        period, earlier = pinned
        self._promoted(conn, earlier, "2026-02-01T01:00:00+00:00")
        scripts = [_period_script(after_hours=6),
                   _period_script(operation="de-substitute", stands_on=None, after_hours=6)]
        assert self._player(scripts, period).finish() == 2
        actions = [r[0] for r in conn.execute(
            f"SELECT action FROM {dl.TABLE} WHERE dataset_id = ? AND to_slot = ? "
            "OR (dataset_id = ? AND from_slot = ? AND action = 'de-substitute') ORDER BY id",
            [DS, period, DS, period]).fetchall()]
        assert actions == ["substitute", "de-substitute"]

    def test_listed_the_other_way_round_the_replay_stops(self, conn, pinned):
        """The same two decisions in the opposite order: the de-substitution,
        played first, has nothing to remove - and a scripted decision that
        changes nothing stops the replay (Keith, 2026-10-13, amending
        REQ-GEN-135 criterion 6): a history quietly lacking the decision a
        scenario is about is what that criterion exists to prevent."""
        period, earlier = pinned
        self._promoted(conn, earlier, "2026-02-01T01:00:00+00:00")
        scripts = [_period_script(operation="de-substitute", stands_on=None, after_hours=6),
                   _period_script(after_hours=6)]
        with pytest.raises(sd.ScriptRefused, match="changed nothing"):
            self._player(scripts, period).finish()

    def test_a_stood_on_period_holding_nothing_stops_the_replay(self, conn, pinned):
        """Criteria 6 and 7: the filing decision's own refusal stands, naming
        the scenario, the operation and the period - no fall-back."""
        period, earlier = pinned
        with pytest.raises(sd.ScriptRefused) as got:
            self._player([_period_script()], period).finish()
        message = str(got.value)
        assert "TS-1" in message and "substitute" in message and period in message
        # Substitution's OWN refusal, not any exception (post-build-review #168).
        assert "holds no promoted supply" in message
        assert "  " not in message and ".." not in message
        assert not conn.execute(f"SELECT 1 FROM {dl.TABLE} WHERE to_slot = ?",
                                [period]).fetchall()

    def test_a_period_with_no_slot_is_refused_at_the_end_of_the_replay(self, conn, pinned):
        _, _ = pinned
        with pytest.raises(sd.ScriptRefused, match="no slot"):
            self._player([_period_script()], "2099-not-a-slot").finish()

    def test_refused_on_an_asset_that_is_not_synthetic(self, monkeypatch, tmp_path):
        """Criterion 11."""
        asset = tmp_path / "data-asset.yaml"
        asset.write_text("synthetic: false\n")
        monkeypatch.setattr("qa_tools.common.hierarchy.DATA_ASSET_YAML", asset)
        with pytest.raises(sd.ScriptRefused, match="synthetic"):
            sd.Player("child-protection", scripts=[_period_script()], placements={})


class TestThePlantedPairsAreSettled:
    """REQ-GEN-196 criteria 6 and 13: on the bootstrapped history, each pair
    (TS-68 to TS-74) carries exactly one choose-file decision, by the
    synthetic person, with each file's outcome as its script says."""

    #: Each pair's two files, `{D}`/`{D+1}` the placement day and the next,
    #: and the outcome each was settled with (criterion 6).
    EXPECTED = {
        "TS-68": {"{D}.csv": "supply", "{D}-1.csv": "superseded"},
        "TS-69": {"{D}.csv": "supply", "{D+1}.csv": "refiled"},
        "TS-70": {"{D}.csv": "rejected", "{D}-resend.csv": "supply"},
        "TS-71": {"{D}_TEST.csv": "rejected", "{D}.csv": "supply"},
        "TS-72": {"{D}.csv": "supply", "{D}-test.csv": "rejected"},
        "TS-73": {"{D}.csv": "rejected", "{D}_TEST.csv": "rejected"},
        "TS-74": {"{D+1}.csv": "refiled", "{D}_TEST.csv": "rejected"},
    }

    def test_one_choose_file_each_with_its_scripted_outcomes(self, deployment_history):
        from datetime import date

        from qa_tools.common import supply_db

        placed = scenario_map.read_placements()
        missing = sorted(set(self.EXPECTED) - set(placed))
        assert not missing, f"not placed in the generated history: {missing}"
        with supply_db.connect(read_only=True, label="test-196") as conn:
            rows = conn.execute(
                f"SELECT d.id, f.filename, f.outcome, f.to_slot FROM {dl.TABLE} d "
                'JOIN "qa".decision_file f ON f.decision_id = d.id '
                "WHERE d.action = 'choose-file' AND d.actor = ?", [SYNTHETIC]).fetchall()
        # EVERY ROW KEPT (#172): keyed by filename alone, a second decision
        # for the same file overwrote the first and still read as one.
        all_for: dict[str, list] = {}
        for decision, name, outcome, to_slot in rows:
            all_for.setdefault(name, []).append((decision, outcome, to_slot))
        twice = {n: r for n, r in all_for.items() if len(r) > 1}
        assert not twice, f"files settled more than once: {twice}"
        by_file = {name: found[0] for name, found in all_for.items()}
        for sid, files in self.EXPECTED.items():
            day = date.fromisoformat(placed[sid].period)
            nxt = (day + timedelta(days=1)).isoformat()
            decisions = set()
            for template, outcome in files.items():
                name = "birth_registrations_" + template.replace(
                    "{D+1}", nxt).replace("{D}", day.isoformat())
                assert name in by_file, f"{sid}: no settled outcome for {name}"
                decision, got, to_slot = by_file[name]
                decisions.add(decision)
                assert got == outcome, f"{sid}: {name} settled {got}, scripted {outcome}"
                if outcome == "refiled":
                    assert to_slot == nxt, f"{sid}: {name} re-filed to {to_slot}"
            assert len(decisions) == 1, f"{sid}: {len(decisions)} choose-file decisions"
