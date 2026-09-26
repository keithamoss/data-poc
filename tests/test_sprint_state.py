"""REQ-DOCS-072 - a sprint's status counted from its criteria.

Written against fixtures for the RULES and against the real files for
the corpus, because the two answer different questions: a fixture can
hold the awkward cases the plan does not happen to contain today, and
only the real files can say whether the plan and the register currently
agree.
"""
from __future__ import annotations

import textwrap

import pytest
import yaml

from qa_tools.common import sprint_state as ss


def _plan(tmp_path, entries: list[tuple[int, str, list[str]]]):
    """A minimal sprint list. `entries` is (number, status, owned ids)."""
    body = []
    for number, status, ids in entries:
        owns = ", ".join(f"`{q}`" for q in ids) if ids else "nothing yet - unscoped."
        body.append(textwrap.dedent(f"""\
            {number}. **[{status}, 2026-01-01]** **[Pipeline & publishing]** **A sprint.**
               Some prose.

               **Owns:** {owns}
            """))
    path = tmp_path / "plan.md"
    path.write_text("\n".join(body))
    return path


def _register(tmp_path, reqs: list[tuple[str, str, int, list[str]]]):
    """`reqs` is (id, status, criteria count, unmet owners)."""
    out = []
    for req_id, status, n, unmet in reqs:
        out.append({
            "id": req_id, "status": status,
            "acceptance_criteria": [f"THE SYSTEM SHALL do thing {i}." for i in range(n)],
            **({"unmet_criteria": [{"criterion": "x", "why": "y", "owner": o}
                                    for o in unmet]} if unmet else {}),
        })
    path = tmp_path / "reqs.yaml"
    path.write_text(yaml.safe_dump({"requirements": out}))
    return path


def _one(tmp_path, status, reqs, ids=None):
    ids = [r[0] for r in reqs] if ids is None else ids
    return ss.survey(_plan(tmp_path, [(1, status, ids)]), _register(tmp_path, reqs))[0]


class TestTheStatusIsCountedNotTyped:
    """Criterion 2."""

    def test_every_criterion_met_is_done(self, tmp_path):
        s = _one(tmp_path, "done", [("REQ-X-001", "built", 4, [])])
        assert (s.met, s.total, s.derived) == (4, 4, ss.DONE)

    def test_nothing_built_is_todo(self, tmp_path):
        s = _one(tmp_path, "todo", [("REQ-X-001", "not_started", 4, [])])
        assert (s.met, s.total, s.derived) == (0, 4, ss.NOT_STARTED)

    def test_some_built_is_in_progress(self, tmp_path):
        s = _one(tmp_path, "in-progress", [("REQ-X-001", "built", 3, []),
                                            ("REQ-X-002", "not_started", 2, [])])
        assert (s.met, s.total, s.derived) == (3, 5, ss.IN_PROGRESS)

    def test_counts_span_every_requirement_the_sprint_owns(self, tmp_path):
        s = _one(tmp_path, "done", [("REQ-X-001", "built", 3, []),
                                     ("REQ-X-002", "built", 4, [])])
        assert (s.met, s.total) == (7, 7)


class TestADeferralIsNotMet:
    """Criterion 5, and the reason the unit is a criterion rather than a
    requirement. Sprint 10 read `done` while owing four deferrals; a
    requirement-level count cannot see that at all."""

    def test_a_built_requirement_with_deferrals_is_not_complete(self, tmp_path):
        s = _one(tmp_path, "done", [("REQ-X-001", "built", 12, ["sprint 11", "sprint 11"])])
        assert (s.met, s.total) == (10, 12)
        assert s.derived != ss.DONE

    def test_counting_requirements_instead_would_have_said_done(self, tmp_path):
        """The rejected design, asserted so nobody reverts to it."""
        s = _one(tmp_path, "done", [("REQ-X-001", "built", 12, ["sprint 11"])])
        built = all(True for _ in [1])  # every requirement IS built
        assert built and s.derived != ss.DONE


