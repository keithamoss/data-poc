"""mothman bdm - Birth Registrations commands (plans/tooling.md #1
Phase 1/2): generate-synthetic-data and the Quality Assurance flow
against Synthetic and Local files source modes. Every function here is
called from both the real Click command (flag-invocable, scriptable)
and the TUI menu (cli/app.py) - one real implementation, two entry
paths, per the wizard/flags duality plans/tooling.md #1 itself was
designed around.

The Local files mode (Phase 2) folds in qa_tools/bdm/check_file.py's own
retired standalone-CLI logic verbatim (that module is gone - this is now
the only place it runs from, per CLAUDE.md's "mothman is the only
programmatic access point" convention) - same real dbt-core/Soda Core/
datacontract-cli/Evidently chain via orchestrate_bdm.run_single(), just
reached from a browsable questionary.path() prompt or --file/
--reference-file flags instead of a positional CSV argument."""
from __future__ import annotations
import json
import os
import sys
import tempfile

import rich_click as click
from rich.console import Console
from rich.table import Table

from qa_tools.bdm import build_per_run_warehouses, orchestrate_bdm
from qa_tools.common import s3_source
from qa_tools.common.git_identity import get_run_by
from qa_tools.common.lambda_results_dir import BDM_MODULES, patch_write_qa_result_for_lambda
from qa_tools.common.local_check import copy_into, run_id_from_path as local_run_id_from_path
from qa_tools.common.qa_results_reader import list_run_ids

from . import common
from qa_tools.common import asset_time

AGENCY_ID = orchestrate_bdm.AGENCY_ID
COLLECTION_ID = orchestrate_bdm.COLLECTION_ID
CONTRACT_PATH = os.path.join(os.path.dirname(__file__), "..", "contract", "bdm-birth-registrations-contract.yaml")

console = Console()


def s3_config() -> dict:
    """The real s3Source/localSource/arrivalPattern config off this
    dataset's own contract YAML - see qa_tools.common.s3_source.
    dataset_s3_config()'s own docstring for the full account of how this
    got safely wired into the real contract (Phase 3, 2026-09-19)."""
    return s3_source.dataset_s3_config(CONTRACT_PATH)


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
    promoted = list_run_ids(AGENCY_ID, COLLECTION_ID)
    if promoted:
        candidate = promoted[-1]
        if os.path.exists(os.path.join(raw_dir(), f"{candidate}.csv")):
            return candidate, f"{candidate}.csv"
    first = manifest[0]
    return first["run_id"], first["file"]


def run_check(run_id: str, run_by: str, reference_run_id: str | None = None,
              on_step=None) -> tuple[list[dict], str]:
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

    results = _run_single_preserving_manifest(
        run_id, csv_path, entry["run_date"], entry["dirty_severity"],
        reference_run_id, reference_csv, run_by=run_by,
        previous_run_id=previous_entry["run_id"] if previous_entry else None,
        previous_csv=previous_entry["file"] if previous_entry else None,
        on_step=on_step,
    )
    return results, tmp_dir


def _run_single_preserving_manifest(*args, **kwargs) -> list[dict]:
    """Calls orchestrate_bdm.run_single(*args, **kwargs), backing up and
    restoring raw_dir()'s real manifest.json around the call - see
    run_check()'s own docstring for the real bug this guards against
    (run_single() unconditionally overwrites it with its own synthetic
    1-or-2-entry manifest, correct for its real Lambda use case but a
    real collision against the full generate_runs.py batch manifest this
    CLI's own run picker reads from). Local files mode (Phase 2) hits
    this exact same collision - a real CSV a human downloaded has
    nothing to do with the batch manifest, but run_single() would still
    clobber it - so this helper is shared, not just run_check()'s own."""
    real_manifest_path = manifest_path()
    real_manifest_backup = None
    if os.path.exists(real_manifest_path):
        with open(real_manifest_path) as f:
            real_manifest_backup = f.read()
    try:
        return orchestrate_bdm.run_single(*args, **kwargs)
    finally:
        if real_manifest_backup is not None:
            with open(real_manifest_path, "w") as f:
                f.write(real_manifest_backup)


