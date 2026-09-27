"""Shared mothman CLI/TUI helpers - plans/tooling.md #1's real design
requirements, not incidental utilities: the non-TTY guard, confirm-by-
default writes, and the tmp-dir-first Promote pattern every QA flow uses
(run the real tools into a throwaway location first, only copy into the
real, permanent qa_results/ history on explicit confirmation - never a
second, wasteful re-run of the real tool chain just to change where the
result lands)."""
from __future__ import annotations
import os
import sys

import click
import questionary
# Own Console, matching what every other cli/ module already does - see
# plans/tooling.md #12, that per-module duplication is a real DRY seed
# in its own right, not something to restructure in passing here.
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from questionary import Style

from qa_tools.common import hand_filing, supply_db, trial
# Both orchestrators define an identical RUN_STEPS; importing one keeps
# this helper honest about the real step count rather than hardcoding 5.
from qa_tools.bdm.orchestrate_bdm import RUN_STEPS

# S3 QA source mode (plans/tooling.md #1 Phase 3) - the real raw-data
# bucket to browse. Env-provided, never hardcoded, since CDK
# auto-generates a globally-unique bucket name at deploy time (see
# aws/cdk/data_pipeline_stack.py's own comment on why neither S3 bucket
# there gets a fixed bucket_name=).
S3_BUCKET_ENV_VAR = "MOTHMAN_RAW_BUCKET_NAME"

# Three-tier colour coding (plans/tooling.md #1, Keith's own explicit
# ask): Tier 1 (human, day-to-day) = green, Tier 2 (machine/CI-only) =
# blue, Tier 3 (developer debugging) = yellow/amber. Tier 4 is its own
# separately-flagged exploratory bucket, not part of this scheme.
console = Console()

TIER_1 = "green"
TIER_2 = "blue"
TIER_3 = "yellow"
TIER_4 = "magenta"

BACK = "<- Back"
CANCEL = "Cancel"

_QMARK_STYLE = Style([
    ("qmark", "fg:#8FB6D6 bold"),
    ("question", "bold"),
    ("pointer", "fg:#8FB6D6 bold"),
    ("highlighted", "fg:#8FB6D6 bold"),
    ("selected", "fg:#8FB6D6"),
])


class NotInteractive(click.ClickException):
    """Raised when a TUI flow would need a real terminal but stdin/stdout
    isn't one - a script, some CI runners, an IDE console (real research
    finding, 2026-09-19: questionary/prompt_toolkit can crash outright in
    that situation rather than degrading gracefully - see plans/
    tooling.md #1's own TUI design considerations). Always names the
    flag-based equivalent so the wizard/flags duality actually holds
    together, not just a bare failure."""

    def __init__(self, flag_hint: str) -> None:
        super().__init__(
            f"This needs a real interactive terminal, and stdin/stdout here isn't one. "
            f"Use the flag-based form instead: {flag_hint}"
        )


def require_tty(flag_hint: str) -> None:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise NotInteractive(flag_hint)


def select(message: str, choices: list[str], flag_hint: str) -> str | None:
    """A questionary select with the non-TTY guard already applied and a
    real "<- Back" choice always appended (the wizard back-navigation gap
    plans/tooling.md #1 flagged as a real, previously-undesigned hole).
    Returns None if the operator picked Back or hit Ctrl-C - callers treat
    that uniformly as "go back a step", not as an error. Escape does NOT
    also trigger this (a real, previously-undocumented gap found via
    scripts/dev/tui_drive.py, 2026-09-19, plans/tooling.md #9 - the
    installed questionary version never binds Keys.Escape in any of its
    prompt types, only Ctrl-C/Ctrl-Q; this docstring used to claim
    otherwise)."""
    require_tty(flag_hint)
    answer = questionary.select(message, choices=[*choices, BACK], style=_QMARK_STYLE).ask()
    if answer is None or answer == BACK:
        return None
    return answer


def path_prompt(message: str, flag_hint: str) -> str | None:
    """A questionary.path() prompt (real tab-completion filesystem
    browsing, no hand-built file picker needed - plans/tooling.md #1's
    own Local-files QA source mode design) with the same non-TTY guard
    every other prompt here uses. Returns None on Ctrl-C or a blank
    answer - callers treat that the same as select()'s Back: stop the
    flow, don't proceed with an empty path. Escape does NOT also trigger
    this - same real gap as select()'s own docstring above, questionary
    never binds Escape in any of its prompt types."""
    require_tty(flag_hint)
    answer = questionary.path(message, style=_QMARK_STYLE).ask()
    return answer or None


