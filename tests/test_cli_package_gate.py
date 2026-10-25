"""The terminal says what a package gate did (REQ-PIPE-276), and a person's
promotion is compared against the read holders its warning showed
(REQ-PIPE-266 criterion 17).

Driven through the real per-arrival lifecycle with each tool's evaluation
stood in for (tests/gate_support.py says exactly what is real), then through
the real terminal surfaces: `mothman cp qa --commit`, `mothman supply queue`,
`mothman supply decide`, the Filing decisions queue and door, the kept report
and the outcome panels - each asserted on what it prints, piped, with
NO_COLOR set and at 80 columns (criterion 21).

READ THROUGH KEITH'S LATER ANSWER 3a (2026-10-25, post-build-review #274 Q3):
a supply whose re-check against the warehouse RAN AND FAILED is its own root.
So the grouping beneath a root is tested where the hold-back could not be
checked - S2 strict and a could-not-check cascade - and S1 red's Clients v2
is its own counted row naming the package-mate's decision first.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from gate_support import (CP, Scenario, cross_red, install_fake_tools, own_red,
                          pin_replacement_setting)
from test_package_gate import V1, Q3, Q4, _in_the_warehouse, established, first_time

PIPED = {"NO_COLOR": "1", "COLUMNS": "80", "TERM": "dumb"}


@pytest.fixture
def sc(private_supply_dsn, cp_raw_dir, tmp_path, monkeypatch):
    scenario = Scenario(root=tmp_path, raw_dir=Path(cp_raw_dir))
    install_fake_tools(monkeypatch, scenario)
    pin_replacement_setting(monkeypatch)
    return scenario


@pytest.fixture
def person(monkeypatch):
    """The keyboard is a real person on contract/people.yaml, and a
    decision's knock-on runs as it does at the terminal."""
    from cli import filing_tui
    from qa_tools.common import people
    from test_carry_forward import REAL_PERSON

    monkeypatch.setattr(filing_tui, "actor_at_the_keyboard",
                        lambda: people.person_by_email(REAL_PERSON))


def _cli(group, args, *, input_=None):
    from click.testing import CliRunner

    got = CliRunner().invoke(group, args, env=PIPED, input=input_)
    return got.exit_code, got.output


def _flat(text: str) -> str:
    return " ".join(re.sub(r"[│╭╮╰╯─]", " ", text).split())


def _arrival(sc, label):
    (a,) = [a for a in sc.arrivals() if sc.label_of(a) == label]
    return a


def _state(dataset_id, period, supply, state="awaiting-decision"):
    from qa_tools.common import slot_state

    return slot_state.SlotState(dataset_id=dataset_id, period=period, state=state,
                                supply=supply)


def _reject(sc, supply, period):
    from test_package_gate import _reject as reject

    reject(sc, supply, period)


def _lines_whole(out: str, command: str) -> bool:
    """The command printed whole, on a line of its own, never wrapped."""
    return any(line.strip() == command for line in out.splitlines())


# ---- the scenarios -------------------------------------------------------------

def s1_red_zip(sc):
    """S1 red: Notifications v2 red on its own data; Clients v2's Client
    reference, re-checked against Notifications v1, fails."""
    v1 = established(sc)
    sc.rules += [own_red("N2"), cross_red("cp-notifications", "cp_clients",
                                          when={"cp_clients": "C2", "cp_notifications": "N1"})]
    v2 = sc.deliver("2024-08-05T10:00:00+08:00", {"cp_clients": "C2", "cp_notifications": "N2"})
    sc.process()
    return v1, v2


def s2_strict(sc):
    """S2 strict: Clients v2 red on its own data, Notifications v2 cannot be
    checked - no Clients in the warehouse - and is held back by it."""
    first_time(sc)
    sc.rules.append(own_red("C2"))
    v2 = sc.deliver("2024-11-03T10:00:00+08:00", {"cp_clients": "C2", "cp_notifications": "N2"})
    sc.process()
    return v2


def part_checked(sc):
    """A zip of two, the first file checked and the second not yet: its
    package's gate is owed."""
    established(sc)
    v2 = sc.deliver("2024-08-05T10:00:00+08:00", {"cp_clients": "C2", "cp_notifications": "N2"})
    sc.process(stop_before="N2")
    assert len(sc.owed("gate")) == 1, "precondition: the package's gate is owed"
    return v2


