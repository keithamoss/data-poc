"""REQ-TEST-252: the CLI and TUI at about thirty collections.

Everything here runs in a COPY of the tracked tree with twenty-eight more
collections registered (tests/thirty_collections.py) - no database, no
bootstrap, nothing written to the repository's own contract/, data/ or
reports/ (criterion 15). Help and the menus read configuration only.

Today's two collections keep their exact text, which the equivalence
capture's S7 surface proves; the tests at the bottom hold the threshold
itself.
"""
from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

import thirty_collections
from cli import common

ROOT = Path(__file__).resolve().parent.parent
#: Who decides in the filing menu: a person of the COPY's own people.yaml,
#: named to git through the environment, so no real identity is borrowed.
DECIDER = "thirty-collections@example.com"
HEAVY = ("pandas", "numpy", "duckdb", "soda", "dbt", "datacontract", "evidently")


@pytest.fixture(scope="module")
def thirty(tmp_path_factory) -> Path:
    tree = thirty_collections.build(tmp_path_factory.mktemp("thirty") / "tree")
    assert (tree / "contract" / "data-asset.yaml").is_file()
    people = tree / "contract" / "people.yaml"
    doc = yaml.safe_load(people.read_text())
    doc["people"].append({"email": DECIDER, "name": "Thirty Collections", "github": "thirty-collections"})
    people.write_text(yaml.safe_dump(doc, sort_keys=False))
    return tree


def _run(tree: Path, *argv: str, columns: int = 120) -> subprocess.CompletedProcess:
    env = {**os.environ, "NO_COLOR": "1", "COLUMNS": str(columns), "TERM": "dumb"}
    return subprocess.run([sys.executable, "-m", "cli.app", *argv], cwd=tree, env=env,
                          capture_output=True, text=True, timeout=120)


def _flat(text: str) -> str:
    """One line of words, rich's box characters removed - a sentence the
    error box wraps over a border reads whole again."""
    return " ".join(re.sub(r"[│╭╮╰╯─]", " ", text).split())


