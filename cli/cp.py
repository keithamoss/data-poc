"""mothman cp - Child Protection commands (plans/tooling.md #1 Phases
1-2): generate-synthetic-data and the Quality Assurance flow against
Synthetic and Local files source modes. Same wizard/flags duality as
cli/bdm.py, adapted for CP's real differences from Birth Registrations:
a 6-table-per-run collection (not one CSV), no row-count-growth/
previous_run_id concept, and orchestrate_cp.run_single() needing all 6
tables already loaded into that run's warehouse (via
build_cp_warehouses.add_table_to_run()) before it's called at all.

The Local files mode (Phase 2) folds in qa_tools/cp/check_delivery.py's
own retired standalone-CLI logic verbatim (that module is gone - this is
now the only place it runs from, per CLAUDE.md's "mothman is the only
programmatic access point" convention) - same real dbt-core/Soda Core/
datacontract-cli/Evidently chain via orchestrate_cp.run_single(), just
reached from a browsable questionary.path() prompt or --folder/
--reference-folder flags instead of a positional folder argument."""
from __future__ import annotations
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

import rich_click as click
from rich.console import Console
from rich.table import Table

from qa_tools.cp import build_cp_warehouses, cp_common, orchestrate_cp
from qa_tools.common import s3_source
from qa_tools.common.git_identity import get_run_by
from qa_tools.common.lambda_results_dir import CP_MODULES, patch_write_qa_result_for_lambda
from qa_tools.common.local_check import run_id_from_path as local_run_id_from_path
from qa_tools.common.qa_results_reader import list_run_ids

from . import common

AGENCY_ID = cp_common.AGENCY_ID
COLLECTION_ID = cp_common.COLLECTION_ID
TABLES = cp_common.TABLES
CONTRACT_PATH = os.path.join(os.path.dirname(__file__), "..", "contract", "child-protection-contract.yaml")

console = Console()


def s3_config() -> dict:
    """The real s3Source/localSource/arrivalPattern config off this
    dataset's own contract YAML - see qa_tools.common.s3_source.
    dataset_s3_config()'s own docstring for the full account of how this
    got safely wired into the real contract (Phase 3, 2026-09-19)."""
    return s3_source.dataset_s3_config(CONTRACT_PATH)


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


def _load_delivery_from_folder(folder: str, run_id: str) -> None:
    """Loads all 6 real tables for one run_id from an arbitrary folder
    into that run's warehouse - the retired qa_tools/cp/check_delivery.py
    CLI's own _load_delivery() logic, folded in here verbatim (Phase 2).
    Used by both Synthetic mode (_load_delivery(), pointed at this run's
    own data/cp_raw/<run_id>/ directory) and Local files mode
    (run_check_local_folder(), pointed at whatever folder the operator
    browsed to)."""
    missing = [t for t in TABLES if not os.path.isfile(os.path.join(folder, f"{t}.csv"))]
    if missing:
        raise click.ClickException(
            f"{folder} is missing: {', '.join(f'{t}.csv' for t in missing)} - "
            f"a CP delivery needs all 6 real tables, the cross-table checks can't run on a partial set")
    for table in TABLES:
        build_cp_warehouses.add_table_to_run(run_id, table, os.path.join(folder, f"{table}.csv"),
                                              out_dir=build_cp_warehouses.OUT_DIR,
                                              raw_dir=build_cp_warehouses.CP_RAW_DIR)


def _load_delivery(run_id: str) -> None:
    """Synthetic mode's own delivery loader - a thin wrapper around
    _load_delivery_from_folder() pointed at this run's own
    data/cp_raw/<run_id>/ directory, with a clearer error message for
    that specific (missing-synthetic-data) case."""
    run_dir = os.path.join(raw_dir(), run_id)
    if not os.path.isdir(run_dir):
        raise click.ClickException(
            f"No manifest entry for run_id={run_id!r} - run generate-synthetic-data first?")
    _load_delivery_from_folder(run_dir, run_id)


def run_check(run_id: str, run_by: str, reference_run_id: str | None = None,
              on_step=None) -> tuple[list[dict], str]:
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

    results = orchestrate_cp.run_single(entry, reference_run_id=reference_run_id, run_by=run_by,
                                        on_step=on_step)
    return results, tmp_dir


