"""A real deployment's asset, in a copy of the repository (REQ-PIPE-385
criteria 1 and 14).

`make(tmp, deliveries)` copies the tracked tree and adds assets/registry/:
the daily asset's configuration with its synthetic/ folder left out, every
check id renamed to the new asset, `synthetic: true` dropped and no offset
date anywhere - a daily calendar and participation from a fixed date. The
supplies are copied in already made (the generator is what such a deployment
does not have), and the copy is committed, since a build links to a commit.

NOT A PROJECT EXTRACTION (Keith, 2026-11-18): REQ-PIPE-379 criterion 5 wanted
one fixture for both tests, and its `no_calendar: never` shape turned out
never to have run end to end - plans/running-thoughts.md #141, scoped
separately.

`mothman(tree, env, *argv)` runs the CLI there with the generator,
synthetic_data_generator, scenarios/ and the bootstrap package blocked at
find_spec - in the CLI's own process and in every Python process it starts,
through a sitecustomize.py on PYTHONPATH - so what the CLI detects and what
is blocked agree (REQ-PIPE-385 criterion 3).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

import tree_copy

ASSET, SOURCE = "registry", "daily"
AGENCY, COLLECTION, SHORT = "registry-services", "civil-registration", "bdm"
DATASET, TABLE = "birth-registrations", "birth_registrations"
BLOCKED = ("generator", "synthetic_data_generator", "scenarios", "bootstrap")
ROOT = tree_copy.ROOT

_SKIP = shutil.ignore_patterns("synthetic", "dbt_packages", "target", "logs", "__pycache__")
_ID = re.compile(rf"(?<![\w-]){SOURCE}(?=[.:]{AGENCY}[.:])")

_SITECUSTOMIZE = f'''"""Blocks the synthetic side at find_spec, as a real deployment lacks it."""
import sys
for _name in {BLOCKED!r}:
    sys.modules[_name] = None
'''

_CHANGELOG = [{"date": "2026-11-18", "author": "REQ-PIPE-385",
               "change": "A real deployment's fixture asset."}]


def _data_asset(folder: Path) -> None:
    """The daily asset's hierarchy and zone, as a real asset declares them:
    no `synthetic: true`, and every setting from a fixed date."""
    source = (folder / "data-asset.yaml").read_text()
    head = source.split("\nhierarchy:\n", 1)[1]
    hierarchy = yaml.safe_load("hierarchy:\n" + head)["hierarchy"]
    # ONE COLLECTION, THE ONE WHOSE SUPPLIES ARRIVE (_one_collection).
    hierarchy["agencies"] = [
        {**a, "collections": [c for c in a["collections"] if c["id"] == COLLECTION]}
        for a in hierarchy["agencies"] if a["id"] == AGENCY]
    doc = {
        "data_asset_id": ASSET,
        "timezone": {"versions": [{"effective_from": "1970-01-01", "zone": "Australia/Perth",
                                   "changelog": _CHANGELOG}]},
        "ticket_policy": "needs-action",
        "ticket_repository": "keithamoss/data-poc",
        "postgres_major": 16,
        "amber_setting": {"versions": [{"effective_from": "2013-01-01", "value": "promote",
                                        "changelog": _CHANGELOG}]},
        "replacement_setting": {"versions": [{"effective_from": "2013-01-01", "value": "never",
                                              "changelog": _CHANGELOG}]},
        "hierarchy": hierarchy,
    }
    (folder / "data-asset.yaml").write_text(yaml.safe_dump(doc, sort_keys=False))


def _calendar(folder: Path) -> None:
    """A daily calendar and participation from a fixed date before the
    supplies, each due at 14:00 on its day."""
    doc = {
        "calendars": [{"name": "daily", "description": "Every day, from a fixed date.",
                       "versions": [{"effective_from": "2025-12-01", "claim_window": "4h",
                                     "cadence": {"rule": "daily"}, "changelog": _CHANGELOG}]}],
        "collections": [{"id": COLLECTION, "files_go_to_period": {"versions": [
            {"effective_from": "2025-12-01", "value": 0, "changelog": _CHANGELOG}]}}],
        "datasets": [{"id": DATASET, "participation": {"versions": [
            {"effective_from": "2025-12-01", "expected_time": "14:00", "days_before": 0,
             "grace": "1h", "changelog": _CHANGELOG}]}}],
    }
    (folder / "calendar.yaml").write_text(yaml.safe_dump(doc, sort_keys=False))


def _one_collection(folder: Path) -> None:
    """A real asset of Birth Registrations' collection alone, whose two
    supplies are the ones that arrived. The daily asset holds others since
    Mental Health joined it (REQ-QAC-350, 2026-11-18); copied with their
    configuration and none of their supplies, the build refused a collection
    with no data. Every other collection's agency folder, adapter, dbt folders
    and presentation entries go, so no gate finds a file for a collection the
    hierarchy does not hold."""
    others = [c for c in (folder / "collections").glob("*.py")
              if c.stem not in ("__init__", COLLECTION.replace("-", "_"))]
    for adapter in others:
        cid = adapter.stem.replace("_", "-")
        adapter.unlink()
        for sub in ("models", "tests", "retired"):
            shutil.rmtree(folder / "dbt" / sub / cid, ignore_errors=True)
    for agency in folder.iterdir():
        if agency.is_dir() and agency.name not in (AGENCY, "collections", "dbt") \
                and any(agency.glob("*-contract.yaml")):
            shutil.rmtree(agency)
    presentation = folder / "presentation.yaml"
    doc = yaml.safe_load(presentation.read_text())
    doc["agencies"] = {k: v for k, v in (doc.get("agencies") or {}).items() if k == AGENCY}
    doc["collections"] = {k: v for k, v in (doc.get("collections") or {}).items() if k == COLLECTION}
    presentation.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))


def make(tmp: Path, deliveries: Path, receipts: Path) -> Path:
    tree = tree_copy.copy_tracked_tree(Path(tmp) / "tree")
    folder = tree / "assets" / ASSET
    shutil.copytree(ROOT / "assets" / SOURCE, folder, ignore=_SKIP)
    for path in folder.rglob("*"):
        if path.is_file() and path.suffix in (".yaml", ".yml"):
            text = path.read_text()
            renamed = _ID.sub(ASSET, text)
            if renamed != text:
                path.write_text(renamed)
    people = folder / "people.yaml"
    people.write_text(people.read_text().replace(f"data_asset: {SOURCE}\n", f"data_asset: {ASSET}\n"))
    _data_asset(folder)
    _calendar(folder)
    _one_collection(folder)
    assert not (folder / "synthetic").exists()
    (folder / "dbt" / "dbt_packages").symlink_to(ROOT / "assets" / SOURCE / "dbt" / "dbt_packages")
    if (ROOT / "node_modules").exists():
        (tree / "node_modules").symlink_to(ROOT / "node_modules")
    data = tree / "data" / ASSET
    shutil.copytree(deliveries, data / "deliveries")
    shutil.copytree(receipts, data / "receipts")
    blocker = Path(tmp) / "blocked"
    blocker.mkdir()
    (blocker / "sitecustomize.py").write_text(_SITECUSTOMIZE)
    git = ["git", "-c", "user.email=t@example.com", "-c", "user.name=t"]
    subprocess.run(["git", "init", "-q"], cwd=tree, check=True)
    added = subprocess.run([*git, "add", "-A"], cwd=tree, capture_output=True, text=True)
    assert added.returncode == 0, added.stderr
    subprocess.run([*git, "commit", "-qm", "a real deployment's asset"], cwd=tree, check=True)
    return tree


def env(tree: Path, dsn: str) -> dict:
    """The CLI's environment in the copy: the asset, a database of its own,
    and the synthetic side blocked in every Python process it starts. `uv
    run` uses this checkout's environment rather than syncing one in the
    copy."""
    return {**os.environ, "MOTHMAN_ASSET": ASSET, "MOTHMAN_SUPPLY_DSN": dsn,
            "MOTHMAN_ENVIRONMENT": "test", "NO_COLOR": "1", "COLUMNS": "200",
            # THE COPY'S OWN CODE FIRST, so `uv run mothman` - whose console
            # script this checkout's environment installed - runs the copy.
            "PYTHONPATH": os.pathsep.join([str(tree.parent / "blocked"), str(tree)]),
            "UV_PROJECT_ENVIRONMENT": str(Path(sys.prefix)), "UV_NO_SYNC": "1"}


def mothman(tree: Path, environ: dict, *argv: str, stdin=subprocess.DEVNULL,
            timeout: int = 1800) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "cli.app", *argv], cwd=tree, env=environ,
                          capture_output=True, text=True, timeout=timeout, stdin=stdin)


def fresh_database(name: str) -> str:
    """An empty database marked as the fixture asset's test environment
    (REQ-PIPE-107), which the copy's checkout is configured for."""
    import psycopg

    from qa_tools.common import db_identity

    admin = os.environ["MOTHMAN_TEST_DSN"]
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{name}"')
    info = psycopg.conninfo.conninfo_to_dict(admin)
    info["dbname"] = name
    dsn = psycopg.conninfo.make_conninfo(**info)
    with psycopg.connect(dsn, autocommit=True) as conn:
        db_identity.mark(conn, db_identity.Identity(ASSET, "test"))
    return dsn
