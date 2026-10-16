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
        c.execute(f'TRUNCATE "{qa_store.SCHEMA}".correction_parked CASCADE')
        _file(SUPPLY, "2023-Q3", RECEIVED)
        yield c
        # LEFT EMPTY FOR THE NEXT MODULE ON THIS WORKER: the activity feed
        # reads every applied correction, so one left behind here appeared in
        # tests/test_embed_dashboard_data.py's feed.
        c.execute(f'TRUNCATE "{qa_store.SCHEMA}".correction_applied')
        c.execute(f'TRUNCATE "{qa_store.SCHEMA}".correction_parked CASCADE')


@pytest.fixture
def manager():
    found = people.asset_managers()
    assert found, "contract/people.yaml names an asset manager"
    return found[0]


def _file(supply, slot, received):
    filing_support.file(assignment.Assignment(
        dataset_id=DATASET, supply_id=supply, slot=slot, branch=assignment.OPEN_UNFILLED,
        considered=(slot,), received_at=received))


def _pair_id(minutes: int) -> str:
    return f"{DATASET}@{asset_time.arrival_key(RECEIVED + timedelta(minutes=minutes))}#1"


def _pair(minutes: int) -> str:
    """A contested pair's `#1`, filed to 2023-Q3: two files of one delivery
    for one table, so its contest is OPEN (REQ-PIPE-194 criteria 8 and 9) -
    a `#` in the id alone is not a contest."""
    at = RECEIVED + timedelta(minutes=minutes)
    pair = _pair_id(minutes)
    _file(pair, "2023-Q3", at)
    filing_support.ensure_delivery(f"pytest-{DATASET}-{pair}", DATASET, at,
                                   filename="cp_clients_v2.csv")
    return pair


def _docs():
    """The committed files with no corrections declared - the ones the real
    contract carries (REQ-PIPE-181's migration, for one) are not this
    module's subject, and would read as pending beside its own."""
    # THE CONFIGURATION AS IT STOOD BEFORE REQ-GEN-207's GROWTH: these cases
    # edit the version that governs the judged supplies (tests/before_growth.py).
    from tests import before_growth

    cal = before_growth.calendar(copy.deepcopy(yaml.safe_load(agreement.CALENDAR_YAML.read_text())))
    asset = before_growth.asset(copy.deepcopy(yaml.safe_load(asset_time.DATA_ASSET_YAML.read_text())))
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

    def test_a_move_is_the_rules_re_file_naming_the_correction(self, conn, manager):
        """The rule's since Keith's answer (o), 2026-10-11 - naming who
        confirmed it."""
        docs = _corrected(_move_q3)
        done = correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT,
                                        docs=docs)
        assert [(s, a, b) for _d, s, a, b in done.moved] == [(SUPPLY, "2023-Q3", "2023-Q2")]
        assert _current(conn)["slot"] == "2023-Q2"
        [(actor, kind, reason)] = conn.execute(
            f"SELECT actor, actor_kind, reason FROM {decision_log.TABLE} WHERE supply = ? "
            "AND action = 'refile' ORDER BY id DESC LIMIT 1", [SUPPLY]).fetchall()
        assert kind == "rule" and "CAB-1" in reason and manager["email"] in reason
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

    def test_a_blocked_move_may_still_be_kept_at_confirmation(self, conn, manager):
        apply_c_pair = _pair(1)
        docs = _corrected(_move_q3)
        done = correction_apply.confirm(
            conn, "CAB-1", actor=manager, keep={(DATASET, apply_c_pair)},
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
    # NEITHER RE-FILE NOR PROMOTE (post-build-review #173): it has no period
    # to leave, and its data was never checked against one.
    assert all("re-file" not in r and "promote" not in r for r in held.responses)


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
        ts61_pair = _pair(9)
        docs = _corrected(_move_q3)
        _p, t = correction_apply.trial_for(conn, "CAB-1", docs=docs)
        [m] = [m for m in t.moves if m.supply_id == ts61_pair]
        assert m.blocked and "contested" in m.blocked
        done = correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT,
                                        docs=docs)
        # PARKED, NOT REFUSED (Keith, 2026-10-11, (p)): the rest is confirmed
        # and the blocked move waits on the outstanding list.
        assert [x[1] for x in done.parked] == [ts61_pair]
        assert not correction_apply.pending(conn, docs)
        assert [x.supply_id for x in correction_apply.parked(conn)] == [ts61_pair]
        assert filing.filing_for(DATASET, ts61_pair)["slot"] == "2023-Q3", "not moved"

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


