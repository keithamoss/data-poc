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


@docs_group.command("quote-check")
@click.argument("report", type=click.Path(path_type=Path, exists=True))
def quote_check_command(report: Path) -> None:
    """Check that every quote in a saved docs-fact-checker report appears
    in the source it names (REQ-DOCS-128). Exits 1 on any mismatch."""
    import yaml

    from qa_tools.common import explainers

    rows = yaml.safe_load(report.read_text()) or []
    if not isinstance(rows, list):
        console.print("The report must be a YAML list, one row per claim.")
        raise SystemExit(1)
    problems = explainers.quote_check(rows)
    for p in problems:
        console.print(f"[bold red]{p}[/]")
    if problems:
        raise SystemExit(1)
    console.print(f"All {sum(1 for r in rows if (r.get('quote') or '').strip())} quotes found in their sources.")


def _report_yaml(path: Path):
    """A saved agent report: the YAML itself, or the agent's reply with
    its one fenced YAML block, which is taken as the report."""
    import re

    import yaml

    text = path.read_text()
    fence = re.search(r"```ya?ml\s*\n(.*?)```", text, re.S)
    return yaml.safe_load(fence.group(1) if fence else text)


@docs_group.command("check-findings")
@click.argument("critic_report", type=click.Path(path_type=Path, exists=True))
@click.option("--page", "page", required=True, type=click.Path(path_type=Path, exists=True),
              help="The page the critic reviewed.")
@click.option("--brief", "brief", required=True, type=click.Path(path_type=Path, exists=True),
              help="The brief's questions, operating questions and non-scope, as YAML.")
@click.option("--round", "round_number", required=True, type=int, help="The review round, from 1.")
@click.option("--diff", "diff", type=click.Path(path_type=Path, exists=True), default=None,
              help="On a re-review, the round's `git diff --no-index --word-diff=plain` output.")
@click.option("--checker", "checker", type=click.Path(path_type=Path, exists=True), default=None,
              help="docs-finding-checker's report, checked against the findings that passed.")
def check_findings_command(critic_report: Path, page: Path, brief: Path, round_number: int,
                           diff: Path | None, checker: Path | None) -> None:
    """Check the critic's report, and the finding-checker's when given,
    against every rule a script can decide (REQ-DOCS-134). Findings it
    rejects are listed for Keith with the rule each failed; a malformed
    report exits 1."""
    import yaml
    from pydantic import TypeAdapter, ValidationError

    from qa_tools.common import explainers as ex

    try:
        report = ex.CriticReport.model_validate(_report_yaml(critic_report))
        questions = ex.BriefQuestions.model_validate(yaml.safe_load(brief.read_text()))
        rows = (TypeAdapter(list[ex.FindingCheckRow]).validate_python(_report_yaml(checker) or [])
                if checker else None)
    except (ValidationError, yaml.YAMLError) as exc:
        console.print(f"[bold red]A report does not match its schema:[/]\n{exc}")
        raise SystemExit(1) from None
    result = ex.check_critic_report(report, page.read_text(), questions, round_number,
                                    diff.read_text() if diff else None)
    failures = list(result.failures)
    if rows is not None:
        failures += ex.check_finding_check(rows, result.passed)
    for fid, rule in result.rejected:
        console.print(f"{fid} rejected by rule: {rule}")
    console.print(f"Passed to docs-finding-checker: {', '.join(result.passed) or 'none'}")
    for f in failures:
        console.print(f"[bold red]{f}[/]")
    if failures:
        raise SystemExit(1)
