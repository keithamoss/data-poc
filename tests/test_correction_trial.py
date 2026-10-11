"""A correction's impact can be previewed before anyone approves it
(REQ-PIPE-169), by the one computation REQ-PIPE-170's trial will confirm.

Recorded facts come from real filings against the real cp-clients agreement
(2023-Q3 dated 2023-08-01, due 09:00 Perth, 8h grace); the corrected
configuration is a changed copy.
"""
from __future__ import annotations

import copy
from datetime import UTC, date, datetime, timedelta, timezone

import pytest
import yaml

import filing_support
from qa_tools.common import (agreement, assignment, asset_time, correction_trial, qa_store,
                             supply_db)

PERTH = timezone(timedelta(hours=8))
DATASET = "cp-clients"
RECEIVED = datetime(2023, 8, 1, 12, tzinfo=PERTH)
#: Its own supply id, and so its own delivery record: a delivery is written
#: once and kept, so sharing `s` with another module on the same worker
#: gave that module this module's receipt instant.
SUPPLY = "trial-s"
AT = datetime(2026, 10, 11, tzinfo=UTC)


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-correction-trial") as c:
        qa_store.ensure_schema(c)
        c.execute(f'TRUNCATE "{qa_store.SCHEMA}".filing CASCADE')
        _file(SUPPLY, "2023-Q3", RECEIVED)
        yield c


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
    """cp-clients' entry, its versions its own - the file shares them between
    datasets through YAML anchors, so an edit would otherwise reach six."""
    entry = next(d for d in cal["datasets"] if d["id"] == DATASET)
    entry["participation"]["versions"] = copy.deepcopy(entry["participation"]["versions"])
    return entry


def _quarterly(cal):
    return next(c for c in cal["calendars"] if c["name"] == "quarterly")


def _move_q3(cal, to):
    for d in _quarterly(cal)["versions"][-1]["dates"]:
        if d["period"] == "2023-Q3":
            d["date"] = to


def _trial(conn, work, base=None):
    return correction_trial.trial(conn, base or _docs(), work, at=AT, dataset_ids=[DATASET])


class TestNothingFrozenChanged:
    """Criterion 11."""

    def test_the_same_agreement_says_so_in_one_line(self, conn):
        t = _trial(conn, _docs())
        assert t.nothing_frozen_changed
        text = correction_trial.report(t, as_at=AT, database="db on host", against="HEAD~1")
        assert "Nothing frozen changed" in text
        assert "## Summary" not in text

    def test_an_appended_future_date_is_not_a_correction(self, conn):
        cal, asset = _docs()
        _quarterly(cal)["versions"][-1]["dates"].append({"period": "2099-Q1",
                                                          "date": "2099-02-01"})
        assert _trial(conn, (cal, asset)).nothing_frozen_changed


class TestWhatItLists:
    """Criteria 2-5."""

    def test_a_shorter_grace_flips_a_verdict_and_moves_late_after(self, conn):
        cal, asset = _docs()
        _clients(cal)["participation"]["versions"][0]["grace"] = "1h"
        t = _trial(conn, (cal, asset))
        assert [(v.supply_id, v.old, v.new) for v in t.verdicts] == [(SUPPLY, "on_time", "late")]
        assert not t.moves, "a grace change moves no supply"
        late_after = [m for m in t.slot_moves if m.slot == "2023-Q3" and m.what == "late after"]
        assert late_after and late_after[0].old - late_after[0].new == timedelta(hours=7)
        assert not [m for m in t.slot_moves if m.what == "due"], "due did not move"

    def test_a_moved_date_files_the_supply_elsewhere_with_its_new_verdict(self, conn):
        cal, asset = _docs()
        _move_q3(cal, "2023-10-20")
        t = _trial(conn, (cal, asset))
        [move] = t.moves
        assert move.supply_id == SUPPLY and move.from_period == "2023-Q3"
        assert move.to_period != "2023-Q3"
        assert not [v for v in t.verdicts if v.supply_id == SUPPLY], \
            "a moving supply's verdict is shown with its move, not twice"
        assert any(m.slot == "2023-Q3" and m.what == "due" for m in t.slot_moves)

    def test_a_removed_period_is_an_obligation_lost(self, conn):
        cal, asset = _docs()
        dates = _quarterly(cal)["versions"][-1]["dates"]
        dates[:] = [d for d in dates if d["period"] != "2023-Q3"]
        t = _trial(conn, (cal, asset))
        assert [(o.period, o.gained) for o in t.obligations] == [("2023-Q3", False)]
        [move] = t.moves
        assert move.from_period == "2023-Q3" and move.to_period != "2023-Q3"

    def test_a_changed_timezone_moves_every_instant(self, conn):
        """The asset file's zone, not the one on disk, for the corrected side."""
        cal, asset = _docs()
        asset["timezone"]["versions"][0]["zone"] = "Australia/Sydney"
        t = _trial(conn, (cal, asset))
        due = [m for m in t.slot_moves if m.slot == "2023-Q3" and m.what == "due"]
        assert due and due[0].old - due[0].new == timedelta(hours=2)
        assert asset_time.timezone_versions()[0].zone.key == "Australia/Perth", \
            "the file's zones are back once the trial ends"


