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

    def test_a_missing_reason_says_so_with_the_real_filenames(self, conn, day):
        """#170: not the generic template."""
        p = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "13:30")),
                              (f"birth_registrations_{day}-1.csv", _at(day, "13:45"))])
        one, two = (n for n, _ in p.files)
        got = CliRunner().invoke(supply_cli.supply_group, [
            "decide", "--operation", "choose-file", "--dataset", DS, "--period", p.period,
            "--file-outcome", f"{one}=supply", "--file-outcome", f"{two}=reject", "--yes"])
        assert got.exit_code != 0
        flat = "".join(ch for ch in got.output if ch not in "│╭╮╰╯─ \n")
        assert "--reason" in flat and "missing" in flat
        assert f"--file-outcome'{one}=supply'" in flat

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



class TestCriticFindingsOn193:
    """post-build-review #170 - each failed before its fix."""

    def test_the_queue_says_when_a_settled_supplys_own_file_arrived(self, conn, day):
        """Criterion 10: the later file chosen, the queue's Arrived column is
        its receipt, not the arrival's first file's."""
        from cli import filing_tui
        from qa_tools.common import people
        from qa_tools.common import filing_decisions as fd

        early, late = f"birth_registrations_{day}.csv", f"birth_registrations_{day}-resend.csv"
        p = Pair(conn, day, [(early, _at(day, "13:30")), (late, _at(day, "13:45"))])
        request = fd.Request(
            operation=fd.CHOOSE_FILE, dataset_id=DS,
            actor=people.person_by_email(REAL_PERSON), reason="the resend is right",
            period=p.period, supply=p.pair,
            file_outcomes=(settlement.Answer(early, settlement.REJECT),
                           settlement.Answer(late, settlement.SUPPLY)))
        request = fd.Request(**{**request.__dict__,
                                "acknowledged": fd.consequences(conn, request).key or None})
        fd.apply(request, effective_at=_at(day + timedelta(days=1), "09:00").isoformat(),
                 conn=conn)
        assert filing_tui.arrived(p.pair) == f"{day} 13:45"

    def test_a_filename_is_never_cut_in_the_summary(self):
        from io import StringIO

        from rich.console import Console

        long = "birth_registrations_2026-10-07-resend-from-the-supplier.csv"
        files = [settlement.PairFile("birth_registrations_2026-10-07.csv", _files()[0].received_at,
                                     "t__1__1", False),
                 settlement.PairFile(long, _files()[1].received_at, "t__1__2", False)]
        out = StringIO()
        Console(file=out, width=80).print(settle_tui.summary_table(
            files, [settlement.Answer(files[0].filename, "supply"),
                    settlement.Answer(long, "reject")], "2026-10-07"))
        # FOLDED onto further lines of its own column - so its END, the part
        # that tells two files apart, is on screen, and nothing is elided.
        shown = out.getvalue()
        assert "…" not in shown
        assert "ier.csv" in shown or "supplier.csv" in shown


class TestCriticFindingsOn193Screens:
    """post-build-review #170, the screens - each failed before its fix."""

    _script = TestTheScreens._script

    def test_a_partial_flag_answer_is_kept(self, monkeypatch):
        """Criterion 15: only the missing file is asked about."""
        asked = self._script(monkeypatch, ["reject", "Record"], ["r"])
        answers, _ = settle_tui.collect(
            "ds", "P", _files(), given=[settlement.Answer("a.csv", settlement.SUPPLY)])
        assert [m for m, _ in asked] == ["What is b.csv?", "Is that right?"]
        assert [a.outcome for a in answers] == ["supply", "reject"]

    def test_back_on_the_first_file_goes_back_to_the_slot(self, monkeypatch):
        """Criterion 24: to the slot's operations, not out of it."""
        self._script(monkeypatch, [None])
        assert settle_tui.collect("ds", "P", _files()) is settle_tui.BACK

    def test_a_blank_refile_target_asks_the_file_again(self, monkeypatch):
        asked = self._script(monkeypatch, ["re-file", "the supply", "reject", "Record"], ["r"])
        monkeypatch.setattr(settle_tui, "_target", lambda *a, **k: None)
        answers, _ = settle_tui.collect("ds", "P", _files())
        assert [m for m, _ in asked][:2] == ["What is a.csv?", "What is a.csv?"]
        assert [a.outcome for a in answers] == ["supply", "reject"]

    def test_a_combination_the_plan_refuses_is_said_before_the_reason(self, monkeypatch):
        """Criteria 4 and 19: refused before the reason is asked, and the
        second file asked again with the first's answer kept."""
        asked = self._script(monkeypatch, ["the supply", "reject", "re-file", "Record"], ["r"])
        monkeypatch.setattr(settle_tui, "_target", lambda *a, **k: "Q")
        refusals = iter(["both files would be filed to P", None])
        answers, reason = settle_tui.collect("ds", "P", _files(),
                                             check=lambda answers: next(refusals))
        assert [m for m, _ in asked].count("What is b.csv?") == 2
        assert [a.outcome for a in answers] == ["supply", "refile"] and reason == "r"


