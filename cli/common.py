"""Shared mothman CLI/TUI helpers - plans/tooling.md #1's real design
requirements, not incidental utilities: the non-TTY guard, confirm-by-
default writes, and the record-or-trial question every QA flow asks
before it runs anything.

IT USED TO DESCRIBE A TMP-DIR-FIRST "PROMOTE" PATTERN - run the real
tools into a throwaway directory, and copy the JSON into the committed
qa_results/ tree only on confirmation. Both halves are gone: there is no
tree (REQ-PIPE-089) and so nothing to copy, and the question moved to
BEFORE the chain because a recorded result is visible as the run
completes, so asking afterwards would offer a choice already made. The
word "promote" went with it (REQ-GHUB-082 criterion 15) and now means
the supply operation in this tool and nothing else."""
from __future__ import annotations

from pathlib import Path
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


def environment_statement() -> str | None:
    """Which environment this terminal is acting against, in the dashboard's
    own words (REQ-TEST-114 criteria 5 and 7): the label from
    contract/environments.yaml for the environment actually resolved, plus
    'not production' wherever it does not publish - words, never colour
    alone, so they survive NO_COLOR, a pipe and a dumb terminal (criterion
    6). None when no environment resolves. Reads configuration and one
    variable, never the database (NFR: no per-command cost)."""
    from qa_tools.common import environments

    try:
        env = environments.current_or_none()
    except environments.EnvironmentError_:
        return None
    if env is None:
        return None
    return f"Environment: {env.label}" + ("" if env.publishes else " (not production)")


def _with_environment_toolbar(question):
    """A persistent bottom toolbar naming the environment, on every prompt
    for as long as it is shown (REQ-TEST-114 criterion 1).

    APPENDED TO THE LAYOUT rather than passed as `bottom_toolbar`: questionary's
    select and checkbox hand their keyword arguments to two PromptSessions,
    one of which already sets bottom_toolbar, so the keyword raises. Every
    questionary prompt's root is an HSplit (checked 2026-10-05 for select,
    text, confirm, path and checkbox), so one extra row works for all five.
    It disappears once the prompt is answered, so the scrollback keeps the
    answer and not a stack of toolbars."""
    statement = environment_statement()
    if statement is None:
        return question
    from prompt_toolkit.filters import IsDone
    from prompt_toolkit.layout import ConditionalContainer, HSplit, Window
    from prompt_toolkit.layout.controls import FormattedTextControl

    application = getattr(question, "application", None)
    root = application.layout.container if application is not None else None
    if isinstance(root, HSplit):
        root.children.append(ConditionalContainer(
            Window(FormattedTextControl([("class:bottom-toolbar.text", f" {statement} ")]),
                   height=1, style="class:bottom-toolbar"),
            filter=~IsDone()))
    return question


def _ask(question):
    return _with_environment_toolbar(question).ask()


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
    answer = _ask(questionary.select(message, choices=[*choices, BACK], style=_QMARK_STYLE))
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
    answer = _ask(questionary.path(message, style=_QMARK_STYLE))
    return answer or None


def text_prompt(message: str, flag_hint: str) -> str | None:
    """A free-text answer, with the same non-TTY guard and the same
    Back-on-Ctrl-C contract every other prompt here has.

    BLANK READS AS BACK, not as an empty answer. The one thing this is
    for is a REASON on a filing decision, which REQ-GHUB-082 criterion
    10 refuses without - so somebody who hits enter on an empty line has
    not supplied a reason, they have changed their mind, and treating
    that as "go back" is both truer and kinder than refusing them.
    """
    require_tty(flag_hint)
    answer = _ask(questionary.text(message, style=_QMARK_STYLE))
    return (answer or "").strip() or None


def _named(message: str) -> str:
    """A confirmation names the environment in the same prompt (REQ-TEST-114
    criterion 4): `[Sandbox (not production)] Record promote ...?`."""
    statement = environment_statement()
    if statement is None:
        return message
    return f"[{statement.removeprefix('Environment: ')}] {message}"


def confirm(message: str, *, yes: bool, default: bool = False,
            flag_hint: str = "pass --yes") -> bool:
    """Confirm-by-default on writes, with a --yes bypass (plans/
    tooling.md #1's own design requirement) - --yes skips the prompt
    entirely rather than answering it, so this never needs a real
    terminal when yes=True (the flag-invocable, scriptable path)."""
    if yes:
        return True
    require_tty(flag_hint)
    answer = _ask(questionary.confirm(_named(message), default=default, style=_QMARK_STYLE))
    return bool(answer)


