"""Settling a pair from the terminal (REQ-PIPE-193 criteria 3, 4, 15, 24, 25
and 27; REQ-PIPE-194 criteria 3 and 4): the option rules, the screens'
order and Back, and the flag form.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

import pytest
from click.testing import CliRunner

from cli import common, settle_tui
from cli import supply as supply_cli
from pair_support import DS, Pair, _at
from qa_tools.common import decision_log, qa_store, settlement, supply_db

REAL_PERSON = "fpycnkgvmt@privaterelay.appleid.com"


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-settle-tui") as c:
        qa_store.ensure_schema(c)
        yield c


@pytest.fixture
def day():
    return date(2026, 11, 1) + timedelta(days=random.randrange(300))


def _files(refused=(False, False)):
    from datetime import datetime, timezone

    at = datetime(2026, 11, 2, 5, tzinfo=timezone.utc)
    return [settlement.PairFile("a.csv", at, "t__1__1", refused[0]),
            settlement.PairFile("b.csv", at + timedelta(minutes=5), "t__1__2", refused[1])]


class TestTheOptions:
    """Criteria 3, 4 and 7, as the person reads them."""

    def test_the_four_in_order_worded_with_the_period(self):
        labels = [o.label for o in settle_tui.first_options(_files(), "2026-11-02")]
        assert labels[0] == "the supply for 2026-11-02"
        assert labels[1] == "re-file - this file belongs to another period (named next)"
        assert labels[2] == "reject - this file is wrong; it can be promoted back later on its own"
        assert labels[3].startswith("a spare copy - kept, can be brought back")

    def test_an_answer_that_leaves_the_other_one_outcome_says_which(self):
        spare = settle_tui.first_options(_files(), "P")[3]
        assert spare.label.endswith("; the other file becomes the supply for P")

    def test_a_ruled_out_outcome_is_shown_with_why_not_hidden(self):
        first = settlement.Answer("a.csv", settlement.SUPPLY)
        second = settle_tui.second_options(_files(), "P", first)
        assert len(second) == 4
        (supply,) = [o for o in second if o.outcome == settlement.SUPPLY]
        assert supply.unavailable and "already the supply" in supply.shown

    def test_a_refused_file_is_offered_only_reject(self):
        opts = settle_tui.first_options(_files(refused=(True, False)), "P")
        assert [o.outcome for o in opts if o.unavailable is None] == [settlement.REJECT]

    def test_choose_file_is_never_on_a_screen(self):
        """Criterion 27."""
        text = " ".join([*settle_tui.WORDS.values(), *settle_tui.SAID.values(),
                         settle_tui.REASON_PROMPT, settle_tui.CONFIRM, settle_tui.SETTLE,
                         settle_tui.REJECT_BOTH, settle_tui.REJECT_BOTH_KEEPS,
                         settle_tui.REFUSED_TITLE, settle_tui.RECORD])
        assert "choose-file" not in text


class TestTheScreens:
    """Criterion 24: each file in turn, Back to the question before, a
    summary that changes either answer, a blank reason back to it."""

    def _script(self, monkeypatch, selects, texts=()):
        selects, texts = list(selects), list(texts)
        asked = []

        def select(message, choices, flag_hint):
            asked.append((message, choices))
            pick = selects.pop(0)
            return None if pick is None else next(c for c in choices if c.startswith(pick))

        monkeypatch.setattr(common, "select", select)
        monkeypatch.setattr(common, "text_prompt", lambda *a, **k: texts.pop(0))
        return asked

    def test_back_on_the_second_returns_to_the_first(self, monkeypatch):
        asked = self._script(monkeypatch,
                             ["the supply", None, "the supply", "reject", "Record"],
                             ["the supplier sent two"])
        answers, reason = settle_tui.collect("ds", "P", _files())
        assert [m for m, _ in asked][:3] == ["What is a.csv?", "What is b.csv?",
                                             "What is a.csv?"]
        assert [a.outcome for a in answers] == ["supply", "reject"]
        assert reason == "the supplier sent two"

    def test_a_blank_reason_returns_to_the_summary_keeping_both(self, monkeypatch):
        asked = self._script(monkeypatch,
                             ["the supply", "a spare copy", "Record", "Record"],
                             [None, "duplicate send"])
        answers, reason = settle_tui.collect("ds", "P", _files())
        assert [m for m, _ in asked].count("Is that right?") == 2
        assert [a.outcome for a in answers] == ["supply", "supersede"]

    def test_back_on_the_summary_records_nothing(self, monkeypatch, capsys):
        self._script(monkeypatch, ["the supply", "reject", None])
        assert settle_tui.collect("ds", "P", _files()) is None
        assert "Not recorded." in capsys.readouterr().out

    def test_changing_the_first_rechecks_the_second(self, monkeypatch):
        """Supply then spare; change the first to reject - a spare copy is no
        longer possible, so the second is asked again."""
        asked = self._script(monkeypatch,
                             ["the supply", "a spare copy", "Change what a.csv",
                              "reject", "the supply", "Record"], ["r"])
        answers, _ = settle_tui.collect("ds", "P", _files())
        assert [a.outcome for a in answers] == ["reject", "supply"]
        assert [m for m, _ in asked].count("What is b.csv?") == 2

    def test_reject_both_goes_straight_to_the_summary(self, monkeypatch):
        """REQ-PIPE-194 criterion 4: through the same summary and reason."""
        asked = self._script(monkeypatch, ["Record"], ["neither is usable"])
        given = [settlement.Answer(f.filename, settlement.REJECT) for f in _files()]
        answers, _ = settle_tui.collect("ds", "P", _files(), given=given)
        assert [m for m, _ in asked] == ["Is that right?"]
        assert {a.outcome for a in answers} == {"reject"}


class TestTheFlagForm:
    """Criterion 15."""

    def test_a_filename_is_matched_exactly_never_split(self):
        names = ["a=b:c.csv", "a.csv"]
        assert settle_tui.parse_outcome("a=b:c.csv=refile:2026-11-03", names) == \
            settlement.Answer("a=b:c.csv", settlement.REFILE, "2026-11-03")
        assert settle_tui.parse_outcome("a.csv=supply", names).outcome == "supply"

    def test_a_file_not_in_the_pair_is_refused_naming_its_files(self):
        import click

        with pytest.raises(click.UsageError, match="its files are a.csv and b.csv"):
            settle_tui.parse_outcome("c.csv=reject", ["a.csv", "b.csv"])

    @pytest.mark.parametrize("flags, says", [
        (["--operation", "promote", "--file-outcome", "a=reject"], "choose-file only"),
        (["--operation", "choose-file", "--supply", "x"], "--supply cannot be used"),
        (["--operation", "choose-file", "--to-period", "x"], "--to-period cannot be used"),
    ])
    def test_usage_errors_name_the_flag(self, flags, says):
        got = CliRunner().invoke(supply_cli.supply_group,
                                 ["decide", "--dataset", DS, "--period", "2026-11-02", *flags])
        assert got.exit_code != 0 and says in got.output

    def test_a_missing_outcome_without_a_terminal_names_the_form(self, conn, day):
        p = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "13:30")),
                              (f"birth_registrations_{day}-1.csv", _at(day, "13:45"))])
        one, two = (n for n, _ in p.files)
        got = CliRunner().invoke(supply_cli.supply_group, [
            "decide", "--operation", "choose-file", "--dataset", DS, "--period", p.period,
            "--file-outcome", f"{one}=supply", "--reason", "r", "--yes"])
        assert got.exit_code != 0
        flat = "".join(ch for ch in got.output if ch not in "│╭╮╰╯─ \n")
        assert f"--file-outcome'{two}=<supply|refile:<period>|reject|supersede>'" in flat

    def test_it_settles_with_yes_and_the_key(self, conn, day, monkeypatch):
        from cli import filing_tui
        from qa_tools.common import people

        monkeypatch.setattr(filing_tui, "actor_at_the_keyboard",
                            lambda: people.person_by_email(REAL_PERSON))
        monkeypatch.setattr(settle_tui, "_run_what_it_owed", lambda *a, **k: {})
        monkeypatch.setattr(filing_tui, "_follow_up", lambda *a, **k: None)
        p = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "13:30")),
                              (f"birth_registrations_{day}_TEST.csv", _at(day, "13:40"))])
        one, two = (n for n, _ in p.files)
        args = ["decide", "--operation", "choose-file", "--dataset", DS, "--period", p.period,
                "--file-outcome", f"{one}=reject", "--file-outcome", f"{two}=reject",
                "--reason", "neither is usable", "--yes"]
        got = CliRunner().invoke(supply_cli.supply_group, args)
        assert got.exit_code == 0, got.output
        assert [d["action"] for d in decision_log.decisions_for(conn, DS)
                if d["supply"] == p.pair] == ["choose-file", "reject"]


class TestThePlainRejectOnTheFlagRoute:
    """Criterion 25: refused, saying where, with the settle form below."""

    def test_it_prints_the_form_with_the_real_filenames(self, conn, day, monkeypatch):
        from cli import filing_tui
        from qa_tools.common import people

        monkeypatch.setattr(filing_tui, "actor_at_the_keyboard",
                            lambda: people.person_by_email(REAL_PERSON))
        p = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "13:30")),
                              (f"birth_registrations_{day}-1.csv", _at(day, "13:45"))])
        got = CliRunner().invoke(supply_cli.supply_group, [
            "decide", "--operation", "reject", "--dataset", DS, "--period", p.period,
            "--supply", p.pair, "--reason", "r", "--yes"])
        assert got.exit_code != 0
        assert "mothman > Filing decisions > " in got.output
        for name, _ in p.files:
            assert f"--file-outcome '{name}=" in got.output
        assert not [d for d in decision_log.decisions_for(conn, DS) if d["supply"] == p.pair]

