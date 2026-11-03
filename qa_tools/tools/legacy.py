"""The legacy flags an adapter may declare (REQ-QAC-242 criteria 4 and 5) -
NONE, since REQ-QAC-247 and REQ-PIPE-248 retired every one.

A LEGACY FLAG PRESERVED DRIFT. The shared modules started from Child
Protection's code, and where Birth Registrations' recorded output differed,
the difference was kept behind a flag on its adapter so no refactor step
changed either collection's output. REQ-QAC-247 resolved the behavioural
ones flag by flag at Keith's calls, and REQ-PIPE-248 unified the shapes.

KNOWN STAYS, EMPTY, BECAUSE IT IS THE GATE (REQ-QAC-247 criterion 5,
REQ-PIPE-248 criterion 6): an adapter declaring any name not here - which is
now every name - fails `mothman check`'s collections gate, naming it. A new
difference between collections is a per-collection setting on the adapter,
named for what it is, never a new legacy flag.
"""
from __future__ import annotations

#: name -> what it preserves.
KNOWN: dict[str, str] = {
}
