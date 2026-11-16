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

from asset_model import config_yaml

from qa_tools.common import qa_store, supply_db
from asset_model import assets as _assets


class NotSynthetic(Exception):
    """This asset's configuration does not declare it synthetic."""


def is_synthetic() -> bool:
    """Whether the asset's data-asset.yaml declares it synthetic - asked of the
    one reader (REQ-PIPE-382 criterion 7, #137 group D)."""
    from asset_model import asset_time

    return asset_time.declared_synthetic()


def in_production() -> bool:
    """Criterion 22, kept BESIDE criterion 43's synthetic declaration
    rather than replaced by it: a production checkout is refused too, so
    a misdeclared asset still cannot be reset where it is real."""
    from qa_tools.common import environments

    here = environments.current_or_none()
    return here is not None and here.id == "production"


def asset_id() -> str:
    from asset_model import asset_time

    return (config_yaml.load(asset_time.data_asset_yaml()) or {})["data_asset_id"]


def confirmation_phrase() -> str:
    """What a person types to confirm - it names what goes, the files as well
    as the history (REQ-GEN-408 criterion 3; SR4)."""
    return f"delete all QA history and generated files for {asset_id()}"


# ---- the generated files (REQ-GEN-408) ------------------------------------------
#
# A REGENERATION REPLACES THE WHOLE HISTORY (R4): the database AND the files the
# generator wrote - the delivery and receipt trees, its bookkeeping, the scenario
# placements and the anchor file - so a history at a new anchor never sits
# beside the old one. A generation deletes only what its bookkeeping says it
# wrote last time, which misses anything the bookkeeping does not list.

class UnsafeFiles(Exception):
    """A file the reset would delete is a symlink, or lies outside the
    selected asset's own data folder - nothing is deleted."""


class HandFiled(Exception):
    """The delivery tree holds a folder the generator did not write."""


def data_dir():
    """The selected asset's data folder, data/<asset>."""
    return _assets.data_dir()


def expected_data_dir():
    """Where that folder must be: ROOT/data/<asset> - the only data folder an
    asset has, an injected assets/ root included (asset_model/assets.py)."""
    return _assets.ROOT / "data" / _assets.selected().name


def generated_paths() -> list:
    """What the reset deletes beside the database, in the order it lists them
    (criterion 1)."""
    from asset_model import history_anchor
    from qa_tools.common import delivery, scenario_map

    root = data_dir()
    return [root / "deliveries", root / "receipts", root / delivery.BOOKKEEPING_FILE,
            root / scenario_map.PLACEMENTS_FILE, root / history_anchor.FILE]


def file_count(path) -> int:
    """How many files a tree or file holds - 0 where it is absent."""
    import os

    if os.path.islink(path) or path.is_file():
        return 1
    if not path.is_dir():
        return 0
    return sum(len(files) for _, _, files in os.walk(path))


def refuse_unsafe() -> None:
    """Criterion 7: real paths resolved first, and refused - deleting nothing -
    where the data folder is a symlink or is not data/<asset>, or anything to
    delete is a symlink or resolves outside it."""
    import os

    root = data_dir()
    problems = []
    if os.path.islink(root):
        problems.append(f"{_shown(root)} is a symbolic link")
    if os.path.realpath(root) != os.path.realpath(expected_data_dir()):
        problems.append(f"{_shown(root)} is not this asset's data folder, "
                        f"{_shown(expected_data_dir())}")
    real_root = os.path.realpath(root)
    for path in generated_paths():
        if os.path.islink(path):
            problems.append(f"{_shown(path)} is a symbolic link")
            continue
        if path.exists() and not os.path.realpath(path).startswith(real_root + os.sep):
            problems.append(f"{_shown(path)} resolves outside {_shown(root)}")
        if path.is_dir():
            for dirpath, dirnames, filenames in os.walk(path):
                for name in dirnames + filenames:
                    if os.path.islink(os.path.join(dirpath, name)):
                        problems.append(
                            f"{_shown(os.path.join(dirpath, name))} is a symbolic link")
    if problems:
        raise UnsafeFiles("nothing was deleted - " + "; ".join(problems)
                          + ". The reset deletes only this asset's own generated files, as "
                            "real paths inside its data folder.")


def hand_filed() -> list[str]:
    """Delivery folders the generator's bookkeeping does not list (criterion 4)
    - a handfiled-* folder from `mothman <collection> qa --commit`, or any
    other."""
    from generator import public as generator
    from qa_tools.common import delivery

    tree = data_dir() / "deliveries"
    if not tree.is_dir():
        return []
    written = generator.written_delivery_names(data_dir() / delivery.BOOKKEEPING_FILE)
    return sorted(p.name for p in tree.iterdir() if p.is_dir() and p.name not in written)


def refuse_hand_filed() -> None:
    found = hand_filed()
    if found:
        raise HandFiled(
            f"the delivery tree, {_shown(data_dir() / 'deliveries')}, holds "
            f"{len(found)} folder(s) the generator did not write: "
            + ", ".join(found) + ". A folder the generator did not write cannot be "
            "regenerated, so the reset stops until it has been moved or deleted by hand. "
            "Nothing was deleted.")


def recorded_anchor_line(conn) -> str:
    """The anchor recorded for the history about to go, with the command that
    rebuilds it - or 'no anchor recorded' (criterion 2): the last moment to
    read it."""
    from asset_model import history_anchor

    found = qa_store.history_anchor(conn) or history_anchor.recorded(data_dir() / history_anchor.FILE)
    if found is None:
        return "no anchor recorded"
    return (f"generated up to {found.isoformat()} - `mothman pipeline bootstrap --anchor "
            f"{found.isoformat()}` rebuilds it")


def delete_generated() -> tuple[list[str], list[str]]:
    """Delete every generated file and tree (criterion 1); returns (what was
    deleted, what remains after a failure). Carries on past one failure, so a
    second reset finishes what the first left."""
    import shutil

    deleted, remains = [], []
    for path in generated_paths():
        if not path.exists():
            continue
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            deleted.append(_shown(path))
        except OSError as exc:
            remains.append(f"{_shown(path)} ({exc.strerror or exc})")
    return deleted, remains


def _shown(path) -> str:
    """A path relative to the repository where it is inside it."""
    import os

    real, root = os.path.realpath(path), os.path.realpath(_assets.ROOT)
    return os.path.relpath(path, _assets.ROOT) if real.startswith(root + os.sep) else str(path)


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
            f"{asset_id()} is not declared synthetic in {_assets.config_dir()}/data-asset.yaml, so "
            f"its history is treated as real and nothing was deleted.")
    if in_production():
        raise NotSynthetic("this checkout is acting as `production` (MOTHMAN_ENVIRONMENT), "
                           "so nothing was deleted.")
    if typed.strip() != confirmation_phrase():
        raise ValueError(f"the confirmation did not read {confirmation_phrase()!r}, "
                         f"so nothing was deleted.")
    # THE FILES' REFUSALS TOO, BEFORE ANYTHING GOES (REQ-GEN-408 criteria 4,
    # 6 and 7): the database is not dropped while its files cannot follow.
    refuse_unsafe()
    refuse_hand_filed()
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
