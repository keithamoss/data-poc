"""mothman pipeline - the full real-tool batch run, Tier 2 (plans/
tooling.md #1 Phase 4's "Full-pipeline run... Tier 2, not human-facing -
that's more there for like integration tests and for yourself and not
there for the humans" - Keith's own framing).

This is the real gap Phase 4's own plan text got wrong: it claimed
orchestrate_bdm.py/orchestrate_cp.py were "already named in Phases 1-3,"
but only their run_single() function is reused by `mothman bdm/cp qa` -
their own __main__ blocks (run_pipeline()/run_pipeline_cp(), the full
manifest BATCH mode that regenerates synthetic data, runs all 4 real
tools against EVERY run, and writes both reports/results_*.json and
fresh qa_results/ history for the whole manifest) had no mothman command
at all until this one - this is what retired run_pipeline.sh's steps 1-2
actually did, and what CP's own equivalent never had a script for
either.

Unlike `mothman bdm/cp qa` (single run, careful scratch-dir-then-Promote
staging so a hand-supplied check never touches real history uninvited), this
command's whole point is the real batch regeneration - every run in the
manifest, written straight to committed qa_results/ history, no staging.
That's real pipeline behaviour, not a debug side effect - run this when
you mean to refresh the actual record (Keith's own local dev loop, CI
integration-test parity), not for one-off poking (use `mothman debug
run-*` for that)."""
from __future__ import annotations

import rich_click as click
from rich.console import Console

console = Console()


def _run_bdm(sequential: bool) -> None:
    from . import bdm
    from qa_tools.bdm.orchestrate_bdm import run_pipeline

    console.print("Generating synthetic data (Birth Registrations)...", style="dim")
    bdm.generate_synthetic_data()
    console.print("Running the real tools against every BDM run...", style="dim")
    run_pipeline(sequential=sequential)


def _run_cp(sequential: bool) -> None:
    from . import cp
    from qa_tools.cp.orchestrate_cp import run_pipeline_cp

    console.print("Generating synthetic data (Child Protection)...", style="dim")
    cp.generate_synthetic_data()
    console.print("Running the real tools against every CP run...", style="dim")
    run_pipeline_cp(sequential=sequential)


@click.group("pipeline")
def pipeline_group() -> None:
    """Full real-tool batch pipeline run - Tier 2 (CI/automation, integration-test parity)."""


@pipeline_group.command("run")
@click.option("--collection", type=click.Choice(["bdm", "cp", "all"]), default="all",
              help="Which collection's full manifest to regenerate and run - bdm = civil-registration, cp = child-protection. Default: both.")
@click.option("--sequential", is_flag=True,
              help="Run each supply's four QA tools one after another rather than dbt beside the other three - slower, and easier to read when debugging. Arrivals always run one at a time, because each filing depends on what the one before it promoted.")
@click.option("--snapshot", is_flag=True,
              help="Also archive a dashboard snapshot afterward (same as SNAPSHOT_DASHBOARD=1).")
@click.option("--publish", "do_publish", is_flag=True,
              help="Also publish the built dashboard. OPT-IN: a run without this builds for "
                   "local viewing and publishes nothing.")
def run_command(collection: str, sequential: bool, snapshot: bool, do_publish: bool) -> None:
    """Replaces run_pipeline.sh: regenerate synthetic data, run the real tools against every
    run in the manifest (recording fresh QA history), then rebuild and embed the dashboard.
    Records real QA history like any other real pipeline run - not a dry run.

    PUBLISHING IS OPT-IN (REQ-PIPE-092 criterion 16), and that was decided the other way
    first. Opt-out reads as friendlier and is wrong here: a debugging run, a batch and a
    scheduled run would each publish a dashboard nobody asked for, and the one that matters
    is the debugging run - somebody reproducing a problem would put their reproduction on
    the public site. `--publish` goes through the same single path
    `mothman dashboard publish` uses (criterion 10).
    """
    import os

    from qa_tools.common import bootstrap as bootstrap_mod
    from qa_tools.common import qa_store, supply_db

    from . import dashboard as dashboard_cli

    # REFUSED OVER RECORDED HISTORY (REQ-PIPE-144 criterion 39), before
    # anything is generated or run, for the reason bootstrap --force is:
    # a re-run adds to the history rather than replacing it.
    #
    # NOTHING PRUNES THE DELIVERY LOG ANY MORE (criteria 19 and 24,
    # amending REQ-PIPE-069 criterion 6). A delivery whose files have
    # moved on - in production, to another bucket, which is every
    # delivery - is history that still exists.
    with supply_db.connect(label="mothman:pipeline-run") as conn:
        qa_store.ensure_schema(conn)
        if bootstrap_mod.holds_history(conn):
            raise click.ClickException(bootstrap_mod.HISTORY_REFUSAL[0].upper()
                                       + bootstrap_mod.HISTORY_REFUSAL[1:])

    # THE PASS LOCK (REQ-PIPE-151 criterion 16), held while anything runs.
    from qa_tools.common import processing_pass

    try:
        with processing_pass.pass_lock("run"):
            if collection in ("bdm", "all"):
                _run_bdm(sequential)
            if collection in ("cp", "all"):
                _run_cp(sequential)
    except processing_pass.PassLockHeld as exc:
        raise click.ClickException(str(exc)) from None

    console.print("Reshaping into dashboard JSON...", style="dim")
    dashboard_cli._build_data()
    console.print("Embedding real data into the dashboard...", style="dim")
    dashboard_cli._embed()

    if snapshot:
        os.environ["SNAPSHOT_DASHBOARD"] = "1"
    from dashboard.snapshot_dashboard import sync_local_snapshots, take_snapshot

    synced = sync_local_snapshots()
    if synced:
        console.print(f"Synced {len(synced)} local snapshot copy/copies for offline viewing.", style="dim")
    if snapshot:
        out_path = take_snapshot()
        console.print(f"Dashboard snapshot written -> {out_path}", style="green")

    console.print("Pipeline run complete -> dashboard/qa-reporting-dashboard.html", style="green")

    if do_publish:
        # THE SAME FUNCTION the command and the wizard's prompt call, not a
        # copy of its steps - criterion 10 is that there is exactly one way
        # to get content published. It rebuilds and re-embeds, which this
        # run has just done; paying that twice is worth one publish path.
        dashboard_cli.publish()