def confirm(message: str, *, yes: bool, default: bool = False) -> bool:
    """Confirm-by-default on writes, with a --yes bypass (plans/
    tooling.md #1's own design requirement) - --yes skips the prompt
    entirely rather than answering it, so this never needs a real
    terminal when yes=True (the flag-invocable, scriptable path)."""
    if yes:
        return True
    require_tty("pass --yes")
    answer = questionary.confirm(message, default=default, style=_QMARK_STYLE).ask()
    return bool(answer)


def report_recorded(run_id: str, count: int) -> None:
    """The real success affordance after an interactive check that was
    kept (Keith's own ask, 2026-09-19, about the step this replaces:
    "after the user confirms promotion of results, they should get a
    success message rather than being bumped straight back to the
    menu").

    WHAT IT REPLACED, and why the panel survived the change rather than
    going with it. `promote()` copied one run's JSON files out of a
    throwaway directory into the committed qa_results/ tree, and
    `report_promoted()` said how many files had landed and where. There
    is no tree and there are no files (REQ-PIPE-089), so the count is of
    recorded results rather than of files - but the reason the panel
    exists is untouched: this is still the most consequential action in
    the whole tool, and it still must not look like the end of a no-op.

    IT NO LONGER SAYS "commit and push qa_results/ yourself to publish".
    That sentence was true and is now false twice over: there is nothing
    to commit, and a git push is not what publishes (REQ-PIPE-092).
    """
    body = Text()
    body.append(f"{count} check result{'' if count == 1 else 's'} recorded for {run_id}\n",
                 style="bold green")
    body.append("in this environment's QA history.\n\n", style="green")
    body.append("Nothing has been published yet - publishing is a separate step\n"
                 "(mothman pipeline run --publish).", style="dim")
    console.print(Panel(body, title="Recorded", border_style="green", expand=False))

    if sys.stdin.isatty() and sys.stdout.isatty():
        questionary.press_any_key_to_continue(
            "Press any key to return to the menu...", style=_QMARK_STYLE).ask()


def raw_bucket_name() -> str:
    """Reads S3_BUCKET_ENV_VAR dynamically at call time (this project's
    own established convention against a module-level constant captured
    once at import time - see cli/bdm.py's raw_dir() for the real bug
    class that guards against). Raised as a real, clear ClickException
    here rather than reading None and failing deeper inside a confusing
    boto3 error."""
    bucket = os.environ.get(S3_BUCKET_ENV_VAR)
    if not bucket:
        raise click.ClickException(
            f"S3 QA source mode needs the {S3_BUCKET_ENV_VAR} environment variable set to the "
            f"real raw-data bucket name (see aws/cdk/data_pipeline_stack.py's RawDataBucket)."
        )
    return bucket


