"""Files that arrive together are gated together, once every one is checked
(REQ-PIPE-266), on verdicts about what the warehouse will hold, transitively
until nothing changes (REQ-PIPE-267).

Every fixture states the content of EVERY Child Protection table in its
period (REQ-PIPE-267 criterion 19), and pins a replacement setting that lets
a green resupply replace a promoted one (criterion 16). Driven through the
real lifecycle with each tool's evaluation stood in for - tests/gate_support.py
says exactly what is real and what is not.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from gate_support import (CP, TABLES, Scenario, checks_reading, cross_red, install_fake_tools,
                          own_red, pin_replacement_setting)

Q3, Q4 = "2024-Q3", "2024-Q4"
CLIENT_REFS = checks_reading("cp_clients", "cp-notifications")
V1 = {"cp_clients": "C1", "cp_notifications": "N1", "cp_investigations": "I1",
      "cp_placements": "P1", "cp_carers": "K1", "cp_case_workers": "W1"}


@pytest.fixture
def sc(private_supply_dsn, cp_raw_dir, tmp_path, monkeypatch):
    scenario = Scenario(root=tmp_path, raw_dir=Path(cp_raw_dir))
    install_fake_tools(monkeypatch, scenario)
    pin_replacement_setting(monkeypatch)
    return scenario


# ---- the three fixture contents (criterion 19) ---------------------------------

def established(sc: Scenario) -> dict:
    """2024-Q3 holding v1 of all six tables, promoted green."""
    got = sc.deliver("2024-07-25T10:00:00+08:00", V1)
    sc.process()
    for label, supply in got.items():
        assert sc.holder(supply.split("@")[0], Q3) == supply, (label, sc.actions(supply))
    return got


def _in_the_warehouse(sc: Scenario, got: dict, period: str) -> None:
    """Each supply promoted into `period` by hand - or, where the period
    already stands on an earlier one for its dataset (inherited: the
    schedule owes nothing then), left there, in the warehouse all the same."""
    for supply in got.values():
        dataset_id = supply.split("@", 1)[0]
        if sc.holder(dataset_id, period):
            continue
        sc.promote_by_hand(supply, period, at="2024-10-26T10:00:00+08:00")


def first_time(sc: Scenario) -> dict:
    """2024-Q4 holding Case Workers, Carers, Investigations and Placements in
    the warehouse (put there by the setup), no Clients or Notifications ever
    supplied."""
    got = sc.deliver("2024-10-25T10:00:00+08:00",
                     {t: V1[t] for t in ("cp_case_workers", "cp_carers",
                                         "cp_investigations", "cp_placements")})
    sc.process()
    _in_the_warehouse(sc, got, Q4)
    return got


def empty_but_workers(sc: Scenario) -> dict:
    """2024-Q4 holding only Case Workers and Carers in the warehouse."""
    got = sc.deliver("2024-10-25T10:00:00+08:00",
                     {t: V1[t] for t in ("cp_case_workers", "cp_carers")})
    sc.process()
    _in_the_warehouse(sc, got, Q4)
    return got


def _gated(sc, supply) -> list[str]:
    return [a for a in sc.actions(supply)
            if a in ("promote", "promotion-withheld", "promotion-refused")]


def _promotion(sc, supply) -> dict:
    (entry,) = [d for d in sc.decisions(supply) if d["action"] == "promote"]
    return entry


def _readers_runs(sc, supply) -> list[dict]:
    return [r for r in sc.runs(supply) if r["scope"] == "readers"]


def _withheld(sc, supply) -> dict:
    found = [d for d in sc.decisions(supply) if d["action"] == "promotion-withheld"]
    assert found, sc.actions(supply)
    return found[-1]


# ---------------------------------------------------------------------------
# REQ-PIPE-266
# ---------------------------------------------------------------------------

class TestGatedTogether:

    def test_no_sibling_is_gated_before_the_last_is_checked(self, sc):
        """S1: nothing is promoted or held back for either v2 before both
        runs are recorded, and a 'gate' item is owed between them."""
        established(sc)
        v2 = sc.deliver("2024-08-05T10:00:00+08:00",
                        {"cp_clients": "C2", "cp_notifications": "N2"})
        sc.process(stop_before="N2")
        assert _gated(sc, v2["C2"]) == [] and _gated(sc, v2["N2"]) == []
        (owed,) = sc.owed("gate")
        assert owed.period == Q3
        sc.process()
        assert _gated(sc, v2["C2"]) and _gated(sc, v2["N2"])
        assert sc.owed("gate") == []

    def test_a_package_promoted_whole_owes_one_reevaluation(self, sc):
        """S2: a first-time zip of two green files promotes both with one
        effective instant, each naming the other, owes ONE re-evaluation, and
        records no readers-only run for either."""
        first_time(sc)
        v2 = sc.deliver("2024-11-03T10:00:00+08:00",
                        {"cp_clients": "C2", "cp_notifications": "N2"})
        sc.process()
        c, n = _promotion(sc, v2["C2"]), _promotion(sc, v2["N2"])
        assert c["effective_at"] == n["effective_at"]
        assert c["gate_application"] == n["gate_application"] is not None
        assert list(c["promoted_with"]) == [v2["N2"]] and list(n["promoted_with"]) == [v2["C2"]]
        from qa_tools.common import qa_store, recheck, supply_db

        with supply_db.connect(read_only=True, label="pytest") as conn:
            owed = conn.execute(
                f"SELECT count(*) FROM {recheck.TABLE} WHERE kind = 'reevaluate' "
                "AND caused_by_decision IN (?, ?)", [c["id"], n["id"]]).fetchone()[0]
            del qa_store
        assert owed == 1
        assert _readers_runs(sc, v2["C2"]) == [] and _readers_runs(sc, v2["N2"]) == []


class TestAFileWaitingForItsDelivery:

    def test_the_kept_report_says_it_waits_and_offers_no_decision(self, sc):
        """Criterion 5: a file of a package not yet fully checked is said to
        be checked and not gated - 'checked, waiting for the rest of its
        delivery (<n> of <m> files checked)' - in the kept report, never its
        'owed to the next processing pass' fallback, and no decision is
        offered on it."""
        from cli import lifecycle_report
        from qa_tools.common import filing_queue, supply_db

        established(sc)
        v2 = sc.deliver("2024-08-05T10:00:00+08:00",
                        {"cp_clients": "C2", "cp_notifications": "N2"})
        sc.process(stop_before="N2")
        (arrival,) = [a for a in sc.arrivals() if sc.label_of(a) == "C2"]
        with supply_db.connect(read_only=True, label="pytest") as conn:
            got = lifecycle_report.outcome_of(conn, arrival)
            offered = filing_queue.from_run(conn, CP, arrival.run_id)
        assert got.gate == "checked, waiting for the rest of its delivery (1 of 2 files checked)"
        assert "next processing pass" not in got.gate
        assert [s for s in offered if s.supply == v2["C2"]] == []


class TestInterruptedPackage:

    def test_a_part_checked_package_is_finished_and_gated_whole(self, sc):
        established(sc)
        v2 = sc.deliver("2024-08-05T10:00:00+08:00",
                        {"cp_clients": "C2", "cp_notifications": "N2"})
        sc.process(stop_before="N2")
        assert _gated(sc, v2["C2"]) == []
        sc.process()
        c, n = _promotion(sc, v2["C2"]), _promotion(sc, v2["N2"])
        assert c["gate_application"] == n["gate_application"]

    def test_a_crashed_sibling_keeps_the_package_waiting(self, sc):
        """Notifications v2's run fails at the Soda stage: Clients v2 is
        neither promoted nor held back, the package's gate is owed, and the
        next pass re-runs Notifications v2 and gates both."""
        established(sc)
        v2 = sc.deliver("2024-08-05T10:00:00+08:00",
                        {"cp_clients": "C2", "cp_notifications": "N2"})
        sc.crash.add(("soda", "cp_notifications__"))
        sc.process()
        assert sc.failures and sc.failures[0].stage == "checks"
        assert _gated(sc, v2["C2"]) == [] and _gated(sc, v2["N2"]) == []
        assert len(sc.owed("gate")) == 1
        sc.crash.clear()
        sc.process()
        c, n = _promotion(sc, v2["C2"]), _promotion(sc, v2["N2"])
        assert c["gate_application"] == n["gate_application"]
        assert sc.owed("gate") == []


class TestBackstopSibling:

    def test_a_backstop_refused_sibling_counts_as_held_back(self, sc, monkeypatch):
        """The agreement backstop refuses cp-notifications at the gate:
        Clients v2 is re-checked against Notifications v1 and promoted."""
        from qa_tools.common import agreement_drift, filing

        established(sc)
        v2 = sc.deliver("2024-08-05T10:00:00+08:00",
                        {"cp_clients": "C2", "cp_notifications": "N2"})
        real = agreement_drift.refusals

        def refusals(*args, **kw):
            ids = kw.get("dataset_ids") or (args[1] if len(args) > 1 else None) or []
            if "cp-notifications" in ids:
                return {"cp-notifications": object()}
            return real(*args, **kw) if args or kw else {}
        monkeypatch.setattr(agreement_drift, "refusals", refusals)
        monkeypatch.setattr(filing, "_refused", lambda dataset_ids: {})
        sc.process()
        assert sc.holder("cp-clients", Q3) == v2["C2"]
        assert sc.holder("cp-notifications", Q3) != v2["N2"]
        (rerun,) = _readers_runs(sc, v2["C2"])
        refs = [r for r in sc.results(rerun["run_key"]) if r["check_id"] in CLIENT_REFS]
        assert refs and all(r["status"] == "pass" for r in refs)


class TestDecisionDuringTheGate:

    @pytest.fixture
    def decide(self, monkeypatch):
        from click.testing import CliRunner

        from cli import filing_tui
        from cli.supply import supply_group
        from qa_tools.common import knock_on, people
        from test_carry_forward import REAL_PERSON

        monkeypatch.setattr(filing_tui, "actor_at_the_keyboard",
                            lambda: people.person_by_email(REAL_PERSON))
        monkeypatch.setattr(knock_on, "follow_up", lambda *a, **k: [])

        def run(*args):
            got = CliRunner().invoke(supply_group, ["decide", *args, "--reason", "test",
                                                    "--yes"], env={"COLUMNS": "200"})
            import re

            return got.exit_code, " ".join(re.sub(r"[│╭╮╰╯─]", " ", got.output).split())
        return run

    def test_a_decision_on_a_package_still_being_gated_is_refused(self, sc, decide):
        """Both wordings, the next-pass line where no run holds the package,
        nothing recorded, exit 75 from mothman supply decide."""
        from qa_tools.common import gate

        established(sc)
        v2 = sc.deliver("2024-08-05T10:00:00+08:00",
                        {"cp_clients": "C2", "cp_notifications": "N2"})
        sc.process(stop_before="N2")
        args = ("--operation", "promote", "--dataset", "cp-clients", "--period", Q3,
                "--supply", v2["C2"])
        code, out = decide(*args)
        assert code == 75, out
        assert "is still being checked (1 of 2 files checked); decide once it is gated." in out
        assert "It is finished by the next processing pass: mothman pipeline process" in out
        assert sc.actions(v2["C2"]) == []
        # EVERY FILE CHECKED, THE GATE STILL OWED - here held by a run, so no
        # next-pass line.
        with gate.period_lock(CP, Q3):
            sc.process()
            code, out = decide(*args)
            assert code == 75, out
            assert "is being gated (2 of 2 files checked); decide once it is gated." in out
            assert "next processing pass" not in out
        code, out = decide(*args)
        assert code == 75 and "next processing pass" in out
        assert sc.actions(v2["C2"]) == []

    @pytest.mark.parametrize("operation, dataset, extra", [
        ("promote", "cp-notifications", ("--supply", "N2")),
        ("reject", "cp-notifications", ("--supply", "N2")),
        ("demote", "cp-clients", ()),
        ("un-inherit", "cp-carers", ()),
        ("de-substitute", "cp-carers", ()),
        ("refile", "cp-notifications", ("--supply", "N2", "--to-period", Q4)),
        ("carry-forward", "cp-case-workers", ()),
    ])
    def test_a_persons_decision_while_a_gate_holds_the_period_is_refused(
            self, sc, decide, operation, dataset, extra):
        """Architect v5 B3: while an application holds 2024-Q3 a person's
        table-moving decision there is refused with exit 75 and the
        gate-running wording, and nothing is recorded."""
        from qa_tools.common import gate

        established(sc)
        v2 = sc.deliver("2024-08-05T10:00:00+08:00", {"cp_notifications": "N2"})
        sc.rules.append(own_red("N2"))
        sc.process()
        extra = tuple(v2.get(x, x) for x in extra)
        before = len([d for s in (*v2.values(),) for d in sc.decisions(s)])
        with gate.period_lock(CP, Q3):
            code, out = decide("--operation", operation, "--dataset", dataset,
                               "--period", Q3, *extra)
        assert code == 75, out
        assert "A gate is running for 2024-Q3. Nothing was changed. Try again in a moment." in out
        assert len([d for s in v2.values() for d in sc.decisions(s)]) == before


# ---------------------------------------------------------------------------
# REQ-PIPE-267
# ---------------------------------------------------------------------------

class TestPackageMateHeldBack:

    def test_clients_rechecked_against_notifications_in_the_warehouse_and_promoted(self, sc):
        """S1 green: Notifications v2 red on blank values of its own is held
        back; Client reference is re-run for Clients v2 against Notifications
        v1 and passes; Clients v2 is promoted beside Notifications v1; the
        knock-on re-runs nothing."""
        v1 = established(sc)
        sc.rules.append(own_red("N2"))
        v2 = sc.deliver("2024-08-05T10:00:00+08:00",
                        {"cp_clients": "C2", "cp_notifications": "N2"})
        sc.process()
        assert sc.holder("cp-notifications", Q3) == v1["N1"]
        assert sc.holder("cp-clients", Q3) == v2["C2"]
        (rerun,) = _readers_runs(sc, v2["C2"])
        refs = [r for r in sc.results(rerun["run_key"]) if r["check_id"] in CLIENT_REFS]
        assert refs and all(r["status"] == "pass" for r in refs)
        assert rerun["gate_application"] == _promotion(sc, v2["C2"])["gate_application"]
        # THE KNOCK-ON RE-RUNS NOTHING: every reader's counted result already
        # read Clients v2.
        others = [r for label, s in v1.items() for r in _readers_runs(sc, s)]
        assert others == [], [r["run_key"] for r in others]

    def test_clients_held_back_when_it_drops_clients_notifications_v1_points_at(self, sc):
        """S1 red: the re-run fails, Clients v2 is held back, and its
        'promotion-withheld' carries criterion 13's fields and wording naming
        Notifications v1 and the held-back Notifications v2."""
        v1 = established(sc)
        sc.rules += [own_red("N2"), cross_red("cp-notifications", "cp_clients",
                                              when={"cp_clients": "C2",
                                                    "cp_notifications": "N1"})]
        v2 = sc.deliver("2024-08-05T10:00:00+08:00",
                        {"cp_clients": "C2", "cp_notifications": "N2"})
        sc.process()
        assert sc.holder("cp-clients", Q3) == v1["C1"]
        entry = _withheld(sc, v2["C2"])
        detail = entry["held_back_detail"]
        assert entry["held_back_by"] == v2["N2"]
        assert detail["came"] == "package-mate"
        assert set(detail["against"].values()) == {v1["N1"]}
        assert set(detail["checks"]) <= set(CLIENT_REFS)
        assert entry["reason"].startswith("Held back: ")
        assert "re-checked against the Notifications" in entry["reason"]
        assert "in place in the warehouse (received" in entry["reason"]
        assert entry["reason"].rstrip().endswith(
            "received with it was held back. This supply's checks of its own data passed.")

    def test_rejecting_the_held_back_package_mate_changes_nothing(self, sc):
        """S1 step 4 (characterization): a person rejecting Notifications v2
        owes no re-evaluation and leaves Clients v2's results and decision
        unchanged."""
        established(sc)
        sc.rules.append(own_red("N2"))
        v2 = sc.deliver("2024-08-05T10:00:00+08:00",
                        {"cp_clients": "C2", "cp_notifications": "N2"})
        sc.process()
        before = (sc.decisions(v2["C2"]), [r["run_key"] for r in sc.runs(v2["C2"])])
        _reject(sc, v2["N2"], Q3)
        assert sc.owed("reevaluate") == []
        assert (sc.decisions(v2["C2"]), [r["run_key"] for r in sc.runs(v2["C2"])]) == before

    def test_promoting_it_later_rechecks_through_the_knock_on(self, sc):
        """S1 step 4's other branch: a person promoting Notifications v2
        re-checks Clients v2 through REQ-PIPE-121's knock-on - by its
        cheapest correct path (NFR 4): Clients v2's Client reference counted
        toward it is the one that read Notifications v2, the knock-on owed
        for the promotion is done, and nothing is left owed."""
        from qa_tools.common import supply_db, supply_status

        established(sc)
        sc.rules.append(own_red("N2"))
        v2 = sc.deliver("2024-08-05T10:00:00+08:00",
                        {"cp_clients": "C2", "cp_notifications": "N2"})
        sc.process()
        sc.promote_by_hand(v2["N2"], Q3, at="2024-09-20T10:00:00+08:00", follow_up=True)
        assert sc.owed("reevaluate") == []
        with supply_db.connect(read_only=True, label="pytest") as conn:
            counted = [r for r in supply_status.latest_results(conn, "cp-clients", v2["C2"])
                       if r["check_id"] in CLIENT_REFS]
        assert counted and all(r["reads"]["cp_notifications"]["supply_id"] == v2["N2"]
                               for r in counted)


class TestFirstTimePackage:

    def test_notifications_held_back_when_clients_is_held_back(self, sc):
        """S2 strict (the mirror, V4-Q1): Clients v2 red on its own data is
        held back; Notifications' Client reference is re-run for Notifications
        v2 with no Clients in the warehouse, records not evaluated and red,
        and Notifications v2 is held back with criterion 13's could-not-be-
        checked wording; a later promotion of Clients v2 by a person re-checks
        and promotes Notifications v2 through the knock-on."""
        first_time(sc)
        sc.rules.append(own_red("C2"))
        v2 = sc.deliver("2024-11-03T10:00:00+08:00",
                        {"cp_clients": "C2", "cp_notifications": "N2"})
        sc.process()
        assert sc.holder("cp-clients", Q4) is None
        assert sc.holder("cp-notifications", Q4) is None
        (rerun,) = _readers_runs(sc, v2["N2"])
        refs = [r for r in sc.results(rerun["run_key"]) if r["check_id"] in CLIENT_REFS]
        assert refs and all(r["status"] == "fail" for r in refs)
        assert all((r["extra"] or {}).get("unrunnable_code") == "held-back-with-its-package"
                   for r in refs)
        entry = _withheld(sc, v2["N2"])
        assert entry["reason"].startswith("Held back: ")
        assert ("could not be checked - no Client Register is in place in the warehouse, "
                "and the Client Register received with it was held back.") in entry["reason"]
        sc.promote_by_hand(v2["C2"], Q4, at="2024-12-20T10:00:00+08:00", follow_up=True)
        assert sc.holder("cp-notifications", Q4) == v2["N2"]

    def test_clients_promotes_alone_when_only_its_reader_is_held_back(self, sc):
        """V4-Q1: Notifications v2 red on its own data is held back, no
        readers-only run is recorded for Clients v2, and Clients v2 is
        promoted."""
        first_time(sc)
        sc.rules.append(own_red("N2"))
        v2 = sc.deliver("2024-11-03T10:00:00+08:00",
                        {"cp_clients": "C2", "cp_notifications": "N2"})
        sc.process()
        assert sc.holder("cp-clients", Q4) == v2["C2"]
        assert sc.holder("cp-notifications", Q4) is None
        assert _readers_runs(sc, v2["C2"]) == []


class TestStaggered:

    def test_waiting_partner_promoted_with_the_later_file(self, sc):
        """S3 and S2b: Notifications v2 alone at 08:40 is held back red (no
        Clients); Clients v2 alone at 09:00 passes Client reference against
        the staged Notifications v2 - both promoted in one gate application,
        no readers-only run."""
        first_time(sc)
        n2 = sc.deliver("2024-11-01T08:40:00+08:00", {"cp_notifications": "N2"})["N2"]
        sc.process()
        assert sc.holder("cp-notifications", Q4) is None
        c2 = sc.deliver("2024-11-01T09:00:00+08:00", {"cp_clients": "C2"})["C2"]
        sc.process()
        c, n = _promotion(sc, c2), _promotion(sc, n2)
        assert c["gate_application"] == n["gate_application"] is not None
        assert _readers_runs(sc, c2) == []

    def test_correction_promotes_with_the_waiting_notifications(self, sc):
        """After S2 strict leaves both held back, a clean Clients v3 arriving
        alone the next day is promoted together with the waiting
        Notifications v2."""
        first_time(sc)
        sc.rules.append(own_red("C2"))
        v2 = sc.deliver("2024-11-03T10:00:00+08:00",
                        {"cp_clients": "C2", "cp_notifications": "N2"})
        sc.process()
        assert sc.holder("cp-notifications", Q4) is None
        c3 = sc.deliver("2024-11-04T10:00:00+08:00", {"cp_clients": "C3"})["C3"]
        sc.process()
        c, n = _promotion(sc, c3), _promotion(sc, v2["N2"])
        assert c["gate_application"] == n["gate_application"] is not None

    def test_arrival_rechecked_against_the_warehouse_when_its_partner_is_red(self, sc):
        """S3b: Clients v2 waits red on its own checks; Notifications v2
        arrives alone twenty minutes later - Clients v2 joins and is not
        promoting, and Notifications v2 is gated on its Client reference
        re-run against Clients v1."""
        v1 = established(sc)
        sc.rules.append(own_red("C2"))
        c2 = sc.deliver("2024-08-05T10:00:00+08:00", {"cp_clients": "C2"})["C2"]
        sc.process()
        assert sc.holder("cp-clients", Q3) == v1["C1"]
        before = sc.decisions(c2)
        n2 = sc.deliver("2024-08-05T10:20:00+08:00", {"cp_notifications": "N2"})["N2"]
        sc.process()
        assert sc.holder("cp-notifications", Q3) == n2
        (rerun,) = _readers_runs(sc, n2)
        refs = [r for r in sc.results(rerun["run_key"]) if r["check_id"] in CLIENT_REFS]
        assert refs and all(r["status"] == "pass" for r in refs)
        assert sc.decisions(c2) == before, "a joined supply's decisions are unchanged"


class TestTransitiveGate:

    def test_three_staggered_files_promote_together(self, sc):
        """S10 re-ordered: Notifications 08:40 and Investigations 09:00 held
        back for want of Clients; Clients v2 at 09:20 - all three promoted in
        Clients v2's gate application, with no readers-only run."""
        empty_but_workers(sc)
        n2 = sc.deliver("2024-11-01T08:40:00+08:00", {"cp_notifications": "N2"})["N2"]
        sc.process()
        i2 = sc.deliver("2024-11-01T09:00:00+08:00", {"cp_investigations": "I2"})["I2"]
        sc.process()
        assert sc.holder("cp-notifications", Q4) is None
        assert sc.holder("cp-investigations", Q4) is None
        c2 = sc.deliver("2024-11-01T09:20:00+08:00", {"cp_clients": "C2"})["C2"]
        sc.process()
        apps = {_promotion(sc, s)["gate_application"] for s in (n2, i2, c2)}
        assert len(apps) == 1 and None not in apps
        assert all(_readers_runs(sc, s) == [] for s in (n2, i2, c2))

    def test_three_staggered_files_in_the_original_order(self, sc):
        """S10 in its original order: Clients v2 promotes alone at 09:00, and
        Notifications v2 and Investigations v2 promote together at 09:20."""
        empty_but_workers(sc)
        n2 = sc.deliver("2024-11-01T08:40:00+08:00", {"cp_notifications": "N2"})["N2"]
        sc.process()
        c2 = sc.deliver("2024-11-01T09:00:00+08:00", {"cp_clients": "C2"})["C2"]
        sc.process()
        assert sc.holder("cp-clients", Q4) == c2
        assert sc.holder("cp-notifications", Q4) is None
        i2 = sc.deliver("2024-11-01T09:20:00+08:00", {"cp_investigations": "I2"})["I2"]
        sc.process()
        n, i = _promotion(sc, n2), _promotion(sc, i2)
        assert n["gate_application"] == i["gate_application"] is not None
        assert _promotion(sc, c2)["gate_application"] != n["gate_application"]

    def test_mutual_waiters_join(self, sc):
        """S11: Notifications and Investigations waiting on each other are
        both joined by a third arrival."""
        empty_but_workers(sc)
        sc.deliver("2024-11-01T08:40:00+08:00", {"cp_notifications": "N2",
                                                  "cp_investigations": "I2"})
        sc.process()
        c2 = sc.deliver("2024-11-01T09:20:00+08:00", {"cp_clients": "C2"})["C2"]
        sc.process()
        assert sc.holder("cp-notifications", Q4) and sc.holder("cp-investigations", Q4)
        assert sc.holder("cp-clients", Q4) == c2


