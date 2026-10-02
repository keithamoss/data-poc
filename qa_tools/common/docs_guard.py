"""What the docs-* explainer agents may read and write, and a check that
they kept to it (REQ-DOCS-124).

THREE LAYERS, because each one covers a gap in the others.

1. A READ GUARD, run as a PreToolUse hook on Read|Grep|Glob in every
   docs-* agent's own definition. It keeps them out of `.env*` (which
   holds the database password), `data/`, `reports/` and the eval set,
   and out of everything outside the repository. docs-critic may read
   nothing at all: it is given everything it needs in its prompt, and a
   critic that can browse the repository is no longer reading cold.
   Claude Code will not launch an agent with zero tools
   (code.claude.com/docs/en/sub-agents), so the critic has Read and
   this guard refuses every call it makes.

2. A WRITE GUARD, run as a PreToolUse hook on
   Write|Edit|MultiEdit|NotebookEdit. The writer may write explainer
   pages, glossary.yaml and the gitignored working folder; the
   illustrator pages and the working folder; nobody else anything - the
   critic, the fact-checker and the finding-checker write nothing. It
   is the ONLY guard for paths outside the repository - a shell rc
   file, ~/.claude/settings.json - because the snapshot below cannot
   see those.

3. A BEFORE/AFTER SNAPSHOT of the whole repository, run by /explain
   around each agent. It walks every file by path, size and
   modification time, INCLUDING gitignored paths, .venv and
   node_modules, and reports anything that changed outside the agent's
   write scope. `git status --ignored` is not enough and was rejected
   by the architect review: an ignored directory that already has
   contents collapses to one line, so a new file inside it is
   invisible - and a `.pth` file dropped into .venv is code execution
   on the next `uv run`.

EVERY DOUBT IS A REFUSAL. Input the guard cannot parse, a path it
cannot resolve, an agent it does not know - all deny. Paths are
resolved to their real location (following symlinks and `..`) before
they are compared, and compared as paths rather than strings, so
`docs/explainers2/` is not inside `docs/explainers/`.

A SEARCH ROOTED ABOVE A DENIED LOCATION IS REFUSED. Grep and Glob with
no `path` search the whole repository, which contains `data/` and the
eval set. Rather than trust the tool to skip ignored files (the eval
set is not ignored at all), the guard refuses the search and says to
search a narrower directory. That costs the writer a whole-repository
grep, which is the price of the guarantee.

THE HOOK MUST TURN ANY FAILURE INTO A BLOCK. Claude Code blocks a tool
call only on exit code 2; exit 1 is a non-blocking error and the call
PROCEEDS. So the agent definitions call this as
`uv run mothman docs guard-write <agent> || exit 2`, which also covers
`uv` or the import failing before this code runs.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

EXPLAINERS = Path("docs/explainers")
WORK = EXPLAINERS / "_work"
GLOSSARY_YAML = EXPLAINERS / "glossary.yaml"
EVALS = Path(".claude/skills/explain/evals")

# Relative to the repository root. `.env*` is matched by name below,
# because a new `.env.something` must be caught without a list edit.
DENIED_READ_DIRS = (Path("data"), Path("reports"), EVALS)

WRITING_AGENTS = {"docs-writer", "docs-illustrator"}
READING_AGENTS = {"docs-writer", "docs-illustrator", "docs-fact-checker", "docs-finding-checker"}
ALL_AGENTS = READING_AGENTS | {"docs-critic"}

# Files a person reviews that live beside the pages but that no agent
# may write, whatever its scope.
NEVER_WRITTEN = {EXPLAINERS / "glossary.md", EXPLAINERS / "concept-map.yaml"}

# Paths whose change /explain reports by name even when in scope,
# because Keith approves every glossary change.
NAMED_WHEN_CHANGED = {GLOSSARY_YAML, EXPLAINERS / "concept-map.yaml"}


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str = ""


def _deny(reason: str) -> Decision:
    return Decision(False, reason)


def _parse(payload: str) -> tuple[str, dict]:
    data = json.loads(payload)
    tool = data["tool_name"]
    tool_input = data["tool_input"]
    if not isinstance(tool, str) or not isinstance(tool_input, dict):
        raise ValueError("unexpected hook input shape")
    return tool, tool_input


def _resolve(raw: str, repo: Path) -> Path:
    """The real location of `raw`, relative paths taken from the repo.
    strict=False so a file about to be created still resolves - its
    parent's symlinks are followed all the same."""
    p = Path(raw)
    if not p.is_absolute():
        p = repo / p
    return p.resolve(strict=False)


def _relative_to_repo(path: Path, repo: Path) -> Path | None:
    repo = repo.resolve()
    if path == repo or path.is_relative_to(repo):
        return path.relative_to(repo)
    return None


def _is_env_file(rel: Path) -> bool:
    return any(part == ".env" or part.startswith(".env.") for part in rel.parts)


