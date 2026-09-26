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


def _blocked_by(owner):
    """A deferral's resolvable blocker, from the shorthand a test uses.

    An int is a sprint, a `REQ-` string is a requirement, anything else
    is unowned - which keeps the tests readable while still exercising
    the real three-way shape.
    """
    if isinstance(owner, int):
        return {"sprints": [owner]}
    if isinstance(owner, str) and owner.startswith("REQ-"):
        return {"requirements": [owner]}
    return {"unowned": True}


def _register(tmp_path, reqs: list[tuple[str, str, int, list]]):
    """`reqs` is (id, status, criteria count, unmet owners)."""
    out = []
    for req_id, status, n, unmet in reqs:
        out.append({
            "id": req_id, "status": status,
            "acceptance_criteria": [f"THE SYSTEM SHALL do thing {i}." for i in range(n)],
            **({"unmet_criteria": [{"criterion": "x", "why": "y", "owner": str(o),
                                     "blocked_by": _blocked_by(o)}
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
        s = _one(tmp_path, "done", [("REQ-X-001", "built", 12, [11, 11])])
        assert (s.met, s.total) == (10, 12)
        assert s.derived != ss.DONE

    def test_counting_requirements_instead_would_have_said_done(self, tmp_path):
        """The rejected design, asserted so nobody reverts to it."""
        s = _one(tmp_path, "done", [("REQ-X-001", "built", 12, [11])])
        built = all(True for _ in [1])  # every requirement IS built
        assert built and s.derived != ss.DONE


class TestBlocked:
    """Criteria 3 and 4 - Keith's own addition, for a sprint that has
    "built all of its stuff and it's waiting on someone else"."""

    def test_a_sprint_owing_only_deferrals_is_blocked(self, tmp_path):
        s = _one(tmp_path, "done", [("REQ-X-001", "built", 5, [11])])
        assert s.derived == ss.BLOCKED

    def test_it_names_what_it_waits_on(self, tmp_path):
        s = _one(tmp_path, "done", [("REQ-X-001", "built", 5, [11])])
        assert "sprint 11" in s.summary()

    def test_work_of_its_own_outranks_a_deferral(self, tmp_path):
        """A sprint with an unbuilt requirement AND a deferral is
        in-progress, not blocked - somebody can still work on it."""
        s = _one(tmp_path, "in-progress", [("REQ-X-001", "built", 5, [11]),
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
    """The row is built from resolved blockers now, not from the prose.

    This class used to test a truncator over the free-text `owner`,
    written the same afternoon because several owners are a paragraph.
    REQ-DOCS-073 removed the need for it rather than improving it -
    the labels come from `blocked_by`, so they are short by
    construction.
    """

    def test_a_paragraph_owner_never_reaches_the_row(self, tmp_path):
        paragraph = ("the promotion sprint (batch 4). Re-checked 2026-09-26 and "
                      "the blocker has SHIPPED, so the reason recorded here is "
                      "no longer the real one, and it needs a person to look.")
        plan = _plan(tmp_path, [(1, "blocked", ["REQ-X-001"])])
        reqs = tmp_path / "reqs.yaml"
        reqs.write_text(yaml.safe_dump({"requirements": [{
            "id": "REQ-X-001", "status": "built",
            "acceptance_criteria": ["a", "b", "c"],
            "unmet_criteria": [{"criterion": "x", "why": "y", "owner": paragraph,
                                 "blocked_by": {"sprints": [9]}}],
        }]}))
        row = ss.survey(plan, reqs)[0].summary()
        assert "sprint 9" in row
        assert "Re-checked" not in row and len(row) <= 100

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


class TestWhatCountsAsBlocked:
    """REQ-DOCS-073 made "deferred to ANOTHER sprint" resolvable, and
    three sprints changed state the day it landed - all three in the
    honest direction."""

    def test_an_unowned_deferral_does_not_block(self, tmp_path):
        """Nobody is going to build it, so the sprint holding it has a
        gap of its own rather than a dependency. Sprints 1, 6 and 7
        were all reading `blocked` on exactly this."""
        s = _one(tmp_path, "in-progress", [("REQ-X-001", "built", 5, ["nobody"])])
        assert s.derived == ss.IN_PROGRESS

    def test_a_deferral_to_this_sprints_own_work_does_not_block(self, tmp_path):
        """The case prose could never tell: a requirement this sprint
        owns is not somebody else."""
        plan = _plan(tmp_path, [(1, "in-progress", ["REQ-X-001", "REQ-X-002"])])
        reqs = _register(tmp_path, [("REQ-X-001", "built", 5, ["REQ-X-002"]),
                                     ("REQ-X-002", "built", 3, [])])
        assert ss.survey(plan, reqs)[0].derived == ss.IN_PROGRESS

    def test_a_deferral_to_another_sprints_requirement_does_block(self, tmp_path):
        plan = _plan(tmp_path, [(1, "blocked", ["REQ-X-001"]),
                                 (2, "done", ["REQ-X-002"])])
        reqs = _register(tmp_path, [("REQ-X-001", "built", 5, ["REQ-X-002"]),
                                     ("REQ-X-002", "built", 3, [])])
        assert ss.survey(plan, reqs)[0].derived == ss.BLOCKED


class TestSharedOwnership:
    """A REAL DEFECT, found by running the view rather than by reading
    it. `REQ-PIPE-035` is owned by sprint 13 for schema-per-period and
    by sprint 18 for drift; resolving a requirement to ONE sprint kept
    whichever came last in the file and deleted sprint 13 from the
    dependency view entirely."""

    def test_a_requirement_can_be_owned_by_two_sprints(self, tmp_path):
        # No register needed: ownership is read from the plan alone,
        # which is the point - a requirement's owners are declared,
        # never inferred from the register.
        plan = _plan(tmp_path, [(1, "blocked", ["REQ-X-001"]),
                                 (2, "blocked", ["REQ-X-001"])])
        assert ss.owning_sprints(plan)["REQ-X-001"] == (1, 2)

    def test_both_owners_appear_in_the_view(self, tmp_path):
        plan = _plan(tmp_path, [(1, "blocked", ["REQ-X-001"]),
                                 (2, "blocked", ["REQ-X-001"]),
                                 (9, "todo", [])])
        reqs = _register(tmp_path, [("REQ-X-001", "built", 4, [9])])
        rows = ss.dependency_data(plan, reqs)["sprints"]
        assert {r["sprint"] for r in rows} == {1, 2, 9}

    def test_a_shared_criterion_is_counted_once(self, tmp_path):
        """Not once per owning sprint. Promotion read as holding up
        twenty criteria when it holds up seventeen."""
        plan = _plan(tmp_path, [(1, "blocked", ["REQ-X-001"]),
                                 (2, "blocked", ["REQ-X-001"]),
                                 (9, "todo", [])])
        reqs = _register(tmp_path, [("REQ-X-001", "built", 4, [9])])
        nine = [r for r in ss.dependency_data(plan, reqs)["sprints"] if r["sprint"] == 9][0]
        assert nine["holds_up"] == 1
        assert nine["holds_up_sprints"] == [1, 2]


class TestTheStaleDeferralWarning:
    """Criteria 2 and 3."""

    def test_a_deferral_whose_blocker_shipped_is_reported(self, tmp_path):
        plan = _plan(tmp_path, [(1, "blocked", ["REQ-X-001"])])
        reqs = _register(tmp_path, [("REQ-X-001", "built", 4, ["REQ-X-002"]),
                                     ("REQ-X-002", "built", 3, [])])
        found = ss.satisfied_blockers(plan, reqs)
        assert len(found) == 1 and "REQ-X-002" in found[0]

    def test_an_outstanding_blocker_is_not_reported(self, tmp_path):
        """Guards the guard: if everything were reported the test above
        would pass while proving nothing."""
        plan = _plan(tmp_path, [(1, "blocked", ["REQ-X-001"])])
        reqs = _register(tmp_path, [("REQ-X-001", "built", 4, ["REQ-X-002"]),
                                     ("REQ-X-002", "not_started", 3, [])])
        assert ss.satisfied_blockers(plan, reqs) == []

    def test_one_outstanding_blocker_keeps_the_whole_deferral_live(self, tmp_path):
        """A deferral naming several is only stale once ALL have
        landed - REQ-PIPE-065 names promotion AND a built requirement,
        and is not stale."""
        plan = _plan(tmp_path, [(1, "blocked", ["REQ-X-001"]), (9, "todo", [])])
        reqs = tmp_path / "reqs.yaml"
        reqs.write_text(yaml.safe_dump({"requirements": [
            {"id": "REQ-X-001", "status": "built",
             "acceptance_criteria": ["a", "b", "c", "d"],
             "unmet_criteria": [{"criterion": "x", "why": "y", "owner": "z",
                                  "blocked_by": {"sprints": [9],
                                                  "requirements": ["REQ-X-002"]}}]},
            {"id": "REQ-X-002", "status": "built", "acceptance_criteria": ["a"]},
        ]}))
        assert ss.satisfied_blockers(plan, reqs) == []

    def test_it_is_never_treated_as_met(self, tmp_path):
        """Criterion 4, asserted rather than described. Seven deferrals
        had blockers that shipped on 2026-09-26 and not one of them
        turned out to be met."""
        plan = _plan(tmp_path, [(1, "blocked", ["REQ-X-001"])])
        reqs = _register(tmp_path, [("REQ-X-001", "built", 4, ["REQ-X-002"]),
                                     ("REQ-X-002", "built", 3, [])])
        s = ss.survey(plan, reqs)[0]
        assert s.met == 3 and s.total == 4 and s.derived != ss.DONE

    def test_the_gate_warns_rather_than_fails(self, monkeypatch, capsys):
        """Criterion 3. Exercised through main() against the real
        files, with the warning channel `mothman check` uses."""
        monkeypatch.setattr(ss, "satisfied_blockers",
                            lambda *a, **k: ["REQ-X-001: waits on sprint 9, which has landed"])
        monkeypatch.setenv(ss.WARNING_EXIT_VAR, "78")
        assert ss.main() == 78
        assert "worth re-testing" in capsys.readouterr().out

    def test_without_the_channel_it_is_a_plain_pass(self, monkeypatch):
        """CI runs these commands directly as workflow steps, where any
        non-zero exit fails the step."""
        monkeypatch.setattr(ss, "satisfied_blockers",
                            lambda *a, **k: ["REQ-X-001: waits on sprint 9, which has landed"])
        monkeypatch.delenv(ss.WARNING_EXIT_VAR, raising=False)
        assert ss.main() == 0


class TestTheDependencyView:
    """Criterion 5 - both directions."""

    def test_it_says_what_a_sprint_waits_on(self, tmp_path):
        plan = _plan(tmp_path, [(1, "blocked", ["REQ-X-001"]), (9, "todo", [])])
        reqs = _register(tmp_path, [("REQ-X-001", "built", 4, [9])])
        one = [r for r in ss.dependency_data(plan, reqs)["sprints"] if r["sprint"] == 1][0]
        assert one["waits_on"] == ["sprint 9"]

    def test_it_says_what_waits_on_a_sprint(self, tmp_path):
        plan = _plan(tmp_path, [(1, "blocked", ["REQ-X-001"]), (9, "todo", [])])
        reqs = _register(tmp_path, [("REQ-X-001", "built", 4, [9])])
        nine = [r for r in ss.dependency_data(plan, reqs)["sprints"] if r["sprint"] == 9][0]
        assert nine["holds_up"] == 1 and nine["holds_up_sprints"] == [1]

    def test_a_requirement_no_sprint_owns_is_still_in_the_graph(self, tmp_path):
        """A REAL HOLE in the first version, which walked the survey:
        REQ-PIPE-068 is owned by no sprint, so its edge vanished."""
        plan = _plan(tmp_path, [(9, "todo", [])])
        reqs = _register(tmp_path, [("REQ-X-001", "built", 4, [9])])
        data = ss.dependency_data(plan, reqs)
        assert data["unowned_waits_on"] == ["sprint 9"]
        nine = [r for r in data["sprints"] if r["sprint"] == 9][0]
        assert nine["holds_up"] == 1 and nine["holds_up_unowned"]

    def test_the_text_view_renders_the_same_data(self, tmp_path):
        """One implementation, two renderings - the CLI and the
        dashboard must not drift."""
        plan = _plan(tmp_path, [(1, "blocked", ["REQ-X-001"]), (9, "todo", [])])
        reqs = _register(tmp_path, [("REQ-X-001", "built", 4, [9])])
        lines = ss.dependency_view(plan, reqs)
        assert any("waits on:   sprint 9" in ln for ln in lines)
        assert any("holds up:   1 criterion in sprint 1" in ln for ln in lines)


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
