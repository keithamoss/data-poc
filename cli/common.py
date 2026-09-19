"""Shared mothman CLI/TUI helpers - plans/tooling.md #1's real design
requirements, not incidental utilities: the non-TTY guard, confirm-by-
default writes, and the tmp-dir-first Promote pattern every QA flow uses
(run the real tools into a throwaway location first, only copy into the
real, permanent qa_results/ history on explicit confirmation - never a
second, wasteful re-run of the real tool chain just to change where the
result lands)."""
from __future__ import annotations
import os
import shutil
import sys
import tempfile
from pathlib import Path

import click
import questionary
# Own Console, matching what every other cli/ module already does - see
# plans/tooling.md #12, that per-module duplication is a real DRY seed
# in its own right, not something to restructure in passing here.
from rich.console import Console
from questionary import Style

from qa_tools.common.qa_results_writer import QA_RESULTS_DIR
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


def promote(tmp_root: str, agency: str, dataset: str, run_id: str) -> Path:
    """Copies one run's real tool output from the throwaway tmp_root a QA
    flow already wrote into (via qa_tools.common.lambda_results_dir's
    patch_write_qa_result_for_lambda) into the real, permanent, committed
    qa_results/ tree - the actual meaning of "Promote". Never re-runs the
    real tool chain a second time just to change where its output lands;
    the tools already ran once, for real, into tmp_root."""
    src = Path(tmp_root) / agency / dataset / run_id
    dst = QA_RESULTS_DIR / agency / dataset / run_id
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True)
    return dst


def new_tmp_results_dir() -> str:
    return tempfile.mkdtemp(prefix="mothman-qa-")


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
