"""
A delivery sprint's status, COUNTED from its requirements' acceptance
criteria rather than typed in by hand (REQ-DOCS-072).

Why this exists, from the day it was written. Keith asked whether the
sprints scoped a few days earlier were finished. Answering it properly
meant reading `requirements.yaml` rather than the sprint tags, and the
two disagreed on ELEVEN of twenty-five sprints. One of those tags had
been stale for three days and was repeated twice in conversation as
fact. His own framing of the fix:

    "I would rather the overall status truly reflect its actual state
    rather than falsely saying it's done. My dream is going, all right,
    we've built X of Y in this sprint, therefore it's in progress, or
    it's all done, or it's not started."

THE UNIT IS A CRITERION, NOT A REQUIREMENT, and that is the whole
design rather than a detail. Counting requirements is the obvious
choice and it is wrong: a requirement can be `built` and still carry
entries in `unmet_criteria`, which is exactly how sprint 10 came to
read `done` while owing four. Criteria are the finer unit, so the
deferral case falls out for free instead of needing its own rule.

THE FOUR STATES:

    done         every criterion across every requirement it owns is met
    not-started  none are, or the sprint owns no requirement at all
    blocked      it owns nothing unmet - every remaining criterion is
                 DEFERRED TO ANOTHER SPRINT
    in-progress  anything else: real work of its own remains

WHAT "DEFERRED TO ANOTHER SPRINT" MEANS IS NOW RESOLVED, NOT READ
(REQ-DOCS-073, 2026-09-26). Each deferral carries a `blocked_by` naming
sprints and/or requirements, and a requirement resolves to whichever
sprint owns it - so a deferral pointing at this sprint's own work is
correctly NOT a blocker, which prose could never tell. Two sprints
changed state the day this landed, both in the honest direction: a
deferral reading "unowned - needs a requirement" is nobody's, so
nothing is coming and the sprint has work of its own.

`blocked` is the one Keith added (2026-09-26), for a sprint that has
"built all of its stuff and it's waiting on someone else". It carries
what neither `done` nor `in-progress` can say, and sprint 10 is the
case: two requirements built, signed and tested, with four deferrals
that all belong to promotion. Chosen over `waiting` because it sits
unambiguously against `parked`, which already means deliberately set
aside rather than sequenced behind something.

OWNERSHIP IS DECLARED, NEVER INFERRED. Each sprint carries an
`**Owns:**` line. The first version of this analysis scanned each
sprint's prose for `REQ-` ids instead, which conflates what a sprint
OWNS with what it merely mentions - sprint 25 mentions eleven
requirements and owns none, sprint 6 mentions `REQ-DASH-041` and does
not own it - and reported three sprints as wrong when only one was.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
SPRINTS_FILE = ROOT / "plans" / "supply-model.md"
REQUIREMENTS_FILE = ROOT / "requirements.yaml"

#: Set by `mothman check` for a gate that has a warning state, so a
#: warning is distinguishable from a pass without being a failure. Unset
#: everywhere else - CI runs these commands directly as workflow steps,
#: where any non-zero exit fails the step.
WARNING_EXIT_VAR = "MOTHMAN_GATE_WARNING_EXIT"

#: The line a sprint uses to declare what it owns. A dedicated marker
#: rather than reuse of the existing `**Scoped <date>**:` blocks, which
#: carry prose and parenthetical asides and routinely name requirements
#: they do not own.
_OWNS = re.compile(r"^\s*\*\*Owns:\*\*\s*(.*)$", re.M)
_SPRINT = re.compile(r"^(\d+)\. \*\*\[([\w-]+), (\d{4}-\d{2}-\d{2})\]", re.M)
_REQ_ID = re.compile(r"REQ-[A-Z]+-\d+")

DONE = "done"
#: `todo`, not "not-started" - the plans vocabulary's own word for it.
#: This requirement's criteria say "not-started" in prose and its
#: non-functional constraint says exactly ONE value is added; emitting
#: a second new spelling for a state the closed set already names would
#: have broken the second to satisfy the wording of the first.
NOT_STARTED = "todo"
BLOCKED = "blocked"
IN_PROGRESS = "in-progress"


@dataclass(frozen=True)
class Deferral:
    """One criterion a requirement does not meet, and what it waits on.

    `blocked_by` is the resolvable half (REQ-DOCS-073) and `owner` the
    sentence explaining it. Both are carried because they answer
    different questions - one for the tooling, one for the reader.
    """

    requirement: str
    #: Position in that requirement's own `unmet_criteria`. Present so
    #: one criterion counts once even where two sprints share the
    #: requirement holding it - without it, REQ-PIPE-035's three
    #: deferrals were counted twice and promotion read as holding up
    #: twenty criteria when it holds up seventeen.
    index: int
    owner: str
    sprints: tuple[int, ...] = ()
    requirements: tuple[str, ...] = ()
    unowned: bool = False

    def elsewhere(self, mine: int | None, owner_of: dict[str, tuple[int, ...]]) -> bool:
        """True where this waits on work belonging to another sprint.

        An unowned deferral is deliberately NOT elsewhere. Nobody is
        going to build it, so the sprint holding it has a real gap of
        its own rather than a dependency - which is the difference
        between `in-progress` and `blocked`.
        """
        if self.unowned:
            return False
        if any(n != mine for n in self.sprints):
            return True
        # A requirement resolves to the sprints that own it; one this
        # sprint does not own is not this sprint's to build, and one
        # owned by nobody yet certainly is not.
        return any(mine not in owner_of.get(q, ()) for q in self.requirements)

    def waiting_on(self, owner_of: dict[str, tuple[int, ...]]) -> list[str]:
        """Short labels for what this waits on, for a one-line row."""
        if self.unowned:
            return ["nobody yet - needs a requirement"]
        out = [f"sprint {n}" for n in self.sprints]
        for q in self.requirements:
            owners = owner_of.get(q) or ()
            where = ", ".join(f"sprint {n}" for n in owners)
            out.append(f"{q} ({where})" if where else q)
        return out


@dataclass
class Sprint:
    number: int
    tag: str
    owns: list[str]
    met: int = 0
    total: int = 0
    #: Every unmet criterion across the requirements this sprint owns.
    deferrals: list[Deferral] = field(default_factory=list)
    #: Which sprint owns each requirement in the whole register, so a
    #: deferral naming a requirement can be resolved to a sprint.
    owner_of: dict[str, tuple[int, ...]] = field(default_factory=dict)

    @property
    def unscoped(self) -> bool:
        return not self.owns

    @property
    def blocked_by(self) -> list[Deferral]:
        """The deferrals that genuinely belong to somebody else."""
        return [d for d in self.deferrals if d.elsewhere(self.number, self.owner_of)]

    @property
    def derived(self) -> str:
        if self.unscoped or self.total == 0:
            return NOT_STARTED
        if self.met == self.total:
            return DONE
        if self.met == 0:
            return NOT_STARTED
        # Every remaining criterion belongs to somebody else, so there
        # is nothing left for THIS sprint to build.
        remaining = self.total - self.met
        if len(self.blocked_by) == remaining and remaining > 0:
            return BLOCKED
        return IN_PROGRESS

    @property
    def agrees(self) -> bool:
        return self.tag == self.derived

    def waiting_on(self) -> list[str]:
        """What this sprint is waiting on, deduplicated, in order."""
        out: list[str] = []
        for d in self.blocked_by:
            for label in d.waiting_on(self.owner_of):
                if label not in out:
                    out.append(label)
        return out

    def summary(self) -> str:
        if self.unscoped:
            return f"{self.number:>3}  {self.derived:12} unscoped"
        counts = f"{self.met}/{self.total}"
        line = f"{self.number:>3}  {self.derived:12} {counts:>7}"
        if self.derived == BLOCKED:
            line += f"  waiting on {', '.join(self.waiting_on())}"
        return line


def _requirements(path: Path | str = REQUIREMENTS_FILE) -> dict[str, dict]:
    doc = yaml.safe_load(Path(path).read_text()) or {}
    return {r["id"]: r for r in doc.get("requirements", [])}


def parse_sprints(path: Path | str = SPRINTS_FILE) -> list[tuple[int, str, list[str]]]:
    """(number, written status, owned requirement ids) per sprint."""
    text = Path(path).read_text()
    marks = list(_SPRINT.finditer(text))
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.start():end]
        owns_line = _OWNS.search(body)
        ids = _REQ_ID.findall(owns_line.group(1)) if owns_line else []
        out.append((int(m.group(1)), m.group(2), ids))
    return out


def owning_sprints(sprints_file: Path | str = SPRINTS_FILE) -> dict[str, tuple[int, ...]]:
    """Which sprints own each requirement, from the `**Owns:**` lines.

    A TUPLE BECAUSE OWNERSHIP IS GENUINELY SHARED, found the day this
    was written: `REQ-PIPE-035` is owned by sprint 13 for
    schema-per-period and by sprint 18 for drift and trend, and both
    claims are real. The first version of this returned one number and
    silently kept whichever sprint came last in the file, which
    deleted sprint 13 from the dependency view altogether.
    """
    out: dict[str, list[int]] = {}
    for number, _tag, ids in parse_sprints(sprints_file):
        for req_id in ids:
            out.setdefault(req_id, []).append(number)
    return {q: tuple(ns) for q, ns in out.items()}


def survey(sprints_file: Path | str = SPRINTS_FILE,
            requirements_file: Path | str = REQUIREMENTS_FILE) -> list[Sprint]:
    """Every sprint, with its criteria counted against the register."""
    reqs = _requirements(requirements_file)
    owner_of = owning_sprints(sprints_file)
    out = []
    for number, tag, ids in parse_sprints(sprints_file):
        sprint = Sprint(number=number, tag=tag, owns=ids, owner_of=owner_of)
        for req_id in ids:
            req = reqs.get(req_id)
            if req is None:
                continue
            criteria = len(req.get("acceptance_criteria") or [])
            unmet = req.get("unmet_criteria") or []
            sprint.total += criteria
            # A criterion is met only where the requirement is BUILT and
            # nothing defers it. An unbuilt requirement contributes its
            # whole count to the denominator and nothing to the top.
            if req.get("status") == "built":
                sprint.met += max(criteria - len(unmet), 0)
                sprint.deferrals += [_deferral(req_id, u, i) for i, u in enumerate(unmet)]
        out.append(sprint)
    return out


def _deferral(req_id: str, raw: dict, index: int) -> Deferral:
    blocked = raw.get("blocked_by") or {}
    return Deferral(
        requirement=req_id,
        index=index,
        owner=str(raw.get("owner") or "?"),
        sprints=tuple(blocked.get("sprints") or ()),
        requirements=tuple(blocked.get("requirements") or ()),
        unowned=bool(blocked.get("unowned")),
    )


def all_deferrals(sprints_file: Path | str = SPRINTS_FILE,
                   requirements_file: Path | str = REQUIREMENTS_FILE) -> list[Deferral]:
    """Every deferral in the register, whether or not a sprint owns it.

    Read from the register rather than gathered off the survey, because
    a requirement no sprint owns still has deferrals and they are still
    dependencies - leaving them out would make the view quietly
    incomplete in the one direction nobody checks.
    """
    reqs = _requirements(requirements_file)
    out = []
    for req_id, req in reqs.items():
        if req.get("status") != "built":
            continue
        out += [_deferral(req_id, u, i)
                for i, u in enumerate(req.get("unmet_criteria") or [])]
    return out


def satisfied_blockers(sprints_file: Path | str = SPRINTS_FILE,
                        requirements_file: Path | str = REQUIREMENTS_FILE) -> list[str]:
    """Deferrals whose every named blocker has since been delivered.

    REQ-DOCS-073 criteria 3 and 4. Reported, NEVER cleared: a blocker
    shipping is evidence the criterion CAN now be met, not that it has
    been. Proved rather than assumed - on 2026-09-26 seven deferrals
    had blockers that had shipped and not one of them turned out to be
    met when checked.

    A deferral naming several blockers is only reported once ALL of
    them are delivered. One still outstanding means the deferral is
    doing its job.
    """
    reqs = _requirements(requirements_file)
    done_sprints = {s.number for s in survey(sprints_file, requirements_file)
                    if s.derived == DONE}
    out = []
    for d in all_deferrals(sprints_file, requirements_file):
        if d.unowned or not (d.sprints or d.requirements):
            continue
        blockers = ([("sprint %d" % n, n in done_sprints) for n in d.sprints]
                     + [(q, (reqs.get(q) or {}).get("status") == "built")
                        for q in d.requirements])
        if blockers and all(delivered for _name, delivered in blockers):
            names = ", ".join(name for name, _ in blockers)
            out.append(f"{d.requirement}: waits on {names}, which "
                        f"{'have' if len(blockers) > 1 else 'has'} since been "
                        f"delivered - re-test the criterion, or re-point it")
    return out


def unknown_requirements(sprints_file: Path | str = SPRINTS_FILE,
                          requirements_file: Path | str = REQUIREMENTS_FILE) -> list[str]:
    """Every id a sprint claims to own that the register does not hold.

    A typo here is otherwise silent in the worst direction: the id
    contributes no criteria, so the sprint's count shrinks and it reads
    closer to done than it is.
    """
    reqs = _requirements(requirements_file)
    bad = []
    for number, _tag, ids in parse_sprints(sprints_file):
        bad += [f"sprint {number} owns {q}, which is not in the register"
                 for q in ids if q not in reqs]
    return bad


def disagreements(sprints_file: Path | str = SPRINTS_FILE,
                   requirements_file: Path | str = REQUIREMENTS_FILE) -> list[str]:
    """Every sprint whose written tag differs from the counted truth.

    Reported rather than corrected. A tag that repairs itself records
    nothing - the point is that somebody looks at why it moved.
    """
    out = []
    for s in survey(sprints_file, requirements_file):
        if not s.agrees:
            counts = "unscoped" if s.unscoped else f"{s.met}/{s.total} criteria met"
            out.append(f"sprint {s.number}: written `{s.tag}`, "
                        f"counted `{s.derived}` ({counts})")
    return out


def dependency_data(sprints_file: Path | str = SPRINTS_FILE,
                     requirements_file: Path | str = REQUIREMENTS_FILE) -> dict:
    """The dependency graph, as data (REQ-DOCS-073 criteria 5 and 6).

    Both directions, because they are different questions with
    different readers. "What is sprint 10 waiting on" is what you ask
    before picking it up; "what is waiting on sprint 11" is what tells
    you that promotion closes remainders in seven other sprints at
    once, which the sprint list alone could never show.

    COMPUTED ONCE, HERE, and rendered by both the CLI and the
    dashboard rather than implemented twice. This project has already
    paid for a second implementation of a shared rule: four
    independent copies of the status logic, one of which rendered a
    check with fourteen real violations green. The dashboard embeds
    this structure at build time.

    BUILT FROM EVERY DEFERRAL IN THE REGISTER, not from the sprints'
    own. A requirement no sprint owns still has deferrals and they are
    still real dependencies - REQ-PIPE-068 is exactly that today, and
    the first version of this walked the survey instead and dropped
    its edge silently.
    """
    rows = survey(sprints_file, requirements_file)
    owner_of = owning_sprints(sprints_file)
    counted = {s.number: s for s in rows}

    waits: dict[int | None, list[str]] = {}
    #: blocker sprint -> the distinct criteria it holds up, and whose.
    held: dict[int, set[tuple[str, int]]] = {}
    whose: dict[int, set[int | None]] = {}
    for d in all_deferrals(sprints_file, requirements_file):
        owners: tuple[int | None, ...] = owner_of.get(d.requirement) or (None,)
        for mine in owners:
            if not d.elsewhere(mine, owner_of):
                continue
            for label in d.waiting_on(owner_of):
                if label not in waits.setdefault(mine, []):
                    waits[mine].append(label)
            blockers = {n for n in d.sprints if n != mine}
            for q in d.requirements:
                blockers |= {n for n in (owner_of.get(q) or ()) if n != mine}
            for n in blockers:
                held.setdefault(n, set()).add((d.requirement, d.index))
                whose.setdefault(n, set()).add(mine)

    out = []
    for number in sorted((set(waits) | set(held)) - {None}):
        sprint = counted.get(number)
        unscoped = sprint is None or sprint.unscoped
        out.append({
            "sprint": number,
            "status": "unscoped" if unscoped else sprint.derived,
            "met": None if unscoped else sprint.met,
            "total": None if unscoped else sprint.total,
            "waits_on": waits.get(number, []),
            "holds_up": len(held.get(number, ())),
            "holds_up_sprints": sorted(n for n in whose.get(number, ()) if n is not None),
            "holds_up_unowned": None in whose.get(number, set()),
        })
    return {
        "sprints": out,
        # A deferral on a requirement no sprint owns is still a
        # dependency, and belongs to no row above.
        "unowned_waits_on": waits.get(None, []),
        "stale": satisfied_blockers(sprints_file, requirements_file),
    }


def dependency_view(sprints_file: Path | str = SPRINTS_FILE,
                     requirements_file: Path | str = REQUIREMENTS_FILE) -> list[str]:
    """`dependency_data()` as lines of text, for the terminal."""
    data = dependency_data(sprints_file, requirements_file)
    out: list[str] = []
    for row in data["sprints"]:
        out.append(f"sprint {row['sprint']} [{row['status']}] {row['met']}/{row['total']}"
                    if row["total"] is not None
                    else f"sprint {row['sprint']} [unscoped] - nothing written yet")
        if row["waits_on"]:
            out.append(f"    waits on:   {', '.join(row['waits_on'])}")
        if row["holds_up"]:
            where = [f"sprint {n}" for n in row["holds_up_sprints"]]
            if row["holds_up_unowned"]:
                where.append("work no sprint owns")
            noun = "criterion" if row["holds_up"] == 1 else "criteria"
            out.append(f"    holds up:   {row['holds_up']} {noun} in {', '.join(where)}")
    if data["unowned_waits_on"]:
        out.append("no sprint owns these, and they are waiting too")
        out.append(f"    waits on:   {', '.join(data['unowned_waits_on'])}")
    return out


def main(argv: list[str] | None = None) -> int:
    """The `mothman check` gate (REQ-DOCS-072 criterion 8).

    Prints the whole survey rather than only the failures, because the
    counts are the thing Keith asked for - "we've built X of Y in this
    sprint" - and a gate that only speaks up when something is wrong
    never shows them.

    A STALE DEFERRAL WARNS RATHER THAN FAILS (REQ-DOCS-073 criterion 3,
    Keith's own call). It is not wrong the way a mismatched tag is - it
    is a prompt to go and look, and the looking needs a person. Failing
    the build for it would also put pressure on whoever hit it to clear
    the deferral to get green, which is the auto-clearing this
    deliberately rejects, arrived at by the back door.
    """
    bad_ids = unknown_requirements()
    rows = survey()
    for row in rows:
        print(row.summary())
    tally = {}
    for row in rows:
        tally[row.derived] = tally.get(row.derived, 0) + 1
    print("\n" + ", ".join(f"{n} {s}" for s, n in sorted(tally.items())))

    problems = bad_ids + disagreements()
    if problems:
        print(f"\nsprint state FAILED ({len(problems)} problem(s)):")
        for p in problems:
            print(f"  - {p}")
        print("\nThe plans file and the register disagree. Fix the tag, or fix\n"
               "the requirement - this gate deliberately does not choose.")
        return 1

    stale = satisfied_blockers()
    if stale:
        print(f"\nsprint state OK, with {len(stale)} deferral(s) worth re-testing:")
        for s in stale:
            print(f"  - {s}")
        print("\nA blocker shipping is evidence the criterion CAN now be met, never\n"
               "that it has been - check each one rather than clearing it.")
        return int(os.environ.get(WARNING_EXIT_VAR) or 0)
    print("\nsprint state OK - every written tag matches its counted state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
