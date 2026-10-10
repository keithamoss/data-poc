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

import contextvars
from contextlib import contextmanager

from pathlib import Path

from qa_tools.common import config_yaml

ROOT = Path(__file__).resolve().parent.parent.parent
PEOPLE_YAML = ROOT / "contract" / "people.yaml"


#: The three levels an assignment may name, exactly one each (REQ-GHUB-171
#: criterion 2) - the key it is written under in contract/people.yaml.
DATA_ASSET = "data_asset"
LEVELS = (DATA_ASSET, "agency", "dataset")
#: How a level reads in a refusal.
LEVEL_WORDS = {DATA_ASSET: "data-asset level", "agency": "agency level", "dataset": "dataset level"}

#: The role that, held at data-asset level, makes a person the ASSET MANAGER
#: (REQ-GHUB-171 criterion 4) - the existing manager role, at a new level
#: (decision 2), rather than a new role name.
MANAGER = "manager"


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
        return {"people": {}, "agency_assignments": {}, "dataset_assignments": {},
                "asset_assignments": [], "roles": []}
    with open(path) as f:
        doc = config_yaml.parse(f) or {}

    people = {p["email"]: p for p in doc.get("people") or []}
    agency_assignments: dict[str, list[dict]] = {}
    dataset_assignments: dict[str, list[dict]] = {}
    asset_assignments: list[dict] = []
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
        elif DATA_ASSET in entry:
            asset_assignments.append({**record, DATA_ASSET: entry[DATA_ASSET]})

    return {"people": people, "agency_assignments": agency_assignments,
            "dataset_assignments": dataset_assignments,
            "asset_assignments": asset_assignments, "roles": list(doc.get("roles") or [])}


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


def is_synthetic(person: dict) -> bool:
    """Whether this record is the scripted history's actor (REQ-GEN-135):
    no GitHub username, never assigned a ticket, and able to raise a
    decision only inside scripted playback (REQ-GHUB-082 criterion 29 as
    amended)."""
    return bool((person or {}).get("synthetic"))


#: Whether scripted playback is running in this process (REQ-GEN-135
#: criterion 10) - the one place the synthetic actor may act.
_PLAYBACK: contextvars.ContextVar[bool] = contextvars.ContextVar("people_playback",
                                                               default=False)


@contextmanager
def playback():
    """Scripted playback, for its duration only. Used by
    qa_tools/common/scripted_decisions.py and nothing else."""
    token = _PLAYBACK.set(True)
    try:
        yield
    finally:
        _PLAYBACK.reset(token)


def in_playback() -> bool:
    """Whether a synthetic history is being played back right now."""
    return _PLAYBACK.get()


def synthetic_actor(config: dict | None = None) -> dict:
    """The synthetic person, for scripted playback (criterion 5)."""
    config = parse_people_config() if config is None else config
    found = [p for p in (config["people"] or {}).values() if is_synthetic(p)]
    if len(found) != 1:
        raise UnknownActor(
            f"contract/people.yaml must hold exactly one entry marked `synthetic: true` "
            f"for scripted playback; it holds {len(found)}")
    return person_by_email(found[0]["email"], config)


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
    if is_synthetic(person) and not _PLAYBACK.get():
        # REQ-GEN-135 criterion 10: every route outside scripted playback.
        raise UnknownActor(
            f"{email!r} is the scripted history's synthetic actor, which can raise a "
            f"decision only while a synthetic history is being played back.")
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
        if is_placeholder(person) or is_synthetic(person):
            raise UnknownActor(
                f"the GitHub account {username!r} belongs to a placeholder or the "
                f"synthetic actor in contract/people.yaml, which cannot raise a filing "
                f"decision from GitHub.")
        return person
    raise UnknownActor(
        f"no person in contract/people.yaml has the GitHub username "
        f"{username!r}, so a decision raised by that account could not be "
        f"attributed to anybody. Add their username there - being able to "
        f"comment on the repository is not the same as being allowed to file.")


def display_name(identity: str | None, config: dict | None = None) -> str:
    """How an identity is SHOWN to a reader (REQ-PIPE-147 criterion 7):
    the person's name from contract/people.yaml where they have an entry,
    otherwise the identity as recorded - never a refusal, because showing
    who filed something must not fail for want of a config entry."""
    if not identity:
        return ""
    try:
        config = parse_people_config() if config is None else config
    except Exception:  # noqa: BLE001 - a display falls back, it never fails
        return identity
    person = (config.get("people") or {}).get(identity.strip())
    return (person or {}).get("name") or identity


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