def cascade(sc):
    """A could-not-check cascade into 2024-Q4, which holds Case Workers,
    Notifications and Investigations only: Carers v2 red on its own data;
    Placements v2 cannot check Carers (none in the warehouse) and is held
    back by it; Clients v2's Placements check read the not-promoting
    Placements v2 and cannot be checked against the warehouse either - held
    back through Placements."""
    got = sc.deliver("2024-10-25T10:00:00+08:00",
                     {t: V1[t] for t in ("cp_case_workers", "cp_notifications",
                                         "cp_investigations")})
    sc.process()
    _in_the_warehouse(sc, got, Q4)
    sc.rules.append(own_red("K2"))
    v2 = sc.deliver("2024-11-03T10:00:00+08:00",
                    {"cp_carers": "K2", "cp_placements": "P2", "cp_clients": "C2"})
    sc.process()
    return v2


# ---------------------------------------------------------------------------
# Criterion 3 - the exit code is fed by the gate
# ---------------------------------------------------------------------------

class TestExitCodes:

    def test_s1_red_qa_commit_exits_1_and_shows_the_recheck(self, sc):
        """mothman cp qa --commit on S1 red, with Clients v2 checked last and
        green on its own run, exits 1 and prints a 're-checked against the
        warehouse' table: staggered, Notifications v2 (red on its own data)
        is waiting when Clients v2 arrives, so Clients v2's Client reference
        is re-run against Notifications v1 inside the gate and fails."""
        from cli.collection_cli import of

        v1 = established(sc)
        sc.rules += [own_red("N2"), cross_red("cp-notifications", "cp_clients",
                                              when={"cp_clients": "C2",
                                                    "cp_notifications": "N1"})]
        sc.deliver("2024-08-05T08:40:00+08:00", {"cp_notifications": "N2"})
        sc.process()
        c2 = sc.deliver("2024-08-05T09:00:00+08:00", {"cp_clients": "C2"})["C2"]
        run_id = _arrival(sc, "C2").run_id
        code, out = _cli(of("cp").group, ["qa", "--run-id", run_id, "--commit"])
        assert sc.holder("cp-clients", Q3) == v1["C1"], out
        assert "re-checked against the warehouse" in out, out
        own = [r for r in sc.results(run_id) if (r["status"] or "") in ("fail", "error")]
        assert own == [], "precondition: Clients v2 is green on its own run"
        assert code == 1, out
        assert sc.actions(c2)[-1] == "promotion-withheld"

    def test_waiting_first_file_exits_as_its_own_results_say(self, sc):
        """A first file of a package, checked and waiting for the rest of
        its delivery: the exit status `mothman cp qa` takes - its own run's
        results, fed by the gate (CollectionCLI.exit_status) - is 0 for a
        green first file and 1 for one red on its own data: nothing has been
        gated yet, so the gate adds nothing."""
        from cli.collection_cli import of

        established(sc)
        sc.rules.append(own_red("I2"))
        sc.deliver("2024-08-05T10:00:00+08:00", {"cp_clients": "C2", "cp_notifications": "N2"})
        sc.deliver("2024-08-06T10:00:00+08:00",
                   {"cp_investigations": "I2", "cp_placements": "P2"})
        sc.process(stop_before="N2")
        green = _arrival(sc, "C2")
        assert of("cp").exit_status(sc.results(green.run_id), [green]) == 0
        sc.process(stop_before="P2")
        red = _arrival(sc, "I2")
        assert len(sc.owed("gate")) == 1, "precondition: the second package waits"
        assert of("cp").exit_status(sc.results(red.run_id), [red]) == 1


# ---------------------------------------------------------------------------
# Criteria 1, 2, 4 and 5 - one vocabulary, and the next step
# ---------------------------------------------------------------------------

