"""mothman bdm - Birth Registrations commands (plans/tooling.md #1
Phase 1): generate-synthetic-data and the Quality Assurance flow against
Synthetic source mode. Every function here is called from both the real
Click command (flag-invocable, scriptable) and the TUI menu (cli/app.py) -
one real implementation, two entry paths, per the wizard/flags duality
plans/tooling.md #1 itself was designed around."""
from __future__ import annotations
import json
import os
import sys

import rich_click as click
from rich.console import Console
from rich.table import Table

from qa_tools.bdm import build_per_run_warehouses, orchestrate_bdm
from qa_tools.common.git_identity import get_run_by
from qa_tools.common.lambda_results_dir import BDM_MODULES, patch_write_qa_result_for_lambda
from qa_tools.common.qa_results_reader import list_run_ids

from . import common

AGENCY_ID = orchestrate_bdm.AGENCY_ID
DATASET_ID = orchestrate_bdm.DATASET_ID

console = Console()


def raw_dir() -> str:
    """Read dynamically, at call time, off build_per_run_warehouses'
    own module attribute - never bound to a module-level constant here.
    A real bug class this project has hit more than once (see
    orchestrate_bdm.run_single()'s own comment on the same pitfall): a
    module-level constant captured at import time would silently ignore
    a test (or any other caller) monkeypatching build_per_run_warehouses.
    RAW_DIR afterwards."""
    return build_per_run_warehouses.RAW_DIR


def manifest_path() -> str:
    return os.path.join(raw_dir(), "manifest.json")


def generate_synthetic_data() -> None:
    """Wraps pipeline.orchestrate.prepare_warehouse(regenerate=True) -
    already fuses "generate the synthetic runs" and "build the combined
    warehouse" into one deterministic, idempotent call (confirmed by
    reading that module directly, not assumed - plans/tooling.md #1),
    including the real resupply-chain/dirty-severity simulation
    unmodified."""
    from pipeline import orchestrate
    orchestrate.prepare_warehouse(regenerate=True)


def load_manifest() -> list[dict]:
    with open(manifest_path()) as f:
        return json.load(f)


def manifest_exists() -> bool:
    return os.path.exists(manifest_path())


def default_reference(manifest: list[dict]) -> tuple[str, str]:
    """The last Promoted run for this dataset (plans/tooling.md #1's own
    design: Evidently's reference/baseline defaults to the last run
    that's actually in the real, permanent qa_results/ history), falling
    back to the manifest's own first (always-clean-by-construction) entry
    - the same reference run_pipeline() itself already uses - if nothing
    has been Promoted yet, or if a previously-Promoted run's own CSV no
    longer exists locally (RUN_PLAN's size has changed across versions of
    this repo before; regeneration is deterministic only for run_ids the
    CURRENT RUN_PLAN still produces)."""
    promoted = list_run_ids(AGENCY_ID, DATASET_ID)
    if promoted:
        candidate = promoted[-1]
        if os.path.exists(os.path.join(raw_dir(), f"{candidate}.csv")):
            return candidate, f"{candidate}.csv"
    first = manifest[0]
    return first["run_id"], first["file"]


