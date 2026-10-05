"""Which deployment is this, and what are the others.

WHY IT EXISTS (Keith, 2026-09-27). Once GitHub Actions is no longer
allowed to reach a database, the dashboard is built where the data is -
so a build from here, a build from somebody's development environment
and the published one are different artifacts that look identical.
Each has to say which environment produced it: "this dashboard here is
physically separate to a dashboard from my development or production or
another user."

THE SPLIT IS THE DESIGN DECISION, and it follows this repo's own
configuration-not-state rule rather than being invented for this module.
The LIST of environments is configuration: it declares how the system
behaves, it is the same for everyone who checks the repository out, and
it is reviewed - so it is committed, at contract/environments.yaml.
WHICH ONE YOU ARE is a property of one deployment, like the database it
talks to - so it comes from MOTHMAN_ENVIRONMENT, sitting beside
MOTHMAN_SUPPLY_DSN where it belongs.

Both alternatives are worse in the same way. Committing the answer
means committing one deployment's identity for everybody. Gitignoring
the list means the set of valid environments is no longer reviewed, and
a typo becomes a new environment rather than an error.

AN UNKNOWN NAME IS REFUSED rather than accepted as a new environment,
which is the whole reason the list is worth having. `MOTHMAN_ENVIRONMENT
=prod` when the list says `production` should stop, not quietly publish
a dashboard labelled with a name nobody declared.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
ENVIRONMENTS_PATH = ROOT / "contract" / "environments.yaml"

#: Where a deployment says which of the declared environments it is.
ENVIRONMENT_ENV = "MOTHMAN_ENVIRONMENT"

#: An id reaches a schema name, a file name and a URL, so it is held to
#: the same shape as every other identifier in this project.
_SAFE_ID = re.compile(r"^[a-z0-9_]+$")


class EnvironmentError_(RuntimeError):
    """Raised where continuing would mean guessing which deployment this
    is - which is the one thing a published artifact must not do."""


@dataclass(frozen=True)
class Environment:
    id: str
    label: str
    description: str = ""
    publishes: bool = False
    #: A person TYPES this environment's id before any change they make by
    #: hand from the terminal (REQ-PIPE-093 criteria 4-8).
    confirm_changes: bool = False
    #: The only switch for ticketing (criterion 10).
    ticketing: bool = False


def _load(path: Path | str | None = None) -> list[Environment]:
    path = Path(path or ENVIRONMENTS_PATH)
    if not path.exists():
        raise EnvironmentError_(f"no environments declared - {path} does not exist")
    raw = yaml.safe_load(path.read_text()) or {}
    declared = raw.get("environments")
    if not declared:
        raise EnvironmentError_(f"{path} declares no environments")

    out: list[Environment] = []
    seen: set[str] = set()
    for entry in declared:
        env_id = (entry or {}).get("id")
        if not env_id or not _SAFE_ID.match(str(env_id)):
            raise EnvironmentError_(
                f"{path}: {env_id!r} is not a usable environment id - lowercase "
                f"letters, digits and underscore only, because it reaches a "
                f"schema name, a file name and a URL")
        if env_id in seen:
            raise EnvironmentError_(f"{path}: {env_id!r} is declared more than once")
        seen.add(env_id)
        out.append(Environment(
            id=env_id,
            label=entry.get("label") or env_id,
            description=(entry.get("description") or "").strip(),
            publishes=bool(entry.get("publishes")),
            confirm_changes=bool(entry.get("confirm_changes")),
            ticketing=bool(entry.get("ticketing")),
        ))

    publishing = [e.id for e in out if e.publishes]
    if len(publishing) > 1:
        raise EnvironmentError_(
            f"{path}: {len(publishing)} environments claim to publish "
            f"({', '.join(publishing)}) - exactly one may, or two deployments "
            f"race to overwrite the same published dashboard")
    return out


def all_environments(path: Path | str | None = None) -> list[Environment]:
    """Every declared environment, in the order the file declares them."""
    return _load(path)


def get(env_id: str, path: Path | str | None = None) -> Environment:
    for env in _load(path):
        if env.id == env_id:
            return env
    known = ", ".join(e.id for e in _load(path))
    raise EnvironmentError_(
        f"{env_id!r} is not a declared environment - known: {known}. Add it to "
        f"{Path(path or ENVIRONMENTS_PATH)} if it is real, rather than letting a "
        f"typo become an environment")


def current(path: Path | str | None = None) -> Environment:
    """This deployment's environment, from MOTHMAN_ENVIRONMENT.

    Loud when unset. A build that cannot say where it came from is
    exactly the artifact this module exists to prevent, so there is no
    default - "local" would be the tempting one and would mean a
    production build silently labelled as somebody's laptop.
    """
    name = os.environ.get(ENVIRONMENT_ENV)
    if not name:
        known = ", ".join(e.id for e in _load(path))
        raise EnvironmentError_(
            f"{ENVIRONMENT_ENV} is not set, so this deployment cannot say which "
            f"environment it is. Set it to one of: {known}. There is deliberately "
            f"no default - a build that guesses is a build that can be labelled "
            f"as somewhere it is not")
    return get(name, path)


def current_or_none(path: Path | str | None = None) -> Environment | None:
    """For a caller that can legitimately carry on without knowing -
    a local report, a test. Never for anything published."""
    try:
        return current(path)
    except EnvironmentError_:
        return None


def ticket_repository() -> str | None:
    """`owner/repo` tickets go to, from contract/data-asset.yaml - a fact
    about the data asset, one per deployment (REQ-PIPE-093 criterion 12).
    Never GITHUB_REPOSITORY, which names whichever repository a workflow
    happens to run in."""
    from qa_tools.common.hierarchy import DATA_ASSET_YAML

    doc = yaml.safe_load(Path(DATA_ASSET_YAML).read_text()) or {}
    repo = str(doc.get("ticket_repository") or "").strip()
    return repo or None


def for_connection(path: Path | str | None = None) -> Environment:
    """The stated environment, checked BEFORE any database connection opens,
    for a read as well as a write (REQ-PIPE-093 criteria 1, 2 and 13).

    Raises where nothing is stated - naming the variable and the declared
    ids, with no default - and where the stated environment turns ticketing
    on while the asset names no ticket repository: refused loudly, because
    quietly running without tickets is how a production asset ends up with
    nobody told."""
    env = current(path)
    if env.ticketing and not ticket_repository():
        raise EnvironmentError_(
            f"the {env.id!r} environment turns ticketing on, but contract/data-asset.yaml "
            f"names no ticket_repository to open tickets in. Name it (owner/repo) or turn "
            f"ticketing off for {env.id!r} in contract/environments.yaml.")
    return env

