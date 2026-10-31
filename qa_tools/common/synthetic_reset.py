"""Reset a SYNTHETIC asset's whole QA history to empty (REQ-PIPE-144
criteria 20-23 and 43).

ONE DELIBERATE COMMAND, `mothman env reset-synthetic`, and nothing else
deletes recorded history. Delivery records are history (criterion 19) -
in production processed files move to another bucket, so "the folder is
gone" must never delete a record - and filings, holds and the decision
log are write-once or append-only, so a re-run cannot replace them; it
can only add to them. Starting from empty therefore has to be its own
explicit act, and Keith's bar for it is "not something a human can
stumble across":

- REFUSED for any asset whose configuration does not declare it
  synthetic (criterion 43, `synthetic: true` in contract/data-asset.yaml)
  - keyed off what the history IS, not off an environment's name;
- CONFIRMED by typing a phrase that names what is deleted (criterion 21);
- CALLED BY NOTHING ELSE (criterion 23) - no command, hook or bootstrap
  reaches this module.

WHAT IT DELETES is rebuild-from-empty made explicit: the `qa` metadata
schema whole (deliveries, delivery files, filings, holds, decisions,
runs, results) and every schema holding supply rows (staging, periods,
rejected, run views, trials). Dropping rather than deleting rows, which
is also what lets an OLDER schema version be reset - ensure_schema
refuses those (criterion 29), and its message points here.
"""
from __future__ import annotations

from qa_tools.common import config_yaml

from qa_tools.common import qa_store, supply_db


class NotSynthetic(Exception):
    """This asset's configuration does not declare it synthetic."""


def is_synthetic() -> bool:
    """Whether contract/data-asset.yaml declares this asset synthetic."""
    from qa_tools.common import asset_time

    raw = config_yaml.parse(asset_time.DATA_ASSET_YAML.read_text()) or {}
    return raw.get("synthetic") is True


def in_production() -> bool:
    """Criterion 22, kept BESIDE criterion 43's synthetic declaration
    rather than replaced by it: a production checkout is refused too, so
    a misdeclared asset still cannot be reset where it is real."""
    from qa_tools.common import environments

    here = environments.current_or_none()
    return here is not None and here.id == "production"


def asset_id() -> str:
    from qa_tools.common import asset_time

    return (config_yaml.parse(asset_time.DATA_ASSET_YAML.read_text()) or {})["data_asset_id"]


def confirmation_phrase() -> str:
    """What a person types to confirm - it names what goes."""
    return f"delete all QA history for {asset_id()}"


#: Our schemas with fixed names - matched EXACTLY, never as a prefix
#: (delivery-critic on REQ-PIPE-144: `staging_someone_elses` was dropped).
_FIXED = (qa_store.SCHEMA, supply_db.STAGING_SCHEMA, supply_db.REJECTED_SCHEMA,
          supply_db.SAMPLE_SCHEMA, "promoted")


class WouldReachOutside(Exception):
    """Something outside what the reset deletes depends on what it deletes,
    so CASCADE would take it too - refused, naming it."""


def schemas_to_drop(conn: supply_db.SupplyConnection) -> list[str]:
    """This asset's own schemas: the fixed names exactly, and the
    per-period, per-run, per-run dbt and trial schemas through the
    modules that name them."""
    from qa_tools.common import period_schema

    present = {row[0] for row in conn.execute("SELECT nspname FROM pg_namespace").fetchall()}
    ours = {n for n in _FIXED if n in present}
    # BY SCHEMA NAME (post-build-review #109, F12): period_schemas()
    # answers with PERIOD names, so this used to add names that are not
    # schemas and leave every period schema - and its superseded schema
    # beside it (REQ-PIPE-118) - behind.
    ours |= set(supply_db.schemas_with_prefix(conn, period_schema.PERIOD_SCHEMA_PREFIX))
    ours |= set(supply_db.run_schemas(conn))
    ours |= set(supply_db.dbt_schemas(conn))
    ours |= set(supply_db.schemas_with_prefix(conn, supply_db.TRIAL_SCHEMA_PREFIX))
    # A QA SCHEMA HOLDING ONLY THE IDENTITY IS NOT HISTORY (REQ-PIPE-107
    # criterion 11): it is what a reset leaves behind on purpose, so it is not
    # something still to drop.
    from qa_tools.common import qa_store

    if qa_store.SCHEMA in ours and {row[0] for row in conn.execute(
            "SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = ? AND c.relkind IN ('r', 'v', 'm', 'p', 'f')",
            [qa_store.SCHEMA]).fetchall()} <= {"identity"}:
        ours.discard(qa_store.SCHEMA)
    return sorted(ours)