def this_asset_id() -> str | None:
    """This deployment's data_asset_id, from contract/data-asset.yaml - what
    a `data_asset:` assignment must name to count (delivery-critic on 171,
    #2: an assignment copied from another asset's file granted nothing at
    the gate but everything at runtime)."""
    from qa_tools.common.hierarchy import DATA_ASSET_YAML

    with open(DATA_ASSET_YAML) as f:
        return (config_yaml.parse(f) or {}).get("data_asset_id")


def _asset_is_synthetic() -> bool:
    """Whether contract/data-asset.yaml declares this asset synthetic - read
    here rather than through the module that resets synthetic history,
    which nothing but `mothman env` may name."""
    from qa_tools.common.hierarchy import DATA_ASSET_YAML

    with open(DATA_ASSET_YAML) as f:
        return (config_yaml.parse(f) or {}).get("synthetic") is True


class RoleRefused(UnknownActor):
    """The person is known, and does not hold the role a decision requires
    at the level it requires it (REQ-GHUB-171 criterion 3)."""


def asset_managers(config: dict | None = None) -> list[dict]:
    """The data asset's managers: real people assigned the manager role at
    data-asset level (REQ-GHUB-171 criterion 4) - the asset manager
    REQ-PIPE-170's confirmation requires. Per-agency managers are not
    among them; they remain in force for their own agency's decisions."""
    config = parse_people_config() if config is None else config
    asset = this_asset_id()
    out = []
    for record in config.get("asset_assignments") or []:
        person = (config["people"] or {}).get(record["email"])
        if record.get(DATA_ASSET) != asset:
            continue  # another asset's manager (delivery-critic on 171, #2)
        if record.get("role") == MANAGER and person and not is_placeholder(person) \
                and not is_synthetic(person):
            out.append(person)
    return out


def holds(person: dict, role: str, level: str, agency_id: str | None = None,
          config: dict | None = None) -> bool:
    """Whether this person is assigned `role` at `level` - the whole data
    asset, or (for agency level) the agency of the dataset concerned."""
    config = parse_people_config() if config is None else config
    email = (person or {}).get("email")
    if level == DATA_ASSET:
        asset = this_asset_id()
        return any(r["email"] == email and r.get("role") == role and r.get(DATA_ASSET) == asset
                   for r in config.get("asset_assignments") or [])
    if level == "agency":
        return any(r["email"] == email and r.get("role") == role
                   for r in (config.get("agency_assignments") or {}).get(agency_id, []))
    return False


def require_role(person: dict, role: str, level: str, agency_id: str | None = None,
                 config: dict | None = None) -> None:
    """Refuse unless `person` holds `role` at `level` (REQ-GHUB-171
    criterion 3), naming the role and the level.

    A placeholder never passes (criterion 7). The scripted history's
    synthetic actor holds the asset manager role DURING PLAYBACK ONLY, and
    only on an asset that declares itself synthetic (criterion 7, decision
    5) - so a generated history can include a confirmed correction."""
    # A REQUIREMENT THAT CANNOT BE MET IS REFUSED, NEVER A TRACEBACK
    # (delivery-critic on 171, #6): only the two levels a decision may
    # require, and an agency requirement names its agency.
    if level not in (DATA_ASSET, "agency"):
        raise RoleRefused(f"a decision may require a role at data-asset or agency level, not "
                          f"{level!r} - the decision's own definition is wrong.")
    if level == "agency" and not agency_id:
        raise RoleRefused(f"this decision requires the {role} role at agency level and no "
                          f"agency was given to say which agency - the decision's own "
                          f"definition is wrong.")
    if not isinstance(person, dict):
        raise RoleRefused(f"{person!r} is not an identified person, so no role can be "
                          f"checked for it.")
    if is_placeholder(person):
        raise RoleRefused(f"{person.get('email')!r} is a placeholder and holds no role.")
    if is_synthetic(person):
        if role == MANAGER and level == DATA_ASSET and in_playback() and _asset_is_synthetic():
            return
        raise RoleRefused(
            f"{person.get('email')!r} is the scripted history's synthetic actor; it holds the "
            f"{role} role at {LEVEL_WORDS[DATA_ASSET]} only during scripted playback on a "
            f"synthetic data asset.")
    if holds(person, role, level, agency_id, config):
        return
    where = (LEVEL_WORDS[level] if level == DATA_ASSET
             else f"{LEVEL_WORDS[level]} for {agency_id}")
    raise RoleRefused(
        f"{person.get('email')!r} does not hold the {role} role at {where}, which this "
        f"decision requires. Assign it in contract/people.yaml under `assignments:` - "
        f"{'`data_asset:`' if level == DATA_ASSET else f'`agency: {agency_id}`'}, "
        f"`role: {role}` - if they should.")
