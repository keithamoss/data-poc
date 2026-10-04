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
    if result.refused:
        raise click.ClickException(result.reason)
    if not result.populated:
        console.print(result.reason, style="yellow")
        return
    console.print(
        f"Populated: {result.staged_after} staged table(s) in this environment.",
        style="green")