class TestVocabulary:

    def test_every_promotion_withheld_says_held_back(self, sc):
        """The kept report's outcome_of says 'held back by the rule', never
        'withheld', 'refused' or 'rejected'; and a held-back supply is never
        listed under 'Held - no period yet'."""
        from cli import lifecycle_report
        from qa_tools.common import filing_queue, supply_db

        _v1, v2 = s1_red_zip(sc)
        with supply_db.connect(read_only=True, label="pytest") as conn:
            got = lifecycle_report.outcome_of(conn, _arrival(sc, "C2"))
            held = filing_queue.held_in(conn, CP)
        assert got.gate.startswith("held back by the rule"), got.gate
        for word in ("withheld", "refused", "rejected"):
            assert word not in got.gate.lower(), got.gate
        assert v2["C2"] not in {h.supply for h in held}

    def test_turned_down_never_says_rejected(self, sc):
        """S2 strict, Clients v2 turned down by a person: the outcome panel
        for Notifications v2 says 'turned down', and no text it prints says
        'rejected' - the sentence never goes through _gate_words."""
        from cli import filing_tui
        from qa_tools.common import recheck, supply_db

        v2 = s2_strict(sc)
        _reject(sc, v2["C2"], Q4)
        with supply_db.connect(read_only=True, label="pytest") as conn:
            from qa_tools.common import root_cause

            why = root_cause.holdback_reason(conn, "cp-notifications", v2["N2"])
        got = recheck.Outcome(1, "r", True, "", status="red", period=Q4, promoted=False,
                              waits_because=why)
        text, _title, _style = filing_tui.outcome_panel("re-check", v2["N2"], Q4, got)
        assert ("The cp-clients file received with it was turned down; this supply now "
                "needs its own decision.") in text, text
        assert "rejected" not in text.lower(), text

    def test_next_step_names_the_package_mate_then_the_supply_after_rejection(self, sc):
        """While Clients v2 waits, Notifications v2's panel names Clients v2's
        decision first, says nothing needs deciding on it, and gives the
        override complete - the real supply id, only '<why>' left - on a line
        of its own; once Clients v2 is turned down, its own decision."""
        from cli import filing_tui
        from qa_tools.common import recheck

        v2 = s2_strict(sc)
        got = recheck.Outcome(1, "r", True, "", status="red", period=Q4, promoted=False,
                              waits_because="Held back: test")
        text, _t, _s = filing_tui.outcome_panel("re-check", v2["N2"], Q4, got)
        lines = text.splitlines()
        assert any(line.startswith(f"Decide cp-clients {Q4} (received ")
                   and line.endswith("- promoting it re-checks this one.") for line in lines)
        assert "Nothing needs deciding on this supply." in lines
        command = (f"mothman supply decide --operation promote --dataset cp-notifications "
                   f"--period {Q4} --supply {v2['N2']} --reason '<why>'")
        assert command in lines and "<id>" not in text
        assert f"or from the {Q4} door." in lines
        _reject(sc, v2["C2"], Q4)
        text, _t, _s = filing_tui.outcome_panel("re-check", v2["N2"], Q4, got)
        assert "turned down; this supply now needs its own decision" in text
        assert "Decide cp-clients" not in text


# ---------------------------------------------------------------------------
# Criterion 6 - grouped by root
# ---------------------------------------------------------------------------

class TestGroupedByRoot:

    def test_grouped_by_root_prints_final_states_only(self, sc, monkeypatch):
        """The kept report: Clients v2 red on its own data holds back
        Notifications v2 and Placements v2, neither of which can be checked
        without it. Its own lines, then one line per resulting outcome
        beneath it, each naming the root - final states only, each held-back
        supply said once. A chain is listed flat under its root, naming what
        it traces through (trace()); at scale, up to eight names then 'and
        <n> more'. (Under Keith's 3a a FAILED re-check is its own root, so
        no Child Protection cascade of could-not-check links runs deeper
        than one: the chain is pinned on trace() itself.)"""
        from cli import lifecycle_report
        from qa_tools.common import root_cause

        first_time(sc)
        sc.rules.append(own_red("C2"))
        v2 = sc.deliver("2024-11-03T10:00:00+08:00",
                        {"cp_clients": "C2", "cp_notifications": "N2", "cp_placements": "P2"})
        sc.process()
        for label in ("N2", "P2"):
            assert sc.actions(v2[label])[-1] == "promotion-withheld", sc.actions(v2[label])
        said = []
        lifecycle_report.report([_arrival(sc, x) for x in ("C2", "N2", "P2")],
                                say=said.append)
        text = "\n".join(said)
        assert "cp-clients (2 more held back with it, listed beneath)" in text, text
        assert "held back with it (same delivery):" in [line.strip() for line in said], text
        beneath = [line.strip() for line in said if line.strip().startswith("- ")]
        assert {line.split()[1].rstrip(",") for line in beneath} <= {
            "cp-notifications", "cp-placements"}, beneath
        assert sum("cp-notifications" in line for line in beneath) == 1
        assert all("deciding cp-clients settles it" in line for line in beneath), beneath
        # NOTHING HELD BACK IS GIVEN LINES OF ITS OWN ABOVE (final states only).
        assert not any(line.startswith("  cp_notifications__") for line in said)

        # A CHAIN, FLAT UNDER ITS ROOT: Z held back by Y, Y by X.
        entries = {"z@1": ("y@1", "package-mate"), "y@1": ("x@1", "package-mate")}
        monkeypatch.setattr(root_cause, "_latest_gate_entry", lambda conn, ds, sup: (
            {"action": "promotion-withheld", "held_back_by": entries[sup][0],
             "held_back_detail": {"came": entries[sup][1], "failed": False}}
            if sup in entries else None))
        monkeypatch.setattr(root_cause, "_turned_down", lambda *a: False)
        monkeypatch.setattr(root_cause, "_absent_table_root", lambda *a: None)
        traced = root_cause.trace(None, "z", "z@1", Q4)
        assert traced.root.supply == "x@1" and traced.via == (("y", "y@1"),)
        lines = lifecycle_report.beneath_lines(
            "x", [(lifecycle_report.WITH_IT, "z", "held back", ["y"])], root_name="x")
        assert lines[-1] == "  - z (through y)  held back", lines
        lines = lifecycle_report.beneath_lines(
            "root", [(lifecycle_report.WITH_IT, f"cp-{i:02d}", "same", ()) for i in range(10)],
            root_name="root")
        assert lines[-1] == ("  - cp-00, cp-01, cp-02, cp-03, cp-04, cp-05, cp-06, cp-07 "
                             "and 2 more  same"), lines

    def test_supply_queue_shows_grouping_gating_and_the_carry_forward_warning(self, sc):
        """mothman supply queue renders through the one renderer: S2 strict's
        Notifications v2 beneath Clients v2 with its override whole on a line
        of its own and not counted; a second delivery still being checked as
        one quiet line, never counted. (REQ-PIPE-271's own tests assert its
        warning in this command's output; here, that it still comes first.)"""
        from cli.supply import supply_group

        v2 = s2_strict(sc)
        sc.deliver("2024-11-04T10:00:00+08:00",
                   {"cp_investigations": "I2", "cp_placements": "P2"})
        sc.process(stop_before="P2")
        code, out = _cli(supply_group, ["queue", "--collection", CP])
        assert code == 0, out
        flat = _flat(out)
        assert ("1 supply/supplies waiting on a decision in Child Protection "
                "(1 more held back with it, listed beneath)") in flat, out
        assert "held back with it (same delivery):" in flat
        assert "- cp-notifications nothing needs deciding on this supply" in flat
        assert _lines_whole(out, f"mothman supply decide --operation promote --dataset "
                                 f"cp-notifications --period {Q4} --supply {v2['N2']} "
                                 f"--reason '<why>'"), out
        assert "Checking a delivery received" in flat and "(1 of 2 files checked)" in flat
        # NO RICH MARKUP SURVIVES INTO A STATE LINE (criterion 21).
        assert "[Red]" not in out and "[red]" not in out


