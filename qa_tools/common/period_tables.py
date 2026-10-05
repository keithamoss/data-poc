"""The one code path that moves a table into or out of a period schema
(REQ-PIPE-129).

PLAIN BASE NAMES IN A PERIOD (criteria 1 and 2): a period holds one
version of each table (REQ-PIPE-128), so the version needs no name of its
own there - `cp_carers`, which is what a person or an external tool
querying the period expects. Staging, every `_superseded` schema and the
rejected schema keep stamped names (criterion 6), because several versions
of one table sit side by side in each.

THE STAMPED NAME IS REBUILT, NEVER STORED (criterion 4): from the table
name and the supply id the decision log already holds - a second record of
the name is a second thing to keep in step.

THREE GUARDS, EACH ENOUGH ON ITS OWN (criteria 9 to 12 and 17): the
decision log refuses moving a supply a later period stands on
(decision_log._judge); this module refuses taking out a table any period's
view depends on, asking the catalogue; and an event trigger in the
database refuses the same move, rename or cascading drop whatever issued
it. Where the platform does not permit the trigger (criterion 18), the
other two run and the gap is reported.
"""
from __future__ import annotations

import contextlib

from qa_tools.common import period_schema, supply_db


class DependentView(RuntimeError):
    """A view in a period depends on the table about to leave its period
    (criterion 10)."""


def stamped_name(logical: str, supply: str) -> str:
    """`<table>__<arrival key>` - the name a supply's table carries outside
    a period, rebuilt from the decision log's table name and supply id."""
    if "@" in (supply or ""):
        key = supply.rsplit("@", 1)[1].split("#", 1)[0]
        return f"{logical}__{key}"
    # A decision that named the physical table itself, as some callers do.
    if supply_db.split_staged(supply or ""):
        return supply
    return logical


def logical_of(physical: str) -> str:
    return (supply_db.split_staged(physical) or (physical,))[0]


def dependants(conn, schema: str, table: str) -> list[str]:
    """`schema.view` for every view in a period schema - not a `_superseded`
    one - that depends on this table (criterion 14): what a move would
    carry along or break. A QA run's own views are not in period schemas,
    so they never block a person's decision."""
    rows = conn.execute(
        "SELECT DISTINCT vn.nspname || '.' || v.relname, vn.nspname "
        "FROM pg_depend d JOIN pg_rewrite r ON r.oid = d.objid "
        "JOIN pg_class v ON v.oid = r.ev_class JOIN pg_namespace vn ON vn.oid = v.relnamespace "
        "JOIN pg_class t ON t.oid = d.refobjid JOIN pg_namespace tn ON tn.oid = t.relnamespace "
        "WHERE tn.nspname = ? AND t.relname = ? AND v.oid <> t.oid",
        [schema, table]).fetchall()
    return sorted(name for name, view_schema in rows
                  if view_schema.startswith(period_schema.PERIOD_SCHEMA_PREFIX)
                  and not view_schema.endswith(period_schema.SUPERSEDED_SUFFIX))


def is_view(conn, schema: str, name: str) -> bool:
    """Asked of the catalogue, never inferred from a name (criterion 8)."""
    rows = conn.execute(
        "SELECT table_type FROM information_schema.tables WHERE table_schema = ? "
        "AND table_name = ?", [schema, name]).fetchall()
    return bool(rows) and rows[0][0] == "VIEW"


def bring_in(conn, *, physical: str, source_schema: str, period: str) -> str:
    """Move a supply's table into its period and give it the plain base
    name, in the caller's transaction (criterion 2). Returns the name."""
    schema = period_schema.period_schema(period)
    logical = logical_of(physical)
    supply_db.move_table(conn, physical, source_schema, schema, through_period_tables=True)
    if physical != logical:
        conn.execute(f'ALTER TABLE "{schema}"."{supply_db._ident(physical, "table name")}" '
                     f'RENAME TO "{supply_db._ident(logical, "table name")}"')
    return logical


