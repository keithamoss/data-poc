"""A command run for one asset never reads or writes the other asset's data/
or reports/ folder (REQ-PIPE-365 criterion 5, and its RELIABILITY NFR: one
asset's reset or failed bootstrap leaves the other's files untouched).

EACH COMMAND RUNS FOR REAL, as a person runs it - `python -m cli.app ...` in
a process of its own with MOTHMAN_ASSET and its own database - in a COPY of
this checkout, so the commands' own writes land in the copy's data/ and
reports/ and never this repository's (the suite never writes the real
reports/). The other asset's folders are populated first, every file
hashed, and compared byte for byte after every command, in both directions.
It READS ONLY ITS OWN REPORTS - the copy's - so it needs no deployment.

A BOOTSTRAP THAT FAILS PARTWAY (post-build-review #345): a real bootstrap
taking a checkpoint, stopped by an exception the moment the checkpoint is
saved - after it has generated its deliveries, run the real tools over the
arrivals before the checkpoint (dbt among them, in its own scratch folder)
and copied the database. The stop is put in by the process's launcher, a
few lines here, so no product code exists only for this test. Then the
checkpoint is listed and deleted through mothman.

A RESUME IS NOT RUN: it replays every arrival after the checkpoint, the
rest of the collection's history, which is many minutes; its database names
are the checkpoint ones tests/test_checkpoints.py covers per asset.

PORTABILITY (the requirement's NFR): the folders are made here, so the test
holds whether or not this checkout has a data/ or reports/ at all - a fresh
clone has neither.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parent.parent

#: The two assets, each run beside the other.
PAIRS = [("quarterly", "daily"), ("daily", "quarterly")]

#: A collection of each asset to generate, by its short name - the smallest
#: generation each asset has (about 20 seconds each).
GENERATED = {"quarterly": "cp", "daily": "bdm"}

#: Where each asset's checkpoint is taken: the first arrival of its second
#: package, so as few arrivals as possible are checked before it. A change to
#: the synthetic history that moves it is refused loudly by the bootstrap
#: ("not the first of its package"), never passed over.
CHECKPOINT_BEFORE = {"quarterly": 6, "daily": 2}

#: Runs `mothman` with the checkpoint's save wrapped: once the copy is made,
#: it raises, so the bootstrap fails partway with its work so far on disk.
STOPPED_AFTER_CHECKPOINT = """
import runpy, sys
from bootstrap import checkpoints
_save = checkpoints.save
def save(*a, **k):
    cp = _save(*a, **k)
    raise RuntimeError("STOPPED BY THE TEST after checkpoint " + cp.name)
