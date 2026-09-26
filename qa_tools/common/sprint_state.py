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

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
SPRINTS_FILE = ROOT / "plans" / "supply-model.md"
REQUIREMENTS_FILE = ROOT / "requirements.yaml"

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


def _who(owner: str) -> str:
    """The first clause of an `owner`, for a one-line survey row.

    The field is free text and several entries are a paragraph - the
    re-check of a stale deferral belongs there, but it is not what a
    row of the survey is for. Kept to the leading clause rather than
    truncated at a character count, so a row never ends mid-word.
    REQ-DOCS-073 makes the field resolvable, which retires this.
    """
    head = re.split(r"(?<=[a-z0-9\)])[.,;] ", owner.strip(), maxsplit=1)[0]
    head = " ".join(head.split())
    return head if len(head) <= 60 else head[:57].rstrip() + "..."


@dataclass
class Sprint:
    number: int
    tag: str
    owns: list[str]
    met: int = 0
    total: int = 0
    #: What each deferred criterion is waiting on, verbatim from the
    #: requirement's own `unmet_criteria[].owner`. Free text today -
    #: REQ-DOCS-073 makes it resolvable.
    waiting_on: list[str] = field(default_factory=list)

    @property
    def unscoped(self) -> bool:
        return not self.owns

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
        if self.waiting_on and len(self.waiting_on) == (self.total - self.met):
            return BLOCKED
        return IN_PROGRESS

    @property
    def agrees(self) -> bool:
        return self.tag == self.derived

    def summary(self) -> str:
        if self.unscoped:
            return f"{self.number:>3}  {self.derived:12} unscoped"
        counts = f"{self.met}/{self.total}"
        line = f"{self.number:>3}  {self.derived:12} {counts:>7}"
        if self.derived == BLOCKED:
            owners = sorted({_who(w) for w in self.waiting_on})
            line += f"  waiting on {', '.join(owners)}"
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


def survey(sprints_file: Path | str = SPRINTS_FILE,
            requirements_file: Path | str = REQUIREMENTS_FILE) -> list[Sprint]:
    """Every sprint, with its criteria counted against the register."""
    reqs = _requirements(requirements_file)
    out = []
    for number, tag, ids in parse_sprints(sprints_file):
        sprint = Sprint(number=number, tag=tag, owns=ids)
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
                sprint.waiting_on += [str(u.get("owner") or "?") for u in unmet]
        out.append(sprint)
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


def main(argv: list[str] | None = None) -> int:
    """The `mothman check` gate (REQ-DOCS-072 criterion 8).

    Prints the whole survey rather than only the failures, because the
    counts are the thing Keith asked for - "we've built X of Y in this
    sprint" - and a gate that only speaks up when something is wrong
    never shows them.
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
    print("\nsprint state OK - every written tag matches its counted state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
