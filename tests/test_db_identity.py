"""A checkout refuses to act against a database belonging to another data
asset or environment (REQ-PIPE-107)."""
from __future__ import annotations

import os
import re
from pathlib import Path

import psycopg
import pytest
from click.testing import CliRunner

from qa_tools.common import db_identity, hierarchy, supply_db

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def unmarked_dsn(supply_dsn, monkeypatch, worker_id):
    """A brand-new database of this test's own, carrying no identity."""
    admin = os.environ["MOTHMAN_TEST_DSN"]
    tag = "".join(c for c in os.environ.get("MOTHMAN_TEST_DB_TAG", "") if c.isalnum())[:12]
    name = f"mothman_ident_{tag + '_' if tag else ''}{worker_id}"
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{name}"')
    info = psycopg.conninfo.conninfo_to_dict(admin)
    info["dbname"] = name
    dsn = psycopg.conninfo.make_conninfo(**info)
    monkeypatch.setenv(supply_db.SUPPLY_DSN_ENV, dsn)
    yield dsn
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def _recorded(dsn):
    with psycopg.connect(dsn, autocommit=True) as conn:
        return db_identity.parse(conn.execute(db_identity.PROBE).fetchone()[1])


def _schemas(dsn):
    with psycopg.connect(dsn, autocommit=True) as conn:
        return {r[0] for r in conn.execute(
            "SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg\\_%' "
            "AND nspname <> 'information_schema'").fetchall()}


def _mark(*args, env="test"):
    from cli.app import cli
    return CliRunner().invoke(cli, ["env", "mark", *args],
                              env={"MOTHMAN_ENVIRONMENT": env})


class TestTheWorkersOwnDatabaseIsChecked:
    """Criteria 1, 5, 6 and 10 - a test worker's database included."""

    def test_the_marked_worker_database_opens(self, supply_dsn):
        assert _recorded(supply_dsn) == db_identity.Identity(hierarchy.data_asset_id(), "test")
        supply_db.connect(dsn=supply_dsn).close()

    def test_another_environment_is_refused_without_the_dsn(self, supply_dsn, monkeypatch):
        monkeypatch.setenv("MOTHMAN_ENVIRONMENT", "sandbox")
        with pytest.raises(supply_db.SupplyDbError) as caught:
            supply_db.connect(dsn=supply_dsn)
        message = str(caught.value)
        assert "environment 'test'" in message and "environment 'sandbox'" in message
        info = psycopg.conninfo.conninfo_to_dict(supply_dsn)
        for part in (info["dbname"], info.get("host", ""), info.get("password", ""),
                     info.get("user", ""), "postgresql://"):
            if part:
                assert part not in message, f"the refusal carries {part!r}"

    def test_another_data_asset_is_refused(self, supply_dsn, monkeypatch):
        monkeypatch.setattr(hierarchy, "data_asset_id", lambda: "data-asset-2")
        with pytest.raises(supply_db.SupplyDbError, match="data-asset-2"):
            supply_db.connect(dsn=supply_dsn)

    def test_the_tools_connection_details_are_checked_first(self, monkeypatch):
        """Criterion 10: dbt, Soda Core and datacontract-cli all take their
        details from connection_fields()."""
        assert supply_db.connection_fields()["dbname"]
        monkeypatch.setenv("MOTHMAN_ENVIRONMENT", "sandbox")
        with pytest.raises(supply_db.SupplyDbError, match="environment 'test'"):
            supply_db.connection_fields()


class TestAnUnmarkedDatabase:
    """Criteria 7, 8 and 9."""

    def test_is_refused_and_not_adopted(self, unmarked_dsn):
        with pytest.raises(supply_db.SupplyDbError, match="no recorded identity"):
            supply_db.connect(dsn=unmarked_dsn)
        assert _recorded(unmarked_dsn) is None

    def test_a_refused_command_leaves_it_exactly_as_it_was(self, unmarked_dsn):
        from qa_tools.common import qa_store

        before = _schemas(unmarked_dsn)
        with pytest.raises(supply_db.SupplyDbError):
            with supply_db.connect(dsn=unmarked_dsn) as conn:
                qa_store.ensure_schema(conn)
        assert _schemas(unmarked_dsn) == before

    def test_a_connection_string_cannot_claim_an_identity(self, unmarked_dsn):
        """The setting is read from the catalogue, never the session."""
        spoof = (unmarked_dsn + " options='-c mothman.data_asset_id=data-asset-1 "
                 "-c mothman.environment=test'")
        with pytest.raises(supply_db.SupplyDbError, match="no recorded identity"):
            supply_db.connect(dsn=spoof)

    def test_half_an_identity_cannot_be_read(self, unmarked_dsn):
        with psycopg.connect(unmarked_dsn, autocommit=True) as conn:
            name = conn.execute("SELECT current_database()").fetchone()[0]
            conn.execute(f'ALTER DATABASE "{name}" SET mothman.environment = \'test\'')
        with pytest.raises(supply_db.SupplyDbError, match="incomplete"):
            supply_db.connect(dsn=unmarked_dsn)

    def test_an_unreadable_identity_is_a_refusal(self, supply_dsn, monkeypatch):
        monkeypatch.setattr(db_identity, "PROBE", "SELECT no_such_function()")
        with pytest.raises(supply_db.SupplyDbError, match="could not be read"):
            supply_db.connect(dsn=supply_dsn)


