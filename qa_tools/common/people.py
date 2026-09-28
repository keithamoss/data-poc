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

import yaml

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
        doc = yaml.safe_load(f) or {}

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


class UnknownActor(Exception):
    """Nobody in contract/people.yaml matches (REQ-GHUB-082 criteria 6
    and 14).

    RAISED RATHER THAN RETURNING None, because every caller's response
    is the same - refuse the decision and say why - and a None that a
    caller forgets to check becomes a decision recorded against an
    empty actor. An unattributable filing decision is worse than no
    decision: the log's whole job is saying who.
    """


def is_placeholder(person: dict) -> bool:
    """Whether this record stands in for somebody not yet named.

    A placeholder is SHOWN and can do NOTHING (REQ-GHUB-082 criterion
    29): no filing decision, no GitHub ticket. It exists so the
    dashboard's "Owned by" badge reads as a name rather than a gap.
    """
    return bool((person or {}).get("placeholder"))


def person_by_email(email: str, config: dict | None = None) -> dict:
    """The person this email address names, or a refusal.

    THE EMAIL IS THE KEY the whole file references a person by, and it
    is the same identity git_identity.get_run_by() already stamps onto
    every QA run - so the terminal route needs no second notion of who
    is at the keyboard.
    """
    config = parse_people_config() if config is None else config
    person = (config["people"] or {}).get((email or "").strip())
    if person is None:
        raise UnknownActor(
            f"{email!r} is not in contract/people.yaml, so a filing decision "
            f"raised by them could not be attributed to anybody. Add them "
            f"there first - an unattributable decision is worse than none, "
            f"because saying who is what the log is for.")
    if is_placeholder(person):
        raise UnknownActor(
            f"{email!r} is a placeholder - a stand-in for somebody not yet "
            f"named - so it cannot raise a filing decision. Replace it with "
            f"the real person.")
    return person


def person_by_github(username: str, config: dict | None = None) -> dict:
    """The person this GitHub account belongs to, or a refusal.

    THE AUTHENTICATED AUTHOR, never a name written in a comment body
    (REQ-GHUB-082 criterion 4). Anybody who can comment on a public
    repository can type somebody else's name; only GitHub can say whose
    account posted.

    CASE-INSENSITIVE, because GitHub's own usernames are - and a
    decision refused over the capitalisation somebody typed years ago
    in a config file is a refusal nobody can act on.
    """
    config = parse_people_config() if config is None else config
    wanted = (username or "").strip().lower()
    for person in (config["people"] or {}).values():
        if (person.get("github") or "").strip().lower() != wanted or not wanted:
            continue
        if is_placeholder(person):
            raise UnknownActor(
                f"the GitHub account {username!r} belongs to a placeholder in "
                f"contract/people.yaml, which cannot raise a filing decision.")
        return person
    raise UnknownActor(
        f"no person in contract/people.yaml has the GitHub username "
        f"{username!r}, so a decision raised by that account could not be "
        f"attributed to anybody. Add their username there - being able to "
        f"comment on the repository is not the same as being allowed to file.")


def actor_name(person: dict) -> str:
    """How a person is written into the decision log.

    THE EMAIL, not the display name, and for the reason every other
    identity in this system uses it: names are edited, two people share
    one, and `run_by` already stamps the email onto every QA run. A log
    a year old should still say which person.
    """
    return (person or {}).get("email") or ""


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