def run_check_local_file(csv_path: str, reference_csv: str, run_by: str,
                          run_id: str | None = None, run_date: str | None = None,
                          on_step=None) -> tuple[list[dict], str]:
    """The Local files QA source mode's real check-running body (plans/
    tooling.md #1 Phase 2) - folds in qa_tools/bdm/check_file.py's own
    retired logic: copies the reference CSV into raw_dir() under a real
    run_id (there's no synthetic manifest[0] to fall back on for a real,
    manually-downloaded file - a real reference is required, not
    defaulted), then reuses orchestrate_bdm.run_single(), same entry
    point both the Synthetic flow above and Thread B's Lambda handler
    call. Returns (results, tmp_results_dir) - same tmp-dir-first Promote
    pattern as run_check()."""
    run_date = run_date or asset_time.now().date().isoformat()
    run_id = run_id or local_run_id_from_path(csv_path)
    reference_run_id = local_run_id_from_path(reference_csv, prefix="ref")
    reference_csv_filename = f"{reference_run_id}.csv"
    copy_into(reference_csv, raw_dir(), reference_csv_filename)

    tmp_dir = common.new_tmp_results_dir()
    patch_write_qa_result_for_lambda(BDM_MODULES, tmp_dir)

    results = _run_single_preserving_manifest(
        run_id, csv_path, run_date, None,
        reference_run_id=reference_run_id, reference_csv=reference_csv_filename, run_by=run_by,
        on_step=on_step,
    )
    return results, tmp_dir