def take_out(conn, *, period: str, logical: str, supply: str, to_schema: str) -> str | None:
    """Take a supply's table out of its period, restoring its stamped name,
    in the caller's transaction (criteria 3, 9 and 10). Returns the stamped
    name, or None where the period holds no such table.

    LOCKED FIRST, then the catalogue asked whether any period's view
    depends on it - and refused naming each, before anything moves. A QA
    run reading the table holds the lock; the transaction's lock timeout
    turns that wait into a refusal (criterion 16)."""
    schema = period_schema.period_schema(period)
    present = conn.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = ? AND table_name = ? "
        "AND table_type = 'BASE TABLE'", [schema, logical]).fetchall()
    if not present:
        return None
    conn.execute(f'LOCK TABLE "{schema}"."{supply_db._ident(logical, "table name")}" '
                 f"IN ACCESS EXCLUSIVE MODE")
    blocking = dependants(conn, schema, logical)
    if blocking:
        raise DependentView(
            f"{schema}.{logical} cannot leave {period}: {', '.join(blocking)} depends on it. "
            f"Clear what stands on it first - each period's view is a substitution or an "
            f"inheritance, removed by de-substitute or un-inherit.")
    stamped = stamped_name(logical, supply)
    if stamped != logical:
        conn.execute(f'ALTER TABLE "{schema}"."{supply_db._ident(logical, "table name")}" '
                     f'RENAME TO "{supply_db._ident(stamped, "table name")}"')
    supply_db.move_table(conn, stamped, schema, to_schema, through_period_tables=True)
    return stamped


# ---- the database guard (criteria 11, 17 and 18) -------------------------

GUARD_FUNCTION = "qa.period_table_guard"
DROP_GUARD_FUNCTION = "qa.period_view_drop_guard"
GUARD_TRIGGER = "period_table_guard"
DROP_GUARD_TRIGGER = "period_view_drop_guard"

GUARD_DDL = f"""
CREATE OR REPLACE FUNCTION {GUARD_FUNCTION}() RETURNS event_trigger
LANGUAGE plpgsql AS $$
DECLARE
  cmd record;
  dependent text;
BEGIN
  -- MOVES AND RENAMES ONLY (criterion 11; Keith, 2026-10-05, #113): an added
  -- column is not a move, and refusing every ALTER would block each schema
  -- change on a table a view stands on. The trigger cannot see the
  -- sub-command, so the statement's own text decides.
  IF current_query() !~* '(SET\s+SCHEMA|RENAME\s+TO)' THEN
    RETURN;
  END IF;
  FOR cmd IN SELECT * FROM pg_event_trigger_ddl_commands()
             WHERE command_tag = 'ALTER TABLE' AND object_type = 'table' LOOP
    SELECT vn.nspname || '.' || v.relname INTO dependent
      FROM pg_depend d JOIN pg_rewrite r ON r.oid = d.objid
      JOIN pg_class v ON v.oid = r.ev_class JOIN pg_namespace vn ON vn.oid = v.relnamespace
     WHERE d.refobjid = cmd.objid AND v.oid <> cmd.objid
       AND vn.nspname LIKE '{period_schema.PERIOD_SCHEMA_PREFIX.replace("_", chr(92) + "_")}%'
       AND vn.nspname NOT LIKE '%{period_schema.SUPERSEDED_SUFFIX.replace("_", chr(92) + "_")}'
     LIMIT 1;
    IF dependent IS NOT NULL THEN
      RAISE EXCEPTION 'refused: % cannot be moved or renamed - the period view % depends on '
        'it. Remove the substitution or inheritance standing on it first (REQ-PIPE-129)',
        cmd.object_identity, dependent;
    END IF;
  END LOOP;
END $$;

CREATE OR REPLACE FUNCTION {DROP_GUARD_FUNCTION}() RETURNS event_trigger
LANGUAGE plpgsql AS $$
DECLARE
  obj record;
BEGIN
  FOR obj IN SELECT * FROM pg_event_trigger_dropped_objects()
             WHERE object_type = 'view' AND NOT original
               AND schema_name LIKE '{period_schema.PERIOD_SCHEMA_PREFIX.replace("_", chr(92) + "_")}%'
               AND schema_name NOT LIKE '%{period_schema.SUPERSEDED_SUFFIX.replace("_", chr(92) + "_")}' LOOP
    -- Dropping the period's own schema takes its views with it on purpose
    -- (a reset); anything else taking one as a side effect is refused.
    IF NOT EXISTS (SELECT 1 FROM pg_event_trigger_dropped_objects() s
                   WHERE s.object_type = 'schema' AND s.object_name = obj.schema_name) THEN
      RAISE EXCEPTION 'refused: dropping this would also drop the view %.%, which a period '
        'resolves through - remove it on its own first (REQ-PIPE-129)',
        obj.schema_name, obj.object_name;
    END IF;
  END LOOP;
END $$;

DROP EVENT TRIGGER IF EXISTS {GUARD_TRIGGER};
CREATE EVENT TRIGGER {GUARD_TRIGGER} ON ddl_command_end
  WHEN TAG IN ('ALTER TABLE') EXECUTE FUNCTION {GUARD_FUNCTION}();
DROP EVENT TRIGGER IF EXISTS {DROP_GUARD_TRIGGER};
CREATE EVENT TRIGGER {DROP_GUARD_TRIGGER} ON sql_drop
  EXECUTE FUNCTION {DROP_GUARD_FUNCTION}();
"""


