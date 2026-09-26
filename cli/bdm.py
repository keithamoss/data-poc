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



def generate_synthetic_data() -> None:
    """Runs the real generator directly - the same shape as cli/cp.py's
    own generate_synthetic_data(), which is new.

    IT USED TO BUILD A DUCKDB WAREHOUSE TOO. This wrapped
    pipeline.orchestrate.prepare_warehouse(), which generated the runs
    and then loaded every one of them into one combined DuckDB file at
    data/warehouse.duckdb. That file had exactly one reader - the
    dashboard build's own direct chart queries - and it lost that reader
    in Phase 3 of plans/publishing-and-history.md, when the build became
    a pure function of committed results. It kept being written for
    another year of project time with nothing reading it, which is the
    quiet kind of legacy: no error, no failing test, just a generator
    step paying for a warehouse nobody opens.

    REQ-PIPE-087 criterion 1 is what finally removed it - all supply data
    lives in the one PostgreSQL database and none of it in a DuckDB file -
    and staging now happens where it belongs, per arrival, as QA runs
    (REQ-PIPE-068). Generating synthetic data is generating synthetic
    data again."""
    from generator import generate_runs
    generate_runs.main()
    # THE MAP IS REBUILT IN THE SAME ACT (REQ-GEN-045 criterion 3).
    # A map regenerated separately is a map that disagrees with the
    # history the first time somebody regenerates one and not the
    # other - and it disagrees silently, because both files look
    # fine on their own.
    from qa_tools.common import scenario_map
    scenario_map.write_map()


def load_manifest() -> list[dict]:
    """Every arrival, RECOGNISED FROM DISK (REQ-GEN-043).

    Named `load_manifest` still because every caller here treats it as
    "the list of runs", but it no longer opens the generator's
    manifest.json - that is bookkeeping, and reading it would file
    supplies from a declaration rather than from what arrived.
    """
    from qa_tools.common import arrivals
    # A HELD supply is not pickable: nothing may choose between its
    # files, so there is no one csv_path to offer (REQ-PIPE-059).
    return [a.as_entry()
                | {"csv_path": str(a.path_for("birth-registrations"))}
            for a in arrivals.arrivals_for("civil-registration", "run_")
            if "birth-registrations" not in a.held]


def manifest_exists() -> bool:
    """Is there anything to pick from? A real question now: with no
    deliveries on disk there are no arrivals, which is what the picker
    needs to know."""
    return bool(load_manifest())


def default_reference(manifest: list[dict]) -> tuple[str, str]:
    """The last Promoted run for this dataset (plans/tooling.md #1's own
    design: Evidently's reference/baseline defaults to the last run
    that's actually in the real, permanent qa_results/ history), falling
    back to the manifest's own first (always-clean-by-construction) entry
    - the same reference run_pipeline() itself already uses - if nothing
    has been Promoted yet, or if a previously-Promoted run is no longer
    among the arrivals recognised on disk (RUN_PLAN's size has changed
    across versions of this repo before; regeneration is deterministic
    only for run_ids the CURRENT RUN_PLAN still produces).

    "Still there" is asked of the RECOGNISED ARRIVALS, not of a
    <run_id>.csv sitting in raw_dir() (REQ-GEN-043). A delivery's file
    is named by the supplier, not after our run_id, so the old check
    asked a question the delivery tree cannot answer - and the path to
    hand downstream is the arrival's own, not one built from a run_id."""
    promoted = list_run_ids(AGENCY_ID, COLLECTION_ID)
    if promoted:
        candidate = promoted[-1]
        entry = next((e for e in manifest if e["run_id"] == candidate), None)
        if entry is not None:
            return candidate, entry["csv_path"]
    first = manifest[0]
    return first["run_id"], first["csv_path"]


def run_check(run_id: str, run_by: str, reference_run_id: str | None = None,
              on_step=None) -> tuple[list[dict], str]:
    """Runs the real check chain for one existing Synthetic manifest entry
    into a fresh throwaway location - never the real, permanent
    qa_results/ history directly. Returns (results, tmp_results_dir); the
    caller decides whether to common.promote() it, matching the same
    tmp-dir-first pattern qa_tools/bdm/check_file.py's own --commit
    handling already uses (qa_tools.common.lambda_results_dir).

    This used to do two extra things, both of which REQ-GEN-043 removed
    the NEED for rather than the code for, which is worth saying so the
    absence does not read as an oversight. It backed up and restored
    raw_dir()'s manifest.json around the call, because run_single()
    overwrote it with its own synthetic one (a real bug, found live: a
    manual smoke test corrupted the real data/raw/manifest.json from 176
    entries down to 1). And it passed the immediately-preceding manifest
    entry down as previous_run_id/previous_csv, so the row-count-growth
    check had a previous run to compare against.

    Neither exists now. run_single() writes no manifest, and the
    row-count-growth check finds the preceding arrival from the
    deliveries RECOGNISED on disk - which is the same answer this used
    to hand it, arrived at without anyone declaring it."""
    manifest = load_manifest()
    idx = next((i for i, e in enumerate(manifest) if e["run_id"] == run_id), None)
    if idx is None:
        raise click.ClickException(
            f"No manifest entry for run_id={run_id!r} - run generate-synthetic-data first?")
    entry = manifest[idx]

    if reference_run_id is None:
        reference_run_id, reference_csv = default_reference(manifest)
    else:
        # Resolved against the recognised arrivals, for the reason
        # default_reference() gives - a supplier's filename is not
        # f"{run_id}.csv", so there is nothing to build a path from.
        reference_entry = next((e for e in manifest if e["run_id"] == reference_run_id), None)
        if reference_entry is None:
            raise click.ClickException(
                f"Reference run {reference_run_id!r} isn't among the arrivals recognised on disk - "
                f"run generate-synthetic-data first?")
        reference_csv = reference_entry["csv_path"]

    csv_path = entry["csv_path"]
    tmp_dir = common.new_tmp_results_dir()
    patch_write_qa_result_for_lambda(BDM_MODULES, tmp_dir)

    results = _run_single_preserving_manifest(
        run_id, csv_path, asset_time.local_date(entry["received_at"]).isoformat(),
        reference_run_id, reference_csv, run_by=run_by,
        on_step=on_step,
    )
    return results, tmp_dir


def _run_single_preserving_manifest(*args, **kwargs) -> list[dict]:
    """Calls orchestrate_bdm.run_single(*args, **kwargs).

    THIS USED TO BACK UP AND RESTORE raw_dir()'s manifest.json around
    the call, because run_single() overwrote it with its own synthetic
    one - correct for its Lambda use case, a real collision against the
    batch manifest this CLI's run picker read from.

    REQ-GEN-043 removed the cause rather than the symptom: run_single()
    writes no manifest at all now, and the picker recognises arrivals
    from disk instead of reading one. The wrapper is kept as a single
    named seam for the two callers that share it, and because deleting
    it would spread orchestrate_bdm.run_single() across two more call
    sites for no gain.
    """
    return orchestrate_bdm.run_single(*args, **kwargs)


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
        run_id, csv_path, run_date,
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
    # The delivery it came from, not an injected severity - the picker
    # shows what arrived, and severity is generator bookkeeping the CLI
    # has no business reading (REQ-GEN-043).
    return [f'{e["run_id"]}  ({asset_time.local_date(e["received_at"])}, {e["delivery"]})'
            for e in manifest]


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