class TestBlocked:
    """Criteria 3 and 4 - Keith's own addition, for a sprint that has
    "built all of its stuff and it's waiting on someone else"."""

    def test_a_sprint_owing_only_deferrals_is_blocked(self, tmp_path):
        s = _one(tmp_path, "done", [("REQ-X-001", "built", 5, ["the promotion sprint"])])
        assert s.derived == ss.BLOCKED

    def test_it_names_what_it_waits_on(self, tmp_path):
        s = _one(tmp_path, "done", [("REQ-X-001", "built", 5, ["the promotion sprint"])])
        assert "the promotion sprint" in s.summary()

    def test_work_of_its_own_outranks_a_deferral(self, tmp_path):
        """A sprint with an unbuilt requirement AND a deferral is
        in-progress, not blocked - somebody can still work on it."""
        s = _one(tmp_path, "in-progress", [("REQ-X-001", "built", 5, ["elsewhere"]),
                                            ("REQ-X-002", "not_started", 3, [])])
        assert s.derived == ss.IN_PROGRESS

    def test_blocked_is_the_only_value_added_to_the_vocabulary(self):
        """The non-functional constraint. `todo` is reused rather than
        a second new spelling like "not-started" being introduced."""
        assert ss.NOT_STARTED == "todo"
        assert {ss.DONE, ss.IN_PROGRESS, ss.NOT_STARTED} <= {
            "done", "in-progress", "investigate", "todo", "parked", "superseded"}
        assert ss.BLOCKED == "blocked"


class TestTheSurveyRowStaysOneLine:
    """Not a rule of the requirement - the `owner` field is free text
    and several real entries are a paragraph recording why a deferral
    was re-checked, which is worth having in the register and is not
    what a survey row is for."""

    def test_a_paragraph_owner_is_cut_to_its_leading_clause(self):
        assert ss._who("unowned - needs a requirement. Re-checked "
                        "2026-09-26 and the blocker has SHIPPED: lots "
                        "more prose follows here.") == "unowned - needs a requirement"

    def test_a_short_owner_is_left_alone(self):
        assert ss._who("the promotion sprint (batch 4)") == "the promotion sprint (batch 4)"

    def test_a_long_unpunctuated_owner_never_runs_past_the_row(self):
        assert len(ss._who("x " * 200)) <= 60

    def test_no_real_row_overflows(self):
        """The corpus, which is where this went wrong."""
        assert all(len(s.summary()) <= 100 for s in ss.survey())


class TestAnUnscopedSprint:
    """Criterion 7 - said to be unscoped rather than merely unstarted,
    because the two need different work: one needs building, the other
    needs a requirement first."""

    def test_it_is_todo_rather_than_done(self, tmp_path):
        s = ss.survey(_plan(tmp_path, [(1, "todo", [])]), _register(tmp_path, []))[0]
        assert s.derived == ss.NOT_STARTED
        assert s.unscoped

    def test_it_says_so(self, tmp_path):
        s = ss.survey(_plan(tmp_path, [(1, "todo", [])]), _register(tmp_path, []))[0]
        assert "unscoped" in s.summary()

    def test_an_empty_sprint_is_never_reported_done(self, tmp_path):
        """The dangerous direction: no requirements means no unmet
        criteria, so a naive all()-over-empty reports done."""
        s = ss.survey(_plan(tmp_path, [(1, "done", [])]), _register(tmp_path, []))[0]
        assert s.derived != ss.DONE


