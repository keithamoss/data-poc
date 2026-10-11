"""After a correction, the data asset's manager confirms its proposed moves
all at once (REQ-PIPE-170).

Recorded facts come from real filings against the real cp-clients agreement
(2023-Q3 dated 2023-08-01, due 09:00 Perth, 8h grace). A correction is
declared in a copy of the configuration - the change made AND its
corrections entry, as a merged correction is - and confirmed against it.
"""
from __future__ import annotations

import copy
import json
from datetime import timedelta, timezone

import pytest
import yaml

import filing_support
from datetime import datetime
from qa_tools.common import (agreement, agreement_freeze, assignment, asset_time,
                             correction_apply, decision_log, filing, hierarchy, people,
                             qa_store, supply_db, supply_holds)

PERTH = timezone(timedelta(hours=8))
DATASET = "cp-clients"
RECEIVED = datetime(2023, 8, 1, 12, tzinfo=PERTH)
SUPPLY = "apply-s"
AT = "2026-10-11T09:00:00+08:00"


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-correction-apply") as c:
        qa_store.ensure_schema(c)
        c.execute(f'TRUNCATE "{qa_store.SCHEMA}".filing CASCADE')
        c.execute(f'TRUNCATE "{qa_store.SCHEMA}".correction_applied')
        _file(SUPPLY, "2023-Q3", RECEIVED)
        yield c
        # LEFT EMPTY FOR THE NEXT MODULE ON THIS WORKER: the activity feed
        # reads every applied correction, so one left behind here appeared in
        # tests/test_embed_dashboard_data.py's feed.
        c.execute(f'TRUNCATE "{qa_store.SCHEMA}".correction_applied')


@pytest.fixture
def manager():
    found = people.asset_managers()
    assert found, "contract/people.yaml names an asset manager"
    return found[0]


def _file(supply, slot, received):
    filing_support.file(assignment.Assignment(
        dataset_id=DATASET, supply_id=supply, slot=slot, branch=assignment.OPEN_UNFILLED,
        considered=(slot,), received_at=received))


def _docs():
    """The committed files with no corrections declared - the ones the real
    contract carries (REQ-PIPE-181's migration, for one) are not this
    module's subject, and would read as pending beside its own."""
    cal = copy.deepcopy(yaml.safe_load(agreement.CALENDAR_YAML.read_text()))
    asset = copy.deepcopy(yaml.safe_load(asset_time.DATA_ASSET_YAML.read_text()))
    for owner in (cal.get("calendars") or []) + (cal.get("datasets") or []) \
            + (cal.get("collections") or []):
        owner.pop("corrections", None)
    return cal, asset


def _clients(cal):
    entry = next(d for d in cal["datasets"] if d["id"] == DATASET)
    entry["participation"]["versions"] = copy.deepcopy(entry["participation"]["versions"])
    return entry


def _quarterly(cal):
    return next(c for c in cal["calendars"] if c["name"] == "quarterly")


def _corrected(change, reference="CAB-1", reason="the agreement was wrong"):
    """The configuration after a merged correction: the change, and its
    declared corrections entry on each owner, as the gate requires."""
    base_cal, base_asset = _docs()
    cal, asset = copy.deepcopy(base_cal), copy.deepcopy(base_asset)
    change(cal, asset)
    found = agreement_freeze.changed(base_cal, cal, base_asset, asset)
    by_owner: dict = {}
    for key, (item, old, new, _f) in found.items():
        by_owner.setdefault(item.owner, []).append({"item": key, "old": old, "new": new})
    for owner, changes in by_owner.items():
        # TODAY ON THE ASSET'S CLOCK: a correction dated before the verdicts
        # it re-judges would not account for them (REQ-PIPE-173), and a fixed
        # date would make that true one day after this test was written.
        today = asset_time.local_date(asset_time.now()).isoformat()
        entry = {"change_reference": reference, "date": today, "author": "a",
                 "approver": "b", "reason": reason, "changes": changes}
        if owner[0] == "calendar":
            target = next(c for c in cal["calendars"] if str(c["name"]) == owner[1])
        elif owner[0] == "dataset":
            target = next(d for d in cal["datasets"] if str(d["id"]) == owner[1])
        else:
            target = asset["timezone"]
        target["corrections"] = list(target.get("corrections") or []) + [entry]
    return cal, asset


