"""A one-off's lifecycle around its load: what `mothman one-off list` shows of
every one-off (REQ-PIPE-442 criterion 10), and what `mothman one-off drop`
removes (criteria 6 to 9).

LIST READS THE CHEAP STAGES ONLY (Keith 2026-11-21, v6 Q5 (a)): the one-offs
root, git, and the configured local server's list of databases through one
administrative connection that claims no asset - opened, committed, pushed or
loaded, how long since its database was created, and the next step. It never
opens a one-off's own database.

THE DROP REMOVES EVERYTHING THE ONE-OFF LEFT, AND ONLY THAT (criteria 6 and
8): the database supply_<id>, its data/<id>/ (the filed copies of its files,
its check workspace and its dbt scratch) and reports/<id>/, and any dbt
target/, logs/ and dbt_packages in its folder - never its committed
configuration. Each item is listed with what it holds before anything goes,
and removed one at a time, so a partial failure names what is left and the
same drop finishes it. Nothing here drops a one-off on its own account
(criterion 9): only the drop command calls `remove`.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from asset_model import assets

#: dbt's own artefacts in a one-off's folder (REQ-PIPE-440 criterion 11).
DBT_ARTEFACTS = ("target", "logs", "dbt_packages", "package-lock.yml")


def server() -> str | None:
    import os

    from qa_tools.common import supply_db

    return os.environ.get(supply_db.SERVER_ENV) or None


def _admin(server_url: str):
    import psycopg

    from qa_tools.common import supply_db

    return psycopg.connect(supply_db.on_server(server_url, "postgres"), autocommit=True,
                           application_name="mothman:one-off")


class Ages(dict):
    """{database name: hours since it was created}, `one_offs`: the names
    among them marked as a one-off's database on the server, and `stages`:
    the stage each one's mark carries where it carries one (decided,
    published)."""

    def __init__(self, ages, one_offs=(), stages=None):
        super().__init__(ages)
        self.one_offs = frozenset(one_offs)
        self.stages = dict(stages or {})


def database_ages() -> Ages | None:
    """{database name: hours since it was created} for every database on the
    configured local server whose name is supply_<something> - through one
    administrative connection, claiming no asset - or None with no server.
    Which of them are one-offs' is read from the same connection: the comment
    a one-off load marks its database with (one_off_load.SERVER_MARK). A
    database dropped while this reads - another session's - has no files left
    to stat: missing_ok, so it is left out rather than failing the list."""
    from qa_tools.common import one_off_load, supply_db

    url = server()
    if url is None:
        return None
    with _admin(url) as conn:
        rows = conn.execute(
            "SELECT d.datname, EXTRACT(EPOCH FROM now() - (pg_stat_file('base/' || d.oid || "
            "'/PG_VERSION', true)).modification) / 3600, shobj_description(d.oid, 'pg_database') "
            "FROM pg_database d WHERE d.datname LIKE %s ORDER BY d.datname",
            [supply_db.ASSET_DATABASE_PREFIX.replace("_", r"\_") + "%"]).fetchall()
    marked = {name: comment for name, age, comment in rows if age is not None
              and (comment or "").startswith(one_off_load.SERVER_MARK)}
    return Ages({name: float(age) for name, age, _c in rows if age is not None}, marked,
                {name: one_off_load.marked_stage(c) for name, c in marked.items()
                 if one_off_load.marked_stage(c)})


def _git(args, cwd) -> str | None:
    import subprocess

    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 else None


def git_stage(folder: Path) -> str:
    """'opened', 'committed' or 'pushed' - from git alone."""
    from qa_tools.common import one_off_load

    if one_off_load.git_refusal(folder, "folder") is None:
        return "pushed"
    top = _git(["rev-parse", "--show-toplevel"], folder)
    if top is None:
        return "opened"
    rel = folder.resolve().relative_to(Path(top).resolve()).as_posix()
    dirty = _git(["status", "--porcelain", "--untracked-files=all", "--", rel], top)
    last = _git(["log", "-1", "--format=%H", "--", rel], top)
    return "committed" if last and not dirty else "opened"


@dataclass(frozen=True)
class Row:
    one_off_id: str
    kind: str          # the kind's display word
    project: str
    stage: str         # opened, committed, pushed, loaded, decided or published
    age_hours: float | None
    next_step: str


def _word(kind: str) -> str:
    from asset_model import one_off_kinds

    plug = one_off_kinds.get(kind)
    return plug.singular if plug else kind


def _next(stage: str, one_off_id: str, folder: Path, *, has_database: bool = True,
          address: str | None = None) -> str:
    """The next step - NEVER ONE THAT WOULD BE REFUSED (REQ-PIPE-442 criterion
    10 as amended 2026-11-22): a published one-off is not loaded again
    (REQ-PIPE-443 criterion 7), and one whose database is gone has nothing
    left to decide or drop."""
    rel = folder
    try:
        rel = folder.relative_to(assets.ROOT)
    except ValueError:
        pass
    if stage == "published":
        if not has_database:
            return f"none - its page is published at {address}"
        return (f"mothman one-off drop --id {one_off_id}, or decide again with "
                f"mothman one-off decide --id {one_off_id}")
    return {"opened": f"git add {rel} && git commit && git push",
            "committed": "git push",
            "pushed": f"mothman one-off load --id {one_off_id} <package>",
            "loaded": f"mothman one-off publish --id {one_off_id}, or drop it with "
                      f"mothman one-off drop --id {one_off_id}",
            "decided": f"mothman one-off publish --id {one_off_id}"}[stage]


def _published_at(kind: str, one_off_id: str) -> str | None:
    """The address of the one-off's published page, read from its kind's
    destination (criterion 1 as amended 2026-11-22), or None - including
    where the destination cannot be read, which `list` does not fail on."""
    from qa_tools.common import one_off_publish

    try:
        found = one_off_publish.published(kind, one_off_id)
    except Exception:  # noqa: BLE001 - list shows the stage it can read
        return None
    return found.address if found is not None else None


def rows(ages: dict[str, float] | None) -> list[Row]:
    """Every one-off, with its stage, its database's age and its next step."""
    from asset_model import config_yaml
    from qa_tools.common import one_off_load

    out = []
    for kind, name in assets.one_offs():
        folder = assets.one_offs_root() / kind / name
        doc = config_yaml.load(folder / "data-asset.yaml") \
            if (folder / "data-asset.yaml").is_file() else {}
        db = one_off_load.database_name(name)
        age = (ages or {}).get(db)
        # THE DATABASE'S MARK, THEN THE DESTINATION, THEN GIT (REQ-PIPE-442
        # criteria 1 and 10 as amended 2026-11-22): decide and publish re-mark
        # the database; a page with no database left is still published.
        address = None
        if age is not None:
            stage = getattr(ages, "stages", {}).get(db) or "loaded"
        else:
            address = _published_at(kind, name)
            stage = "published" if address else git_stage(folder)
        out.append(Row(name, _word(kind), str((doc or {}).get("project") or "(no project)"),
                       stage, age, _next(stage, name, folder, has_database=age is not None,
                                         address=address)))
    return out