def run_check_local_folder(folder: str, reference_folder: str, run_by: str,
                            run_id: str | None = None, run_date: str | None = None,
                            on_step=None) -> tuple[list[dict], str]:
    """The Local files QA source mode's real check-running body (plans/
    tooling.md #1 Phase 2) - folds in qa_tools/cp/check_delivery.py's own
    retired logic: loads both folder and reference_folder's 6 real
    tables (an arbitrary, already-downloaded delivery - not tied to any
    Synthetic manifest entry) via _load_delivery_from_folder(), then
    reuses orchestrate_cp.run_single(), same entry point the Synthetic
    flow above and Thread B's Lambda handler call. Returns (results,
    tmp_results_dir) - same tmp-dir-first Promote pattern as run_check()."""
    run_date = run_date or datetime.now(timezone.utc).date().isoformat()
    run_id = run_id or local_run_id_from_path(folder)
    reference_run_id = local_run_id_from_path(reference_folder, prefix="ref")

    tmp_dir = common.new_tmp_results_dir()
    patch_write_qa_result_for_lambda(CP_MODULES, tmp_dir)

    _load_delivery_from_folder(reference_folder, reference_run_id)
    _load_delivery_from_folder(folder, run_id)

    entry = {"run_id": run_id, "run_date": run_date, "dirty_severity": None}
    results = orchestrate_cp.run_single(entry, reference_run_id=reference_run_id, run_by=run_by,
                                        on_step=on_step)
    return results, tmp_dir


def run_check_s3_delivery(bucket: str, delivery_prefix: str, reference_delivery_prefix: str, run_by: str,
                           run_id: str | None = None, run_date: str | None = None,
                           s3_client=None,
                                on_step=None) -> tuple[list[dict], str]:
    """The S3 QA source mode's real check-running body for Child
    Protection (plans/tooling.md #1 Phase 3) - a delivery here is all 6
    real table CSVs landing together under one shared S3 prefix
    (<s3Source><delivery_id>/), not a single flat key the way BDM's is.
    Downloads every object under delivery_prefix/reference_delivery_prefix
    (real boto3, via qa_tools.common.s3_source) into their own fresh
    local staging dirs, then reuses run_check_local_folder() exactly as
    if a human had downloaded the whole delivery themselves: S3 mode is
    "download, then Local files mode", not a third parallel
    check-running code path. Returns (results, tmp_results_dir) - same
    tmp-dir-first Promote pattern as run_check_local_folder()."""
    staging_dir = tempfile.mkdtemp(prefix="mothman-s3-")
    reference_staging_dir = tempfile.mkdtemp(prefix="mothman-s3-ref-")
    s3_source.download_prefix(bucket, delivery_prefix, staging_dir, s3_client=s3_client)
    s3_source.download_prefix(bucket, reference_delivery_prefix, reference_staging_dir, s3_client=s3_client)
    return run_check_local_folder(staging_dir, reference_staging_dir, run_by, run_id=run_id, run_date=run_date,
                                   on_step=on_step)