def _move_q3(cal, asset, to="2023-10-20"):
    for d in _quarterly(cal)["versions"][-1]["dates"]:
        if d["period"] == "2023-Q3":
            d["date"] = to


def _grace(cal, asset):
    _clients(cal)["participation"]["versions"][0]["grace"] = "1h"


def _current(conn, supply=SUPPLY):
    return filing.filing_for(DATASET, supply)


class TestPending:
    """Criterion 20: derived from configuration and the applied record."""

    def test_a_declared_correction_with_no_record_is_pending(self, conn):
        docs = _corrected(_grace)
        [p] = correction_apply.pending(conn, docs)
        assert p.reference == "CAB-1" and DATASET in correction_apply.affected_datasets(
            p, docs[0])

    def test_the_agreement_before_it_is_rebuilt_from_its_own_old_values(self, conn):
        docs = _corrected(_move_q3)
        [p] = correction_apply.pending(conn, docs)
        base, work = correction_apply.states(p, [p], docs)
        base_items = agreement_freeze.flatten(*base)
        assert base_items["calendar quarterly period 2023-Q3"].value == "2023-08-01"
        assert agreement_freeze.flatten(*work)[
            "calendar quarterly period 2023-Q3"].value == "2023-10-20"


class TestConfirming:
    """Criteria 4-9, 15, 18-20."""

    def test_only_the_asset_manager_may_confirm(self, conn):
        docs = _corrected(_move_q3)
        with pytest.raises(people.RoleRefused):
            correction_apply.confirm(conn, "CAB-1", actor={"email": "nobody@example.com"},
                                     effective_at=AT, docs=docs)

    def test_a_move_is_a_persons_re_file_naming_the_correction(self, conn, manager):
        docs = _corrected(_move_q3)
        done = correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT,
                                        docs=docs)
        assert [(s, a, b) for _d, s, a, b in done.moved] == [(SUPPLY, "2023-Q3", "2023-Q2")]
        assert _current(conn)["slot"] == "2023-Q2"
        [(actor, kind, reason)] = conn.execute(
            f"SELECT actor, actor_kind, reason FROM {decision_log.TABLE} WHERE supply = ? "
            "AND action = 'refile' ORDER BY id DESC LIMIT 1", [SUPPLY]).fetchall()
        assert actor == manager["email"] and kind == "person" and "CAB-1" in reason
        assert done.owed_rechecks, "it re-runs QA and re-gates through an owed re-check"

    def test_it_is_applied_once_and_is_no_longer_pending(self, conn, manager):
        docs = _corrected(_move_q3)
        correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT, docs=docs)
        assert correction_apply.pending(conn, docs) == []
        [(summary,)] = conn.execute(
            f"SELECT summary FROM {correction_apply.APPLIED} WHERE change_reference = 'CAB-1'"
        ).fetchall()
        record = summary if isinstance(summary, dict) else json.loads(summary)
        assert record["moved"]
        with pytest.raises(correction_apply.NotPending, match="already applied"):
            correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT, docs=docs)

    def test_a_kept_supply_stays_and_is_recorded_as_kept(self, conn, manager):
        docs = _corrected(_move_q3)
        done = correction_apply.confirm(
            conn, "CAB-1", actor=manager, keep={(DATASET, SUPPLY)},
            keep_reason="genuinely Q3 data, sent early", effective_at=AT, docs=docs)
        assert not done.moved and done.kept
        assert _current(conn)["slot"] == "2023-Q3"
        [(reason,)] = conn.execute(
            f"SELECT reason FROM {decision_log.TABLE} WHERE supply = ? AND action = 'keep' "
            "ORDER BY id DESC LIMIT 1", [SUPPLY]).fetchall()
        assert "CAB-1" in reason and "sent early" in reason

    def test_keeping_needs_a_reason(self, conn, manager):
        docs = _corrected(_move_q3)
        with pytest.raises(decision_log.DecisionRefused, match="needs a reason"):
            correction_apply.confirm(conn, "CAB-1", actor=manager, keep={(DATASET, SUPPLY)},
                                     effective_at=AT, docs=docs)

    def test_a_blocked_move_must_be_cleared_or_kept(self, conn, manager):
        _file("apply-c@1#1", "2023-Q3", RECEIVED + timedelta(minutes=1))
        docs = _corrected(_move_q3)
        with pytest.raises(decision_log.DecisionRefused, match="blocked"):
            correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT, docs=docs)
        done = correction_apply.confirm(
            conn, "CAB-1", actor=manager, keep={(DATASET, "apply-c@1#1")},
            keep_reason="contested - deciding separately", effective_at=AT, docs=docs)
        assert done.kept and done.moved

    def test_a_supply_no_period_takes_is_held_naming_the_correction(self, conn, manager):
        """Case Workers owes February and August only: with 2023-Q3 moved to
        October its August supply has no open period, so it is held."""
        workers = "cp-case-workers"
        filing_support.file(assignment.Assignment(
            dataset_id=workers, supply_id="apply-h", slot="2023-Q3",
            branch=assignment.OPEN_UNFILLED, considered=("2023-Q3",), received_at=RECEIVED))
        docs = _corrected(_move_q3)
        _p, t = correction_apply.trial_for(conn, "CAB-1", docs=docs)
        [m] = [m for m in t.moves if m.supply_id == "apply-h"]
        assert m.held and not m.blocked
        done = correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT,
                                        docs=docs)
        assert (workers, "apply-h", "2023-Q3") in done.held
        assert filing.filing_for(workers, "apply-h")["slot"] is None
        [hold] = [h for h in supply_holds.outstanding(conn) if h.supply_id == "apply-h"]
        assert "CAB-1" in json.dumps(hold.reason)

    def test_a_verdict_is_re_judged_in_place_naming_the_correction(self, conn, manager):
        docs = _corrected(_grace)
        done = correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT,
                                        docs=docs)
        assert [(s, old, new) for _d, s, _slot, old, new in done.rejudged] == [
            (SUPPLY, "on_time", "late")]
        assert _current(conn)["classification"] == "late"

    def test_a_list_that_changed_since_it_was_shown_is_refused(self, conn, manager):
        docs = _corrected(_move_q3)
        with pytest.raises(decision_log.DecisionRefused, match="changed since"):
            correction_apply.confirm(conn, "CAB-1", actor=manager, acknowledge="00000000",
                                     effective_at=AT, docs=docs)


