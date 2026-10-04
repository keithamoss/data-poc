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

        monkeypatch.setenv("MOTHMAN_ENVIRONMENT", "production")
        with supply_db.connect(label="test-reset") as conn:
            qa_store.ensure_schema(conn)
            _history(conn)
        result = CliRunner().invoke(env_group, ["reset-synthetic"],
                                    input=synthetic_reset.confirmation_phrase() + "\n")
        assert result.exit_code != 0 and "production" in result.output
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

