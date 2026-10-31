"""Settling a contested pair so that no file of it is this period's supply
re-checks the datasets whose checks the contest stopped (REQ-PIPE-211).

A Child Protection cp_clients pair arrives in 2025-Q1 with a Notifications
supply; Investigations v1 and Placements v1 are already promoted there. Every
check reading cp_clients - Notifications', Investigations' and Placements' -
records not evaluated, contested, while the two files wait to be settled.
Driven through the real lifecycle with each tool's evaluation stood in for
(tests/gate_support.py), then settled through filing_decisions.apply - the
one path every route shares - or through the terminal's own settle flow and
`mothman supply decide --operation choose-file`.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from gate_support import CP_REF_RUN_ID, Scenario, install_fake_tools, pin_replacement_setting
from test_package_gate import Q4, first_time

PAIR = ("cp_clients.csv", "cp_clients_part2.csv")
PIPED = {"NO_COLOR": "1", "COLUMNS": "80", "TERM": "dumb"}


@pytest.fixture
def sc(private_supply_dsn, cp_raw_dir, tmp_path, monkeypatch):
    scenario = Scenario(root=tmp_path, raw_dir=Path(cp_raw_dir))
    install_fake_tools(monkeypatch, scenario)
    pin_replacement_setting(monkeypatch)
    return scenario


@pytest.fixture
def person(monkeypatch):
    from cli import filing_tui
    from qa_tools.common import people
    from test_carry_forward import REAL_PERSON

    monkeypatch.setattr(filing_tui, "actor_at_the_keyboard",
                        lambda: people.person_by_email(REAL_PERSON))
    return people.person_by_email(REAL_PERSON)


def contested(sc) -> dict:
    """2025-Q1 (first_time: Case Workers, Carers, Investigations v1 and
    Placements v1 in the warehouse) and a zip of two Client Register files
    and Notifications v2. Returns {label: supply}."""
    from qa_tools.common import asset_time, delivery

    got = first_time(sc)
    at = asset_time.parse_instant("2024-11-03T10:00:00+08:00", "test")
    source = sc.raw_dir / CP_REF_RUN_ID
    clients = (source / "cp_clients.csv").read_text()
    files = {PAIR[0]: clients, PAIR[1]: clients,
             "cp_notifications.csv": (source / "cp_notifications.csv").read_text()}
    delivery.write_delivery("cp-pair-zip", files, received_at={n: at for n in files},
                            deliveries_dir=sc.deliveries, receipts_dir=sc.receipts)
    key = asset_time.arrival_key(at)
    sc.labels[f"cp-notifications@{key}"] = "N2"
    sc.process()
    out = {"pair": f"cp-clients@{key}#1", "N2": f"cp-notifications@{key}",
           "I1": got["I1"], "P1": got["P1"]}
    assert _contested_reads(sc, out), "precondition: the contest stopped its readers"
    return out


def _counted_reading_clients(sc, dataset_id: str, supply: str) -> list[dict]:
    """The newest counted result per check, in 2025-Q1, of every check of
    this supply that reads cp_clients (REQ-PIPE-269 criterion 7)."""
    from qa_tools.common import supply_db, supply_status

    with supply_db.connect(read_only=True, label="pytest") as conn:
        latest = supply_status.latest_results(conn, dataset_id, supply,
                                              view=supply_status.View(period=Q4))
    return [r for r in latest if "cp_clients" in (r.get("reads") or {})
            or "cp_clients" in (r.get("unrunnable_tables") or [])]


def _absent_and_contested(record: dict) -> bool:
    read = (record.get("reads") or {}).get("cp_clients") or {}
    return read.get("state") == "ABSENT" and bool(read.get("contested"))


def _contested_reads(sc, got) -> bool:
    return any(_absent_and_contested(r) for label in ("N2", "I1", "P1")
               for r in _counted_reading_clients(sc, got[label].split("@")[0], got[label]))


def _settle(sc, got, answers, actor) -> int:
    """A person's settlement through filing_decisions.apply, its owed work
    then completed as the processing pass completes it. Returns the
    choose-file entry's id."""
    from qa_tools.common import filing_decisions as fd, supply_db

    request = fd.Request(operation=fd.CHOOSE_FILE, dataset_id="cp-clients", actor=actor,
                         reason="test: settled", period=Q4, supply=got["pair"],
                         confirmed=True, file_outcomes=tuple(answers))
    with supply_db.connect(read_only=True, label="pytest") as conn:
        key = fd.consequences(conn, request).key
    import dataclasses

    fd.apply(dataclasses.replace(request, acknowledged=key or None),
             effective_at="2024-11-10T10:00:00+08:00")
    with supply_db.connect(read_only=True, label="pytest") as conn:
        (entry,) = conn.execute(
            "SELECT max(id) FROM qa.decision WHERE action = 'choose-file'").fetchone()
    return entry


