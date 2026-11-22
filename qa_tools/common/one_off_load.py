"""What a one-off load refuses before it reads or connects to anything
(REQ-PIPE-440 criteria 8, 9 and 12), and the deployment's one local dbt_utils
copy (criterion 12).

THE REFUSALS ARE THE LOAD'S, the load itself is REQ-PIPE-442's: it asks
`refusals()` first and stops on any.

- The recipe beside the package no longer matches the digest the folder
  records (criterion 8): both digests named.
- The folder, or the kind's template it reads live, has uncommitted changes or
  untracked files, or the commit holding it is not on the remote branch the
  working branch tracks (criterion 9): the git commands that would commit and
  push it, filled in, and the reason. A push is not a GitHub API call
  (REQ-PIPE-446 criterion 14). The gitignored dbt artefacts (criterion 11)
  never show.
- No local dbt_utils copy, or one at another revision than the enduring
  assets lock (criterion 12): naming the setup command.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from asset_model import assets

SETUP_COMMAND = "mothman one-off setup-dbt-utils"
#: What the setup records beside the copy: the revision it installed.
MARKER = ".mothman-dbt-utils.json"


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def _repo_of(path: Path) -> Path | None:
    got = _git(["rev-parse", "--show-toplevel"], path if path.is_dir() else path.parent)
    return Path(got.stdout.strip()) if got.returncode == 0 else None


def git_refusal(path: Path, what: str) -> str | None:
    """Why `path` cannot be loaded from as it stands in git, with the commands
    that fix it - or None where it is committed and on the tracked remote
    branch (criterion 9)."""
    path = Path(path)
    repo = _repo_of(path)
    if repo is None:
        return f"{what} ({path}) is not in a git repository, so no commit holds it."
    rel = path.resolve().relative_to(repo.resolve()).as_posix()
    reason = ("the published page names the commit it ran from, and only a pushed commit "
              "is one anyone else can find.")
    dirty = _git(["status", "--porcelain", "--untracked-files=all", "--", rel], repo).stdout
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], repo).stdout.strip() or "<branch>"
    upstream = _git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], repo)
    remote, _, remote_branch = (upstream.stdout.strip().partition("/")
                                if upstream.returncode == 0 else ("origin", "", branch))
    push = f"git push {remote} {remote_branch or branch}"
    if dirty.strip():
        return (f"{what} ({rel}) has uncommitted changes or untracked files. Commit and push "
                f"it first:\n  git add {rel}\n  git commit -m \"<why>\"\n  {push}\n"
                f"The reason: {reason}")
    if upstream.returncode != 0:
        return (f"{what} ({rel}) is committed, but the branch {branch!r} tracks no remote "
                f"branch. Push it first:\n  git push -u {remote} {branch}\nThe reason: {reason}")
    last = _git(["log", "-1", "--format=%H", "--", rel], repo).stdout.strip()
    if not last:
        return (f"{what} ({rel}) is in no commit. Commit and push it first:\n  git add {rel}\n"
                f"  git commit -m \"<why>\"\n  {push}\nThe reason: {reason}")
    on_remote = _git(["merge-base", "--is-ancestor", last, "@{u}"], repo).returncode == 0
    if not on_remote:
        return (f"{what} ({rel}) is committed but its commit is not on {remote}/"
                f"{remote_branch}. Push it first:\n  {push}\nThe reason: {reason}")
    return None


def digest_refusal(folder: Path, package_location: str, *, s3_client=None) -> str | None:
    """Criterion 8: the recipe beside the package against the folder's record."""
    from asset_model.kinds import extraction_folder, extraction_recipe

    recorded = extraction_folder.recorded(folder)["recipe_digest"]
    now = extraction_recipe.recipe_digest(package_location, s3_client=s3_client)
    if now != recorded:
        return (f"the recipe at {package_location} no longer matches the one {folder} was "
                f"generated from: the folder records {recorded}, the recipe reads {now}. A "
                f"changed recipe is a new extraction.")
    return None


# ---- the local dbt_utils copy (criterion 12) ---------------------------------

def locked_revision() -> str:
    """The dbt_utils revision the enduring assets lock (the dbt packages gate
    holds them equal)."""
    from asset_model import config_yaml

    first = assets.every()[0]
    lock = config_yaml.load(first.dbt_project / "package-lock.yml")
    return next(p for p in lock["packages"] if p.get("name") == "dbt_utils")["revision"]