class TestKeithsAnswerO:
    """Keith, 2026-10-11 (morning-report (o)): a confirmed correction's moves
    and holds are the RULE's, naming who confirmed them - so a later
    correction may move them again; the rule never overrides a person."""

    def _decision(self, conn, supply):
        return conn.execute(
            f"SELECT actor_kind, reason FROM {decision_log.TABLE} WHERE supply = ? "
            "AND action = 'refile' ORDER BY id DESC LIMIT 1", [supply]).fetchall()[0]

    def test_a_move_is_the_rules_and_names_the_confirmer(self, conn, manager):
        _file("o-move", "2023-Q2", datetime(2023, 7, 10, 12, tzinfo=PERTH))
        docs = _corrected(_claim_window(28))
        correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT, docs=docs)
        kind, reason = self._decision(conn, "o-move")
        assert kind == decision_log.RULE and manager["email"] in reason and "CAB-1" in reason

    def test_a_hold_is_the_rules_and_names_the_confirmer(self, conn, manager):
        _workers_file("o-hold", "2023-Q3", datetime(2023, 7, 25, 12, tzinfo=PERTH))
        docs = _corrected(_claim_window(1))
        correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT, docs=docs)
        kind, reason = self._decision(conn, "o-hold")
        assert kind == decision_log.RULE and manager["email"] in reason


def _reject(conn, supply=SUPPLY):
    with decision_log.apply_decision(conn, decision_log.Decision(
            agency_id="child-protection-family-support", collection_id="child-protection",
            dataset_id=DATASET, action=decision_log.REJECT, supply=supply,
            actor="somebody", actor_kind=decision_log.PERSON,
            effective_at="2023-08-02T09:00:00+08:00", to_slot="2023-Q3",
            reason="bad file")):
        pass


