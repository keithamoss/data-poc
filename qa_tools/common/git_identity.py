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

Lambda fallback (2026-09-18 night, plans/running-thoughts.md #5 Thread
B - the AWS event-driven MVP design): a real Lambda invocation has no
`.git` checkout and no `git config` at all, so the local-git-identity
path above would always fail there, for a reason that has nothing to
do with a missing/guessed identity - there's no human running it to
begin with. That's not the same failure `MissingGitIdentityError` exists
to catch (a person who forgot to configure git), so it gets a real,
distinct answer instead: a `aws-lambda:<function-name>` service
identity, checked for FIRST (before ever shelling out to `git config`,
which wouldn't exist in that runtime anyway). This is still real,
truthful attribution ("this ran automatically, via this specific Lambda
function"), not a placeholder standing in for a missing human - the
same distinction Keith's own "never fall back to unknown" rule is
protecting.

GitHub Actions is the same case and got the same answer (2026-09-28,
found by CI going red). An Actions runner has a real `.git` checkout and
no `git config user.email` at all, so the local path failed there for a
reason that has nothing to do with a person forgetting to configure git -
there is no person. `GITHUB_ACTIONS` is set by the runner itself and by
nothing else, so a run there attributes to
`github-actions:<owner/repo>@<workflow>`, which says exactly what it was:
this workflow, in this repository, ran it.

WHY NOT SET `git config user.email` IN THE WORKFLOW, which was the
obvious one-line fix. It works and it lies a little: whatever address it
carried would read in the activity feed like a person who ran the
pipeline. It also has to be remembered in every workflow that ever runs a
real tool, and the one that forgets fails far from here. A truthful
service identity needs no setup step and cannot be forgotten.
"""
from __future__ import annotations

import os
import subprocess


class MissingGitIdentityError(Exception):
    """Raised when `git config user.email` isn't set (or is empty) -
    orchestrate_bdm.py/orchestrate_cp.py must fail before running any
    real tool, not partway through, so nothing gets committed under a
    missing/guessed identity."""


def get_run_by() -> str:
    """Real attribution for this invocation, stamped into the recorded run
    as `run_by`. Three real sources, checked in order:

    1. A real AWS Lambda runtime (AWS_LAMBDA_FUNCTION_NAME is set by the
       Lambda service itself, never by a human) - returns
       "aws-lambda:<function-name>", a real service identity, not a
       placeholder.
    2. A real GitHub Actions runner (GITHUB_ACTIONS likewise) - returns
       "github-actions:<owner/repo>@<workflow>". Same reasoning as the
       Lambda case: nobody ran it, so there is no human identity to be
       missing, and naming the workflow is the truthful answer.
    3. Otherwise, the local git identity's email (`git config
       user.email`) - raises MissingGitIdentityError if that isn't set,
       since whoever runs this pipeline locally already needs it
       configured to commit their own output anyway, so this never
       blocks a real workflow, only one that's missing basic git setup.

    THE SERVICE CHECKS COME FIRST, and the order is load-bearing rather
    than tidy: an Actions runner DOES have a `.git` checkout, so a
    developer's global git config leaking into the image would otherwise
    attribute a CI run to whoever happened to be configured.
    """
    lambda_function_name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    if lambda_function_name:
        return f"aws-lambda:{lambda_function_name}"

    if os.environ.get("GITHUB_ACTIONS") == "true":
        # Both are set by the runner. Defaulted rather than demanded,
        # because a partial Actions environment must still attribute
        # truthfully - "github-actions" alone is honest, where raising
        # here would take a real CI run down over a missing label.
        repo = os.environ.get("GITHUB_REPOSITORY") or "unknown-repository"
        workflow = os.environ.get("GITHUB_WORKFLOW") or "unknown-workflow"
        return f"github-actions:{repo}@{workflow}"

    result = subprocess.run(["git", "config", "user.email"], capture_output=True, text=True)
    email = result.stdout.strip()
    if result.returncode != 0 or not email:
        raise MissingGitIdentityError(
            "git config user.email is not set - required to attribute this QA run "
            "(plans/publishing-and-history.md Phase 3's changelog feature). "
            "Set it with: git config user.email \"you@example.com\""
        )
    return email
