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
    seen: set[str] = set()
    usernames: dict[str, str] = {}
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
