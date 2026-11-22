"""`mothman check` over one-off folders (REQ-PIPE-448 criteria 2 and 3).

FULL GATES ON WHAT CHANGED, A DIGEST PASS OVER THE REST (Keith 2026-11-21,
round 5 Q2 (b)): each per-asset gate is a subprocess, so gating 200 folders in
full would be about 2,000 interpreter starts. A folder changed since the diff
base is gated in full - through the hidden `mothman one-off gate --id`
(Keith 2026-11-22) - and its digest checked too; every other folder is checked,
in this one process, against the digest it recorded when generated
(REQ-PIPE-440 criterion 5). Untracked files count in both; the gitignored dbt
artefacts (REQ-PIPE-440 criterion 11) are left out.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from asset_model import assets

DIGEST_FILE = "generated.sha256.json"
#: dbt's own artefacts under a one-off's dbt/ - gitignored, never configuration.
_DBT_ARTEFACTS = ("dbt/target/", "dbt/logs/", "dbt/dbt_packages/")
_DBT_LOCK = "dbt/package-lock.yml"


def _artefact(rel: str) -> bool:
    return rel == _DBT_LOCK or any(rel.startswith(p) for p in _DBT_ARTEFACTS)


def files_now(folder: Path) -> list[str]:
    """Every file in the folder as it is now, tracked or not, but the digest
    record and dbt's own artefacts."""
    return sorted(rel for p in folder.rglob("*") if p.is_file()
                  for rel in [p.relative_to(folder).as_posix()]
                  if rel != DIGEST_FILE and not _artefact(rel))


def digest_problem(folder: Path) -> str | None:
    """Where the folder no longer matches its recorded digest, naming the
    folder and the first file that differs - or None."""
    folder = Path(folder)
    record = folder / DIGEST_FILE
    if not record.is_file():
        return f"{folder}: no {DIGEST_FILE} - it was not generated, or the record was removed."
    recorded = json.loads(record.read_text()).get("files") or {}
    now = files_now(folder)
    for rel in sorted(set(recorded) | set(now)):
        if rel not in now:
            return f"{folder}: {rel} is recorded in its digest and is not there."
        if rel not in recorded:
            return f"{folder}: {rel} is not one of its generated files (added by hand?)."
        if hashlib.sha256((folder / rel).read_bytes()).hexdigest() != recorded[rel]:
            return f"{folder}: {rel} differs from what was generated."
    return None


def _git(args, cwd) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def changed(path: Path, base: str | None = None) -> bool:
    """Whether anything under `path` changed since the diff base, committed or
    not - untracked files included."""
    from qa_tools.common import diff_base

    path = Path(path)
    top = _git(["rev-parse", "--show-toplevel"], path if path.is_dir() else path.parent)
    if top.returncode != 0:
        return True     # outside git, nothing says it is unchanged
    repo = Path(top.stdout.strip())
    rel = path.resolve().relative_to(repo.resolve()).as_posix()
    base = base or diff_base.diff_base(root=repo)
    if _git(["diff", "--name-only", base, "--", rel], repo).stdout.strip():
        return True
    return bool(_git(["status", "--porcelain", "--untracked-files=all", "--", rel],
                     repo).stdout.strip())


def gate_folder(label: str, one_off_id: str) -> tuple[int, str]:
    """One gate in full over one one-off folder, as a subprocess of its own
    (`mothman one-off gate --id`), carrying the one-offs root where it is not
    the repository's - never MOTHMAN_ASSET (REQ-PIPE-446 criterion 9)."""
    import os
    import sys

    env = {k: v for k, v in os.environ.items() if k != assets.ASSET_ENV}
    args = [sys.executable, "-m", "cli.app", "one-off", "gate", "--id", one_off_id]
    if assets.one_offs_root() != assets.ROOT / assets.ONE_OFFS:
        args += ["--root", str(assets.one_offs_root())]
    done = subprocess.run([*args, label], cwd=assets.ROOT, env=env, capture_output=True,
                          text=True)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def kind_pass(label: str, kind, *, base: str | None = None) -> dict:
    """{full, digest, failed: {id: why}} for one gate over every folder of one
    kind: changed folders gated in full and digest-checked, the rest by digest."""
    out = {"full": 0, "digest": 0, "failed": {}}
    for k, name in assets.one_offs():
        if k != kind.name:
            continue
        folder = assets.one_offs_root() / k / name
        if changed(folder, base):
            out["full"] += 1
            code, said = gate_folder(label, name)
            if code not in (0, 78):
                out["failed"][name] = said.strip().splitlines()[-1] if said.strip() else \
                    f"exit {code}"
                continue
        else:
            out["digest"] += 1
        problem = digest_problem(folder)
        if problem:
            out["failed"][name] = problem
    return out


def template_pass(kind, *, base: str | None = None) -> dict | None:
    """{gate: [problem]} for every gate the kind declares for its template
    (REQ-PIPE-448 criterion 6) - or None where the template has not changed
    since the diff base, or the kind has none."""
    template = assets.kind_template(kind.name)
    if not kind.template_gates or not template.is_dir() or not changed(template, base):
        return None
    return {name: list(check(template)) for name, check in sorted(kind.template_gates.items())}