class TestMarking:
    """Criteria 2, 3 and 4."""

    def test_the_environment_must_be_typed(self, unmarked_dsn):
        result = _mark("--confirm", "sandbox")
        assert result.exit_code != 0 and "nothing was marked" in result.output
        assert _recorded(unmarked_dsn) is None

    def test_without_a_terminal_it_asks_for_the_flag(self, unmarked_dsn):
        result = _mark()
        assert result.exit_code != 0 and "--confirm" in result.output
        assert _recorded(unmarked_dsn) is None

    def test_typed_it_marks_and_the_database_then_opens(self, unmarked_dsn):
        result = _mark("--confirm", "test")
        assert result.exit_code == 0, result.output
        assert _recorded(unmarked_dsn) == db_identity.Identity(hierarchy.data_asset_id(), "test")
        supply_db.connect(dsn=unmarked_dsn).close()
        again = _mark("--confirm", "test")
        assert again.exit_code == 0 and "already marked" in again.output

    def test_another_identity_is_replaced_only_when_typed_out(self, unmarked_dsn):
        assert _mark("--confirm", "sandbox", env="sandbox").exit_code == 0
        refused = _mark("--confirm", "test")
        assert refused.exit_code != 0 and "--replacing" in refused.output
        assert _recorded(unmarked_dsn).environment == "sandbox"
        wrong = _mark("--confirm", "test", "--replacing", "data-asset-1/local")
        assert wrong.exit_code != 0
        ok = _mark("--confirm", "test", "--replacing", "data-asset-1/sandbox")
        assert ok.exit_code == 0, ok.output
        assert _recorded(unmarked_dsn).environment == "test"

    def test_nothing_else_writes_an_identity(self):
        """Criterion 4: the only writers are the marking command and the test
        fixtures that create scratch databases."""
        writers = set()
        for path in list(ROOT.glob("qa_tools/**/*.py")) + list(ROOT.glob("cli/*.py")) + \
                list(ROOT.glob("pipeline/*.py")) + list(ROOT.glob("dashboard/*.py")):
            text = path.read_text()
            if path.name == "db_identity.py":
                continue
            if re.search(r"db_identity\.mark(_by_admin)?\(|mothman\.(environment|data_asset_id)",
                         text):
                writers.add(path.relative_to(ROOT).as_posix())
        assert writers == {"cli/env.py"}


class TestTheResetLeavesTheIdentity:
    """Criterion 11."""

    def test_reset_synthetic_keeps_it(self, unmarked_dsn):
        from qa_tools.common import qa_store, synthetic_reset

        assert _mark("--confirm", "test").exit_code == 0
        with supply_db.connect(dsn=unmarked_dsn) as conn:
            qa_store.ensure_schema(conn)
            synthetic_reset.reset(conn, synthetic_reset.confirmation_phrase())
        assert _recorded(unmarked_dsn) == db_identity.Identity(hierarchy.data_asset_id(), "test")


class TestEveryPlaceMarksItsOwn:
    """Criterion 12."""

    def test_the_sandbox_hook(self):
        assert "mothman env mark --confirm sandbox" in \
            (ROOT / ".claude/hooks/session-start.sh").read_text()

    def test_the_dev_container(self):
        assert "mothman env mark --confirm local" in \
            (ROOT / ".devcontainer/post-create.sh").read_text()

    def test_every_ci_job_with_a_database(self):
        import yaml

        workflow = yaml.safe_load((ROOT / ".github/workflows/test.yml").read_text())
        for name, job in workflow["jobs"].items():
            if "postgres" not in (job.get("services") or {}):
                continue
            runs = [s.get("run", "") for s in job["steps"]]
            mark = next(i for i, r in enumerate(runs) if "mothman env mark --confirm ci" in r)
            later = [i for i, r in enumerate(runs) if "mothman" in r and i != mark
                     and "env mark" not in r]
            assert all(i > mark for i in later), f"{name} uses the database before marking it"
