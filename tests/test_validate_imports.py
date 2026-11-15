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
    """A git repository with one empty module per side and an empty
    allowlist. The gate reads tracked files, so _run() stages everything."""
    _git(tmp_path, "init", "-q")
    for rel in HOMES.values():
        _write(tmp_path, rel)
    (tmp_path / vi.ALLOWLIST).write_text("entries: []\n")
    return tmp_path


def _run(root: Path, capsys, stage: bool = True) -> tuple[int, str]:
    if stage:
        _git(root, "add", "-A")
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
           "from asset_model import assets\n\ndef f():\n"
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
           "import asset_model.assets\nasset_model.assets.load('adapter', 'x')\n")
    _write(repo, "generator/thing.py",
           "from asset_model import assets\nassets.load(kind='provider', module='x')\n")
    assert _run(repo, capsys)[0] == 0


def test_a_loader_kind_that_is_not_a_literal_fails_naming_the_call(repo, capsys):
    _write(repo, "generator/thing.py",
           "from asset_model import assets\n\ndef f(kind):\n    return assets.load(kind, 'x')\n")
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
    """The repository's base commit, allowlisting one import."""
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
    files = syntax_walk.tracked_python_files(ROOT, exempt=tuple(vi.EXEMPT))
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
            for f in syntax_walk.tracked_python_files(ROOT, exempt=tuple(vi.EXEMPT))
            if f.relative_to(ROOT).parts[0] != f.name}
    assert tops, "the gate reads no directory - nothing to check"
    assert sorted(t for t in tops if f"{t}/**" not in paths) == []
    assert vi.ALLOWLIST in paths


# ------------------------------------------- the post-build critic's findings
# (plans/post-build-review.md, REQ-TEST-384's critic, 2026-11-15)


def test_the_pipeline_importing_a_provider_module_fails(repo, capsys):
    _write(repo, "qa_tools/common/thing.py",
           "import assets.quarterly.synthetic.collections.x\n")
    code, out = _run(repo, capsys)
    assert code == 1
    assert ("qa_tools/common/thing.py:1: pipeline imports generator "
            "(assets.quarterly.synthetic.collections.x) - forbidden edge") in out


def test_a_provider_importing_an_adapter_module_fails(repo, capsys):
    _write(repo, "assets/quarterly/synthetic/collections/p.py",
           "from assets.quarterly.collections import x\n")
    code, out = _run(repo, capsys)
    assert code == 1
    assert ("assets/quarterly/synthetic/collections/p.py:1: generator imports pipeline "
            "(assets.quarterly.collections) - forbidden edge") in out


def test_asset_model_importing_anything_under_assets_fails(repo, capsys):
    """REQ-PIPE-380 criterion 9: any file under assets/, sided or not."""
    _write(repo, "asset_model/reader.py", "import assets.quarterly.helpers\n")
    code, out = _run(repo, capsys)
    assert code == 1
    assert ("asset_model/reader.py:1: asset_model imports no side "
            "(assets.quarterly.helpers) - forbidden edge") in out


def test_import_module_by_keyword_is_caught(repo, capsys):
    _write(repo, "generator/thing.py",
           "from importlib import import_module\nimport_module(name='cli.command')\n")
    code, out = _run(repo, capsys)
    assert code == 1
    assert "generator/thing.py:2: generator imports cli (cli.command)" in out


def test_dunder_import_with_a_literal_is_caught(repo, capsys):
    _write(repo, "generator/thing.py", "__import__('cli.command')\n")
    code, out = _run(repo, capsys)
    assert code == 1
    assert "generator/thing.py:1: generator imports cli (cli.command)" in out


def test_a_file_that_cannot_be_parsed_is_a_finding_not_a_crash(repo, capsys):
    _write(repo, "generator/thing.py", "x = 1\n\ndef broken(:\n")
    code, out = _run(repo, capsys)
    assert code == 1
    assert "generator/thing.py:3: cannot be parsed" in out


def test_an_untracked_file_is_not_read(repo, capsys):
    """COMPATIBILITY: the gate reads committed files only."""
    _git(repo, "add", "-A")
    _write(repo, "generator/scratch.py", "import cli.command\n")
    code, out = _run(repo, capsys, stage=False)
    assert code == 0, out


