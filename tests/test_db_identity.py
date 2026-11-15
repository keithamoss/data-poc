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


def _typed(environment: str) -> str:
    """What a person types to mark a database for this test's asset and
    `environment` (REQ-PIPE-343 criterion 1: both ids, as
    <data asset>/<environment>)."""
    return f"{hierarchy.data_asset_id()}/{environment}"


def _words(result) -> str:
    """A command's output as plain words - the error panel wraps and boxes
    it, which is not what a test is about."""
    plain = re.sub(r"\x1b\[[0-9;]*m", "", result.output).replace("│", " ")
    return " ".join(plain.split())


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


#: The two directions: the test's own asset owns the worker database, and a
#: checkout configured for the other asset is pointed at it.
_OWNERS = [pytest.param(a, marks=pytest.mark.asset(a)) for a in ("quarterly", "daily")]


class TestEachAssetIsRefusedTheOthersDatabase:
    """REQ-PIPE-343 criterion 8: a checkout configured for each asset, pointed
    at the OTHER asset's marked database - this test worker's own, private,
    marked for the owning asset by the suite's fixture with its whole qa
    schema, so shaped like the real one - is refused on every route
    REQ-PIPE-107 criterion 10 names: a mothman command, the worker's database
    opened directly, and the connection details handed to dbt, Soda Core and
    datacontract-cli. The database is left exactly as it was found - a
    leftover run schema planted first, which the command would otherwise
    drop, is still there."""

    @pytest.mark.parametrize("owner", _OWNERS)
    def test_every_route_refuses_and_leaves_it_as_found(self, owner, supply_dsn, monkeypatch):
        from cli.app import cli
        from qa_tools import collections
        from qa_tools.common import assets, datacontract_common, dbt_common

        assert _recorded(supply_dsn) == db_identity.Identity(owner, "test")
        planted = "qa_planted_by_the_wrong_asset_test"
        with psycopg.connect(supply_dsn, autocommit=True) as conn:
            conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{planted}"')
        try:
            before = (_recorded(supply_dsn), _schemas(supply_dsn))
            mine = next(n for n in assets.names() if n != owner)
            assets.release_claim()
            monkeypatch.setenv(assets.ASSET_ENV, mine)
            monkeypatch.setenv(supply_db.SUPPLY_DSN_ENV, supply_dsn)
            contract = str(assets.selected().folder / collections.all_collections()[0].contract)
            dbname = psycopg.conninfo.conninfo_to_dict(supply_dsn)["dbname"]

            def refused(message: str) -> None:
                assert repr(owner) in message and repr(mine) in message, message
                assert dbname not in message and "postgresql://" not in message, message

            routes = {
                "the worker's database": lambda: supply_db.connect(dsn=supply_dsn),
                "dbt's connection details": dbt_common._dbt_env,
                "Soda Core's": lambda: supply_db.soda_config_yaml("ds", "public"),
                "datacontract-cli's": lambda: datacontract_common.run_against_warehouse(
                    contract, "public"),
            }
            for route, call in routes.items():
                try:
                    call()
                except supply_db.SupplyDbError as exc:
                    refused(str(exc))
                else:
                    pytest.fail(f"{route} was not refused")
            result = CliRunner().invoke(cli, ["supply", "tidy", "--yes"], env={
                assets.ASSET_ENV: mine, supply_db.SUPPLY_DSN_ENV: supply_dsn,
                "MOTHMAN_ENVIRONMENT": "test"})
            assert result.exit_code != 0
            refused(_words(result))
            assets.release_claim()
            assert (_recorded(supply_dsn), _schemas(supply_dsn)) == before
            assert planted in before[1]
        finally:
            with psycopg.connect(supply_dsn, autocommit=True) as conn:
                conn.execute(f'DROP SCHEMA IF EXISTS "{planted}"')