class TestCascade:

    @pytest.mark.parametrize("order", [0, 1, 2])
    def test_mutual_readers_settle_in_any_order(self, sc, monkeypatch, order):
        """S5: a zip of Clients, Notifications and Investigations v2 over
        v1s, Investigations v2 red on its own checks - the same promotions
        and hold-backs whichever order the three are listed in."""
        from qa_tools.common import gate

        real = gate.package_at

        def rotated(*a, **kw):
            p = real(*a, **kw)
            supplies = list(p.supplies)
            supplies = supplies[order:] + supplies[:order]
            return gate.Package(p.collection_id, p.period, p.delivery, p.received,
                                tuple(supplies), p.checked)
        monkeypatch.setattr(gate, "package_at", rotated)
        v1 = established(sc)
        sc.rules.append(own_red("I2"))
        v2 = sc.deliver("2024-08-05T10:00:00+08:00", {"cp_clients": "C2",
                                                       "cp_notifications": "N2",
                                                       "cp_investigations": "I2"})
        sc.process()
        assert sc.holder("cp-investigations", Q3) == v1["I1"]
        assert sc.holder("cp-clients", Q3) == v2["C2"]
        assert sc.holder("cp-notifications", Q3) == v2["N2"]


class TestRecheckEntry:

    def _refile(self, sc, supply: str, to_period: str) -> None:
        from qa_tools.common import asset_time, filing_decisions as fd, people, supply_db
        from test_carry_forward import REAL_PERSON

        dataset_id = supply.split("@", 1)[0]
        with supply_db.connect(label="pytest-refile") as conn:
            fd.apply(fd.Request(operation=fd.REFILE, dataset_id=dataset_id,
                                actor=people.person_by_email(REAL_PERSON),
                                reason="test: it is next quarter's", confirmed=True,
                                period=Q3, to_period=to_period, supply=supply),
                     effective_at=asset_time.now().isoformat(), conn=conn)

    def test_refiled_partners_are_gated_on_their_current_filing(self, sc, monkeypatch):
        """T14: a person re-files Clients v2 and Notifications v2 from 2024-Q3
        into 2024-Q4 - two owed re-checks. While Notifications v2's is owed it
        is not joined to Clients v2's application and never promoted on its
        2024-Q3 results; once both have run, each is promoted on results
        recorded for 2024-Q4."""
        from qa_tools.common import amber_setting, gate, replacement_setting, supply_db

        # A FILLED Q3 WAITS FOR A PERSON here: a resupply may not replace.
        monkeypatch.setattr(replacement_setting, "resolve",
                            lambda dataset_id, at, **kw: amber_setting.Resolved(
                                value=replacement_setting.NEVER, level="test",
                                version="test"))
        established(sc)
        first_time(sc)
        v2 = sc.deliver("2024-08-05T10:00:00+08:00",
                        {"cp_clients": "C2", "cp_notifications": "N2"})
        sc.process()
        assert sc.holder("cp-clients", Q3) != v2["C2"]
        self._refile(sc, v2["C2"], Q4)
        self._refile(sc, v2["N2"], Q4)
        owed = sc.owed("recheck")
        assert {o.supply_id for o in owed} == {v2["C2"], v2["N2"]}
        with supply_db.connect(read_only=True, label="pytest") as conn:
            assert gate.joinable(conn, "cp-notifications", v2["N2"], Q4) is None
        sc.run_owed()
        assert sc.owed("recheck") == []
        for label in ("C2", "N2"):
            entry = _promotion(sc, v2[label])
            assert entry["to_slot"] == Q4
            runs = [r for r in sc.runs(v2[label]) if r["scope"] == "full"]
            assert runs and all(r["period"] == Q4 for r in runs)

    def test_a_package_member_still_being_checked_is_not_joined(self, sc):
        """An application reaching a member of a package whose 'gate' item is
        owed neither joins nor promotes it."""
        from qa_tools.common import gate, supply_db

        established(sc)
        v2 = sc.deliver("2024-08-05T10:00:00+08:00",
                        {"cp_clients": "C2", "cp_notifications": "N2"})
        sc.process(stop_before="N2")
        with supply_db.connect(read_only=True, label="pytest") as conn:
            assert gate.joinable(conn, "cp-clients", v2["C2"], Q3) is None
            item = gate._member_item(conn, "cp-clients", v2["C2"])
        applied = gate.apply(CP, Q3, entry=gate.KNOCK_ON, checked=[item],
                             effective_at="2024-08-06T10:00:00+08:00")
        assert applied.promoted == () and _gated(sc, v2["C2"]) == []


