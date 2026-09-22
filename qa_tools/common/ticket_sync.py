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
Was red-only through the initial MVP; extended to amber too (2026-09-18,
running-thoughts.md #6, "read-only tension: accepting/rejecting amber
supplies") once a real accept mechanism needed somewhere to write a
decision - a dataset that's only ever been amber, never red, had no
real ticket to comment `/accept` on until this. plans/conceptual-
design.md Thread A's own amber-GOVERNANCE question (does amber ever
NEED a decision, is it a legitimate steady state, etc.) stays parked,
not blocking this - this is mechanism only, scoped that way
deliberately via AskUserQuestion. No escalation, no suppression, no
provider access - all real pieces of the original design (docs/
remediation-workflow-design.md) explicitly deferred past this MVP, not
overlooked.

A newly-opened ticket now also gets a real `--assignee` when
contract/people.yaml has anyone real assigned to that dataset/agency
(running-thoughts.md #2, "data-asset-level people/roles config",
2026-09-18, scoped via AskUserQuestion) - qa_tools/common/people.py's
own dataset-then-agency resolution, omitted entirely when nobody's
configured yet (this repo's own committed people.yaml ships empty -
real names are Keith's to fill in).

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
  no ticket,  amber       -> open a new one (2026-09-18 - see above)
  no ticket,  green       -> nothing to do
  ticket,     red         -> post a real "still red" comment (the
                              original design's own "even non-
                              transitions post" principle - evidence of
                              activity/attempts, not silence)
  ticket,     amber/green -> post a real "resolved to <status>" comment
                              - never auto-closes (closing always
                              requires a human, unchanged from the
                              original design)

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

from qa_tools.common import hierarchy
from qa_tools.common.dataset_status import dataset_status
from qa_tools.common.people import PEOPLE_YAML, github_usernames_for, parse_people_config
from qa_tools.common.ticket_check_summary import build_check_summary

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
BDM_DASHBOARD_JSON = os.path.join(ROOT, "reports", "birth_registrations_dashboard.json")
CP_DASHBOARD_JSON = os.path.join(ROOT, "reports", "child_protection_dashboard.json")

# Every real ticket this module ever opens carries this label too (on top
# of its own dataset:<id> one) - the "one unified queue, filterable"
# principle from the original design: a real, stable way to find every
# QA-pipeline-opened ticket across every dataset at once, distinct from
# any other issue a human might open on this repo for unrelated reasons.
TICKET_LABEL = "qa-ticket"

# dataset -> (agency, collection), needed here so open_ticket() can
# resolve real ticket assignees (qa_tools/common/people.py's own
# dataset-then-agency fallback) and so a ticket body can carry a real
# dashboard deep link, which names all three.
#
# This used to be a plain dict, and its own comment recorded that it was
# the FOURTH copy of the same mapping - alongside github_links.py's
# AGENCY_QA_FOLDER/DATASET_QA_FOLDER and acceptance_sync.py's
# QA_RESULTS_SCOPE_FOR_DATASET - and that four was the trigger for
# consolidating them. REQ-QAC-039 is that consolidation: all four now
# resolve through the one hierarchy in contract/data-asset.yaml.
DATASET_SCOPE = {d.dataset_id: (d.agency_id, d.collection_id) for d in hierarchy.all_datasets()}

DATASET_AGENCY = {dataset: agency for dataset, (agency, _collection) in DATASET_SCOPE.items()}


@dataclass
class DatasetScope:
    id: str
    name: str
    agency_id: str
    collection_id: str


def _load_scopes() -> list[tuple[DatasetScope, dict]]:
    """Every real dataset scope this MVP covers, paired with its own
    already-built dashboard JSON - real order: Birth Registrations
    first, then Child Protection's 6 tables in their own file's own
    order (never re-sorted)."""
    scopes: list[tuple[DatasetScope, dict]] = []
    with open(BDM_DASHBOARD_JSON) as f:
        bdm = json.load(f)
    scopes.append((_scope_for(bdm), bdm))

    with open(CP_DASHBOARD_JSON) as f:
        cp = json.load(f)
    for ds in cp["datasets"]:
        scopes.append((_scope_for(ds), ds))
    return scopes


def _scope_for(dataset: dict) -> DatasetScope:
    agency_id, collection_id = DATASET_SCOPE[dataset["id"]]
    return DatasetScope(id=dataset["id"], name=dataset["name"],
                        agency_id=agency_id, collection_id=collection_id)


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


def _ensure_label(owner: str, repo: str, name: str, description: str) -> None:
    """`gh issue create --label` needs the label to already exist as a
    real repo label - unlike `gh issue list --label` (a search filter,
    silently matches nothing for a label that doesn't exist yet),
    creating an issue with a label that isn't real fails outright. Real
    bug hit 2026-09-18 (plans/qa-pipeline.md item 79): the very first
    real push-triggered run failed here, since neither `qa-ticket` nor
    any `dataset:<id>` label had ever been created on the real repo -
    the earlier manual capability check (a plain untagged test issue)
    never exercised this path. `--force` makes this idempotent (create
    or update, never errors on an already-existing label) - safe to
    call on every real run, not just the first."""
    _run_gh([
        "label", "create", name, "--repo", f"{owner}/{repo}",
        "--description", description, "--color", "d73a4a", "--force",
    ])


_EMPTY_PEOPLE_CONFIG = {"people": {}, "agency_assignments": {}, "dataset_assignments": {}}


def open_ticket(owner: str, repo: str, scope: DatasetScope, status: str,
                people_config: dict | None = None, dataset: dict | None = None) -> int:
    _ensure_label(owner, repo, TICKET_LABEL, "Opened automatically by this project's real QA pipeline")
    _ensure_label(owner, repo, _dataset_label(scope.id), f"Real QA tickets for {scope.name}")

    # running-thoughts.md #2 (2026-09-18, scoped via AskUserQuestion):
    # real ticket assignment, resolved from contract/people.yaml -
    # dataset-level assignments win outright over agency-level ones
    # (people.py's own assignees_for() docstring). No real people
    # configured yet (contract/people.yaml ships empty - real names/
    # emails are Keith's to fill in, not fabricated) means an empty
    # list here, same graceful degradation every other optional
    # embedded feed in this project already gets - `gh issue create`
    # without `--assignee` at all, not an error.
    usernames = github_usernames_for(scope.id, scope.agency_id, people_config or _EMPTY_PEOPLE_CONFIG)

    body = (
        f"**{scope.name}** (`{scope.id}`) is currently reading **{status}** - "
        f"the worst status among its own real checks across every column.\n\n"
        f"Opened automatically by this project's real QA pipeline "
        f"(`qa_tools/common/ticket_sync.py`) - see the live dashboard's own "
        f"{scope.name} page for the real check-by-check breakdown.\n\n"
        f"This ticket will get a real comment on every future QA run while "
        f"it stays open - closing it is always a human decision, never "
        f"automatic."
        + (
            "\n\nA real supply, even amber, can be accepted for now by "
            "commenting `/accept` on this issue - it's matched to whichever "
            "run was current at the time (running-thoughts.md #6). The "
            "supply itself stays amber on the dashboard; a real "
            "acknowledgment badge shows next to it."
            if status == "amber" else ""
        )
        # REQ-GHUB-027. The paragraph above still points at the dashboard,
        # and deliberately so - this section answers "what is wrong" where
        # the dashboard answers "and what has it been doing for a month".
        # Appended rather than replacing anything: a ticket that names its
        # failing checks is still a ticket about a dataset's status.
        + _check_section(scope, status, dataset)
    )
    args = [
        "issue", "create", "--repo", f"{owner}/{repo}",
        "--title", f"{scope.name} is {status}",
        "--body", body,
        "--label", f"{TICKET_LABEL},{_dataset_label(scope.id)}",
    ]
    if usernames:
        args += ["--assignee", ",".join(usernames)]
    out = _run_gh(args)
    # `gh issue create` (non-interactive, --title/--body given) prints
    # exactly the new issue's real URL to stdout and nothing else.
    return int(out.strip().rsplit("/", 1)[-1])



def _check_section(scope: DatasetScope, status: str, dataset: dict | None) -> str:
    """The REQ-GHUB-027 block, ready to append to a body or a comment.

    Returns "" for a green dataset, which has nothing not-green to list,
    and for a caller that did not pass the dataset at all - open_ticket()
    is public and was callable without it before this.
    """
    if not dataset:
        return ""
    summary = build_check_summary(
        dataset, status, scope.agency_id, scope.collection_id, scope.id)
    return f"\n\n---\n\n{summary}" if summary else ""


def comment(owner: str, repo: str, issue_number: int, body: str) -> None:
    _run_gh(["issue", "comment", str(issue_number), "--repo", f"{owner}/{repo}", "--body", body])


def sync_dataset(owner: str, repo: str, scope: DatasetScope, dataset: dict, people_config: dict | None = None) -> str:
    """Returns a short, real description of the action actually taken
    (or genuinely 'nothing to do') - for the caller's own log, never a
    guess about what would happen."""
    status = dataset_status(dataset)
    existing = find_open_ticket(owner, repo, scope.id)


    if existing is None:
        if status in ("red", "amber"):
            issue_number = open_ticket(owner, repo, scope, status, people_config, dataset)
            return f"{scope.id}: opened #{issue_number} ({status})"
        return f"{scope.id}: {status}, no open ticket - nothing to do"

    # REQ-GHUB-027: every run's comment carries the list as it stands at
    # that run, and posts it even when it is word-for-word what the last
    # comment said. Keith's own call, with the repetition stated: the
    # thread is then a real record of the failure set shrinking, and a
    # reader never has to scroll up to find the most recent one.
    if status == "red":
        comment(owner, repo, existing,
                f"Still **red** as of this run - {scope.name} continues to fail its own checks."
                + _check_section(scope, status, dataset))
        return f"{scope.id}: #{existing} still red, commented"

    comment(owner, repo, existing,
            f"Resolved to **{status}** as of this run. This ticket does NOT "
            f"auto-close - close it once you've confirmed the fix, or leave "
            f"it open if follow-up is still needed."
            + _check_section(scope, status, dataset))
    return f"{scope.id}: #{existing} resolved to {status}, commented (not closed)"


def sync_all(owner: str, repo: str, people_config: dict | None = None) -> list[str]:
    return [sync_dataset(owner, repo, scope, dataset, people_config) for scope, dataset in _load_scopes()]


def main() -> None:
    owner, repo = os.environ["GITHUB_REPOSITORY"].split("/", 1)
    people_config = parse_people_config(PEOPLE_YAML)
    for line in sync_all(owner, repo, people_config):
        print(line)


if __name__ == "__main__":
    main()