def _ask_text(message: str) -> str | None:
    """One line of free text from the person at the terminal."""
    return _ask(questionary.text(message, style=_QMARK_STYLE))


def confirm_change(message: str, *, yes: bool, default: bool = False,
                   flag_hint: str = "pass --yes") -> bool:
    """The ONE confirmation before a person changes the database by hand from
    the terminal (REQ-PIPE-093 criteria 4 to 7).

    WHERE THE STATED ENVIRONMENT DECLARES `confirm_changes` - production
    today, decided from that property and never from the word - the person
    TYPES the environment's id in place of the yes or no. Nothing skips it:
    not --yes, not any other flag or variable (criterion 6), and with no
    terminal there is nobody to type it, so the change is refused rather
    than made. A mismatch records nothing and says so (criterion 7).
    Everywhere else this is the ordinary confirm(), --yes and all.

    ASKED ONCE PER FLOW: a caller making several changes in one flow asks
    once, before the first.

    WHAT NEVER ASKS, stated here because criterion 9 asks for each
    exemption to be stated beside the code: the pipeline's own filing and
    promotion (no person, no terminal - they never call this); scripted
    playback (REQ-GEN-135, scripted_decisions._apply calls the decision path
    directly, and a bootstrap in production must stay unattended); a decision
    arriving through the GitHub route (its own confirmation is the ticket
    reply); and a processing pass with no terminal attached (REQ-PIPE-151).
    """
    from qa_tools.common import environments

    env = environments.current()
    if not env.confirm_changes:
        return confirm(message, yes=yes, default=default, flag_hint=flag_hint)
    require_tty(f"type {env.id!r} at a terminal - in the {env.id!r} environment a change "
                f"made by hand cannot be confirmed by a flag")
    console.print(f"[bold]{message}[/bold]")
    typed = (_ask_text(f"This changes the {env.label} database. Type {env.id} to confirm:")
             or "").strip()
    if typed != env.id:
        console.print(f"Did not match {env.id!r} - nothing recorded.", style="yellow")
        return False
    return True


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
                 "(mothman dashboard publish).", style="dim")
    console.print(Panel(body, title="Recorded", border_style="green", expand=False))

    if sys.stdin.isatty() and sys.stdout.isatty():
        # Through _ask, so the environment's toolbar shows here too (#119 D6).
        _ask(questionary.press_any_key_to_continue(
            "Press any key to return to the menu...", style=_QMARK_STYLE))


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
            global _ACTIVE_PROGRESS
            _ACTIVE_PROGRESS = progress
            task = progress.add_task(f"Checking {label}", total=len(RUN_STEPS))
            done = 0

            def on_step(step_label: str) -> None:
                nonlocal done
                # Called BEFORE each step starts, so `done` is the count
                # genuinely finished - never report work that hasn't
                # happened yet just to make the bar move sooner.
                progress.update(task, completed=done, description=f"Running {step_label}")
                done += 1

            try:
                yield on_step
                progress.update(task, completed=len(RUN_STEPS), description="Done")
            finally:
                _ACTIVE_PROGRESS = None

    return _run()


#: The live progress display, while one is drawing - see paused_progress().
_ACTIVE_PROGRESS = None


def paused_progress():
    """Stop the live progress display while a person is asked something.

    A Rich Progress keeps redrawing, so a prompt asked inside one was
    drawn UNDER it: "Keep this check?" appeared only after it had been
    answered, the file-names-become-public warning was never visible,
    and a typed original-arrival time was not echoed at all (critic,
    sprint 5, driving a real pty). The display resumes afterwards.
    """
    from contextlib import contextmanager

    @contextmanager
    def _paused():
        live = _ACTIVE_PROGRESS
        if live is None:
            yield
            return
        live.stop()
        try:
            yield
        finally:
            live.start()
    return _paused()


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
            "which records nothing. Pass --commit to file this supply as a delivery.",
            style="yellow")
        return False
    console.print(describe_keep_choice(paths))
    return confirm("Keep this check?", yes=False, default=False)


