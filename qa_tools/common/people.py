"""
Real people, roles, and which datasets/agencies they're responsible for
(running-thoughts.md #2, "data-asset-level people/roles config",
2026-09-18, scoped via AskUserQuestion with Keith) - a pure parse/
resolve module, deliberately separate from ticket_sync.py itself (the
same real-parse/real-write split ticket_status.py/ticket_sync.py
already established): this module only ever reads contract/people.yaml
and resolves it; it never calls `gh` or writes anything.

Two real consumers, both scoped explicitly rather than assumed: real
GitHub ticket assignment (ticket_sync.py's own `--assignee`, via
github_usernames_for()) and a small "Owned by" indicator on the
dashboard's agency/dataset headers (assignees_for(), embedded by
dashboard/embed_dashboard_data.py as a new ASSIGNMENTS const). Gating
WHO may comment `/accept` on the amber-acceptance mechanism (running-
thoughts.md #6) was explicitly NOT chosen as a consumer this pass - see
that AskUserQuestion round's own answer.

contract/people.yaml's own header comment has the full real schema; see
that file directly rather than duplicating it here.
"""
from __future__ import annotations

from pathlib import Path


from qa_tools.common import yaml_io

ROOT = Path(__file__).resolve().parent.parent.parent
PEOPLE_YAML = ROOT / "contract" / "people.yaml"


def parse_people_config(path: Path | str = PEOPLE_YAML) -> dict:
    """{"people": {email: {...}}, "agency_assignments": {agencyId:
    [record, ...]}, "dataset_assignments": {datasetId: [record, ...]}} -
    a pure, defensive parse of contract/people.yaml's own real committed
    content. A missing file (or one that's still genuinely empty, as
    this repo's own committed copy ships until real people are added)
    reads as "nobody assigned to anything" rather than raising - same
    graceful-degradation treatment every other optional embedded feed
    in this project already gets (TICKET_STATUS/ACCEPTANCES with no
    real token locally, etc.). An `assignments:` entry referencing a
    `person:` email that isn't in `people:` is skipped, not a hard
    error - a real typo in a hand-edited config shouldn't break a
    dashboard build, only silently not assign anyone (same defensive
    posture ticket_status.py's own parse_open_tickets() already applies
    to an issue missing a real dataset:<id> label)."""
    if not Path(path).exists():
        return {"people": {}, "agency_assignments": {}, "dataset_assignments": {}}
    with open(path) as f:
        doc = yaml_io.load(f) or {}

    people = {p["email"]: p for p in doc.get("people") or []}
    agency_assignments: dict[str, list[dict]] = {}
    dataset_assignments: dict[str, list[dict]] = {}
    for entry in doc.get("assignments") or []:
        person = people.get(entry.get("person"))
        if person is None:
            continue
        record = {
            "email": entry["person"],
            "name": person.get("name"),
            "nickname": person.get("nickname"),
            "github": person.get("github"),
            "role": entry.get("role"),
        }
        if "dataset" in entry:
            dataset_assignments.setdefault(entry["dataset"], []).append(record)
        elif "agency" in entry:
            agency_assignments.setdefault(entry["agency"], []).append(record)

    return {"people": people, "agency_assignments": agency_assignments, "dataset_assignments": dataset_assignments}


def assignees_for(dataset_id: str, agency_id: str, config: dict) -> list[dict]:
    """Real people (full records, not just usernames) assigned to this
    dataset. Dataset-level entries win OUTRIGHT over agency-level ones -
    never merged: a dataset carrying its own explicit assignments is
    assumed to have deliberately overridden its agency's default list,
    not supplemented it, so "who's assigned to this dataset" always has
    exactly one real source, never a surprise union of two lists a
    human configured separately. Falls back to the agency-level list
    only when the dataset itself has no entries of its own at all;
    an empty list if neither does (contract/people.yaml still empty,
    or this scope genuinely has nobody assigned yet)."""
    dataset_entries = config["dataset_assignments"].get(dataset_id)
    if dataset_entries:
        return dataset_entries
    return config["agency_assignments"].get(agency_id, [])


def github_usernames_for(dataset_id: str, agency_id: str, config: dict) -> list[str]:
    """Just the real GitHub usernames from assignees_for() - what
    ticket_sync.py's own --assignee call actually needs. A person with
    real roles but no `github:` set (that field is optional in
    contract/people.yaml - someone can be listed/shown without being
    assignable to a real ticket) is silently excluded here, not an
    error; they can still appear in the dashboard's own "Owned by"
    badge via assignees_for() directly. Sorted for a deterministic
    `--assignee a,b,c` argument, not dependent on dict insertion order."""
    return sorted({p["github"] for p in assignees_for(dataset_id, agency_id, config) if p.get("github")})
