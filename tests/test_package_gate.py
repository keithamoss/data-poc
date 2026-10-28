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


    def test_a_contested_pair_waiting_for_its_package_is_not_a_failure(self, sc):
        """REQ-PIPE-266 criterion 3 for a CONTESTED PAIR (post-build-review
        #274 D5): two Client Register files and a Notifications file received
        together, the pair checked and Notifications not yet. The pass reports
        the pair as checked, waiting for its package - never a failure. It
        rebuilt the supply id without the pair's '#1', so the package lookup
        found nothing and the waiting pair was failed."""
        from gate_support import CP_REF_RUN_ID
        from qa_tools.common import asset_time, delivery, processing_pass

        established(sc)
        at = asset_time.parse_instant("2024-08-05T10:00:00+08:00", "test")
        source = sc.raw_dir / CP_REF_RUN_ID
        clients = (source / "cp_clients.csv").read_text()
        files = {"cp_clients.csv": clients, "cp_clients_part2.csv": clients,
                 "cp_notifications.csv": (source / "cp_notifications.csv").read_text()}
        delivery.write_delivery("cp-pair-zip", files, received_at={n: at for n in files},
                                deliveries_dir=sc.deliveries, receipts_dir=sc.receipts)
        sc.labels[f"cp-notifications@{asset_time.arrival_key(at)}"] = "N2"
        sc.process(stop_before="N2")
        found = sc.arrivals()
        (pair,) = [a for a in found if a.delivery_name == "cp-pair-zip"
                   and "cp-clients" in a.files_by_dataset]
        assert len(pair.files_by_dataset["cp-clients"]) == 2, "precondition: a pair"
        assert len(sc.owed("gate")) == 1, "precondition: its package's gate is owed"
        report = processing_pass.PassReport()
        processing_pass._one(pair, found, at.isoformat(), "pytest@example.org", report,
                             lambda *a: None)
        assert report.left_waiting == [pair.run_id]
        assert report.failures == []


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
        before, held = _everything_recorded(), _warehouse(sc, Q3)
        with gate.period_lock(CP, Q3):
            code, out = decide("--operation", operation, "--dataset", dataset,
                               "--period", Q3, *extra)
        assert code == 75, out
        assert "A gate is running for 2024-Q3. Nothing was changed. Try again in a moment." in out
        # NOTHING RECORDED ANYWHERE - no decision, filing, owed item or
        # not-supplied mark about any supply - and the warehouse holds exactly
        # what it held (criterion 16).
        assert _everything_recorded() == before
        assert _warehouse(sc, Q3) == held


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

    def test_a_hold_back_against_another_supply_is_not_a_repeat(self, sc):
        """REQ-PIPE-266 criterion 9's repeat is judged on the entry's
        structured fields - ALL of them that say what it was checked against
        (post-build-review #274): the same cause and checks, re-checked against
        a different supply in the warehouse, is a new hold-back."""
        from qa_tools.common import gate, supply_db

        v1 = established(sc)
        sc.rules += [own_red("N2"), cross_red("cp-notifications", "cp_clients",
                                              when={"cp_clients": "C2",
                                                    "cp_notifications": "N1"})]
        v2 = sc.deliver("2024-08-05T10:00:00+08:00",
                        {"cp_clients": "C2", "cp_notifications": "N2"})
        sc.process()
        detail = _withheld(sc, v2["C2"])["held_back_detail"]
        member = gate.Member(item={"dataset_id": "cp-clients", "supply": v2["C2"]},
                             checked_now=True)

        def cause(against):
            return gate.Cause(checks=tuple(detail["checks"]), against=against,
                              by=detail["by"], by_dataset=detail["by_dataset"],
                              by_received=detail["by_received"], came=detail["came"])
        with supply_db.connect(read_only=True, label="pytest") as conn:
            assert gate._same_holdback(conn, member, cause(detail["against"]))
            moved = {c: "cp-notifications@202408010000000800" for c in detail["against"]}
            assert moved != detail["against"] and v1
            assert not gate._same_holdback(conn, member, cause(moved))

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

    def test_a_hold_back_is_said_once_until_something_moves(self, sc):
        """A re-gate that finds a held-back supply still red only for want of a
        table writes nothing more (Keith, 2026-10-25, answer 2a, as
        promotion._record_refused kept 'once since the supply last moved'):
        TS-75's Notifications got a second, differently worded note from the
        knock-on right after its package's hold-back."""
        sc.rules.append(own_red("C2"))
        # A FIRST-TIME ZIP OF ALL SIX (TS-75's shape): Carers and Case Workers
        # promote, and the knock-on their promotion owes re-gates the readers.
        got = sc.deliver("2024-07-25T10:00:00+08:00", {
            "cp_clients": "C2", "cp_notifications": "N2", "cp_investigations": "I2",
            "cp_placements": "P2", "cp_carers": "K2", "cp_case_workers": "W2"})
        sc.process()
        sc.run_owed()
        assert sc.holder("cp-carers", Q3) == got["K2"], "precondition: a move to knock on"
        for label in ("N2", "I2", "P2"):
            assert _gated(sc, got[label]) == ["promotion-withheld"], (label,
                                                                      sc.actions(got[label]))

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

    def test_one_application_promotes_at_one_instant_after_every_members_decision(
            self, sc, monkeypatch):
        """post-build-review #284 (1), Keith 2026-10-29, option (b): each
        arrival keeps its own seeded lag, so an early file's hold-back may take
        effect AFTER the later file whose application promotes it. The WHOLE
        application is floored at the latest decision already recorded across
        all its members, so every promotion in it shares ONE effective instant
        (REQ-PIPE-266 criterion 4) and none comes before a member's own
        hold-back; the completing file gives up its own instant. REJECTED: the
        per-member floor of #276 (b), which split one application across
        several instants."""
        from datetime import timedelta

        from qa_tools.common import supply_status
        from qa_tools.tools import orchestrate

        def lag(collection_id, arrival):
            early = "cp-clients" not in (arrival.files_by_dataset or {})
            return (arrival.received_at + timedelta(days=5 if early else 0, hours=1)).isoformat()
        monkeypatch.setattr(orchestrate, "effective_at_of", lag)
        empty_but_workers(sc)
        n2 = sc.deliver("2024-11-01T08:40:00+08:00", {"cp_notifications": "N2"})["N2"]
        sc.process()
        i2 = sc.deliver("2024-11-01T09:00:00+08:00", {"cp_investigations": "I2"})["I2"]
        sc.process()
        c2 = sc.deliver("2024-11-01T09:20:00+08:00", {"cp_clients": "C2"})["C2"]
        sc.process()

        def at(value):
            return supply_status.instant(value)
        promoted = {s: _promotion(sc, s) for s in (n2, i2, c2)}
        assert len({p["gate_application"] for p in promoted.values()}) == 1
        instants = {at(p["effective_at"]) for p in promoted.values()}
        assert len(instants) == 1, {s: p["effective_at"] for s, p in promoted.items()}
        latest = max(at(_withheld(sc, s)["effective_at"]) for s in (n2, i2))
        assert instants == {latest}, (instants, latest)
        assert latest == at("2024-11-06T10:00:00+08:00"), \
            "Investigations' hold-back, the latest decision across the members"

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
        per state of the period; one that still counts nothing then holds
        its supply back not judged (Keith, 2026-10-25, 1a), never decided
        without."""
        from qa_tools.common import gate

        established(sc)
        sc.rules.append(own_red("N2"))
        calls = []
        real = gate._reevaluate

        def first_records_nothing(y, checks, *a, **k):
            # (causes, members, warehouse, application, period, run_by)
            calls.append((y.supply, frozenset(checks), a[3]))
            if len(calls) > 1:
                return real(y, checks, *a, **k)
            return None
        monkeypatch.setattr(gate, "_reevaluate", first_records_nothing)
        v2 = sc.deliver("2024-08-05T10:00:00+08:00",
                        {"cp_clients": "C2", "cp_notifications": "N2"})
        sc.process()
        # ONCE PER APPLICATION: the package's re-evaluated Clients v2 once and
        # stopped; the retry is a new application (the knock-on it is owed).
        assert calls[0][0] == v2["C2"]
        assert [c[2] for c in calls].count(calls[0][2]) == 1, calls
        assert len(calls) == 2, calls
        # THE OUTCOME, not only the count: Notifications v2 is refused on its
        # own red; Clients v2 is held back NOT JUDGED rather than promoted
        # without the check (Keith, 2026-10-25, answer 1a), and the knock-on
        # it is owed re-runs the check against the warehouse, where it counts
        # - so Clients v2 is promoted WITH it, after the hold-back.
        assert _gated(sc, v2["N2"]) == ["promotion-refused"]
        assert sc.holder("cp-notifications", Q3) != v2["N2"]
        assert _gated(sc, v2["C2"]) == ["promotion-withheld", "promote"]
        assert sc.holder("cp-clients", Q3) == v2["C2"]
        assert _withheld(sc, v2["C2"])["held_back_detail"]["not_counted"]
        assert sc.owed("gate") == [] and sc.owed("recheck") == []
        assert sc.owed("reevaluate") == []
        from qa_tools.common import gate, qa_store, supply_db

        with supply_db.connect(read_only=True, label="pytest") as conn:
            ended = {e for (e,) in conn.execute(
                f'SELECT ended FROM "{qa_store.SCHEMA}".gate_application')}
        assert ended == {gate.SETTLED}

    def test_a_check_whose_reevaluation_never_counts_does_not_promote_without_it(
            self, sc, monkeypatch):
        """Keith, 2026-10-25, answer 1a (post-build-review #274 D2): a supply
        whose cross-table check still does not count after the fixed point's
        re-evaluation is HELD BACK as not judged until it counts - its
        'promotion-withheld' says so - and its retry STAYS OWED: the
        knock-on retrying it, finding the check still counting nothing,
        leaves the item owed for the next pass rather than clearing it, and
        never loops within one."""
        from qa_tools.common import gate, recheck

        established(sc)
        sc.rules.append(own_red("N2"))
        monkeypatch.setattr(gate, "_reevaluate", lambda *a, **k: None)
        real = recheck.execute
        readers_runs = []

        def nothing_for_readers(**kw):
            if kw["purpose"].get("scope") == "readers":
                readers_runs.append(kw["supply_id"])
                return None, []
            return real(**kw)
        monkeypatch.setattr(recheck, "execute", nothing_for_readers)
        v2 = sc.deliver("2024-08-05T10:00:00+08:00",
                        {"cp_clients": "C2", "cp_notifications": "N2"})
        sc.process()
        assert sc.holder("cp-clients", Q3) != v2["C2"]
        assert _gated(sc, v2["C2"]) == ["promotion-withheld"]
        entry = _withheld(sc, v2["C2"])
        assert entry["held_back_by"] == v2["N2"]
        assert set(entry["held_back_detail"]["not_counted"]) <= set(CLIENT_REFS)
        assert entry["reason"].startswith("Held back, not judged: ")
        assert "re-checked by the next processing pass" in entry["reason"]
        (owed,) = sc.owed("reevaluate")
        assert owed.period == Q3 and "cp_notifications" in owed.tables
        assert readers_runs.count(v2["C2"]) == 1, readers_runs
        # THE NEXT PASS RETRIES IT ONCE, and it is still owed and not judged.
        (outcome,) = sc.run_owed()
        assert not outcome.completed and outcome.not_judged and outcome.status == "red"
        assert [o.id for o in sc.owed("reevaluate")] == [owed.id]
        assert readers_runs.count(v2["C2"]) == 2, readers_runs
        assert _gated(sc, v2["C2"]) == ["promotion-withheld"]
        assert sc.holder("cp-clients", Q3) != v2["C2"]
        from qa_tools.common import processing_pass

        assert not processing_pass._owed_failure(outcome)


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
        assert sc.holder("cp-notifications", Q3) == v2["N2"]
        with supply_db.connect(read_only=True, label="pytest") as conn:
            assert conn.execute(f'SELECT count(*) FROM "{qa_store.SCHEMA}".run'
                                ).fetchone()[0] == runs
        # THE RETRY TAKES EFFECT WHEN THE FIRST ATTEMPT WOULD HAVE (post-build-
        # review #274 D1): at the instant the arrival that completed the
        # package gives - never the wall clock, which made a replayed history
        # promote "today" and differ between two bootstraps.
        assert _promotion(sc, v2["C2"])["effective_at"] == _promotion(
            sc, v2["N2"])["effective_at"] == _first_attempts_instant(sc, v2)

    def test_a_failed_move_in_a_knock_on_is_owed_for_every_reader(self, sc, monkeypatch):
        """Post-build-review #274 D6: a knock-on re-gating two waiting readers
        from different deliveries, its second move failing. Nothing promotes,
        and BOTH are gated again by the next pass - the retry was owed over the
        first reader's package only, and the knock-on cleared its own item
        without looking at the failure, so the second reader waited forever."""
        from qa_tools.common import decision_log, promotion

        # NOTIFICATIONS AND PLACEMENTS both read the Client Register and
        # neither reads the other, so no verdict joins them into one package's
        # retry - each has to be owed its own.
        first_time(sc)
        n = sc.deliver("2024-11-01T10:00:00+08:00", {"cp_notifications": "N2"})
        p = sc.deliver("2024-11-02T10:00:00+08:00", {"cp_placements": "P2"})
        sc.process()
        p1 = sc.holder("cp-placements", Q4)
        assert sc.holder("cp-notifications", Q4) is None, "precondition: N2 waits"
        assert p1 != p["P2"], "precondition: P2 waits"
        c = sc.deliver("2024-11-03T10:00:00+08:00", {"cp_clients": "C2"})
        sc.rules.append(own_red("C2"))
        sc.process()
        real = promotion.promote
        moves = []

        def flaky(conn, **kw):
            if kw.get("actor_kind") == decision_log.RULE:
                moves.append(kw["supply"])
                if len(moves) == 2:
                    raise RuntimeError("the second move failed (test)")
            return real(conn, **kw)
        monkeypatch.setattr(promotion, "promote", flaky)
        sc.promote_by_hand(c["C2"], Q4, at="2024-11-10T10:00:00+08:00", follow_up=True)
        assert len(moves) == 2, f"precondition: the knock-on moved two readers, {moves}"
        assert sc.holder("cp-notifications", Q4) is None
        assert sc.holder("cp-placements", Q4) == p1
        monkeypatch.setattr(promotion, "promote", real)
        sc.run_owed()
        assert sc.holder("cp-notifications", Q4) == n["N2"]
        assert sc.holder("cp-placements", Q4) == p["P2"]
        assert sc.owed() == []
        # AFTER THE PROMOTION THAT CAUSED THE KNOCK-ON, never at the readers'
        # own earlier arrivals (post-build-review #274 D1's rule, for a retry).
        cause = _promotion(sc, c["C2"])["effective_at"]
        assert _promotion(sc, n["N2"])["effective_at"] >= cause
        assert _promotion(sc, p["P2"])["effective_at"] >= cause

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

        from qa_tools.common import supply_status

        established(sc)
        # TWO ROUNDS: Investigations v2 is red on its own, so round one
        # re-checks Clients v2 and Notifications v2 against Investigations v1;
        # Notifications v2 fails that and is held back, so round two re-checks
        # Clients v2 again, against Notifications v1.
        sc.rules += [own_red("I2"), cross_red("cp-notifications", "cp_investigations",
                                              when={"cp_investigations": "I1",
                                                    "cp_notifications": "N2"})]
        v2 = sc.deliver("2024-08-05T10:00:00+08:00", {
            "cp_clients": "C2", "cp_notifications": "N2", "cp_investigations": "I2"})
        sc.process()
        with supply_db.connect(read_only=True, label="pytest") as conn:
            runs = conn.execute(
                f'SELECT run_key, supply_id, gate_application, readers_checks FROM '
                f'"{qa_store.SCHEMA}".run WHERE gate_application IS NOT NULL '
                "ORDER BY run_seq").fetchall()
            facts = qa_results_reader.run_facts("child-protection-family-support", CP,
                                                conn=conn)
            newest = {r["check_id"]: r for r in supply_status.latest_results(
                conn, "cp-clients", v2["C2"])}
        rounds = [r for r in runs if r[1] == v2["C2"]]
        assert len(rounds) == 2, f"precondition: Clients v2 re-checked twice, {runs}"
        # ONE POINT PER SUPPLY: every run of the application shares its cause.
        for key, supply, app, _checks in runs:
            assert facts[key]["cause"] == f"gate:{app}"
        assert len({facts[k]["cause"] for k, *_ in rounds}) == 1
        # THE LAST ROUND SHOWN: each check either round re-ran reads as the
        # newest round that ran it, the second against Notifications v1.
        last = {}
        for key, _supply, _app, checks in rounds:
            for check in checks:
                last[check] = key
        assert last
        for check, key in last.items():
            assert newest[check]["run_id"] == key, check
        for check in rounds[1][3]:
            assert newest[check]["reads"]["cp_notifications"]["supply_id"] == sc.holder(
                "cp-notifications", Q3) != v2["N2"]


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


class TestAFiledSupplyWithNoReceipt:

    def test_it_is_reported_not_skipped(self, sc, monkeypatch):
        """A supply filed to a period whose receipt row is missing has no
        package to read: the gate says so as a failure of that supply rather
        than skipping it in silence (post-build-review #274)."""
        from qa_tools.common import gate

        established(sc)
        v2 = sc.deliver("2024-08-05T10:00:00+08:00", {"cp_clients": "C2"})
        monkeypatch.setattr(gate, "package_of", lambda *a, **k: None)
        sc.process()
        (arrival,) = [a for a in sc.arrivals() if sc.label_of(a) == "C2"]
        got = gate.after_arrival(CP, arrival, effective_at="2024-08-06T10:00:00+08:00")
        assert "no receipt is recorded" in got.failed["cp-clients"]
        assert v2["C2"] in got.failed["cp-clients"]


def _first_attempts_instant(sc, supplies: dict):
    """The effective instant the gate gives the package `supplies` came in,
    by the arrival path's own rule, for the arrival processed last."""
    from qa_tools.common import asset_time, promotion
    from qa_tools.tools import orchestrate

    mine = set(supplies.values())
    (last,) = [a for a in sorted(sc.arrivals(), key=lambda a: (a.received_at, a.sequence,
                                                                a.run_id))
               if f"{next(iter(a.files_by_dataset))}@"
               f"{asset_time.arrival_key(a.received_at)}" in mine][-1:]
    return promotion.effective_at_for(
        last.received_at, seed=last.run_id, before=promotion.next_receipt(last),
        within=orchestrate._claim_window(CP, last))


def _everything_recorded() -> dict:
    """How many rows each record a decision can write holds."""
    from qa_tools.common import qa_store, supply_db

    s = qa_store.SCHEMA
    with supply_db.connect(read_only=True, label="pytest") as conn:
        return {t: conn.execute(f'SELECT count(*) FROM "{s}".{t}').fetchone()[0]
                for t in ("decision", "filing", "owed_run", "gate_application")}


def _warehouse(sc, period: str) -> dict:
    return {t: sc.holder("cp-" + t[3:].replace("_", "-"), period) for t in TABLES}


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


def test_the_period_lock_has_an_advisory_lock_space_of_its_own():
    """Every advisory-lock space this project takes is its own: the period
    lock shared 51513 with a run attempt's lock (qa_store.ATTEMPT_LOCK_SPACE),
    so a hash collision between a period key and a run key would have read
    one as the other."""
    from qa_tools.common import gate, processing_pass, qa_store, recheck

    spaces = [gate.PERIOD_LOCK_SPACE, qa_store.ATTEMPT_LOCK_SPACE, recheck.OWED_CLAIM_SPACE,
              processing_pass.PASS_LOCK_SPACE, processing_pass.ARRIVAL_LOCK_SPACE]
    assert len(set(spaces)) == len(spaces), spaces