def offer_to_publish() -> None:
    """After an interactive check that was kept, ask whether to publish
    (REQ-PIPE-092 criterion 14).

    A PROMPT, NEVER AUTOMATIC, and the criterion says so in as many
    words. Publishing is the one act in this tool with an audience
    outside it - everything else changes what this environment knows,
    and this changes what other people see. Somebody who has just run
    QA to look at a number should not discover they have republished a
    public site.

    IT REACHES THE SITE BY THE SAME PATH THE COMMAND USES (criterion
    15): cli.dashboard.publish(), which builds, gates and pushes. Not a
    lighter version of it - a prompt that skipped the render gate would
    be the second publish path criterion 10 forbids, wearing a
    friendlier face.

    SILENT WITH NO TERMINAL. There is nobody to ask, and the safe answer
    to "shall I change what the public sees" asked of nobody is no.
    """
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return
    if not confirm("Publish the dashboard now?", yes=False, default=False):
        console.print("Not published - the published dashboard is unchanged. "
                       "`mothman dashboard publish` when you want to.", style="dim")
        return
    from cli import dashboard as dashboard_cli

    dashboard_cli.publish()


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
    # AN ARRIVAL WHOSE QA IS ALREADY RECORDED IS NEVER RECORDED AGAIN UNDER
    # ITS OWN ID (REQ-PIPE-086 criteria 6 to 8): a further recorded check is
    # REQ-PIPE-140's re-check, owed by the decision or reload that calls for
    # it, under a run id of its own. Here it runs as a trial, saying why, and
    # --commit is refused naming --trial.
    if run_id in recorded_runs([run_id]):
        if keep:
            raise click.ClickException(
                f"{run_id} already has recorded QA, and an arrival is never recorded "
                f"twice under its own id. A further recorded check is a re-check "
                f"(REQ-PIPE-140), owed by the decision that calls for it. Pass --trial "
                f"to check it again without recording.")
        console.print(f"{run_id} already has recorded QA - running it as a TRIAL, "
                      f"which records nothing.", style="yellow")
        return False
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


def record_delivery_of(arrival) -> None:
    """Record the delivery an arrival came in - write-once, as the batch's
    delivery_log.record_all() does for every delivery before it files one
    (REQ-PIPE-086 criterion 12: every per-arrival step on every route)."""
    from qa_tools.common import arrivals, delivery, delivery_log

    for d in delivery.list_deliveries():
        if d.name == arrival.delivery_name:
            delivery_log.record(d, arrivals.recognise(d))
            return


def recorded_runs(run_ids) -> set[str]:
    """Which of these arrivals' runs already have recorded QA - completed
    runs under their own id. One read. Empty where nothing is set up, which
    a picker over generated data that was never checked legitimately is."""
    from qa_tools.common import qa_store, supply_db

    ids = list(run_ids)
    if not ids:
        return set()
    with supply_db.connect(read_only=True, label="mothman:picker") as conn:
        if not conn.execute(f"SELECT to_regclass('{qa_store.SCHEMA}.run')").fetchone()[0]:
            return set()
        return {r[0] for r in conn.execute(
            f'SELECT run_key FROM "{qa_store.SCHEMA}".run WHERE completed_at IS NOT NULL '
            "AND run_key = ANY(?)", [ids]).fetchall()}


def file_or_trial(paths, collection_id: str, run_id_prefix: str,
                   *, keep: bool | None, route: str, originally: str | None = None,
                   storage_times: dict | None = None) -> hand_filing.Filed:
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
    with paused_progress():
        return _file_or_trial(paths, collection_id, run_id_prefix, keep=keep,
                              route=route, originally=originally,
                              storage_times=storage_times)