def test_a_tracked_file_in_a_hidden_directory_is_in_no_side(repo, capsys):
    _write(repo, ".github/scripts/x.py", "x = 1\n")
    code, out = _run(repo, capsys)
    assert code == 1
    assert ".github/scripts/x.py:1: in no side" in out


@pytest.mark.parametrize("text", [
    "entries:\n- generator/thing.py\n",
    "entries: generator/thing.py\n",
    "entries: [\n",
])
def test_a_malformed_allowlist_is_a_finding_not_a_crash(repo, capsys, text):
    (repo / vi.ALLOWLIST).write_text(text)
    code, out = _run(repo, capsys)
    assert code == 1
    assert f"{vi.ALLOWLIST}:" in out
    assert "malformed" in out


def test_a_duplicate_allowlist_entry_fails(repo, capsys):
    _write(repo, "generator/thing.py", "import cli.command\n")
    entry = {"file": "generator/thing.py", "imports": "cli.command", "removed_by": "REQ-GEN-386"}
    _allow(repo, entry, entry)
    code, out = _run(repo, capsys)
    assert code == 1
    assert (f"{vi.ALLOWLIST}: entry generator/thing.py imports cli.command (REQ-GEN-386) "
            f"is listed twice") in out


# ------------------------------------------- B6: the five lists (criterion 14)

#: The packages later requirements create (REQ-PIPE-380, REQ-GEN-381,
#: REQ-GEN-386), each of which must join every list below the day it exists.
NEW_PACKAGES = ("asset_model", "scenarios", "bootstrap")


def _assigned_tuple(path: Path, name: str) -> list[str]:
    import ast

    tree = ast.parse(path.read_text())
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else (
            [node.target] if isinstance(node, ast.AnnAssign) else [])
        if any(isinstance(t, ast.Name) and t.id == name for t in targets):
            return [str(v) for v in ast.literal_eval(node.value)]
    raise AssertionError(f"{path} assigns no {name}")


def _lists(root: Path) -> dict[str, list[str]]:
    """The five lists B6 names, read from the files under `root`, each as the
    entries it holds."""
    import re
    import tomllib

    workflow = yaml.safe_load((root / ".github/workflows/validate-config.yml").read_text())
    test_yml = (root / ".github/workflows/test.yml").read_text()
    pyproject = tomllib.loads((root / "pyproject.toml").read_text())
    return {
        "validate-config.yml paths": workflow[True]["push"]["paths"],
        "validate_caches.SCANNED": _assigned_tuple(
            root / "qa_tools/common/validate_caches.py", "SCANNED"),
        "validate_collections.SCANNED": _assigned_tuple(
            root / "qa_tools/common/validate_collections.py", "SCANNED"),
        "pyproject.toml coverage source": pyproject["tool"]["coverage"]["run"]["source"],
        "cli/check.py COVERAGE_PACKAGES": _assigned_tuple(
            root / "cli/check.py", "COVERAGE_PACKAGES"),
        "test.yml --cov": re.findall(r"--cov=([\w.]+)", test_yml),
        "replay_inputs.INPUTS": _assigned_tuple(
            root / "qa_tools/common/replay_inputs.py", "INPUTS"),
    }


def _named(package: str, entries: list[str]) -> bool:
    return any(e in (package, f"{package}/**", f"{package}/") for e in entries)


def unlisted(root: Path) -> list[str]:
    """'<package> is not in <list>' for each of NEW_PACKAGES that exists under
    `root` and is missing from one of the lists."""
    lists = _lists(root)
    return [f"{p} is not in {name}" for p in NEW_PACKAGES if (root / p).is_dir()
            for name, entries in lists.items() if not _named(p, entries)]


