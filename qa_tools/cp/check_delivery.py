"""
On-demand CLI: run the real QA check chain (dbt-core/Soda Core/
datacontract-cli/Evidently, including the cross-table referential-
integrity checks) against a single, already-downloaded Child Protection
delivery - the CP counterpart to qa_tools/bdm/check_file.py. See that
module's own docstring for the full Thread A scoping account
(plans/running-thoughts.md #5, 2026-09-19), including why this is built
with Click rather than argparse.

Run as `uv run python3 -m qa_tools.cp.check_delivery <folder> --reference-folder <known-good-folder>`,
where <folder> contains all 6 real CP table CSVs (cp_clients.csv,
cp_notifications.csv, cp_investigations.csv, cp_placements.csv,
cp_carers.csv, cp_case_workers.csv) - the same shape a manual S3/local
download of one CP delivery already has. Unlike BDM's single file, CP's
cross-table checks need every table loaded before they can run at all
(the same real dependency-ordering requirement Thread B's completion-
tracker exists to enforce for the automated path) - this CLI loads all
6 up front since a person running it by hand already has the whole
delivery in one folder, there's no "wait for the rest to arrive" case
here the way there is for Lambda-triggered per-file arrivals.

Defaults to a throwaway, local-only check - pass --commit to write this
run into the real, permanent qa_results/ git history instead.

A real git-identity bug (found via a genuinely red CI run, not local
`uv run pytest` - see qa_tools/bdm/check_file.py's own docstring for
the full account) is fixed the same way here: a real git identity is
only required for --commit; the throwaway path gets a real, honest
"not persisted" attribution instead.
"""
from __future__ import annotations
import os
import tempfile
from datetime import datetime, timezone

import click

from qa_tools.common.git_identity import get_run_by
from qa_tools.common.lambda_results_dir import CP_MODULES, patch_write_qa_result_for_lambda
from qa_tools.common.local_check import format_report, run_id_from_path
from . import build_cp_warehouses, orchestrate_cp

CP_TABLE_NAMES = ["cp_clients", "cp_notifications", "cp_investigations", "cp_placements", "cp_carers",
                   "cp_case_workers"]


def _load_delivery(folder: str, run_id: str) -> None:
    missing = [t for t in CP_TABLE_NAMES if not os.path.isfile(os.path.join(folder, f"{t}.csv"))]
    if missing:
        raise click.ClickException(
            f"{folder} is missing: {', '.join(f'{t}.csv' for t in missing)} - "
            f"a CP delivery needs all 6 real tables, the cross-table checks can't run on a partial set")
    # out_dir/raw_dir passed explicitly, read off the module attributes at
    # call time - the same real bug orchestrate_bdm.run_single() hit and
    # documents in its own comment: add_table_to_run()'s own out_dir/
    # raw_dir default parameter values are bound once, at import time, so
    # a caller (a test, or anyone else) monkeypatching build_cp_warehouses.
    # OUT_DIR/CP_RAW_DIR afterwards would otherwise be silently ignored.
    for table in CP_TABLE_NAMES:
        build_cp_warehouses.add_table_to_run(run_id, table, os.path.join(folder, f"{table}.csv"),
                                              out_dir=build_cp_warehouses.OUT_DIR,
                                              raw_dir=build_cp_warehouses.CP_RAW_DIR)


@click.command()
@click.argument("folder", type=click.Path(exists=True, file_okay=False))
@click.option("--reference-folder", required=True, type=click.Path(exists=True, file_okay=False),
              help="A known-good delivery folder (same 6-table shape) to compare distribution drift against.")
@click.option("--run-date", default=None, help="Defaults to today (UTC).")
@click.option("--run-id", "run_id", default=None, help="Defaults to a generated id from the folder name + timestamp.")
@click.option("--commit", is_flag=True,
              help="Write this run into the real, permanent qa_results/ git history "
                   "(default: local-only, throwaway).")
def main(folder: str, reference_folder: str, run_date: str | None, run_id: str | None, commit: bool) -> None:
    """Run the real QA check chain against FOLDER - a Child Protection delivery (all 6 tables) you've already
    downloaded."""
    run_date = run_date or datetime.now(timezone.utc).date().isoformat()
    run_id = run_id or run_id_from_path(folder)
    reference_run_id = run_id_from_path(reference_folder, prefix="ref")

    _load_delivery(reference_folder, reference_run_id)
    _load_delivery(folder, run_id)

    entry = {"run_id": run_id, "run_date": run_date, "dirty_severity": None}

    if not commit:
        with tempfile.TemporaryDirectory() as tmp_dir:
            patch_write_qa_result_for_lambda(CP_MODULES, tmp_dir)
            results = orchestrate_cp.run_single(entry, reference_run_id=reference_run_id,
                                                 run_by="local-check:not-persisted")
    else:
        results = orchestrate_cp.run_single(entry, reference_run_id=reference_run_id, run_by=get_run_by())

    click.echo(format_report(results, run_id))
    if not commit:
        click.echo("\n(local-only check - not written to qa_results/ history; re-run with --commit to keep it)")

    raise SystemExit(1 if any(r["status"] in ("fail", "error") for r in results) else 0)


if __name__ == "__main__":
    main()