def _file_or_trial(paths, collection_id, run_id_prefix, *, keep, route, originally,
                   storage_times) -> hand_filing.Filed:
    if not decide_keep(paths, keep=keep):
        return _as_trial(paths)
    # ANOTHER COLLECTION'S FILE IS REFUSED FIRST (REQ-PIPE-086 criterion 5) -
    # before the typed id or any question about it, and with no trial on
    # offer: it is the wrong command, not an unplaceable file.
    try:
        hand_filing.check_collection(paths, collection_id)
    except hand_filing.WrongCollection as exc:
        raise click.ClickException(str(exc)) from None
    # A HAND-FILING IN AN ENVIRONMENT THAT CONFIRMS CHANGES is typed for
    # (REQ-PIPE-093 criterion 4): --commit decides to keep it, and is not
    # allowed to be the confirmation too (criterion 6). yes=True because
    # everywhere else keeping was already confirmed above.
    if not confirm_change("File this supply as a real delivery?", yes=True):
        raise click.ClickException("not filed - the environment's id was not typed.")
    # WHO, AND WHEN IT WAS ORIGINALLY RECEIVED - both settled before
    # anything is written (REQ-PIPE-147 criterion 4, REQ-PIPE-103 criteria
    # 9-17). A refusal here files nothing and offers no trial: the supply
    # is placeable, the operator only has to answer.
    from qa_tools.common import asset_time, git_identity

    try:
        who = git_identity.get_run_by()
    except git_identity.MissingGitIdentityError as exc:
        raise click.ClickException(
            f"nothing says who is filing this supply ({exc}). Set it with `git config "
            f"user.email you@example.org`. Nothing was filed.") from None
    names = [Path(p).name for p in paths]
    answer = originally if originally is not None else _ask_original(names, storage_times)
    # THE RECEIPT IS TAKEN ONCE THE PERSON HAS ANSWERED, not before: a
    # long pause at the prompt otherwise sits between our receipt and the
    # filing, and an automated arrival landing meanwhile would carry a
    # later receipt but be recorded first.
    received_at = asset_time.now()
    try:
        stated = hand_filing.resolve_original(answer, files=names, received_at=received_at,
                                              storage_times=storage_times)
    except hand_filing.CannotFile as exc:
        raise click.ClickException(str(exc)) from None
    try:
        filed = hand_filing.file_supply(paths, collection_id, run_id_prefix,
                                        received_at=received_at, stated_original=stated,
                                        route=route, filed_by=who)
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
    # SHOWN BESIDE THE RECEIPT, NEVER AS IT (REQ-PIPE-103 criterion 19).
    console.print(describe_original(stated, received_at), style="dim")
    return filed


def describe_original(stated: dict[str, str], received_at) -> str:
    """The stated original arrival, labelled as the filer's statement and
    set beside our receipt rather than presented as it."""
    from qa_tools.common import delivery as delivery_mod
    from qa_tools.common import display_time

    shown = sorted({("not known" if v == delivery_mod.NOT_KNOWN
                     else display_time.format_instant(v)) for v in stated.values()})
    return (f"Received by us {display_time.format_instant(received_at)}; originally "
            f"received {', '.join(shown)} (stated by you - recorded, never used to "
            f"file or judge the supply).")


def _ask_original(names, storage_times: dict | None) -> str:
    """Ask when this supply was originally received (REQ-PIPE-103 criterion
    9), or refuse where nobody can be asked (criterion 14).

    FROM S3, each object's own LastModified is offered as one set,
    confirmed in one step (criterion 17) - the time is already in hand
    from the download, and making the person look it up invites a typo.
    """
    from qa_tools.common import display_time

    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise click.ClickException(
            "keeping a supply needs to know when it was originally received, and there is "
            "no terminal to ask - pass --originally-received <time>, `not-known`"
            + (", or `storage` for each S3 object's own time" if storage_times else "")
            + ". Nothing was filed.")
    if storage_times:
        console.print("S3 says each object was last written:", style="bold")
        for name in names:
            console.print(f"  {name}  {display_time.format_instant(storage_times[name])}")
        if confirm("Record these as when each was originally received?", yes=False,
                   default=True):
            return hand_filing.STORAGE
    return click.prompt(_named("When was this supply originally received? (e.g. 2026-09-20 "
                               "14:30 on the asset's own clock, or `not known`)"))


def _as_trial(paths) -> hand_filing.Filed:
    """A trial reads the operator's own files where they are. Nothing
    is copied, because nothing is being recorded as having arrived.

    It says what recognition WOULD make of each file if it were kept
    (REQ-TEST-150 criterion 10), and never stops on the answer."""
    from cli import lifecycle_report

    console.print("If these were kept, recognition would place them like this:", style="dim")
    lifecycle_report.trial_recognition(paths)
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


def finish_kept(results: list[dict], filed, *, collection_id: str, run_id_prefix: str,
                table, all_checks: bool = False) -> None:
    """The report after a hand-supplied check (REQ-TEST-150).

    ONE KEPT DELIVERY, SEVERAL ARRIVALS: every failing and warning check in
    full and passing checks as a count per dataset, unless --all-checks
    (criterion 11) - then what was said about it, and LAST, what the
    lifecycle decided about each arrival, read from what it recorded
    (criteria 1 to 9)."""
    from cli import lifecycle_report

    found = (hand_filing.arrivals_of(filed, collection_id, run_id_prefix)
             if filed.delivery_name else [])
    if len(found) > 1 and not all_checks:
        _compact_results(results, table, filed.run_id)
    else:
        console.print(table(results, filed.run_id))
    say_what_it_did(filed.run_id, filed.delivery_name, [a.run_id for a in found])
    if found:
        lifecycle_report.report(found, since=filed.received_at)


