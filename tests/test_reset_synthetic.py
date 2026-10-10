"""Starting a SYNTHETIC asset from empty is one deliberate act, and
nothing else deletes recorded history (REQ-PIPE-144 criteria 19-23, 38
and 43)."""
from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from qa_tools.common import bootstrap, qa_store, supply_db, synthetic_reset

ROOT = Path(__file__).resolve().parent.parent


def _history(conn) -> None:
    import filing_support
    from qa_tools.common.assignment import Assignment

    filing_support.file(Assignment(dataset_id="cp-clients", supply_id="cp-clients@x",
                                   slot="2026-Q1", branch="open-slot-unfilled",
                                   considered=("2026-Q1",)))


class TestTheCommand:

    def test_it_deletes_everything_once_the_phrase_is_typed(self, private_supply_dsn):
        from cli.env import env_group

        with supply_db.connect(label="test-reset") as conn:
            qa_store.ensure_schema(conn)
            _history(conn)
            assert bootstrap.holds_history(conn)
        result = CliRunner().invoke(env_group, ["reset-synthetic"],
                                    input=synthetic_reset.confirmation_phrase() + "\n")
        assert result.exit_code == 0, result.output
        with supply_db.connect(label="test-reset") as conn:
            assert not bootstrap.holds_history(conn)
            assert synthetic_reset.schemas_to_drop(conn) == []

    def test_a_period_standing_on_another_does_not_stop_it(self, private_supply_dsn):
        """#113 H1: the database guard refuses a cascaded drop of a period's
        view, and dropping schemas one at a time made the stood-on period's
        drop exactly that. One statement drops them together."""
        with supply_db.connect(label="test-reset") as conn:
            qa_store.ensure_schema(conn)
            _history(conn)
            conn.execute('CREATE SCHEMA "period_2023_q1"')
            conn.execute('CREATE TABLE "period_2023_q1"."cp_carers" (id int)')
            conn.execute('CREATE SCHEMA "period_2023_q2"')
            conn.execute('CREATE VIEW "period_2023_q2"."cp_carers" AS '
                         'SELECT * FROM "period_2023_q1"."cp_carers"')
            synthetic_reset.reset(conn, synthetic_reset.confirmation_phrase())
            assert synthetic_reset.schemas_to_drop(conn) == []

    def test_the_identity_table_is_never_dropped(self, private_supply_dsn):
        """Keith, 2026-10-06 (post-build-review #122 D1/D2): dropping the qa
        schema and re-marking in one transaction still let another
        connection's probe, on an older snapshot, see a NEW identity table
        it could not read - and refuse a marked database as unmarked. And
        the re-mark rewrote marked_at. Every qa table goes but this one."""
        def _identity(conn):
            return conn.execute(
                f"SELECT to_regclass('{qa_store.SCHEMA}.identity')::oid, "
                f'(SELECT marked_at FROM "{qa_store.SCHEMA}".identity)').fetchall()[0]

        with supply_db.connect(label="test-reset") as conn:
            qa_store.ensure_schema(conn)
            _history(conn)
            before = _identity(conn)
            assert before[1] is not None, "the test database is marked"
            synthetic_reset.reset(conn, synthetic_reset.confirmation_phrase())
            assert _identity(conn) == before
            assert not bootstrap.holds_history(conn)
            assert synthetic_reset.schemas_to_drop(conn) == []

    def test_a_wrong_phrase_deletes_nothing(self, private_supply_dsn):
        from cli.env import env_group

        with supply_db.connect(label="test-reset") as conn:
            qa_store.ensure_schema(conn)
            _history(conn)
        result = CliRunner().invoke(env_group, ["reset-synthetic"], input="yes\n")
        assert result.exit_code != 0
        with supply_db.connect(label="test-reset") as conn:
            assert bootstrap.holds_history(conn)

    def test_the_prompt_names_what_it_deletes(self, private_supply_dsn):
        from cli.env import env_group

        result = CliRunner().invoke(env_group, ["reset-synthetic"], input="no\n")
        flat = " ".join(result.output.split())
        assert synthetic_reset.confirmation_phrase() in flat
        assert "decision" in flat and "filing" in flat and "delivery" in flat

    def test_an_asset_not_declared_synthetic_is_refused(self, private_supply_dsn, monkeypatch):
        from cli.env import env_group

        monkeypatch.setattr(synthetic_reset, "is_synthetic", lambda: False)
        with supply_db.connect(label="test-reset") as conn:
            qa_store.ensure_schema(conn)
            _history(conn)
        result = CliRunner().invoke(env_group, ["reset-synthetic"],
                                    input=synthetic_reset.confirmation_phrase() + "\n")
        assert result.exit_code != 0 and "not declared synthetic" in result.output
        with supply_db.connect(label="test-reset") as conn:
            assert bootstrap.holds_history(conn)
            with pytest.raises(synthetic_reset.NotSynthetic):
                synthetic_reset.reset(conn, synthetic_reset.confirmation_phrase())

    def test_a_production_checkout_is_refused(self, private_supply_dsn, monkeypatch):
        """Criterion 22."""
        from cli.env import env_group

        with supply_db.connect(label="test-reset") as conn:
            qa_store.ensure_schema(conn)
            _history(conn)
        # Only the command acts as production: this database is marked
        # `test`, so anything else would be refused by the identity check
        # (REQ-PIPE-107) before it got as far as the rule under test.
        monkeypatch.setenv("MOTHMAN_ENVIRONMENT", "production")
        result = CliRunner().invoke(env_group, ["reset-synthetic"],
                                    input=synthetic_reset.confirmation_phrase() + "\n")
        assert result.exit_code != 0 and "production" in result.output
        monkeypatch.setenv("MOTHMAN_ENVIRONMENT", "test")
        with supply_db.connect(label="test-reset") as conn:
            assert bootstrap.holds_history(conn)

    def test_this_asset_is_declared_synthetic(self):
        assert synthetic_reset.is_synthetic() is True

    def test_it_resets_a_schema_too_old_to_open(self, private_supply_dsn):
        """ensure_schema refuses an older schema and points HERE, so this
        must work on one."""
        with supply_db.connect(label="test-reset") as conn:
            qa_store.ensure_schema(conn)
            conn.execute(f'UPDATE "{qa_store.SCHEMA}".schema_version SET version = 1')
            synthetic_reset.reset(conn, synthetic_reset.confirmation_phrase())
            qa_store.ensure_schema(conn)


