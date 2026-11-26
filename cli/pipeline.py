"""mothman pipeline - the full real-tool batch run, Tier 2 (plans/
tooling.md #1 Phase 4's "Full-pipeline run... Tier 2, not human-facing -
that's more there for like integration tests and for yourself and not
there for the humans" - Keith's own framing).

`mothman pipeline run` is the real path on every asset (CLI A, SETTLED by
Keith 2026-11-14; REQ-PIPE-385 criterion 4): it processes every arrival in
the delivery tree through the real tools, recording QA history, then builds
the dashboard. It generates nothing, plays nothing and installs no replay
clock - a replayed synthetic history is `mothman pipeline bootstrap`'s, which
the bootstrap package (bootstrap/) runs. `process` is the scheduler's pass
over what has arrived since.
"""
from __future__ import annotations

import rich_click as click
from rich.console import Console

from cli import common, synthetic

console = Console()


@click.group("pipeline", cls=synthetic.Group,
             synthetic={"bootstrap", "resume", "checkpoint", "cache-key"})
def pipeline_group() -> None:
    """Full real-tool batch pipeline run - Tier 2 (CI/automation, integration-test parity)."""


@pipeline_group.command("run")
@common.short_collection_option(
    all_choice=True,
    help="Which collection's arrivals to process - {legend}. Default: {every}.")
@click.option("--sequential", is_flag=True,
              help="Run each supply's four QA tools one after another rather than dbt and datacontract-cli each in a worker beside Soda Core and Evidently (dbt stays in its own worker either way) - slower, and easier to read when debugging. Arrivals always run one at a time, because each filing depends on what the one before it promoted - and collections that share a calendar always run as one stream in receipt order.")
@click.option("--snapshot", is_flag=True,
              help="Also archive a dashboard snapshot afterward (same as SNAPSHOT_DASHBOARD=1).")
@click.option("--publish", "do_publish", is_flag=True,
              help="Also publish the built dashboard. OPT-IN: a run without this builds for "
                   "local viewing and publishes nothing.")
