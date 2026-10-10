"""
Tool-generic Evidently PSI-drift computation, shared by
qa_tools/bdm/run_evidently_bdm.py and
qa_tools/cp/run_evidently_cp.py. The actual reference run,
comparison column, and any dataset-specific extra checks (e.g. birth
registrations' row-count-growth check, which Child Protection doesn't
have) stay in each dataset's own file - see plans/qa-pipeline.md #84.
"""
from __future__ import annotations

ENGINE_TAG = "Evidently 0.7"

# same pass/warn/fail bands both existing datasets use, applied to the
# real PSI value Evidently computes - Evidently's own DataDriftPreset only
# carries one drift/no-drift threshold (0.1) by default, not a three-way
# band, so the warn/fail split here is this project's convention, not
# Evidently's.
WARN_THRESHOLD = 0.10
FAIL_THRESHOLD = 0.25


#: What a drift or volume check reports when it has nothing to measure
#: against (REQ-QAC-108 criterion 5, 2026-09-29). It is the dashboard's
#: existing quiet word rather than a new one, and the point is entirely
#: what it is NOT: a check whose reference period does not exist has
#: measured nothing, and "pass" would say the supply was compared and
#: found fine.
#:
#: It can never win a rollup - dataset_status orders it below green - so
#: one unmeasurable drift check does not hold up a dataset whose real
#: checks are green. A dataset whose EVERY contributing check is quiet
#: rolls up quiet, which promotion.status_of() refuses.
NO_REFERENCE = "nodata"


def status_for_psi(psi: float) -> str:
    """The band this PSI value falls in.

    `is_reference` WAS REMOVED 2026-09-29 with REQ-QAC-108. It returned
    "pass" when a run was its own reference, which was reachable only
    because the reference was a fixed run the batch chose once - the
    thing criterion 4 forbids. The reference is now always an EARLIER
    period's supply, so a run can never be its own, and the "no
    reference at all" case is answered by NO_REFERENCE before this
    function is reached rather than by a parameter inside it.
    """
    if psi > FAIL_THRESHOLD:
        return "fail"
    if psi > WARN_THRESHOLD:
        return "warn"
    return "pass"


# HOW BOTH COLLECTIONS JUDGE VOLUME (REQ-QAC-108 criterion 1). These
# were Birth Registrations' own constants; they moved here so Child
# Protection's six datasets could share them rather than acquire a
# second convention - which is the criterion's own reason for existing,
# in its own words, "so that both collections judge volume the same
# way". Keith's call on the numbers, 2026-09-28: mirror the bands
# Birth Registrations already had rather than invent a second set.
#
# A DROP ONLY, NOT ANY CHANGE. "Some reduction in a daily refresh is
# fine" (Keith), so only a genuinely large fall trips this - and growth
# never does, because a supply arriving bigger than the last one is the
# ordinary state of a table that is accumulating.
WARN_ROW_DROP = 0.10
FAIL_ROW_DROP = 0.25


def status_for_row_drop(rate_drop: float) -> str:
    """The band a proportional drop falls in.

    `rate_drop` is (reference - current) / reference, so it is POSITIVE
    when the supply shrank and negative when it grew.
    """
    if rate_drop > FAIL_ROW_DROP:
        return "fail"
    if rate_drop > WARN_ROW_DROP:
        return "warn"
    return "pass"


def recorded_row_counts(agency: str, collection: str, run_id: str) -> dict | None:
    """One run's recorded per-table row counts, or None.

    The plural counterpart to recorded_row_count(): Child Protection's
    dataset_stats records `row_counts` per table, where Birth
    Registrations, being one table, records a single `row_count`.
    """
    stats = recorded_stats(agency, collection, run_id)
    if not stats:
        return None
    return stats.get("row_counts") or None


