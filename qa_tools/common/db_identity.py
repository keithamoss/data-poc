"""Which data asset and environment a database belongs to, recorded in the
database itself and checked on every connection (REQ-PIPE-107).

WHY THE DATABASE IS ASKED, NOT THE DSN. The same environment is reached by
different hostnames from inside and outside, and two environments can differ
only by a hostname somebody mistypes. Asking the database who it is answers
the question that matters: is this the database this checkout means to act on.

WHERE IT LIVES: one row in `qa.identity` (Keith, 2026-10-06, over the
database-level settings it was first built as).
- A ROW TRAVELS WITH THE DATABASE: a dump carries it and so does a database
  copied from a template, where a database-level setting does neither.
- ONE ROW AT MOST, enforced by the table rather than by care.
- REQ-PIPE-144's reset drops the qa schema whole, so it reads the row first
  and puts it back in the same transaction (criterion 11).
- In the qa schema itself, so anything that can write QA history could
  relabel the database. Accepted by Keith over a schema of its own writable
  only by the owner; the guard is against a checkout pointed at the wrong
  database, not against someone already holding write access to it.
- The old settings are not read at all, so a database marked that way is
  unmarked now and refuses until `mothman env mark` (regenerate, never
  migrate).
- STILL ONE ROUND TRIP with REQ-PIPE-146's server version (NFR 1). An
  unmarked database has no qa schema, and naming a missing table is an
  error rather than an empty answer, so the table is read through
  query_to_xml() behind a to_regclass() test - evaluated only when it
  exists, in the same statement.

FAILS CLOSED (NFR 3). Missing, half-recorded or unreadable is a refusal, and a
refusal never carries any part of the connection string (criterion 6) - it is
the message most likely to be pasted into a chat.
"""
from __future__ import annotations

from dataclasses import dataclass

SCHEMA = "qa"
TABLE = f'"{SCHEMA}".identity'

#: The table, created by marking - before anything else has made the qa
#: schema - and by the qa schema's own DDL. One row: `only_row` can only be
#: true and is the key.
DDL = (
    f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"',
    f"""CREATE TABLE IF NOT EXISTS {TABLE} (
    only_row      boolean PRIMARY KEY DEFAULT true CHECK (only_row),
    data_asset_id text NOT NULL CHECK (data_asset_id <> ''),
    environment   text NOT NULL CHECK (environment <> ''),
    marked_at     timestamptz NOT NULL DEFAULT now()
)""",
)

#: One statement, the first a connection runs: the server's version
#: (REQ-PIPE-146) and the recorded identity, read only where the table is.
PROBE = f"""
SELECT current_setting('server_version_num'),
       CASE WHEN to_regclass('{SCHEMA}.identity') IS NULL THEN NULL
            ELSE query_to_xml('SELECT data_asset_id, environment FROM {TABLE}',
                              true, false, '')
       END
"""


class IdentityRefused(RuntimeError):
    """This database is not the one this checkout is configured for, carries
    no identity, or its identity could not be read. Never names the DSN."""


@dataclass(frozen=True)
class Identity:
    data_asset_id: str
    environment: str

    def __str__(self) -> str:
        return f"data asset {self.data_asset_id!r}, environment {self.environment!r}"


def parse(recorded) -> Identity | None:
    """The recorded identity from PROBE's second column, None when there is
    no table or no row. Anything else unreadable is a refusal."""
    if recorded is None:
        return None
    import xml.etree.ElementTree as ET

    try:
        rows = ET.fromstring(str(recorded)).findall("row")
    except ET.ParseError:
        raise IdentityRefused("this database's recorded identity could not be read - "
                              "refusing.") from None
    if not rows:
        return None
    row = rows[0]
    asset, env = row.findtext("data_asset_id"), row.findtext("environment")
    if not asset or not env:
        raise IdentityRefused("this database's recorded identity is incomplete, so it "
                              "cannot be read - refusing. Re-mark it with `mothman env mark`.")
    return Identity(asset, env)


def expected() -> Identity:
    """What this checkout is configured for: the asset from
    contract/data-asset.yaml, the environment as stated (REQ-PIPE-093)."""
    from qa_tools.common import environments, hierarchy

    return Identity(hierarchy.data_asset_id(), environments.current().id)


def check(setconfig, want: Identity | None = None) -> Identity:
    """Criteria 5 to 8: the recorded identity must equal the configured one."""
    want = want or expected()
    found = parse(setconfig)
    if found is None:
        raise IdentityRefused(
            f"this database carries no recorded identity, so nothing says it belongs to "
            f"{want} - refusing rather than assuming it. If it is the right one, mark it "
            f"with `mothman env mark` (it asks you to type {want.environment!r}).")
    if found != want:
        raise IdentityRefused(
            f"this database belongs to {found}, but this checkout is configured for "
            f"{want} - refusing before doing anything.")
    return found


def read(conn) -> tuple[str, Identity | None]:
    """`(server_version_num, recorded identity or None)` with no checking -
    for the marking command, which is the one thing allowed to meet an
    unmarked database."""
    num, setconfig = conn.execute(PROBE).fetchone()
    return num, parse(setconfig)


def mark(conn, identity: Identity) -> None:
    """Write the identity. ONLY `mothman env mark`, the reset putting it back,
    and the fixtures and setup scripts named in criterion 12 call this
    (criterion 4)."""
    raw = getattr(conn, "raw", conn)  # a SupplyConnection, or psycopg's own
    for statement in DDL:
        raw.execute(statement)
    raw.execute(
        f"INSERT INTO {TABLE} (data_asset_id, environment) VALUES (%s, %s) "
        "ON CONFLICT (only_row) DO UPDATE SET data_asset_id = EXCLUDED.data_asset_id, "
        "environment = EXCLUDED.environment, marked_at = now()",
        [identity.data_asset_id, identity.environment])


def mark_by_admin(admin_conn, database: str, identity: Identity) -> None:
    """Mark a database from a connection to ANOTHER one - how a test fixture
    marks the scratch database it has just created (criterion 12). A row has
    to be written from inside the database, so this opens a connection to it
    with the same credentials."""
    import psycopg

    info = psycopg.conninfo.conninfo_to_dict(admin_conn.info.dsn)
    info["dbname"] = database
    if admin_conn.info.password:
        info["password"] = admin_conn.info.password
    with psycopg.connect(psycopg.conninfo.make_conninfo(**info), autocommit=True) as conn:
        mark(conn, identity)