class TestParkedMoves:
    """Keith, 2026-10-11, (p): confirm what can move, park a blocked move on
    the outstanding list until its blocker clears, then move it - to the
    period confirmed - or keep it, with a reason. Each failed before."""

    def test_the_rest_is_confirmed_and_the_blocked_one_parked(self, conn, manager):
        park_c_pair = _pair(1)
        docs = _corrected(_move_q3)
        done = correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT,
                                        docs=docs)
        assert SUPPLY in {s for _d, s, *_ in done.moved}
        [(ds, supply, frm, to, why)] = done.parked
        assert (ds, supply, frm) == (DATASET, park_c_pair, "2023-Q3") and "contested" in why
        [parked] = correction_apply.parked(conn)
        assert parked.reference == "CAB-1" and parked.to_period == to
        assert parked.confirmed_by == manager["email"]
        record = json.loads(conn.execute(
            f"SELECT summary::text FROM {correction_apply.APPLIED}").fetchall()[0][0])
        assert record["parked"][0][1] == park_c_pair

    def test_it_moves_to_the_period_confirmed_once_the_blocker_clears(self, conn, manager):
        _file("park-m", "2023-Q3", RECEIVED + timedelta(minutes=6))
        _reject(conn, "park-m")
        docs = _corrected(_move_q3)
        done = correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT,
                                        docs=docs)
        [(_ds, _s, _frm, to, why)] = done.parked
        assert "rejected" in why
        assert correction_apply.drain_parked(conn, docs=docs, say=lambda _m: None) == []
        assert _current(conn, "park-m")["slot"] == "2023-Q3", "still blocked, still where it was"
        _promote(conn, DATASET, "park-m", "2023-Q3")   # the rejection reversed
        moved = correction_apply.drain_parked(conn, docs=docs, say=lambda _m: None)
        assert moved == [(DATASET, "park-m", "2023-Q3", to)]
        assert _current(conn, "park-m")["slot"] == to
        assert correction_apply.parked(conn) == []
        reason, actor_kind = conn.execute(
            f"SELECT reason, actor_kind FROM {decision_log.TABLE} WHERE supply = ? "
            "AND action = 'refile' ORDER BY id DESC LIMIT 1", ["park-m"]).fetchall()[0]
        assert "CAB-1" in reason and manager["email"] in reason and actor_kind == "rule"

    def test_a_refused_dataset_is_left_parked(self, conn, manager):
        # ITS OWN SUPPLY: the decision log is not emptied between tests, so
        # another test's promotion of SUPPLY would read as this one's
        # un-rejection.
        _file("park-f", "2023-Q3", RECEIVED + timedelta(minutes=5))
        _reject(conn, "park-f")
        docs = _corrected(_move_q3)
        correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT, docs=docs)
        assert [x.supply_id for x in correction_apply.parked(conn)] == ["park-f"]
        _promote(conn, DATASET, "park-f", "2023-Q3")
        assert correction_apply.drain_parked(conn, docs=docs, skip=frozenset({DATASET}),
                                             say=lambda _m: None) == []
        assert len(correction_apply.parked(conn)) == 1

    def test_the_manager_may_keep_it_instead_with_a_reason(self, conn, manager):
        park_k_pair = _pair(2)
        docs = _corrected(_move_q3)
        correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT, docs=docs)
        with pytest.raises(decision_log.DecisionRefused, match="needs a reason"):
            correction_apply.keep_parked(conn, "CAB-1", DATASET, park_k_pair, actor=manager,
                                         reason=" ", effective_at=AT)
        correction_apply.keep_parked(conn, "CAB-1", DATASET, park_k_pair, actor=manager,
                                     reason="deciding the contest separately",
                                     effective_at=AT)
        assert correction_apply.parked(conn) == []
        reason = conn.execute(
            f"SELECT reason FROM {decision_log.TABLE} WHERE supply = ? AND action = ?",
            [park_k_pair, decision_log.KEEP]).fetchall()[0][0]
        assert "CAB-1" in reason and "deciding the contest separately" in reason
        with pytest.raises(decision_log.DecisionRefused, match="no parked move"):
            correction_apply.keep_parked(conn, "CAB-1", DATASET, park_k_pair, actor=manager,
                                         reason="again", effective_at=AT)

    def test_only_the_asset_manager_keeps_one(self, conn, manager):
        park_r_pair = _pair(3)
        docs = _corrected(_move_q3)
        correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT, docs=docs)
        nobody = {"email": "not-a-manager@example.org", "name": "Nobody"}
        with pytest.raises(people.RoleRefused):
            correction_apply.keep_parked(conn, "CAB-1", DATASET, park_r_pair, actor=nobody,
                                         reason="r", effective_at=AT)

    def test_each_parked_move_is_an_outstanding_item(self, conn, manager):
        from qa_tools.common import outstanding

        park_o_pair = _pair(4)
        docs = _corrected(_move_q3)
        correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT, docs=docs)
        [item] = outstanding._from_parked_corrections(conn)
        assert item.kind == outstanding.PARKED_CORRECTION_MOVE
        assert "CAB-1" in item.headline and park_o_pair in item.headline
        assert any("contested" in r for r in item.responses)
        assert any(f"--keep {park_o_pair}" in r for r in item.responses)


