"""The PostgreSQL major this data asset targets, declared once and asserted
(REQ-PIPE-146).

WHY ASSERT IT AT ALL. The places this pipeline runs pin PostgreSQL in
different ways or not at all: Aurora pins the engine you choose and is the
anchor; a CI service container and the dev container pin an image tag; a
laptop gets whatever its package manager hands out; a cloud session gets
whatever its image shipped. A version difference nothing asserts is invisible
locally - the same failure this repository's own .python-version exists for.

THE MAJOR ONLY. Any minor is accepted and nothing is said about it (criterion
4): minors are bug and security fixes, and a warning on every CI run would be
noise somebody learns to ignore.

server_version_num, NEVER aurora_version() (criterion 3): the first exists on
every PostgreSQL; the second exists only on Aurora and would refuse every
other server for a reason that has nothing to do with the version.
"""
from __future__ import annotations

import re
from pathlib import Path

from qa_tools.common import config_yaml

ROOT = Path(__file__).resolve().parent.parent.parent
COMPOSE = ROOT / ".devcontainer" / "docker-compose.yml"
TEST_WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"
KEY = "postgres_major"


class VersionMismatch(RuntimeError):
    """The server is on a different major from the one this asset declares."""


def _data_asset_doc(path=None) -> dict:
    from qa_tools.common.hierarchy import DATA_ASSET_YAML

    return config_yaml.parse(Path(path or DATA_ASSET_YAML).read_text()) or {}


def declaration_errors(path=None) -> list[str]:
    """Criterion 6: missing, or not a whole-number major, is a gate failure."""
    doc = _data_asset_doc(path)
    if KEY not in doc:
        return [f"contract/data-asset.yaml: `{KEY}` is missing - declare the PostgreSQL "
                f"major this data asset targets (REQ-PIPE-146)"]
    value = doc[KEY]
    # bool is an int in Python, and `true` is not a version.
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return [f"contract/data-asset.yaml: `{KEY}` is {value!r}, which is not a whole-number "
                f"major such as 16"]
    return []


def declared_major(path=None) -> int:
    errors = declaration_errors(path)
    if errors:
        raise VersionMismatch(errors[0])
    return int(_data_asset_doc(path)[KEY])


def major_of(server_version_num: int | str) -> int:
    """`160013` -> 16. PostgreSQL 10 onwards encodes major * 10000 + minor."""
    return int(server_version_num) // 10000


def check_server(conn, declared: int | None = None) -> None:
    """Criterion 2: refuse a server on a different major, naming both."""
    check_number(conn.execute("SELECT current_setting('server_version_num')").fetchone()[0],
                 declared)


def check_number(num, declared: int | None = None) -> None:
    """check_server() for a version already read - supply_db reads it in the
    same statement as the database's identity (REQ-PIPE-107 NFR 1)."""
    want = declared if declared is not None else declared_major()
    got = major_of(num)
    if got != want:
        raise VersionMismatch(
            f"this server runs PostgreSQL {got} (server_version_num {num}), but "
            f"contract/data-asset.yaml declares postgres_major {want} - refusing rather than "
            f"letting a version nobody targeted behave differently from production")


_TAGGED = re.compile(r"^(?:[\w.\-]+/)*postgres:(?P<tag>\d[\w.\-]*)$")


def _is_postgres(image: str) -> bool:
    """Any image whose name says PostgreSQL - `postgres`, a registry path to
    it, or another publisher's `postgresql` - tagged, digest-pinned, templated
    or not at all (post-build-review #119 D4: anything narrower passes the
    shapes it does not recognise in silence)."""
    name = image.split("@", 1)[0].split(":", 1)[0].rsplit("/", 1)[-1]
    return name.startswith("postgres")


def image_tags(compose=None, workflow=None) -> dict[str, str]:
    """`{where: image}` for every PostgreSQL image in the dev container and in
    EVERY job of test.yml - its services and its own `container` - every one,
    not the first (post-build-review #87)."""
    found: dict[str, str] = {}
    compose_doc = config_yaml.parse(Path(compose or COMPOSE).read_text()) or {}
    for name, service in (compose_doc.get("services") or {}).items():
        image = str((service or {}).get("image") or "")
        if image and _is_postgres(image):
            found[f".devcontainer/docker-compose.yml service {name}"] = image
    wf = config_yaml.parse(Path(workflow or TEST_WORKFLOW).read_text()) or {}
    for job_name, job in (wf.get("jobs") or {}).items():
        job = job or {}
        for svc_name, svc in (job.get("services") or {}).items():
            image = str((svc if isinstance(svc, str) else (svc or {}).get("image")) or "")
            if image and _is_postgres(image):
                found[f".github/workflows/test.yml job {job_name} service {svc_name}"] = image
        container = job.get("container")
        image = str((container if isinstance(container, str)
                     else (container or {}).get("image")) or "")
        if image and _is_postgres(image):
            found[f".github/workflows/test.yml job {job_name} container"] = image
    return found


def image_tag_errors(declared: int | None = None, compose=None, workflow=None) -> list[str]:
    """Criterion 5: every image names the declared major - and one whose major
    cannot be read off it (no tag, a digest only, a template, another
    publisher's image) is an error, never a pass."""
    want = declared if declared is not None else declared_major()
    tags = image_tags(compose, workflow)
    if not tags:
        return ["no PostgreSQL image found in .devcontainer/docker-compose.yml or "
                ".github/workflows/test.yml - nothing to hold to postgres_major"]
    errors = []
    for where, image in tags.items():
        match = _TAGGED.match(image)
        if not match:
            errors.append(f"{where} runs {image}, whose PostgreSQL major cannot be read "
                          f"from its tag - pin it as postgres:{want} (or a {want}.x tag)")
            continue
        head = match.group("tag").split("-")[0].split(".")[0]
        if head != str(want):
            errors.append(f"{where} runs {image}, but contract/data-asset.yaml declares "
                          f"postgres_major {want}")
    return errors


def errors() -> list[str]:
    """Both gate checks, for the hierarchy gate that already reads this file."""
    out = declaration_errors()
    if out:
        return out
    return image_tag_errors()