def test_the_summary_is_the_previews_form_with_what_was_kept(conn, manager):
    _file("apply-k", "2023-Q3", RECEIVED + timedelta(minutes=2))
    docs = _corrected(_move_q3)
    p, t = correction_apply.trial_for(conn, "CAB-1", docs=docs)
    done = correction_apply.confirm(conn, "CAB-1", actor=manager, keep={(DATASET, "apply-k")},
                                    keep_reason="really Q3", effective_at=AT, docs=docs)
    text = correction_apply.summary(p, t, done, as_at=datetime.now(PERTH), database="d")
    assert text.startswith("# Applied: correction CAB-1")
    assert text.index("## Summary") < text.index("## Kept where they are")
    assert "`apply-k` in 2023-Q3: really Q3" in text


def test_a_correction_hold_says_which_correction_and_what_to_do():
    held = supply_holds.Held(dataset_id=DATASET, supply_id="x", kind=supply_holds.ASSIGNMENT_RULE,
                             reason={"unavailable": [], "considered": [], "correction": "CAB-9",
                                     "correction_reason": "dates were wrong"},
                             raised_by="correction CAB-9", delivery=None, raised_at=None)
    assert "correction CAB-9 was confirmed" in held.describe()
    assert "dates were wrong" in held.describe()
    assert any("declare a correction" in r for r in held.responses)
    assert all("re-file" not in r for r in held.responses), "a held supply is promoted"


