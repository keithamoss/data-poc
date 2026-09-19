"""
On-demand CLI: run the real QA check chain (dbt-core/Soda Core/
datacontract-cli/Evidently) against a single, already-downloaded Birth
Registrations CSV - Thread A of plans/running-thoughts.md #5, scoped
2026-09-19: staff already pull data from S3/local storage manually
today and are comfortable with a CLI - this fits that existing motion
(check before you use it) rather than replacing it. Reuses
orchestrate_bdm.run_single() - the same entry point Thread B's Lambda
handler calls, invoked locally instead.

Run as `uv run python3 -m qa_tools.bdm.check_file <csv_path> --reference-csv <known-good.csv>`.
A distribution-drift comparison needs a real reference file - there's no
synthetic manifest[0] to fall back on for a real, manually-downloaded
file, so --reference-csv is required, not defaulted (see orchestrate_bdm.
run_single()'s own docstring for the same open question in Thread B's
Lambda context).

Defaults to a throwaway, local-only check (Keith's own explicit call,
2026-09-19) - pass --commit to write this run into the real, permanent
qa_results/ git history instead.

Built with Click (Keith's own explicit ask, 2026-09-19) rather than
argparse - real, validated path arguments (click.Path(exists=True)
rejects a typo'd path before any real tool ever runs, not partway
through) and a real exit-code contract Click already handles correctly
under both direct invocation and click.testing.CliRunner (tests/
test_check_cli.py).
"""
from __future__ import annotations
import tempfile
from datetime import datetime, timezone

import click

from qa_tools.common.lambda_results_dir import BDM_MODULES, patch_write_qa_result_for_lambda
from qa_tools.common.local_check import copy_into, format_report, run_id_from_path
from . import build_per_run_warehouses, orchestrate_bdm


@click.command()
@click.argument("csv_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--reference-csv", required=True, type=click.Path(exists=True, dir_okay=False),
              help="A known-good CSV to compare distribution drift against (e.g. last accepted delivery).")
@click.option("--run-date", default=None, help="Defaults to today (UTC).")
@click.option("--run-id", "run_id", default=None, help="Defaults to a generated id from the filename + timestamp.")
@click.option("--commit", is_flag=True,
              help="Write this run into the real, permanent qa_results/ git history "
                   "(default: local-only, throwaway).")
def main(csv_path: str, reference_csv: str, run_date: str | None, run_id: str | None, commit: bool) -> None:
    """Run the real QA check chain against CSV_PATH - a Birth Registrations file you've already downloaded."""
    run_date = run_date or datetime.now(timezone.utc).date().isoformat()
    run_id = run_id or run_id_from_path(csv_path)
    reference_run_id = run_id_from_path(reference_csv, prefix="ref")
    reference_csv_filename = f"{reference_run_id}.csv"
    copy_into(reference_csv, build_per_run_warehouses.RAW_DIR, reference_csv_filename)

    if not commit:
        with tempfile.TemporaryDirectory() as tmp_dir:
            patch_write_qa_result_for_lambda(BDM_MODULES, tmp_dir)
            results = orchestrate_bdm.run_single(run_id, csv_path, run_date, None,
                                                  reference_run_id=reference_run_id,
                                                  reference_csv=reference_csv_filename)
    else:
        results = orchestrate_bdm.run_single(run_id, csv_path, run_date, None,
                                              reference_run_id=reference_run_id, reference_csv=reference_csv_filename)

    click.echo(format_report(results, run_id))
    if not commit:
        click.echo("\n(local-only check - not written to qa_results/ history; re-run with --commit to keep it)")

    raise SystemExit(1 if any(r["status"] in ("fail", "error") for r in results) else 0)


if __name__ == "__main__":
    main()
