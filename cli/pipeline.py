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
              help="Run the manifest's checks one at a time instead of in parallel - "
                   "easier to debug one specific run's stack trace.")
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

    from qa_tools.common import delivery_log

    from . import dashboard as dashboard_cli

    # THE LOG MUST NOT DESCRIBE A HISTORY THAT NO LONGER EXISTS
    # (REQ-PIPE-069 criterion 6). Pruned against what is actually on
    # disk rather than wiped and rebuilt - see delivery_log.prune() for
    # why, and for the sixty records the wipe version deleted.
    #
    # HERE rather than inside either orchestrator, because only this
    # level knows about both collections: one orchestrator pruning
    # against what IT recognised would delete the other's records every
    # time.
    from qa_tools.common import delivery as delivery_mod

    present = {d.name for d in delivery_mod.survey().received}
    gone = delivery_log.prune(present)
    if gone:
        console.print(f"Removed {len(gone)} delivery record(s) for deliveries that "
                       f"are no longer present.", style="dim")

    if collection in ("bdm", "all"):
        _run_bdm(sequential)
    if collection in ("cp", "all"):
        _run_cp(sequential)

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


@pipeline_group.command("regenerate-history")
@click.option("--collection", type=click.Choice(["bdm", "cp", "all"]), default="all",
              help="Which collection's recorded history to delete and rebuild. Default: both.")
@click.option("--sequential", is_flag=True,
              help="Run the manifest's checks one at a time instead of in parallel.")
@click.option("--yes", is_flag=True,
              help="Skip the confirmation prompt. For a scripted or unattended run.")
def regenerate_history_command(collection: str, sequential: bool, yes: bool) -> None:
    """Delete this collection's recorded QA history and write it again from scratch.

    REQ-PIPE-038 criteria 4-7. DELETES rather than migrates, which is Keith's own call
    (2026-09-21): the data is synthetic, so re-running is honest where reshaping recorded
    results in place would not be.

    IT USED TO DELETE A COMMITTED TREE of JSON files, and the change is worth stating
    because the command's NAME did not change with it. REQ-PIPE-089 made the history rows
    in the `qa` schema, so this deletes runs - and their results, tool output, tables_read
    and dataset_stats, which cascade off them - rather than directories. What it does has
    not changed; where it does it has.

    THE CONFIRMATION PROMPT STAYS, and its reasoning changed rather than weakening. It used
    to be "this destroys thousands of tracked files, and git holds them but recoverable is
    not the same as intended". Nothing is tracked now, so git holds nothing: the recorded
    history is the only copy, which is a stronger reason to ask, not a weaker one. What
    makes it safe at all is that the pipeline is seeded, so the rebuild is deterministic.
    """
    from qa_tools.common import qa_store, supply_db

    scopes = []
    if collection in ("bdm", "all"):
        scopes.append(("registry-services", "civil-registration"))
    if collection in ("cp", "all"):
        scopes.append(("child-protection-family-support", "child-protection"))

    with supply_db.connect(label="mothman:regenerate-history") as conn:
        qa_store.ensure_schema(conn)
        counts = {(a, c): len(qa_store.runs_for(conn, a, c)) for a, c in scopes}

    total = sum(counts.values())
    console.print(f"About to DELETE {total} recorded run(s) across {len(scopes)} collection(s) "
                   "and check them again with the real tools.", style="yellow")
    for (agency, coll), n in counts.items():
        console.print(f"  {agency}/{coll}: {n} run(s)", style="dim")

    if not yes and not click.confirm("Delete and regenerate?", default=False):
        console.print("Nothing deleted.", style="dim")
        return

    with supply_db.connect(label="mothman:regenerate-history") as conn:
        qa_store.ensure_schema(conn)
        deleted = sum(qa_store.delete_history(conn, agency, coll) for agency, coll in scopes)
    console.print(f"Deleted {deleted} run(s). Regenerating...", style="dim")

    if collection in ("bdm", "all"):
        _run_bdm(sequential)
    if collection in ("cp", "all"):
        _run_cp(sequential)

    # CRITERION 5 SURVIVES THE MOVE AS AN ASSERTION ABOUT SCOPES, not
    # about directories. Nothing may be left in the old shape, and the
    # failure it guards is still silent: a scope that is neither a
    # dataset nor a reserved name reads as a dataset nobody configured,
    # and every reader that walks a collection picks it up as one. It
    # was a stray `run_014` directory at collection level before; it is
    # a stray value in the scope column now.
    from qa_tools.common import tables_read as tables_read_mod
    from qa_tools.common.hierarchy import datasets_in_collection

    with supply_db.connect(label="mothman:regenerate-history") as conn:
        for agency, coll in scopes:
            known = {d.dataset_id for d in datasets_in_collection(coll)}
            found = {row[0] for row in conn.execute(
                f'SELECT DISTINCT dataset_id FROM "{qa_store.SCHEMA}".check_result cr '
                f'JOIN "{qa_store.SCHEMA}".run r ON r.run_key = cr.run_key '
                "WHERE r.agency_id = ? AND r.collection_id = ?", [agency, coll]).fetchall()}
            strays = sorted(name for name in found
                             if name
                             and not tables_read_mod.is_reserved_scope(name)
                             and name not in known)
            if strays:
                raise click.ClickException(
                    f"{agency}/{coll} still holds {len(strays)} scope(s) that are neither a "
                    f"dataset nor a reserved name: {', '.join(strays)}")

    console.print("Recorded history regenerated under the per-dataset model.", style="green")


@pipeline_group.command("bootstrap")
@click.option("--collection", type=click.Choice(["bdm", "cp", "all"]), default="all",
              help="Which collection to populate - bdm = civil-registration, "
                   "cp = child-protection. Default: both.")
@click.option("--force", is_flag=True,
              help="Rebuild even if this environment already holds staged supplies. "
                   "Safe - the pipeline is seeded and deterministic - just not free.")
@click.option("--sequential", is_flag=True,
              help="Run the checks one at a time instead of in parallel.")
def bootstrap_command(collection: str, force: bool, sequential: bool) -> None:
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
                        on_step=lambda msg: console.print(f"{msg}...", style="dim"))
    if not result.populated:
        console.print(result.reason, style="yellow")
        return
    console.print(
        f"Populated: {result.staged_after} staged table(s) in this environment.",
        style="green")