def run_command(collection: str, sequential: bool, snapshot: bool, do_publish: bool) -> None:
    """Run the real tools against every arrival in the delivery tree, recording QA
    history, then rebuild and embed the dashboard - a real pipeline run, not a dry run.
    It needs a database with no QA history yet.

    PUBLISHING IS OPT-IN (REQ-PIPE-092 criterion 16), and that was decided the other way
    first. Opt-out reads as friendlier and is wrong here: a debugging run, a batch and a
    scheduled run would each publish a dashboard nobody asked for, and the one that matters
    is the debugging run - somebody reproducing a problem would put their reproduction on
    the public site. `--publish` goes through the same single path
    `mothman dashboard publish` uses (criterion 10).
    """
    import os

    from asset_model import asset_time
    from qa_tools.common import qa_store, streams, supply_db

    from . import dashboard as dashboard_cli

    # A PUBLISH THIS ASSET MAY NOT MAKE IS REFUSED BEFORE THE RUN, not after
    # it (REQ-PIPE-372 criterion 2): nothing is processed only to be refused.
    if do_publish:
        refused = dashboard_cli.publish_refusal()
        if refused:
            raise click.ClickException(refused)

    # REFUSED OVER RECORDED HISTORY (REQ-PIPE-144 criterion 39), before
    # anything is run, for the reason bootstrap --force is: a re-run adds to
    # the history rather than replacing it. The refusal is the pipeline's own
    # (qa_tools/common/streams.py, REQ-GEN-381 criterion 5), so this command
    # needs nothing of the bootstrap package.
    #
    # NOTHING PRUNES THE DELIVERY LOG ANY MORE (criteria 19 and 24,
    # amending REQ-PIPE-069 criterion 6). A delivery whose files have
    # moved on - in production, to another bucket, which is every
    # delivery - is history that still exists.
    with supply_db.connect(label="mothman:pipeline-run") as conn:
        qa_store.ensure_schema(conn)
        if streams.holds_history(conn):
            raise click.ClickException(streams.HISTORY_REFUSAL[0].upper()
                                       + streams.HISTORY_REFUSAL[1:])

    # THE REAL PATH ON EVERY ASSET (CLI A, SETTLED by Keith 2026-11-14;
    # REQ-PIPE-385 criterion 4; REQ-PIPE-383 criteria 5 and 6): it generates
    # nothing, plays no scripted decision, installs no replay clock, compares no
    # targets and confirms no correction - a replayed history is
    # `mothman pipeline bootstrap`'s. Said once, dimly, where it would be asked.
    if asset_time.declared_synthetic():
        console.print("Scripted decisions are played only by `mothman pipeline bootstrap` "
                      "- this run played none.", style="dim")

    # THE PASS LOCK (REQ-PIPE-151 criterion 16), held while anything runs.
    from qa_tools.common import processing_pass
    from qa_tools.tools import orchestrate

    try:
        with processing_pass.pass_lock("run"):
            from asset_model import collections

            chosen = [c.short for c in collections.all_collections()
                      if collection in (c.short, "all")]
            try:
                groups = streams.streams(chosen)
            except streams.StreamRefused as exc:
                raise click.ClickException(str(exc)) from exc
            for group in groups:
                colls = [collections.by_short(short) for short in group]
                console.print("Running the real tools against every "
                              + " and ".join(c.short.upper() for c in colls) + " arrival"
                              + (", as one stream in receipt order" if len(colls) > 1 else "")
                              + "...", style="dim")
                orchestrate.run_stream([c.id for c in colls], sequential=sequential)
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
        # A FAILED PUBLISH KEEPS THE RUN (REQ-PIPE-255 criterion 29): the
        # results are recorded and the local page built; only the upload is
        # retried.
        dashboard_cli.publish_after_a_run()


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
      0   everything it attempted completed, and nothing it recorded is failing
      1   everything completed, and at least one recorded result is failing
      2   an arrival, an owed item or a stage failed - it is left for the next pass
      3   a dataset is refused: its judged past no longer matches the delivery
          agreement and no correction declares why (see check-agreement)
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
            report = processing_pass.run_pass(
                say=lambda m: console.print(m, style="dim", markup=False, highlight=False))
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
        waited = [o for o in report.owed if getattr(o, "frozen", False)]
        console.print(f"Processed {len(report.processed)} arrival(s); applied the gate to "
                      f"{len(report.gated_only)} already checked; ran "
                      f"{len(report.owed) - len(waited)} owed item(s).", style="green")
        # WAITING ON A REFUSAL is said, never counted as run (delivery-critic
        # on (f)-(i), finding 6).
        # TOTALLED BY PERIOD (REQ-PIPE-327 criterion 4): at thirty
        # collections one summary naming one period is wrong as often as right.
        for period in sorted(report.by_period, key=lambda p: (p is None, p or "")):
            n = report.by_period[period]
            words = ", ".join(x for x in (f"{n['filed']} filed" if n["filed"] else "",
                                          f"{n['held']} held" if n["held"] else "") if x)
            console.print(f"  {period or 'No period yet'}: {words}", markup=False,
                          highlight=False)
        if waited or report.left_frozen:
            console.print(f"{len(waited)} owed item(s) and {len(report.left_frozen)} "
                          f"arrival(s) wait on a refused dataset - they go ahead once the "
                          f"agreement is restored or the change is declared.", style="yellow")
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
    # REQ-PIPE-179 criterion 26: apart again, and quietly - not a state
    # needing a person.
    line = schedule_ended.turned_off_pass_line(report.turned_off)
    if line:
        console.print(line, style="dim")
    if report.refiled:
        console.print(f"{len(report.refiled)} supply/supplies held for an ended schedule were "
                      f"filed now that dates cover them.", style="green")
    if report.refiled_cleared:
        console.print(f"{len(report.refiled_cleared)} supply/supplies held while their dataset "
                      f"was refused were filed now that the agreement matches again.",
                      style="green")
    if report.parked_moved:
        console.print(f"{len(report.parked_moved)} parked correction move(s) went ahead now "
                      f"that what blocked them has cleared.", style="green")
    # REQ-PIPE-170 criterion 20: noted, never worked out by the pass.
    if report.pending_corrections:
        console.print(f"{len(report.pending_corrections)} calendar correction(s) await the data "
                      f"asset's manager to confirm: {', '.join(report.pending_corrections)}. "
                      f"`mothman supply corrections` shows each one's moves.", style="yellow")
    # REQ-PIPE-173 criterion 4: a refused dataset is stated in the summary.
    if report.refused:
        console.print(f"REFUSED {len(report.refused)} dataset(s) - recorded judgements no "
                      f"longer match the delivery agreement: {', '.join(report.refused)}. "
                      f"`mothman schedule check-agreement` names each change.", style="red")
    for what, why in report.failures:
        console.print(f"FAILED {what}: {why}", style="red")
    # COMMENTS READ, DECISIONS RAISED, REFUSALS (REQ-GHUB-433 criterion 14).
    if report.comments is not None:
        console.print(report.comments.line(), style="dim")
    for line in report.tickets:
        console.print(line, style="dim")
    if report.red and not report.failures:
        console.print("At least one recorded result is a Fail.", style="yellow")