def dbt_utils_path() -> Path | None:
    """Where this environment keeps the copy, or None where it names none."""
    from qa_tools.common import environments

    env = environments.current()
    if not env.one_off_dbt_utils:
        return None
    path = Path(env.one_off_dbt_utils)
    return path if path.is_absolute() else assets.ROOT / path


def dbt_utils_refusal() -> str | None:
    path = dbt_utils_path()
    if path is None:
        return ("this environment names no one_off_dbt_utils in assets/environments.yaml, so "
                "a one-off's dbt project has no local dbt_utils to read.")
    marker = path / MARKER
    if not marker.is_file():
        return (f"no local dbt_utils copy at {path} - run `{SETUP_COMMAND}` once for this "
                f"deployment. A load makes no network fetch.")
    have = json.loads(marker.read_text()).get("revision")
    want = locked_revision()
    if have != want:
        return (f"the local dbt_utils copy at {path} is revision {have}, and the enduring "
                f"assets lock {want} - run `{SETUP_COMMAND}` again.")
    return None


def _installed_from_an_asset() -> Path | None:
    """An enduring asset's own dbt_packages/dbt_utils, where `mothman env
    dbt-deps` has installed it at the locked revision - copied without any
    network fetch."""
    for a in assets.every():
        found = a.dbt_packages / "dbt_utils"
        if (found / "dbt_project.yml").is_file():
            return found
    return None


def _fetch_locked(into: Path) -> None:
    """dbt deps over the enduring assets' own packages.yml and lock, in a
    scratch project - the one network fetch, made by the setup step only."""
    first = assets.every()[0]
    with tempfile.TemporaryDirectory(prefix="mothman-dbt-utils-") as tmp:
        work = Path(tmp)
        for name in ("packages.yml", "package-lock.yml"):
            shutil.copy(first.dbt_project / name, work / name)
        (work / "dbt_project.yml").write_text(
            "name: mothman_dbt_utils_setup\nversion: '1.0.0'\nconfig-version: 2\n")
        subprocess.run(["dbt", "deps", "--project-dir", str(work)], check=True,
                       capture_output=True, text=True)
        shutil.copytree(work / "dbt_packages" / "dbt_utils", into)


