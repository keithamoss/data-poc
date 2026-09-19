"""
Shared logic for the mothman CLI's Local files QA source mode
(`cli/bdm.py`'s `run_check_local_file()`, `cli/cp.py`'s
`run_check_local_folder()`) - Thread A of plans/running-thoughts.md #5
("fit into today's actual workflow"), scoped 2026-09-19 with Keith:
staff already pull data down from S3/local storage manually today and
are technical (data engineers/analysts comfortable with a CLI) - the
real gap isn't an automated trigger (that's Thread B), it's a fast,
on-demand way to run this pipeline's real QA checks against whatever
they've just downloaded, before they use it. Reuses orchestrate_bdm.
run_single()/orchestrate_cp.run_single() - the exact same single-arrival
entry points Thread B built for Lambda - invoked locally instead of from
an S3 event.

Originally the shared logic behind two standalone CLIs
(`qa_tools/bdm/check_file.py`/`qa_tools/cp/check_delivery.py`) - both
retired (plans/tooling.md #1 Phase 2, 2026-09-19) once mothman's own
Local files source mode folded their logic in directly; run_id_from_path/
copy_into outlived them unchanged, just called from cli/bdm.py/cli/cp.py
now instead. Their own format_report() (a plain-text terminal report) did
not outlive them - cli/bdm.py's/cli/cp.py's own report_table() (a richer,
rich.table.Table-rendered report, shared with the Synthetic source mode
these two never had) replaced it, so it was deleted rather than kept
unused.

Ad hoc runs default to NOT touching the real, permanent qa_results/ git
history (Keith's own explicit call, 2026-09-19: "throwaway by default,
--commit to keep it") - a person sanity-checking their own manual pull
usually isn't trying to log an official QA event, and doing so by
default risked cluttering committed history with exploratory/duplicate
runs. `--commit` opts a specific run into the real history instead,
using qa_tools.common.git_identity.get_run_by() for real attribution
same as every other real run.
"""
from __future__ import annotations
import os
from datetime import datetime, timezone


def run_id_from_path(path: str, prefix: str = "adhoc") -> str:
    """A real, sortable, collision-resistant run_id for an ad hoc local
    check - not a synthetic manifest entry, so there's no existing
    run_id to reuse. Includes the source file/folder's own name (for a
    human skimming qa_results/ later, if --commit was used) and a real
    UTC timestamp (collision-resistant across repeat runs against the
    same file, e.g. re-checking after a fix)."""
    stem = os.path.splitext(os.path.basename(path.rstrip("/")))[0]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{stem}_{timestamp}"


def copy_into(src_path: str, dest_dir: str, dest_filename: str) -> str:
    """Copies src_path to dest_dir/dest_filename, a no-op if it's
    already there (same idempotency orchestrate_bdm.run_single() already
    relies on for its own arrived-file copy)."""
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, dest_filename)
    if os.path.abspath(src_path) != os.path.abspath(dest_path):
        with open(src_path, "rb") as src, open(dest_path, "wb") as dst:
            dst.write(src.read())
    return dest_path
