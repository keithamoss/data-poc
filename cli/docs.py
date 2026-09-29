"""mothman docs - the tooling behind the concept explainers
(plans/explainers.md, REQ-DOCS-115 to 132).

Named `docs` rather than `explainers` on Keith's call (2026-09-29): the
same docs-* agent team is meant to write the "Running Mothman" pipeline
docs later, and the commands should not need renaming when it does.

The guard commands are what the docs-* agents' PreToolUse hooks call.
They read the hook's JSON on stdin and exit 2 to block, because 2 is
the only exit code that blocks a tool call - see
qa_tools/common/docs_guard.py for why the hook line itself also ends
in `|| exit 2`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import rich_click as click
from rich.console import Console

from qa_tools.common import docs_guard

console = Console()


@click.group("docs")
def docs_group() -> None:
    """The concept explainers: agent guards and the before/after check."""


def _run_guard(check, agent: str) -> None:
    decision = check(agent, sys.stdin.read())
    if not decision.allowed:
        print(f"Refused by the docs-* guard: {decision.reason}.", file=sys.stderr)
        raise SystemExit(2)


@docs_group.command("guard-read")
@click.argument("agent")
def guard_read_command(agent: str) -> None:
    """PreToolUse hook body for Read, Grep and Glob. Exits 2 to refuse."""
    _run_guard(docs_guard.guard_read, agent)


@docs_group.command("guard-write")
@click.argument("agent")
def guard_write_command(agent: str) -> None:
    """PreToolUse hook body for Write, Edit, MultiEdit and NotebookEdit.
    Exits 2 to refuse."""
    _run_guard(docs_guard.guard_write, agent)


@docs_group.command("snapshot")
@click.option("--out", type=click.Path(path_type=Path), default=docs_guard.DEFAULT_SNAPSHOT,
              show_default=True, help="Where to write the snapshot.")
def snapshot_command(out: Path) -> None:
    """Record every file in the repository, including ignored ones,
    before a docs-* agent runs."""
    count = docs_guard.take_snapshot(docs_guard.REPO_ROOT, out)
    console.print(f"Recorded {count} files.")


@docs_group.command("verify-changes")
@click.argument("agent")
@click.option("--snapshot", type=click.Path(path_type=Path, exists=True),
              default=docs_guard.DEFAULT_SNAPSHOT, show_default=True)
def verify_changes_command(agent: str, snapshot: Path) -> None:
    """Compare the repository against the snapshot after AGENT ran.
    Exits 1 if it changed anything outside its write scope."""
    report = docs_guard.verify_changes(agent, docs_guard.REPO_ROOT, snapshot)
    for path in report.named:
        console.print(f"Changed, for Keith to see: {path}")
    if report.out_of_scope:
        console.print(f"[bold red]{agent} changed files outside its scope - stop the run:[/]")
        for path in report.out_of_scope:
            console.print(f"  {path}")
        raise SystemExit(1)
    console.print(f"{len(report.changed)} changed, all inside {agent}'s scope.")


@docs_group.command("validate")
@click.option("--list-rules", is_flag=True, help="Print every rule id and what it checks.")
@click.option("--print-hash", "hash_page", type=click.Path(path_type=Path, exists=True),
              help="Print the sign-off hash of one page, for its sign-off record.")
def validate_command(list_rules: bool, hash_page: Path | None) -> None:
    """Check every explainer page against the house standard's
    machine-checkable rules (REQ-DOCS-122, REQ-DOCS-132)."""
    from qa_tools.common import validate_explainers

    if list_rules:
        for rule, what in validate_explainers.RULES.items():
            print(f"{rule}  {what}")
        return
    if hash_page is not None:
        print(validate_explainers.page_hash(hash_page.read_text()))
        return
    raise SystemExit(validate_explainers.main())


@docs_group.command("glossary")
@click.option("--check", is_flag=True,
              help="Fail if the committed glossary.md is not what this would write.")
def glossary_command(check: bool) -> None:
    """Write docs/explainers/glossary.md from glossary.yaml and
    requirements.yaml (REQ-DOCS-119). Never edit glossary.md by hand."""
    from qa_tools.common import explainers

    if check:
        if not explainers.glossary_is_current():
            console.print("glossary.md is out of date - run 'mothman docs glossary' and commit it.")
            raise SystemExit(1)
        console.print("glossary.md is current.")
        return
    out = explainers.write_glossary_md()
    console.print(f"Wrote {out.relative_to(explainers.REPO_ROOT)}.")