class TestWhatCannotMove:
    """Criterion 4: a supply a later period stands on is marked; a person's
    filing is not overruled by a rule."""

    def test_one_of_a_contested_pair_is_blocked_naming_the_remedy(self, conn):
        _file("s2@1#1", "2023-Q3", RECEIVED + timedelta(minutes=5))
        cal, asset = _docs()
        _move_q3(cal, "2023-10-20")
        blocked = {m.supply_id: m.blocked for m in _trial(conn, (cal, asset)).moves}
        assert blocked[SUPPLY] is None
        assert "contested pair" in blocked["s2@1#1"]

    def test_a_supply_a_person_placed_is_listed_not_proposed(self, conn):
        # Somewhere neither agreement's rule would put it: a person's call.
        filing_support.place(conn, DATASET, SUPPLY, "2023-Q1", f"pytest-cp-clients-{SUPPLY}")
        cal, asset = _docs()
        _move_q3(cal, "2023-10-20")
        t = _trial(conn, (cal, asset))
        assert not t.moves
        [n] = t.not_proposed
        assert (n.supply_id, n.period) == (SUPPLY, "2023-Q1")
        text = correction_trial.report(t, as_at=AT, database="d", against="HEAD~1")
        assert "a person put these where they are" in text


class TestTheReport:
    """Criterion 7, NFR 1 and 3."""

    def test_summary_first_with_its_as_at_and_database(self, conn):
        cal, asset = _docs()
        _move_q3(cal, "2023-10-20")
        t = _trial(conn, (cal, asset))
        text = correction_trial.report(t, as_at=AT, database="supply on localhost",
                                       against="origin/main")
        assert text.index("## Summary") < text.index("## Supplies that would move")
        assert "supply on localhost" in text and "origin/main" in text
        assert "| cp-clients |" in text

    def test_the_database_is_named_without_its_connection_string(self, monkeypatch):
        monkeypatch.setattr(supply_db, "supply_db_dsn",
                            lambda: "postgresql://u:s3cret@db.example:5432/supply")
        label = correction_trial.database_label()
        assert label == "supply on db.example" and "s3cret" not in label

    def test_the_same_facts_give_the_same_report(self, conn):
        cal, asset = _docs()
        _move_q3(cal, "2023-10-20")
        one = correction_trial.report(_trial(conn, (cal, asset)), as_at=AT, database="d",
                                      against="r")
        two = correction_trial.report(_trial(conn, (cal, asset)), as_at=AT, database="d",
                                      against="r")
        assert one == two


def test_nothing_is_recorded(conn):
    """Criterion 10."""
    tables = ("filing", "verdict", "decision", "supply_hold")

    def counts():
        out = {}
        for name in tables:
            rows = conn.execute(
                "SELECT to_regclass(?)", [f'"{qa_store.SCHEMA}".{name}']).fetchall()
            if rows[0][0]:
                out[name] = conn.execute(
                    f'SELECT count(*) FROM "{qa_store.SCHEMA}".{name}').fetchall()[0][0]
        return out

    before = counts()
    cal, asset = _docs()
    _move_q3(cal, "2023-10-20")
    _clients(cal)["participation"]["versions"][0]["grace"] = "1h"
    _trial(conn, (cal, asset))
    assert counts() == before


def test_it_reads_configuration_and_recorded_facts_only():
    """Criterion 8: no supply rows - no staging, period or run schema."""
    import inspect

    source = inspect.getsource(correction_trial)
    for forbidden in ("staging_schema_for", "run_schema", "period_tables", "candidates_in"):
        assert forbidden not in source