class TestParkedMovesOnEveryRoute:
    """Keith, 2026-10-11, (p): parked moves are listed by `mothman supply
    corrections`, kept through confirm-correction --keep on the confirmed
    reference, and reached from the filing menu. Each failed before."""

    @pytest.fixture
    def parked_one(self, conn, manager, monkeypatch):
        from qa_tools.common import correction_trial

        _pair(7)
        docs = _corrected(_move_q3)
        monkeypatch.setattr(correction_trial, "working", lambda: docs)
        correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT, docs=docs)
        return docs

    def _run(self, *args):
        from click.testing import CliRunner

        from cli import supply as supply_cli
        return CliRunner().invoke(supply_cli.supply_group, list(args))

    def test_corrections_lists_what_is_parked(self, conn, parked_one):
        got = self._run("corrections")
        assert got.exit_code == 0, got.output
        assert "parked" in got.output and _pair_id(7) in got.output
        assert "No corrections are waiting" not in got.output

    def test_the_confirmed_reference_takes_keep(self, conn, parked_one, monkeypatch, manager):
        from cli import filing_tui

        monkeypatch.setattr(filing_tui, "actor_at_the_keyboard", lambda: manager)
        got = self._run("confirm-correction", "--reference", "CAB-1", "--keep", _pair_id(7),
                        "--keep-reason", "deciding it separately", "--yes")
        assert got.exit_code == 0, got.output
        assert correction_apply.parked(conn) == []

    def test_without_keep_it_says_they_go_ahead_on_their_own(
            self, conn, parked_one, monkeypatch, manager):
        from cli import filing_tui

        monkeypatch.setattr(filing_tui, "actor_at_the_keyboard", lambda: manager)
        got = self._run("confirm-correction", "--reference", "CAB-1")
        assert got.exit_code != 0 and "already confirmed" in got.output
        assert "--keep" in got.output

    def test_the_filing_menu_offers_them(self, conn, parked_one, monkeypatch, manager):
        from cli import common, filing_tui

        monkeypatch.setattr(filing_tui, "actor_at_the_keyboard", lambda: manager)
        asked = []
        picks = iter([filing_tui._MENU_PARKED, f"Keep cp-clients {_pair_id(7)}"])

        def select(message, choices, **k):
            asked.append(list(choices))
            want = next(picks)
            return next(c for c in choices if c.startswith(want))
        monkeypatch.setattr(common, "select", select)
        monkeypatch.setattr(common, "text_prompt", lambda *a, **k: "kept from the menu")
        monkeypatch.setattr(common, "confirm_change", lambda *a, **k: True)
        filing_tui.filing_menu()
        assert any(c.startswith(filing_tui._MENU_PARKED) for c in asked[0])
        assert correction_apply.parked(conn) == []


def _park(conn, supply, frm, to, reference="CAB-1", blocked="it was rejected"):
    conn.execute(
        f"INSERT INTO {correction_apply.PARKED} (change_reference, dataset_id, supply_id, "
        "from_period, to_period, blocked, confirmed_by, parked_at) VALUES "
        "(?, ?, ?, ?, ?, ?, ?, ?)",
        [reference, DATASET, supply, frm, to, blocked, "fpycnkgvmt@privaterelay.appleid.com",
         AT])


