"""
Real per-person, per-dataset "current not-red streak" leaderboard
(running-thoughts.md #3, "gamification MVP", 2026-09-18, scoped via two
AskUserQuestion rounds with Keith): celebrates CONSISTENCY, not
turnaround speed - a deliberately narrowed scope, not a guess. A streak
belongs to a PERSON within one dataset, not to the dataset's own run
count: it walks that person's own chronological sequence of runs THEY
personally published on that one dataset (skipping over any other
person's interleaved runs entirely - those neither extend nor break
this person's own streak), and counts backward from their own most
recent run until hitting a red one. Amber does NOT break it (Keith's
own explicit call, given how common a real amber run legitimately is
in this project's own committed history - 77 of them in BDM alone).

CI-safe: reads only already-built dashboard JSON (dataset_status.
status_by_run()'s real input) and committed qa_results/ history
(qa_results_reader) - no `gh` call, no live data, matching CLAUDE.md's
hard rule.

Privacy (this repo is public, Keith's own call): only people with a
real entry in contract/people.yaml ever appear here, by name/nickname -
`run_by` is a real email address (qa_tools/common/git_identity.py), and
this module never surfaces a bare email on a publicly-deployed page. A
run published by someone with no matching people.yaml entry - which is
exactly every real run in this project's own history today, since that
file ships empty - simply doesn't count toward anyone's streak yet.
"""
from __future__ import annotations

from qa_tools.common.acceptance_sync import QA_RESULTS_SCOPE_FOR_DATASET
from qa_tools.common.dataset_status import status_by_run
from qa_tools.common.qa_results_reader import QA_RESULTS_DIR, list_run_ids, read_run_provenance


def _person_runs(dataset_id: str, qa_results_dir=QA_RESULTS_DIR) -> list[dict]:
    """[{run_id, run_by}, ...] in real chronological order
    (list_run_ids()'s own natural sort) - one entry per real committed
    run for this dataset's own qa_results scope (Child Protection's 6
    real tables all resolve to the SAME collection-level scope here,
    same as acceptance_sync.py's own run-window logic), skipping any
    run with no real run_by recorded (committed before git_identity.py's
    stamping existed, or dataset_stats genuinely missing)."""
    scope = QA_RESULTS_SCOPE_FOR_DATASET.get(dataset_id)
    if scope is None:
        return []
    agency, dataset = scope
    runs = []
    for run_id in list_run_ids(agency, dataset, qa_results_dir):
        provenance = read_run_provenance(agency, dataset, run_id, qa_results_dir)
        if provenance and provenance.get("run_by"):
            runs.append({"run_id": run_id, "run_by": provenance["run_by"]})
    return runs


def compute_streaks(dataset_id: str, dataset_json: dict, qa_results_dir=QA_RESULTS_DIR) -> dict[str, dict]:
    """{run_by_email: {"streak": n, "last_run_id": ...}} - each real
    person's own CURRENT not-red streak on this one dataset. `dataset_
    json` is the already-built dashboard JSON for this one dataset
    (reports/birth_registrations_dashboard.json, or one entry of
    child_protection_dashboard.json's own `datasets` list) -
    status_by_run()'s own real input shape. Only people with a streak
    of at least 1 appear (someone whose own most recent run was red has
    nothing to show)."""
    runs = _person_runs(dataset_id, qa_results_dir)
    status = status_by_run(dataset_json)

    by_person: dict[str, list[dict]] = {}
    for run in runs:
        by_person.setdefault(run["run_by"], []).append(run)

    streaks: dict[str, dict] = {}
    for person, person_runs in by_person.items():
        # person_runs inherits `runs`'s own real chronological order -
        # walk backward from this person's own most recent run.
        streak = 0
        last_run_id = None
        for run in reversed(person_runs):
            if status.get(run["run_id"], "green") == "red":
                break
            if last_run_id is None:
                last_run_id = run["run_id"]
            streak += 1
        if streak:
            streaks[person] = {"streak": streak, "last_run_id": last_run_id}
    return streaks


def build_leaderboard(dataset_jsons: dict[str, dict], people_config: dict,
                       qa_results_dir=QA_RESULTS_DIR) -> list[dict]:
    """[{dataset_id, name, nickname, github, streak}, ...], sorted by
    streak descending - the real, publicly-embeddable rows dashboard/
    embed_dashboard_data.py's own LEADERBOARD const uses directly.
    `dataset_jsons`: {dataset_id: already-built dashboard JSON for that
    one dataset}, one entry per real scope this covers. `email` is
    deliberately never included in a row - see this module's own
    docstring on why."""
    rows = []
    for dataset_id, dataset_json in dataset_jsons.items():
        for email, info in compute_streaks(dataset_id, dataset_json, qa_results_dir).items():
            person = people_config["people"].get(email)
            if person is None:
                continue
            rows.append({
                "dataset_id": dataset_id,
                "name": person.get("name"),
                "nickname": person.get("nickname"),
                "github": person.get("github"),
                "streak": info["streak"],
            })
    rows.sort(key=lambda r: r["streak"], reverse=True)
    return rows