def _inside(rel: Path, base: Path) -> bool:
    return rel == base or rel.is_relative_to(base)


# ---------------------------------------------------------------- read


def guard_read(agent: str, payload: str, repo: Path = REPO_ROOT) -> Decision:
    try:
        return _guard_read(agent, payload, repo)
    except Exception as exc:  # noqa: BLE001 - every doubt is a refusal
        return _deny(f"the read guard could not check this call ({exc}), so it is refused")


def _guard_read(agent: str, payload: str, repo: Path) -> Decision:
    if agent not in ALL_AGENTS:
        return _deny(f"{agent!r} is not a docs-* agent this guard knows")
    tool, tool_input = _parse(payload)
    if agent == "docs-critic":
        return _deny("docs-critic reads only what it is given in its prompt, never the repository")

    if tool == "Read":
        raw = tool_input["file_path"]
        search = False
    elif tool in ("Grep", "Glob"):
        raw = tool_input.get("path") or str(repo)
        search = True
    else:
        return _deny(f"the read guard does not handle {tool}")

    rel = _relative_to_repo(_resolve(raw, repo), repo)
    if rel is None:
        return _deny("that path is outside the repository")
    if _is_env_file(rel):
        return _deny("environment files hold credentials and are never read")
    for denied in DENIED_READ_DIRS:
        if _inside(rel, denied):
            return _deny(f"{denied}/ is off limits to the docs-* agents")
        if search and (rel == Path(".") or denied.is_relative_to(rel)):
            return _deny(f"that search would cover {denied}/, which is off limits; "
                         "search a narrower directory instead")
    if search and (rel == Path(".") or next((repo / rel).rglob(".env*"), None) is not None):
        return _deny("that search would cover an environment file; search a narrower directory instead")
    return Decision(True)


# --------------------------------------------------------------- write


def _write_scope(agent: str, rel: Path) -> bool:
    if rel in NEVER_WRITTEN or rel.name == ".gitignore":
        return False
    if _inside(rel, WORK) and rel != WORK:
        return True
    is_page = (rel.suffix == ".md" and _inside(rel, EXPLAINERS)
               and len(rel.relative_to(EXPLAINERS).parts) >= 2)
    if agent == "docs-writer":
        return is_page or rel == GLOSSARY_YAML
    if agent == "docs-illustrator":
        return is_page
    return False


def guard_write(agent: str, payload: str, repo: Path = REPO_ROOT) -> Decision:
    try:
        return _guard_write(agent, payload, repo)
    except Exception as exc:  # noqa: BLE001 - every doubt is a refusal
        return _deny(f"the write guard could not check this call ({exc}), so it is refused")


def _guard_write(agent: str, payload: str, repo: Path) -> Decision:
    if agent not in WRITING_AGENTS:
        return _deny(f"{agent} may not write any file")
    tool, tool_input = _parse(payload)
    key = "notebook_path" if tool == "NotebookEdit" else "file_path"
    if tool not in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        return _deny(f"the write guard does not handle {tool}")
    rel = _relative_to_repo(_resolve(tool_input[key], repo), repo)
    if rel is None:
        return _deny("that path is outside the repository")
    if not _write_scope(agent, rel):
        return _deny(f"{agent} may not write {rel}")
    return Decision(True)


# ------------------------------------------------------------ snapshot


def _walk(repo: Path) -> dict[str, list[int]]:
    """Every file under the repository except .git, by size and
    modification time. Symlinks are recorded as themselves (lstat), so
    a new link is a change even if its target is not."""
    out: dict[str, list[int]] = {}
    repo = repo.resolve()
    for root, dirs, files in os.walk(repo):
        if Path(root) == repo and ".git" in dirs:
            dirs.remove(".git")
        for name in files:
            full = Path(root) / name
            try:
                st = full.lstat()
            except OSError:
                continue
            out[full.relative_to(repo).as_posix()] = [st.st_size, st.st_mtime_ns]
    return out


def take_snapshot(repo: Path, out: Path) -> int:
    snap = _walk(repo)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snap))
    return len(snap)


@dataclass
class ChangeReport:
    changed: list[str] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)
    named: list[str] = field(default_factory=list)


def verify_changes(agent: str, repo: Path, snapshot: Path) -> ChangeReport:
    before = json.loads(snapshot.read_text())
    after = _walk(repo)
    report = ChangeReport()
    for path in sorted(set(before) | set(after)):
        if before.get(path) == after.get(path):
            continue
        report.changed.append(path)
        rel = Path(path)
        if agent not in WRITING_AGENTS or not _write_scope(agent, rel):
            report.out_of_scope.append(path)
        if rel in NAMED_WHEN_CHANGED:
            report.named.append(path)
    return report


DEFAULT_SNAPSHOT = REPO_ROOT / ".git" / "mothman-docs-snapshot.json"
