"""mothman cp - Child Protection commands (plans/tooling.md #1 Phase 1,
"still open" item finished): generate-synthetic-data and the Quality
Assurance flow against Synthetic source mode. Same wizard/flags duality
as cli/bdm.py, adapted for CP's real differences from Birth
Registrations: a 6-table-per-run collection (not one CSV), no
row-count-growth/previous_run_id concept, and orchestrate_cp.run_single()
needing all 6 tables already loaded into that run's warehouse (via
build_cp_warehouses.add_table_to_run()) before it's called at all -
qa_tools/cp/check_delivery.py's own _load_delivery() already establishes
this exact pattern for local-folder CP checks; run_check() below reuses
it against an existing Synthetic manifest entry's own data/cp_raw/<run_id>/
directory instead of an arbitrary folder."""
from __future__ import annotations
import json
import os
import sys

import rich_click as click
from rich.console import Console
from rich.table import Table

from qa_tools.cp import build_cp_warehouses, cp_common, orchestrate_cp
from qa_tools.common.git_identity import get_run_by
from qa_tools.common.lambda_results_dir import CP_MODULES, patch_write_qa_result_for_lambda
from qa_tools.common.qa_results_reader import list_run_ids

from . import common

AGENCY_ID = cp_common.AGENCY_ID
COLLECTION_ID = cp_common.COLLECTION_ID
TABLES = cp_common.TABLES

console = Console()


def raw_dir() -> str:
    """Read dynamically off build_cp_warehouses' own module attribute -
    same rationale as cli/bdm.py's raw_dir(), never a module-level
    constant bound once at import time."""
    return build_cp_warehouses.CP_RAW_DIR


def manifest_path() -> str:
    return os.path.join(raw_dir(), "manifest.json")


def generate_synthetic_data() -> None:
    """Runs the real generator directly - unlike Birth Registrations,
    there's no pipeline.orchestrate equivalent that also builds the
    combined warehouse for CP; build_cp_warehouses.build_all() (called
    inside run_check() below, via add_table_to_run() per table) is CP's
    own per-run-warehouse step, done lazily per run rather than eagerly
    for the whole manifest here."""
    from generator import generate_cp_runs
    generate_cp_runs.main()


def load_manifest() -> list[dict]:
    with open(manifest_path()) as f:
        return json.load(f)


def manifest_exists() -> bool:
    return os.path.exists(manifest_path())


def default_reference(manifest: list[dict]) -> str:
    """The last Promoted run for this collection, falling back to the
    manifest's own first (always-clean-by-construction) entry - same
    reasoning as cli/bdm.py's default_reference(), except CP has no
    per-reference CSV filename to check for (a reference run's own 6
    table CSVs live under raw_dir()/<run_id>/, checked directly rather
    than inferred from a manifest `file` field CP's manifest doesn't
    have)."""
    promoted = list_run_ids(AGENCY_ID, COLLECTION_ID)
    if promoted:
        candidate = promoted[-1]
        if os.path.isdir(os.path.join(raw_dir(), candidate)):
            return candidate
    return manifest[0]["run_id"]


def _load_delivery(run_id: str) -> None:
    """Loads all 6 real tables for an existing Synthetic manifest run_id
    into that run's warehouse - the same call qa_tools/cp/check_delivery.
    py's own _load_delivery() makes for an arbitrary folder, pointed at
    this run's own data/cp_raw/<run_id>/ directory instead."""
    run_dir = os.path.join(raw_dir(), run_id)
    missing = [t for t in TABLES if not os.path.isfile(os.path.join(run_dir, f"{t}.csv"))]
    if missing:
        raise click.ClickException(
            f"{run_dir} is missing: {', '.join(f'{t}.csv' for t in missing)} - "
            f"run generate-synthetic-data first?")
    for table in TABLES:
        build_cp_warehouses.add_table_to_run(run_id, table, os.path.join(run_dir, f"{table}.csv"),
                                              out_dir=build_cp_warehouses.OUT_DIR,
                                              raw_dir=build_cp_warehouses.CP_RAW_DIR)


def run_check(run_id: str, run_by: str, reference_run_id: str | None = None) -> tuple[list[dict], str]:
    """Runs the real check chain for one existing Synthetic manifest
    entry into a fresh throwaway location - never the real, permanent
    qa_results/ history directly. Returns (results, tmp_results_dir); the
    caller decides whether to common.promote() it, same tmp-dir-first
    pattern as cli/bdm.py's own run_check().

    Unlike BDM, orchestrate_cp.run_single() has no manifest-clobbering
    side effect to guard against (CP's manifest isn't touched by the
    real tool chain at all) - but it DOES require both this run's and
    the reference run's 6 tables already loaded into their own per-run
    warehouses before it's called, which _load_delivery() above does for
    each."""
    manifest = load_manifest()
    if not any(e["run_id"] == run_id for e in manifest):
        raise click.ClickException(
            f"No manifest entry for run_id={run_id!r} - run generate-synthetic-data first?")
    entry = next(e for e in manifest if e["run_id"] == run_id)

    if reference_run_id is None:
        reference_run_id = default_reference(manifest)
    if not os.path.isdir(os.path.join(raw_dir(), reference_run_id)):
        raise click.ClickException(
            f"Reference run {reference_run_id!r}'s data isn't in {raw_dir()} - "
            f"run generate-synthetic-data first?")

    tmp_dir = common.new_tmp_results_dir()
    patch_write_qa_result_for_lambda(CP_MODULES, tmp_dir)

    _load_delivery(reference_run_id)
    _load_delivery(run_id)

    results = orchestrate_cp.run_single(entry, reference_run_id=reference_run_id, run_by=run_by)
    return results, tmp_dir