def setup_dbt_utils() -> Path:
    """Install the deployment's one local dbt_utils copy, at the locked
    revision, into the path its configuration names - from an enduring asset's
    installed copy where there is one, else by one dbt deps."""
    path = dbt_utils_path()
    if path is None:
        raise RuntimeError(dbt_utils_refusal())
    if path.exists():
        shutil.rmtree(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    source = _installed_from_an_asset()
    if source is not None:
        shutil.copytree(source, path)
    else:
        _fetch_locked(path)
    (path / MARKER).write_text(json.dumps({"revision": locked_revision()}) + "\n")
    return path


def refusals(folder: Path, package_location: str, template: Path, *, s3_client=None) -> list[str]:
    """Everything a load refuses on, before it reads or connects to anything."""
    found = [r for r in (digest_refusal(folder, package_location, s3_client=s3_client),
                         git_refusal(folder, "the one-off's folder"),
                         git_refusal(template, "the kind's template"),
                         dbt_utils_refusal()) if r]
    return found


# ---- the load (REQ-PIPE-442 criteria 3 to 5; REQ-QAC-441 criterion 3) -------

class LoadRefused(RuntimeError):
    """The load cannot go ahead. Its message says why and what to do."""


#: Where a one-off's database records which package it holds and the commit it
#: was loaded at (REQ-PIPE-442 criterion 3, REQ-DASH-444 criterion 8).
LOAD_TABLE = "qa.one_off_load"
_LOAD_DDL = f"""
CREATE TABLE IF NOT EXISTS {LOAD_TABLE} (
    only_row        boolean PRIMARY KEY DEFAULT true CHECK (only_row),
    one_off_id      text NOT NULL,
    package_digest  text NOT NULL,
    recipe_digest   text NOT NULL,
    loaded_commit   text NOT NULL,
    deliveries      jsonb NOT NULL DEFAULT '{{}}',
    loaded_at       timestamptz NOT NULL DEFAULT now()
)"""


def package_digest(location: str, files, *, s3_client=None) -> str:
    """sha256 over every file of the package, by name and content - what
    tells a resumed load (the same package) from a re-send (another)."""
    import hashlib

    from asset_model.kinds import extraction_recipe

    source = extraction_recipe.source(location, s3_client)
    h = hashlib.sha256()
    for name in sorted(files):
        h.update(name.encode() + b"\0" + hashlib.sha256(source.read(name)).digest())
    return h.hexdigest()


def database_name(one_off_id: str) -> str:
    from qa_tools.common import supply_db

    return f"{supply_db.ASSET_DATABASE_PREFIX}{one_off_id}"


def _server() -> str:
    from qa_tools.common import supply_db

    server = os.environ.get(supply_db.SERVER_ENV)
    if not server:
        raise LoadRefused(f"{supply_db.SERVER_ENV} is not set: a one-off's database is created "
                          f"on the configured local server it names.")
    return server


def ensure_database(one_off_id: str, digest: str, recipe_digest: str, commit: str) -> str:
    """Create supply_<id> on the configured local server and mark it as the
    one-off's, recording the package's digest and the commit - or, where it
    already exists, RESUME a load of the same package and REFUSE another's
    (criterion 5). Returns 'created' or 'resumed'."""
    import psycopg
    from psycopg import sql

    from qa_tools.common import db_identity, environments, supply_db

    server = _server()
    name = database_name(one_off_id)
    with psycopg.connect(supply_db.on_server(server, "postgres"), autocommit=True,
                         application_name="mothman:one-off-load") as admin:
        exists = admin.execute("SELECT 1 FROM pg_database WHERE datname = %s",
                               [name]).fetchone() is not None
        if not exists:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    dsn = supply_db.on_server(server, name)
    with psycopg.connect(dsn, autocommit=True, application_name="mothman:one-off-load") as conn:
        if exists:
            held = _held(conn)
            if held is None:
                raise LoadRefused(f"{name} exists on the server and records no one-off package - "
                                  f"it is not this load's to use. Nothing was loaded.")
            if held[0] != digest:
                raise LoadRefused(
                    f"{name} already holds another package (digest {held[0]}), and this one is "
                    f"{digest}. A re-send is a new one-off, with an id of its own. Nothing was "
                    f"loaded.")
            return "resumed"
        db_identity.mark(conn, db_identity.Identity(one_off_id, environments.current().id))
        conn.execute("CREATE SCHEMA IF NOT EXISTS qa")
        conn.execute(_LOAD_DDL)
        # ITS RELEASE DECISIONS' TABLE, from the start (REQ-PIPE-435), so the
        # publisher reads an empty one rather than none.
        from qa_tools.common import one_off_decision

        one_off_decision.ensure_table(conn)
        conn.execute(f"INSERT INTO {LOAD_TABLE} (one_off_id, package_digest, recipe_digest, "
                     "loaded_commit) VALUES (%s, %s, %s, %s)",
                     [one_off_id, digest, recipe_digest, commit])
    return "created"


def _held(conn):
    found = conn.execute("SELECT to_regclass(%s)", [LOAD_TABLE]).fetchone()[0]
    if found is None:
        return None
    return conn.execute(f"SELECT package_digest, deliveries FROM {LOAD_TABLE}").fetchone()


def recorded_load(conn) -> dict | None:
    """What supply_<id> records about its load: the package digest, the
    recipe digest and the commit (REQ-DASH-444 criterion 8)."""
    raw = getattr(conn, "raw", conn)
    if raw.execute("SELECT to_regclass(%s)", [LOAD_TABLE]).fetchone()[0] is None:
        return None
    row = raw.execute(f"SELECT one_off_id, package_digest, recipe_digest, loaded_commit, "
                      f"deliveries FROM {LOAD_TABLE}").fetchone()
    return dict(zip(("one_off_id", "package_digest", "recipe_digest", "loaded_commit",
                     "deliveries"), row)) if row else None


def _remember_delivery(collection_id: str, delivery: str) -> None:
    from qa_tools.common import supply_db

    with supply_db.connect(label="mothman:one-off-load") as conn:
        conn.raw.execute(f"UPDATE {LOAD_TABLE} SET deliveries = deliveries || %s::jsonb",
                         [json.dumps({collection_id: delivery})])


def head_commit(path: Path) -> str:
    repo = _repo_of(Path(path))
    got = _git(["rev-parse", "HEAD"], repo) if repo else None
    if got is None or got.returncode != 0:
        raise LoadRefused(f"{path} is in no git commit, so the load cannot record the commit "
                          f"it ran at.")
    return got.stdout.strip()


def _completed(run_id: str) -> bool:
    from qa_tools.common import qa_store, supply_db

    with supply_db.connect(read_only=True, label="mothman:one-off-load") as conn:
        if conn.execute("SELECT to_regclass(?)", [f"{qa_store.SCHEMA}.run"]).fetchone()[0] \
                is None:
            return False
        rows = conn.execute(f'SELECT completed_at FROM "{qa_store.SCHEMA}".run '
                            "WHERE run_key = ?", [run_id]).fetchall()
    return bool(rows) and rows[0][0] is not None


def load(package, *, run_by: str, s3_client=None, say=print) -> dict:
    """Load the selected one-off's package into its own database, after the
    caller has gated its folder (criterion 3): its database created or resumed,
    its check workspace materialised from the folder and the kind's template,
    one delivery per collection filed from the declared files present, each
    arrival staged, checked by all four tools and recorded, and the package's
    own facts - a declared table that never arrived, a file nobody declared -
    recorded as failing default-layer results (REQ-QAC-441 criterion 3).
    Returns what it did."""
    import tempfile

    from asset_model import collections, config_yaml
    from asset_model.kinds import extraction_checks
    from qa_tools.common import dbt_common, hand_filing, one_off_checks, one_off_package
    from qa_tools.common import delivery as delivery_mod
    from qa_tools.tools import orchestrate, run_dbt, stage

    folder = assets.committed_folder()
    one_off_id = folder.name
    digest = package_digest(package.location, package.files, s3_client=s3_client)
    commit = head_commit(folder)
    how = ensure_database(one_off_id, digest, package.recipe.digest, commit)
    say(f"{'Created' if how == 'created' else 'Resuming the load into'} "
        f"{database_name(one_off_id)}.")
    workspace = one_off_checks.materialise(dbt_utils_path())
    assets.use_workspace(workspace)
    try:
        dbt_common.install_packages(assets.selected().dbt_project, run_dbt.PROFILES_DIR)
        doc = config_yaml.load(folder / "data-asset.yaml") or {}
        tables = extraction_checks.declared(doc, config_yaml.load(folder / "calendar.yaml"))
        found = one_off_package.findings(package.files, tables, "recipe.json")
        from qa_tools.common import supply_db

        with supply_db.connect(read_only=True, label="mothman:one-off-load") as conn:
            deliveries = dict((recorded_load(conn) or {}).get("deliveries") or {})
        home = one_off_package.home_of(tables)
        received = {}
        report = {"database": database_name(one_off_id), "how": how, "runs": [],
                  "missing": [t.dataset_id for t in found.missing],
                  "undeclared": list(found.undeclared), "results": []}
        source = None
        with tempfile.TemporaryDirectory(prefix="mothman-one-off-") as tmp:
            for coll in collections.all_collections():
                mine = [t for t in found.present if t.collection_id == coll.id]
                if not mine:
                    continue
                if coll.id in deliveries:
                    filed_name = deliveries[coll.id]
                else:
                    if source is None:
                        from asset_model.kinds import extraction_recipe

                        source = extraction_recipe.source(package.location, s3_client)
                    paths = []
                    for t in mine:
                        local = Path(tmp) / t.file
                        local.parent.mkdir(parents=True, exist_ok=True)
                        local.write_bytes(source.read(t.file))
                        paths.append(local)
                    filed = hand_filing.file_supply(
                        paths, coll.id, coll.run_prefix,
                        stated_original={"*": delivery_mod.NOT_KNOWN}, route="folder",
                        filed_by=run_by)
                    filed_name = filed.delivery_name
                    _remember_delivery(coll.id, filed_name)
                    say(f"Filed {coll.name} as delivery {filed_name}.")
                arrivals = [a for a in hand_filing.arrivals_of(
                    hand_filing.Filed(filed_name, "", (), None), coll.id, coll.run_prefix)]
                todo = [a for a in arrivals if not _completed(a.run_id)]
                for a in arrivals:
                    received.setdefault("at", a.received_at)
                    report["runs"].append(a.run_id)
                for a in todo:
                    stage.stage_arrival(coll.id, a)
                    if home.collection_id == coll.id and \
                            home.dataset_id in a.files_by_dataset:
                        one_off_package.record_undeclared(found, a.run_id, home.dataset_id,
                                                          delivery=filed_name)
                if todo:
                    report["results"] += orchestrate.run_arrivals(coll.id, todo, run_by)
        at = received.get("at")
        if at is None:
            from asset_model import asset_time

            at = asset_time.now()
        for t in found.missing:
            run_id = one_off_package.run_id_for(t.table, at)
            report["runs"].append(run_id)
            if _completed(run_id):
                continue
            one_off_package.record_missing(
                t, at, run_by, delivery=deliveries.get(t.collection_id),
                undeclared=found if t.dataset_id == home.dataset_id else None)
            say(f"{t.file} is declared and did not arrive - recorded as failing.")
        return report
    finally:
        assets.use_workspace(None)