# ---------------------------------------------------------------------------
# Criteria 7 to 9 - what a decision will set off; REQ-PIPE-266 criterion 17
# ---------------------------------------------------------------------------

class TestConsequences:

    def test_override_lists_the_worse_recheck_consequence(self, sc):
        """T13: promoting S1 red's held-back Clients v2 re-checks
        Notifications v1 - in the warehouse - against it, and Client
        reference already failed for that pair: both ends named and the
        likely 'Promoted, then re-checked worse', as a keyed consequence."""
        from qa_tools.common import filing_decisions as fd, people, supply_db
        from test_carry_forward import REAL_PERSON

        v1, v2 = s1_red_zip(sc)
        request = fd.Request(operation=fd.PROMOTE, dataset_id="cp-clients",
                             actor=people.person_by_email(REAL_PERSON), reason="t",
                             period=Q3, supply=v2["C2"])
        with supply_db.connect(read_only=True, label="pytest") as conn:
            got = fd.consequences(conn, request)
        worse = [line for line in got.lines if "will very likely become" in line]
        assert worse, got.lines
        assert worse[0].startswith("cp-notifications (in the warehouse, received ")
        assert "is re-checked against this supply." in worse[0]
        assert worse[0].endswith('so cp-notifications will very likely become '
                                 '"Promoted, then re-checked worse".')
        assert got.key, "a consequence beyond the slot needs its key with --yes"
        del v1

    def test_override_over_a_not_yet_due_check_says_so(self, monkeypatch, private_supply_dsn):
        """Promoting over a could-not-run whose table is not yet due says so,
        naming when it falls due."""
        from qa_tools.common import (filing_decisions as fd, knock_on, people,
                                     period_schema, supply_db, supply_status)
        from test_carry_forward import REAL_PERSON

        from qa_tools.common import promotion

        check = next(c for c in promotion._declared_reads()
                     if ".cp-notifications." in c and "relationships" in c
                     and "cp_clients" in promotion._declared_reads()[c])
        record = {"check_id": check, "status": "fail", "unrunnable_tables": ["cp_clients"],
                  "unrunnable_code": period_schema.NOT_YET_DUE,
                  "unrunnable_codes": {"cp_clients": period_schema.NOT_YET_DUE},
                  "unrunnable_due_at": "2024-11-14T17:00:00+08:00",
                  "unrunnable_reason": "not yet due"}
        monkeypatch.setattr(supply_status, "latest_results", lambda *a, **k: [record])
        monkeypatch.setattr(knock_on, "readers", lambda *a, **k: [])
        request = fd.Request(operation=fd.PROMOTE, dataset_id="cp-notifications",
                             actor=people.person_by_email(REAL_PERSON), reason="t",
                             period=Q4, supply="cp-notifications@202411010840000800")
        with supply_db.connect(label="pytest") as conn:
            from qa_tools.common import qa_store

            qa_store.ensure_schema(conn)
            lines = fd._held_back_consequences(conn, request)
        (line,) = lines
        assert line.endswith("could not run: cp-clients is not due until 5:00pm Thursday, "
                             "14 November 2024. Promoting now promotes on a check nobody "
                             "could run; it is re-checked when cp-clients is promoted."), line

    def test_order_b_red_links_the_two_rows(self, sc):
        """Staggered Order B red: Clients v2 at 9:00 fails Client reference
        against Notifications v1; Notifications v2 at 9:05 passes against the
        staged Clients v2 and is red on its own data. Clients v2's row and
        door say promoting Notifications v2 re-checks it, and promoting
        Notifications v2 lists the re-check among its consequences."""
        from cli import filing_tui
        from qa_tools.common import (filing_decisions as fd, filing_queue, people,
                                     root_cause, supply_db)
        from test_carry_forward import REAL_PERSON

        established(sc)
        sc.rules += [own_red("N2"), cross_red("cp-notifications", "cp_clients",
                                              when={"cp_clients": "C2",
                                                    "cp_notifications": "N1"})]
        c2 = sc.deliver("2024-08-05T09:00:00+08:00", {"cp_clients": "C2"})["C2"]
        sc.process()
        n2 = sc.deliver("2024-08-05T09:05:00+08:00", {"cp_notifications": "N2"})["N2"]
        sc.process()
        with supply_db.connect(read_only=True, label="pytest") as conn:
            groups = root_cause.group_queue(conn, filing_queue.awaiting(conn, CP))
            request = fd.Request(operation=fd.PROMOTE, dataset_id="cp-notifications",
                                 actor=people.person_by_email(REAL_PERSON), reason="t",
                                 period=Q3, supply=n2)
            got = fd.consequences(conn, request)
        rows = {r.supply for r in groups.rows}
        assert {c2, n2} <= rows, "two counted rows, each its own root"
        said = groups.lines.get(("cp-clients", Q3, c2)) or []
        assert any(line.endswith("passes against the cp-notifications waiting for a decision "
                                 "(received 9:05am Monday, 5 August 2024); promoting that one "
                                 "re-checks this one.") for line in said), said
        note, offer_nothing = filing_tui.door_note(_state("cp-clients", Q3, c2))
        assert not offer_nothing and "promoting that one re-checks this one." in note
        assert any(line.startswith("re-checks cp-clients' waiting supply received 9:00am")
                   and line.endswith("if it is green, the rule promotes it.")
                   for line in got.lines), got.lines

    def test_a_promotion_whose_read_supply_moved_raises_the_consequences_refusal(
            self, sc, person):
        """REQ-PIPE-266 criterion 17: S1 red's held-back Clients v2 read
        Notifications v1 in the warehouse. A person confirms its promotion
        against that warning; before it is applied Notifications v2 is
        promoted by hand, so the read holder moved. Under the locks the
        consequences are compared again, the refusal is the existing
        consequences-changed one, nothing is recorded, and with --yes it
        exits 1 naming the new key."""
        from cli.supply import supply_group
        from qa_tools.common import filing_decisions as fd, people, supply_db
        from test_carry_forward import REAL_PERSON

        _v1, v2 = s1_red_zip(sc)
        request = fd.Request(operation=fd.PROMOTE, dataset_id="cp-clients",
                             actor=people.person_by_email(REAL_PERSON), reason="t",
                             period=Q3, supply=v2["C2"])
        with supply_db.connect(read_only=True, label="pytest") as conn:
            shown = fd.consequences(conn, request)
        sc.promote_by_hand(v2["N2"], Q3, at="2024-09-20T10:00:00+08:00")
        before = sc.actions(v2["C2"])
        code, out = _cli(supply_group, [
            "decide", "--operation", "promote", "--dataset", "cp-clients", "--period", Q3,
            "--supply", v2["C2"], "--reason", "test", "--yes", "--acknowledge", shown.key])
        with supply_db.connect(read_only=True, label="pytest") as conn:
            now = fd.consequences(conn, request)
        assert code == 1, out
        assert now.key != shown.key and now.key in _flat(out), out
        assert "does not match this decision's warning" in _flat(out)
        assert sc.actions(v2["C2"]) == before, "nothing recorded"
        assert sc.holder("cp-clients", Q3) != v2["C2"]


