"""Shared mothman CLI/TUI helpers - plans/tooling.md #1's real design
requirements, not incidental utilities: the non-TTY guard, confirm-by-
default writes, and the tmp-dir-first Promote pattern every QA flow uses
(run the real tools into a throwaway location first, only copy into the
real, permanent qa_results/ history on explicit confirmation - never a
second, wasteful re-run of the real tool chain just to change where the
result lands)."""
from __future__ import annotations
import shutil
import sys
import tempfile
from pathlib import Path

import click
import questionary
from questionary import Style

from qa_tools.common.qa_results_writer import QA_RESULTS_DIR

# Three-tier colour coding (plans/tooling.md #1, Keith's own explicit
# ask): Tier 1 (human, day-to-day) = green, Tier 2 (machine/CI-only) =
# blue, Tier 3 (developer debugging) = yellow/amber. Tier 4 is its own
# separately-flagged exploratory bucket, not part of this scheme.
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
    Returns None if the operator picked Back or hit Ctrl-C/Esc - callers
    treat that uniformly as "go back a step", not as an error."""
    require_tty(flag_hint)
    answer = questionary.select(message, choices=[*choices, BACK], style=_QMARK_STYLE).ask()
    if answer is None or answer == BACK:
        return None
    return answer


def path_prompt(message: str, flag_hint: str) -> str | None:
    """A questionary.path() prompt (real tab-completion filesystem
    browsing, no hand-built file picker needed - plans/tooling.md #1's
    own Local-files QA source mode design) with the same non-TTY guard
    every other prompt here uses. Returns None on Ctrl-C/Esc or a blank
    answer - callers treat that the same as select()'s Back: stop the
    flow, don't proceed with an empty path."""
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
