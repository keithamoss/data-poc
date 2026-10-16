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
    "datacontract.reads_unreadable_tables": (
        "datacontract-cli's rules are recorded even over a table the run has no view "
        "for, and nothing is noted as left out - Birth Registrations' copy never "
        "had REQ-PIPE-078's left-out handling."),
    "soda.reads_unreadable_tables": (
        "Soda is handed every check whatever the run can read, and nothing is noted "
        "as left out - REQ-PIPE-078's handling, as for datacontract-cli above."),
    "soda.scope_suffix": (
        "a generically named Soda check is recorded as `<metric>[<filter or all>]` "
        "rather than `<metric>` - the name Birth Registrations' checks have always "
        "carried, which the dashboard keys a check on."),
    "soda.named_check_value_is_invalid_count": (
        "a custom-named check with a routed column records its own value as the "
        "invalid-row count, as Birth Registrations' copy did and Child Protection's "
        "never has."),
    "evidently.reads_unreadable_tables": (
        "the drift check is always evaluated, whether or not the run can read its "
        "table, and nothing is noted as left out."),
    "evidently.volume_from_drift_frame": (
        "the one volume check is counted by Evidently's RowCount over the drift "
        "frame, with that snapshot kept in the raw output as `row_count`; a reference "
        "with no recorded count is counted from its rows; a reference of zero rows "
        "reads as no drop; and the result sits on the check's own column rather than "
        "the table - Birth Registrations' single-table copy."),
    "dbt.no_built_model_guard": (
        "the table's row count, the audit recount and the failing-row samples are "
        "taken whether or not dbt built the model - Birth Registrations' copy never "
        "checked."),
    "dbt.audits_skipped_tests": (
        "a test dbt reports as skipped is still recounted from its audit table; only "
        "an errored one is not."),
    "dbt.no_left_out_note": (
        "tests left out for an unreadable model are not noted as left out "
        "(REQ-PIPE-115 criterion 17) - the models are still excluded."),
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
    "stats.zero_counts_kept": (
        "a value-count distribution lists every known value, zeros included; Child "
        "Protection's lists only the values present."),
    "stats.arrival_after_registration": (
        "the earliest extract is the earliest among rows extracted on or after their "
        "registration date, falling back to the earliest of all."),
}