class TestTheFixedPointEnds:

    def test_a_reevaluation_whose_result_never_counts_is_not_repeated(self, sc, monkeypatch):
        """Found on the first bootstrap after the build (TS-67's re-filed
        Notifications): a re-evaluation whose run records nothing that counts
        - its check out of scope - was owed again every round, forever (247
        runs before it was stopped). Each check is re-evaluated at most once
        per state of the period, then decided without."""
        from qa_tools.common import gate

        established(sc)
        sc.rules.append(own_red("N2"))
        calls = []
        monkeypatch.setattr(gate, "_reevaluate", lambda y, checks, *a, **k: calls.append(
            (y.supply, frozenset(checks))))
        v2 = sc.deliver("2024-08-05T10:00:00+08:00",
                        {"cp_clients": "C2", "cp_notifications": "N2"})
        sc.process()
        assert len(calls) == 1, calls
        assert calls[0][0] == v2["C2"]


class TestOnePeriodOneApplication:

    def test_a_second_application_in_the_same_period_is_left_owed(self, sc):
        """The pass gating a package while another application holds the
        period: it finds the lock held, leaves its item owed, never waits,
        and the next pass gates it."""
        from qa_tools.common import gate

        established(sc)
        v2 = sc.deliver("2024-08-05T10:00:00+08:00",
                        {"cp_clients": "C2", "cp_notifications": "N2"})
        with gate.period_lock(CP, Q3) as held:
            assert held
            sc.process()
            assert _gated(sc, v2["C2"]) == [] and _gated(sc, v2["N2"]) == []
            assert len(sc.owed("gate")) == 1
        sc.run_owed()
        assert sc.holder("cp-clients", Q3) == v2["C2"]
        assert sc.owed("gate") == []

    def test_a_failed_move_promotes_nothing(self, sc, monkeypatch):
        """The second of two promotions fails: neither is promoted, the
        application is ABANDONED and owed as a 'gate' item, and its retry
        re-runs no tool."""
        from qa_tools.common import gate, promotion, qa_store, supply_db

        established(sc)
        v2 = sc.deliver("2024-08-05T10:00:00+08:00",
                        {"cp_clients": "C2", "cp_notifications": "N2"})
        real = promotion.promote
        calls = []

        def flaky(conn, **kw):
            calls.append(kw["supply"])
            if len(calls) == 2:
                raise RuntimeError("the second move failed (test)")
            return real(conn, **kw)
        monkeypatch.setattr(promotion, "promote", flaky)
        sc.process()
        assert sc.holder("cp-clients", Q3) != v2["C2"]
        assert sc.holder("cp-notifications", Q3) != v2["N2"]
        with supply_db.connect(read_only=True, label="pytest") as conn:
            ended = [e for (e,) in conn.execute(
                f'SELECT ended FROM "{qa_store.SCHEMA}".gate_application ORDER BY id')]
            runs = conn.execute(f'SELECT count(*) FROM "{qa_store.SCHEMA}".run').fetchone()[0]
        assert gate.ABANDONED in ended
        (owed,) = sc.owed("gate")
        assert owed.caused_by_application is not None
        monkeypatch.setattr(promotion, "promote", real)
        sc.run_owed()
        assert sc.holder("cp-clients", Q3) == v2["C2"]
        with supply_db.connect(read_only=True, label="pytest") as conn:
            assert conn.execute(f'SELECT count(*) FROM "{qa_store.SCHEMA}".run'
                                ).fetchone()[0] == runs

    def test_the_knock_on_is_not_blocked_by_its_own_application(self, sc):
        """After an application promotes Clients v2, its knock-on takes the
        period lock and runs in the same pass - nothing is left owed."""
        established(sc)
        sc.deliver("2024-08-05T10:00:00+08:00", {"cp_clients": "C2"})
        sc.process()
        assert sc.owed("reevaluate") == []

    def test_a_cascade_shows_only_its_last_round(self, sc):
        """An application's runs share ONE point, keyed on the application
        (REQ-PIPE-279's point key, amended)."""
        from qa_tools.common import qa_results_reader, qa_store, supply_db

        established(sc)
        sc.rules.append(own_red("I2"))
        sc.deliver("2024-08-05T10:00:00+08:00", {"cp_clients": "C2", "cp_notifications": "N2",
                                                  "cp_investigations": "I2"})
        sc.process()
        with supply_db.connect(read_only=True, label="pytest") as conn:
            apps = {k: a for k, a in conn.execute(
                f'SELECT run_key, gate_application FROM "{qa_store.SCHEMA}".run '
                "WHERE gate_application IS NOT NULL").fetchall()}
            facts = qa_results_reader.run_facts("child-protection-family-support", CP,
                                                conn=conn)
        assert apps, "precondition: the cascade re-checked something"
        for key, app in apps.items():
            assert facts[key]["cause"] == f"gate:{app}"