# ---------------------------------------------------------------------------
# Criterion 10 - every supply the knock-on re-gated
# ---------------------------------------------------------------------------

class TestFollowUp:

    def test_follow_up_lists_every_regated_supply(self, sc, person):
        """S1 red: a person promotes Notifications v2; the knock-on re-gates
        Clients v2 on its arrival result against it and the rule promotes it
        - listed with its outcome, not only what was left incomplete."""
        from cli.supply import supply_group
        from qa_tools.common import filing_decisions as fd, people, supply_db
        from test_carry_forward import REAL_PERSON

        _v1, v2 = s1_red_zip(sc)
        with supply_db.connect(read_only=True, label="pytest") as conn:
            key = fd.consequences(conn, fd.Request(
                operation=fd.PROMOTE, dataset_id="cp-notifications",
                actor=people.person_by_email(REAL_PERSON), reason="t", period=Q3,
                supply=v2["N2"])).key
        args = ["decide", "--operation", "promote", "--dataset", "cp-notifications",
                "--period", Q3, "--supply", v2["N2"], "--reason", "test", "--yes"]
        code, out = _cli(supply_group, args + (["--acknowledge", key] if key else []))
        assert code == 0, out
        flat = _flat(out)
        assert "Re-gated after this decision" in flat, out
        assert re.search(r"- [^:]*cp-clients[^:]*: \w+, promoted by the rule", flat), out
        assert sc.holder("cp-clients", Q3) == v2["C2"]
        assert "knock-on:" not in out