class TestARemarkReachesPooledConnections:
    """post-build-review (split T1): a connection is pooled by what its
    identity check vouched for, so a database re-marked for another asset
    while one sat idle was reached through it unchecked - found by the test
    above when the suite's fixture re-marked a worker's database between two
    tests of different assets."""

    def test_a_connection_pooled_before_a_remark_is_not_handed_out(self, unmarked_dsn):
        from qa_tools.common import assets

        mine = hierarchy.data_asset_id()
        other = next(n for n in assets.names() if n != mine)
        with psycopg.connect(unmarked_dsn, autocommit=True) as conn:
            db_identity.mark(conn, db_identity.Identity(mine, "test"))
        supply_db.connect(dsn=unmarked_dsn).close()  # back to the pool, vouched for `mine`
        with psycopg.connect(unmarked_dsn, autocommit=True) as conn:
            db_identity.mark(conn, db_identity.Identity(other, "test"))
        with pytest.raises(supply_db.SupplyDbError, match=repr(other)):
            supply_db.connect(dsn=unmarked_dsn)


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

    def test_an_empty_identity_table_is_no_identity(self, unmarked_dsn):
        with psycopg.connect(unmarked_dsn, autocommit=True) as conn:
            for statement in db_identity.DDL:
                conn.execute(statement)
        with pytest.raises(supply_db.SupplyDbError, match="no recorded identity"):
            supply_db.connect(dsn=unmarked_dsn)

    def test_an_unreadable_identity_is_a_refusal(self, supply_dsn, monkeypatch):
        monkeypatch.setattr(db_identity, "PROBE", "SELECT no_such_function()")
        with pytest.raises(supply_db.SupplyDbError, match="could not be read"):
            supply_db.connect(dsn=supply_dsn)


class TestMarking:
    """Criteria 2, 3 and 4."""

    def test_the_environment_must_be_typed(self, unmarked_dsn):
        result = _mark("--confirm", _typed("sandbox"))
        assert result.exit_code != 0 and "nothing was marked" in result.output
        assert _recorded(unmarked_dsn) is None

    def test_the_data_asset_must_be_typed_too(self, unmarked_dsn):
        """REQ-PIPE-343 criterion 1: the person types the asset's data_asset_id
        as well as the environment id - the environment alone marks nothing."""
        result = _mark("--confirm", "test")
        assert result.exit_code != 0 and "nothing was marked" in result.output
        assert "<data asset>/<environment>" in _words(result)
        assert _recorded(unmarked_dsn) is None

    def test_another_assets_id_typed_marks_nothing(self, unmarked_dsn):
        other = "daily" if hierarchy.data_asset_id() != "daily" else "quarterly"
        result = _mark("--confirm", f"{other}/test")
        assert result.exit_code != 0 and "nothing was marked" in result.output
        assert _recorded(unmarked_dsn) is None

    def test_at_a_terminal_both_are_asked_for(self, unmarked_dsn, monkeypatch):
        from cli import common

        monkeypatch.setattr(common, "require_tty", lambda hint: None)
        asked = []
        monkeypatch.setattr(common, "_ask_text", lambda m: asked.append(m) or _typed("test"))
        assert _mark().exit_code == 0
        assert "<data asset>/<environment>" in asked[0]
        assert _recorded(unmarked_dsn) == db_identity.Identity(hierarchy.data_asset_id(), "test")

    def test_without_a_terminal_it_asks_for_the_flag(self, unmarked_dsn):
        result = _mark()
        assert result.exit_code != 0 and "--confirm" in result.output
        assert _recorded(unmarked_dsn) is None

    def test_typed_it_marks_and_the_database_then_opens(self, unmarked_dsn):
        result = _mark("--confirm", _typed("test"))
        assert result.exit_code == 0, result.output
        assert _recorded(unmarked_dsn) == db_identity.Identity(hierarchy.data_asset_id(), "test")
        supply_db.connect(dsn=unmarked_dsn).close()
        again = _mark("--confirm", _typed("test"))
        assert again.exit_code == 0 and "already marked" in again.output

    def test_another_identity_is_replaced_only_when_typed_out(self, unmarked_dsn,
                                                              monkeypatch):
        """At a terminal, typing the identity being replaced - exactly."""
        from cli import common

        assert _mark("--confirm", _typed("sandbox"), env="sandbox").exit_code == 0
        monkeypatch.setattr(common, "require_tty", lambda hint: None)
        from qa_tools.common import hierarchy

        asset_id = hierarchy.data_asset_id()  # the asset's own id (the asset split)
        answers = iter([f"{asset_id}/local"])
        monkeypatch.setattr(common, "_ask_text", lambda m: next(answers))
        wrong = _mark("--confirm", _typed("test"))
        assert wrong.exit_code != 0 and _recorded(unmarked_dsn).environment == "sandbox"
        answers = iter([f"{asset_id}/sandbox"])
        ok = _mark("--confirm", _typed("test"))
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
            if re.search(r"db_identity\.mark\(|mothman\.(environment|data_asset_id)",
                         text):
                writers.add(path.relative_to(ROOT).as_posix())
        # The reset used to drop the qa schema and put the identity back; it
        # now never touches the identity table at all (post-build-review #122
        # D1/D2), so marking is the only writer.
        assert writers == {"cli/env.py"}


