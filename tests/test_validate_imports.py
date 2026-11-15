"""REQ-TEST-384: the imports gate fails any import, or any load by path,
across a forbidden edge between asset_model/, the real pipeline, the
generator, scenarios/, the bootstrap and cli/, and any file in no side,
against a shrink-only allowlist whose every entry names its requirement.

These drive the real gate - `validate_imports.main` over a small repository
written to a temporary directory, the real `mothman dashboard
validate-imports` over this repository, and `mothman check --only imports` -
and assert on what each prints. None needs a database, a browser or a
deployment, so all are in push CI's critical set (REQ-TEST-375)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from qa_tools.common import syntax_walk
from qa_tools.common import validate_imports as vi

ROOT = Path(__file__).resolve().parent.parent

#: REQ-TEST-375: in the hand-picked set every push runs in CI.
#: Asset-free: the gate reads no asset; quarterly is the suite's default (C11).
pytestmark = [pytest.mark.critical, pytest.mark.asset("quarterly")]

#: One file per side, by where the gate looks for it.
HOMES = {
    "asset_model": "asset_model/reader.py",
    "pipeline": "qa_tools/common/thing.py",
    "generator": "generator/thing.py",
    "scenarios": "scenarios/register.py",
    "bootstrap": "bootstrap/replay.py",
    "cli": "cli/command.py",
}
#: What each side's file imports to reach another side.
TARGETS = {
    "asset_model": "asset_model.reader",
    "pipeline": "qa_tools.common.thing",
    "generator": "generator.thing",
    "scenarios": "scenarios.register",
    "bootstrap": "bootstrap.replay",
    "cli": "cli.command",
}

#: REQ-TEST-384 criterion 3, written out here rather than read from the gate,
#: so a slip in the gate's own table fails a test.
FORBIDDEN = {
    ("asset_model", t) for t in HOMES if t != "asset_model"} | {
    ("pipeline", "generator"), ("pipeline", "scenarios"), ("pipeline", "bootstrap"),
    ("pipeline", "cli"),
    ("scenarios", "pipeline"), ("scenarios", "generator"), ("scenarios", "bootstrap"),
    ("scenarios", "cli"),
    ("generator", "bootstrap"), ("generator", "cli"), ("generator", "pipeline"),
    ("bootstrap", "cli"),
}
ALLOWED_EDGES = sorted({(s, t) for s in HOMES for t in HOMES} - FORBIDDEN)


def _write(root: Path, rel: str, text: str = "") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    for parent in path.relative_to(root).parents:
        if str(parent) not in (".", "assets") and not str(parent).startswith("assets/"):
            (root / parent / "__init__.py").touch()
    path.write_text(text)


@pytest.fixture
def repo(tmp_path):
    """A repository with one empty module per side and an empty allowlist."""
    for rel in HOMES.values():
        _write(tmp_path, rel)
    (tmp_path / vi.ALLOWLIST).write_text("entries: []\n")
    return tmp_path


def _run(root: Path, capsys) -> tuple[int, str]:
    code = vi.main(root=root)
    return code, capsys.readouterr().out


def _allow(root: Path, *entries: dict) -> None:
    (root / vi.ALLOWLIST).write_text(yaml.safe_dump({"entries": list(entries)}))


# ---------------------------------------------------------------- the edges


@pytest.mark.parametrize("side,target", sorted(FORBIDDEN))
def test_each_forbidden_edge_fails(repo, capsys, side, target):
    _write(repo, HOMES[side], f"import {TARGETS[target]}\n")
    code, out = _run(repo, capsys)
    assert code == 1, out
    assert (f"{HOMES[side]}:1: {side} imports {target} ({TARGETS[target]}) - forbidden edge"
            in out)


@pytest.mark.parametrize("side,target", ALLOWED_EDGES)
def test_each_allowed_edge_passes(repo, capsys, side, target):
    _write(repo, HOMES[side], f"from {TARGETS[target].rsplit('.', 1)[0]} import "
                              f"{TARGETS[target].rsplit('.', 1)[1]}\n")
    code, out = _run(repo, capsys)
    assert code == 0, out
    assert "- forbidden edge" not in out


def test_an_import_inside_a_function_is_caught(repo, capsys):
    _write(repo, "generator/thing.py", "def later():\n    from cli import command\n")
    code, out = _run(repo, capsys)
    assert code == 1
    assert "generator/thing.py:2: generator imports cli (cli.command) - forbidden edge" in out


def test_an_import_under_type_checking_is_caught(repo, capsys):
    _write(repo, "qa_tools/common/thing.py",
           "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import generator.thing\n")
    code, out = _run(repo, capsys)
    assert code == 1
    assert "qa_tools/common/thing.py:3: pipeline imports generator (generator.thing)" in out


def test_import_module_with_a_literal_name_is_caught(repo, capsys):
    _write(repo, "qa_tools/common/thing.py",
           "import importlib\nimportlib.import_module('bootstrap.replay')\n")
    code, out = _run(repo, capsys)
    assert code == 1
    assert "qa_tools/common/thing.py:2: pipeline imports bootstrap (bootstrap.replay)" in out


def test_a_relative_import_is_read_against_its_own_package(repo, capsys):
    """`from .. import x` inside asset_model/ stays inside it."""
    _write(repo, "asset_model/sub/inner.py", "from .. import reader\nfrom . import other\n")
    _write(repo, "asset_model/sub/other.py")
    assert _run(repo, capsys)[0] == 0


def test_an_assets_adapter_and_provider_are_sorted_by_folder(repo, capsys):
    """A thirtieth collection needs no change: its adapter is the real
    pipeline's and its provider the generator's, by where each sits."""
    _write(repo, "assets/any/collections/thirtieth.py", "import generator.thing\n")
    _write(repo, "assets/any/synthetic/collections/thirtieth.py", "import qa_tools.common.thing\n")
    code, out = _run(repo, capsys)
    assert code == 1
    assert ("assets/any/collections/thirtieth.py:1: pipeline imports generator "
            "(generator.thing)") in out
    assert ("assets/any/synthetic/collections/thirtieth.py:1: generator imports pipeline "
            "(qa_tools.common.thing)") in out


def test_standard_and_third_party_imports_are_no_edge(repo, capsys):
    _write(repo, "asset_model/reader.py", "import os\nimport yaml\nfrom pathlib import Path\n")
    assert _run(repo, capsys)[0] == 0


# ------------------------------------------------------------- no side, exempt


def test_a_file_in_no_side_fails(repo, capsys):
    _write(repo, "newpackage/module.py", "x = 1\n")
    code, out = _run(repo, capsys)
    assert code == 1
    assert "newpackage/module.py:1: in no side" in out


@pytest.mark.parametrize("top", ["tests", "scripts", "docs"])
def test_tests_scripts_and_docs_are_not_read(repo, capsys, top):
    _write(repo, f"{top}/anything.py", "import cli.command\nimport generator.thing\n")
    assert _run(repo, capsys)[0] == 0


# ------------------------------------------------------------- loads by path


def test_a_provider_loaded_by_path_from_the_real_pipeline_fails(repo, capsys):
    _write(repo, "qa_tools/common/thing.py",
           "from qa_tools.common import assets\n\ndef f():\n"
           "    return assets.load('provider', 'x')\n")
    code, out = _run(repo, capsys)
    assert code == 1
    assert ("qa_tools/common/thing.py:4: pipeline imports generator (provider loaded by path) "
            "- forbidden edge") in out


def test_an_adapter_loaded_by_path_from_the_generator_fails(repo, capsys):
    _write(repo, "generator/thing.py",
           "from asset_model.assets import load as fetch\nfetch('adapter', 'x')\n")
    code, out = _run(repo, capsys)
    assert code == 1
    assert "generator/thing.py:2: generator imports pipeline (adapter loaded by path)" in out


def test_loads_on_their_own_sides_pass(repo, capsys):
    _write(repo, "qa_tools/common/thing.py",
           "import qa_tools.common.assets\nqa_tools.common.assets.load('adapter', 'x')\n")
    _write(repo, "generator/thing.py",
           "from asset_model import assets\nassets.load(kind='provider', module='x')\n")
    assert _run(repo, capsys)[0] == 0


def test_a_loader_kind_that_is_not_a_literal_fails_naming_the_call(repo, capsys):
    _write(repo, "generator/thing.py",
           "from qa_tools.common import assets\n\ndef f(kind):\n    return assets.load(kind, 'x')\n")
    _allow(repo, {"file": "generator/thing.py", "imports": "qa_tools.common.assets",
                  "removed_by": "REQ-PIPE-380"})
    code, out = _run(repo, capsys)
    assert code == 1
    assert ("generator/thing.py:4: generator loads by path with a kind that is not a literal "
            "(assets.load(kind, 'x'))") in out


def test_an_unrelated_load_is_not_the_loader(repo, capsys):
    _write(repo, "asset_model/reader.py", "import json\njson.load(open('x'))\n")
    assert _run(repo, capsys)[0] == 0


# ------------------------------------------------------------- the output


def test_findings_close_with_a_count_and_the_fix(repo, capsys):
    _write(repo, "generator/thing.py", "import cli.command\nimport bootstrap.replay\n")
    code, out = _run(repo, capsys)
    lines = [x for x in out.strip().splitlines() if not x.startswith("imports: note")]
    assert code == 1
    assert lines[0].startswith("generator/thing.py:1: ")
    assert lines[-1].startswith("imports: 2 problem(s).")
    assert "move the code across the boundary, not to add an entry" in lines[-1]


# ------------------------------------------------------------- the allowlist


def test_an_allowlisted_import_passes(repo, capsys):
    _write(repo, "generator/thing.py", "import cli.command\n\ndef f():\n    import cli.command\n")
    _allow(repo, {"file": "generator/thing.py", "imports": "cli.command",
                  "removed_by": "REQ-GEN-386"})
    code, out = _run(repo, capsys)
    assert code == 0, out
    assert "1 entry left to remove" in out


def test_an_entry_naming_no_requirement_fails(repo, capsys):
    _write(repo, "generator/thing.py", "import cli.command\n")
    _allow(repo, {"file": "generator/thing.py", "imports": "cli.command"})
    code, out = _run(repo, capsys)
    assert code == 1
    assert (f"{vi.ALLOWLIST}: entry generator/thing.py imports cli.command (no requirement) "
            f"names no requirement") in out


def test_an_entry_naming_a_requirement_the_register_lacks_fails(repo, capsys):
    (repo / "requirements.yaml").write_text("requirements:\n  - id: REQ-GEN-386\n")
    _write(repo, "generator/thing.py", "import cli.command\n")
    _allow(repo, {"file": "generator/thing.py", "imports": "cli.command",
                  "removed_by": "REQ-GEN-999"})
    code, out = _run(repo, capsys)
    assert code == 1
    assert "names REQ-GEN-999, which requirements.yaml does not hold" in out


def test_a_stale_entry_fails_asking_for_its_deletion(repo, capsys):
    _allow(repo, {"file": "generator/thing.py", "imports": "cli.command",
                  "removed_by": "REQ-GEN-386"})
    code, out = _run(repo, capsys)
    assert code == 1
    assert (f"{vi.ALLOWLIST}: entry generator/thing.py imports cli.command (REQ-GEN-386) "
            f"matches no import any more - delete it") in out


def _git(root: Path, *argv: str) -> str:
    return subprocess.run(["git", *argv], cwd=root, check=True, capture_output=True,
                          text=True).stdout.strip()


def _commit_all(root: Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", message)
    return _git(root, "rev-parse", "--short", "HEAD")


@pytest.fixture
def history(repo):
    """The repository under git, its base commit allowlisting one import."""
    _git(repo, "init", "-q")
    _write(repo, "generator/thing.py", "import cli.command\n")
    _allow(repo, {"file": "generator/thing.py", "imports": "cli.command",
                  "removed_by": "REQ-GEN-386"})
    return repo, _commit_all(repo, "base")


def test_an_added_entry_fails_naming_the_base_commit(history, capsys, monkeypatch):
    repo, base = history
    monkeypatch.setenv("MOTHMAN_DIFF_BASE", base)
    _write(repo, "generator/thing.py", "import cli.command\nimport bootstrap.replay\n")
    _allow(repo, {"file": "generator/thing.py", "imports": "cli.command",
                  "removed_by": "REQ-GEN-386"},
           {"file": "generator/thing.py", "imports": "bootstrap.replay",
            "removed_by": "REQ-GEN-386"})
    _commit_all(repo, "grow the list")
    code, out = _run(repo, capsys)
    assert code == 1
    assert (f"{vi.ALLOWLIST}: entry generator/thing.py imports bootstrap.replay (REQ-GEN-386) "
            f"is absent at the base commit {base} - the list only shrinks (REQ-TEST-384)") in out
    assert "imports cli.command (REQ-GEN-386) is absent" not in out


def test_a_shrunk_list_passes_against_its_base(history, capsys, monkeypatch):
    repo, base = history
    monkeypatch.setenv("MOTHMAN_DIFF_BASE", base)
    _write(repo, "generator/thing.py", "")
    _allow(repo)
    _commit_all(repo, "move the code across")
    code, out = _run(repo, capsys)
    assert code == 0, out


def test_an_unreadable_base_is_said_rather_than_passed_in_silence(history, capsys, monkeypatch):
    repo, _ = history
    monkeypatch.setenv("MOTHMAN_DIFF_BASE", "0" * 40)
    monkeypatch.setattr(vi._diff_base, "_resolves", lambda ref, root=None: False)
    code, out = _run(repo, capsys)
    assert code == 0, out
    assert "gain check skipped" in out


def test_a_missing_allowlist_fails(repo, capsys):
    (repo / vi.ALLOWLIST).unlink()
    code, out = _run(repo, capsys)
    assert code == 1
    assert f"{vi.ALLOWLIST} is missing" in out


# ------------------------------------------------------------- this repository


def test_this_repository_passes_through_the_real_command():
    """Criterion 8: the gate lands green, its allowlist holding exactly the
    tree's own findings - none new and none stale - each naming the
    requirement that removes it."""
    from cli.dashboard import dashboard_group

    result = CliRunner().invoke(dashboard_group, ["validate-imports"])
    assert result.exit_code == 0, result.output
    assert "no forbidden edge outside imports-allowlist.yaml" in result.output


def test_the_landing_allowlist_names_only_the_requirements_that_remove_its_entries():
    entries = vi.load_allowlist(ROOT)
    assert entries, "the allowlist is empty - nothing to check"
    removers = {"REQ-PIPE-380", "REQ-GEN-381", "REQ-PIPE-382", "REQ-PIPE-383", "REQ-PIPE-385",
                "REQ-GEN-386", "REQ-QAC-389", "REQ-PIPE-390"}
    assert {e.removed_by for e in entries} <= removers


def test_every_python_file_here_has_a_side_or_is_exempt():
    files = syntax_walk.python_files(ROOT, exempt=tuple(vi.EXEMPT))
    assert files, "the walker found no file - nothing to check"
    assert [f for f in files if vi.side_of_file(f.relative_to(ROOT).as_posix()) is None] == []


# ------------------------------------------------------------- where it runs


def test_mothman_check_runs_it_once_whatever_the_asset(monkeypatch):
    import cli.check as check_cli

    calls = []

    class Done:
        returncode = 0

    monkeypatch.setattr(check_cli.subprocess, "run", lambda argv, **kw: calls.append(
        (argv, (kw.get("env") or {}).get("MOTHMAN_ASSET"))) or Done())
    monkeypatch.setattr(check_cli.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.delenv("MOTHMAN_ASSET", raising=False)
    result = CliRunner().invoke(check_cli.check_command, ["--only", "imports"])
    assert result.exit_code == 0, result.output
    assert calls == [(["uv", "run", "mothman", "dashboard", "validate-imports"], None)]
    labels = [g[0] for g in check_cli._GATES]
    assert labels.index("imports") < labels.index("schedule")
    assert dict((g[0], g[2]) for g in check_cli._GATES)["imports"]


def _workflow() -> dict:
    return yaml.safe_load((ROOT / ".github/workflows/validate-config.yml").read_text())


def test_validate_config_runs_it_in_each_asset_leg():
    job = _workflow()["jobs"]["validate"]
    assert set(job["strategy"]["matrix"]["asset"]) == {"quarterly", "daily"}
    assert "uv run mothman dashboard validate-imports" in [s.get("run") for s in job["steps"]]


def test_validate_configs_paths_name_every_directory_the_gate_reads():
    """Criterion 12: a push changing only one of them still runs the gate."""
    paths = _workflow()[True]["push"]["paths"]  # PyYAML reads `on:` as True
    tops = {f.relative_to(ROOT).parts[0]
            for f in syntax_walk.python_files(ROOT, exempt=tuple(vi.EXEMPT))
            if f.relative_to(ROOT).parts[0] != f.name}
    assert tops, "the gate reads no directory - nothing to check"
    assert sorted(t for t in tops if f"{t}/**" not in paths) == []
    assert vi.ALLOWLIST in paths