# ---------------------------------------------------------------------------
# Criteria 11 to 13 - a delivery still being checked
# ---------------------------------------------------------------------------

class TestADeliveryBeingChecked:

    def test_mid_gate_decision_is_refused_before_the_reason_prompt(self, sc, person,
                                                                   monkeypatch):
        """The flag form, with no --reason: refused with REQ-PIPE-266
        criterion 15's wording before any reason is asked for, exit 75."""
        from cli import common
        from cli.supply import supply_group

        v2 = part_checked(sc)
        monkeypatch.setattr(common, "text_prompt", lambda *a, **k: pytest.fail(
            "a reason was asked for a decision about to be refused"))
        code, out = _cli(supply_group, ["decide", "--operation", "promote", "--dataset",
                                        "cp-clients", "--period", Q3, "--supply", v2["C2"]])
        assert code == 75, out
        assert "is still being checked (1 of 2 files checked); decide once it is gated." in \
            _flat(out)

    def test_a_delivery_being_gated_is_a_quiet_uncounted_group(self, sc, monkeypatch, capsys):
        """The Filing decisions queue: one dim line for the delivery, never
        counted and never offered - and where it is all there is, 'Nothing
        is waiting on a person in Child Protection.' with the line beneath it
        and no 'Which one?'."""
        from cli import common, filing_tui

        from qa_tools.common import filing_queue

        part_checked(sc)
        asked = []
        monkeypatch.setattr(common, "select", lambda msg, choices, **k: asked.append(
            (msg, choices)))
        # ALL THERE IS: the fixture's own unfilled earlier periods aside.
        monkeypatch.setattr(filing_queue, "closed_gaps", lambda *a, **k: [])
        filing_tui.queue_flow(CP)
        out = capsys.readouterr().out
        flat = _flat(out)
        assert "Nothing is waiting on a person in Child Protection." in flat, out
        assert re.search(r"Checking a delivery received .* \(1 of 2 files checked\)", flat)
        assert flat.index("Nothing is waiting") < flat.index("Checking a delivery")
        assert asked == [], asked
        assert "waiting on a decision in Child Protection" not in flat

    def test_owed_gate_item_is_worded_in_supply_queue(self, sc):
        """'gate of the delivery received <instant> (<n> of <m> files
        checked)', never a re-evaluation of a period's readers."""
        from cli.supply import supply_group

        part_checked(sc)
        code, out = _cli(supply_group, ["queue", "--collection", CP])
        flat = _flat(out)
        assert code == 0, out
        assert re.search(r"gate of the delivery received .* \(1 of 2 files checked\)", flat), out
        assert "re-evaluation of None" not in flat and "readers of" not in flat

    def test_the_door_offers_no_decision_while_checking(self, sc, monkeypatch, capsys):
        """The period's door shows the supply as 'checking with its delivery
        (1 of 2 files checked)' and offers no decision on it."""
        from cli import common, filing_tui

        v2 = part_checked(sc)
        asked = []
        monkeypatch.setattr(common, "select", lambda msg, choices, **k: asked.append(msg))
        note, offer_nothing = filing_tui.door_note(_state("cp-clients", Q3, v2["C2"]))
        assert offer_nothing and "checking with its delivery (1 of 2 files checked)" in note
        filing_tui._decide_on(_state("cp-clients", Q3, v2["C2"]), offer=("promote", "reject"))
        assert asked == [], asked
        assert "checking with its delivery (1 of 2 files checked)" in _flat(
            capsys.readouterr().out)