class TestCriticFindingsOn152:
    """delivery-critic on the parked moves (post-build-review #152). Each
    failed before its fix."""

    def test_1_one_move_that_cannot_go_ahead_holds_back_no_other(self, conn):
        _file("c1-a", "2023-Q3", RECEIVED + timedelta(minutes=11))
        _file("c1-b", "2023-Q3", RECEIVED + timedelta(minutes=12))
        _park(conn, "c1-a", "2023-Q3", "2023-Q9")
        _park(conn, "c1-b", "2023-Q3", "2023-Q2")
        said = []
        moved = correction_apply.drain_parked(conn, docs=_docs(), say=said.append)
        assert moved == [(DATASET, "c1-b", "2023-Q3", "2023-Q2")]
        assert [p.supply_id for p in correction_apply.parked(conn)] == ["c1-a"]
        assert any("c1-a" in s and "2023-Q9" in s for s in said)

    def test_2_a_held_supply_is_never_placed_into_a_period_that_does_not_exist(self, conn):
        filing_support.file(assignment.Assignment(
            dataset_id=DATASET, supply_id="c2-h", slot=None, branch=assignment.HELD,
            considered=(), received_at=RECEIVED + timedelta(minutes=13)))
        _park(conn, "c2-h", None, "2023-Q9")
        correction_apply.drain_parked(conn, docs=_docs(), say=lambda _m: None)
        assert _current(conn, "c2-h")["slot"] is None
        assert [p.supply_id for p in correction_apply.parked(conn)] == ["c2-h"]

    def test_7_a_parked_move_is_carried_out_under_the_agreement_as_at_confirmation(
            self, conn, monkeypatch):
        """Keith, 2026-10-11: as confirm() does, every later correction not
        yet confirmed is reverted - here CAB-2, which shortens the grace."""
        from qa_tools.common import correction_trial
        from test_correction_replay import _declare

        docs = _declare(_docs(), _grace, "CAB-2", "2026-01-01")
        _file("c7", "2023-Q3", RECEIVED + timedelta(minutes=14))
        _park(conn, "c7", "2023-Q3", "2023-Q2")
        seen = []
        real = correction_trial.configured

        def configured(cal, asset):
            seen.append(_clients(copy.deepcopy(cal))["participation"]["versions"][0]
                        .get("grace"))
            return real(cal, asset)
        monkeypatch.setattr(correction_trial, "configured", configured)
        correction_apply.drain_parked(conn, docs=docs, say=lambda _m: None)
        assert seen and seen[0] != "1h", "CAB-2 is reverted while it waits"

    def test_4_one_a_person_moved_meanwhile_says_so_and_is_kept_where_it_is(
            self, conn, manager):
        from qa_tools.common import outstanding

        _file("c4", "2023-Q3", RECEIVED + timedelta(minutes=15))
        _park(conn, "c4", "2023-Q3", "2023-Q2")
        filing.refile(conn, DATASET, "c4", "2023-Q4", decision_id=1)
        [item] = [i for i in outstanding._from_parked_corrections(conn) if "c4" in i.headline]
        assert "2023-Q4" in item.headline and "the next processing pass" not in item.detail
        correction_apply.keep_parked(conn, "CAB-1", DATASET, "c4", actor=manager,
                                     reason="leave it", effective_at=AT)
        to_slot = conn.execute(
            f"SELECT to_slot FROM {decision_log.TABLE} WHERE supply = 'c4' AND action = ?",
            [decision_log.KEEP]).fetchall()[0][0]
        assert to_slot == "2023-Q4"

    def test_9_the_move_resolves_with_its_own_decision(self, conn):
        _file("c9", "2023-Q3", RECEIVED + timedelta(minutes=16))
        _park(conn, "c9", "2023-Q3", "2023-Q2")
        correction_apply.drain_parked(conn, docs=_docs(), say=lambda _m: None)
        resolved = conn.execute(
            f"SELECT decision_id FROM {correction_apply.RESOLVED}").fetchall()[0][0]
        action, supply = conn.execute(
            f"SELECT action, supply FROM {decision_log.TABLE} WHERE id = ?",
            [resolved]).fetchall()[0]
        assert (action, supply) == (decision_log.REFILE, "c9")

    def test_10_keeping_several_is_all_or_nothing(self, conn, manager, monkeypatch):
        from cli import supply as supply_cli

        _file("c10-a", "2023-Q3", RECEIVED + timedelta(minutes=17))
        _file("c10-b", "2023-Q3", RECEIVED + timedelta(minutes=18))
        _park(conn, "c10-a", "2023-Q3", "2023-Q2")
        _park(conn, "c10-b", "2023-Q3", "2023-Q2")
        real = correction_apply.keep_parked

        def keep(conn_, reference, ds, supply, **kw):
            if supply == "c10-b":
                raise decision_log.DecisionRefused("no")
            return real(conn_, reference, ds, supply, **kw)
        monkeypatch.setattr(correction_apply, "keep_parked", keep)
        import click
        with pytest.raises(click.ClickException):
            supply_cli.keep_parked_moves(conn, "CAB-1", ("c10-a", "c10-b"), "r",
                                         actor=manager, yes=True)
        assert {p.supply_id for p in correction_apply.parked(conn)} == {"c10-a", "c10-b"}


