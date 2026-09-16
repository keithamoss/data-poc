"""
Captures "who ran this" for the changelog/activity-feed feature
(plans/publishing-and-history.md Phase 3's remaining item, 2026-09-16) -
the local git identity of whoever is running orchestrate_bdm.py/
orchestrate_cp.py, read once per invocation and stamped into that run's
committed qa_results/ as `run_by` (qa_results_writer.py).

Email, not name: `git config user.email` is required to make any git
commit at all (git refuses `git commit` without it configured), so it's
reliably available under exactly the same condition as `user.name`, and
disambiguates two people who happen to share a display name.

Fails loudly rather than falling back to "unknown" - Keith's explicit
call, 2026-09-16, matching the same "mandatory, not silently skipped"
posture as check_lifecycle.py's MissingCheckIdError: a QA event with no
real attribution is a data-quality problem in its own right, not
something to paper over with a placeholder.
"""
from __future__ import annotations

import subprocess


class MissingGitIdentityError(Exception):
    """Raised when `git config user.email` isn't set (or is empty) -
    orchestrate_bdm.py/orchestrate_cp.py must fail before running any
    real tool, not partway through, so nothing gets committed under a
    missing/guessed identity."""


def get_run_by() -> str:
    """The current git identity's email, for stamping into this
    invocation's qa_results/ as `run_by`. Raises MissingGitIdentityError
    if `git config user.email` isn't set - whoever runs this pipeline
    already needs it configured to commit their own output anyway, so
    this never blocks a real workflow, only one that's missing basic git
    setup."""
    result = subprocess.run(["git", "config", "user.email"], capture_output=True, text=True)
    email = result.stdout.strip()
    if result.returncode != 0 or not email:
        raise MissingGitIdentityError(
            "git config user.email is not set - required to attribute this QA run "
            "(plans/publishing-and-history.md Phase 3's changelog feature). "
            "Set it with: git config user.email \"you@example.com\""
        )
    return email