def test_each_new_package_once_it_exists_is_named_in_every_list():
    """B6, narrowed by Keith 2026-11-15: asset_model/, scenarios/ and
    bootstrap/, once each exists, are named in validate-config.yml's paths,
    both SCANNED tuples, the coverage sources and replay_inputs.INPUTS.

    asset_model/ exists since REQ-PIPE-380 and is in every list; scenarios/ and
    bootstrap/ join with the requirements that create them (REQ-GEN-381,
    REQ-GEN-386). That it can fail is shown on a fixture repository below."""
    lists = _lists(ROOT)
    assert all(lists.values()), f"a list read empty - nothing to check: {lists}"
    assert unlisted(ROOT) == []


def _copy_lists(dest: Path) -> None:
    import shutil

    for rel in (".github/workflows/validate-config.yml", ".github/workflows/test.yml",
                "pyproject.toml", "qa_tools/common/validate_caches.py",
                "qa_tools/common/validate_collections.py", "cli/check.py",
                "qa_tools/common/replay_inputs.py"):
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, dest / rel)


def test_a_new_package_left_out_of_a_list_fails(tmp_path):
    _copy_lists(tmp_path)
    (tmp_path / "scenarios").mkdir()
    missing = unlisted(tmp_path)
    assert "scenarios is not in validate_caches.SCANNED" in missing
    assert "scenarios is not in replay_inputs.INPUTS" in missing
    assert not any(m.startswith(("asset_model", "bootstrap")) for m in missing)


def test_a_new_package_named_in_every_list_passes(tmp_path):
    _copy_lists(tmp_path)
    (tmp_path / "bootstrap").mkdir()
    for rel, old, new in (
        (".github/workflows/validate-config.yml", '- "qa_tools/**"',
         '- "qa_tools/**"\n      - "bootstrap/**"'),
        ("qa_tools/common/validate_caches.py", 'SCANNED = ("asset_model", "qa_tools",',
         'SCANNED = ("asset_model", "bootstrap", "qa_tools",'),
        ("qa_tools/common/validate_collections.py", 'SCANNED = ("asset_model", "qa_tools",',
         'SCANNED = ("asset_model", "bootstrap", "qa_tools",'),
        ("pyproject.toml", 'source = ["asset_model", "qa_tools",',
         'source = ["asset_model", "bootstrap", "qa_tools",'),
        ("cli/check.py", 'COVERAGE_PACKAGES = ("asset_model", "qa_tools",',
         'COVERAGE_PACKAGES = ("asset_model", "bootstrap", "qa_tools",'),
        (".github/workflows/test.yml", "--cov=qa_tools", "--cov=bootstrap --cov=qa_tools"),
        ("qa_tools/common/replay_inputs.py", 'INPUTS = ("asset_model/**", "generator/**",',
         'INPUTS = ("asset_model/**", "bootstrap/**", "generator/**",'),
    ):
        path = tmp_path / rel
        text = path.read_text()
        assert old in text, (rel, old)
        path.write_text(text.replace(old, new))
    assert unlisted(tmp_path) == []


def test_asset_model_is_named_in_every_list_now_it_exists():
    """REQ-PIPE-380 criterion 17: asset_model/ landed, so it is in every
    list - shown against this repository, not a fixture."""
    assert (ROOT / "asset_model").is_dir()
    lists = _lists(ROOT)
    assert [name for name, entries in lists.items() if not _named("asset_model", entries)] == []


# --------------------- REQ-PIPE-376 criterion 8: no underscore asset_model name


@pytest.mark.parametrize("text", [
    "from asset_model.reader import _hidden\n",
    "from asset_model import reader\nreader._hidden()\n",
    "from asset_model import reader as r\n\ndef f():\n    return r._hidden\n",
    "import asset_model.reader\nasset_model.reader._hidden()\n",
    "from asset_model import reader\ngetattr(reader, '_hidden')\n",
])
def test_an_underscore_asset_model_name_read_outside_it_fails(repo, capsys, text):
    _write(repo, HOMES["pipeline"], text)
    code, out = _run(repo, capsys)
    assert code == 1, out
    assert "qa_tools/common/thing.py:" in out and "asset_model.reader._hidden" in out, out
    assert "REQ-PIPE-376" in out, out


