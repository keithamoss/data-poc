"""A bulk re-check (REQ-PIPE-177): every supply a fixed check judged under an
old definition, re-checked in one action.

Each test gets an EMPTY database of its own (dbsupport), so the only stale
fingerprints in it are the ones the test records - other tests on a worker
record results with attempt_support.ANY_CHECK's fixed fingerprint under real
check ids, which would otherwise be stale here too. Supplies are filed the
way test_supersession files them, and judged by a completed run whose result
carries the fingerprint the test names.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

import attempt_support
import dbsupport
from qa_tools.common import agreement_drift, qa_store, recheck, supply_db
from qa_tools.common import bulk_recheck as bulk
from qa_tools.common import decision_log as dl
from qa_tools.common import filing_decisions as fd
from test_supersession import DS, REAL_PERSON, WHEN, _filed

AG, COL = "child-protection-family-support", "child-protection"
CHECK = "data-asset-1.child-protection-family-support.child-protection.cp-carers.row_count_soda"
OTHER = ("data-asset-1.child-protection-family-support.child-protection.cp-carers.carer_id."
         "missing_count_soda")
STALE = "v1:" + "a" * 64


@pytest.fixture
def conn(monkeypatch):
    dbsupport.use_empty_supply_db(monkeypatch)
    # No backstop unless a test asks for one: filings into invented periods
    # read as a moved judged past.
    monkeypatch.setattr(agreement_drift, "refusals", lambda *a, **k: {})
    with supply_db.connect(label="test-bulk-recheck") as c:
        qa_store.ensure_schema(c)
        yield c


def current(check_id=CHECK) -> str:
    return bulk.current_checks()[check_id].config_hash


def judged(conn, supply, fingerprint, *, check=CHECK, status="pass"):
    """A completed arrival run of `supply` with one result for `check`."""
    key = f"pytest_bulk_{uuid.uuid4().hex[:10]}"
    qa_store.record_run(conn, run_key=key, agency_id=AG, collection_id=COL,
                        run_timestamp=WHEN, run_by=REAL_PERSON, environment="sandbox")
    qa_store.set_run_purpose(conn, key, dataset_id=DS, supply_id=supply)
    qa_store.record_results(conn, key, [{"dataset_id": DS, "check_id": check,
                                         "status": status}],
                            tool=check.rsplit("_", 1)[-1], agency_id=AG, collection_id=COL,
                            fingerprints={check: fingerprint})
    attempt_support.opened(conn, key)
    qa_store.complete_run(conn, key)
    return key


def filed(conn, period=None, fingerprint=STALE, **kw):
    period = period or f"2099-S{uuid.uuid4().hex[:6]}"
    supply, _ = _filed(conn, period, WHEN)
    judged(conn, supply, fingerprint, **kw)
    return supply, period


def actor():
    return {"email": REAL_PERSON}


# ---- criterion 2: which supplies ------------------------------------------------

class TestWhichSuppliesAreCovered:
    def test_a_waiting_supply_whose_newest_result_is_stale_is_covered(self, conn):
        supply, period = filed(conn)
        p = bulk.plan(conn, CHECK)
        assert [(c.supply, c.period, c.state, c.stale) for c in p.covered] == [
            (supply, period, "waiting", STALE)]

    def test_a_supply_whose_newest_result_is_current_is_not(self, conn):
        filed(conn, fingerprint=current())
        assert bulk.plan(conn, CHECK).covered == []

    def test_the_newest_result_decides_not_an_older_stale_one(self, conn):
        supply, _ = filed(conn)
        judged(conn, supply, current())
        assert bulk.plan(conn, CHECK).covered == []

    def test_a_supply_with_no_result_for_the_check_is_never_selected(self, conn):
        _filed(conn, "2099-Snone", WHEN)
        supply, _ = filed(conn, check=OTHER)
        assert bulk.plan(conn, CHECK).covered == []
        assert [c.supply for c in bulk.plan(conn, OTHER).covered] == [supply]

    def test_a_promoted_supply_is_covered_and_counted_as_promoted(self, conn):
        from test_door_flag_parity import _promote

        supply, period = filed(conn)
        _promote(conn, supply, f"cp_carers__{supply.split('@')[1]}", period)
        p = bulk.plan(conn, CHECK)
        assert [(c.supply, c.state) for c in p.covered] == [(supply, "promoted")]
        assert p.promoted == 1

    def test_rejected_and_superseded_are_counted_not_covered(self, conn):
        """Criterion 33."""
        rejected, period = filed(conn)
        dl_reject(conn, rejected, period)
        p = bulk.plan(conn, CHECK)
        assert p.covered == []
        assert [(x.supply, x.why) for x in p.left_out] == [(rejected, "rejected")]
        text = "\n".join(_panel(p))
        assert "1 rejected and 0 superseded" in text
        assert "--operation promote" in text and "--operation un-supersede" in text

    def test_a_dataset_the_backstop_refuses_is_left_out_named_and_kept_in_the_nudge(
            self, conn, monkeypatch):
        """Criterion 28."""
        supply, _ = filed(conn)
        refusal = SimpleNamespace(message=lambda: f"{DS} is refused: ...\n  To fix: declare it.")
        monkeypatch.setattr(agreement_drift, "refusals", lambda *a, **k: {DS: refusal})
        p = bulk.plan(conn, CHECK)
        assert p.covered == [] and [x.why for x in p.left_out] == ["backstop"]
        text = "\n".join(_panel(p))
        assert f"{DS}'s 1 supply" in text and "To fix: declare it." in text
        assert [n.total for n in bulk.nudges(conn)] == [1]


class TestAnOpenPairIsLeftOut:
    def test_a_file_of_an_open_contested_pair_is_left_out_and_counted(self, conn, monkeypatch):
        """Criterion 27: its settlement checks it under the current definition."""
        supply, _ = filed(conn)
        from qa_tools.common import supply_files

        pair = supply_files.pair_supply(supply)
        monkeypatch.setattr(bulk, "_open_contests", lambda c: {(DS, pair): ("a.csv", "b.csv")})
        p = bulk.plan(conn, CHECK)
        assert p.covered == [] and [(x.why, x.files) for x in p.left_out] == [
            ("open-pair", ("a.csv", "b.csv"))]
        assert "1 file(s) of an open contested pair" in "\n".join(_panel(p))


def dl_reject(conn, supply, period):
    fd.apply(fd.Request(operation=fd.REJECT, dataset_id=DS, actor=actor(),
                        reason="wrong file", confirmed=True, period=period, supply=supply),
             effective_at=WHEN, conn=conn)


def _panel(p):
    from cli import bulk_recheck_tui

    return bulk_recheck_tui.panel_lines(p, flag_route=True)


# ---- criteria 3 to 5: refusals --------------------------------------------------

class TestRefusals:
    def test_no_supply_to_cover_is_refused_saying_why(self, conn):
        p = bulk.plan(conn, CHECK)
        assert "already checked under its current definition" in bulk.nothing_to_cover(p)

    def test_a_retired_check_is_refused(self, conn):
        retired = next((c for c in bulk.current_checks().values() if c.retired_as_of), None)
        assert retired is not None, "the tree holds a retired check to try"
        with pytest.raises(bulk.Refused, match="retired check's results no longer judge"):
            bulk.plan(conn, retired.check_id)

    def test_a_file_check_is_refused_with_the_reprocess_command_on_its_own_line(self, conn):
        file_check = next(c for c in bulk.current_checks().values() if c.tool == "file")
        with pytest.raises(bulk.Refused) as got:
            bulk.plan(conn, file_check.check_id)
        assert "file checks run only" in str(got.value)
        assert "\nmothman supply load --collection " in str(got.value)

    def test_an_unknown_check_is_refused(self, conn):
        with pytest.raises(bulk.Refused, match="No check has the id"):
            bulk.plan(conn, "no.such.check")


# ---- criterion 7: recording ------------------------------------------------------

class TestRecording:
    def test_one_transaction_one_decision_and_one_owed_per_supply_naming_the_check(self, conn):
        a, pa = filed(conn, period="2099-S0001")
        b, pb = filed(conn, period="2099-S0000")
        p = bulk.plan(conn, CHECK)
        got = bulk.record(conn, CHECK, actor=actor(), reason="row count was wrong",
                          effective_at=WHEN, acknowledged=p.key)
        rows = conn.execute(
            f"SELECT supply, to_slot, action, check_id, check_changelog_date, reason, "
            f"bulk_recheck FROM {dl.TABLE} WHERE bulk_recheck = ? ORDER BY id",
            [got.bulk_id]).fetchall()
        entry = bulk.changelog_entry(bulk.current_checks()[CHECK])
        # SORTED SLOT ORDER.
        assert [(r[0], r[1]) for r in rows] == [(b, pb), (a, pa)]
        assert {(r[2], r[3], r[4], r[5]) for r in rows} == {
            (dl.RECHECK, CHECK, entry and str(entry["date"]), "row count was wrong")}
        owed = {o.id: o for o in recheck.owed(conn)}
        assert set(got.owed) <= set(owed)
        assert sorted(owed[i].supply_id for i in got.owed) == sorted([a, b])
        (n, check, supplies) = conn.execute(f"SELECT count(*), max(check_id), max(supplies) "
                                            f"FROM {bulk.TABLE}").fetchone()
        assert (n, check, supplies) == (1, CHECK, 2)

    def test_a_changed_set_is_refused_and_nothing_is_recorded(self, conn):
        filed(conn)
        p = bulk.plan(conn, CHECK)
        filed(conn)
        with pytest.raises(bulk.Refused, match="has changed since it was shown"):
            bulk.record(conn, CHECK, actor=actor(), reason="x", effective_at=WHEN,
                        acknowledged=p.key)
        assert conn.execute(f"SELECT count(*) FROM {bulk.TABLE}").fetchone()[0] == 0
        assert conn.execute(f"SELECT count(*) FROM {dl.TABLE} WHERE action = ?",
                            [dl.RECHECK]).fetchone()[0] == 0

    def test_a_reason_is_required(self, conn):
        filed(conn)
        p = bulk.plan(conn, CHECK)
        with pytest.raises(bulk.Refused, match="needs a reason"):
            bulk.record(conn, CHECK, actor=actor(), reason=" ", effective_at=WHEN,
                        acknowledged=p.key)

    def test_the_key_changes_with_the_fingerprint(self, conn):
        filed(conn)
        p = bulk.plan(conn, CHECK)
        other = bulk.Plan(check=p.check, fingerprint="v1:" + "b" * 64, changelog=None,
                          covered=p.covered)
        assert p.key != other.key


# ---- criteria 8, 10, 14, 15, 17, 25: running ---------------------------------------

def _recorded(conn, n=2):
    for i in range(n):
        filed(conn, period=f"2099-S{i:04d}")
    p = bulk.plan(conn, CHECK)
    return p, bulk.record(conn, CHECK, actor=actor(), reason="fixed", effective_at=WHEN,
                          acknowledged=p.key)


class TestRunning:
    def test_each_supply_runs_its_own_owed_recheck_through_the_one_executor(
            self, conn, monkeypatch):
        _p, rec = _recorded(conn)
        ran = []
        monkeypatch.setattr(recheck, "run", lambda owed_id, **k: ran.append(owed_id) or
                            recheck.Outcome(owed_id, "r", True, "ok", status="amber"))
        from cli import bulk_recheck_tui

        s = bulk_recheck_tui.run_foreground(rec)
        assert ran == list(rec.owed)
        assert len(s.changed) == 0 or all(r.now == "amber" for r in s.changed)

    def test_a_failed_rerun_stays_owed_and_the_rest_run(self, conn, monkeypatch, capsys):
        _p, rec = _recorded(conn, 3)
        first = rec.owed[0]

        def run(owed_id, **k):
            if owed_id == first:
                return recheck.Outcome(owed_id, "", False, "dbt fell over")
            return recheck.Outcome(owed_id, "r", True, "ok", status="green")
        monkeypatch.setattr(recheck, "run", run)
        from cli import bulk_recheck_tui

        s = bulk_recheck_tui.run_foreground(rec)
        assert len(s.ran) == 3 and s.still_owed == 1
        out = capsys.readouterr().out
        assert "[1/3] re-checking cp-carers" in out and "[3/3]" in out
        assert "Ctrl-C stops it at any point" in out
        assert "mothman pipeline process" in out

    def test_ctrl_c_ends_with_a_summary_and_the_rest_owed(self, conn, monkeypatch, capsys):
        _p, rec = _recorded(conn, 3)
        calls = []

        def run(owed_id, **k):
            calls.append(owed_id)
            if len(calls) == 2:
                raise KeyboardInterrupt
            return recheck.Outcome(owed_id, "r", True, "ok", status="red")
        monkeypatch.setattr(recheck, "run", run)
        from cli import bulk_recheck_tui

        s = bulk_recheck_tui.run_foreground(rec)
        out = capsys.readouterr().out
        assert s.still_owed == 2 and "Traceback" not in out
        assert "still owed" in out and "\nmothman pipeline process" in out
        assert "now red, was" in out

    def test_the_summary_names_changes_and_never_says_rejected_or_refused(self):
        c = bulk.Covered(DS, "s1", "2099-S1", "promoted", "green", STALE)
        s = bulk.Summary(ran=[bulk.Ran(c, recheck.Outcome(1, "r", True, "x", status="red"),
                                       (CHECK,))])
        text = "\n".join(bulk.summary_lines(s))
        assert "1 verdict(s) changed, 0 stayed the same, 0 still owed." in text
        assert "now red, was green" in text and CHECK in text
        assert "Promoted, then re-checked red" in text
        assert "rejected" not in text.lower() and "refused" not in text.lower()

    def test_run_all_owed_takes_only_the_ids_it_is_given(self, conn, monkeypatch):
        _p, rec = _recorded(conn)
        ran = []
        monkeypatch.setattr(recheck, "run", lambda owed_id, **k: ran.append(owed_id) or
                            recheck.Outcome(owed_id, "r", True, "ok"))
        recheck.run_all_owed(kinds=(recheck.RECHECK,), ids=[rec.owed[1]])
        assert ran == [rec.owed[1]]

    def test_no_new_owed_item_is_started_after_the_deadline(self, conn, monkeypatch):
        """Criterion 24."""
        import time

        _recorded(conn)
        ran = []
        monkeypatch.setattr(recheck, "run", lambda owed_id, **k: ran.append(owed_id))
        assert recheck.run_all_owed(kinds=(recheck.RECHECK,),
                                    deadline=time.monotonic() - 1) == []
        assert ran == []

    def test_the_processing_pass_passes_its_deadline_to_the_owed_work(self, conn, monkeypatch):
        import time

        from qa_tools.common import processing_pass

        seen = {}

        def owed(**k):
            seen.update(k)
            return []
        monkeypatch.setattr(recheck, "run_all_owed", owed)
        deadline = time.monotonic() - 1
        processing_pass.run_pass(deadline=deadline, say=lambda *a, **k: None)
        assert seen.get("deadline") == deadline


# ---- criteria 13, 19, 20, 29: the nudge and the owed list --------------------------

class TestTheNudgeAndTheOwedList:
    def test_the_collections_line_and_the_other_collections(self):
        one = bulk.Nudge(CHECK, 5, {COL: 3, "civil-registration": 2}, "2026-10-01", "fixed")
        assert bulk.nudge_line([one], COL) == (
            f"3 supplies were checked before {CHECK} changed (2 more in other collections)")
        two = bulk.Nudge(OTHER, 4, {COL: 4}, "2026-10-02", "also fixed")
        assert bulk.nudge_line([one, two], COL) == (
            "7 supplies were checked before 2 checks changed (2 more in other collections)")
        assert bulk.nudge_line([two], "civil-registration") is None

    def test_supply_queue_prints_the_line_each_check_and_the_command(self, conn):
        from cli.supply import queue_command

        filed(conn)
        got = CliRunner().invoke(queue_command, ["--collection", COL])
        assert f"1 supply was checked before {CHECK} changed" in got.output
        assert f"  {CHECK} - 1 here, 1 in all, changed " in got.output
        assert "\nmothman supply recheck --check <check_id> --reason <why>\n" in got.output

    def test_one_bulk_rechecks_owed_items_are_one_line(self, conn):
        _p, rec = _recorded(conn, 3)
        groups, rest = bulk.owed_groups(conn, recheck.owed(conn))
        assert rest == [] and len(groups) == 1
        assert bulk.owed_line(groups[0]).startswith(f"3 of 3 re-checks for {CHECK} still owed "
                                                    "(raised ")


# ---- criteria 6, 11, 12, 18, 22, 23, 26, 30, 31, 32: the flag route ---------------

def _cli(*args, monkeypatch=None):
    from cli.supply import recheck_command

    # WIDE, so a panel never breaks a check id across lines.
    return CliRunner().invoke(recheck_command, ["--check", CHECK, *args],
                              env={"COLUMNS": "400"})


class TestTheFlagRoute:
    @pytest.fixture(autouse=True)
    def _person(self, monkeypatch):
        from cli import filing_tui

        monkeypatch.setattr(filing_tui, "actor_at_the_keyboard", actor)

    def test_without_a_terminal_or_yes_it_shows_the_panel_and_refuses_giving_the_key(
            self, conn):
        filed(conn)
        key = bulk.plan(conn, CHECK).key
        got = _cli("--reason", "x")
        assert got.exit_code == 1
        flat = "".join(ch for ch in got.output if ch not in " \n│")
        assert f"Check:{CHECK}" in flat and "Itscurrentchangelogentry" in flat
        assert f"--yes --acknowledge {key}" in got.output
        assert conn.execute(f"SELECT count(*) FROM {bulk.TABLE}").fetchone()[0] == 0

    def test_yes_without_the_right_key_is_refused(self, conn):
        filed(conn)
        assert _cli("--reason", "x", "--yes").exit_code == 1
        assert _cli("--reason", "x", "--yes", "--acknowledge", "nope").exit_code == 1

    def test_hand_off_records_every_recheck_and_runs_none(self, conn, monkeypatch):
        filed(conn)
        ran = []
        monkeypatch.setattr(recheck, "run", lambda *a, **k: ran.append(a))
        key = bulk.plan(conn, CHECK).key
        got = _cli("--reason", "fixed", "--yes", "--acknowledge", key, "--hand-off")
        assert got.exit_code == 0, got.output
        assert ran == []
        assert "\nmothman pipeline process\n" in got.output
        assert "every owed QA run, not only these" in got.output
        assert conn.execute(f"SELECT handed_off FROM {bulk.TABLE}").fetchone() == (True,)

    def test_a_foreground_run_exits_0_and_a_partial_one_exits_3(self, conn, monkeypatch):
        filed(conn)
        monkeypatch.setattr(recheck, "run", lambda owed_id, **k: recheck.Outcome(
            owed_id, "r", True, "ok", status="green"))
        got = _cli("--reason", "fixed", "--yes", "--acknowledge", bulk.plan(conn, CHECK).key)
        assert got.exit_code == 0, got.output
        filed(conn)
        monkeypatch.setattr(recheck, "run", lambda owed_id, **k: recheck.Outcome(
            owed_id, "", False, "broke"))
        got = _cli("--reason", "fixed", "--yes", "--acknowledge", bulk.plan(conn, CHECK).key)
        assert got.exit_code == 3, got.output

    def test_nothing_to_cover_exits_1(self, conn):
        got = _cli("--reason", "x", "--yes", "--acknowledge", "k")
        assert got.exit_code == 1 and "already checked under its current" in got.output

    def test_list_prints_what_it_would_cover_and_records_nothing(self, conn):
        supply, period = filed(conn)
        got = _cli("--list")
        assert got.exit_code == 0 and supply in got.output and period in got.output
        assert conn.execute(f"SELECT count(*) FROM {bulk.TABLE}").fetchone()[0] == 0

    @pytest.mark.parametrize("flag", [["--supply", "x"], ["--dataset", DS],
                                      ["--from-period", "a"], ["--through-period", "b"]])
    def test_the_real_run_takes_no_range(self, conn, flag):
        got = _cli(*flag)
        assert got.exit_code == 1 and "is for --trial only" in got.output

    def test_help_says_it_runs_in_the_foreground_unless_handed_off(self):
        from cli.supply import recheck_command

        got = CliRunner().invoke(recheck_command, ["--help"])
        assert "in the foreground, one line per supply, unless --hand-off" in " ".join(
            got.output.split())

    def test_a_large_one_warns_with_an_estimate_and_names_hand_off(self, conn):
        for i in range(11):
            filed(conn, period=f"2099-S{i:04d}")
        text = "\n".join(_panel(bulk.plan(conn, CHECK)))
        assert "more than 10 supplies" in text and "roughly 11 minutes" in text
        assert "--hand-off" in text and "leaves the rest owed" in text

    def test_the_estimate(self):
        assert bulk.estimate(11) == "roughly 11 minutes"
        assert bulk.estimate(400) == "roughly 7 hours"

    def test_the_reason_question_says_where_it_is_published(self, conn):
        from cli import bulk_recheck_tui

        filed(conn)
        filed(conn)
        q = bulk_recheck_tui.reason_question(bulk.plan(conn, CHECK))
        assert "published on the dashboard against each of the 2 supplies" in q


# ---- criterion 21: terminal only -------------------------------------------------

class TestTerminalOnly:
    def test_it_is_a_terminal_only_operation(self):
        assert fd.BULK_RECHECK in fd.TERMINAL_ONLY
        assert fd.BULK_RECHECK not in fd.OPERATIONS

    def test_github_refuses_it_naming_the_terminal(self):
        from qa_tools.common import filing_from_github as gh

        with pytest.raises(dl.DecisionRefused, match="made in the terminal"):
            gh.read(gh.Comment(author="someone", body="/bulk-recheck\nwhy",
                               slot_key=f"{DS}/2026-Q1"))


# ---- the shared query (NFR 3) ----------------------------------------------------

class TestTheSharedQuery:
    def test_the_stale_pairs_name_only_what_differs_from_the_current_definition(self, conn):
        filed(conn)
        filed(conn, fingerprint=current())
        filed(conn, check=OTHER, fingerprint=current(OTHER))
        assert bulk.stale_fingerprints(conn, bulk.current_checks()) == {CHECK: {STALE}}

    def test_the_nudge_and_the_selection_agree(self, conn):
        filed(conn)
        filed(conn)
        (n,) = bulk.nudges(conn)
        assert n.total == len(bulk.plan(conn, CHECK).covered) == 2


# ---- criteria 13 and 18, and REQ-PIPE-178 criterion 14: the door ------------------

class TestTheDoor:
    @pytest.fixture(autouse=True)
    def _person(self, monkeypatch):
        from cli import filing_tui

        monkeypatch.setattr(filing_tui, "actor_at_the_keyboard", actor)

    def _drive(self, monkeypatch, answers):
        from cli import common

        asked = []

        def select(message, choices, flag_hint, default=None):
            asked.append((message, list(choices)))
            return answers.pop(0)
        monkeypatch.setattr(common, "select", select)
        monkeypatch.setattr(common, "text_prompt", lambda m, flag_hint: "fixed the check")
        monkeypatch.setattr(common, "confirm_change", lambda *a, **k: True)
        monkeypatch.setattr(common, "confirm", lambda *a, **k: True)
        return asked

    def test_the_first_menu_offers_it_above_the_collections_counting_every_one(
            self, conn, monkeypatch):
        from cli import common, filing_tui

        filed(conn)
        seen = {}

        def grouped_select(message, groups, *, top=(), **k):
            seen["top"] = top
            return None
        monkeypatch.setattr(common, "grouped_select", grouped_select)
        filing_tui.filing_menu()
        assert "Supplies checked before a check changed (1)" in seen["top"]

    def test_above_ten_it_offers_the_hand_off_first_and_hands_off(self, conn, monkeypatch):
        from cli import bulk_recheck_tui

        for i in range(11):
            filed(conn, period=f"2099-S{i:04d}")
        ran = []
        monkeypatch.setattr(recheck, "run", lambda *a, **k: ran.append(a))
        asked = self._drive(monkeypatch, [bulk_recheck_tui.RECHECK_ALL,
                                          bulk_recheck_tui.HAND_OFF])
        bulk_recheck_tui.flow(CHECK)
        assert asked[1][1] == [bulk_recheck_tui.HAND_OFF, bulk_recheck_tui.RUN_HERE]
        assert ran == []
        assert conn.execute(f"SELECT supplies, handed_off FROM {bulk.TABLE}").fetchone() == (
            11, True)

    def test_a_trial_is_offered_before_the_real_runs_confirmation_and_returns_to_it(
            self, conn, monkeypatch):
        from cli import bulk_recheck_tui

        supply, period = filed(conn)
        tried = []
        monkeypatch.setattr(bulk, "try_one", lambda c, **k: tried.append(c) or bulk.Tried(
            c, "green", "it would wait for a person"))
        monkeypatch.setattr(recheck, "run", lambda owed_id, **k: recheck.Outcome(
            owed_id, "r", True, "ok", status="green"))
        label = f"{DS} {period} - {supply} (green)"
        asked = self._drive(monkeypatch, [
            bulk_recheck_tui.TRY_FIRST, label, "Done - run the trial",
            bulk_recheck_tui.RECHECK_ALL])
        bulk_recheck_tui.flow(CHECK)
        assert [c.supply for c in tried] == [supply]
        assert bulk_recheck_tui.TRY_FIRST in asked[0][1]
        # BACK TO THE REAL RUN'S CONFIRMATION after the trial.
        assert asked[-1][1] == [bulk_recheck_tui.RECHECK_ALL, bulk_recheck_tui.TRY_FIRST]
        assert conn.execute(f"SELECT count(*) FROM {bulk.TABLE}").fetchone()[0] == 1

    def test_a_collections_queue_leads_to_the_asset_wide_entry(self, conn, monkeypatch):
        from cli import bulk_recheck_tui, common, filing_tui

        filed(conn)
        opened = []
        monkeypatch.setattr(bulk_recheck_tui, "door", lambda nudges: opened.append(nudges))
        monkeypatch.setattr(common, "select", lambda message, choices, flag_hint, default=None:
                            next(c for c in choices if "checked before" in c))
        filing_tui.queue_flow(COL)
        assert [n.check_id for n in opened[0]] == [CHECK]


# ---- NFR 3: the set form is results_about's rule ---------------------------------

def _newest_one_at_a_time(conn, check, keys):
    return {k: f for k in keys
            if (f := bulk.newest_fingerprint(conn, k[0], k[1], check.check_id)) is not None}


class TestTheSetFormIsResultsAbout:
    def test_own_and_read_results_newest_first(self, conn):
        checks = bulk.current_checks()
        a, _ = filed(conn)
        judged(conn, a, current())
        b, _ = filed(conn)
        cross = next(c for c in checks.values() if c.reads_tables and c.tool == "soda")
        # A cross-table result that READ supply b of cp-carers, and one that
        # read another supply of it.
        for read in (b, "cp-carers@elsewhere"):
            key = f"pytest_bulk_x_{uuid.uuid4().hex[:8]}"
            qa_store.record_run(conn, run_key=key, agency_id=AG, collection_id=COL,
                                run_timestamp=WHEN, run_by=REAL_PERSON, environment="sandbox")
            qa_store.record_results(
                conn, key, [{"dataset_id": cross.check_id.split(".")[3],
                             "check_id": cross.check_id, "status": "pass"}],
                tool="soda", agency_id=AG, collection_id=COL,
                scope=qa_store.CROSS_TABLE_SCOPE, fingerprints={cross.check_id: STALE},
                reads=[[qa_store.CheckRead("cp_carers", qa_store.READ, read)]])
            attempt_support.opened(conn, key)
            qa_store.complete_run(conn, key)
        for check in (checks[CHECK], cross):
            got = bulk.newest_by_supply(conn, check)
            mine = {k: v for k, v in got.items() if k in {(DS, a), (DS, b)}}
            assert mine == _newest_one_at_a_time(conn, check, {(DS, a), (DS, b)}), check.check_id
        assert bulk.newest_by_supply(conn, checks[CHECK])[(DS, a)] == current()
        assert bulk.newest_by_supply(conn, cross)[(DS, b)] == STALE


@pytest.mark.needs_deployment
class TestTheSetFormHoldsOnTheDeployment:
    """Every supply of the bootstrapped deployment that any result of these
    checks is about: the set form and results_about name the same newest."""

    def test_for_a_single_table_and_a_cross_table_check(self, deployment_history):
        checks = bulk.current_checks()
        cross = next(c for c in checks.values() if c.reads_tables and c.tool == "dbt")
        with supply_db.connect(read_only=True, label="test-bulk-recheck") as c:
            for check in (checks[CHECK], cross):
                got = bulk.newest_by_supply(c, check)
                assert got, f"no result of {check.check_id} is about any supply"
                assert got == _newest_one_at_a_time(c, check, set(got)), check.check_id