_STATUS_STYLE = {"pass": "green", "warn": "yellow", "fail": "red", "error": "bold red"}


def report_table(results: list[dict], run_id: str) -> Table:
    table = Table(title=f"Quality Assurance report - {run_id}")
    table.add_column("Tool")
    table.add_column("Check")
    table.add_column("Status")
    for r in results:
        style = _STATUS_STYLE.get(r.get("status"), "")
        status = r.get("status", "?")
        table.add_row(r.get("engine", "?"), r.get("check_id") or r.get("name", "?"),
                      f"[{style}]{status}[/{style}]" if style else status)
    n_fail = sum(1 for r in results if r.get("status") in ("fail", "error"))
    n_warn = sum(1 for r in results if r.get("status") == "warn")
    n_pass = sum(1 for r in results if r.get("status") == "pass")
    table.caption = f"{n_pass} pass / {n_warn} warn / {n_fail} fail-or-error, {len(results)} checks total"
    return table


def has_failures(results: list[dict]) -> bool:
    return any(r.get("status") in ("fail", "error") for r in results)


def picker_choices(manifest: list[dict]) -> list[str]:
    return [f'{e["run_id"]}  ({e["run_date"]}, {e["dirty_severity"] or "clean"})' for e in manifest]


def run_id_from_choice(choice: str) -> str:
    return choice.split()[0]


def run_qa_interactive(commit_default: bool = False) -> None:
    """The Quality Assurance flow's Synthetic-source-mode body for Child
    Protection, called from both `mothman cp qa` (no --run-id given, a
    real terminal) and the TUI main menu - one real implementation, same
    upfront-git-identity reasoning as cli/bdm.py's own run_qa_interactive()."""
    run_by = get_run_by()

    if not manifest_exists():
        if not common.confirm("No synthetic data generated yet - generate it now?", yes=False, default=True):
            console.print("Nothing to check without synthetic data. Stopping.", style="yellow")
            return
        console.print("Generating synthetic data (population=70,000, 15 quarterly snapshots)...", style="dim")
        generate_synthetic_data()

    manifest = load_manifest()
    choice = common.select("Pick a run to check:", picker_choices(manifest),
                            flag_hint="mothman cp qa --run-id <run_id>")
    if choice is None:
        return
    run_id = run_id_from_choice(choice)

    console.print(f"Running the real dbt-core/Soda Core/datacontract-cli/Evidently chain for {run_id}...",
                  style="dim")
    results, tmp_dir = run_check(run_id, run_by)
    console.print(report_table(results, run_id))

    if common.confirm("Promote this run into the real, permanent qa_results/ history?",
                       yes=False, default=commit_default):
        dst = common.promote(tmp_dir, AGENCY_ID, COLLECTION_ID, run_id)
        console.print(f"Promoted -> {dst}", style="green")
        console.print(
            "This only wrote to qa_results/ - commit and push it yourself to publish "
            "(that's what triggers the real CI rebuild).", style="dim")
    else:
        console.print("Not promoted - nothing written to the real qa_results/ history.", style="dim")


@click.group("cp")
def cp_group() -> None:
    """Child Protection - Tier 1 commands."""


@cp_group.command("generate-synthetic-data")
@click.option("--yes", is_flag=True, help="Skip the overwrite confirmation.")
def generate_synthetic_data_command(yes: bool) -> None:
    """Generate (or deterministically regenerate) the full synthetic Child Protection collection."""
    if manifest_exists() and not common.confirm(
            "This will regenerate data/cp_raw/ (deterministic - same content either way). Continue?",
            yes=yes, default=True):
        console.print("Not regenerated.", style="yellow")
        return
    generate_synthetic_data()
    console.print(f"Generated -> {raw_dir()}", style="green")


@cp_group.command("qa")
@click.option("--run-id", default=None, help="An existing manifest run_id (e.g. cp_run_05_2024-...). "
                                              "Omit to pick interactively.")
@click.option("--reference-run-id", default=None,
              help="Defaults to the last Promoted run, or the manifest's own first (clean) entry.")
@click.option("--commit", is_flag=True, help="Write this run into the real, permanent qa_results/ history.")
def qa_command(run_id: str | None, reference_run_id: str | None, commit: bool) -> None:
    """Run the real QA check chain against a Synthetic Child Protection run."""
    if run_id is None:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            raise click.ClickException("Not a real terminal - pass --run-id explicitly.")
        run_qa_interactive(commit_default=commit)
        return

    run_by = get_run_by() if commit else "local-check:not-persisted"
    results, tmp_dir = run_check(run_id, run_by, reference_run_id=reference_run_id)
    console.print(report_table(results, run_id))
    if commit:
        dst = common.promote(tmp_dir, AGENCY_ID, COLLECTION_ID, run_id)
        console.print(f"Promoted -> {dst}", style="green")
    else:
        console.print("(local-only check - not written to qa_results/ history; re-run with --commit to keep it)",
                       style="dim")
    sys.exit(1 if has_failures(results) else 0)