class TestTheTargetPrompt:
    """Criterion 19 and #170: a target holding another open pair is refused
    and asked again."""

    def test_a_period_holding_an_open_pair_is_asked_again(self, conn, monkeypatch, capsys):
        from qa_tools.common import slots

        period = "2026-11-02"
        first, second = (slots.relative_period(DS, period, 1),
                         slots.relative_period(DS, period, 2))
        answers = iter([first, second])
        monkeypatch.setattr(common, "require_tty", lambda *a, **k: None)
        monkeypatch.setattr(common, "_ask", lambda *a, **k: next(answers))
        monkeypatch.setattr(settlement, "open_pair_in",
                            lambda conn, ds, p, besides: (f"{p} has two files of its own"
                                                          if p == first else None))
        assert settle_tui._target(DS, period, "f.csv", None, besides=f"{DS}@1#1") == second
        assert f"{first} has two files of its own" in capsys.readouterr().out


class TestAChangedConsequenceIsShownAndAskedAgain:
    """Criterion 18 and #170: what changed is said, and the person asked
    again - not left at a refusal."""

    def test_it_asks_again_with_the_new_warning(self, monkeypatch):
        from cli import filing_tui
        from qa_tools.common import filing_decisions as fd

        first, now = fd.Consequences(lines=("A",)), fd.Consequences(lines=("B",))
        shown = iter([first, now])
        applied = []

        def apply(request, **k):
            applied.append(request.acknowledged)
            if len(applied) == 1:
                raise fd.ConsequencesNotAcknowledged(now, given=request.acknowledged,
                                                     terminal_only=True)
            return fd.Outcome(operation=fd.CHOOSE_FILE, dataset_id="ds", period="P",
                              changed=True, message="ok")

        monkeypatch.setattr(settlement, "refused_before_asking", lambda *a: None)
        monkeypatch.setattr(settlement, "pair_files", lambda *a: ("d", "P", _files()))
        monkeypatch.setattr(filing_tui, "open_log", lambda: _NullConn())
        monkeypatch.setattr(filing_tui, "_consequences", lambda request: next(shown))
        monkeypatch.setattr(fd, "settlement_plan", lambda conn, request: _NoRuns())
        monkeypatch.setattr(fd, "apply", apply)
        monkeypatch.setattr(common, "confirm_change", lambda *a, **k: True)
        monkeypatch.setattr(settle_tui, "_run_what_it_owed", lambda *a, **k: {})
        monkeypatch.setattr(filing_tui, "_follow_up", lambda *a, **k: None)
        monkeypatch.setattr(fd, "reconcile_after", lambda *a, **k: None)
        monkeypatch.setattr(settle_tui.hierarchy, "dataset", lambda ds: _DS())
        got = settle_tui.settle("ds", "P", "ds@1#1", reason="r", summary=False,
                                answers=[settlement.Answer("a.csv", "supply"),
                                         settlement.Answer("b.csv", "reject")],
                                actor={"email": "x@example.org", "name": "X"})
        assert got is not None and got.changed
        assert applied == [first.key, now.key]


class _NullConn:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _NoRuns:
    runs = ()


class _DS:
    dataset_name = "Birth Registrations"
    collection_id = "civil-registration"