def kept_arrival(collection_id: str, run_id_prefix: str, run_id: str):
    """The recognised arrival a synthetic keep names - refused plainly where
    recognition finds none, rather than a bare StopIteration (#120 D13)."""
    from qa_tools.common import arrivals

    for arrival in arrivals.arrivals_for(collection_id, run_id_prefix):
        if arrival.run_id == run_id:
            return arrival
    raise click.ClickException(
        f"{run_id} isn't among the arrivals recognised on disk, so there is nothing to keep "
        f"- run generate-synthetic-data first?")


def report_kept_arrival(collection_id: str, run_id_prefix: str, run_id: str) -> None:
    """REQ-TEST-150 criteria 1 to 9 for a kept SYNTHETIC arrival, which is as
    much a kept route as a hand-filed one (REQ-PIPE-086 criterion 9) and
    printed none of it until #120 D4."""
    from cli import lifecycle_report

    arrival = kept_arrival(collection_id, run_id_prefix, run_id)
    lifecycle_report.report([arrival], since=arrival.received_at)


def _compact_results(results, table, run_id) -> None:
    """Criterion 11: what needs reading in full, and a count of the rest."""
    loud = [r for r in results if r.get("status") not in ("pass",)]
    if loud:
        console.print(table(loud, run_id))
    passing: dict[str, int] = {}
    for r in results:
        if r.get("status") == "pass":
            passing[r.get("dataset_id") or "?"] = passing.get(r.get("dataset_id") or "?", 0) + 1
    for dataset_id, n in sorted(passing.items()):
        console.print(f"  {dataset_id}: {n} check{'' if n == 1 else 's'} passed "
                      f"(--all-checks lists them)", highlight=False)


def say_what_it_did(run_id: str, delivery_name: str, arrivals=None) -> None:
    """Criterion 8 - and its second half is the one worth keeping: a
    run that filed a delivery must never be described as local-only."""
    if delivery_name and arrivals and len(arrivals) > 1:
        # EVERY ARRIVAL THE DELIVERY BECAME, not the first (#120 D8).
        console.print(
            f"Kept. Delivery {delivery_name} was filed as {len(arrivals)} arrivals "
            f"({', '.join(arrivals)}), and their results are recorded.", style="green")
    elif delivery_name:
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


def refuse_reference_for_kept(keep: bool | None, reference, flag: str) -> None:
    """A reference given for a KEPT supply is refused, not ignored
    (REQ-PIPE-086 criterion 14): it would let a person believe they chose
    the yardstick for a gating check."""
    if keep and reference is not None:
        raise click.ClickException(
            f"a kept supply is measured against the last promoted supply (REQ-QAC-108), "
            f"so it takes no reference - drop {flag}, or pass --trial to compare "
            f"against one.")


def require_reference_for_trial(reference, flag: str) -> None:
    """A trial is compared against the reference a person names (criterion 14)."""
    if reference is None:
        raise click.ClickException(
            f"a trial is compared against a reference you name - pass {flag}. A kept "
            f"supply needs none: it is measured against the last promoted supply.")


def reference_for_fallback_trial(reference, flag: str, what: str):
    """The reference for a KEPT supply that filing refused and the person
    turned into a trial (#120 D5). Nobody was asked for one - a kept supply
    needs none - so at a terminal it is asked for now, rather than stopping
    with a flag named to a person in a menu; without one the flag is the
    remedy, as it is for any trial."""
    if reference is not None:
        return reference
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        require_reference_for_trial(reference, flag)
    with paused_progress():
        answer = path_prompt(f"A trial is compared against a reference - which {what} is "
                             f"the known-good one?", flag)
    if not answer:
        raise click.ClickException(
            "no reference was given, so the trial has nothing to compare against. "
            "Nothing was run and nothing was filed.")
    return answer


def reference_suffix(result: dict) -> str:
    """What a drift or volume verdict was compared across, for the
    terminal report (REQ-QAC-108 criterion 14): where the red is the gap
    rule's, the measurement's own verdict is said apart from it, and the
    check is not called drift unless the measurement crossed its band."""
    reason = result.get("reference_reason")
    if not reason:
        return ""
    measured = result.get("measured_status")
    if measured and result.get("status") == "fail" and measured != "fail":
        return f" [dim](measured {measured} - red because {reason})[/dim]"
    if result.get("reference_not_evaluated"):
        return f" [dim]({reason})[/dim]"
    return ""