def _reject_both():
    from qa_tools.common import settlement

    return [settlement.Answer(PAIR[0], settlement.REJECT),
            settlement.Answer(PAIR[1], settlement.REJECT)]


def _assert_readers_rechecked(sc, got, entry, *, code=None):
    """Criterion 10's post-condition for the waiting sibling and a promoted
    reader: no counted result is ABSENT and contested, and each names the
    settlement as its cause."""
    from qa_tools.common import supply_db

    for label in ("N2", "I1"):
        dataset_id = got[label].split("@")[0]
        counted = _counted_reading_clients(sc, dataset_id, got[label])
        assert counted, (label, "a reader must have checks reading cp_clients")
        assert not any(_absent_and_contested(r) for r in counted), (label, counted)
        with supply_db.connect(read_only=True, label="pytest") as conn:
            causes = {conn.execute("SELECT caused_by_decision FROM qa.run WHERE run_key = ?",
                                   [r["run_id"]]).fetchone()[0] for r in counted}
        assert causes == {entry}, (label, causes, entry)
        if code is not None:
            assert {r.get("unrunnable_code") for r in counted} == {code}, (label, counted)


# ---------------------------------------------------------------------------
# Criterion 10 - today's defect, written first
# ---------------------------------------------------------------------------

class TestTheReadersAreReCheckedWhenNoFileStays:

    def test_reject_both_rechecks_the_readers_as_rejected(self, sc, person):
        got = contested(sc)
        entry = _settle(sc, got, _reject_both(), person)
        sc.run_owed()
        _assert_readers_rechecked(sc, got, entry, code="rejected")

    def test_one_rejected_and_one_refiled_rechecks_the_readers(self, sc, person):
        """The mixed settlement's reason is slot_state's one judgement (Keith,
        2026-10-24, open question 1 = A): the readers are re-checked and none
        is left contested, whatever the reason reads."""
        from qa_tools.common import settlement

        got = contested(sc)
        entry = _settle(sc, got, [settlement.Answer(PAIR[0], settlement.REJECT),
                                  settlement.Answer(PAIR[1], settlement.REFILE, "2025-Q2")],
                        person)
        sc.run_owed()
        _assert_readers_rechecked(sc, got, entry)

    def test_both_refiled_out_gives_the_clocks_reason(self, sc, person):
        """CHECK AT BUILD (decision): a settlement re-filing BOTH files out
        leaves the slot read by slot_state.left_by_refile, so the readers get
        the clock's reason - never RETURNED's 'staged awaiting decision'."""
        from qa_tools.common import period_schema, settlement

        got = contested(sc)
        entry = _settle(sc, got, [settlement.Answer(PAIR[0], settlement.REFILE, "2025-Q2"),
                                  settlement.Answer(PAIR[1], settlement.REFILE, "2025-Q3")],
                        person)
        sc.run_owed()
        _assert_readers_rechecked(sc, got, entry)
        codes = {r.get("unrunnable_code") for r in _counted_reading_clients(
            sc, "cp-notifications", got["N2"])}
        assert codes <= {period_schema.PAST_DUE, period_schema.NOT_YET_DUE}, codes


# ---------------------------------------------------------------------------
# Criterion 11 - regression tests, already true before this requirement
# ---------------------------------------------------------------------------

class TestTheOtherOutcomesAlreadyReCheck:

    def test_a_file_chosen_as_the_supply_rechecks_the_waiting_readers(self, sc, person):
        from qa_tools.common import settlement

        got = contested(sc)
        _settle(sc, got, [settlement.Answer(PAIR[0], settlement.SUPPLY),
                          settlement.Answer(PAIR[1], settlement.REJECT)], person)
        sc.run_owed()
        counted = _counted_reading_clients(sc, "cp-notifications", got["N2"])
        assert counted and not any(_absent_and_contested(r) for r in counted)

    def test_a_later_file_superseding_the_pair_rechecks_the_waiting_readers(self, sc):
        got = contested(sc)
        sc.deliver("2024-11-05T10:00:00+08:00", {"cp_clients": "C3"})
        sc.process()
        sc.run_owed()
        counted = _counted_reading_clients(sc, "cp-notifications", got["N2"])
        assert counted and not any(_absent_and_contested(r) for r in counted)

    def test_a_settlements_owed_runs_come_before_its_reevaluation(self, sc, person):
        """Criterion 7: by owed_at then id, the re-filed file's own QA run is
        completed before the re-evaluation of the period's readers."""
        from qa_tools.common import recheck, settlement

        got = contested(sc)
        _settle(sc, got, [settlement.Answer(PAIR[0], settlement.REJECT),
                          settlement.Answer(PAIR[1], settlement.REFILE, "2025-Q2")], person)
        kinds = [o.kind for o in sc.owed()]
        assert recheck.RECHECK in kinds and recheck.REEVALUATE in kinds, kinds
        assert kinds.index(recheck.RECHECK) < kinds.index(recheck.REEVALUATE), kinds
        done = sc.run_owed()
        first_readers = next(i for i, o in enumerate(done) if o.run_key and "__r" in o.run_key
                             and not o.run_key.startswith("cp_clients"))
        first_refiled = next(i for i, o in enumerate(done) if o.run_key
                             and o.run_key.startswith("cp_clients"))
        assert first_refiled < first_readers, [o.run_key for o in done]