def run_check_single_table(table: str, file_path: str, run_by: str,
                            run_id: str | None = None, run_date: str | None = None,
                            on_step=None) -> tuple[list[dict], str]:
    """Single-table Child Protection QA (plans/tooling.md #1's own
    "Single-table Child Protection QA" design, Phase 3.5) - a real
    partial-resupply scenario (one table re-sent after a fix, the other
    5 unchanged) modeled at check-running time the same way
    generator/resupply.py already models it at data-generation time.

    CP's real dbt models need all 6 real tables present (ref()/
    source()), so a check against just one freshly-arrived table can't
    run a reduced set - it auto-pulls the OTHER 5 tables from the most
    recent Promoted run's own local data (data/cp_raw/<run_id>/
    <table>.csv - the only place this PoC durably keeps CP table data
    once a check has finished running), via the exact same
    default_reference() the Synthetic flow already uses to pick its own
    reference run. That same run doubles as the Evidently drift baseline
    too - a real, known-good, already-Promoted 6-table delivery is
    exactly what a drift baseline needs anyway, so no separate reference
    flag is required here the way full-delivery Local files/S3 mode
    needs one.

    Requires at least one CP run already generated/Promoted locally
    (falls back to the manifest's own first entry, same as
    default_reference()) - there's no "other 5 tables" to pull from
    otherwise, a real and clearly-reported limitation, not a silent
    wrong answer."""
    manifest = load_manifest()
    other_tables_run_id = default_reference(manifest)
    if not os.path.isdir(os.path.join(raw_dir(), other_tables_run_id)):
        raise click.ClickException(
            f"No local data for run {other_tables_run_id!r} (the last Promoted/fallback run) - "
            f"run generate-synthetic-data first? Single-table mode needs a known-good delivery "
            f"already on disk to source the other 5 tables from.")

    run_date = run_date or datetime.now(timezone.utc).date().isoformat()
    run_id = run_id or local_run_id_from_path(file_path, prefix="table")

    tmp_dir = common.new_tmp_results_dir()
    patch_write_qa_result_for_lambda(CP_MODULES, tmp_dir)

    _load_delivery(other_tables_run_id)  # full 6-table warehouse, doubles as the Evidently reference

    for other_table in (t for t in TABLES if t != table):
        build_cp_warehouses.add_table_to_run(
            run_id, other_table, os.path.join(raw_dir(), other_tables_run_id, f"{other_table}.csv"),
            out_dir=build_cp_warehouses.OUT_DIR, raw_dir=build_cp_warehouses.CP_RAW_DIR)
    build_cp_warehouses.add_table_to_run(
        run_id, table, file_path, out_dir=build_cp_warehouses.OUT_DIR, raw_dir=build_cp_warehouses.CP_RAW_DIR)

    entry = {"run_id": run_id, "run_date": run_date, "dirty_severity": None}
    results = orchestrate_cp.run_single(entry, reference_run_id=other_tables_run_id, run_by=run_by,
                                        on_step=on_step)
    return results, tmp_dir


def run_check_s3_single_table(bucket: str, table: str, key: str, run_by: str,
                               run_id: str | None = None, run_date: str | None = None,
                               s3_client=None,
                                on_step=None) -> tuple[list[dict], str]:
    """Single-table Child Protection QA's S3 source mode (Phase 3.5) -
    downloads the one real table object (real boto3, via
    qa_tools.common.s3_source), then reuses run_check_single_table()
    exactly as if a human had downloaded it themselves - S3 mode is
    "download, then Local files mode" here too, same as the full-delivery
    S3 mode above."""
    staging_dir = tempfile.mkdtemp(prefix="mothman-s3-")
    local_path = s3_source.download_key(bucket, key, staging_dir, s3_client=s3_client)
    return run_check_single_table(table, local_path, run_by, run_id=run_id, run_date=run_date,
                                   on_step=on_step)


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


_SOURCE_SYNTHETIC = "Synthetic - pick or generate a run"
_SOURCE_LOCAL_FOLDER = "Local files - a delivery folder you've already downloaded"
_SOURCE_S3 = "S3 - browse the real raw-data bucket"
_SOURCE_LOCAL_FILE = "Local file - a CSV you've already downloaded"

_DELIVERY_FULL = "Full delivery - all 6 real tables"
_DELIVERY_SINGLE_TABLE = "Single table - a partial resupply (one table only)"


def _offer_promote(results: list[dict], run_id: str, tmp_dir: str, commit_default: bool) -> None:
    console.print(report_table(results, run_id))
    if common.confirm("Promote this run into the real, permanent qa_results/ history?",
                       yes=False, default=commit_default):
        dst = common.promote(tmp_dir, AGENCY_ID, COLLECTION_ID, run_id)
        common.report_promoted(dst)
    else:
        console.print("Not promoted - nothing written to the real qa_results/ history.", style="dim")


