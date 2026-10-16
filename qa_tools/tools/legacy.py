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
}
