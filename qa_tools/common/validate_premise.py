"""Nothing may still say the dashboard is built from committed files
(REQ-DOCS-101 criterion 7).

WHY A GATE RATHER THAN A REVIEW. REQ-PIPE-089 moved the QA history into
the database and REQ-PIPE-092 moved the publisher out of GitHub Actions,
and between them they falsified a premise stated in fifteen signed
requirements and three documents. A sweep fixed those. What a sweep
cannot do is stay fixed: the next requirement drafted from a stale
paragraph reintroduces the contradiction, and the register then reads as
though it agrees with itself while some clauses carry the old premise.
This requirement's own first NFR names that as the real risk - a
half-done sweep is worse than none.

HOW IT WORKS, and the shape is this project's own: a scan for the retired
phrases, plus an explicit ALLOWLIST of the places that legitimately still
say them. The allowlist is the load-bearing half. Every retired premise
has places where naming it is correct - an AMENDED note saying what the
clause used to read, a decision recording what was known at the time, a
docstring explaining why a mechanism was replaced - and a scan without an
allowlist would either fail on all of those or be written so loosely that
it catches nothing.

WHAT IT DOES NOT DO. It does not judge prose quality and it does not
enforce a house style for amendments. It answers one question: does any
line in this repository still ASSERT a retired premise as though it were
current? An assertion is a line that says it plainly with nothing nearby
marking it as history, and "nearby" is what the allowlist encodes.

TWO THINGS ARE DELIBERATELY OUT OF SCOPE, both named on the requirement
itself (criterion 8 and the third NFR):

  - a `decisions:` field is never checked, because a decision records
    what was known when it was taken and editing one to agree with a
    later design destroys the only record of the reasoning.
  - REQ-DASH-055 NFR 4 and the notes on REQ-GEN-042/043 merely MENTION
    the words, and are named in the allowlist so a later reader does not
    amend them for consistency's sake and change what they mean.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

#: The retired premises, as the phrases that assert them. Deliberately
#: narrow: each one is a phrase that can only be an assertion about where
#: results live or who publishes, never an incidental word.
#:
#: NOT "committed history" ON ITS OWN, which appears legitimately in
#: every amendment note that quotes what a clause used to read. The
#: phrases here are the CLAIMS.
RETIRED_PREMISES: dict[str, str] = {
    r"qa_results/ is committed":
        "the QA history is a table in the metadata schema (REQ-PIPE-089)",
    r"committed to git, not gitignored":
        "recorded in the database (REQ-PIPE-089)",
    r"only CI can (?:deploy|publish)":
        "the publisher runs where the data is (REQ-PIPE-092)",
    r"CI is the only publish path":
        "the publisher runs where the data is (REQ-PIPE-092)",
    r"rebuilt? (?:the .*)?from committed qa_results":
        "rebuilt from the recorded QA history (REQ-PIPE-089)",
    r"CI (?:rebuilds|builds|deploys|publishes) the (?:whole )?dashboard":
        "the publisher runs where the data is (REQ-PIPE-092)",
    r"[Cc]ommitted (?:per-run )?QA (?:results|history)(?! used| was| is a table)":
        "recorded QA history, in the metadata schema (REQ-PIPE-089)",
}

#: A NAME IS NOT A CLAIM, and this is the one refinement that made the
#: gate usable. The first draft hunted `deploy-pages.yml`, the retired
#: workflow, and found 41 lines - almost all of them CLAUDE.md and README
#: narrating real history, plus two enormous single-line table rows that
#: happened to contain the phrase somewhere in 400 characters. A gate that
#: fires on every mention of a retired thing is a gate that forces its own
#: history to be deleted, which is the opposite of what criterion 5 asks
#: for. So the patterns above are ASSERTIONS - a sentence that can only be
#: a claim about where results live or who publishes.

#: WHERE EACH PHRASE MAY STILL APPEAR, and why. A path prefix plus the
#: reason, so the reason is in the file rather than in a commit message.
#:
#: THE PLANS DIRECTORY IS ALLOWED WHOLESALE and that is a real decision
#: rather than laziness: `plans/*.md` is working material that records
#: what was believed at the time, and CLAUDE.md's own rule is that it
#: gets DELETED as its requirements land rather than rewritten. A gate
#: forcing it into line would be a gate forcing history to be falsified.
ALLOWED: tuple[tuple[str, str], ...] = (
    ("plans/", "working material; records what was believed when written"),
    ("CHANGELOG.yaml", "a release note describes the change that retired it"),
    ("qa_tools/common/validate_premise.py", "this gate names the phrases it hunts"),
    ("tests/test_validate_premise.py", "its tests have to state one to catch one"),
    ("docs/aws-event-driven-mvp-design.md",
     "carries its own RETIRED sections, which say what they replaced"),
)

#: A line marks itself as HISTORY rather than an assertion by carrying one
#: of these. Kept short on purpose: a long list of escape words is a gate
#: nobody can fail.
HISTORY_MARKERS = (
    "AMENDED", "SUPERSEDED", "RETIRED", "used to", "USED TO", "no longer",
    "NO LONGER", "was retired", "until REQ-PIPE-", "before REQ-PIPE-",
    "since REQ-PIPE-", "struck", "Struck", "~~",
)

#: A LINE THAT FORBIDS A PREMISE IS NOT ASSERTING IT, and REQ-DOCS-101's
#: own criterion 1 is the proof: it has to name the retired premise in
#: order to forbid it, and so does this gate's own test. Without these the
#: gate fails on the requirement that asked for the gate, which is the
#: kind of circularity that gets a gate deleted rather than fixed.
NEGATION_MARKERS = (
    "SHALL NOT", "shall not", "leave no", "no requirement", "never",
    "must not", "MUST NEVER", "must never", "stop",
)

#: Files this never reads. `decisions:` lives inside requirements.yaml, so
#: that file is scanned with the decisions fields excluded rather than
#: skipped - see `_lines_to_scan`.
SKIP_SUFFIXES = (".pyc", ".gz", ".woff2", ".cast", ".png", ".jpg", ".ico")
SKIP_DIRS = (".git", ".venv", "node_modules", "data", "reports", "_site",
             "dbt_project/target", "dbt_project/dbt_packages", ".playwright-mcp",
             "__pycache__", ".pytest_cache", "dashboard/snapshots",
             # The explainer agents' gitignored working folder: its
             # review reports quote a draft's prose on purpose, so a
             # finding about an old sentence would fail this gate
             # locally for text nobody committed (REQ-DOCS-129).
             "docs/explainers/_work")

#: Build outputs, which carry whatever the template said and are
#: gitignored. Scanning one means a stale local build fails the gate for a
#: line nobody wrote.
SKIP_FILES = ("dashboard/qa-reporting-dashboard.html",)


def _is_allowed(rel: str) -> str | None:
    for prefix, reason in ALLOWED:
        if rel.startswith(prefix):
            return reason
    return None


def _files() -> list[Path]:
    out = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if any(part in rel.split("/") for part in SKIP_DIRS) \
                or any(rel.startswith(d) for d in SKIP_DIRS):
            continue
        if path.suffix in SKIP_SUFFIXES or rel in SKIP_FILES:
            continue
        out.append(path)
    return out


#: Fields in requirements.yaml this never reads, and why each is a RECORD
#: rather than a claim about the present.
#:
#: `decisions` is criterion 8's own: a decision records what was known
#: when it was taken, and editing one to agree with a later design
#: destroys the only account of the reasoning.
#:
#: `evidence` is here on the same grounds, which the requirement does not
#: name and which the first real run of this gate surfaced: an evidence
#: entry dated 2026-09-16 says a rebuild from committed qa_results/ was
#: diffed byte-identical, and that is TRUE OF THAT DAY. Rewording it to
#: "recorded history" would claim a measurement nobody took. A dated
#: measurement is a record, not an assertion about now.
HISTORICAL_FIELDS = ("decisions:", "evidence:")


def _historical_line_numbers(text: str) -> set[int]:
    """Every line inside a field that records rather than asserts."""
    skip: set[int] = set()
    inside = False
    block_indent = 0
    for i, line in enumerate(text.split("\n"), 1):
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if any(stripped.startswith(field) for field in HISTORICAL_FIELDS):
            inside, block_indent = True, indent
            continue
        if inside:
            if stripped and indent <= block_indent:
                inside = False
            else:
                skip.add(i)
    return skip


def _flat(text: str) -> str:
    """The same text with its line breaks and indentation collapsed, so a
    phrase wrapped across lines reads as one phrase."""
    return re.sub(r"\s+", " ", text).strip()


def _paragraphs(lines: list[str]) -> list[tuple[int, str]]:
    """The file as STATEMENTS - maximal runs of consecutive non-blank
    lines - each with the line number it starts on.

    A PARAGRAPH RATHER THAN A LINE, and the first draft of this gate got
    it wrong twice in two different directions, both from the same fact:
    YAML wraps a block scalar over several lines, so one statement is many
    lines and neither its meaning nor its wording survives being read a
    line at a time.

      - A NEGATION LANDS ON A DIFFERENT LINE FROM THE PHRASE. "THE SYSTEM
        SHALL NOT embed any part of it into committed QA results" arrives
        as two lines, and the gate reported a criterion that FORBIDS the
        premise as one asserting it - including REQ-DOCS-101's own
        criterion 1, the requirement that asked for this gate.
      - A PHRASE ITSELF IS SPLIT. "committed to git, not gitignored" wraps
        after "committed to", and a line-by-line regex finds neither half.
        That is worse than a false positive: the gate reports clean while
        the assertion is right there.

    A WINDOW AROUND EACH LINE WAS THE SECOND ATTEMPT and produced a third
    problem - one wrapped assertion reported four times, once per line of
    the window, plus reports anchored on lines that contain nothing.
    Paragraphs fix all three, because a paragraph is the unit both the
    phrase and its markers actually live in.

    IT SUITS EVERY FILE THIS SCANS, which is why it is not a YAML parse: a
    block scalar, a Markdown paragraph and a docstring section are all
    runs of non-blank lines.
    """
    out: list[tuple[int, str]] = []
    buffer: list[str] = []
    first = 0
    for i, line in enumerate(lines, 1):
        if line.strip():
            if not buffer:
                first = i
            buffer.append(line)
            continue
        if buffer:
            out.append((first, "\n".join(buffer)))
            buffer = []
    if buffer:
        out.append((first, "\n".join(buffer)))
    return out


def findings() -> list[str]:
    problems: list[str] = []
    for path in _files():
        rel = path.relative_to(ROOT).as_posix()
        if _is_allowed(rel):
            continue
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        skip = _historical_line_numbers(text) if rel.endswith((".yaml", ".yml")) else set()
        lines = text.split("\n")
        for start_line, paragraph in _paragraphs(lines):
            span = range(start_line, start_line + paragraph.count("\n") + 1)
            if any(n in skip for n in span):
                continue
            if any(marker in paragraph for marker in HISTORY_MARKERS) \
                    or any(marker in paragraph for marker in NEGATION_MARKERS):
                continue
            flat = _flat(paragraph)
            for pattern, correction in RETIRED_PREMISES.items():
                if re.search(pattern, flat):
                    problems.append(
                        f"{rel}:{start_line}: asserts a retired premise - "
                        f"{flat[:120]}\n"
                        f"    the current answer is: {correction}\n"
                        f"    if this is HISTORY, say so in it (one of: "
                        f"{', '.join(HISTORY_MARKERS[:4])}, ...)")
    return problems


def main() -> int:
    problems = findings()
    if problems:
        print(f"{len(problems)} line(s) still assert a premise this design retired:\n")
        for problem in problems:
            print(problem)
        print("\nREQ-DOCS-101 criterion 7. A contradiction that reads as current is "
               "worse than a gap: it leaves two accounts and nothing saying which wins.")
        return 1
    print(f"premise validation OK - {len(RETIRED_PREMISES)} retired premise(s), "
          f"no line asserts one.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