class TestAnApplicationCountsOnlyOnceSettled:

    def test_unsettled_and_abandoned_results_count_toward_nothing(self, sc):
        """Criterion 12: a re-evaluation inside an application counts toward
        no status, page or count until it SETTLES, and an ABANDONED one never
        - qa.run_visible, which every reader and the dashboard build read
        through, filters on it; the lifecycle is gate.py's."""
        from qa_tools.common import gate, qa_store, supply_db, supply_status

        established(sc)
        sc.rules.append(own_red("N2"))
        v2 = sc.deliver("2024-08-05T10:00:00+08:00",
                        {"cp_clients": "C2", "cp_notifications": "N2"})
        sc.process()
        (rerun,) = _readers_runs(sc, v2["C2"])
        key = rerun["run_key"]

        def visible(conn) -> bool:
            return bool(conn.execute(f'SELECT 1 FROM "{qa_store.SCHEMA}".run_visible '
                                     "WHERE run_key = ?", [key]).fetchall())

        def counted(conn) -> bool:
            return any(r["run_id"] == key for r in supply_status.results_about(
                conn, "cp-clients", v2["C2"], view=supply_status.View()).shown)

        with supply_db.connect(label="pytest") as conn:
            assert visible(conn) and counted(conn), "settled: it counts"
            for how in (None, gate.ABANDONED):
                app = gate.start(conn, collection_id=CP, period=Q3, entry=gate.RECHECK)
                if how:
                    gate.abandon(conn, app)
                conn.execute(f'UPDATE "{qa_store.SCHEMA}".run SET gate_application = ? '
                             "WHERE run_key = ?", [app, key])
                assert not visible(conn) and not counted(conn), how or "unsettled"
                assert gate.counted(conn, app) is False
            gate.settle(conn, app)  # an abandoned one stays abandoned
            assert not visible(conn)


def _reject(sc, supply: str, period: str) -> None:
    from qa_tools.common import hierarchy, rejection, supply_db, supply_files

    dataset_id = supply.split("@", 1)[0]
    ds = hierarchy.dataset(dataset_id)
    with supply_db.connect(label="pytest-reject") as conn:
        rejection.reject(conn, agency_id=ds.agency_id, collection_id=ds.collection_id,
                         dataset_id=dataset_id, supply=supply,
                         physical_tables=supply_files.tables_in(conn, dataset_id, supply,
                                                                supply_db.STAGING_SCHEMA),
                         actor="fixture@example.org", reason="test: turned down",
                         effective_at="2024-09-20T10:00:00+08:00", from_slot=period)


def test_every_table_is_named():
    assert set(V1) == set(TABLES)