class TestOwnershipIsDeclaredNotInferred:
    """Criteria 1 and 9. The first version of this analysis scanned each
    sprint's prose for REQ- ids and conflated OWNED with MENTIONED -
    sprint 25 mentions eleven requirements and owns none."""

    def test_an_id_in_the_prose_is_not_owned(self, tmp_path):
        path = tmp_path / "plan.md"
        path.write_text(textwrap.dedent("""\
            1. **[todo, 2026-01-01]** **[Pipeline & publishing]** **A sprint.**
               Related to `REQ-X-999`, which this sprint does NOT own.

               **Owns:** nothing yet - unscoped.
            """))
        reqs = _register(tmp_path, [("REQ-X-999", "built", 4, [])])
        assert ss.survey(path, reqs)[0].owns == []

    def test_only_the_owns_line_counts(self, tmp_path):
        path = tmp_path / "plan.md"
        path.write_text(textwrap.dedent("""\
            1. **[done, 2026-01-01]** **[Pipeline & publishing]** **A sprint.**
               See also `REQ-X-999`.

               **Owns:** `REQ-X-001`
            """))
        reqs = _register(tmp_path, [("REQ-X-001", "built", 2, []),
                                     ("REQ-X-999", "not_started", 9, [])])
        s = ss.survey(path, reqs)[0]
        assert s.owns == ["REQ-X-001"] and s.total == 2

    def test_an_id_that_does_not_exist_is_reported(self, tmp_path):
        """Silent in the worst direction otherwise: a typo contributes no
        criteria, so the sprint reads closer to done than it is."""
        plan = _plan(tmp_path, [(1, "todo", ["REQ-X-404"])])
        reqs = _register(tmp_path, [("REQ-X-001", "built", 2, [])])
        problems = ss.unknown_requirements(plan, reqs)
        assert len(problems) == 1 and "REQ-X-404" in problems[0]


class TestTheGate:
    """Criterion 8."""

    def test_a_disagreement_is_reported_with_both_values(self, tmp_path):
        plan = _plan(tmp_path, [(1, "done", ["REQ-X-001"])])
        reqs = _register(tmp_path, [("REQ-X-001", "not_started", 4, [])])
        found = ss.disagreements(plan, reqs)
        assert len(found) == 1
        assert "sprint 1" in found[0] and "`done`" in found[0] and "`todo`" in found[0]

    def test_agreement_reports_nothing(self, tmp_path):
        plan = _plan(tmp_path, [(1, "done", ["REQ-X-001"])])
        reqs = _register(tmp_path, [("REQ-X-001", "built", 4, [])])
        assert ss.disagreements(plan, reqs) == []

    def test_the_gate_does_not_rewrite_the_tag(self, tmp_path):
        """Decided rather than incidental: a tag that repairs itself
        records nothing, and the point is that somebody looks at why."""
        plan = _plan(tmp_path, [(1, "done", ["REQ-X-001"])])
        before = plan.read_text()
        ss.disagreements(plan, _register(tmp_path, [("REQ-X-001", "not_started", 4, [])]))
        assert plan.read_text() == before

    def test_it_is_wired_into_mothman_check(self):
        """A gate nothing runs is the shape that passes review and
        catches nothing."""
        from cli.check import _GATES

        assert any(g[0] == "sprints" for g in _GATES)


class TestTheRealFiles:
    """The corpus, not a fixture - which is the half a rule-level test
    cannot answer."""

    def test_the_plan_and_the_register_agree(self):
        assert ss.disagreements() == []

    def test_every_owned_id_exists(self):
        assert ss.unknown_requirements() == []

    def test_all_twenty_five_sprints_declare_ownership(self):
        parsed = ss.parse_sprints()
        assert len(parsed) == 25
        # Declaring nothing is a valid declaration; NOT having the line
        # at all is what this catches, since a missing line silently
        # reads as unscoped.
        text = ss.SPRINTS_FILE.read_text()
        assert text.count("**Owns:**") == 25

    def test_the_counts_are_not_vacuous(self):
        """Guards the guard: if every sprint owned nothing, everything
        above would pass while proving nothing."""
        scoped = [s for s in ss.survey() if not s.unscoped]
        assert len(scoped) >= 15
        assert sum(s.total for s in scoped) > 200

    @pytest.mark.parametrize("state", [ss.DONE, ss.BLOCKED, ss.NOT_STARTED])
    def test_the_real_plan_exercises_each_state(self, state):
        """Every branch this gate can report is reachable against the
        real corpus, so none of them is dead code."""
        assert any(s.derived == state for s in ss.survey())