class TestNothingElseDeletes:

    def test_no_other_module_calls_it(self):
        """Criterion 23: not reachable from any other command."""
        callers = []
        for path in list((ROOT / "cli").glob("*.py")) + list((ROOT / "qa_tools").rglob("*.py")):
            if path.name in ("synthetic_reset.py",):
                continue
            text = path.read_text()
            if "synthetic_reset" in text and path.name != "env.py":
                callers.append(path.name)
        assert callers == []

    def test_bootstrap_force_refuses_over_history(self, private_supply_dsn):
        """Criterion 38: --force never wipes, and never stacks on top."""
        with supply_db.connect(label="test-reset") as conn:
            qa_store.ensure_schema(conn)
            _history(conn)
        result = bootstrap.bootstrap(force=True)
        assert result.refused and not result.populated
        assert "reset-synthetic" in result.reason
        with supply_db.connect(label="test-reset") as conn:
            assert bootstrap.holds_history(conn)

    def test_the_filing_and_delivery_tables_have_their_new_shape(self, private_supply_dsn):
        """Criterion 33's column-absence tests."""
        with supply_db.connect(label="test-reset") as conn:
            qa_store.ensure_schema(conn)
            def cols(table):
                return {r[0] for r in conn.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = ? AND table_name = ?",
                    [qa_store.SCHEMA, table]).fetchall()}
            assert not {"record", "received_at"} & cols("filing")
            assert "contested" not in cols("delivery")
            assert {"received_at", "received_instant", "received_from",
                    "receipt_sequence"} <= cols("delivery_file")



class TestItTouchesOnlyWhatIsOurs:
    """delivery-critic on REQ-PIPE-144: the reset matched schema NAMES by
    prefix, so `staging_someone_elses` went too, and its CASCADE reached a
    view in `public` that the prompt never listed."""

    def test_a_schema_that_only_shares_a_prefix_is_left_alone(self, private_supply_dsn):
        with supply_db.connect(label="test-reset") as conn:
            qa_store.ensure_schema(conn)
            conn.execute('CREATE SCHEMA "staging_someone_elses"')
            conn.execute('CREATE SCHEMA "sample_reports"')
            assert "staging_someone_elses" not in synthetic_reset.schemas_to_drop(conn)
            assert "sample_reports" not in synthetic_reset.schemas_to_drop(conn)
            synthetic_reset.reset(conn, synthetic_reset.confirmation_phrase())
            names = {r[0] for r in conn.execute("SELECT nspname FROM pg_namespace").fetchall()}
            assert {"staging_someone_elses", "sample_reports"} <= names

    def test_it_refuses_rather_than_cascade_into_something_else(self, private_supply_dsn):
        with supply_db.connect(label="test-reset") as conn:
            qa_store.ensure_schema(conn)
            conn.execute(f'CREATE VIEW public.depends_on_qa AS SELECT * FROM "{qa_store.SCHEMA}".filing')
            with pytest.raises(synthetic_reset.WouldReachOutside) as caught:
                synthetic_reset.reset(conn, synthetic_reset.confirmation_phrase())
            assert "public.depends_on_qa" in str(caught.value)
            assert conn.execute(f"SELECT to_regclass('{qa_store.SCHEMA}.filing')").fetchall()[0][0]
