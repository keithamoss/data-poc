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

from qa_tools.common.supply_db import normalise_ident_part


#: How much of a source filename a run id carries.
#:
#: FIFTEEN IS ARITHMETIC, not taste. A staged table is named
#: `<table>__<arrival>` with an optional `__<ordinal>`, inside
#: PostgreSQL's 63-byte identifier limit. This asset's longest logical
#: table is `birth_registrations` (19), so the arrival segment has
#: 63 - 19 - 2 - 3 = 39 bytes. A run id costs `adhoc_` (6) plus `_`
#: plus a 16-character timestamp before any stem at all, leaving 16 -
#: and 15 is that with a byte of margin.
#:
#: Twenty was the first answer and was one byte too many: it produced
#: a 64-byte table name for exactly the common case, so the digest in
#: supply_db.arrival_segment() would have fired on every ad-hoc check
#: of a normally-named delivery, which is the unreadability this was
#: meant to remove.
MAX_STEM = 15


def run_id_from_path(path: str, prefix: str = "adhoc") -> str:
    """A real, sortable, collision-resistant run_id for an ad hoc local
    check - not a synthetic manifest entry, so there's no existing
    run_id to reuse. Includes the source file/folder's own name (for a
    human skimming qa_results/ later, if --commit was used) and a real
    UTC timestamp (collision-resistant across repeat runs against the
    same file, e.g. re-checking after a fix).

    NORMALISED HERE, because this is the one place an unsafe name can
    enter the system (2026-09-27). Everywhere else a run id is minted
    `run_001`-style and is a safe identifier by construction; this one
    is built from a filename a person chose, so it can carry anything -
    `Births Jan.csv`, an accented character, a hyphen - and the
    timestamp format contributes an uppercase `T` and `Z` of its own.

    A run id becomes a PostgreSQL schema name (supply_db.run_schema),
    and dbt and Soda write that name into their own SQL unquoted while
    PostgreSQL folds an unquoted identifier to lower case. So an unsafe
    id produces a schema those tools cannot see, which surfaces as every
    check in the run failing on a missing relation.

    Normalising at the source rather than encoding at the point of use
    is what keeps the schema name readable and exactly reversible -
    `adhoc_births_jan_20260927t024200z`, not
    `adhoc_births_5f_jan_...`. supply_db._ident() refuses anything
    unsafe, so if this normalisation is ever wrong the failure is loud
    and names this function.

    THE STEM IS CAPPED (Keith, 2026-09-27: "why are the ad hoc ids so
    long?"). It used to be the whole filename, which was thirty of the
    fifty-three characters in
    `adhoc_birth_registrations_2026_09_20_20260927t041329z` - and for
    this project's own deliveries that filename already carries the
    dataset name and a date, so the staged table name said
    `birth_registrations` twice, carried two dates, and came to 74
    bytes against PostgreSQL's 63-byte limit.

    THE STEM RATHER THAN THE WHOLE ID, because capping the id would
    eat the timestamp, and the timestamp is what makes a repeat check
    of the same file a different run. What the cap costs is some
    distinctness between two files whose names agree for the first
    twenty characters AND are checked in the same second; the prefix
    already separates the two files one command handles, so that is a
    remote collision rather than a live one.

    supply_db.arrival_segment() still bounds a long id with a digest
    if one arrives from elsewhere - this stops the ordinary case
    needing it.
    """
    stem = os.path.splitext(os.path.basename(path.rstrip("/")))[0]
    # A NAME WITH NOTHING USABLE IN IT IS NOT AN ERROR HERE. `!!!.csv`
    # is a file somebody can really hand this, and the timestamp alone
    # is a perfectly good run id - normalise_ident_part() raises on an
    # empty result because its other caller has no such fallback.
    try:
        stem = normalise_ident_part(stem)[:MAX_STEM].strip("_")
    except ValueError:
        stem = ""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    parts = [prefix, stem, timestamp] if stem else [prefix, timestamp]
    return normalise_ident_part("_".join(parts))




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
