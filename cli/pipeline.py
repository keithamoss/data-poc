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


@pipeline_group.command("regenerate-history")
@click.option("--collection", type=click.Choice(["bdm", "cp", "all"]), default="all",
              help="Which collection's committed history to delete and rebuild. Default: both.")
@click.option("--sequential", is_flag=True,
              help="Run the manifest's checks one at a time instead of in parallel.")
@click.option("--yes", is_flag=True,
              help="Skip the confirmation prompt. For a scripted or unattended run.")
def regenerate_history_command(collection: str, sequential: bool, yes: bool) -> None:
    """Delete this collection's committed qa_results/ history and write it again from scratch.

    REQ-PIPE-038 criteria 4-7. DELETES rather than migrates, which is Keith's own call
    (2026-09-21): the data is synthetic, so re-running is honest where reshaping committed
    files in place would not be. Runs locally and only locally - CI never regenerates,
    opens or queries anything under data/.
    """
    import shutil

    from qa_tools.common.qa_results_writer import QA_RESULTS_DIR

    scopes = []
    if collection in ("bdm", "all"):
        scopes.append(("registry-services", "civil-registration"))
    if collection in ("cp", "all"):
        scopes.append(("child-protection-family-support", "child-protection"))

    targets = [QA_RESULTS_DIR / agency / coll for agency, coll in scopes]
    existing = [t for t in targets if t.is_dir()]
    n_files = sum(len(list(t.rglob("*.json"))) for t in existing)

    console.print(f"About to DELETE {n_files} committed result file(s) across "
                   f"{len(existing)} collection(s) and write them again from the real tools.",
                   style="yellow")
    for target in existing:
        console.print(f"  {target.relative_to(QA_RESULTS_DIR.parent)}", style="dim")
    # WHY A PROMPT AT ALL, when every other mothman command just runs.
    # This is the one command whose whole job is destroying committed
    # history, and it is a one-way change to thousands of tracked
    # files. Git holds the old tree, so it is recoverable - but
    # recoverable is not the same as intended.
    if not yes and not click.confirm("Delete and regenerate?", default=False):
        console.print("Nothing deleted.", style="dim")
        return

    for target in existing:
        shutil.rmtree(target)
    console.print(f"Deleted {n_files} file(s). Regenerating...", style="dim")

    if collection in ("bdm", "all"):
        _run_bdm(sequential)
    if collection in ("cp", "all"):
        _run_cp(sequential)

    # CRITERION 5: nothing may be left in the old shape. Asserted here
    # rather than trusted, because the failure is silent - a stale run
    # directory at collection level reads as a dataset called
    # `run_014`, and every reader that walks the collection picks it up
    # as one.
    from qa_tools.common import tables_read as tables_read_mod
    from qa_tools.common.hierarchy import datasets_in_collection

    for agency, coll in scopes:
        known = {d.dataset_id for d in datasets_in_collection(coll)}
        base = QA_RESULTS_DIR / agency / coll
        if not base.is_dir():
            continue
        strays = sorted(d.name for d in base.iterdir()
                         if d.is_dir()
                         and not tables_read_mod.is_reserved_scope(d.name)
                         and d.name not in known)
        if strays:
            raise click.ClickException(
                f"{agency}/{coll} still holds {len(strays)} scope(s) that are neither a "
                f"dataset nor a reserved name: {', '.join(strays)}")

    console.print("Committed history regenerated under the per-dataset model.", style="green")
