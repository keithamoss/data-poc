"""Whether every real person in contract/people.yaml can actually act
(REQ-GHUB-082 criterion 29).

THE FAILURE THIS CLOSES IS SILENT AND LATE. A filing decision raised on
a GitHub ticket is attributed to its authenticated author, and that
author is matched to a person by their `github:` username. Somebody
added to this file without one is shown on the dashboard, assigned
nothing, and finds out they cannot raise a decision at the moment they
try to raise one - which will be the moment something is wrong.

A PLACEHOLDER IS THE DELIBERATE EXCEPTION, not an oversight. Three of
the four entries in this repo's own committed file are Monty
Python-named stand-ins for colleagues not yet named for real (Keith's
own ask, 2026-09-19). They exist so the "Owned by" badge reads as a
name rather than a gap, and they must never be able to do anything: no
filing decision, no GitHub ticket. `placeholder: true` says so, and
this gate requires a username from everybody else.

SO THE MARKER IS LOAD-BEARING IN BOTH DIRECTIONS. Without it this gate
would fail on the file as committed, and the obvious way out - drop the
requirement, or give the placeholders usernames - is the one that ends
with a fictional person assigned to a real ticket.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

from qa_tools.common.people import PEOPLE_YAML


def _data_asset_id() -> str | None:
    from qa_tools.common.hierarchy import DATA_ASSET_YAML

    try:
        return (yaml.safe_load(Path(DATA_ASSET_YAML).read_text()) or {}).get("data_asset_id")
    except (OSError, yaml.YAMLError):
        return None


def problems(path: Path | str = PEOPLE_YAML) -> list[str]:
    """Every problem with this file, or an empty list.

    A MISSING FILE IS NOT A PROBLEM, on the same terms
    parse_people_config() already sets: this repo ships the file empty
    until real people are added, and a gate that fails on an empty
    config fails on a fresh clone.
    """
    path = Path(path)
    if not path.exists():
        return []
    try:
        doc = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        return [f"{path} does not parse as YAML: {exc}"]

    found: list[str] = []
    out = found
    seen: set[str] = set()
    usernames: dict[str, str] = {}
    assigned = {(a or {}).get("person") for a in doc.get("assignments") or []}
    for entry in doc.get("people") or []:
        email = (entry or {}).get("email")
        if not email:
            found.append(f"a person with no `email:` - it is the key everything "
                          f"else references them by: {entry!r}")
            continue
        if email in seen:
            found.append(f"{email} is listed twice, so which record wins is "
                          f"whichever PyYAML read last")
        seen.add(email)

        placeholder = bool(entry.get("placeholder"))
        github = (entry.get("github") or "").strip()
        if entry.get("synthetic"):
            # REQ-GHUB-082 criterion 29 as amended by REQ-GEN-135 criterion 11:
            # the scripted history's actor carries no GitHub username and is
            # never assigned - so the GitHub route cannot reach it at all.
            if github:
                out.append(f"{email} is marked `synthetic: true` and carries a GitHub "
                           f"username ({github!r}); the synthetic actor must have none, so "
                           f"no GitHub comment can act as it.")
            if placeholder:
                out.append(f"{email} is marked both `synthetic: true` and `placeholder: "
                           f"true`; the synthetic actor acts in scripted playback, which a "
                           f"placeholder never may - it is one or the other.")
            if email in assigned:
                out.append(f"{email} is marked `synthetic: true` and is assigned to an "
                           f"agency; the synthetic actor is never assigned a ticket.")
            continue
        if placeholder and github:
            found.append(
                f"{email} is marked `placeholder: true` and carries a GitHub "
                f"username ({github!r}). A placeholder stands in for somebody "
                f"not yet named; a username makes it assignable to a real "
                f"ticket and able to raise a real filing decision.")
        if not placeholder and not github:
            found.append(
                f"{email} has no `github:`. Without one they cannot be "
                f"assigned a ticket and cannot raise a filing decision from "
                f"GitHub - which they will discover at the moment they try. "
                f"Add the username, or mark them `placeholder: true` if they "
                f"are a stand-in.")
        if github:
            if github in usernames:
                found.append(
                    f"GitHub username {github!r} is on two people "
                    f"({usernames[github]} and {email}), so a decision raised "
                    f"by that account cannot be attributed to one of them")
            usernames[github] = email

    # THE ROLES, DECLARED (REQ-GHUB-171 criterion 1): a role a person holds
    # or is assigned that the file does not declare is a typo, refused.
    declared = set(doc.get("roles") or [])
    if not declared:
        found.append("the file declares no `roles:` - list the roles a person may hold "
                     "(qa, peer_review, manager), so a misspelt one is caught")
    for entry in doc.get("people") or []:
        for role in (entry or {}).get("roles") or []:
            if declared and role not in declared:
                found.append(f"{(entry or {}).get('email')} holds role {role!r}, which "
                             f"`roles:` does not declare ({', '.join(sorted(declared))})")
    from qa_tools.common.people import DATA_ASSET, LEVELS, MANAGER
    data_asset_id = _data_asset_id()
    asset_managers = []
    for entry in doc.get("assignments") or []:
        entry = entry or {}
        role = entry.get("role")
        if declared and role not in declared:
            found.append(f"an assignment of {entry.get('person')!r} names role {role!r}, "
                         f"which `roles:` does not declare ({', '.join(sorted(declared))})")
        # THE ROLE IS ONE THE PERSON HOLDS (delivery-critic on 171, #1): two
        # statements of who is a manager must agree, or which one a reader
        # consults decides the answer.
        holder = next((p for p in doc.get("people") or []
                       if (p or {}).get("email") == entry.get("person")), None)
        if holder is not None and role and role not in ((holder or {}).get("roles") or []):
            found.append(f"{entry.get('person')} is assigned role {role!r}, which their own "
                         f"`roles:` does not hold - add it there, or remove the assignment")
        # EXACTLY ONE LEVEL (criterion 2).
        levels = [k for k in LEVELS if k in entry]
        if len(levels) != 1:
            found.append(f"the assignment of {entry.get('person')!r} as {role!r} names "
                         f"{' and '.join(levels) or 'no level'} - it must name exactly one "
                         f"of `data_asset:`, `agency:` or `dataset:`")
        elif levels == [DATA_ASSET]:
            if data_asset_id and entry[DATA_ASSET] != data_asset_id:
                found.append(f"the assignment of {entry.get('person')!r} names data asset "
                             f"{entry[DATA_ASSET]!r}; this asset is {data_asset_id!r}")
            elif role == MANAGER:
                asset_managers.append(entry.get("person"))
    # A REAL ASSET MANAGER (criterion 6): an error, not a warning - no
    # correction can be confirmed without one (decision 3).
    real = {(p or {}).get("email") for p in doc.get("people") or []
            if not (p or {}).get("placeholder") and not (p or {}).get("synthetic")}
    # An empty people list fails too (delivery-critic on 171, #5) - only a
    # MISSING file passes, as on a fresh clone.
    if not [p for p in asset_managers if p in real]:
        found.append("no real person holds the manager role at data-asset level - add an "
                     "assignment `data_asset: <the data_asset_id>`, `role: manager` for the "
                     "person accountable for the whole asset. Without one no correction's "
                     "filing moves can be confirmed (REQ-PIPE-170).")
    people = {(p or {}).get("email") for p in doc.get("people") or []}
    for entry in doc.get("assignments") or []:
        person = (entry or {}).get("person")
        if person and person not in people:
            found.append(
                f"an assignment references {person!r}, who is not in `people:`. "
                f"It is silently skipped at read time, so the scope it names "
                f"has nobody assigned and nothing says so.")
    return found


def main() -> int:
    found = problems()
    if found:
        print(f"people validation FAILED ({len(found)} problem(s)):")
        for line in found:
            print(f"  - {line}")
        return 1
    doc = yaml.safe_load(Path(PEOPLE_YAML).read_text()) if Path(PEOPLE_YAML).exists() else {}
    people = (doc or {}).get("people") or []
    placeholders = sum(1 for p in people if (p or {}).get("placeholder"))
    print(f"people validation OK - {len(people)} person/people, "
          f"{placeholders} placeholder(s), zero errors.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