# ---------------------------------------------------------------------------
# Criteria 12 to 17 - the terminal
# ---------------------------------------------------------------------------

def _flat(text: str) -> str:
    return " ".join(re.sub(r"[│╭╮╰╯─]", " ", text).split())


def _readers_section(out: str) -> str:
    flat = _flat(out)
    start = flat.index("Datasets that read cp-clients in 2025-Q1, re-checked:")
    return flat[start:]


class TestTheTerminal:

    def test_the_warning_names_the_readers_rechecked_while_you_wait(self, sc, person):
        """Criterion 12: a note, shaped like the QA-runs note and never part
        of the key, naming the datasets by id."""
        from qa_tools.common import filing_decisions as fd, supply_db

        got = contested(sc)
        request = fd.Request(operation=fd.CHOOSE_FILE, dataset_id="cp-clients", actor=person,
                             reason="t", period=Q4, supply=got["pair"],
                             file_outcomes=tuple(_reject_both()))
        with supply_db.connect(read_only=True, label="pytest") as conn:
            shown = fd.consequences(conn, request)
        (note,) = [n for n in shown.notes if "datasets that read cp-clients" in n]
        # P7 (CLI UX critic): no dangling 'Then', and the likely red said
        # BEFORE the person confirms.
        assert note == ("After settling, the cross-table checks of 3 datasets that read "
                        "cp-clients in 2025-Q1 are re-checked while you wait - not their own "
                        "tables:\n"
                        "    cp-investigations, cp-notifications, cp-placements\n"
                        "  With no cp-clients file left in 2025-Q1, they will very likely "
                        "turn red: those checks cannot run until one is promoted."), note
        assert not any(n.startswith("Then") for n in shown.notes), shown.notes
        assert not any("re-checks the cross-table" in line for line in shown.lines)

    def test_reject_both_in_the_settle_flow_rechecks_before_the_outcome_panel(
            self, sc, person, capsys):
        """Criteria 13 and 14 through the settle flow: the wait line and each
        re-check's progress, then the outcome panel with the datasets
        re-checked - red first, in words - and no 'contested', 'rejected',
        'refused' or raw 'knock-on:' among them."""
        from cli import settle_tui
        from qa_tools.common import filing_decisions as fd, supply_db

        got = contested(sc)
        request = fd.Request(operation=fd.CHOOSE_FILE, dataset_id="cp-clients", actor=person,
                             reason="t", period=Q4, supply=got["pair"],
                             file_outcomes=tuple(_reject_both()))
        with supply_db.connect(read_only=True, label="pytest") as conn:
            key = fd.consequences(conn, request).key
        capsys.readouterr()  # the fixture's own processing, not the settlement's
        settle_tui.settle("cp-clients", Q4, got["pair"], answers=_reject_both(),
                          reason="test", yes=True, acknowledged=key or None, summary=False)
        out = capsys.readouterr().out
        flat = _flat(out)
        assert ("Re-checking the 3 datasets that read cp-clients in 2025-Q1. Ctrl-C stops "
                "it; the settlement stands either way.") in flat, out
        assert re.search(r"re-check 1 of \d - cp-\w+ for 2025-Q1", flat), out
        assert flat.index("Re-checking the 3 datasets") < flat.index("Settled"), out
        section = _readers_section(out)
        assert "red - could not run: 2025-Q1 holds no cp-clients" in section, section
        for word in ("contested", "rejected", "refused", "knock-on:"):
            assert word not in section, (word, section)
        assert "knock-on:" not in out
        assert sc.owed("reevaluate") == []

    def test_reject_both_with_the_flag_form_rechecks_and_exits_0(self, sc, person):
        from click.testing import CliRunner

        from cli.supply import supply_group
        from qa_tools.common import filing_decisions as fd, supply_db

        got = contested(sc)
        request = fd.Request(operation=fd.CHOOSE_FILE, dataset_id="cp-clients", actor=person,
                             reason="t", period=Q4, supply=got["pair"],
                             file_outcomes=tuple(_reject_both()))
        with supply_db.connect(read_only=True, label="pytest") as conn:
            key = fd.consequences(conn, request).key
        args = ["decide", "--operation", "choose-file", "--dataset", "cp-clients",
                "--period", Q4, "--file-outcome", f"{PAIR[0]}=reject",
                "--file-outcome", f"{PAIR[1]}=reject", "--reason", "test", "--yes"]
        result = CliRunner().invoke(supply_group, args + (["--acknowledge", key] if key else []),
                                    env=PIPED)
        assert result.exit_code == 0, result.output
        assert "Datasets that read cp-clients in 2025-Q1, re-checked:" in _flat(result.output)

    def test_a_ctrl_c_during_the_recheck_leaves_it_owed_and_exits_3(self, sc, person,
                                                                     monkeypatch):
        """Criterion 15: no traceback, the 'Re-check owed' panel, the
        re-evaluation still owed, and the flag form exits 3."""
        from click.testing import CliRunner

        from cli.supply import supply_group
        from qa_tools.common import filing_decisions as fd, knock_on, supply_db

        got = contested(sc)
        request = fd.Request(operation=fd.CHOOSE_FILE, dataset_id="cp-clients", actor=person,
                             reason="t", period=Q4, supply=got["pair"],
                             file_outcomes=tuple(_reject_both()))
        with supply_db.connect(read_only=True, label="pytest") as conn:
            key = fd.consequences(conn, request).key

        def interrupted(*_a, **_k):
            raise KeyboardInterrupt
        monkeypatch.setattr(knock_on, "complete", interrupted)
        args = ["decide", "--operation", "choose-file", "--dataset", "cp-clients",
                "--period", Q4, "--file-outcome", f"{PAIR[0]}=reject",
                "--file-outcome", f"{PAIR[1]}=reject", "--reason", "test", "--yes"]
        result = CliRunner().invoke(supply_group, args + (["--acknowledge", key] if key else []),
                                    env=PIPED)
        flat = _flat(result.output)
        assert result.exit_code == 3, result.output
        assert "Traceback" not in result.output
        assert "Re-check owed" in flat
        assert ("The settlement is recorded. The re-check of the datasets that read cp-clients "
                "did not finish, so it is owed") in flat, flat
        assert any(line.strip() == "mothman pipeline process"
                   for line in result.output.splitlines())
        assert sc.owed("reevaluate"), "the re-evaluation stays owed"


