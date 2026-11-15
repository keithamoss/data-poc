"""Drift arithmetic (REQ-PIPE-380 criterion 10, Q1 of 2026-11-14, SETTLED by
Keith): a collection's declared drift checks, their bands, the value-count
folding, and the PSI between two value-count distributions - the one copy,
which the real Evidently check (qa_tools/tools/run_evidently.py), the stats
recorder (qa_tools/tools/dataset_stats.py) and the generator's drift
planning (the Linkage Products provider) all call, so a planned verdict is
computed exactly as the check computes it.

THE OTHER HALF IS qa_tools/common/evidently_common.py, which reads a run's
recorded stats through qa_results_reader (criterion 11); this module reads
committed configuration and the values its callers pass, nothing else.
pandas and Evidently are imported inside the functions that need them, so
importing asset_model/ needs neither (criterion 8, NFR PORTABILITY).
"""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent

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

    Each check is found by its `method`: one or more `psi` checks, on one
    dataset or several (Emergency Department declares two on one,
    REQ-QAC-231; Linkage Products one on each geocoding table), and a
    `row_drop` check per table, whose dataset is the check id's fourth
    segment (asset.agency.collection.dataset...) and whose table is that
    dataset's in the hierarchy."""
    from asset_model import check_lifecycle, collections, hierarchy

    coll = collections.by_id(collection_id)
    rel = coll.check_file("evidently")
    checks = check_lifecycle.load_evidently_checks(ROOT / rel)
    psi = [i for i, m in checks.items() if m.get("method") == "psi"]
    if not checks:
        # A COLLECTION MAY DECLARE NO EVIDENTLY CHECK (REQ-QAC-333 criterion
        # 5: Linkage Products' file is present and empty) - its runs then ask
        # Evidently for nothing, rather than failing the run. A file that
        # declares checks but no drift check is still refused: that is a slip.
        return EvidentlyChecks({}, (), {})
    if not psi:
        raise ValueError(f"{rel}: expected at least one psi check, found none")
    # DRIFT CHECKS ON SEVERAL DATASETS (REQ-QAC-297 criterion 11): each run
    # evaluates its OWN dataset's, against that dataset's last promoted
    # supply, which is the reference orchestrate already resolves per run
    # (REQ-PIPE-105) - so two datasets no longer need one shared reference.
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


#: What every value a column does not declare is counted under.
INVALID_CODE = "(invalid code)"


def fold_value_counts(pairs, known) -> list[list]:
    """`[[value, count], ...]` as dataset_stats records it, from any
    `(value, count)` pairs: every KNOWN value's count, zeros included
    (REQ-QAC-247), in declared order, then every other value folded into one
    '(invalid code)' count where there is any. The one copy - the recorded
    stats and the generator's drift planning (REQ-GEN-295 criterion 7 as
    amended) both fold through it, so a planned reference has the recorded
    one's shape."""
    counts = {k: 0 for k in known}
    other = 0
    for value, n in pairs:
        if value in counts:
            counts[value] += n
        else:
            other += n
    out = [[k, v] for k, v in counts.items()]
    if other:
        out.append([INVALID_CODE, other])
    return out


def excluding(frame, entry: dict):
    """A drift frame without the values the check declares excluded, from
    reference and current alike (REQ-QAC-297 criterion 11) - so a value
    another check already measures, such as an unplaced level, does not raise
    a second alarm for one fault. Generic: any column, any values. The one
    copy: the real check (run_evidently) and the generator's drift planning
    (psi_of_counts) both exclude through it."""
    excluded = [str(v) for v in (entry.get("exclude_values") or ())]
    if not excluded:
        return frame
    column = entry["column"]
    return frame[~frame[column].astype(str).isin(excluded)].reset_index(drop=True)


def psi_of_counts(current_counts, reference_counts, entry: dict) -> tuple[float | None, str]:
    """(PSI, status) of one drift check from two value-count distributions,
    `[[value, count], ...]` - the inputs the real check reads (the reference
    is rebuilt from its recorded value counts, exactly; see below), through
    the same exclusion, the same Evidently PSI and the same thresholds
    (status_for over the check's own entry). REQ-GEN-295 criterion 7 as
    amended 2026-11-02 (Keith, morning report A2): the generator plans a
    geocoding file's drift verdict with this, so it predicts the check from
    what the check reads. NO_REFERENCE where either side holds nothing to
    compare, as the real check records an empty current supply."""
    if reference_counts is None:
        return None, NO_REFERENCE
    column = entry["column"]
    current = excluding(frame_from_value_counts(current_counts, column), entry)
    reference = excluding(frame_from_value_counts(reference_counts, column), entry)
    if not len(current) or not len(reference):
        return None, NO_REFERENCE
    psi, _snapshot = compute_psi(current, reference, column)
    return psi, status_for(psi, entry)


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