# ---------------------------------------------------------------------------
# Criterion 20 and REQ-PIPE-266 criterion 16 - 75 means 'try later'
# ---------------------------------------------------------------------------

class TestTryLater:

    def test_a_lock_timeout_refusal_exits_75(self, private_supply_dsn, person, monkeypatch):
        """A decision transaction whose lock wait times out is refused with
        RUN_IN_PROGRESS and, on the flag form, exits 75 (V5-Q2 = A)."""
        import psycopg

        from cli.supply import supply_group
        from qa_tools.common import decision_log, filing_decisions, supply_db

        with supply_db.connect(label="pytest") as conn:
            from qa_tools.common import qa_store

            qa_store.ensure_schema(conn)

        def timed_out(*_a, **_k):
            raise psycopg.errors.LockNotAvailable("canceling statement due to lock timeout")

        monkeypatch.setattr(decision_log, "_lock", timed_out)
        monkeypatch.setattr(filing_decisions, "_refuse_promoting_where_it_is_not_filed",
                            lambda *a: None)
        monkeypatch.setattr(filing_decisions, "_refuse_promoting_what_never_loaded",
                            lambda *a: None)
        monkeypatch.setattr(filing_decisions, "_refuse_on_an_open_pair", lambda *a: None)
        monkeypatch.setattr(filing_decisions, "_already", lambda *a: None)
        monkeypatch.setattr(filing_decisions, "consequences",
                            lambda *a: filing_decisions.Consequences(lines=()))
        code, out = _cli(supply_group, [
            "decide", "--operation", "mark-not-supplied", "--dataset", "cp-carers",
            "--period", Q3, "--reason", "test", "--yes"])
        assert code == 75, out
        assert "Nothing was done; retry in a minute." in _flat(out)

    def test_a_persons_decision_refused_while_a_gate_runs_exits_75(
            self, private_supply_dsn, person):
        """A table-moving decision while a gate application holds the period:
        'A gate is running for 2024-Q3. Nothing was changed. Try again in a
        moment.', exit 75."""
        from cli.supply import supply_group
        from qa_tools.common import gate, qa_store, supply_db

        with supply_db.connect(label="pytest") as conn:
            qa_store.ensure_schema(conn)
        with gate.period_lock(CP, Q3):
            code, out = _cli(supply_group, [
                "decide", "--operation", "promote", "--dataset", "cp-clients", "--period",
                Q3, "--supply", "cp-clients@202408050900000800", "--reason", "t", "--yes"])
        assert code == 75, out
        assert "A gate is running for 2024-Q3. Nothing was changed. Try again in a moment." \
            in _flat(out)

    def test_the_documented_exit_codes_name_75s_three_causes(self):
        from cli.supply import supply_group

        code, out = _cli(supply_group, ["decide", "--help"])
        flat = _flat(out)
        assert code == 0
        assert ("the delivery is still being checked, a gate is running for the period, or "
                "a lock wait timed out") in flat, flat


# ---------------------------------------------------------------------------
# Criteria 14, 15, 17, 18 and 19
# ---------------------------------------------------------------------------

