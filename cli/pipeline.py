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
staging so an ad hoc check never touches real history uninvited), this
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
def run_command(collection: str, sequential: bool, snapshot: bool) -> None:
    """Replaces run_pipeline.sh: regenerate synthetic data, run the real tools against every
    run in the manifest (writing fresh qa_results/ history), then rebuild and embed the
    dashboard. Same real, permanent qa_results/ write as any other real pipeline run - not a
    dry run."""
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