def _dependents_outside(conn, schemas: list[str]) -> list[str]:
    """Objects in OTHER schemas that depend on something in `schemas` -
    what `DROP SCHEMA ... CASCADE` would silently take with it."""
    if not schemas:
        return []
    rows = conn.execute(
        """
        SELECT DISTINCT dn.nspname || '.' || dc.relname
        FROM pg_depend d
        JOIN pg_rewrite r ON r.oid = d.objid AND d.classid = 'pg_rewrite'::regclass
        JOIN pg_class dc ON dc.oid = r.ev_class
        JOIN pg_namespace dn ON dn.oid = dc.relnamespace
        JOIN pg_class rc ON rc.oid = d.refobjid AND d.refclassid = 'pg_class'::regclass
        JOIN pg_namespace rn ON rn.oid = rc.relnamespace
        WHERE rn.nspname = ANY(?) AND NOT (dn.nspname = ANY(?))
        ORDER BY 1""", [list(schemas), list(schemas)]).fetchall()
    return [r[0] for r in rows]


def what_it_deletes(conn: supply_db.SupplyConnection) -> dict[str, int]:
    """Row counts per recorded-history table, for the person to read
    before they type the phrase. Zero for a table that is not there."""
    out = {}
    for table in ("delivery", "delivery_file", "filing", "hold", "decision",
                  "run", "check_result"):
        if conn.execute(f"SELECT to_regclass('{qa_store.SCHEMA}.{table}')").fetchall()[0][0]:
            out[table] = conn.execute(
                f'SELECT count(*) FROM "{qa_store.SCHEMA}".{table}').fetchall()[0][0]
        else:
            out[table] = 0
    return out


def _empty_qa_schema(conn: supply_db.SupplyConnection) -> None:
    """Drop every object in the qa schema except `identity`. Views first,
    then tables, then functions (taking the guard's event triggers with
    them - qa_store.ensure_schema() puts both back), then any sequence
    that outlived its table."""
    def names(sql: str) -> list[str]:
        return [r[0] for r in conn.execute(sql, [qa_store.SCHEMA]).fetchall()]

    rel = ("SELECT quote_ident(c.relname) FROM pg_class c JOIN pg_namespace n "
           "ON n.oid = c.relnamespace WHERE n.nspname = ? AND c.relname <> 'identity' "
           "AND c.relkind IN ({})")
    q = f'"{qa_store.SCHEMA}".'
    views = names(rel.format("'v', 'm'"))
    if views:
        conn.execute("DROP VIEW IF EXISTS " + ", ".join(q + v for v in views) + " CASCADE")
    tables = names(rel.format("'r', 'p'"))
    if tables:
        conn.execute("DROP TABLE IF EXISTS " + ", ".join(q + t for t in tables) + " CASCADE")
    for fn in names("SELECT p.oid::regprocedure::text FROM pg_proc p JOIN pg_namespace n "
                    "ON n.oid = p.pronamespace WHERE n.nspname = ?"):
        conn.execute(f"DROP FUNCTION IF EXISTS {fn} CASCADE")
    sequences = names(rel.format("'S'"))
    if sequences:
        conn.execute("DROP SEQUENCE IF EXISTS " + ", ".join(q + x for x in sequences)
                     + " CASCADE")


def reset(conn: supply_db.SupplyConnection, typed: str,
          schemas: list[str] | None = None) -> list[str]:
    """Drop the whole QA history; return the schemas dropped.

    Raises NotSynthetic before touching anything for an asset not
    declared synthetic, and ValueError for a confirmation that is not
    the phrase exactly.
    """
    if not is_synthetic():
        raise NotSynthetic(
            f"{asset_id()} is not declared synthetic in contract/data-asset.yaml, so "
            f"its history is treated as real and nothing was deleted.")
    if in_production():
        raise NotSynthetic("this checkout is acting as `production` (MOTHMAN_ENVIRONMENT), "
                           "so nothing was deleted.")
    if typed.strip() != confirmation_phrase():
        raise ValueError(f"the confirmation did not read {confirmation_phrase()!r}, "
                         f"so nothing was deleted.")
    dropped = schemas_to_drop(conn) if schemas is None else list(schemas)
    outside = _dependents_outside(conn, dropped)
    if outside:
        raise WouldReachOutside(
            f"{', '.join(outside)} depend(s) on what the reset would delete, so dropping it "
            f"would take them too. Nothing was deleted - remove or move them first.")
    # ONE STATEMENT, EVERY SCHEMA (#113): the database guard refuses a
    # cascaded drop of a period's view unless its own schema goes in the
    # same statement (REQ-PIPE-129 criterion 17), so dropping one at a time
    # failed on the first period another stood on.
    # THE IDENTITY STAYS (REQ-PIPE-107 criterion 11) - and its TABLE is never
    # dropped (Keith, 2026-10-06, post-build-review #122 D1/D2). Dropping the
    # qa schema and re-marking it in one transaction still let a probe on an
    # older snapshot meet a table created after it began, and refuse a marked
    # database as unmarked; and the re-mark rewrote marked_at. So the qa
    # schema is emptied of everything else instead, in the same transaction
    # as the other schemas' drop.
    others = [name for name in dropped if name != qa_store.SCHEMA]
    if dropped:
        with conn.raw.transaction():
            if others:
                conn.execute("DROP SCHEMA " + ", ".join(f'"{name}"' for name in others)
                             + " CASCADE")
            if qa_store.SCHEMA in dropped:
                _empty_qa_schema(conn)
    return dropped
