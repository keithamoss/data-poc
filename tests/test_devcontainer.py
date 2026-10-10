"""The development container supplies a PostgreSQL, and it is the same
one CI uses (REQ-TEST-095 criteria 4, 5 and 6).

WHAT THIS CAN AND CANNOT CHECK. It cannot launch a container - no
Docker daemon is reachable in this project's cloud sessions - so it
checks the things that are checkable from the files and would silently
drift otherwise: that both PostgreSQL versions agree, that the suite is
handed a connection string rather than starting anything, and that
something waits for the database to accept connections.

THE VERSION AGREEMENT IS THE ONE WORTH GUARDING. Two files name a
PostgreSQL major by hand, and a green suite in the dev container only
means what a green suite in CI means while they match. REQ-PIPE-093
will make it one declared value both read; until it exists, this test
is what notices.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
DEVCONTAINER = ROOT / ".devcontainer"


def _devcontainer_json() -> dict:
    """devcontainer.json permits // comments, which json.loads does not."""
    raw = (DEVCONTAINER / "devcontainer.json").read_text()
    return json.loads(re.sub(r"^\s*//.*$", "", raw, flags=re.M))


def _compose() -> dict:
    return yaml.safe_load((DEVCONTAINER / "docker-compose.yml").read_text())


def _ci_postgres_images(workflow_text: str | None = None) -> dict[str, str]:
    """`{job: image}` for EVERY job with a postgres service.

    EVERY, not the first (post-build-review #87): test.yml runs two jobs
    with their own service containers, and returning the first one found
    left the second free to drift with nothing noticing.
    """
    text = workflow_text if workflow_text is not None else \
        (ROOT / ".github" / "workflows" / "test.yml").read_text()
    workflow = yaml.safe_load(text)
    found = {name: (job.get("services") or {})["postgres"]["image"]
             for name, job in workflow["jobs"].items()
             if "postgres" in (job.get("services") or {})}
    if not found:
        pytest.fail("no postgres service container found in .github/workflows/test.yml")
    return found


def test_a_development_container_exists():
    assert (DEVCONTAINER / "devcontainer.json").is_file()
    assert (DEVCONTAINER / "docker-compose.yml").is_file()


def test_it_supplies_a_postgres_the_suite_connects_to():
    compose = _compose()
    assert "db" in compose["services"], "the dev container supplies no database"
    env = _devcontainer_json()["remoteEnv"]
    # HANDED A CONNECTION STRING, not left to discover one - criterion
    # 1's "takes a connection string for a PostgreSQL that already
    # exists" is only true if something sets it.
    assert env["MOTHMAN_TEST_DSN"].startswith("postgresql://")
    assert env["MOTHMAN_SUPPLY_DSN"].startswith("postgresql://")
    assert "@db:" in env["MOTHMAN_TEST_DSN"], \
        "the DSN must name the compose service, not localhost"


def test_the_dev_container_and_ci_pin_the_same_postgres_major():
    """The whole point of pinning. A green suite in one place means what
    a green suite in the other means only while these agree."""
    dev = _compose()["services"]["db"]["image"]
    for job, ci in _ci_postgres_images().items():
        assert _major(dev) == _major(ci), (
            f"the dev container runs {dev} and CI's {job} job runs {ci} - a suite "
            f"green in one says nothing about the other. REQ-PIPE-146 makes this "
            f"one declared value.")


def _major(image: str) -> str:
    return image.split(":")[1].split(".")[0]


def test_every_ci_job_is_compared_not_only_the_first():
    """post-build-review #87, pinned against a workflow where only the
    SECOND job has drifted - the case the first-match lookup missed."""
    workflow = """
jobs:
  fast:
    services:
      postgres: {image: "postgres:16"}
  slow:
    services:
      postgres: {image: "postgres:17"}
"""
    images = _ci_postgres_images(workflow)
    assert images == {"fast": "postgres:16", "slow": "postgres:17"}
    assert {_major(i) for i in images.values()} == {"16", "17"}


def test_something_waits_for_the_database_to_accept_connections():
    """Criterion 6. A started container is not an accepting one, and the
    suite refuses to run without a reachable database rather than
    skipping - so without this a fresh container's first run races."""
    compose = _compose()
    assert "healthcheck" in compose["services"]["db"], "no health check on the database"
    assert compose["services"]["app"]["depends_on"]["db"]["condition"] == "service_healthy", \
        "the app does not wait for the database to be healthy"


def test_the_container_does_not_start_a_database_from_the_test_path():
    """Criterion 1 again, from the other side: the SUITE must not start,
    install or containerise a database. Compose supplying one beside it
    is a different thing from conftest bringing one up."""
    conftest = (ROOT / "tests" / "conftest.py").read_text()
    for forbidden in ("docker", "testcontainers", "pg_ctl", "initdb"):
        assert forbidden not in conftest.lower(), \
            f"tests/conftest.py mentions {forbidden!r} - the suite must only connect"
