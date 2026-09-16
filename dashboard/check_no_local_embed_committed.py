"""
Pre-commit guard for Phase 3's rule (plans/publishing-and-history.md):
never commit a local rebuild of dashboard/qa-reporting-dashboard.html's
two embedded data consts (REAL_BIRTH_REG_DATA/REAL_CP_DATA) - CI
rebuilds and deploys them itself, on every push, from committed
qa_results/ history; the git-committed copy of these two lines is
deliberately frozen (see that file's own header comment for the full
incident this policy came from). A local `./run_pipeline.sh` run (or a
Playwright verification pass, dashboard/check_dashboard_renders.py)
legitimately rewrites them in the working tree for local preview -
that's expected - but committing that rewrite reintroduces the exact
commit-back race Phase 3 was built to avoid.

Blocks a commit only when EVERY changed line in the staged diff for
this file is one of the two `const REAL_*_DATA = ...;` lines - a
genuine hand-edit to the dashboard's HTML/CSS/JS (which IS meant to be
committed directly - see CLAUDE.md's own dashboard/ table entry) will
always touch other lines too, so this never blocks real work.

Wired in as a local pre-commit hook (.pre-commit-config.yaml) - run
`pre-commit install` once (README's Development section) to have this
fire automatically on every `git commit`.
"""
from __future__ import annotations
import re
import subprocess
import sys

DASHBOARD_PATH = "dashboard/qa-reporting-dashboard.html"
_CONST_LINE_RE = re.compile(r"^[+-]\s*const (REAL_BIRTH_REG_DATA|REAL_CP_DATA) = .*;\s*$")


def main() -> int:
    result = subprocess.run(
        ["git", "diff", "--cached", "-U0", "--", DASHBOARD_PATH],
        capture_output=True, text=True,
    )
    diff = result.stdout
    if not diff:
        return 0  # not staged, or no changes to this file

    changed_lines = [
        line for line in diff.splitlines()
        if (line.startswith("+") or line.startswith("-"))
        and not line.startswith("+++") and not line.startswith("---")
    ]
    if not changed_lines:
        return 0

    if all(_CONST_LINE_RE.match(line) for line in changed_lines):
        print(
            f"\n✖ {DASHBOARD_PATH}: every changed line is one of the two embedded-data "
            "consts (REAL_BIRTH_REG_DATA/REAL_CP_DATA).\n"
            "  This looks like a local embed_dashboard_data.py / ./run_pipeline.sh rebuild, "
            "not a real edit.\n"
            "  Phase 3's rule (plans/publishing-and-history.md): CI rebuilds and deploys these "
            "two lines on every push - the committed copy stays frozen.\n"
            f"  Run `git restore --staged --worktree -- {DASHBOARD_PATH}` and re-commit without "
            "this file if that's what happened.\n",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
