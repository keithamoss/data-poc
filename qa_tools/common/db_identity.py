"""Which data asset and environment a database belongs to, recorded in the
database itself and checked on every connection (REQ-PIPE-107).

WHY THE DATABASE IS ASKED, NOT THE DSN. The same environment is reached by
different hostnames from inside and outside, and two environments can differ
only by a hostname somebody mistypes. Asking the database who it is answers
the question that matters: is this the database this checkout means to act on.

WHERE IT LIVES: two database-level settings, `mothman.data_asset_id` and
`mothman.environment`, written by `ALTER DATABASE ... SET` and read back from
the catalogue (`pg_db_role_setting`), never from `current_setting()`.
- A database-level setting is outside every schema, so REQ-PIPE-144's reset,
  which drops the QA history schema by schema, leaves it in place
  (criterion 11) without being taught to.
- Reading the catalogue rather than the session's value means a connection
  string carrying `options=-c mothman.environment=...` cannot claim an
  identity the database does not have - which would be exactly the adoption
  from configuration criterion 7 forbids.
- It shares REQ-PIPE-146's round trip: the server version and the identity
  come back in one statement, the first one a connection runs (criterion 5,
  NFR 1).

FAILS CLOSED (NFR 3). Missing, half-recorded or unreadable is a refusal, and a
refusal never carries any part of the connection string (criterion 6) - it is
the message most likely to be pasted into a chat.
"""
from __future__ import annotations

from dataclasses import dataclass

ASSET_SETTING = "mothman.data_asset_id"
ENVIRONMENT_SETTING = "mothman.environment"

#: One statement, the first a connection runs: the server's version
#: (REQ-PIPE-146) and the database's own recorded settings.
PROBE = """
SELECT current_setting('server_version_num'),
       (SELECT s.setconfig
          FROM pg_catalog.pg_db_role_setting s
          JOIN pg_catalog.pg_database d ON d.oid = s.setdatabase
         WHERE d.datname = current_database() AND s.setrole = 0)
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


def parse(setconfig) -> Identity | None:
    """The recorded identity from `pg_db_role_setting.setconfig`, None when
    neither half is recorded. Half of one is unreadable, not absent."""
    values = {}
    for item in setconfig or []:
        key, _, value = str(item).partition("=")
        values[key] = value
    asset, env = values.get(ASSET_SETTING), values.get(ENVIRONMENT_SETTING)
    if asset is None and env is None:
        return None
    if not asset or not env:
        raise IdentityRefused(
            "this database's recorded identity is incomplete (it names "
            f"{'only a data asset' if asset else 'only an environment'}), so it cannot be "
            "read - refusing. Re-mark it with `mothman env mark`.")
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
    """Write the identity. ONLY `mothman env mark` and the fixtures and setup
    scripts named in criterion 12 call this (criterion 4). The database name
    comes from the server, never from the connection string."""
    from psycopg import sql

    name = conn.execute("SELECT current_database()").fetchone()[0]
    for setting, value in ((ASSET_SETTING, identity.data_asset_id),
                           (ENVIRONMENT_SETTING, identity.environment)):
        conn.execute(sql.SQL("ALTER DATABASE {} SET {} = {}").format(
            sql.Identifier(name), sql.SQL(setting), sql.Literal(value)))


def mark_by_admin(admin_conn, database: str, identity: Identity) -> None:
    """Mark a database from a connection to ANOTHER one - how a test fixture
    marks the scratch database it has just created (criterion 12)."""
    from psycopg import sql

    for setting, value in ((ASSET_SETTING, identity.data_asset_id),
                           (ENVIRONMENT_SETTING, identity.environment)):
        admin_conn.execute(sql.SQL("ALTER DATABASE {} SET {} = {}").format(
            sql.Identifier(database), sql.SQL(setting), sql.Literal(value)))