class TestCriticFindingsOn152TheCommand:
    def _run(self, *args):
        from click.testing import CliRunner

        from cli import supply as supply_cli
        return CliRunner().invoke(supply_cli.supply_group, list(args))

    def test_5_an_applied_reference_shows_its_parked_moves(self, conn, manager, monkeypatch):
        from qa_tools.common import correction_trial
        from test_correction_replay import _declare

        c5_pair = _pair(19)
        docs = _corrected(_move_q3)
        correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT, docs=docs)
        later = _declare(docs, _grace, "CAB-2", asset_time.local_date(
            asset_time.now()).isoformat())
        monkeypatch.setattr(correction_trial, "working", lambda: later)
        got = self._run("corrections", "--reference", "CAB-1")
        assert got.exit_code == 0, got.output
        assert c5_pair in got.output

    def test_5_an_unknown_reference_is_refused_even_with_nothing_pending(
            self, conn, manager, monkeypatch):
        from qa_tools.common import correction_trial

        _pair(20)
        docs = _corrected(_move_q3)
        correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT, docs=docs)
        monkeypatch.setattr(correction_trial, "working", lambda: docs)
        got = self._run("corrections", "--reference", "BOGUS")
        assert got.exit_code != 0 and "BOGUS" in got.output


class TestATurnOffDeclaredAsACorrection:
    """REQ-PIPE-179 criteria 35-37: a correction that turns cp-clients off
    after 30 June 2023, so its 2023-Q3 supply sits in a period the corrected
    agreement owes nothing in."""

    @staticmethod
    def _off(cal, asset, to="2023-06-30"):
        v = _clients(cal)["participation"]["versions"][0]
        v.update(effective_to=to, turned_off_reason="supplier paused")

    def test_the_supply_left_in_the_gap_is_held_as_turned_off(self, conn, manager):
        """Criterion 35."""
        from qa_tools.common import correction_trial

        docs = _corrected(self._off)
        done = correction_apply.confirm(conn, "CAB-1", actor=manager, effective_at=AT,
                                        docs=docs)
        assert [s for _d, s, *_ in done.held] == [SUPPLY]
        with correction_trial.configured(*docs):
            held = supply_holds.hold_on(conn, DATASET, SUPPLY)
            assert held.turned_off and "supplier paused" in held.describe()

    def test_it_cannot_be_kept_there(self, conn, manager):
        """Criterion 36: keep is not offered."""
        from qa_tools.common import correction_trial

        docs = _corrected(self._off)
        [p] = correction_apply.pending(conn, docs)
        base, work = correction_apply.states(p, [p], docs)
        t = correction_trial.trial(conn, base, work, dataset_ids=[DATASET])
        [m] = [m for m in t.moves if m.supply_id == SUPPLY]
        assert m.keep_refused and "2023-Q3 no longer owes a supply" in m.keep_refused
        why = correction_apply.why_not_confirmable(t, {(DATASET, SUPPLY)}, "it is Q3 data")
        assert why and "cannot be kept" in why
        assert "it cannot be kept" in correction_trial.report(
            t, as_at=datetime(2026, 10, 14, tzinfo=PERTH), database="d", against="a")

    def test_a_parked_move_into_a_gap_stays_parked(self, conn):
        """Criterion 37: said, naming the gap and what ends it."""
        _file("g1", "2023-Q3", RECEIVED + timedelta(minutes=21))
        _park(conn, "g1", "2023-Q3", "2023-Q4")
        # IN FORCE, not a pending correction - the drain reverts those.
        cal, asset = _docs()
        versions = _clients(cal)["participation"]["versions"]
        versions.append({**{k: v for k, v in versions[0].items() if k != "changelog"},
                         "effective_from": "2024-01-01",
                         "changelog": [{"date": "2026-10-14", "author": "a", "change": "on"}]})
        self._off(cal, asset, to="2023-09-30")
        docs = (cal, asset)
        said = []
        assert correction_apply.drain_parked(conn, docs=docs, say=said.append) == []
        assert [p.supply_id for p in correction_apply.parked(conn)] == ["g1"]
        [line] = [s for s in said if "g1" in s]
        assert "turned off" in line and "supplier paused" in line
        assert "effective_to or effective_from" in line and "stays parked" in line