class TargetTrialUnavailable(click.ClickException):
    """A target trial asked of a collection whose provider declares none
    (REQ-GEN-246 criterion 6)."""


def try_targets(collection_id: str) -> int:
    """A collection's target trial - the collection command's (cli/
    collection_cli.py), handed to the bootstrap, which may not import cli/
    (REQ-GEN-381 criterion 3)."""
    from cli.collection_cli import of

    return of(collection_id).try_targets(collection_id=collection_id)


def generate_collection(collection_id: str, *, trial: bool, anchor: str | None = None) -> None:
    """One collection's synthetic history, its target trial, then the scenario
    map - bootstrap/generation.py's, with its refusals said as this terminal
    says a refusal."""
    import time

    from asset_model import config_pin, config_yaml
    from bootstrap import generation
    from generator import public as generator_public

    started = time.monotonic()
    try:
        generation.generate_on_its_own(
            collection_id, trial=trial, try_targets=try_targets,
            say=lambda m: console.print(m, style="yellow"), anchor=anchor)
    except generator_public.AnchorRefused as exc:
        # BEFORE ANYTHING IS WRITTEN (REQ-GEN-404 criteria 7 to 9).
        raise click.ClickException(str(exc)) from None
    except generation.NoGenerator as exc:
        raise click.ClickException(str(exc)) from None
    except generation.TargetTrialUnavailable as exc:
        raise TargetTrialUnavailable(str(exc)) from None
    except (config_pin.PinRefused, config_yaml.OffsetRefused) as exc:
        # A REFUSAL, NOT A TRACEBACK (post-build-review #397): the asset is
        # not synthetic, so there is nothing to generate.
        raise click.ClickException(str(exc)) from None
    # ONE LINE, ITS OWN (REQ-GEN-398 criterion 3; CLI finding 4): run on its
    # own, the command says how long generation took. Inside a bootstrap it is
    # an entry of the 'Took ...' line instead, and this function is not used.
    console.print(generation.took_line(time.monotonic() - started), style="dim")


@pipeline_group.command("cache-key")
def cache_key_command() -> None:
    """Print the key CI caches this asset's bootstrapped database under
    (REQ-TEST-117): one digest of every input that shapes its bootstrap - the
    shared inputs and this asset's own folder, never another asset's
    (REQ-PIPE-365 criterion 3). The input list is
    bootstrap/replay_inputs.py's, which a checkpoint replay compares
    too (REQ-TEST-160) - one list, two readers. Needs no database."""
    from bootstrap import replay_inputs

    click.echo(replay_inputs.cache_key())


@pipeline_group.command("bootstrap")
@common.short_collection_option(
    all_choice=True, help="Which collection to populate - {legend}. Default: {every}.")