def compute_psi(current_df, reference_df, column: str) -> tuple[float | None, dict]:
    """Returns (psi_value, raw_snapshot) - the raw Evidently snapshot dict
    is the real native tool output, committed as-is to qa_results/ by each
    caller (plans/publishing-and-history.md Thread B) - this function
    used to discard it, returning only the extracted float."""
    from evidently import Report
    from evidently.presets import DataDriftPreset

    report = Report(metrics=[DataDriftPreset(columns=[column], cat_method="psi")])
    snapshot = report.run(current_df, reference_df)
    result = snapshot.dict()
    psi_value = None
    for m in result["metrics"]:
        if m["metric_name"].startswith(f"ValueDrift(column={column}"):
            psi_value = m["value"]
            break
    return psi_value, result


# ---------------------------------------------------------------------------
# A drift reference that does not require the reference run's ROWS
# (REQ-QAC-088 criteria 2 and 3, 2026-09-27)
#
# Evidently was the last tool reading the supplier's CSV rather than the
# warehouse. The obvious fix - find the reference run's rows and read
# them - looked blocked: a run's view schema is dropped when its run
# ends, and once promotion exists those rows live in a period schema
# rather than in staging. Keith pushed back on that being a blocker, and
# he was right, because it is the wrong question.
#
# The reference DISTRIBUTION is already recorded. dataset_stats writes
# `value_counts` and `row_count` for every run, computed at the one
# point in the pipeline with a legitimate live connection - which is
# exactly the pattern that module exists for. So the reference never
# needs to be FOUND; it was written down when writing it down was cheap.
# Only the CURRENT run needs rows, and its own view schema is open while
# it is being checked.
#
# AND THE RECONSTRUCTION IS EXACT, not an approximation, which is the
# part worth stating because it sounds like it should not be. PSI over a
# CATEGORICAL column depends only on the category proportions, so
# expanding recorded counts back into rows reproduces the reference
# distribution precisely. Measured against real Evidently 0.7.23: PSI
# from real reference rows and PSI from a reference rebuilt out of
# value_counts came back bit-identical.
#
# THE LIMIT, and it fails loudly rather than silently approximating:
# this is exact for a categorical column only. A numeric column's drift
# needs binned histograms, and a value-count distribution is not one -
# so if a numeric drift check is ever added, dataset_stats must record
# fixed-bin histograms for it and frame_from_value_counts must refuse
# rather than doing something defensible-looking.
# ---------------------------------------------------------------------------

def recorded_stats(agency: str, collection: str, run_id: str) -> dict | None:
    """One run's recorded `dataset_stats`, or None if it has none."""
    from qa_tools.common import qa_results_reader

    envelope = qa_results_reader.read_raw(agency, collection, run_id, "dataset_stats")
    if not envelope:
        return None
    return envelope.get("raw_output") or None


def reference_value_counts(agency: str, collection: str, run_id: str,
                            column: str) -> list[list] | None:
    """The recorded `[[value, count], ...]` for one column of one run."""
    stats = recorded_stats(agency, collection, run_id)
    if not stats:
        return None
    return (stats.get("value_counts") or {}).get(column)


def recorded_row_count(agency: str, collection: str, run_id: str) -> int | None:
    """One run's recorded row count - measured from the warehouse when
    that run was checked, never from the generator's own bookkeeping."""
    stats = recorded_stats(agency, collection, run_id)
    return None if not stats else stats.get("row_count")


def frame_from_value_counts(value_counts, column: str):
    """Rebuild a single-column frame whose distribution matches the
    recorded counts exactly.

    Refuses a non-integer count rather than coercing: a fractional or
    missing count means the recorded stats are not what this assumes,
    and quietly rounding it would put a wrong number into a drift
    verdict, which is the direction that does not announce itself.
    """
    import pandas as pd

    rows: list = []
    for entry in value_counts or []:
        try:
            value, count = entry
            count = int(count)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"recorded value_counts for {column!r} is not [[value, count], ...]: "
                f"{entry!r}") from exc
        if count < 0:
            raise ValueError(f"negative recorded count for {column}={value!r}: {count}")
        rows.extend([value] * count)
    return pd.DataFrame({column: rows})