class TestTheCommands:
    """Criteria 10, 12, 14, 16-18, 22, through the real commands."""

    @pytest.fixture
    def declared(self, monkeypatch):
        from qa_tools.common import correction_trial

        docs = _corrected(_move_q3)
        monkeypatch.setattr(correction_trial, "working", lambda: docs)
        return docs

    def _run(self, *args, input=None):
        from click.testing import CliRunner

        from cli import supply as supply_cli
        return CliRunner().invoke(supply_cli.supply_group, list(args), input=input)

    def _as(self, monkeypatch, person):
        from cli import filing_tui

        monkeypatch.setattr(filing_tui, "actor_at_the_keyboard", lambda: person)

    def test_none_pending_says_so(self, conn, monkeypatch):
        from qa_tools.common import correction_trial

        monkeypatch.setattr(correction_trial, "working", _docs)
        got = self._run("corrections")
        assert got.exit_code == 0 and "No corrections are waiting" in got.output

    def test_it_lists_pending_and_shows_one_summary_first(self, conn, declared):
        listed = self._run("corrections")
        assert "CAB-1" in listed.output and "cp-clients" in listed.output
        one = self._run("corrections", "--reference", "CAB-1")
        assert one.exit_code == 0, one.output
        assert one.output.index("## Summary") < one.output.index("## Supplies that would move")
        assert "--acknowledge" in one.output

    def test_anyone_else_is_refused_before_any_reason_naming_who_may(
            self, conn, declared, monkeypatch, manager):
        self._as(monkeypatch, {"email": "nobody@example.com"})
        got = self._run("confirm-correction", "--reference", "CAB-1")
        assert got.exit_code != 0
        assert "manager role" in got.output and people.actor_name(manager) in got.output
        assert "Summary" not in got.output, "refused before anything is worked out"

    def test_yes_needs_the_key(self, conn, declared, monkeypatch, manager):
        self._as(monkeypatch, manager)
        got = self._run("confirm-correction", "--reference", "CAB-1", "--yes")
        assert got.exit_code != 0 and "--acknowledge" in got.output
        assert correction_apply.pending(conn, declared), "nothing was applied"

    def test_confirmed_with_the_key_it_applies_and_says_to_attach_it(
            self, conn, declared, monkeypatch, manager, tmp_path):
        self._as(monkeypatch, manager)
        _p, t = correction_apply.trial_for(conn, "CAB-1", docs=declared)
        out = tmp_path / "applied.md"
        got = self._run("confirm-correction", "--reference", "CAB-1", "--yes",
                        "--acknowledge", correction_apply.key(t), "--output", str(out))
        assert got.exit_code == 0, got.output
        assert "Attach it to CAB-1" in got.output
        assert out.read_text().startswith("# Applied: correction CAB-1")
        assert correction_apply.pending(conn, declared) == []

    def test_keeping_a_supply_that_is_not_proposed_is_refused(
            self, conn, declared, monkeypatch, manager):
        self._as(monkeypatch, manager)
        got = self._run("confirm-correction", "--reference", "CAB-1", "--keep", "nope",
                        "--keep-reason", "r", "--yes", "--acknowledge", "x")
        assert got.exit_code != 0 and "not among this correction" in got.output


