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
    import yaml

    first = assets.every()[0]
    lock = yaml.safe_load((first.dbt_project / "package-lock.yml").read_text())
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
