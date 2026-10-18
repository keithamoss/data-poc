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
    "stage.stamps_run_columns": (
        "every staged row is stamped with `run_id` and `run_date` columns, which "
        "Birth Registrations' dbt model selects and Child Protection's tables have "
        "never carried."),
    "stats.rows_by_run_id": (
        "every statistic is scoped by the `run_id` column each staged row carries, "
        "as well as by the run's view schema."),
}