@click.option("--force", is_flag=True,
              help="Run even if staging already holds tables. Never over recorded QA "
                   "history - that is refused; `mothman env reset-synthetic` starts "
                   "from empty.")
@click.option("--sequential", is_flag=True,
              help="Check one stream after the other instead of side by side, and each supply's four QA tools one after another rather than dbt and datacontract-cli each in a worker beside Soda Core and Evidently (dbt stays in its own worker either way) - slower, and the reference a parallel bootstrap should match. Collections that share a calendar are always one stream, their arrivals interleaved in receipt order as the live pass does; arrivals always run one at a time, because each filing depends on what the one before it promoted.")
@click.option("--checkpoint-before", "checkpoint_before", type=int, default=None,
              metavar="N",
              help="Keep a copy of the database as it stood once arrival N-1 was processed, "
                   "to resume from later with `mothman pipeline resume`. A synthetic asset, "
                   "one collection, an empty database. If N falls inside a delivery it "
                   "moves back to where that delivery begins. `mothman pipeline checkpoint "
                   "arrivals --collection cp` lists the arrival numbers.")
@click.option("--skip-target-trial", is_flag=True,
              help="Do not try each injected target against the real tools after "
                   "generating. Every targeted supply is still compared with what it was "
                   "built to once the replay finishes.")
@click.option("--anchor", "anchor", default=None, metavar="YYYY-MM-DD",
              help="Generate the history up to this date rather than the fixed test anchor "
                   "(2026-09-25) - to rebuild a demo history given its date back. From "
                   "2026-09-25 to today on the asset's clock. An empty database only.")
@click.option("--roll-anchor", "roll_anchor", is_flag=True,
              help="Generate the demo history up to today on the asset's own clock (or the "
                   "day before, if a receipt is still planned for later today). An empty "
                   "database only; the deployment-half tests refuse a rolled history.")
def bootstrap_command(collection: str, force: bool, sequential: bool,
                      checkpoint_before: int | None, skip_target_trial: bool,
                      anchor: str | None = None, roll_anchor: bool = False) -> None:
    """Take an empty environment to one with data and QA results in it.

    \b
    Examples:
      mothman pipeline bootstrap                      the fixed test anchor, 2026-09-25
      mothman pipeline bootstrap --roll-anchor        a demo up to today
      mothman pipeline bootstrap --anchor 2026-11-13  a history up to that date

    Run this after cloning, on a fresh dev container, or whenever a
    database has been dropped. It is IDEMPOTENT: if this environment
    already holds staged supplies it does nothing and says so, so it
    is safe to run unconditionally at startup.

    The same function backs the TUI's own menu entry and CI's
    populate-a-throwaway-database step, so none of the three can drift
    from the others.
    """
    from bootstrap import bootstrap as boot

    if anchor is not None and roll_anchor:
        # A USAGE ERROR NAMING BOTH (REQ-GEN-404 criterion 5).
        raise click.UsageError("--anchor and --roll-anchor were both given - give one: "
                               "--anchor names the date, --roll-anchor rolls to today.")
    result = boot.bootstrap(collection=collection, force=force, sequential=sequential,
                            on_step=_step, checkpoint_before=checkpoint_before,
                            skip_target_trial=skip_target_trial, try_targets=try_targets,
                            anchor=anchor, roll_anchor=roll_anchor)
    if result.refused:
        raise click.ClickException(result.reason)
    if not result.populated:
        console.print(result.reason, style="yellow")
        return
    # AFTER THE 'Took' AND BUDGET LINES, IN THIS ORDER (REQ-GEN-399 criterion
    # 4): the pinned digest, dimmed, then the closing line.
    if result.pin_digest:
        console.print(boot.pinned_line(result.pin_digest), style="dim")
    if result.checkpoint:
        # REPEATED AT THE END (post-build-review #133 B6) - the line that
        # took it is hundreds of lines up - and before any failure below, so
        # a failed run still names it (post-build-review #398).
        console.print(f"Checkpoint kept: {result.checkpoint}. Resume from it with "
                      f"`mothman pipeline resume {result.checkpoint}`.", style="green")
    # A STARTED PROCESS UNDER ANOTHER PIN FAILS THE BOOTSTRAP (criterion 3), and
    # so does a DELIVERY TREE CHANGED MID-REPLAY (REQ-PIPE-430 criterion 3) -
    # said before anything green (post-build-review #398).
    for message in (boot.pin_mismatch_message(result.pin_differences),
                    boot.tree_changed_message(result.tree_changes)):
        if message:
            raise click.ClickException(message)
    console.print(f"Populated: {boot.closing_line(result)}", style="green", soft_wrap=True)
    _fail_on_disagreements(result.disagreements)


