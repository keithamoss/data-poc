"""The frozen defaults a check's definition fingerprint leaves out
(REQ-QAC-176 criteria 8 to 11).

WHY THIS EXISTS. A fingerprint is stored with every check result, and the
bulk re-check (REQ-PIPE-177) selects every supply whose stored fingerprint
differs from the check's current one. So a setting the system grows later -
a new dbt config key, a new Soda option - must not move every stored
fingerprint the day it is written into a check at the value the system was
already using. An entry here says "this setting, at this value, is what the
system did before the setting existed", and the writer leaves a setting
equal to it out before hashing, as the Rust stable_hash crate does.

FROZEN, NOT EDITED. A default edited in place would be invisible - the old
hash left the field out and so would the new one - so the list is APPEND-ONLY
and shared across scheme versions: an entry is changed only by appending a
new one under a new scheme version (criterion 11). The check-lifecycle gate
(validate_check_lifecycle, run by `mothman check`) refuses a changed or
removed entry, and refuses a new entry naming a setting some check at the
diff base already writes at that value, since dropping it would move that
check's stored fingerprint.

A LITERAL, READ BY ast AT ANY GIT REF. The gate compares this file at the
diff base with the working tree, so the list must be readable from a file's
text without importing it - which is why it is a plain tuple of plain dicts
and nothing else is computed here.

EACH ENTRY:
    tool    the check's tool - dbt, soda, datacontract, evidently or file
    path    the setting's path within the settings the writer hashes, as a
            list of map keys from the top
    kind    the check kind it is scoped to (a dbt test type, an ODCS rule
            type, an Evidently method, a file check's name), or None for
            every check of the tool
    value   the value the system used when the setting was introduced -
            compared by type AND value, so True never equals 1 and 1 never
            equals 1.0
    scheme  the fingerprint scheme version that introduced it, e.g. "v1"

EMPTY AT v1, and correctly so: v1 is the first fingerprint, so no setting has
yet been added after a result was recorded. The first entry is appended the
day a check file grows a setting at a value the system already used.
"""
from __future__ import annotations

FROZEN_DEFAULTS: tuple[dict, ...] = (
)