class TestTheCommands:
    """Criteria 1, 7, 9, 12 and 14, through the real commands."""

    @pytest.fixture
    def moved(self, monkeypatch):
        cal, asset = _docs()
        work = copy.deepcopy(cal)
        _move_q3(work, "2023-10-20")
        _clients(work)["participation"]["versions"][0]["grace"] = "1h"
        monkeypatch.setattr(correction_trial, "at_ref", lambda ref: (cal, asset))
        monkeypatch.setattr(correction_trial, "working", lambda: (work, asset))

    def _run(self, *args):
        from click.testing import CliRunner

        from cli import schedule as schedule_cli
        return CliRunner().invoke(schedule_cli.schedule_group, list(args))

    def test_help_says_it_reads_the_database(self):
        assert "READS THE DATABASE" in self._run("preview-correction", "--help").output

    def test_it_writes_markdown_summary_first(self, conn, moved, tmp_path):
        out = tmp_path / "impact.md"
        got = self._run("preview-correction", "--against", "HEAD", "--output", str(out))
        assert got.exit_code == 0, got.output
        text = out.read_text()
        assert text.startswith("# Impact of the correction")
        assert text.index("## Summary") < text.index("## Supplies that would move")

    def test_unreachable_facts_refuse_rather_than_report_configuration_alone(
            self, moved, monkeypatch):
        from qa_tools.common import supply_db as db

        def down(*a, **k):
            raise db.SupplyDbError("connection refused")
        monkeypatch.setattr(db, "connect", down)
        got = self._run("preview-correction", "--against", "HEAD")
        assert got.exit_code == 2
        assert "could not be read" in got.output and "## Summary" not in got.output

    def test_draft_prints_one_entry_per_owner_with_what_was_given(self, moved):
        got = self._run("draft-correction", "--against", "HEAD", "--reference", "CAB-7",
                        "--reason", "the date was a typo")
        assert got.exit_code == 0, got.output
        assert got.output.count("Add to the corrections list of") == 2
        assert "calendar 'quarterly'" in got.output and "cp-clients" in got.output
        assert "change_reference: CAB-7" in got.output
        assert "author: <you>" in got.output, "what was not given stays a placeholder"
        assert "item: calendar quarterly period 2023-Q3" in got.output

    def test_draft_entries_parse_back_as_the_correction(self, moved):
        """Pasteable: the entry's YAML is the declared correction."""
        got = self._run("draft-correction", "--against", "HEAD", "--reference", "CAB-7",
                        "--reason", "a: colon", "--approver", "x@y", "--author", "me")
        block = got.output.split("Add to the corrections list of calendar 'quarterly'")[1]
        block = block.split("May approve")[0].split(":\n", 1)[1]
        [entry] = yaml.safe_load(block)["corrections"]
        assert entry["reason"] == "a: colon" and entry["change_reference"] == "CAB-7"
        assert entry["changes"][0]["new"] == "2023-10-20"


class TestTheCalendarEntry:
    """Criterion 13: reachable from the main menu, viewing only."""

    def test_it_is_on_the_main_menu(self):
        from cli import app

        assert app._MAIN_MENU_CALENDAR.startswith("Calendar")

    def test_it_shows_the_agreement_in_force_and_the_corrections(self, conn, monkeypatch,
                                                                  capsys):
        from cli import common
        from cli import schedule as schedule_cli

        answers = iter([DATASET, None])
        monkeypatch.setattr(common, "select", lambda *a, **k: next(answers))
        monkeypatch.setattr(common, "text_prompt", lambda *a, **k: "2023-07-01")
        schedule_cli.calendar_menu()
        out = capsys.readouterr().out
        assert "cp-clients as at 1 Jul 2023" in out
        assert "Calendar: quarterly" in out
        assert "Next period owed: 2023-Q3" in out and "grace 8h" in out
        assert "corrections" in out.lower()

    def test_the_view_edits_no_configuration(self):
        import inspect

        from cli import schedule as schedule_cli
        source = inspect.getsource(schedule_cli.calendar_menu) + inspect.getsource(
            schedule_cli._draft)
        assert "calendar.yaml\").write" not in source and "CALENDAR_YAML" not in source


