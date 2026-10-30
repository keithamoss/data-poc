"""
Tool-generic Evidently PSI-drift computation, shared by
qa_tools/tools/run_evidently.py. The actual reference run,
comparison column, and any dataset-specific extra checks (e.g. birth
registrations' row-count-growth check, which Child Protection doesn't
have) stay in each dataset's own file - see plans/qa-pipeline.md #84.
"""
from __future__ import annotations

from typing import NamedTuple

ENGINE_TAG = "Evidently 0.7"

# THE BANDS LIVE IN EACH CHECK'S OWN ENTRY (REQ-QAC-223 criterion 3).
# They used to be four module constants shared by every Evidently check,
# which the changelog gate could not see: a definition hash covers a
# check's CHECK_LIFECYCLE entry, and a band changed here moved every check's
# verdicts without changing any of them. Each entry now carries its column,
# its method and its warn/fail bands as literals - the same values in every
# entry today (Keith, 2026-09-28: Child Protection mirrors Birth
# Registrations' bands), duplicated deliberately so that one check's band
# can change, with its own changelog entry, without moving the others.
# Evidently's own DataDriftPreset carries one drift/no-drift threshold
# (0.1); the three-way band is this project's convention.


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


class EvidentlyChecks(NamedTuple):
    """One collection's Evidently checks, as its check file declares them."""
    checks: dict          # {check_id: metadata}
    psi: tuple            # the drift checks' ids, in file order (REQ-QAC-231)
    row_drop: dict        # {table: the row-drop check's id}


def collection_checks(collection_id: str) -> EvidentlyChecks:
    """A collection's Evidently checks, read from its own check file
    (REQ-QAC-241 criterion 10) - no check id is a Python constant.

    Each check is found by its `method`: one or more `psi` checks, all on
    one dataset (Emergency Department declares two, REQ-QAC-231), and a
    `row_drop` check per table, whose dataset is the check id's fourth
    segment (asset.agency.collection.dataset...) and whose table is that
    dataset's in the hierarchy."""
    from pathlib import Path

    from qa_tools import collections
    from qa_tools.common import check_lifecycle, hierarchy

    coll = collections.by_id(collection_id)
    rel = coll.check_file("evidently")
    checks = check_lifecycle.load_evidently_checks(Path(__file__).resolve().parents[2] / rel)
    psi = [i for i, m in checks.items() if m.get("method") == "psi"]
    if not checks:
        # A COLLECTION MAY DECLARE NO EVIDENTLY CHECK (REQ-QAC-333 criterion
        # 5: Linkage Products' file is present and empty) - its runs then ask
        # Evidently for nothing, rather than failing the run.
        return EvidentlyChecks({}, (), {})
    if not psi:
        raise ValueError(f"{rel}: expected at least one psi check, found none")
    datasets = {i.split(".")[3] for i in psi}
    if len(datasets) != 1:
        # ONE DRIFT DATASET: its last promoted supply is the run's reference
        # (orchestrate's reference choice), so drift checks on two datasets
        # would each need a reference of their own.
        raise ValueError(f"{rel}: every psi check must be on one dataset, found {sorted(datasets)}")
    row_drop = {hierarchy.dataset(i.split(".")[3]).table: i
                for i, m in checks.items() if m.get("method") == "row_drop"}
    return EvidentlyChecks(checks, tuple(psi), row_drop)


def status_for(value: float, entry: dict) -> str:
    """The band `value` falls in under one check's own entry - its
    `warn_threshold` and `fail_threshold`, each tripped on a strict `>`.

    For "psi" the value is the PSI itself. For "row_drop" it is the
    proportional DROP, (reference - current) / reference: POSITIVE when the
    supply shrank, so growth never trips it ("some reduction in a daily
    refresh is fine", Keith, 2026-09-28; only a large fall matters).

    `is_reference` WAS REMOVED 2026-09-29 with REQ-QAC-108: the reference is
    always an EARLIER period's supply, and "no reference at all" is answered
    by NO_REFERENCE before this is reached.
    """
    if value > entry["fail_threshold"]:
        return "fail"
    if value > entry["warn_threshold"]:
        return "warn"
    return "pass"


def recorded_row_counts(agency: str, collection: str, run_id: str) -> dict | None:
    """One run's recorded per-table row counts, or None - measured from the
    warehouse when that run was checked, never from the generator's own
    bookkeeping. Every collection records `row_counts` by table since
    REQ-PIPE-248 (Birth Registrations recorded one `row_count`)."""
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
