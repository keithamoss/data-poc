"""`mothman check`'s `columns` gate (REQ-GEN-183 criterion 9): every
SQL-bodied check in force declares the columns its SQL reads, in the
contract's own table names, and names none the contract does not define.

The same check runs in CI inside the check-lifecycle gate; this is the
current tree alone, with no git history, so it is cheap enough to run on
every `mothman check`.
"""
from __future__ import annotations

import sys

from qa_tools.common import check_lifecycle as cl


def main() -> int:
    from qa_tools.common import validate_check_lifecycle as vcl

    checks = vcl.collect_checks(None)
    errors = cl.reads_columns_errors(checks, cl.contract_columns())
    if errors:
        print(f"reads_columns validation FAILED ({len(errors)} error(s)):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    sql = sum(1 for c in checks if c.sql_bodied and not c.retired_as_of)
    print(f"reads_columns validation OK - {sql} SQL-bodied checks each name the columns "
          f"they read.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