def test_a_backstopped_reader_is_not_said_refused(private_supply_dsn):
    """D5 (post-build critic): the knock-on's 'refused by the agreement
    backstop' reaches the settlement's panel, which criterion 14 forbids the
    word 'refused' in - said in other words, the meaning kept."""
    from cli import settle_tui
    from qa_tools.common import qa_store, supply_db

    with supply_db.connect(label="pytest") as conn:
        qa_store.ensure_schema(conn)
    readers = settle_tui._Readers("cp-clients", Q4, "child-protection", regated=(
        ("cp-notifications", "cp-notifications@1", Q4, "amber",
         "still waiting - refused by the agreement backstop"),))
    said = " ".join(settle_tui.reader_lines(readers))
    assert "refused" not in said, said
    assert "agreement backstop" in said, said


class TestTheFlagFormExits3WhenItsOwnRunsAreLeftOwed:
    """post-build-review #263: a settlement by flags whose OWN QA run does not
    finish exits CHECKS_STILL_OWED_EXIT (3), as every other operation of the
    command does - not 0, which a script cannot tell from a complete one."""

    def test_a_failed_owed_run_exits_3(self, sc, person, monkeypatch):
        from click.testing import CliRunner

        from cli import filing_tui
        from cli.supply import supply_group
        from qa_tools.common import filing_decisions as fd, recheck, settlement, supply_db

        got = contested(sc)
        answers = (settlement.Answer(PAIR[0], settlement.SUPPLY),
                   settlement.Answer(PAIR[1], settlement.REJECT))
        request = fd.Request(operation=fd.CHOOSE_FILE, dataset_id="cp-clients", actor=person,
                             reason="t", period=Q4, supply=got["pair"], file_outcomes=answers)
        with supply_db.connect(read_only=True, label="pytest") as conn:
            key = fd.consequences(conn, request).key

        def fails(*_a, **_k):
            raise RuntimeError("the tool fell over")
        monkeypatch.setattr(recheck, "run", fails)
        args = ["decide", "--operation", "choose-file", "--dataset", "cp-clients",
                "--period", Q4, "--file-outcome", f"{PAIR[0]}=supply",
                "--file-outcome", f"{PAIR[1]}=reject", "--reason", "test", "--yes"]
        result = CliRunner().invoke(supply_group, args + (["--acknowledge", key] if key else []),
                                    env=PIPED)
        assert "not checked yet - owed" in _flat(result.output), result.output
        assert result.exit_code == filing_tui.CHECKS_STILL_OWED_EXIT, result.output