class TestItLivesInATable:
    """Keith, 2026-10-06 (REQ-PIPE-107's provisional, over database-level
    settings): the identity is ONE ROW in the qa schema, so it travels with
    a dump and with a database copied from a template."""

    def test_marking_writes_one_row(self, unmarked_dsn):
        from qa_tools.common import qa_store

        assert _mark("--confirm", _typed("test")).exit_code == 0
        with psycopg.connect(unmarked_dsn, autocommit=True) as conn:
            rows = conn.execute(f'SELECT data_asset_id, environment FROM '
                                f'"{qa_store.SCHEMA}".identity').fetchall()
        assert rows == [(hierarchy.data_asset_id(), "test")]

    def test_a_second_row_cannot_exist(self, unmarked_dsn):
        from qa_tools.common import qa_store

        assert _mark("--confirm", _typed("test")).exit_code == 0
        with psycopg.connect(unmarked_dsn, autocommit=True) as conn:
            with pytest.raises(psycopg.errors.IntegrityError):
                conn.execute(f'INSERT INTO "{qa_store.SCHEMA}".identity '
                             "(data_asset_id, environment) VALUES ('other', 'production')")

    def test_a_template_copy_carries_it(self, unmarked_dsn):
        assert _mark("--confirm", _typed("test")).exit_code == 0
        admin = os.environ["MOTHMAN_TEST_DSN"]
        source = psycopg.conninfo.conninfo_to_dict(unmarked_dsn)["dbname"]
        copy = f"{source}_copy"
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{copy}" WITH (FORCE)')
            conn.execute(f'CREATE DATABASE "{copy}" TEMPLATE "{source}"')
        try:
            info = psycopg.conninfo.conninfo_to_dict(unmarked_dsn)
            info["dbname"] = copy
            assert _recorded(psycopg.conninfo.make_conninfo(**info)) == \
                db_identity.Identity(hierarchy.data_asset_id(), "test")
        finally:
            with psycopg.connect(admin, autocommit=True) as conn:
                conn.execute(f'DROP DATABASE IF EXISTS "{copy}" WITH (FORCE)')

    def test_one_statement_reads_it_and_the_version(self, supply_dsn):
        """NFR 1: one round trip at connect time, the table read only where
        it exists - an unmarked database has no qa schema to read."""
        assert db_identity.PROBE.count(";") == 0
        assert "to_regclass" in db_identity.PROBE


class TestTheResetLeavesTheIdentity:
    """Criterion 11."""

    def test_reset_synthetic_keeps_it(self, unmarked_dsn):
        from qa_tools.common import qa_store, synthetic_reset

        assert _mark("--confirm", _typed("test")).exit_code == 0
        with supply_db.connect(dsn=unmarked_dsn) as conn:
            qa_store.ensure_schema(conn)
            synthetic_reset.reset(conn, synthetic_reset.confirmation_phrase())
        assert _recorded(unmarked_dsn) == db_identity.Identity(hierarchy.data_asset_id(), "test")