def stray_databases(ages: dict[str, float] | None) -> dict[str, float]:
    """One-off databases on the server: every supply_<name> marked as a
    one-off's (database_ages), with or without its folder still here - never
    an enduring asset's, whatever it is named (the mock run of 2026-11-22
    listed supply_daily_c, an enduring asset's database on a suffixed DSN)."""
    marked = getattr(ages, "one_offs", frozenset())
    return {db: age for db, age in sorted((ages or {}).items()) if db in marked}


# ---- the drop ---------------------------------------------------------------

@dataclass(frozen=True)
class Item:
    """One thing the drop removes, and what it holds."""

    what: str          # how it is named to the person
    holds: str         # its counts
    kind: str          # 'database' or 'path'
    target: str        # the database's name, or the path


def _files(path: Path) -> int:
    return sum(1 for p in path.rglob("*") if p.is_file() or p.is_symlink()) if path.is_dir() \
        else 1


def _database_holds(name: str, url: str) -> str:
    import psycopg

    from qa_tools.common import supply_db

    with psycopg.connect(supply_db.on_server(url, name), autocommit=True,
                         application_name="mothman:one-off-drop") as conn:
        tables = conn.execute(
            "SELECT schemaname, relname FROM pg_stat_user_tables").fetchall()
        rows = 0
        for schema, table in tables:
            rows += conn.execute(f'SELECT count(*) FROM "{schema}"."{table}"').fetchone()[0]
    return f"{len(tables)} table(s), {rows} row(s)"


def _shown(path) -> str:
    """A state path as a person reads it: its tree and its own folder, as
    `data/<id>` - taken from the resolver's path, wherever the state root is."""
    from pathlib import Path

    path = Path(path)
    return f"{path.parent.name}/{path.name}"


def inventory() -> list[Item]:
    """Everything the drop of the selected one-off would remove, each with what
    it holds - only what is there."""
    from qa_tools.common import one_off_checks, one_off_load

    asset = assets.selected()
    folder = assets.committed_folder()
    out = []
    url = server()
    db = one_off_load.database_name(asset.name)
    if url is not None and db in (database_ages() or {}):
        out.append(Item(f"the database {db}", _database_holds(db, url), "database", db))
    # THE RESOLVER'S PATHS, NAMED AS THEY ARE (REQ-PIPE-342 criterion 6): the
    # words show where each one is rather than building a path of their own.
    for path, what in ((asset.data, f"{_shown(asset.data)}/ (its filed files, check workspace "
                                     f"{one_off_checks.WORKSPACE} and dbt scratch)"),
                       (asset.reports, f"{_shown(asset.reports)}/")):
        if path.exists():
            out.append(Item(what, f"{_files(path)} file(s)", "path", str(path)))
    for name in DBT_ARTEFACTS:
        path = folder / "dbt" / name
        if path.exists() or path.is_symlink():
            out.append(Item(f"its dbt {name}", f"{_files(path)} file(s)", "path", str(path)))
    return out


def remove(item: Item) -> None:
    """Remove one item - raising where it cannot be removed."""
    if item.kind == "database":
        from psycopg import sql

        with _admin(server()) as conn:
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                sql.Identifier(item.target)))
        return
    path = Path(item.target)
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)