checkpoints.save = save
sys.argv = ["mothman", *sys.argv[1:]]
runpy.run_module("cli.app", run_name="__main__", alter_sys=True)
"""


def _checkout_copy(dest: Path) -> Path:
    """Every file git considers part of this checkout, copied - tracked, or
    new and not ignored, as the cache key reads it - with a git repository of
    its own so `pipeline cache-key` can list them there."""
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, check=True, capture_output=True).stdout.decode()
    copied = 0
    for rel in filter(None, listed.split("\0")):
        src = ROOT / rel
        if src.is_file():
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest / rel)
            copied += 1
    assert copied > 100, f"only {copied} files copied - this would check nothing"
    subprocess.run(["git", "init", "-q"], cwd=dest, check=True)
    # dbt's installed packages are ignored, so not copied above; the
    # bootstrap's real dbt run needs them (`mothman env dbt-deps`, a
    # documented setup step CI runs too).
    for asset in GENERATED:
        packages = ROOT / "assets" / asset / "dbt" / "dbt_packages"
        if not packages.is_dir():
            pytest.fail(f"{packages} is missing - run `MOTHMAN_ASSET={asset} uv run mothman "
                        f"env dbt-deps` first")
        shutil.copytree(packages, dest / "assets" / asset / "dbt" / "dbt_packages")
    return dest


def _populate(repo: Path, asset: str) -> None:
    """A folder of each kind criterion 1 names, and the two the state-path
    sweep added (dbt scratch, the ticket files), with something in each."""
    data, reports = repo / "data" / asset, repo / "reports" / asset
    files = {
        data / "deliveries" / "Extract A" / "a.csv": "id\n1\n",
        data / "receipts" / "Extract A" / "a.csv.json": json.dumps({"delivery": "Extract A"}),
        data / "generator_bookkeeping.json": json.dumps({"asset": asset}),
        data / "scenario_placements.json": json.dumps({"TS-1": asset}),
        data / "dbt_scratch" / "x" / "manifest.json": "{}",
        reports / f"results_{asset}.json": json.dumps({"asset": asset}),
        reports / "open_tickets.json": "[]",
        reports / "ticket_resolutions.json": "[]",
    }
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def _snapshot(repo: Path, asset: str) -> dict[str, str]:
    """Every file and folder under the asset's data/ and reports/, each file
    by the sha256 of its bytes."""
    out = {}
    for top in ("data", "reports"):
        base = repo / top / asset
        assert base.is_dir(), f"{base} was never populated - this would compare nothing"
        for p in sorted(base.rglob("*")):
            rel = str(p.relative_to(repo))
            out[rel] = "dir" if p.is_dir() else hashlib.sha256(p.read_bytes()).hexdigest()
    return out


@pytest.fixture
def database(supply_dsn):
    """A database per acting asset, of this test's own - never the worker's,
    which other tests use, and never a real supply database. Any checkpoint
    or resume copied from it is dropped afterwards too."""
    admin = os.environ["MOTHMAN_TEST_DSN"]
    tag = "".join(c for c in os.environ.get("MOTHMAN_TEST_DB_TAG", "") if c.isalnum())[:12]
    made = []

    def make(asset: str) -> str:
        name = f"mothman_beside_{tag + '_' if tag else ''}{asset}_{os.getpid()}"
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            conn.execute(f'CREATE DATABASE "{name}"')
        made.append(name)
        info = psycopg.conninfo.conninfo_to_dict(admin)
        info["dbname"] = name
        return psycopg.conninfo.make_conninfo(**info)
    yield make
    with psycopg.connect(admin, autocommit=True) as conn:
        for name in made:
            copies = conn.execute(
                "SELECT datname FROM pg_database WHERE shobj_description(oid, 'pg_database') "
                "LIKE %s", [f'%"source": "{name}"%']).fetchall()
            for (copy,) in copies:
                conn.execute(f'DROP DATABASE IF EXISTS "{copy}" WITH (FORCE)')
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def _env(asset: str, dsn: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("MOTHMAN_", "PYTEST_", "COV_CORE"))}
    env.update({"MOTHMAN_ASSET": asset, "MOTHMAN_SUPPLY_DSN": dsn,
                "MOTHMAN_ENVIRONMENT": "test",
                "MOTHMAN_TEST_DSN": os.environ["MOTHMAN_TEST_DSN"]})
    return env


def _mothman(repo: Path, env: dict, *args: str, input: str | None = None,
             ok: bool = True, launcher: str | None = None) -> subprocess.CompletedProcess:
    head = ["-c", launcher] if launcher else ["-m", "cli.app"]
    got = subprocess.run([sys.executable, *head, *args], cwd=repo, env=env,
                         input=input, capture_output=True, text=True, timeout=1200)
    if ok:
        assert got.returncode == 0, f"mothman {' '.join(args)}:\n{got.stdout}\n{got.stderr}"
    return got


@pytest.mark.parametrize("asset,other", PAIRS)
def test_each_command_leaves_the_other_assets_folders_byte_for_byte(
        tmp_path, database, asset, other):
    repo = _checkout_copy(tmp_path / "checkout")
    env = _env(asset, database(asset))
    # THE COPY'S CODE, NOT THIS CHECKOUT'S: otherwise every path below would
    # resolve to this repository's data/ and reports/.
    probe = subprocess.run([sys.executable, "-c", "import qa_tools; print(qa_tools.__file__)"],
                           cwd=repo, env=env, capture_output=True, text=True, check=True)
    assert probe.stdout.strip().startswith(str(repo)), probe.stdout
    _mothman(repo, env, "env", "mark", "--confirm", f"{asset}/test")

    # WITHOUT ITS TARGET TRIAL where it has one: the trial is a separate
    # tool run that writes nothing under data/, and costs minutes.
    short = GENERATED[asset]
    generate = (short, "generate-synthetic-data", "--yes")
    if "--skip-target-trial" in _mothman(repo, env, *generate, "--help").stdout:
        generate += ("--skip-target-trial",)

    _populate(repo, other)
    before = _snapshot(repo, other)
    assert len([v for v in before.values() if v != "dir"]) == 8

    def unchanged(what: str) -> None:
        assert _snapshot(repo, other) == before, (
            f"`mothman {what}` for {asset!r} changed {other!r}'s folders")

    # Criterion 1's paths, then criteria 2 and 3's commands.
    for args, typed in ((generate, None),
                        (("pipeline", "cache-key"), None),
                        (("pipeline", "checkpoint", "list"), None),
                        (("env", "reset-synthetic"),
                         f"delete all QA history and generated files for {asset}\n")):
        _mothman(repo, env, *args, input=typed)
        unchanged(" ".join(args))

    # THE FAILED BOOTSTRAP, PARTWAY: a checkpoint taken, then stopped.
    args = ("pipeline", "bootstrap", "--collection", short,
            "--checkpoint-before", str(CHECKPOINT_BEFORE[asset]), "--skip-target-trial")
    got = _mothman(repo, env, *args, ok=False, launcher=STOPPED_AFTER_CHECKPOINT)
    stopped = re.search(r"STOPPED BY THE TEST after checkpoint (\S+)", got.stdout + got.stderr)
    assert got.returncode != 0 and stopped, (
        f"the bootstrap was meant to stop after its checkpoint:\n{got.stdout}\n{got.stderr}")
    checkpoint = stopped.group(1)
    assert checkpoint.startswith(f"mothman_ckpt_{asset}_"), checkpoint
    assert any((repo / "data" / asset / "deliveries").iterdir()), \
        f"the bootstrap wrote no deliveries under data/{asset} before it stopped"
    assert (repo / "data" / asset / "dbt_scratch").is_dir(), \
        f"the bootstrap ran no dbt under data/{asset} before it stopped"
    unchanged(" ".join(args) + " (stopped after its checkpoint)")

    listed = _mothman(repo, env, "pipeline", "checkpoint", "list")
    assert checkpoint in listed.stdout, listed.stdout
    unchanged("pipeline checkpoint list")
    _mothman(repo, env, "pipeline", "checkpoint", "delete", "--yes", checkpoint)
    unchanged("pipeline checkpoint delete")

    # Criterion 4's commands, then a bootstrap refused for its arrival
    # number after regenerating to count them.
    for args in (("dashboard", "rebuild-results"), ("dashboard", "build-data")):
        _mothman(repo, env, *args)
        unchanged(" ".join(args))
    args = ("pipeline", "bootstrap", "--collection", short, "--checkpoint-before", "1")
    got = _mothman(repo, env, *args, ok=False)
    assert got.returncode != 0 and "choose 2 to" in got.stdout + got.stderr, (
        f"mothman {' '.join(args)} was meant to be refused for its arrival number:\n"
        f"{got.stdout}\n{got.stderr}")
    unchanged(" ".join(args))

    # AND THE COMMANDS DID WRITE - into their own asset's folder, so the
    # comparison above is beside a run that wrote something, not a no-op.
    assert any((repo / "reports" / asset).rglob("*.json")), \
        f"nothing was written under reports/{asset} - the commands did nothing"


#: The data asset this module's tests act for, unless a test says otherwise
#: (C11, Keith 2026-11-02: every test module names its asset). The commands
#: themselves run in processes of their own, each naming its asset.
pytestmark = pytest.mark.asset("quarterly")