def disagreement_message(disagreements) -> str | None:
    """The one wording every bootstrap caller gives (REQ-GEN-186 criterion
    3) - the CLI and the TUI alike (post-build-review #157 finding 1)."""
    if not disagreements:
        return None
    return (f"{len(disagreements)} targeted supply/supplies did not read as built once "
            f"replayed - nothing recorded was changed:\n"
            + "\n".join(f"  - {d}" for d in disagreements))


def _fail_on_disagreements(disagreements) -> None:
    """FAILS, BUT CHANGES NOTHING (REQ-GEN-186 criteria 3 and 6): the history
    stands as recorded, and the failure names each supply the real tools read
    differently from how it was built, with the checks responsible."""
    message = disagreement_message(disagreements)
    if message:
        raise click.ClickException(message)


def _step(msg: str) -> None:
    """A progress line. A statement keeps its own full stop; only work still
    under way trails off (#133 B13)."""
    console.print(msg if msg.endswith((".", ")")) else f"{msg}...", style="dim", soft_wrap=True)


@pipeline_group.group("checkpoint")
def checkpoint_group() -> None:
    """Checkpoints of a replay, to resume from (REQ-TEST-159). Taken with
    `mothman pipeline bootstrap --collection cp --checkpoint-before N`, for any collection."""


@checkpoint_group.command("list")
def checkpoint_list_command() -> None:
    """This asset's checkpoints on this server, oldest first, then its
    resumes' databases - never another asset's (REQ-PIPE-365) - then any
    made before the asset split, which belong to no asset."""
    from asset_model import assets as _assets
    from bootstrap import checkpoints

    found = checkpoints.listed()
    if not found:
        console.print(f"No checkpoints of asset {_assets.selected().name!r}. Take one with "
                      "`mothman pipeline bootstrap --collection cp --checkpoint-before N`.")
    for cp in found:
        if not cp.collection_id:
            console.print(f"{cp.name}  (its description cannot be read - a resume from it "
                          f"would be refused)", style="yellow")
            continue
        taken = _on_asset_clock(cp.taken_at) if cp.taken_at else "?"
        console.print(f"{cp.name}  {cp.collection_id}, before arrival {cp.before} of "
                      f"{len(dict.fromkeys(a.run_id for a in cp.recorded.arrivals))}, "
                      f"taken {taken} from {cp.source}")
    if found:
        console.print(f"Keeping the newest {checkpoints.keep()} checkpoints of each database "
                      f"({checkpoints.KEEP_ENV} changes it).", style="dim")
    # RESUMES ARE LISTED, NEVER PRUNED (#133 B8, Keith 2026-10-07): a person
    # may be pointed at one.
    made = checkpoints.resumes()
    if made:
        console.print("Resume databases (never removed automatically):")
        for r in made:
            console.print(f"  {r.name}")
    # MADE BEFORE THE SPLIT (post-build-review #347): named for no asset, so
    # shown apart from every asset's, never pruned, deletable by name.
    old = checkpoints.legacy()
    if old:
        console.print("Made before the asset split - belongs to no asset (delete with "
                      "`mothman pipeline checkpoint delete NAME`):")
        for name in old:
            console.print(f"  {name}")