class TestEveryPlaceMarksItsOwn:
    """Criterion 12."""

    # EACH ASSET'S OWN DATABASE (REQ-PIPE-343 criterion 4), marked in a loop
    # over the asset folders, typing both ids (criterion 1).
    _EACH_ASSET = 'for asset in $(cd assets && ls -d */ | tr -d /); do'

    def test_the_sandbox_hook(self):
        text = (ROOT / ".claude/hooks/session-start.sh").read_text()
        assert 'mothman env mark --confirm "${asset}/sandbox"' in text
        assert 'supply_${asset}' in text and self._EACH_ASSET in text
        # REQ-PIPE-352 criterion 4: each asset's staged-table count, named for
        # the asset, read from its own database.
        count = text[text.index("# --- Is there any data here?"):text.index('echo "Ready."')]
        assert self._EACH_ASSET in count and 'db="supply_${asset}"' in count
        assert count.count('-d "$db"') == 3 and "-d supply " not in count
        assert 'say "${asset}: ${db} has ${STAGED} staged table(s)."' in count

    def test_the_dev_container(self):
        text = (ROOT / ".devcontainer/post-create.sh").read_text()
        loop = text.index(self._EACH_ASSET)
        mark = text.index('mothman env mark --confirm "${asset}/local"')
        assert loop < mark and 'MOTHMAN_SUPPLY_DSN="${server}/supply_${asset}"' in text

    def test_every_ci_job_with_a_database(self):
        import yaml

        from qa_tools.common import postgres_version

        workflow = yaml.safe_load((ROOT / ".github/workflows/test.yml").read_text())
        checked = 0
        for name, job in workflow["jobs"].items():
            # BY IMAGE, whatever the service is called (#119 D7).
            images = [str((s or {}).get("image") or "") for s in
                      (job.get("services") or {}).values()]
            if not any(postgres_version._is_postgres(i) for i in images if i):
                continue
            checked += 1
            runs = [s.get("run", "") for s in job["steps"]]
            mark = next(i for i, r in enumerate(runs)
                        if 'mothman env mark --confirm "${asset}/ci"' in r)
            # `pipeline cache-key` hashes files and never connects - which
            # tests/test_replay_inputs.py asserts - so it may key the cache
            # before the database exists.
            later = [i for i, r in enumerate(runs) if "mothman" in r and i != mark
                     and "env mark" not in r and "pipeline cache-key" not in r]
            assert all(i > mark for i in later), f"{name} uses the database before marking it"
        assert checked >= 2, "no CI job with a database was found - this checked nothing"


class TestReplacingAnIdentityNeedsAPerson:
    """post-build-review #119 D1 (REQ-PIPE-093 criteria 4 and 6): a flag may
    stand in for typing only to mark an UNMARKED database - the setup
    scripts' case. Replacing an identity, production's or anyone's, needs a
    person at a terminal, and no flag skips it."""

    def test_flags_alone_cannot_replace_an_identity(self, unmarked_dsn):
        assert _mark("--confirm", _typed("sandbox"), env="sandbox").exit_code == 0
        out = _mark("--confirm", _typed("production"), env="production")
        assert out.exit_code != 0 and "terminal" in out.output
        assert _recorded(unmarked_dsn).environment == "sandbox"

    def test_a_production_identity_cannot_be_relabelled_by_flags(self, unmarked_dsn):
        assert _mark("--confirm", _typed("production"), env="production").exit_code == 0
        out = _mark("--confirm", _typed("sandbox"), env="sandbox")
        assert out.exit_code != 0
        assert _recorded(unmarked_dsn).environment == "production"

    def test_the_refusal_does_not_hand_over_the_answer(self, unmarked_dsn):
        """Criterion 3 asks the person to TYPE the identity being replaced;
        printing the exact flag turns that into a copy-paste."""
        assert _mark("--confirm", _typed("sandbox"), env="sandbox").exit_code == 0
        out = _mark("--confirm", _typed("test"))
        import re

        flat = re.sub(r"[\s\u2502\u256d\u256e\u2570\u256f\u2500]+", " ", out.output)
        assert out.exit_code != 0 and "data-asset-1/sandbox" not in flat.replace(
            "data asset 'data-asset-1', environment 'sandbox'", "")


#: The data asset this module's tests act for, unless a test says otherwise
#: (C11, Keith 2026-11-02: every test module names its asset).
pytestmark = pytest.mark.asset("quarterly")