class TestWhatTheRuleDid:

    def test_owed_recheck_is_never_shown_as_rechecked_worse(self, sc):
        """A promoted Notifications v1, re-checked green by a person; then a
        person demotes Clients v1 and the knock-on has not run, so
        Notifications v1 reads red only for 'recheck-owed'. It is not listed
        as 'Promoted, then re-checked worse', and the door words it as not
        yet re-checked, the command on a line of its own."""
        from cli import filing_tui
        from qa_tools.common import (filing_decisions as fd, people, recheck, rechecking,
                                     supply_db, supply_status)
        from test_carry_forward import REAL_PERSON

        v1 = established(sc)
        actor = people.person_by_email(REAL_PERSON)
        got = fd.apply(fd.Request(operation=fd.RECHECK, dataset_id="cp-notifications",
                                  actor=actor, reason="t", period=Q3, supply=v1["N1"],
                                  confirmed=True), effective_at="2024-09-01T10:00:00+08:00")
        (owed_id,) = got.owed
        assert recheck.run(owed_id).completed
        demote = fd.Request(operation=fd.DEMOTE, dataset_id="cp-clients", actor=actor,
                            reason="t", period=Q3, supply=v1["C1"], confirmed=True)
        with supply_db.connect(read_only=True, label="pytest") as conn:
            key = fd.consequences(conn, demote).key
        import dataclasses

        fd.apply(dataclasses.replace(demote, acknowledged=key or None),
                 effective_at="2024-09-20T10:00:00+08:00")
        assert sc.owed("reevaluate"), "precondition: the knock-on is owed and not run"
        with supply_db.connect(read_only=True, label="pytest") as conn:
            owed = supply_status.red_only_for_recheck_owed(conn, "cp-notifications",
                                                           v1["N1"])
            worse = rechecking.worse_than_promoted(conn, "cp-notifications", v1["N1"])
        assert owed, "precondition: red only for an owed re-check"
        assert worse == []
        note, _nothing = filing_tui.door_note(_state("cp-notifications", Q3, v1["N1"],
                                                     state="promoted"))
        lines = (note or "").splitlines()
        assert any(line.startswith("Not yet re-checked against the cp-clients demoted ")
                   and line.endswith("the re-check runs on the next processing pass:")
                   for line in lines), note
        assert "mothman pipeline process" in lines
        assert "re-checked worse" not in (note or "").lower()

    def test_rule_promotion_after_a_warehouse_recheck_says_why(self, sc):
        """S1 green: Clients v2 re-checked against Notifications v1 and
        promoted by the rule - the kept report and the outcome panel say why."""
        from cli import filing_tui, lifecycle_report
        from qa_tools.common import recheck, supply_db

        established(sc)
        sc.rules.append(own_red("N2"))
        v2 = sc.deliver("2024-08-05T10:00:00+08:00",
                        {"cp_clients": "C2", "cp_notifications": "N2"})
        sc.process()
        assert sc.holder("cp-clients", Q3) == v2["C2"]
        with supply_db.connect(read_only=True, label="pytest") as conn:
            gate = lifecycle_report.outcome_of(conn, _arrival(sc, "C2")).gate
        assert gate.startswith("promoted by the rule"), gate
        assert ("re-checked against the cp-notifications in place in the warehouse "
                "(received 10:00am Thursday, 25 July 2024), green, because the "
                "cp-notifications received with it was held back") in gate, gate
        got = recheck.Outcome(1, "r", True, "", status="green", period=Q3, promoted=True)
        text, _t, _s = filing_tui.outcome_panel("re-check", v2["C2"], Q3, got)
        assert "It was promoted by the rule - " in text and "green, because the " \
            "cp-notifications received with it was held back" in text, text

    def test_crashed_sibling_wording(self, sc):
        """Notifications v2's run stops at the checks stage: Clients v2,
        checked, waits for its package - said, with the command on a line of
        its own."""
        from qa_tools.common import gate

        established(sc)
        sc.deliver("2024-08-05T10:00:00+08:00", {"cp_clients": "C2", "cp_notifications": "N2"})
        sc.crash.add(("soda", "cp_notifications__"))
        sc.process()
        (stopped,) = sc.failures
        assert gate.crashed_sibling_lines(stopped) == [
            "cp-clients: checked, waiting for its package - cp-notifications' run stopped at "
            "the checks stage; the next pass re-runs it and gates both",
            "mothman pipeline process"]

    def test_partial_refile_warns(self, sc):
        """Re-filing S2 strict's Clients v2 into another period without its
        package-mate warns before confirming, naming cp-notifications, and is
        still offered on the same terms - a note, never part of the key."""
        from qa_tools.common import filing_decisions as fd, people, supply_db
        from test_carry_forward import REAL_PERSON

        v2 = s2_strict(sc)
        request = fd.Request(operation=fd.REFILE, dataset_id="cp-clients",
                             actor=people.person_by_email(REAL_PERSON), reason="t",
                             period=Q4, supply=v2["C2"], to_period="2025-Q1")
        with supply_db.connect(read_only=True, label="pytest") as conn:
            got = fd.consequences(conn, request)
        assert any("came in one delivery with cp-notifications" in n for n in got.notes), \
            got.notes
        assert not any("cp-notifications" in line and "one delivery" in line
                       for line in got.lines)

    def test_a_joined_supply_carries_the_supplier_hint(self, sc, capsys):
        """A supply held back by a supply that arrived separately: one dim
        line beneath it pointing at the supplier guidance."""
        from cli import filing_tui
        from qa_tools.common import filing_queue, supply_db

        first_time(sc)
        sc.rules.append(own_red("C2"))
        sc.deliver("2024-11-03T09:00:00+08:00", {"cp_clients": "C2"})
        sc.process()
        sc.deliver("2024-11-03T09:05:00+08:00", {"cp_notifications": "N2"})
        sc.process()
        with supply_db.connect(read_only=True, label="pytest") as conn:
            groups = filing_tui.queue_groups(conn, filing_queue.awaiting(conn, CP))
            filing_tui.say_queue(conn, groups, CP)
        flat = _flat(capsys.readouterr().out)
        assert "(1 more held back by it, listed beneath)" in flat, flat
        assert "held back by it:" in flat
        assert ("Files sent separately are gated as each arrives; sent as one zip they are "
                "gated together (supplier guidance, REQ-DOCS-274).") in flat
