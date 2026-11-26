"""
What of the Evidently drift check reads RECORDED RESULTS: a run's recorded
dataset_stats, its row counts and a column's recorded value counts - the
drift reference, which never needs the reference run's rows (see below).

THE DRIFT ARITHMETIC IS asset_model/drift.py (REQ-PIPE-380 criterion 10):
the PSI, the bands, the value-count folding and a collection's declared
drift checks are shared with the generator, which plans a drift verdict
from the same code. The cut sits at qa_results_reader: reading what a run
recorded is the real pipeline's, so this half stays here (criterion 11) and
the drift module reads only configuration and the values its callers pass.
"""
from __future__ import annotations

ENGINE_TAG = "Evidently 0.7"


def recorded_row_counts(agency: str, collection: str, run_id: str) -> dict | None:
    """One run's recorded per-table row counts, or None - measured from the
    warehouse when that run was checked, never from the generator's own
    bookkeeping. Every collection records `row_counts` by table since
    REQ-PIPE-248 (Birth Registrations recorded one `row_count`)."""
    stats = recorded_stats(agency, collection, run_id)
    if not stats:
        return None
    return stats.get("row_counts") or None


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