class TestTheTerminal:
    """Criteria 2, 5, 13-15, 17, 18: the filing menu's corrections door."""

    @pytest.fixture
    def declared(self, monkeypatch):
        from qa_tools.common import correction_trial

        docs = _corrected(_move_q3)
        monkeypatch.setattr(correction_trial, "working", lambda: docs)
        return docs

    def _answers(self, monkeypatch, selects, texts=()):
        from cli import common

        picks, words = iter(selects), iter(texts)
        asked = []

        def select(message, choices, **k):
            asked.append((message, list(choices)))
            want = next(picks)
            return next((c for c in choices if want is not None and c.startswith(want)), None)
        monkeypatch.setattr(common, "select", select)
        monkeypatch.setattr(common, "text_prompt", lambda *a, **k: next(words))
        monkeypatch.setattr(common, "confirm_change", lambda *a, **k: True)
        return asked

    def test_pending_corrections_are_offered_above_the_collections(
            self, conn, declared, monkeypatch, manager):
        from cli import filing_tui

        monkeypatch.setattr(filing_tui, "actor_at_the_keyboard", lambda: manager)
        asked = self._answers(monkeypatch, [filing_tui._MENU_CORRECTIONS, filing_tui._KEEP_DONE])
        filing_tui.filing_menu()
        assert asked[0][1][0].startswith(filing_tui._MENU_CORRECTIONS)
        assert correction_apply.pending(conn, declared) == [], "confirmed from the menu"

    def test_anyone_else_may_look_and_is_told_who_confirms(
            self, conn, declared, monkeypatch, capsys):
        from cli import filing_tui

        monkeypatch.setattr(filing_tui, "actor_at_the_keyboard",
                            lambda: {"email": "nobody@example.com"})
        asked = self._answers(monkeypatch, [])
        filing_tui.corrections_flow(correction_apply.pending(conn, declared))
        out = capsys.readouterr().out
        assert "## Summary" in out and "only the asset manager confirms" in out
        assert not asked, "no choice or reason was asked for"
        assert correction_apply.pending(conn, declared)

    def test_the_manager_keeps_one_with_a_reason_and_confirms_the_rest(
            self, conn, declared, monkeypatch, manager):
        from cli import filing_tui

        _file("apply-t2", "2023-Q3", RECEIVED + timedelta(minutes=4))
        monkeypatch.setattr(filing_tui, "actor_at_the_keyboard", lambda: manager)
        self._answers(monkeypatch, [f"Keep {DATASET} apply-t2", filing_tui._KEEP_DONE],
                      ["really Q3 data"])
        filing_tui.corrections_flow(correction_apply.pending(conn, declared))
        assert filing.filing_for(DATASET, "apply-t2")["slot"] == "2023-Q3"
        assert filing.filing_for(DATASET, SUPPLY)["slot"] == "2023-Q2"


class TestThePassNotesIt:
    """Criteria 3, 19 and 20: needing action from configuration and the
    applied record alone, and gone once applied."""

    def test_a_pending_correction_needs_action_until_applied(self, conn, monkeypatch, manager):
        from qa_tools.common import correction_trial, outstanding

        docs = _corrected(_move_q3)
        monkeypatch.setattr(correction_trial, "working", lambda: docs)
        [item] = [i for i in outstanding._from_pending_corrections(conn)]
        assert item.kind == outstanding.PENDING_CORRECTION
        assert item.severity == outstanding.NEEDS_ACTION and "CAB-1" in item.headline
        assert "cp-clients" in [ds for _a, _c, ds in item.affects]
        correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT, docs=docs)
        assert outstanding._from_pending_corrections(conn) == []

    def test_the_pass_summary_names_it(self, monkeypatch, capsys):
        from cli import pipeline
        from qa_tools.common import processing_pass

        pipeline._say_pass(processing_pass.PassReport(pending_corrections=["CAB-1"]))
        out = capsys.readouterr().out
        assert "CAB-1" in out and "confirm" in out


def _workers_file(supply, slot, received):
    filing_support.file(assignment.Assignment(
        dataset_id="cp-case-workers", supply_id=supply, slot=slot,
        branch=assignment.OPEN_UNFILLED, considered=(slot,), received_at=received))


def _claim_window(days):
    def change(cal, asset):
        _quarterly(cal)["versions"][-1]["claim_window"] = f"{days}d"
    return change