def test_a_declared_correction_reads_applied_once_a_verdict_names_it(conn):
    from qa_tools.common import verdict

    cal, asset = _docs()
    _clients(cal)["corrections"] = [{"change_reference": "CAB-42", "date": "2026-10-11",
                                     "author": "a", "approver": "b", "reason": "r",
                                     "changes": [{"item": "x", "old": 1, "new": 2}]}]
    [d] = [d for d in correction_trial.declared(conn, cal, asset) if d.reference == "CAB-42"]
    assert not d.applied
    [r] = verdict.rejudged(conn, DATASET, agreement.from_doc(_grace(cal)))
    verdict.record_rejudgement(conn, r, correction_ref="CAB-42", correction_changelog="t",
                               recorded_at=datetime.now(UTC))
    [d] = [d for d in correction_trial.declared(conn, cal, asset) if d.reference == "CAB-42"]
    assert d.applied


def _grace(cal):
    cal = copy.deepcopy(cal)
    _clients(cal)["participation"]["versions"][0]["grace"] = "1h"
    return cal


def test_ts64_the_drafted_entry_is_the_gates_refusal_entry():
    """TS-64: an undeclared change to a frozen date - the command's entry
    and the one the gate refuses with are the same text."""
    from datetime import date

    from qa_tools.common import agreement_freeze

    cal, asset = _docs()
    work = copy.deepcopy(cal)
    _move_q3(work, "2023-10-20")
    today = date(2026, 10, 11)
    [finding] = agreement_freeze.check(cal, work, asset, asset, {}, today=today,
                                       base_codeowners=None)
    [entry] = agreement_freeze.drafts(cal, work, asset, asset, {}, base_codeowners=None,
                                      today=today)
    assert entry == finding.fix