@checkpoint_group.command("arrivals")
@common.short_collection_option(required=True, help="{legend}.")
def checkpoint_arrivals_command(collection: str) -> None:
    """The arrival numbers `--checkpoint-before N` counts, with the delivery
    and receipt instant of each - from a regeneration, never data/."""
    from asset_model import collections
    from bootstrap import checkpoints

    found = checkpoints.arrivals_of(collections.by_short(collection).id)
    for i, a in enumerate(found, start=1):
        files = ", ".join(f for names in a.files_by_dataset.values() for f in names)
        console.print(f"{i:>4}  {_on_asset_clock(a.received_at)}  "
                      f"{a.delivery_name}  {files}", soft_wrap=True)
    console.print(f"{len(found)} arrivals. A checkpoint can be taken before 2 to {len(found)}; "
                  "one inside a delivery moves back to where it begins.", style="dim")


@checkpoint_group.command("delete")
@click.argument("name")
@click.option("--yes", is_flag=True, help="Delete without asking.")
def checkpoint_delete_command(name: str, yes: bool) -> None:
    """Delete one checkpoint, or a resume's database, by name (from
    `mothman pipeline checkpoint list`). Anything connected to it is cut off."""
    from bootstrap import checkpoints

    if not yes and not click.confirm(
            f"Delete {name}? Anything connected to it is disconnected, and a checkpoint takes "
            "a bootstrap to make again", default=False):
        raise click.ClickException("nothing was deleted")
    try:
        checkpoints.delete(name)
    except checkpoints.CheckpointRefused as exc:
        raise click.ClickException(str(exc)) from exc
    console.print(f"Deleted {name}.")


@pipeline_group.command("resume")
@click.argument("name")
@click.option("--sequential", is_flag=True,
              help="Run each arrival's four QA tools one after another rather than dbt and datacontract-cli each in a worker beside Soda Core and Evidently (dbt stays in its own worker either way).")
def resume_command(name: str, sequential: bool) -> None:
    """Replay a collection from checkpoint NAME (see `mothman pipeline
    checkpoint list`) into a NEW database of its own, which you then point
    MOTHMAN_SUPPLY_DSN at - the line to paste is printed at the end.

    The first arrival a change can affect is worked out by regenerating the
    deliveries and comparing them, and every other input, with what the
    checkpoint recorded. A change before the checkpoint is refused, naming the
    arrival; nothing changed says so and replays nothing. The checkpoint, and
    the database you were using, are never written to."""
    from bootstrap.bootstrap import resume

    result = resume(name, sequential=sequential, on_step=_step)
    if result.refused:
        raise click.ClickException(result.reason)
    if not result.replayed:
        console.print(result.reason)
        return
    from qa_tools.common import supply_db

    console.print(result.reason + ".", style="green")
    # ONE LINE THAT CAN BE PASTED (#133 B1): URL form like every other DSN in
    # this project, never wrapped, the password left as a placeholder because
    # this is the line most likely to be pasted somewhere.
    console.print("To use it:")
    console.print(f"  export {supply_db.SUPPLY_DSN_ENV}={_pasteable(result.dsn)}",
                  soft_wrap=True, highlight=False)
    console.print("To go back, set it to your previous value again.", style="dim")
    from bootstrap import bootstrap as boot

    changed = boot.tree_changed_message(result.tree_changes)
    if changed:
        raise click.ClickException(changed)
    _fail_on_disagreements(result.disagreements)


def _on_asset_clock(value) -> str:
    """An instant on the asset's own clock, as a person reads it (#133 B13)."""
    from asset_model import asset_time

    return asset_time.localise(value).strftime("%Y-%m-%d %H:%M %Z")


def _pasteable(dsn: str) -> str:
    """postgresql://user:<password>@host:port/db - the password a placeholder."""
    import psycopg

    info = psycopg.conninfo.conninfo_to_dict(dsn)
    who = info.get("user", "")
    if info.get("password"):
        who += ":<password>"
    host = info.get("host", "localhost") + (f":{info['port']}" if info.get("port") else "")
    return f"postgresql://{who}{'@' if who else ''}{host}/{info.get('dbname', '')}"
