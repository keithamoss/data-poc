"""REQ-TEST-245: every collection's commands come from one factory.

What is tested here is what the two per-collection modules could never
show: that a THIRD collection, registered only in the hierarchy, gets its
group, its menu entry and its --collection value with no code of its own
(criteria 1, 5, 6 and 11); that a broken adapter takes down only its own
commands (criterion 8); and that asking for help imports no QA tool
(criterion 7). Today's two collections keep their existing tests in
test_cli_bdm.py and test_cli_cp.py, which drive the same factory.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli import collection_cli, common
from third_collection import BARE_ID, BARE_SHORT, FAKE_ID, FAKE_SHORT

ROOT = Path(__file__).resolve().parent.parent
_runner = CliRunner()


@pytest.fixture(autouse=True)
def _fresh_command_objects():
    """One command object per collection for the life of the process - so a
    test's third collection must not outlive it."""
    collection_cli._cached.cache_clear()
    yield
    collection_cli._cached.cache_clear()


def _coll(cid):
    from qa_tools import collections

    return collections.by_id(cid)


class TestOneFactory:
    """Criteria 1 to 4, for a collection nobody wrote a module for."""

    def test_a_third_collection_gets_its_group_by_shape(self, third_collection):
        group = collection_cli.make_group(_coll(FAKE_ID))
        assert group.name == FAKE_SHORT
        assert set(group.commands) == {"qa", "generate-synthetic-data"}
        qa = {p.name for p in group.commands["qa"].params}
        assert "file_path" in qa and "folder" not in qa, "one table means --file (criterion 3)"
        assert isinstance(collection_cli.of(FAKE_SHORT), collection_cli.CollectionCLI)

    def test_it_is_labelled_by_its_one_dataset(self, third_collection):
        assert collection_cli.label(_coll(FAKE_ID)) == "Fake Things"
        assert collection_cli.label(_coll("child-protection")) == "Child Protection"
        assert collection_cli.label(_coll("civil-registration")) == "Birth Registrations"

    def test_the_trial_flag_follows_the_providers_one_declaration(self, third_collection):
        """The fake provider declares no target trial, so its group offers
        no --skip-target-trial; Birth Registrations' declares one (criterion 4)."""
        def offers(cid):
            gen = collection_cli.make_group(_coll(cid)).commands["generate-synthetic-data"]
            return "skip_target_trial" in {p.name for p in gen.params}

        assert not offers(FAKE_ID)
        assert offers("civil-registration")
        assert not offers("child-protection")

    def test_the_many_table_shape_lists_its_tables_from_the_hierarchy(self):
        qa = collection_cli.make_group(_coll("child-protection")).commands["qa"]
        table = next(p for p in qa.params if p.name == "table")
        assert list(table.type.choices) == [d.table for d in _coll("child-protection").datasets]


class TestTheTUIMenus:
    """Criteria 5 and 11 for cli/app.py: 'Which dataset?' is listed from the
    registry in hierarchy order and the choice runs THAT collection."""

    def _drive(self, monkeypatch, pick):
        import cli.app as app

        offered = {}

        def select(message, choices, **_):
            offered["choices"] = list(choices)
            return pick
        monkeypatch.setattr(common, "select", select)
        ran = []
        monkeypatch.setattr(collection_cli.of(FAKE_ID), "run_qa_interactive",
                            lambda: ran.append(FAKE_ID))
        for cid in ("civil-registration", "child-protection"):
            monkeypatch.setattr(collection_cli.of(cid), "run_qa_interactive",
                                lambda cid=cid: ran.append(cid))
        app._qa_menu()
        return offered["choices"], ran

    def test_a_third_collection_is_offered_and_runs_its_own_flow(self, third_collection,
                                                                monkeypatch):
        choices, ran = self._drive(monkeypatch, "Fake Things")
        assert choices == ["Birth Registrations", "Child Protection", "Fake Things"]
        assert ran == [FAKE_ID]

    def test_child_protection_is_not_where_an_unknown_choice_falls(self, third_collection,
                                                                  monkeypatch):
        with pytest.raises(KeyError):
            self._drive(monkeypatch, "Something Else")

    def test_the_generate_menu_dispatches_the_same_way(self, third_collection, monkeypatch):
        import cli.app as app

        monkeypatch.setattr(common, "select", lambda *a, **k: "Fake Things")
        fake = collection_cli.of(FAKE_ID)
        made = []
        monkeypatch.setattr(fake, "manifest_exists", lambda: False)
        monkeypatch.setattr(fake, "generate_synthetic_data", lambda **_: made.append(FAKE_ID))
        monkeypatch.setattr(fake, "generated_output_dir", lambda: "/nowhere")
        app._generate_menu()
        assert made == [FAKE_ID]