class TestCriticFindingsOn169:
    """delivery-critic on REQ-PIPE-169 (post-build-review #147). Each failed
    before its fix."""

    def test_f1_a_moving_supply_keeps_its_old_verdict_and_is_counted(self, conn):
        cal, asset = _docs()
        _move_q3(cal, "2023-10-20")
        t = _trial(conn, (cal, asset))
        [move] = t.moves
        assert move.old_verdict == "on_time"
        assert t.by_dataset()[DATASET]["verdicts"] == 1, "a moved supply's flip counts"
        text = correction_trial.report(t, as_at=AT, database="d", against="r")
        assert "2023-Q3 (On time) ->" in text

    def test_f2_a_rule_hold_is_proposed_not_called_a_persons(self, conn):
        """A hold the rule wrote (an agreement-refused one) is the rule's,
        whatever period the base agreement would name today."""
        filing_support.file(assignment.Assignment(
            dataset_id=DATASET, supply_id="held-r", slot=None, branch=assignment.HELD,
            considered=(), received_at=RECEIVED + timedelta(minutes=1)))
        cal, asset = _docs()
        _move_q3(cal, "2023-10-20")
        t = _trial(conn, (cal, asset))
        assert "held-r" not in {n.supply_id for n in t.not_proposed}
        [held] = [m for m in t.moves if m.supply_id == "held-r"]
        assert held.from_period is None and held.to_period is not None

    def test_f2_a_persons_filing_is_never_proposed_even_where_the_rule_agreed(self, conn):
        _file("person-q3", "2023-Q2", RECEIVED + timedelta(minutes=2))
        filing_support.place(conn, DATASET, "person-q3", "2023-Q3", "pytest-cp-clients-person-q3")
        cal, asset = _docs()
        _move_q3(cal, "2023-10-20")
        t = _trial(conn, (cal, asset))
        assert "person-q3" not in {m.supply_id for m in t.moves}
        assert "person-q3" in {n.supply_id for n in t.not_proposed}

    def test_f3_a_rejected_supply_is_blocked(self, conn):
        from qa_tools.common import decision_log

        with decision_log.apply_decision(conn, decision_log.Decision(
                agency_id="child-protection-family-support", collection_id="child-protection",
                dataset_id=DATASET, action=decision_log.REJECT, supply=SUPPLY,
                actor="somebody", actor_kind=decision_log.PERSON,
                effective_at="2023-08-02T09:00:00+08:00", to_slot="2023-Q3",
                reason="bad file")):
            pass
        cal, asset = _docs()
        _move_q3(cal, "2023-10-20")
        [move] = [m for m in _trial(conn, (cal, asset)).moves if m.supply_id == SUPPLY]
        assert move.blocked and "rejected" in move.blocked

    def test_f3_a_held_supply_is_placed_not_re_filed(self, conn):
        filing_support.file(assignment.Assignment(
            dataset_id=DATASET, supply_id="held-p", slot=None, branch=assignment.HELD,
            considered=(), received_at=RECEIVED + timedelta(minutes=3)))
        cal, asset = _docs()
        _move_q3(cal, "2023-10-20")
        t = _trial(conn, (cal, asset))
        text = correction_trial.report(t, as_at=AT, database="d", against="r")
        assert "`held-p`: held -> placed into" in text

    def test_f4_an_unreadable_working_copy_is_refused_in_words(self, monkeypatch):
        cal, asset = _docs()
        broken = copy.deepcopy(cal)
        _clients(broken)["participation"]["versions"][0]["grace"] = "not a duration"
        monkeypatch.setattr(correction_trial, "_working_docs", lambda: (broken, asset))
        with pytest.raises(correction_trial.Unreadable, match="working copy"):
            correction_trial.working()

    def test_f4_draft_never_gives_an_all_clear_on_an_unreadable_copy(self, monkeypatch):
        cal, asset = _docs()
        broken = copy.deepcopy(cal)
        _clients(broken)["participation"]["versions"][0]["grace"] = "not a duration"
        monkeypatch.setattr(correction_trial, "_working_docs", lambda: (broken, asset))
        monkeypatch.setattr(correction_trial, "at_ref", lambda ref: (cal, asset))
        from click.testing import CliRunner

        from cli import schedule as schedule_cli
        got = CliRunner().invoke(schedule_cli.schedule_group,
                                 ["draft-correction", "--against", "HEAD"])
        assert got.exit_code == 2 and "nothing to declare" not in got.output
        assert "working copy" in got.output

    def test_f4_the_calendar_entry_survives_an_unreadable_copy(self, monkeypatch, capsys):
        from cli import common
        from cli import schedule as schedule_cli

        cal, asset = _docs()
        broken = copy.deepcopy(cal)
        _clients(broken)["participation"]["versions"][0]["grace"] = "not a duration"
        monkeypatch.setattr(correction_trial, "_working_docs", lambda: (broken, asset))
        answers = iter([DATASET, None])
        monkeypatch.setattr(common, "select", lambda *a, **k: next(answers))
        monkeypatch.setattr(common, "text_prompt", lambda *a, **k: None)
        schedule_cli.calendar_menu()
        assert "working copy" in capsys.readouterr().out

    def test_f5_a_blocked_reason_stays_inside_its_bullet(self):
        t = correction_trial.Trial(
            changes=(correction_trial.FrozenChange("k", ("calendar", "q"), 1, 2),),
            moves=(correction_trial.Move(DATASET, "x", "2023-Q3", "2023-Q2", "late",
                                         blocked="line one\nmothman fix it"),))
        text = correction_trial.report(t, as_at=AT, database="d", against="r")
        bullet = text.split("BLOCKED:")[1].split("\n- ")[0]
        assert all(line.startswith("  ") for line in bullet.splitlines()[1:])

    def test_f5_the_summary_says_which_way_an_obligation_went(self):
        t = correction_trial.Trial(
            changes=(correction_trial.FrozenChange("k", ("calendar", "q"), 1, 2),),
            obligations=(correction_trial.Obligation(DATASET, "2023-Q3", date(2023, 8, 1),
                                                     gained=False),))
        text = correction_trial.report(t, as_at=AT, database="d", against="r")
        assert "Periods gained / lost" in text and "| 0 / 1 |" in text

    def test_f5_what_changed_reads_as_values_not_python(self):
        t = correction_trial.Trial(changes=(correction_trial.FrozenChange(
            "calendar quarterly period 2024-Q1", ("calendar", "quarterly"), "2024-02-01",
            None),))
        text = correction_trial.report(t, as_at=AT, database="d", against="r")
        assert "'2024-02-01' -> None" not in text
        assert "'2024-02-01' -> (nothing)" in text

    def test_f9_before_the_dataset_began_it_owes_nothing_yet(self):
        f = correction_trial.in_force("birth-registrations", date(2024, 3, 1))
        assert f.owes.startswith("nothing yet")

    def test_f10_draft_asks_nothing_when_nothing_needs_declaring(self, monkeypatch):
        from cli import common
        from cli import schedule as schedule_cli

        cal, asset = _docs()
        monkeypatch.setattr(correction_trial, "at_ref", lambda ref: (cal, asset))
        monkeypatch.setattr(correction_trial, "working", lambda: (cal, asset))

        def asked(*a, **k):
            raise AssertionError("asked for a reference with nothing to declare")
        monkeypatch.setattr(common, "text_prompt", asked)
        monkeypatch.setattr(common, "select", asked)
        schedule_cli._draft("HEAD", interactive=True)