def run_qa_interactive(commit_default: bool = False) -> None:
    """The Quality Assurance flow's real body for Child Protection,
    called from both `mothman cp qa` (no --run-id/--folder given, a real
    terminal) and the TUI main menu - one real implementation across
    both the Synthetic and Local files source modes (plans/tooling.md #1
    Phases 1-2), same upfront-git-identity reasoning as cli/bdm.py's own
    run_qa_interactive()."""
    run_by = get_run_by()

    delivery_scope = common.select(
        "Full delivery or single table?", [_DELIVERY_FULL, _DELIVERY_SINGLE_TABLE],
        flag_hint="mothman cp qa --run-id <run_id> / mothman cp qa --table <table> --file <csv>")
    if delivery_scope is None:
        return

    if delivery_scope == _DELIVERY_SINGLE_TABLE:
        _run_qa_interactive_single_table(run_by, commit_default)
        return

    source = common.select(
        "Which source?", [_SOURCE_SYNTHETIC, _SOURCE_LOCAL_FOLDER, _SOURCE_S3],
        flag_hint="mothman cp qa --run-id <run_id> / mothman cp qa --folder <dir> --reference-folder <dir> / "
                   "mothman cp qa --s3-delivery <prefix> --s3-reference-delivery <prefix>")
    if source is None:
        return

    if source == _SOURCE_LOCAL_FOLDER:
        _run_qa_interactive_local_folder(run_by, commit_default)
        return

    if source == _SOURCE_S3:
        _run_qa_interactive_s3(run_by, commit_default)
        return

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
    with common.chain_progress(run_id) as on_step:
        results, tmp_dir = run_check(run_id, run_by, on_step=on_step)
    _offer_promote(results, run_id, tmp_dir, commit_default)


def _run_qa_interactive_local_folder(run_by: str, commit_default: bool) -> None:
    """The Local files source mode's TUI body (plans/tooling.md #1 Phase
    2) - browses via questionary.path() (real tab-completion, no
    hand-built file picker), then runs the exact same
    run_check_local_folder() the flag-invocable --folder/--reference-folder
    form below also calls."""
    folder = common.path_prompt(
        "Path to the delivery folder you've already downloaded (all 6 real CP tables):",
        flag_hint="mothman cp qa --folder <dir> --reference-folder <dir>")
    if folder is None:
        return
    reference_folder = common.path_prompt(
        "Path to a known-good reference delivery folder (for distribution-drift comparison):",
        flag_hint="mothman cp qa --folder <dir> --reference-folder <dir>")
    if reference_folder is None:
        return

    run_id = local_run_id_from_path(folder)
    console.print(f"Running the real dbt-core/Soda Core/datacontract-cli/Evidently chain for {folder}...",
                  style="dim")
    with common.chain_progress(run_id) as on_step:
        results, tmp_dir = run_check_local_folder(folder, reference_folder, run_by, run_id=run_id,
                                                   on_step=on_step)
    _offer_promote(results, run_id, tmp_dir, commit_default)


def _run_qa_interactive_s3(run_by: str, commit_default: bool) -> None:
    """The S3 source mode's TUI body for Child Protection (plans/
    tooling.md #1 Phase 3) - lists real "delivery" prefixes one level
    under the dataset's own configured s3Source prefix (contract/
    child-protection-contract.yaml's own customProperties), via S3's
    own Delimiter="/" folder-like grouping, picks two of them, then runs
    the exact same run_check_s3_delivery() the flag-invocable
    --s3-delivery/--s3-reference-delivery form below also calls."""
    bucket = common.raw_bucket_name()
    prefix = s3_config()["prefix"] or ""
    console.print(f"Listing deliveries under s3://{bucket}/{prefix} ...", style="dim")
    deliveries = s3_source.list_delivery_prefixes(bucket, prefix)
    if not deliveries:
        console.print(f"No deliveries under s3://{bucket}/{prefix}", style="yellow")
        return

    flag_hint = "mothman cp qa --s3-delivery <prefix> --s3-reference-delivery <prefix>"
    delivery = common.select("Pick a delivery to check:", deliveries, flag_hint=flag_hint)
    if delivery is None:
        return
    reference_delivery = common.select("Pick a known-good reference delivery:", deliveries, flag_hint=flag_hint)
    if reference_delivery is None:
        return

    run_id = local_run_id_from_path(delivery, prefix="s3")
    console.print(f"Downloading + running the real dbt-core/Soda Core/datacontract-cli/Evidently chain "
                  f"for s3://{bucket}/{delivery}...", style="dim")
    with common.chain_progress(run_id) as on_step:
        results, tmp_dir = run_check_s3_delivery(bucket, delivery, reference_delivery, run_by,
                                                  run_id=run_id, on_step=on_step)
    _offer_promote(results, run_id, tmp_dir, commit_default)