def _panel(text: str, title: str) -> list[str]:
    """The lines inside one rich-click panel, box characters stripped."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if f"─ {title} " in line)
    out = []
    for line in lines[start + 1:]:
        if line.startswith("╰"):
            break
        out.append(line.strip("│ ").rstrip())
    return out


class TestTheFixture:
    def test_it_registers_thirty_collections_across_at_least_five_agencies(self, thirty):
        out = _run(thirty, "collections")
        assert out.returncode == 0, out.stderr
        rows = [r for r in out.stdout.splitlines() if r.strip()]
        from qa_tools import collections

        # Every real collection plus the twenty-eight added - thirty when
        # there were two real ones, one more for each collection since.
        assert len(rows) == len(collections.all_collections()) + len(thirty_collections.added())
        assert len(rows) >= 30
        assert len({c["agency_id"] for c in thirty_collections.added()}) >= 5

    def test_it_writes_nothing_to_the_repository(self, thirty):
        real = (ROOT / "contract" / "data-asset.yaml").read_text()
        added = thirty_collections.added()
        assert added and not [c["id"] for c in added if c["id"] in real]
        for c in thirty_collections.added():
            assert not (ROOT / "qa_tools" / "collections" /
                        f"{c['id'].replace('-', '_')}.py").exists()


class TestHelpAtThirty:
    """Criteria 2, 3, 16 and 17."""

    @pytest.mark.parametrize("columns", [80, 120])
    def test_every_collection_in_its_panel_and_every_tool_in_the_other(self, thirty, columns):
        out = _run(thirty, "--help", columns=columns)
        assert out.returncode == 0, out.stderr
        collections_panel = _panel(out.stdout, "Collections")
        tools_panel = _panel(out.stdout, "Tools")
        shorts = [row.split()[0] for row in collections_panel if row and not row.startswith(" ")]
        from qa_tools import collections

        expected = ([c.short for c in collections.all_collections()]
                    + [c["short"] for c in thirty_collections.added()])
        assert [s for s in shorts if s in expected] == expected, "in hierarchy order"
        assert not set(expected) & {row.split()[0] for row in tools_panel if row}
        joined = " ".join(" ".join(collections_panel).split())
        for c in thirty_collections.added():
            # Each line names its label and its agency, and wraps between
            # words only - a word split across lines would not be found whole.
            assert c["name"] in joined, (columns, c["name"])
            assert c["agency_name"] in joined, (columns, c["agency_name"])
        assert "collections" in {row.split()[0] for row in tools_panel if row}

    @pytest.mark.parametrize("argv", [["--help"], ["edp", "--help"], ["edw", "qa", "--help"],
                                      ["bdm", "qa", "--help"]], ids=" ".join)
    def test_help_imports_no_tool(self, thirty, argv):
        probe = ("import json, sys\nfrom cli.app import cli\n"
                 "try:\n    cli.main(sys.argv[1:], prog_name='mothman', standalone_mode=False)\n"
                 "except SystemExit:\n    pass\n"
                 f"print('\\n' + json.dumps(sorted({{m.split('.')[0] for m in sys.modules}} & set({HEAVY!r}))))\n")
        done = subprocess.run([sys.executable, "-c", probe, *argv], cwd=thirty,
                              capture_output=True, text=True, timeout=120,
                              env={**os.environ, "NO_COLOR": "1"})
        assert done.returncode == 0, done.stderr
        assert "Usage:" in done.stdout
        assert done.stdout.strip().splitlines()[-1] == "[]"


class TestTheCollectionOptionAtThirty:
    """Criteria 9, 11, 13 and 19."""

    @pytest.mark.parametrize("argv", [["pipeline", "run"], ["debug", "run-dbt"], ["supply", "load"]],
                             ids=" ".join)
    def test_help_points_at_the_list_rather_than_listing_it(self, thirty, argv):
        out = _run(thirty, *argv, "--help")
        assert out.returncode == 0, out.stderr
        flat = " ".join(out.stdout.split())
        assert "COLLECTION" in flat and "mothman collections" in flat
        assert "edp = " not in flat and "civil-registration" not in flat

    @pytest.mark.parametrize("argv", [["pipeline", "run"], ["debug", "run-dbt", "--run-id", "x"],
                                      ["supply", "load"]], ids=" ".join)
    def test_an_unknown_one_is_refused_with_the_closest_and_where_to_look(self, thirty, argv):
        out = _run(thirty, *argv, "--collection", "emergncy-department-presentatons")
        assert out.returncode == 2
        flat = _flat(out.stderr) + " " + _flat(out.stdout)
        assert "emergency-department-presentations" in flat
        assert "mothman collections" in flat
        assert "Known:" not in flat, "every collection is never listed above N_LIST"

    def test_a_short_and_an_id_mean_the_same_collection(self, thirty):
        """Through the option type every --collection uses, not --help, which
        returns before any value is converted (the REQ-TEST-252 critic's T1)."""
        probe = ("import sys\nfrom cli import common\n"
                 "for to in ('short', 'id'):\n"
                 "    print(to, *(common.CollectionParam(to=to).convert(v, None, None) "
                 "for v in sys.argv[1:]))\n")
        done = subprocess.run([sys.executable, "-c", probe, "edp", "emergency-department-presentations"],
                              cwd=thirty, capture_output=True, text=True, timeout=120)
        assert done.returncode == 0, done.stderr
        assert done.stdout.split("\n")[:2] == [
            "short edp edp", "id emergency-department-presentations emergency-department-presentations"]


class TestTheThresholdAtTwo:
    """Criteria 4, 10 and 13 at today's two collections."""

    def test_two_is_not_many(self):
        assert common.N_LIST == 9 and not common.many_collections()

    def test_the_refusal_still_lists_every_collection(self):
        said = common.unknown_collection_message("bmd")
        assert "Closest: bdm" in said and "Known: bdm (civil-registration), cp (child-protection)" in said
        assert "mothman collections" in said

    def test_the_grouped_picker_is_todays_select_at_two(self, monkeypatch):
        asked = {}
        monkeypatch.setattr(common, "select", lambda message, choices, flag_hint: asked.update(
            message=message, choices=choices) or choices[0])
        got = common.grouped_select("Which dataset?", [("Registry Services", ["Birth Registrations"]),
                                                       ("Child Protection", ["Child Protection"])],
                                    "hint", many=False)
        assert got == "Birth Registrations"
        assert asked == {"message": "Which dataset?",
                         "choices": ["Birth Registrations", "Child Protection"]}


def _tui_drive():
    spec = importlib.util.spec_from_file_location("tui_drive", ROOT / "scripts" / "dev" / "tui_drive.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestTheMenusAtThirty:
    """Criteria 5, 7, 8 and 18, driven in a real terminal with
    scripts/dev/tui_drive.py, keyboard only."""

    def _session(self, thirty):
        drive = _tui_drive()
        script = ("import os, sys\nos.chdir(sys.argv[1]); sys.path.insert(0, sys.argv[1])\n"
                  "from cli import app\napp.cli.main([], prog_name='mothman', standalone_mode=False)\n")
        session = drive.TuiSession([sys.executable, "-c", script, str(thirty)], 110, 40)
        assert session.wait_for("What would you like to do?", 30), session.screen_lines()
        return session

    def _screen(self, session) -> str:
        session.drain(time.time() + 0.8)
        return "\n".join(line.rstrip() for line in session.screen_lines())

    def test_the_quality_assurance_menu_groups_filters_and_dispatches(self, thirty):
        session = self._session(thirty)
        try:
            session.send("enter")  # Quality Assurance
            assert session.wait_for("Which dataset?", 15)
            shown = self._screen(session)
            assert "Department of Health - Hospitals" in shown and "type to filter" in shown
            for ch in "waiting":
                session.send(ch)
            shown = self._screen(session)
            assert "Emergency Department Waiting Times" in shown
            assert "Hospital Admissions" not in shown
            for ch in "zzz":
                session.send(ch)
            session.send("enter")
            shown = self._screen(session)
            assert "Nothing matches" in shown and "Which dataset?" in shown, shown
            for _ in range(3):
                session.send("backspace")
            session.send("enter")
            shown = self._screen(session)
            # ITS OWN NEXT PROMPT, not the picker's echo (the critic's T2): the
            # N-table collection asks whether it is a full delivery.
            assert re.search(r"Which dataset\? Emergency Department Waiting Times", shown), shown
            assert session.wait_for("Full delivery or single table?", 15), session.screen_lines()
        finally:
            session.close()

    def test_the_generate_menu_groups_and_filters_too(self, thirty):
        session = self._session(thirty)
        try:
            for _ in range(4):
                session.send("down")
            session.send("enter")  # Generate synthetic data
            assert session.wait_for("Which dataset?", 15)
            shown = self._screen(session)
            assert "Department of Education" in shown
            for ch in "enrol":
                session.send(ch)
            shown = self._screen(session)
            assert "School Enrolments" in shown and "School Attendance" not in shown
            session.send("enter")
            shown = self._screen(session)
            assert re.search(r"Which dataset\? School Enrolments", shown), shown
            # THE COLLECTION'S OWN GENERATION RAN, in the copy: its provider
            # plans no slots, so it writes nothing and says so.
            assert session.wait_for("Wrote 0 deliveries", 30), session.screen_lines()
        finally:
            session.close()

    def test_the_filing_menu_groups_filters_and_reaches_its_collection(self, thirty, monkeypatch):
        for key, value in {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "user.email",
                           "GIT_CONFIG_VALUE_0": DECIDER}.items():
            monkeypatch.setenv(key, value)
        # A person decides here: on a runner GITHUB_ACTIONS would name the
        # workflow ahead of that git identity (post-build-review #240).
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        session = self._session(thirty)
        try:
            session.send("down")
            session.send("enter")  # Filing decisions
            assert session.wait_for("Which collection", 30), session.screen_lines()
            shown = self._screen(session)
            assert "Department of Justice" in shown and "type to filter" in shown
            for ch in "finalis":
                session.send(ch)
            shown = self._screen(session)
            assert "Court Finalisations" in shown and "Court Lodgements" not in shown
            session.send("enter")
            assert session.wait_for("Court Finalisations - what are you doing?", 15), \
                session.screen_lines()
        finally:
            session.close()



class TestTheFilingMenuAtTwo:
    """Keith, 2026-10-18: the filing menu labels a collection as the QA menu
    does and lists it in hierarchy order at every size - it showed Child
    Protection before 'Civil Registration' until then."""

    def test_it_offers_the_qa_menus_labels_in_hierarchy_order(self, monkeypatch):
        from cli import filing_tui

        asked = {}
        monkeypatch.setattr(filing_tui, "actor_at_the_keyboard", lambda: {"email": "t@example.com"})
        monkeypatch.setattr(filing_tui, "_pending_corrections", lambda: [])
        monkeypatch.setattr(filing_tui, "_parked_moves", lambda: [])
        monkeypatch.setattr(common, "grouped_select",
                            lambda message, groups, flag_hint, **kw: asked.update(groups=groups) or None)
        filing_tui.filing_menu()
        from qa_tools import collections

        # At N_LIST or fewer, one ungrouped list: every collection the menu
        # offers, by its QA-menu label, in hierarchy order.
        filed = set(filing_tui._collections())
        expected = [c.label for c in collections.all_collections() if c.id in filed]
        assert expected[:2] == ["Birth Registrations", "Child Protection"]
        assert asked["groups"] == [("", expected)]