class TestCriticFindingsOn190:
    """delivery-critic on REQ-PIPE-179 (post-build-review #190), D5 and D6:
    keep is never offered where it would be refused, and a parked move into
    a gap names the gap. Each failed before its fix."""

    @staticmethod
    def _gap_then_back(cal, asset):
        """cp-clients off after 30 June 2023, back on 1 October 2023 - so
        2023-Q3 owes nothing and 2023-Q4 is owed."""
        versions = _clients(cal)["participation"]["versions"]
        versions.append({**{k: v for k, v in versions[0].items() if k != "changelog"},
                         "effective_from": "2023-10-01",
                         "changelog": [{"date": "2026-10-14", "author": "a", "change": "on"}]})
        versions[0].update(effective_to="2023-06-30", turned_off_reason="supplier paused")

    def _parked_in_the_gap(self, conn, supply, minutes):
        from qa_tools.common import correction_trial

        _file(supply, "2023-Q3", RECEIVED + timedelta(minutes=minutes))
        _park(conn, supply, "2023-Q3", "2023-Q4")
        cal, asset = _docs()
        self._gap_then_back(cal, asset)
        return correction_trial.configured(cal, asset)

    def test_d5_a_parked_supply_in_a_gap_is_refused_a_keep(self, conn, manager):
        with self._parked_in_the_gap(conn, "d5-a", 31):
            with pytest.raises(decision_log.DecisionRefused, match="cannot be kept in 2023-Q3"):
                correction_apply.keep_parked(conn, "CAB-1", DATASET, "d5-a", actor=manager,
                                             reason="r", effective_at=AT)

    def test_d5_the_outstanding_item_does_not_offer_the_keep(self, conn):
        from qa_tools.common import outstanding

        with self._parked_in_the_gap(conn, "d5-b", 32):
            [item] = [i for i in outstanding._from_parked_corrections(conn)
                      if "d5-b" in i.headline]
        assert not any("--keep" in r for r in item.responses)
        assert "cannot be kept" in item.detail

    def test_d5_the_terminal_offers_no_keep_for_it(self, conn):
        from cli import filing_tui

        with self._parked_in_the_gap(conn, "d5-c", 33):
            parked = [p for p in correction_apply.parked(conn) if p.supply_id == "d5-c"]
            assert filing_tui._parked_keep_choices(parked) == {}

    def test_d5_the_confirm_menu_offers_no_keep_where_it_is_refused(self, conn):
        from cli import filing_tui
        from qa_tools.common import correction_trial

        docs = _corrected(TestATurnOffDeclaredAsACorrection._off)
        [p] = correction_apply.pending(conn, docs)
        base, work = correction_apply.states(p, [p], docs)
        t = correction_trial.trial(conn, base, work, dataset_ids=[DATASET])
        refused = [m for m in t.moves if m.keep_refused]
        assert refused, "precondition - the trial has a move that cannot be kept"
        offered = set(filing_tui._keep_choices(t.moves).values())
        assert not offered & {(m.dataset_id, m.supply_id) for m in refused}

    def test_d6_a_parked_move_into_a_gap_names_the_gap(self, conn):
        from qa_tools.common import correction_trial, outstanding

        _file("d6-a", "2023-Q3", RECEIVED + timedelta(minutes=34))
        _park(conn, "d6-a", "2023-Q3", "2023-Q4")
        cal, asset = _docs()
        _clients(cal)["participation"]["versions"][0].update(
            effective_to="2023-09-30", turned_off_reason="supplier paused")
        with correction_trial.configured(cal, asset):
            [item] = [i for i in outstanding._from_parked_corrections(conn)
                      if "d6-a" in i.headline]
        assert "turned off" in item.detail and "supplier paused" in item.detail
        assert "next processing pass moves it" not in item.detail
