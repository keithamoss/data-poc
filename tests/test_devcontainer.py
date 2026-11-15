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
    assert "@db:" in env["MOTHMAN_TEST_DSN"], \
        "the DSN must name the compose service, not localhost"


def test_it_names_a_server_and_no_supply_database():
    """Keith, 2026-11-15: the dev container exports no MOTHMAN_SUPPLY_DSN -
    each command finds its asset's database, supply_<asset>, from
    MOTHMAN_ASSET - so what it states is the SERVER, as MOTHMAN_PG, a URL
    naming no database, and never a database a command would default to."""
    from qa_tools.common import supply_db

    env = _devcontainer_json()["remoteEnv"]
    assert "MOTHMAN_SUPPLY_DSN" not in env
    assert "MOTHMAN_ASSET" not in env
    assert not [k for k in env if k.startswith("PG")], "libpq's variables, rejected by Keith"
    assert env["MOTHMAN_PG"] == "postgresql://user:password@db:5432"
    assert supply_db.on_server(env["MOTHMAN_PG"], "supply_x").endswith("@db:5432/supply_x")
    post_create = (DEVCONTAINER / "post-create.sh").read_text()
    assert "MOTHMAN_SUPPLY_DSN=" not in post_create and "${MOTHMAN_SUPPLY_DSN" not in post_create
    db = _compose()["services"]["db"]
    assert "POSTGRES_DB" not in (db.get("environment") or {}), \
        "compose still creates a database no asset owns"
    assert "supply" not in " ".join(db["healthcheck"]["test"])


INIT_SCRIPT = DEVCONTAINER / "create-asset-databases.sh"


def _init_script_lists(assets_dir: Path) -> list[str]:
    import subprocess

    done = subprocess.run(["bash", str(INIT_SCRIPT), "--list"], capture_output=True,
                          text=True, check=True, env={"MOTHMAN_ASSETS_DIR": str(assets_dir),
                                                      "PATH": "/usr/bin:/bin"})
    return done.stdout.split()


def test_compose_creates_one_database_per_asset_from_the_mounted_asset_folders():
    """Keith, 2026-11-15: a compose init script, with assets/ mounted
    read-only into the database container, creates supply_<asset> per asset
    folder that has a data-asset.yaml (REQ-PIPE-343 criterion 7)."""
    db = _compose()["services"]["db"]
    mounts = db["volumes"]
    assert any(m.startswith("../assets:") and m.endswith(":ro") for m in mounts), mounts
    init = [m for m in mounts if ":/docker-entrypoint-initdb.d/" in m]
    assert init and init[0].split(":")[0] == f"./{INIT_SCRIPT.name}", mounts
    assets_at = next(m.split(":")[1] for m in mounts if m.startswith("../assets:"))
    assert f'MOTHMAN_ASSETS_DIR:-{assets_at}' in INIT_SCRIPT.read_text()

    want = sorted(f"supply_{yaml.safe_load((d / 'data-asset.yaml').read_text())['data_asset_id']}"
                  for d in (ROOT / "assets").iterdir() if (d / "data-asset.yaml").is_file())
    assert want, "no asset folder has a data-asset.yaml - the comparison would prove nothing"
    assert sorted(_init_script_lists(ROOT / "assets")) == want


def _run_init_script(assets_dir: Path):
    import subprocess

    return subprocess.run(["bash", str(INIT_SCRIPT), "--list"], capture_output=True, text=True,
                          env={"MOTHMAN_ASSETS_DIR": str(assets_dir), "PATH": "/usr/bin:/bin"})


@pytest.mark.parametrize("line", ["data_asset_id: Bad_Id", "data_asset_id: a;drop",
                                  "# no id at all"])
def test_a_bad_or_missing_id_fails_loudly_naming_the_folder(tmp_path, line):
    """post-build-review #334 L4: the id becomes a database name in SQL, so
    it is held to the asset-name pattern, and an asset with none fails."""
    (tmp_path / "alpha").mkdir()
    (tmp_path / "alpha" / "data-asset.yaml").write_text("data_asset_id: alpha\n")
    (tmp_path / "zeta").mkdir()
    (tmp_path / "zeta" / "data-asset.yaml").write_text(line + "\n")
    done = _run_init_script(tmp_path)
    assert done.returncode != 0
    assert "zeta" in done.stderr and "data_asset_id" in done.stderr


def test_the_list_succeeds_when_the_last_folder_is_no_asset(tmp_path):
    (tmp_path / "alpha").mkdir()
    (tmp_path / "alpha" / "data-asset.yaml").write_text('data_asset_id: "alpha"\n')
    (tmp_path / "zeta").mkdir()
    done = _run_init_script(tmp_path)
    assert (done.returncode, done.stdout.split()) == (0, ["supply_alpha"]), done.stderr


def test_a_folder_with_no_data_asset_yaml_gets_no_database(tmp_path):
    (tmp_path / "alpha").mkdir()
    (tmp_path / "alpha" / "data-asset.yaml").write_text("# an asset\ndata_asset_id: alpha   # its id\n")
    (tmp_path / "beta").mkdir()  # no data-asset.yaml: not an asset
    (tmp_path / "environments.yaml").write_text("environments: []\n")
    assert _init_script_lists(tmp_path) == ["supply_alpha"]


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


#: The data asset this module's tests act for, unless a test says otherwise
#: (C11, Keith 2026-11-02: every test module names its asset).
pytestmark = pytest.mark.asset("quarterly")