def _run_qa_interactive_single_table(run_by: str, commit_default: bool) -> None:
    """Single-table Child Protection QA's TUI body (plans/tooling.md #1
    Phase 3.5) - picks a table, then Local file or S3 as the source for
    just that one table's data. The other 5 tables and the Evidently
    reference both come automatically from the last Promoted run
    (run_check_single_table()'s own docstring has the full account) - no
    separate reference prompt needed here, unlike full-delivery mode."""
    flag_hint = "mothman cp qa --table <table> --file <csv> / mothman cp qa --table <table> --s3-key <key>"
    table = common.select("Which table?", TABLES, flag_hint=flag_hint)
    if table is None:
        return

    source = common.select("Which source?", [_SOURCE_LOCAL_FILE, _SOURCE_S3], flag_hint=flag_hint)
    if source is None:
        return

    if source == _SOURCE_S3:
        bucket = common.raw_bucket_name()
        prefix = s3_config()["prefix"] or ""
        console.print(f"Listing s3://{bucket}/{prefix} ...", style="dim")
        keys = s3_source.list_keys(bucket, prefix)
        if not keys:
            console.print(f"No objects under s3://{bucket}/{prefix}", style="yellow")
            return
        key = common.select(f"Pick the {table} object to check:", keys, flag_hint=flag_hint)
        if key is None:
            return
        run_id = local_run_id_from_path(key, prefix="table")
        console.print(f"Downloading + running the real dbt-core/Soda Core/datacontract-cli/Evidently chain "
                      f"for s3://{bucket}/{key} (table: {table})...", style="dim")
        with common.chain_progress(run_id) as on_step:
            results, tmp_dir = run_check_s3_single_table(bucket, table, key, run_by, run_id=run_id,
                                                          on_step=on_step)
    else:
        file_path = common.path_prompt(f"Path to the {table} CSV you've already downloaded:", flag_hint=flag_hint)
        if file_path is None:
            return
        run_id = local_run_id_from_path(file_path, prefix="table")
        console.print(f"Running the real dbt-core/Soda Core/datacontract-cli/Evidently chain for {file_path} "
                      f"(table: {table})...", style="dim")
        with common.chain_progress(run_id) as on_step:
            results, tmp_dir = run_check_single_table(table, file_path, run_by, run_id=run_id,
                                                       on_step=on_step)

    _offer_promote(results, run_id, tmp_dir, commit_default)


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


def _finish_flag_mode(results: list[dict], run_id: str, tmp_dir: str, commit: bool) -> None:
    console.print(report_table(results, run_id))
    if commit:
        dst = common.promote(tmp_dir, AGENCY_ID, COLLECTION_ID, run_id)
        console.print(f"Promoted -> {dst}", style="green")
    else:
        console.print("(local-only check - not written to qa_results/ history; re-run with --commit to keep it)",
                       style="dim")
    sys.exit(1 if has_failures(results) else 0)


@cp_group.command("qa")
@click.option("--run-id", default=None, help="Synthetic mode: an existing manifest run_id "
                                              "(e.g. cp_run_05_2024-...). Omit to pick interactively.")
@click.option("--reference-run-id", default=None,
              help="Synthetic mode: defaults to the last Promoted run, or the manifest's own first (clean) entry.")
@click.option("--folder", "folder_path", default=None, type=click.Path(exists=True, file_okay=False),
              help="Local files mode: an already-downloaded delivery folder, all 6 real tables "
                   "(instead of --run-id).")
@click.option("--reference-folder", default=None, type=click.Path(exists=True, file_okay=False),
              help="Local files mode: a known-good reference delivery folder to compare distribution drift "
                   "against. Required together with --folder.")
@click.option("--s3-delivery", default=None,
              help="S3 mode: a delivery prefix under the dataset's s3Source prefix to check "
                   "(instead of --run-id/--folder).")
@click.option("--s3-reference-delivery", default=None,
              help="S3 mode: a known-good reference delivery prefix to compare distribution drift against. "
                   "Required together with --s3-delivery.")
@click.option("--table", type=click.Choice(cp_common.TABLES), default=None,
              help="Single-table mode (plans/tooling.md #1 Phase 3.5): check just this one table (a real "
                   "partial resupply) - the other 5 tables auto-pull from the last Promoted run. "
                   "Required together with --file or --s3-key.")