class TestTheSharedCollectionOption:
    """Criteria 6 and 11 for cli/pipeline.py, cli/debug.py and cli/supply.py."""

    def test_pipeline_run_runs_a_third_collection(self, third_collection, monkeypatch):
        import qa_tools.common.bootstrap as boot
        from cli import dashboard as dashboard_cli
        from cli import pipeline as pipeline_cli

        monkeypatch.setattr(boot, "holds_history", lambda conn: False)
        ran = []
        monkeypatch.setattr(pipeline_cli, "_run_collection",
                            lambda coll, sequential: ran.append(coll.id))
        monkeypatch.setattr(dashboard_cli, "_build_data", lambda: None)
        monkeypatch.setattr(dashboard_cli, "_embed", lambda: None)
        import dashboard.snapshot_dashboard as snap
        monkeypatch.setattr(snap, "sync_local_snapshots", lambda: [])
        out = _runner.invoke(pipeline_cli.pipeline_group, ["run", "--collection", FAKE_SHORT])
        assert out.exit_code == 0, out.output
        assert ran == [FAKE_ID]

    def test_debug_runs_a_tool_for_a_third_collection(self, third_collection, monkeypatch):
        from cli import debug as debug_cli
        from qa_tools.tools import run_dbt

        asked = []
        monkeypatch.setattr(run_dbt, "evaluate", lambda cid, run_id, ts: asked.append(cid) or [])
        monkeypatch.setattr(collection_cli.of(FAKE_ID), "report_table", lambda r, i: "")
        out = _runner.invoke(debug_cli.debug_group,
                             ["run-dbt", "--collection", FAKE_SHORT, "--run-id", "fk_run_001"])
        assert out.exit_code == 0, out.output
        assert asked == [FAKE_ID]

    def test_the_short_option_refuses_naming_every_short(self, third_collection):
        from cli import debug as debug_cli

        out = _runner.invoke(debug_cli.debug_group,
                             ["run-dbt", "--collection", "zz", "--run-id", "x"])
        assert out.exit_code == 2
        assert "'bdm', 'cp', 'fk'" in out.output or "bdm, cp, fk" in out.output, out.output

    @pytest.mark.parametrize("value", [FAKE_SHORT, FAKE_ID])
    def test_supply_takes_a_third_collection_by_short_or_id(self, third_collection,
                                                           monkeypatch, value):
        from cli import filing_tui
        from cli import supply as supply_cli

        shown = []
        monkeypatch.setattr(filing_tui, "standing_view",
                            lambda cid, dataset_id: shown.append(cid))
        out = _runner.invoke(supply_cli.supply_group, ["slots", "--collection", value])
        assert out.exit_code == 0, out.output
        assert shown == [FAKE_ID]

    def test_supply_refuses_an_unknown_one_naming_the_known(self, third_collection):
        from cli import supply as supply_cli

        out = _runner.invoke(supply_cli.supply_group, ["slots", "--collection", "zz"])
        assert out.exit_code == 2
        assert FAKE_ID in out.output and "Known:" in out.output


class TestABrokenAdapter:
    """Criterion 8: refused by name, no traceback, nothing else harmed."""

    @pytest.mark.parametrize("args", [["qa", "--run-id", "bare_run_001", "--trial"],
                                      ["generate-synthetic-data", "--yes"]])
    def test_its_own_commands_refuse_naming_it(self, without_adapter, args):
        out = _runner.invoke(collection_cli.make_group(_coll(BARE_ID)), args)
        assert out.exit_code == 1, out.output
        assert f"{BARE_ID} cannot run: its adapter could not be loaded" in out.output
        assert "Traceback" not in out.output
        assert not isinstance(out.exception, Exception) or isinstance(out.exception, SystemExit)

    def test_every_other_collection_still_works(self, without_adapter):
        for cid in ("civil-registration", "child-protection", FAKE_ID):
            out = _runner.invoke(collection_cli.make_group(_coll(cid)), ["qa", "--help"])
            assert out.exit_code == 0, (cid, out.output)

    def test_the_tui_refuses_it_the_same_way(self, without_adapter, monkeypatch):
        import rich_click as click

        import cli.app as app

        monkeypatch.setattr(common, "select", lambda *a, **k: "Bare Things")
        with pytest.raises(click.ClickException, match=f"{BARE_ID} cannot run"):
            app._qa_menu()
        assert BARE_SHORT  # the short is registered; only its adapter is missing


#: What `--help` must never load (criterion 7).
HEAVY = ("pandas", "numpy", "duckdb", "soda", "dbt", "datacontract", "evidently")

_PROBE = """
import json, sys
from cli.app import cli
try:
    cli.main(sys.argv[1:], prog_name="mothman", standalone_mode=False)
except SystemExit:
    pass
heavy = {heavy!r}
print("\\n" + json.dumps(sorted({{m.split(".")[0] for m in sys.modules}} & set(heavy))))
"""


class TestHelpImportsNoTool:
    """Criterion 7, in a FRESH interpreter each time - an import made by an
    earlier test in this process would hide one made by `--help`."""

    @pytest.mark.parametrize("argv", [["--help"], ["bdm", "--help"], ["cp", "--help"],
                                      ["bdm", "qa", "--help"], ["cp", "qa", "--help"]],
                             ids=" ".join)
    def test_it_imports_none_of_the_tools(self, argv):
        done = subprocess.run([sys.executable, "-c", _PROBE.format(heavy=HEAVY), *argv],
                              cwd=ROOT, capture_output=True, text=True, timeout=120)
        assert done.returncode == 0, done.stderr
        assert "Usage:" in done.stdout, "the probe must actually have printed the help"
        assert json.loads(done.stdout.strip().splitlines()[-1]) == []
