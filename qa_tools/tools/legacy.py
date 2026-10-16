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
}