def run_check_s3(bucket: str, key: str, reference_key: str, run_by: str,
                  run_id: str | None = None, run_date: str | None = None, s3_client=None,
                  on_step=None) -> tuple[list[dict], str]:
    """The S3 QA source mode's real check-running body (plans/tooling.md
    #1 Phase 3) - downloads key/reference_key (real boto3, via
    qa_tools.common.s3_source) into a fresh local staging dir, then
    reuses run_check_local_file() exactly as if a human had downloaded
    them themselves: S3 mode is "download, then Local files mode", not a
    third parallel check-running code path. Returns (results,
    tmp_results_dir) - same tmp-dir-first Promote pattern as
    run_check_local_file()."""
    staging_dir = tempfile.mkdtemp(prefix="mothman-s3-")
    local_path = s3_source.download_key(bucket, key, staging_dir, s3_client=s3_client)
    local_reference_path = s3_source.download_key(bucket, reference_key, staging_dir, s3_client=s3_client)
    return run_check_local_file(local_path, local_reference_path, run_by, run_id=run_id, run_date=run_date,
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
_SOURCE_LOCAL_FILE = "Local files - a CSV you've already downloaded"
_SOURCE_S3 = "S3 - browse the real raw-data bucket"


def _offer_promote(results: list[dict], run_id: str, tmp_dir: str, commit_default: bool) -> None:
    console.print(report_table(results, run_id))
    if common.confirm("Promote this run into the real, permanent qa_results/ history?",
                       yes=False, default=commit_default):
        dst = common.promote(tmp_dir, AGENCY_ID, COLLECTION_ID, run_id)
        common.report_promoted(dst)
    else:
        console.print("Not promoted - nothing written to the real qa_results/ history.", style="dim")


def run_qa_interactive(commit_default: bool = False) -> None:
    """The Quality Assurance flow's real body, called from both `mothman
    bdm qa` (no --run-id/--file given, a real terminal) and the TUI main
    menu - one real implementation across both the Synthetic and Local
    files source modes (plans/tooling.md #1 Phases 1-2). A real git
    identity is required upfront here (not deferred to Promote time):
    the flow always asks "Promote?" only after the report is already
    shown, so run_by has to be resolved - and correct - before the real
    tool chain ever runs, or a later "yes, promote" would copy a
    placeholder identity into permanent history."""
    run_by = get_run_by()

    source = common.select(
        "Which source?", [_SOURCE_SYNTHETIC, _SOURCE_LOCAL_FILE, _SOURCE_S3],
        flag_hint="mothman bdm qa --run-id <run_id> / mothman bdm qa --file <csv> --reference-file <csv> / "
                   "mothman bdm qa --s3-key <key> --s3-reference-key <key>")
    if source is None:
        return

    if source == _SOURCE_LOCAL_FILE:
        _run_qa_interactive_local_file(run_by, commit_default)
        return

    if source == _SOURCE_S3:
        _run_qa_interactive_s3(run_by, commit_default)
        return

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

    # plans/tooling.md #13 - this used to print the line below and then
    # go completely silent for ~13.5s while the real chain ran.
    console.print(f"Running the real dbt-core/Soda Core/datacontract-cli/Evidently chain for {run_id}...",
                  style="dim")
    with common.chain_progress(run_id) as on_step:
        results, tmp_dir = run_check(run_id, run_by, on_step=on_step)
    _offer_promote(results, run_id, tmp_dir, commit_default)


def _run_qa_interactive_local_file(run_by: str, commit_default: bool) -> None:
    """The Local files source mode's TUI body (plans/tooling.md #1 Phase
    2) - browses via questionary.path() (real tab-completion, no
    hand-built file picker), then runs the exact same
    run_check_local_file() the flag-invocable --file/--reference-file
    form below also calls."""
    csv_path = common.path_prompt("Path to the CSV you've already downloaded:",
                                   flag_hint="mothman bdm qa --file <csv> --reference-file <csv>")
    if csv_path is None:
        return
    reference_csv = common.path_prompt(
        "Path to a known-good reference CSV (for distribution-drift comparison):",
        flag_hint="mothman bdm qa --file <csv> --reference-file <csv>")
    if reference_csv is None:
        return

    run_id = local_run_id_from_path(csv_path)
    console.print(f"Running the real dbt-core/Soda Core/datacontract-cli/Evidently chain for {csv_path}...",
                  style="dim")
    with common.chain_progress(run_id) as on_step:
        results, tmp_dir = run_check_local_file(csv_path, reference_csv, run_by, run_id=run_id,
                                                 on_step=on_step)
    _offer_promote(results, run_id, tmp_dir, commit_default)


def _run_qa_interactive_s3(run_by: str, commit_default: bool) -> None:
    """The S3 source mode's TUI body (plans/tooling.md #1 Phase 3) -
    lists real object keys under the dataset's own configured s3Source
    prefix (contract/bdm-birth-registrations-contract.yaml's own
    customProperties), picks two of them, then runs the exact same
    run_check_s3() the flag-invocable --s3-key/--s3-reference-key form
    below also calls."""
    bucket = common.raw_bucket_name()
    prefix = s3_config()["prefix"] or ""
    console.print(f"Listing s3://{bucket}/{prefix} ...", style="dim")
    keys = s3_source.list_keys(bucket, prefix)
    if not keys:
        console.print(f"No objects under s3://{bucket}/{prefix} - nothing to check.", style="yellow")
        return

    flag_hint = "mothman bdm qa --s3-key <key> --s3-reference-key <key>"
    key = common.select("Pick an object to check:", keys, flag_hint=flag_hint)
    if key is None:
        return
    reference_key = common.select("Pick a known-good reference object:", keys, flag_hint=flag_hint)
    if reference_key is None:
        return

    run_id = local_run_id_from_path(key, prefix="s3")
    console.print(f"Downloading + running the real dbt-core/Soda Core/datacontract-cli/Evidently chain "
                  f"for s3://{bucket}/{key}...", style="dim")
    with common.chain_progress(run_id) as on_step:
        results, tmp_dir = run_check_s3(bucket, key, reference_key, run_by, run_id=run_id,
                                         on_step=on_step)
    _offer_promote(results, run_id, tmp_dir, commit_default)


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


def _finish_flag_mode(results: list[dict], run_id: str, tmp_dir: str, commit: bool) -> None:
    console.print(report_table(results, run_id))
    if commit:
        dst = common.promote(tmp_dir, AGENCY_ID, COLLECTION_ID, run_id)
        console.print(f"Promoted -> {dst}", style="green")
    else:
        console.print("(local-only check - not written to qa_results/ history; re-run with --commit to keep it)",
                       style="dim")
    sys.exit(1 if has_failures(results) else 0)


@bdm_group.command("qa")
@click.option("--run-id", default=None, help="Synthetic mode: an existing manifest run_id "
                                              "(e.g. run_005_2026-...). Omit to pick interactively.")
@click.option("--reference-run-id", default=None,
              help="Synthetic mode: defaults to the last Promoted run, or the manifest's own first (clean) entry.")
@click.option("--file", "file_path", default=None, type=click.Path(exists=True, dir_okay=False),
              help="Local files mode: an already-downloaded CSV to check (instead of --run-id).")
@click.option("--reference-file", default=None, type=click.Path(exists=True, dir_okay=False),
              help="Local files mode: a known-good CSV to compare distribution drift against. "
                   "Required together with --file.")
@click.option("--s3-key", default=None,
              help="S3 mode: an object key under the dataset's s3Source prefix to check "
                   "(instead of --run-id/--file).")
@click.option("--s3-reference-key", default=None,
              help="S3 mode: a known-good reference object key to compare distribution drift against. "
                   "Required together with --s3-key.")
@click.option("--commit", is_flag=True, help="Write this run into the real, permanent qa_results/ history.")
def qa_command(run_id: str | None, reference_run_id: str | None, file_path: str | None,
               reference_file: str | None, s3_key: str | None, s3_reference_key: str | None,
               commit: bool) -> None:
    """Run the real QA check chain against a Birth Registrations run - Synthetic (--run-id),
    Local files (--file/--reference-file), or S3 (--s3-key/--s3-reference-key) source mode."""
    if s3_key is not None:
        if run_id is not None or file_path is not None:
            raise click.ClickException(
                "Pass exactly one of --run-id (Synthetic mode), --file (Local files mode), "
                "or --s3-key (S3 mode).")
        if s3_reference_key is None:
            raise click.ClickException(
                "--s3-key requires --s3-reference-key (a known-good object key to compare against).")
        bucket = common.raw_bucket_name()
        run_by = get_run_by() if commit else "local-check:not-persisted"
        local_run_id = local_run_id_from_path(s3_key, prefix="s3")
        with common.chain_progress(local_run_id) as on_step:
            results, tmp_dir = run_check_s3(bucket, s3_key, s3_reference_key, run_by,
                                             run_id=local_run_id, on_step=on_step)
        _finish_flag_mode(results, local_run_id, tmp_dir, commit)
        return

    if file_path is not None:
        if run_id is not None:
            raise click.ClickException("Pass either --run-id (Synthetic mode) or --file (Local files mode), not both.")
        if reference_file is None:
            raise click.ClickException("--file requires --reference-file (a known-good CSV to compare against).")
        run_by = get_run_by() if commit else "local-check:not-persisted"
        local_run_id = local_run_id_from_path(file_path)
        with common.chain_progress(local_run_id) as on_step:
            results, tmp_dir = run_check_local_file(file_path, reference_file, run_by,
                                                     run_id=local_run_id, on_step=on_step)
        _finish_flag_mode(results, local_run_id, tmp_dir, commit)
        return

    if run_id is None:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            raise click.ClickException("Not a real terminal - pass --run-id or --file explicitly.")
        run_qa_interactive(commit_default=commit)
        return

    run_by = get_run_by() if commit else "local-check:not-persisted"
    with common.chain_progress(run_id) as on_step:
        results, tmp_dir = run_check(run_id, run_by, reference_run_id=reference_run_id, on_step=on_step)
    _finish_flag_mode(results, run_id, tmp_dir, commit)
