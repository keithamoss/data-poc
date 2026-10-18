"""Every legacy flag an adapter may declare (REQ-QAC-242 criteria 4 and 5).

A LEGACY FLAG PRESERVES DRIFT. The shared modules start from Child
Protection's code, which had grown past Birth Registrations' copy in places,
and the two had drifted in others. Where a collection's recorded output
differs from what the shared code would produce, the difference is kept
behind a flag on that collection's own adapter, so no refactor step changes
either collection's output. Each flag says what it preserves; REQ-PIPE-248
retires them as the shapes are unified.

An adapter declaring a name not here fails `mothman check`'s collections
gate, naming it.
"""
from __future__ import annotations

#: name -> what it preserves.
KNOWN: dict[str, str] = {
    "evidently.volume_from_drift_frame": (
        "the one volume check is counted by Evidently's RowCount over the drift "
        "frame, with that snapshot kept in the raw output as `row_count`; a reference "
        "with no recorded count is counted from its rows; a reference of zero rows "
        "reads as no drop; and the result sits on the check's own column rather than "
        "the table - Birth Registrations' single-table copy."),
    "stage.stamps_run_columns": (
        "every staged row is stamped with `run_id` and `run_date` columns, which "
        "Birth Registrations' dbt model selects and Child Protection's tables have "
        "never carried."),
    "stats.single_table_shape": (
        "dataset statistics carry one `row_count` rather than `row_counts` by table, "
        "value counts and aggregates keyed by column rather than `table.column`, one "
        "`arrival` rather than one per table, and an empty record with a null count "
        "when the table cannot be read - Birth Registrations' single-table shape."),
    "stats.rows_by_run_id": (
        "every statistic is scoped by the `run_id` column each staged row carries, "
        "as well as by the run's view schema."),
    "stats.arrival_after_registration": (
        "the earliest extract is the earliest among rows extracted on or after their "
        "registration date, falling back to the earliest of all."),
    "results.single_dataset_header": (
        "the results file names its one dataset under `dataset` rather than the "
        "collection under `collection` and its datasets under `datasets`."),
    "orchestrate.entry_carries_csv_path": (
        "each run entry, and so the batch's results file, also names the arrival's "
        "file, or its delivery directory where two files contest the dataset."),
}