def chain_progress(label: str):
    """Context manager for the real check chain's own progress indicator,
    yielding an `on_step` callback to hand to
    orchestrate_bdm/cp.run_single() (plans/tooling.md #13).

    The chain takes ~13.5s and used to print exactly one line and then
    nothing at all for the whole stretch - a static screen with no sign
    the tool was alive, working, or hung. Keith, watching it in the
    recorded demo: "20 seconds of like nothing and waiting and there's
    no progress indicator."

    This is a REAL progress measure, not a decorative one: the chain has
    genuinely known, discrete steps (RUN_STEPS on either orchestrator -
    one source of truth for both the labels and the count), so the bar
    reflects actual position. The honest caveat is that those steps are
    very unevenly sized - dbt-core ~5s and datacontract-cli ~6s dominate,
    Soda Core and Evidently are ~0.1s each (plans/performance.md) - so it
    advances in real but lumpy jumps. The spinner and elapsed-time
    columns are what carry continuity across the two long steps, which
    is exactly where a bare bar would look stalled.

    `transient=True` so the finished bar erases itself and the real
    report lands on a clean screen rather than under leftover chrome.
    Falls back to a plain one-line print when stdout isn't a TTY (a
    redirected log, CI), where an animated bar would just emit thousands
    of control sequences into a file."""
    from contextlib import contextmanager

    from rich.progress import (BarColumn, Progress, SpinnerColumn, TextColumn,
                               TimeElapsedColumn)

    @contextmanager
    def _run():
        if not sys.stdout.isatty():
            console.print(f"Running the real check chain for {label}...", style="dim")
            yield None
            return
        with Progress(
            SpinnerColumn(),
            TextColumn("[dim]{task.description}[/dim]"),
            BarColumn(bar_width=28),
            TextColumn("[dim]{task.completed}/{task.total}[/dim]"),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task(f"Checking {label}", total=len(RUN_STEPS))
            done = 0

            def on_step(step_label: str) -> None:
                nonlocal done
                # Called BEFORE each step starts, so `done` is the count
                # genuinely finished - never report work that hasn't
                # happened yet just to make the bar move sooner.
                progress.update(task, completed=done, description=f"Running {step_label}")
                done += 1

            yield on_step
            progress.update(task, completed=len(RUN_STEPS), description="Done")

    return _run()


# ---------------------------------------------------------------------------
# Keep it, or try it (REQ-PIPE-103)
#
# ONE QUESTION, ASKED BEFORE ANYTHING RUNS, deciding both halves of
# what "keep" means: the supply is filed as a real delivery, AND its
# results are recorded. Keith's own framing, 2026-09-27 - "do it in
# the right order (file delivery then run check) but gate it behind a
# 'do you want to commit this' that the operator can choose 'no' on".
#
# WHY NOT THE OLD ORDER. This flow used to run the checks into a
# temporary directory and ask "Promote?" afterwards, which is a
# reasonable shape for a decision about RESULTS and the wrong one for
# a decision about an ARRIVAL: a supply filed after its check has run
# needs a run id minted before recognition could assign one, so the
# results end up keyed by an id recognition never gives out. Asking
# first is what lets a kept supply be an ordinary arrival with nothing
# to rename afterwards.
# ---------------------------------------------------------------------------

def describe_keep_choice(paths) -> str:
    """What the operator is actually choosing between.

    THE PUBLICATION CONSEQUENCE IS STATED, not buried (REQ-PIPE-103's
    first non-functional constraint). This repository is public and
    the delivery log records real file names; generated names entered
    that with eyes open, and a supply somebody was emailed is the
    first route by which a name we did not choose gets there. So the
    names are shown, at the moment the choice is made, rather than
    discovered later in a git history.
    """
    names = ", ".join(sorted(os.path.basename(str(p)) for p in paths))
    return (f"Keep: file as a real delivery received now, and record the results.\n"
            f"      These file names become part of this repository's public "
            f"delivery log: {names}\n"
            f"Trial: run the same four tools against the same rows and record "
            f"nothing anywhere.")


def decide_keep(paths, *, keep: bool | None) -> bool:
    """Keep this supply, or run it as a trial?

    `keep` IS THE FLAG'S ANSWER and stops the prompt entirely rather
    than pre-filling it (criterion 3) - the same shape `confirm(yes=)`
    already uses, so a scripted caller never needs a terminal.

    A TRIAL IS THE NON-INTERACTIVE DEFAULT. With no flag and no
    terminal there is nobody to ask, and the two wrong answers are not
    equally wrong: a trial that should have been kept costs a re-run,
    and a delivery filed on somebody's behalf is a public record of an
    arrival they did not agree to.
    """
    if keep is not None:
        return keep
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        console.print(
            "Not a real terminal and no --keep/--trial given - running as a TRIAL, "
            "which records nothing. Pass --keep to file this supply as a delivery.",
            style="yellow")
        return False
    console.print(describe_keep_choice(paths))
    return confirm("Keep this check?", yes=False, default=False)


def decide_record(run_id: str, *, keep: bool | None) -> bool:
    """Record this Synthetic-mode check, or run it as a trial?

    A DIFFERENT QUESTION FROM decide_keep(), which is why it is its own
    function rather than a reworded call. decide_keep() asks whether to
    FILE a supply the operator is handing over - an arrival nothing has
    recorded yet. Here the arrival is already recognised on disk and
    already filed; the only thing still open is whether this run's
    VERDICTS join the dataset's quality history.

    ASKED BEFORE THE CHAIN RUNS (REQ-PIPE-089 criterion 8). It used to be
    asked afterwards, as "promote this run?", which worked only because
    the results sat in a throwaway directory until somebody accepted
    them. Recorded results are visible as the run completes, so asking
    after would be offering a choice already made.

    A TRIAL IS THE NON-INTERACTIVE DEFAULT, for the same asymmetry
    decide_keep() records: a trial that should have been recorded costs a
    re-run, and a recorded run that should not have been is a verdict in
    a dataset's permanent quality history that nobody chose.
    """
    if keep is not None:
        return keep
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        console.print(
            "Not a real terminal and no --commit/--trial given - running as a TRIAL, "
            "which records nothing. Pass --commit to record this check.",
            style="yellow")
        return False
    return confirm(f"Record this check of {run_id} in the dataset's QA history?",
                    yes=False, default=False)


def file_or_trial(paths, collection_id: str, run_id_prefix: str,
                   *, keep: bool | None) -> hand_filing.Filed:
    """Turn a decision into a run. Returns what to check and under what
    identity - a hand_filing.Filed either way, with an empty
    `delivery_name` and `received_at` of None for a trial.

    ONE RETURN SHAPE FOR BOTH, which is what keeps the two routes from
    drifting apart downstream: a caller stages `filed.paths` under
    `filed.run_id` at `filed.received_at` and never asks which of the
    two things happened, except to say so at the end.

    A KEPT SUPPLY'S RUN ID COMES BACK FROM RECOGNITION, exactly as it
    would for a delivery that arrived on its own (criterion 1). A
    trial's comes from the clock alone (criterion 4).

    A FILE RECOGNITION CANNOT PLACE IS NOT FILED (Keith's own call,
    2026-09-27, over renaming it to fit or filing it unplaceable). The
    refusal explains itself and offers the trial, which needs no
    recognition because the command already says which dataset is
    being checked.
    """
    if not decide_keep(paths, keep=keep):
        return _as_trial(paths)
    try:
        filed = hand_filing.file_supply(paths, collection_id, run_id_prefix)
    except hand_filing.CannotFile as exc:
        console.print(str(exc), style="yellow")
        interactive = sys.stdin.isatty() and sys.stdout.isatty()
        if not interactive or not confirm(
                "Run it as a TRIAL instead?", yes=False, default=True):
            raise click.ClickException(
                "not filed. Rename the file to match the pattern, or pass "
                "--trial to check it without filing.") from exc
        return _as_trial(paths)
    console.print(f"Filed as delivery {filed.delivery_name}, "
                   f"recognised as {filed.run_id}.", style="green")
    return filed


def _as_trial(paths) -> hand_filing.Filed:
    """A trial reads the operator's own files where they are. Nothing
    is copied, because nothing is being recorded as having arrived."""
    return hand_filing.Filed(delivery_name="", run_id=trial.trial_run_id(),
                             paths=tuple(str(p) for p in paths), received_at=None)


def reference_run_id() -> str:
    """The disposable run a drift comparison needs.

    ALWAYS A TRIAL, whichever way the supply itself went. The
    reference is a known-good file the operator already had; filing it
    would record an arrival that never happened, and this pipeline's
    whole delivery log is a claim about what actually arrived. So it
    is staged, compared against, and dropped.
    """
    return trial.trial_run_id(reference=True)


def discard_reference(run_id: str) -> None:
    """Give back what the reference borrowed.

    NEVER FAILS THE COMMAND, for the reason the orchestrators' own
    tidy-up gives: the results are already reported by the time this
    runs, and `mothman supply tidy` clears whatever is left.
    """
    if not trial.is_trial(run_id):
        return
    try:
        with supply_db.connect(label="mothman:discard-reference") as conn:
            trial.discard(conn, run_id)
    except Exception as exc:  # noqa: BLE001 - see the docstring
        console.print(f"could not discard the reference run's schemas "
                       f"({type(exc).__name__}: {exc}) - `mothman supply tidy` "
                       f"clears leftovers.", style="yellow")


def say_what_it_did(run_id: str, delivery_name: str) -> None:
    """Criterion 8 - and its second half is the one worth keeping: a
    run that filed a delivery must never be described as local-only."""
    if delivery_name:
        console.print(
            f"Kept. {run_id} is a real arrival, filed as delivery "
            f"{delivery_name}, and its results are recorded.", style="green")
    else:
        console.print(
            f"Trial. {run_id} ran the same four tools against the same rows; "
            f"nothing was filed and nothing was recorded.", style="dim")


def keep_from_flags(commit: bool, trial_flag: bool) -> bool | None:
    """The answer a non-interactive caller gave, or None for "ask"
    (criterion 3).

    `--commit` IS THE KEEP FLAG rather than a new one beside it. It
    already meant "write this run into the real, permanent history",
    and under REQ-PIPE-103 that is the same decision as filing the
    supply - one act with two halves, not two choices that could
    disagree. A run whose results are kept but whose arrival was never
    recorded is exactly the split this requirement closes.

    `--trial` IS ITS EXPLICIT OPPOSITE, so a script can state either
    answer rather than relying on a default it cannot see.
    """
    if commit and trial_flag:
        raise click.ClickException(
            "--commit and --trial say opposite things. --commit files this supply "
            "as a delivery and records the results; --trial runs the same checks "
            "and records nothing.")
    if commit:
        return True
    if trial_flag:
        return False
    return None