class TestScenarioRegister:
    """TS-57 to TS-62 (plans/supply-model.md), each a unit test (criterion
    23's second half). TS-63 needs REQ-PIPE-179, unsigned; TS-64 is
    tests/test_correction_trial.py's."""

    def test_ts57_a_correction_that_only_re_judges(self, conn, manager):
        from qa_tools.common import verdict

        late = RECEIVED + timedelta(days=1)
        _file("ts57", "2023-Q3", late)
        # A DAY LATER is the register's late -> on time: arrived 12:00 the
        # day after the old due date, inside the new one's grace (three days
        # later would make it early, not on time).
        docs = _corrected(lambda cal, asset: _move_q3(cal, asset, "2023-08-02"))
        _p, t = correction_apply.trial_for(conn, "CAB-1", docs=docs)
        assert not [m for m in t.moves if m.supply_id == "ts57"], "no move"
        assert [(v.old, v.new) for v in t.verdicts if v.supply_id == "ts57"] == [
            ("late", "on_time")]
        assert correction_apply.pending(conn, docs), "still needs confirming"
        correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT, docs=docs)
        history = verdict.history(conn, DATASET, "ts57")
        assert [v["classification"] for v in history] == ["late", "on_time"]
        assert history[-1]["correction_ref"] == "CAB-1"

    def test_ts58_a_supply_moves_into_the_window_that_now_covers_it(self, conn, manager):
        _file("ts58", "2023-Q2", datetime(2023, 7, 10, 12, tzinfo=PERTH))
        docs = _corrected(_claim_window(28))
        _p, t = correction_apply.trial_for(conn, "CAB-1", docs=docs)
        [m] = [m for m in t.moves if m.supply_id == "ts58"]
        assert (m.from_period, m.to_period) == ("2023-Q2", "2023-Q3")
        done = correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT,
                                        docs=docs)
        assert (DATASET, "ts58", "2023-Q2", "2023-Q3") in done.moved
        assert done.owed_rechecks, "re-QA'd and re-gated through an owed re-check"

    def test_ts59_one_kept_with_a_reason_the_other_moved(self, conn, manager):
        _file("ts59a", "2023-Q2", datetime(2023, 7, 10, 12, tzinfo=PERTH))
        _file("ts59b", "2023-Q2", datetime(2023, 7, 11, 12, tzinfo=PERTH))
        docs = _corrected(_claim_window(28))
        p, t = correction_apply.trial_for(conn, "CAB-1", docs=docs)
        done = correction_apply.confirm(conn, "CAB-1", actor=manager,
                                        keep={(DATASET, "ts59a")}, keep_reason="really Q2",
                                        effective_at=AT, docs=docs)
        assert filing.filing_for(DATASET, "ts59a")["slot"] == "2023-Q2"
        assert filing.filing_for(DATASET, "ts59b")["slot"] == "2023-Q3"
        [(actor, slot, reason)] = conn.execute(
            f"SELECT actor, to_slot, reason FROM {decision_log.TABLE} WHERE supply = 'ts59a' "
            "AND action = 'keep'").fetchall()
        assert actor == manager["email"] and slot == "2023-Q2"
        assert "CAB-1" in reason and "really Q2" in reason
        text = correction_apply.summary(p, t, done, as_at=datetime.now(PERTH), database="d")
        assert "ts59a" in text and "ts59b" in text

    def test_ts60_a_supply_left_with_no_period_is_held(self, conn, manager):
        _workers_file("ts60", "2023-Q3", datetime(2023, 7, 25, 12, tzinfo=PERTH))
        docs = _corrected(_claim_window(1))
        _p, t = correction_apply.trial_for(conn, "CAB-1", docs=docs)
        [m] = [m for m in t.moves if m.supply_id == "ts60"]
        assert m.held
        done = correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT,
                                        docs=docs)
        assert ("cp-case-workers", "ts60", "2023-Q3") in done.held
        [hold] = [h for h in supply_holds.outstanding(conn) if h.supply_id == "ts60"]
        assert hold.correction == "CAB-1"

    def test_ts61_a_blocked_move_keeps_the_correction_open(self, conn, manager):
        _file("ts61@1#1", "2023-Q3", RECEIVED + timedelta(minutes=9))
        docs = _corrected(_move_q3)
        _p, t = correction_apply.trial_for(conn, "CAB-1", docs=docs)
        [m] = [m for m in t.moves if m.supply_id == "ts61@1#1"]
        assert m.blocked and "contested" in m.blocked
        with pytest.raises(decision_log.DecisionRefused, match="blocked"):
            correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT, docs=docs)
        assert correction_apply.pending(conn, docs), "still needing action"
        assert filing.filing_for(DATASET, "ts61@1#1")["slot"] == "2023-Q3", "not moved"

    def test_ts62_merged_not_confirmed_refuses_nothing(self, conn):
        from qa_tools.common import agreement_drift

        docs = _corrected(_grace)
        assert agreement_drift.refusal_for(conn, DATASET, cal_doc=docs[0],
                                           asset_doc=docs[1]) is None, \
            "a declared, unapplied correction accounts for the difference"
        assert correction_apply.pending(conn, docs), "and it is listed as needing action"


