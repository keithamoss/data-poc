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
"""
from __future__ import annotations
import argparse
import sys
import tempfile

from qa_tools.common.lambda_results_dir import BDM_MODULES, patch_write_qa_result_for_lambda
from qa_tools.common.local_check import copy_into, format_report, run_id_from_path
from . import build_per_run_warehouses, orchestrate_bdm


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("csv_path", help="The Birth Registrations CSV to check - wherever you already downloaded it.")
    parser.add_argument("--reference-csv", required=True,
                         help="A known-good CSV to compare distribution drift against (e.g. last accepted delivery).")
    parser.add_argument("--run-date", default=None, help="Defaults to today (UTC).")
    parser.add_argument("--run-id", default=None, help="Defaults to a generated id from the filename + timestamp.")
    parser.add_argument("--commit", action="store_true",
                         help="Write this run into the real, permanent qa_results/ git history "
                              "(default: local-only, throwaway).")
    args = parser.parse_args(argv)

    from datetime import datetime, timezone
    run_date = args.run_date or datetime.now(timezone.utc).date().isoformat()
    run_id = args.run_id or run_id_from_path(args.csv_path)
    reference_run_id = run_id_from_path(args.reference_csv, prefix="ref")
    reference_csv_filename = f"{reference_run_id}.csv"
    copy_into(args.reference_csv, build_per_run_warehouses.RAW_DIR, reference_csv_filename)

    if not args.commit:
        with tempfile.TemporaryDirectory() as tmp_dir:
            patch_write_qa_result_for_lambda(BDM_MODULES, tmp_dir)
            results = orchestrate_bdm.run_single(run_id, args.csv_path, run_date, None,
                                                  reference_run_id=reference_run_id,
                                                  reference_csv=reference_csv_filename)
    else:
        results = orchestrate_bdm.run_single(run_id, args.csv_path, run_date, None,
                                              reference_run_id=reference_run_id, reference_csv=reference_csv_filename)

    print(format_report(results, run_id))
    if not args.commit:
        print("\n(local-only check - not written to qa_results/ history; re-run with --commit to keep it)")

    return 1 if any(r["status"] in ("fail", "error") for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