def test_an_underscore_name_inside_asset_model_and_a_public_one_outside_pass(repo, capsys):
    _write(repo, "asset_model/other.py", "from asset_model import reader\nreader._hidden()\n")
    _write(repo, HOMES["generator"], "from asset_model import reader\nreader.shown()\n"
                                     "reader.__name__\n")
    code, out = _run(repo, capsys)
    assert code == 0, out


def test_an_underscore_name_is_not_excused_by_the_allowlist(repo, capsys):
    _write(repo, HOMES["pipeline"], "from asset_model.reader import _hidden\n")
    _allow(repo, {"file": HOMES["pipeline"], "imports": "asset_model.reader._hidden",
                  "removed_by": "REQ-PIPE-376"})
    code, out = _run(repo, capsys)
    assert code == 1 and "underscore-led" in out, out


# --------------------- REQ-PIPE-390 criterion 5: no status ranking of its own


@pytest.mark.parametrize("side", ["pipeline", "generator", "cli"])
def test_a_status_ranking_outside_asset_model_fails(repo, capsys, side):
    _write(repo, HOMES[side], '_RANK = {"green": 0, "amber": 1, "red": 2}\n')
    code, out = _run(repo, capsys)
    assert code == 1, out
    assert f"{HOMES[side]}:1:" in out and "ranking of the status words" in out, out
    assert "REQ-PIPE-390" in out, out


def test_a_ranking_with_nodata_below_zero_fails_too(repo, capsys):
    _write(repo, HOMES["bootstrap"], 'ORDER = {"nodata": -1, "green": 0}\n')
    code, out = _run(repo, capsys)
    assert code == 1 and "ranking of the status words" in out, out


@pytest.mark.parametrize("text, how", [
    ('def rank(s):\n    return ("green", "amber", "red").index(s)\n', ".index()"),
    ('ORDER = ["nodata", "green", "amber", "red"]\n\ndef rank(s):\n    return ORDER.index(s)\n',
     ".index()"),
    ('RANK = {s: i for i, s in enumerate(("green", "amber", "red"))}\n', "enumerate()"),
    ('ORDER = ("green", "amber", "red")\nRANK = dict((s, i) for i, s in enumerate(ORDER))\n',
     "enumerate()"),
    ('RANKED = [(i, s) for i, s in enumerate(["green", "red"])]\n', "enumerate()"),
])
def test_a_ranking_by_index_or_enumerate_outside_asset_model_fails(repo, capsys, text, how):
    _write(repo, HOMES["pipeline"], text)
    code, out = _run(repo, capsys)
    assert code == 1, out
    assert "ranking of the status words" in out and how in out and "REQ-PIPE-390" in out, out


def test_a_sequence_of_the_words_only_tested_for_membership_passes(repo, capsys):
    _write(repo, HOMES["generator"], 'VERDICTS = ("green", "amber", "red")\n\n'
                                     'def ok(v):\n    return v in VERDICTS\n'
                                     'NAMES = ["x", "y"]\nN = NAMES.index("x")\n')
    _write(repo, HOMES["asset_model"],
           'ORDER = ("green", "amber", "red")\nR = {s: i for i, s in enumerate(ORDER)}\n')
    code, out = _run(repo, capsys)
    assert code == 0, out


def test_asset_models_ranking_and_words_that_rank_nothing_pass(repo, capsys):
    _write(repo, HOMES["asset_model"],
           'ORDER = {"nodata": -1, "green": 0, "amber": 1, "red": 2}\n')
    _write(repo, HOMES["pipeline"], 'WORDS = {"green": "Pass", "amber": "Warn", "red": "Fail"}\n'
                                    'ONE = {"green": 0}\n')
    code, out = _run(repo, capsys)
    assert code == 0, out


def test_the_two_rules_find_nothing_in_this_repository():
    """Both rules over the real tree: every former ranking copy reads
    asset_model.statuses, and no underscore-led asset_model name is used
    outside it. Asserts the tree was read, so an empty scan cannot pass."""
    findings, problems = vi.scan(ROOT)
    assert findings, "the scan read nothing - the allowlist's findings are missing"
    said = [str(p) for p in problems if "REQ-PIPE-376" in str(p) or "REQ-PIPE-390" in str(p)]
    assert said == []