def run_check(run_id: str, run_by: str, reference_run_id: str | None = None) -> tuple[list[dict], str]:
    """Runs the real check chain for one existing Synthetic manifest entry
    into a fresh throwaway location - never the real, permanent
    qa_results/ history directly. Returns (results, tmp_results_dir); the
    caller decides whether to common.promote() it, matching the same
    tmp-dir-first pattern qa_tools/bdm/check_file.py's own --commit
    handling already uses (qa_tools.common.lambda_results_dir).

    Real bug found live while building this (a manual smoke test actually
    corrupted the real data/raw/manifest.json from 176 entries down to 1):
    orchestrate_bdm.run_single() unconditionally OVERWRITES RAW_DIR/
    manifest.json with its own synthetic 1-or-2-entry manifest - correct
    and intentional for its real Lambda use case (no pre-existing manifest
    there at all - see that function's own docstring), but a real
    collision here, since this CLI's own run picker reads that same path
    as the real, full generate_runs.py batch manifest. Backs the real
    manifest up and restores it around the call rather than changing
    run_single()'s own already-tested Lambda-path contract. Also passes
    the REAL immediately-preceding manifest entry as previous_run_id/
    previous_csv while we're already reading the real manifest anyway -
    real row-count-growth check coverage instead of the silent skip the
    Lambda MVP path settles for when nothing supplies those."""
    manifest = load_manifest()
    idx = next((i for i, e in enumerate(manifest) if e["run_id"] == run_id), None)
    if idx is None:
        raise click.ClickException(
            f"No manifest entry for run_id={run_id!r} - run generate-synthetic-data first?")
    entry = manifest[idx]
    previous_entry = manifest[idx - 1] if idx > 0 else None

    if reference_run_id is None:
        reference_run_id, reference_csv = default_reference(manifest)
    else:
        reference_csv = f"{reference_run_id}.csv"
    if not os.path.exists(os.path.join(raw_dir(), f"{reference_run_id}.csv")):
        raise click.ClickException(
            f"Reference run {reference_run_id!r}'s CSV isn't in {raw_dir()} - "
            f"run generate-synthetic-data first?")

    csv_path = os.path.join(raw_dir(), entry["file"])
    tmp_dir = common.new_tmp_results_dir()
    patch_write_qa_result_for_lambda(BDM_MODULES, tmp_dir)

    real_manifest_path = manifest_path()
    with open(real_manifest_path) as f:
        real_manifest_backup = f.read()
    try:
        results = orchestrate_bdm.run_single(
            run_id, csv_path, entry["run_date"], entry["dirty_severity"],
            reference_run_id, reference_csv, run_by=run_by,
            previous_run_id=previous_entry["run_id"] if previous_entry else None,
            previous_csv=previous_entry["file"] if previous_entry else None,
        )
    finally:
        with open(real_manifest_path, "w") as f:
            f.write(real_manifest_backup)
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
    """The Quality Assurance flow's Synthetic-source-mode body, called
    from both `mothman bdm qa` (no --run-id given, a real terminal) and
    the TUI main menu - one real implementation. A real git identity is
    required upfront here (not deferred to Promote time): the flow always
    asks "Promote?" only after the report is already shown, so run_by has
    to be resolved - and correct - before the real tool chain ever runs,
    or a later "yes, promote" would copy a placeholder identity into
    permanent history."""
    run_by = get_run_by()

    if not manifest_exists():
        if not common.confirm("No synthetic data generated yet - generate it now?", yes=False, default=True):
            console.print("Nothing to check without synthetic data. Stopping.", style="yellow")
            return
        console.print("Generating synthetic data...", style="dim")
        generate_synthetic_data()

    manifest = load_manifest()
    choice = common.select("Pick a run to check:", picker_choices(manifest),
                            flag_hint="mothman bdm qa --run-id <run_id>")
    if choice is None:
        return
    run_id = run_id_from_choice(choice)

    console.print(f"Running the real dbt-core/Soda Core/datacontract-cli/Evidently chain for {run_id}...",
                  style="dim")
    results, tmp_dir = run_check(run_id, run_by)
    console.print(report_table(results, run_id))

    if common.confirm("Promote this run into the real, permanent qa_results/ history?",
                       yes=False, default=commit_default):
        dst = common.promote(tmp_dir, AGENCY_ID, DATASET_ID, run_id)
        console.print(f"Promoted -> {dst}", style="green")
        console.print(
            "This only wrote to qa_results/ - commit and push it yourself to publish "
            "(that's what triggers the real CI rebuild).", style="dim")
    else:
        console.print("Not promoted - nothing written to the real qa_results/ history.", style="dim")


@click.group("bdm")
def bdm_group() -> None:
    """Birth Registrations - Tier 1 commands."""


@bdm_group.command("generate-synthetic-data")
@click.option("--yes", is_flag=True, help="Skip the overwrite confirmation.")
def generate_synthetic_data_command(yes: bool) -> None:
    """Generate (or deterministically regenerate) the full synthetic Birth Registrations batch."""
    if manifest_exists() and not common.confirm(
            "This will regenerate data/raw/ (deterministic - same content either way). Continue?",
            yes=yes, default=True):
        console.print("Not regenerated.", style="yellow")
        return
    generate_synthetic_data()
    console.print(f"Generated -> {raw_dir()}", style="green")


@bdm_group.command("qa")
@click.option("--run-id", default=None, help="An existing manifest run_id (e.g. run_005_2026-...). "
                                              "Omit to pick interactively.")
@click.option("--reference-run-id", default=None,
              help="Defaults to the last Promoted run, or the manifest's own first (clean) entry.")
@click.option("--commit", is_flag=True, help="Write this run into the real, permanent qa_results/ history.")
def qa_command(run_id: str | None, reference_run_id: str | None, commit: bool) -> None:
    """Run the real QA check chain against a Synthetic Birth Registrations run."""
    if run_id is None:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            raise click.ClickException("Not a real terminal - pass --run-id explicitly.")
        run_qa_interactive(commit_default=commit)
        return

    run_by = get_run_by() if commit else "local-check:not-persisted"
    results, tmp_dir = run_check(run_id, run_by, reference_run_id=reference_run_id)
    console.print(report_table(results, run_id))
    if commit:
        dst = common.promote(tmp_dir, AGENCY_ID, DATASET_ID, run_id)
        console.print(f"Promoted -> {dst}", style="green")
    else:
        console.print("(local-only check - not written to qa_results/ history; re-run with --commit to keep it)",
                       style="dim")
    sys.exit(1 if has_failures(results) else 0)