@click.option("--file", "table_file", default=None, type=click.Path(exists=True, dir_okay=False),
              help="Single-table mode: an already-downloaded CSV for --table (instead of --folder/--run-id).")
@click.option("--s3-key", default=None,
              help="Single-table mode: an object key under the dataset's s3Source prefix for --table "
                   "(instead of --s3-delivery).")
@click.option("--commit", is_flag=True, help="Write this run into the real, permanent qa_results/ history.")
def qa_command(run_id: str | None, reference_run_id: str | None, folder_path: str | None,
               reference_folder: str | None, s3_delivery: str | None, s3_reference_delivery: str | None,
               table: str | None, table_file: str | None, s3_key: str | None, commit: bool) -> None:
    """Run the real QA check chain against a Child Protection run - Synthetic (--run-id),
    Local files (--folder/--reference-folder), S3 (--s3-delivery/--s3-reference-delivery), or
    single-table (--table plus --file or --s3-key) source mode."""
    if table is None and (table_file is not None or s3_key is not None):
        raise click.ClickException(
            "--file/--s3-key need --table (single-table mode) to know which table they're for.")

    if table is not None:
        if run_id is not None or folder_path is not None or s3_delivery is not None:
            raise click.ClickException(
                "Pass --table only with --file or --s3-key (single-table mode) - not --run-id/--folder/"
                "--s3-delivery (those are full-delivery modes).")
        if (table_file is None) == (s3_key is None):
            raise click.ClickException("--table requires exactly one of --file or --s3-key.")
        run_by = get_run_by() if commit else "local-check:not-persisted"
        if table_file is not None:
            local_run_id = local_run_id_from_path(table_file, prefix="table")
            with common.chain_progress(local_run_id) as on_step:
                results, tmp_dir = run_check_single_table(table, table_file, run_by,
                                                           run_id=local_run_id, on_step=on_step)
        else:
            bucket = common.raw_bucket_name()
            local_run_id = local_run_id_from_path(s3_key, prefix="table")
            with common.chain_progress(local_run_id) as on_step:
                results, tmp_dir = run_check_s3_single_table(bucket, table, s3_key, run_by,
                                                              run_id=local_run_id, on_step=on_step)
        _finish_flag_mode(results, local_run_id, tmp_dir, commit)
        return

    if s3_delivery is not None:
        if run_id is not None or folder_path is not None:
            raise click.ClickException(
                "Pass exactly one of --run-id (Synthetic mode), --folder (Local files mode), "
                "or --s3-delivery (S3 mode).")
        if s3_reference_delivery is None:
            raise click.ClickException(
                "--s3-delivery requires --s3-reference-delivery (a known-good delivery prefix to compare against).")
        bucket = common.raw_bucket_name()
        run_by = get_run_by() if commit else "local-check:not-persisted"
        local_run_id = local_run_id_from_path(s3_delivery, prefix="s3")
        with common.chain_progress(local_run_id) as on_step:
            results, tmp_dir = run_check_s3_delivery(bucket, s3_delivery, s3_reference_delivery, run_by,
                                                      run_id=local_run_id, on_step=on_step)
        _finish_flag_mode(results, local_run_id, tmp_dir, commit)
        return

    if folder_path is not None:
        if run_id is not None:
            raise click.ClickException(
                "Pass either --run-id (Synthetic mode) or --folder (Local files mode), not both.")
        if reference_folder is None:
            raise click.ClickException(
                "--folder requires --reference-folder (a known-good delivery folder to compare against).")
        run_by = get_run_by() if commit else "local-check:not-persisted"
        local_run_id = local_run_id_from_path(folder_path)
        with common.chain_progress(local_run_id) as on_step:
            results, tmp_dir = run_check_local_folder(folder_path, reference_folder, run_by,
                                                       run_id=local_run_id, on_step=on_step)
        _finish_flag_mode(results, local_run_id, tmp_dir, commit)
        return

    if run_id is None:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            raise click.ClickException("Not a real terminal - pass --run-id or --folder explicitly.")
        run_qa_interactive(commit_default=commit)
        return

    run_by = get_run_by() if commit else "local-check:not-persisted"
    with common.chain_progress(run_id) as on_step:
        results, tmp_dir = run_check(run_id, run_by, reference_run_id=reference_run_id, on_step=on_step)
    _finish_flag_mode(results, run_id, tmp_dir, commit)
