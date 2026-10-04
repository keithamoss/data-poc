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

import yaml

from qa_tools.common import qa_store, supply_db


class NotSynthetic(Exception):
    """This asset's configuration does not declare it synthetic."""


def is_synthetic() -> bool:
    """Whether contract/data-asset.yaml declares this asset synthetic."""
    from qa_tools.common import asset_time

    raw = yaml.safe_load(asset_time.DATA_ASSET_YAML.read_text()) or {}
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

    return (yaml.safe_load(asset_time.DATA_ASSET_YAML.read_text()) or {})["data_asset_id"]


def confirmation_phrase() -> str:
    """What a person types to confirm - it names what goes."""
    return f"delete all QA history for {asset_id()}"


def schemas_to_drop(conn: supply_db.SupplyConnection) -> list[str]:
    """The qa schema and every supply-row schema present, sorted."""
    names = [row[0] for row in conn.execute(
        "SELECT nspname FROM pg_namespace").fetchall()]
    keep = [n for n in names
            if n == qa_store.SCHEMA or n.startswith(qa_store.SUPPLY_SCHEMA_PREFIXES)]
    return sorted(keep)


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


def reset(conn: supply_db.SupplyConnection, typed: str) -> list[str]:
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
    dropped = schemas_to_drop(conn)
    for name in dropped:
        conn.execute(f'DROP SCHEMA "{name}" CASCADE')
    return dropped
