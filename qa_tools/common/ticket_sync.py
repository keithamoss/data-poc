"""
Item 76 (plans/qa-pipeline.md) - the GitHub Issues ticketing MVP's real
create/dedup/update logic. Scoped via AskUserQuestion with Keith,
2026-09-18, picking this project's own resupply-chain redesign (item
73) up on the same idea - derive real behaviour from real, observable
facts, not synthetic bookkeeping: one real GitHub Issue per real
DATASET (matching the dashboard's own Tier 3 unit - `birth-
registrations`, plus each of Child Protection's 6 real tables
separately - not one combined CP ticket, and not per-column either,
both real forks Keith resolved explicitly), keyed off each dataset's
own current real aggregate status (qa_tools/common/dataset_status.py).
Red-only for this MVP (amber sidestepped - plans/conceptual-design.md
Thread A's own governance question stays parked, not blocking this);
no escalation, no suppression, no provider access - all real pieces of
the original design (docs/remediation-workflow-design.md) explicitly
deferred past this MVP, not overlooked.

Runs via the real `gh` CLI (subprocess - same convention this project
already uses for dbt/soda/datacontract-cli) - authenticates via
GITHUB_TOKEN, already set automatically inside a GitHub Actions job (no
new secret needed); a local/manual run needs `gh auth login` once first
(same one-time-setup shape as `uv run playwright install chromium`).
Deliberately its own separate, write-permitted GitHub Actions workflow
(.github/workflows/ticket-sync.yml), never deploy-pages.yml - Keith's
own explicit call: that workflow's whole design is built around staying
read-only against everything except the Pages deploy itself, and
opening/commenting on a real GitHub Issue is a genuinely different kind
of action (an external write with real visibility) than deploy-
pages.yml's own deterministic rebuild-from-committed-history.

Dedup: at most one real, already-OPEN GitHub Issue per dataset, found
by a `dataset:<id>` label search. Behaviour per (open ticket?, current
status):

  no ticket,  red         -> open a new one
  ticket,     red         -> post a real "still red" comment (the
                              original design's own "even non-
                              transitions post" principle - evidence of
                              activity/attempts, not silence)
  ticket,     amber/green -> post a real "resolved to <status>" comment
                              - never auto-closes (closing always
                              requires a human, unchanged from the
                              original design)
  no ticket,  amber/green -> nothing to do

Reads ONLY the already-built dashboard JSON (reports/
birth_registrations_dashboard.json / child_protection_dashboard.json -
the exact same CI-safe output deploy-pages.yml's own build chain
already produces from committed qa_results/ history) - never data/,
never a live DuckDB connection, per CLAUDE.md's hard rule that no "read
committed history" code path may touch live data.
"""
from __future__ import annotations
import json
import os
import subprocess
from dataclasses import dataclass

from qa_tools.common.dataset_status import dataset_status

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
BDM_DASHBOARD_JSON = os.path.join(ROOT, "reports", "birth_registrations_dashboard.json")
CP_DASHBOARD_JSON = os.path.join(ROOT, "reports", "child_protection_dashboard.json")

# Every real ticket this module ever opens carries this label too (on top
# of its own dataset:<id> one) - the "one unified queue, filterable"
# principle from the original design: a real, stable way to find every
# QA-pipeline-opened ticket across every dataset at once, distinct from
# any other issue a human might open on this repo for unrelated reasons.
TICKET_LABEL = "qa-ticket"


@dataclass
class DatasetScope:
    id: str
    name: str


def _load_scopes() -> list[tuple[DatasetScope, dict]]:
    """Every real dataset scope this MVP covers, paired with its own
    already-built dashboard JSON - real order: Birth Registrations
    first, then Child Protection's 6 tables in their own file's own
    order (never re-sorted)."""
    scopes: list[tuple[DatasetScope, dict]] = []
    with open(BDM_DASHBOARD_JSON) as f:
        bdm = json.load(f)
    scopes.append((DatasetScope(id=bdm["id"], name=bdm["name"]), bdm))

    with open(CP_DASHBOARD_JSON) as f:
        cp = json.load(f)
    for ds in cp["datasets"]:
        scopes.append((DatasetScope(id=ds["id"], name=ds["name"]), ds))
    return scopes


def _dataset_label(dataset_id: str) -> str:
    return f"dataset:{dataset_id}"


def _run_gh(args: list[str]) -> str:
    result = subprocess.run(["gh", *args], capture_output=True, text=True, check=True)
    return result.stdout


def find_open_ticket(owner: str, repo: str, dataset_id: str) -> int | None:
    """The number of the currently-open GitHub Issue for this dataset, if
    any - a real `gh issue list` query. This module never opens a second
    ticket for a dataset while one's already open, by construction (this
    is the only place that decides "does one already exist")."""
    out = _run_gh([
        "issue", "list", "--repo", f"{owner}/{repo}",
        "--label", _dataset_label(dataset_id), "--state", "open",
        "--json", "number", "--limit", "1",
    ])
    issues = json.loads(out)
    return issues[0]["number"] if issues else None


def open_ticket(owner: str, repo: str, scope: DatasetScope) -> int:
    body = (
        f"**{scope.name}** (`{scope.id}`) is currently reading **red** - "
        f"the worst status among its own real checks across every column.\n\n"
        f"Opened automatically by this project's real QA pipeline "
        f"(`qa_tools/common/ticket_sync.py`) - see the live dashboard's own "
        f"{scope.name} page for the real check-by-check breakdown.\n\n"
        f"This ticket will get a real comment on every future QA run while "
        f"it stays open - closing it is always a human decision, never "
        f"automatic."
    )
    out = _run_gh([
        "issue", "create", "--repo", f"{owner}/{repo}",
        "--title", f"{scope.name} is red",
        "--body", body,
        "--label", f"{TICKET_LABEL},{_dataset_label(scope.id)}",
    ])
    # `gh issue create` (non-interactive, --title/--body given) prints
    # exactly the new issue's real URL to stdout and nothing else.
    return int(out.strip().rsplit("/", 1)[-1])


def comment(owner: str, repo: str, issue_number: int, body: str) -> None:
    _run_gh(["issue", "comment", str(issue_number), "--repo", f"{owner}/{repo}", "--body", body])


def sync_dataset(owner: str, repo: str, scope: DatasetScope, dataset: dict) -> str:
    """Returns a short, real description of the action actually taken
    (or genuinely 'nothing to do') - for the caller's own log, never a
    guess about what would happen."""
    status = dataset_status(dataset)
    existing = find_open_ticket(owner, repo, scope.id)

    if existing is None:
        if status == "red":
            issue_number = open_ticket(owner, repo, scope)
            return f"{scope.id}: opened #{issue_number} (red)"
        return f"{scope.id}: {status}, no open ticket - nothing to do"

    if status == "red":
        comment(owner, repo, existing,
                f"Still **red** as of this run - {scope.name} continues to fail its own checks.")
        return f"{scope.id}: #{existing} still red, commented"

    comment(owner, repo, existing,
            f"Resolved to **{status}** as of this run. This ticket does NOT "
            f"auto-close - close it once you've confirmed the fix, or leave "
            f"it open if follow-up is still needed.")
    return f"{scope.id}: #{existing} resolved to {status}, commented (not closed)"


def sync_all(owner: str, repo: str) -> list[str]:
    return [sync_dataset(owner, repo, scope, dataset) for scope, dataset in _load_scopes()]


def main() -> None:
    owner, repo = os.environ["GITHUB_REPOSITORY"].split("/", 1)
    for line in sync_all(owner, repo):
        print(line)


if __name__ == "__main__":
    main()
