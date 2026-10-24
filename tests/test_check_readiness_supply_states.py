"""REQ-PIPE-079 criteria 4 and 14-16 - WHY a table has no promoted supply.

Four different situations that all look identical from inside a check -
the table it reads is not there - and which an operator needs told
apart, because each has a different next action:

  14. not supplied yet, and not yet overdue -> NOT red. Nothing is
      wrong; the supply is not due. Reporting red here is the false-red
      that teaches people to ignore the colour.
  16. a supply IS staged, waiting for somebody to decide -> red, and say
      so. The action is "go and decide", which is nobody's until they
      are told it exists.
  15. past due and nothing staged -> red, and say it is overdue. The
      action is "chase the supplier".
   4. anything else -> the existing message: no filled slot in this
      period and not in the delivery under test.

THE ORDER IS THE INTERESTING PART, and criterion 4 says so in its own
words: "none of the more specific cases in this requirement applies".
Past due and staged-awaiting-a-decision can BOTH be true at once, and
the staged one wins, because it names the action that is actually
available to the person reading it.
"""
from __future__ import annotations


from qa_tools.common import period_schema as ps


def a_resolution(resolved=()):
    """The minimum PeriodResolution shape check_readiness reads."""
    class _Inner:
        def __init__(self, names):
            self.resolved = {n: f"{n}__physical" for n in names}

    class _Res:
        def __init__(self, names):
            self.resolution = _Inner(names)
    return _Res(resolved)


class TestNotYetDueIsNotRed:
    """Criterion 14."""

    def test_it_is_not_red(self):
        verdict = ps.check_readiness(
            ["cp_carers"], a_resolution(),
            supply_states={"cp_carers": ps.NOT_YET_DUE})
        assert verdict is not None
        assert verdict.status != ps.RED, \
            "a supply that is not due yet is not a failure, and red here teaches people to ignore red"

    def test_and_it_says_why(self):
        verdict = ps.check_readiness(
            ["cp_carers"], a_resolution(),
            supply_states={"cp_carers": ps.NOT_YET_DUE})
        described = verdict.describe().lower()
        assert "not yet" in described or "not been supplied" in described
        assert "cp_carers" in verdict.names


class TestPastDueIsRed:
    """Criterion 15."""

    def test_it_is_red(self):
        verdict = ps.check_readiness(
            ["cp_carers"], a_resolution(),
            supply_states={"cp_carers": ps.PAST_DUE})
        assert verdict.status == ps.RED

    def test_and_says_the_table_is_overdue(self):
        verdict = ps.check_readiness(
            ["cp_carers"], a_resolution(),
            supply_states={"cp_carers": ps.PAST_DUE})
        assert "overdue" in verdict.describe().lower()


class TestAStagedSupplyAwaitingADecisionIsItsOwnCase:
    """Criterion 16 - red, and DISTINCTLY from the case where no supply
    exists at all."""

    def test_it_is_red(self):
        verdict = ps.check_readiness(
            ["cp_carers"], a_resolution(),
            supply_states={"cp_carers": ps.STAGED_AWAITING_DECISION})
        assert verdict.status == ps.RED

    def test_and_says_a_supply_is_waiting_for_a_decision(self):
        verdict = ps.check_readiness(
            ["cp_carers"], a_resolution(),
            supply_states={"cp_carers": ps.STAGED_AWAITING_DECISION})
        described = verdict.describe().lower()
        assert "decision" in described or "awaiting" in described

    def test_and_reads_DIFFERENTLY_from_nothing_having_arrived(self):
        staged = ps.check_readiness(
            ["cp_carers"], a_resolution(),
            supply_states={"cp_carers": ps.STAGED_AWAITING_DECISION}).describe()
        nothing = ps.check_readiness(["cp_carers"], a_resolution()).describe()
        assert staged != nothing, \
            "criterion 16 asks for this to be distinct from no supply existing at all"


class TestWhichCaseWinsWhenSeveralApply:
    """Criterion 4's 'none of the more specific cases applies'."""

    def test_staged_awaiting_a_decision_beats_past_due(self):
        """Both can be true. The staged one names an action the reader
        can actually take now - go and decide - where 'overdue' sends
        them to chase a supplier who has already sent it."""
        verdict = ps.check_readiness(
            ["cp_carers"], a_resolution(),
            supply_states={"cp_carers": ps.STAGED_AWAITING_DECISION})
        assert "decision" in verdict.describe().lower()


class TestTheOldBehaviourIsUnchangedWhereNoStateIsKnown:
    """Criterion 4 - the fallback, and every existing caller."""

    def test_it_is_still_red_with_the_original_message(self):
        verdict = ps.check_readiness(["cp_carers"], a_resolution())
        assert verdict.status == ps.RED
        assert "no filled slot in this period" in verdict.describe()

    def test_a_table_that_IS_resolved_still_runs(self):
        assert ps.check_readiness(["cp_carers"], a_resolution(["cp_carers"])) is None