def _promote(conn, dataset, supply, slot):
    """A promotion record and the period's table, written directly - the
    period then reads as held by this supply, with a table to take out."""
    from qa_tools.common import period_schema

    schema = period_schema.period_schema(slot)
    table = hierarchy.dataset(dataset).table
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')
    conn.execute(f'DROP TABLE IF EXISTS "{schema}"."{table}"')
    conn.execute(f'CREATE TABLE "{schema}"."{table}" (id integer)')
    return conn.execute(
        f"INSERT INTO {decision_log.TABLE} (agency_id, collection_id, dataset_id, action, "
        "supply, to_slot, actor, actor_kind, effective_at) VALUES ('a', 'c', ?, 'promote', ?, "
        "?, 'x', 'person', ?) RETURNING id",
        # A FIXED INSTANT BEFORE AT, never now(): with now() the promotion
        # read as newer than a correction confirmed at AT once the wall clock
        # passed 09:00 on 11 Oct 2026, and the period stayed held by it.
        [dataset, supply, slot, RECEIVED + timedelta(days=1)]).fetchall()[0][0]


class TestCriticFindingsOn170:
    """delivery-critic on REQ-PIPE-170 (post-build-review #148). Each failed
    before its fix."""

    def test_d1_a_correction_on_several_owners_is_one_correction(self, conn, manager):
        """The gate makes each changed item be declared on its own owner, so
        one change reference can span a calendar and a dataset."""
        def both(cal, asset):
            _move_q3(cal, asset)
            _grace(cal, asset)
        late = RECEIVED + timedelta(days=100)
        docs = _corrected(both)
        found = correction_apply.pending(conn, docs)
        assert [p.reference for p in found] == ["CAB-1"], "listed once"
        [p] = found
        assert {k.split()[0] for k, _o, _n in p.changes} == {"calendar", "dataset"}
        assert len(correction_apply.affected_datasets(p, docs[0])) > 1
        del late

    def test_d1_every_owners_part_is_applied(self, conn, manager):
        """CAB-1 moves 2023-Q3's date (the calendar's part) and shortens
        cp-clients' grace (the dataset's part): both are applied."""
        _file("d1-g", "2023-Q2", datetime(2023, 5, 1, 12, tzinfo=PERTH))

        def both(cal, asset):
            _move_q3(cal, asset)
            _grace(cal, asset)
        docs = _corrected(both)
        done = correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT,
                                        docs=docs)
        assert (DATASET, SUPPLY, "2023-Q3", "2023-Q2") in done.moved, "the calendar's part"
        assert ("d1-g", "late") in {(s, new) for _d, s, _slot, _old, new in done.rejudged}, \
            "the dataset's part"
        assert correction_apply.pending(conn, docs) == []

    def test_d2_holding_a_promoted_supply_empties_its_period(self, conn, manager):
        workers = "cp-case-workers"
        _workers_file("cp-case-workers@d2h0000001", "2023-Q3", RECEIVED)
        _promote(conn, workers, "cp-case-workers@d2h0000001", "2023-Q3")
        docs = _corrected(_move_q3)
        correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT, docs=docs)
        assert decision_log.promoted_into(conn, workers, "2023-Q3") is None

    def test_d3_keeping_a_held_supply_keeps_it_held(self, conn, manager):
        filing_support.file(assignment.Assignment(
            dataset_id=DATASET, supply_id="d3-h", slot=None, branch=assignment.HELD,
            considered=(), received_at=RECEIVED + timedelta(minutes=5)))
        supply_holds.raise_hold(conn, dataset_id=DATASET, supply_id="d3-h",
                                kind=supply_holds.ASSIGNMENT_RULE, reason={"unavailable": []},
                                raised_by="t")
        docs = _corrected(_move_q3)
        correction_apply.confirm(conn, "CAB-1", actor=manager, keep={(DATASET, "d3-h")},
                                 keep_reason="not sure what it is", effective_at=AT, docs=docs)
        assert filing.filing_for(DATASET, "d3-h")["slot"] is None
        assert [h for h in supply_holds.outstanding(conn) if h.supply_id == "d3-h"], \
            "its hold is still open"
        [(to_slot,)] = conn.execute(
            f"SELECT to_slot FROM {decision_log.TABLE} WHERE supply = 'd3-h' AND action = 'keep'"
        ).fetchall()
        assert to_slot is None, "it was kept held, not kept in the period it was not placed in"

    def test_d4_a_supply_held_before_is_held_again(self, conn, manager):
        workers = "cp-case-workers"
        _workers_file("cp-case-workers@d4h0000001", "2023-Q3", RECEIVED)
        did = _promote(conn, workers, "cp-case-workers@d4h0000001", "2023-Q3")
        conn.execute(f"INSERT INTO {supply_holds.TABLE} (dataset_id, supply_id, kind, reason, "
                     "raised_by, resolved_by, resolved_at) VALUES (?, 'cp-case-workers@d4h0000001', ?, '{}', "
                     "'earlier', ?, now())", [workers, supply_holds.ASSIGNMENT_RULE, did])
        docs = _corrected(_move_q3)
        correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT, docs=docs)
        [hold] = [h for h in supply_holds.outstanding(conn) if h.supply_id == "cp-case-workers@d4h0000001"]
        assert hold.correction == "CAB-1"

    def test_d5_a_kept_supply_is_not_barred_from_the_gate(self, conn, manager):
        from qa_tools.common import rejection

        docs = _corrected(_move_q3)
        correction_apply.confirm(conn, "CAB-1", actor=manager, keep={(DATASET, SUPPLY)},
                                 keep_reason="really Q3", effective_at=AT, docs=docs)
        assert not rejection.decided_by_a_person(conn, DATASET, SUPPLY)

    def test_d6_what_a_kept_supply_would_become_is_shown_and_keyed(self, conn):
        docs = _corrected(_move_q3)
        _p, t = correction_apply.trial_for(conn, "CAB-1", docs=docs)
        [m] = [m for m in t.moves if m.supply_id == SUPPLY]
        assert m.if_kept is not None, "its verdict if kept is worked out"
        text = correction_trial_report(t)
        assert "if kept" in text

    def test_d8_the_applied_summary_says_what_was_done(self, conn, manager):
        docs = _corrected(_move_q3)
        p, t = correction_apply.trial_for(conn, "CAB-1", docs=docs)
        done = correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT,
                                        docs=docs)
        text = correction_apply.summary(p, t, done, as_at=datetime.now(PERTH), database="d")
        assert "Nothing was recorded" not in text and "would move" not in text
        assert "## Supplies moved or held" in text

    def test_d9_every_resolver_reads_this_corrections_agreement(self):
        """The re-file and its plan resolve slots through agreement.current(),
        the files on disk - which hold every merged correction, a later
        pending one included. Inside configured() they read the state given."""
        from qa_tools.common import agreement as agreement_mod, correction_trial, slots

        cal, asset = _docs()
        _move_q3(cal, asset, "2023-10-20")
        on_disk = agreement_mod.current()
        with correction_trial.configured(cal, asset):
            assert slots.slot_named(DATASET, "2023-Q3").date.isoformat() == "2023-10-20"
        assert agreement_mod.current() is on_disk, "restored afterwards"

    def test_l3_an_applied_reference_says_where_it_is_recorded(self, conn, manager):
        docs = _corrected(_move_q3)
        correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT, docs=docs)
        with pytest.raises(correction_apply.NotPending, match="applied"):
            correction_apply.trial_for(conn, "CAB-1", docs=docs)
        try:
            correction_apply.trial_for(conn, "CAB-1", docs=docs)
        except correction_apply.NotPending as exc:
            assert "decision history" not in str(exc)


def correction_trial_report(t):
    from qa_tools.common import correction_trial

    return correction_trial.report(t, as_at=datetime.now(PERTH), database="d", against="r")