@pipeline_group.command("process")
def process_command() -> None:
    """Process everything that has arrived and is not yet processed, finish
    what is owed, then reconcile tickets - asking nothing, so a scheduler can
    call it (REQ-PIPE-151).

    Every collection's arrivals in one receipt order, each through the same
    per-arrival lifecycle the pipeline's batch uses. It never generates,
    regenerates or deletes anything: `mothman pipeline run` and `bootstrap`
    stay the full rebuild.

    \b
    Exit status:
      0   everything it attempted completed, and nothing it recorded is red
      1   everything completed, and at least one recorded result is red
      2   an arrival, an owed item or a stage failed - it is left for the next pass
      75  another pass holds this database's lock; nothing was changed
    """
    from . import common

    run_process(confirm=common.confirm_change)


def run_process(*, confirm) -> None:
    """The command's body, shared with the TUI's menu entry."""
    import sys

    from qa_tools.common import environments, processing_pass

    # TYPED ID WHERE THE ENVIRONMENT ASKS FOR IT, FROM A PERSON AT A TERMINAL
    # (REQ-PIPE-093 criterion 15) - and never from a scheduler, which has no
    # terminal: a production pass that stopped for a person would never run.
    env = environments.current()
    if env.confirm_changes and sys.stdin.isatty():
        if not confirm(f"Process everything not yet processed in {env.label}?", yes=False):
            console.print("Nothing processed.", style="yellow")
            return
    try:
        with processing_pass.pass_lock("process"):
            report = processing_pass.run_pass(say=lambda m: console.print(m, style="dim"))
    except processing_pass.PassLockHeld as exc:
        console.print(str(exc), style="yellow")
        raise SystemExit(processing_pass.EXIT_LOCKED) from None
    _say_pass(report)
    if report.exit_status:
        raise SystemExit(report.exit_status)


def _say_pass(report) -> None:
    if report.nothing_to_do:
        console.print("Nothing to process and nothing owed.", style="green")
    else:
        console.print(f"Processed {len(report.processed)} arrival(s); applied the gate to "
                      f"{len(report.gated_only)} already checked; ran {len(report.owed)} owed "
                      f"item(s).", style="green")
    for what in report.left_locked:
        console.print(f"{what}: being processed elsewhere - left for the next pass.",
                      style="yellow")
    if report.left_behind_failure:
        console.print(f"{len(report.left_behind_failure)} later arrival(s) left for the next "
                      f"pass behind a failure in their collection.", style="yellow")
    if report.left_behind_locked:
        console.print(f"{len(report.left_behind_locked)} later arrival(s) left for the next "
                      f"pass behind one being processed elsewhere, to keep receipt order.",
                      style="yellow")
    if report.left_for_budget:
        console.print(f"{len(report.left_for_budget)} arrival(s) left for the next pass - "
                      f"this pass's time budget ran out.", style="yellow")
    # REQ-PIPE-154 criteria 6 and 7: apart from every other hold, because
    # the fix is configuration rather than the supplier's.
    from qa_tools.common import schedule_ended
    line = schedule_ended.pass_line(report.schedule_ended)
    if line:
        console.print(line, style="yellow")
    if report.refiled:
        console.print(f"{len(report.refiled)} supply/supplies held for an ended schedule were "
                      f"filed now that dates cover them.", style="green")
    for what, why in report.failures:
        console.print(f"FAILED {what}: {why}", style="red")
    for line in report.tickets:
        console.print(line, style="dim")
    if report.red and not report.failures:
        console.print("At least one recorded result is red.", style="yellow")


def generated_into(root):
    """Both generators writing under `root` - for a resume's comparison
    (REQ-TEST-160), which lives in qa_tools/ and so may not import the
    generator package itself."""
    from generator.output import generated_into as _generated_into

    return _generated_into(root)