def install_guard(conn) -> bool:
    """Install the event triggers where the platform permits them - they
    need elevated rights (NFR 7). Returns whether they are installed;
    False is reported, never raised (criterion 18)."""
    try:
        with conn.raw.transaction():
            conn.execute(GUARD_DDL)
        return True
    except Exception:  # noqa: BLE001 - a platform that refuses runs on the other two
        return False


def guard_installed(conn) -> bool:
    rows = conn.execute("SELECT count(*) FROM pg_event_trigger WHERE evtname IN (?, ?) "
                        "AND evtenabled <> 'D'", [GUARD_TRIGGER, DROP_GUARD_TRIGGER]).fetchall()
    return bool(rows) and rows[0][0] == 2


@contextlib.contextmanager
def guard_disabled(conn):
    """For a test proving another guard refuses on its own (criterion 12)."""
    present = guard_installed(conn)
    if present:
        conn.execute(f"ALTER EVENT TRIGGER {GUARD_TRIGGER} DISABLE")
        conn.execute(f"ALTER EVENT TRIGGER {DROP_GUARD_TRIGGER} DISABLE")
    try:
        yield
    finally:
        if present:
            conn.execute(f"ALTER EVENT TRIGGER {GUARD_TRIGGER} ENABLE")
            conn.execute(f"ALTER EVENT TRIGGER {DROP_GUARD_TRIGGER} ENABLE")


# ---- reporting a missing guard (criterion 18) ----------------------------

WARNING_EXIT_VAR = "MOTHMAN_GATE_WARNING_EXIT"


def guard_report(conn) -> str | None:
    """None where the guard is installed, else what to tell a person. A
    database with no qa schema yet has nothing to guard, so says nothing."""
    if guard_installed(conn):
        return None
    return ("the database guard on period tables (REQ-PIPE-129) is NOT installed - this "
            "platform refused the event triggers, or they were dropped. The decision log "
            "and the move code path still refuse a move a period's view depends on; "
            "anything else issuing DDL against a period schema is unguarded. Install it "
            "with `mothman supply install-guard`.")


def main() -> int:
    """`mothman check`'s guard gate: a WARNING, never a failure - the other
    two guards still run (criterion 18). Silent where no database is
    configured or reachable, which is a CI runner's ordinary state."""
    import os

    try:
        with supply_db.connect(label="mothman:guard-check") as conn:
            if not conn.execute("SELECT to_regclass('qa.schema_version')").fetchall()[0][0]:
                # NOT "installed" (#113): an empty database has nothing to
                # guard yet, and the first schema build installs it.
                print("note: this database has no qa schema yet, so there is nothing to "
                      "guard; building the schema installs the guard.")
                return 0
            problem = guard_report(conn)
    except Exception as exc:  # noqa: BLE001 - no database is not this gate's business
        print(f"note: no supply database to check the period-table guard in "
              f"({type(exc).__name__}).")
        return 0
    if problem is None:
        print("The period-table guard is installed.")
        return 0
    print(f"warning: {problem}")
    return int(os.environ.get(WARNING_EXIT_VAR) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