@pipeline_group.command("cache-key")
def cache_key_command() -> None:
    """Print the key CI caches a bootstrapped database under (REQ-TEST-117):
    one digest of every input that shapes a bootstrap. The input list is
    qa_tools/common/replay_inputs.py's, which a checkpoint replay compares
    too (REQ-TEST-160) - one list, two readers. Needs no database."""
    from qa_tools.common import replay_inputs

    click.echo(replay_inputs.cache_key())


@pipeline_group.command("bootstrap")
@click.option("--collection", type=click.Choice(["bdm", "cp", "all"]), default="all",
              help="Which collection to populate - bdm = civil-registration, "
                   "cp = child-protection. Default: both.")
@click.option("--force", is_flag=True,
              help="Run even if staging already holds tables. Never over recorded QA "
                   "history - that is refused; `mothman env reset-synthetic` starts "
                   "from empty.")
@click.option("--sequential", is_flag=True,
              help="Check one collection after the other instead of side by side - slower, and the reference a parallel bootstrap should match. Arrivals within a collection always run one at a time, because each filing depends on what the one before it promoted.")
@click.option("--checkpoint-before", "checkpoint_before", type=int, default=None,
              metavar="N",
              help="Keep a copy of the database as it stood once arrival N-1 was processed, "
                   "to resume from later with `mothman pipeline resume` (synthetic asset, "
                   "one collection). N moves back to the start of its receipt instant if "
                   "it falls inside one.")
def bootstrap_command(collection: str, force: bool, sequential: bool,
                      checkpoint_before: int | None) -> None:
    """Take an empty environment to one with data and QA results in it.

    Run this after cloning, on a fresh dev container, or whenever a
    database has been dropped. It is IDEMPOTENT: if this environment
    already holds staged supplies it does nothing and says so, so it
    is safe to run unconditionally at startup.

    The same function backs the TUI's own menu entry and CI's
    populate-a-throwaway-database step, so none of the three can drift
    from the others.
    """
    from qa_tools.common.bootstrap import bootstrap

    result = bootstrap(collection=collection, force=force, sequential=sequential,
                        on_step=lambda msg: console.print(f"{msg}...", style="dim"),
                        checkpoint_before=checkpoint_before)
    if result.refused:
        raise click.ClickException(result.reason)
    if not result.populated:
        console.print(result.reason, style="yellow")
        return
    console.print(
        f"Populated: {result.staged_after} staged table(s) in this environment.",
        style="green")


@pipeline_group.group("checkpoint")
def checkpoint_group() -> None:
    """Checkpoints of a replay, to resume from (REQ-TEST-159). Taken with
    `mothman pipeline bootstrap --collection bdm|cp --checkpoint-before N`."""


@checkpoint_group.command("list")
def checkpoint_list_command() -> None:
    """Every checkpoint on this server, oldest first."""
    from qa_tools.common import checkpoints

    found = checkpoints.listed()
    if not found:
        console.print("No checkpoints. Take one with `mothman pipeline bootstrap "
                      "--collection cp --checkpoint-before N`.")
        return
    for cp in found:
        if not cp.collection_id:
            console.print(f"{cp.name}  (its description cannot be read - a resume would "
                          f"replay from the first arrival)", style="yellow")
            continue
        console.print(f"{cp.name}  {cp.collection_id}, before arrival {cp.before} of "
                      f"{len(cp.recorded.arrivals)}, taken {cp.taken_at} from {cp.source}")
    console.print(f"Keeping the newest {checkpoints.keep()} "
                  f"({checkpoints.KEEP_ENV} changes it).", style="dim")


@checkpoint_group.command("delete")
@click.argument("name")
def checkpoint_delete_command(name: str) -> None:
    """Delete one checkpoint, or a resume's database, by name."""
    from qa_tools.common import checkpoints

    try:
        checkpoints.delete(name)
    except checkpoints.CheckpointRefused as exc:
        raise click.ClickException(str(exc)) from exc
    console.print(f"Deleted {name}.")


@pipeline_group.command("resume")
@click.argument("name")
@click.option("--sequential", is_flag=True,
              help="Run each arrival's tools one after another rather than dbt beside the rest.")
def resume_command(name: str, sequential: bool) -> None:
    """Replay a collection from a checkpoint into a database of its own.

    The first arrival a change can affect is worked out by regenerating the
    deliveries and comparing them, and every other input, with what the
    checkpoint recorded. A change before the checkpoint is refused, naming the
    arrival; nothing changed says so and replays nothing. The checkpoint, and
    the database you were using, are never written to."""
    from qa_tools.common.bootstrap import resume

    result = resume(name, sequential=sequential,
                    on_step=lambda msg: console.print(f"{msg}...", style="dim"))
    if result.refused:
        raise click.ClickException(result.reason)
    if not result.replayed:
        console.print(result.reason)
        return
    from qa_tools.common import supply_db

    console.print(result.reason + ".", style="green")
    # REDACTED: the DSN carries the password, and this line is the one most
    # likely to be pasted somewhere.
    console.print(f"Point MOTHMAN_SUPPLY_DSN at {supply_db._redact(result.dsn)} to use it.")
