"""A malformed contract/data-asset.yaml stops every mothman command with
one line - the file, the line, what is wrong - and never a traceback
(REQ-PIPE-122 criterion 24, Keith 2026-10-05; post-build-review #107).

It used to crash every command, `--help` included, before the validator
could say anything: the file is read while the command modules import.
"""
from __future__ import annotations

import pytest

import asset_folders

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Imports cli.app the way the console script does, with the asset resolver
# pointed first at a folder holding a broken copy - every reader takes its
# path from the resolver (REQ-PIPE-342 criterion 6).
_DRIVER = """
import sys, runpy
from pathlib import Path
from qa_tools.common import assets
broken = Path(sys.argv[1])
assets.use_folder(broken.parent)
sys.argv = ["mothman", *sys.argv[2:]]
runpy.run_module("cli.app", run_name="__main__")
"""


def _broken_copy(tmp_path: Path) -> Path:
    text = (asset_folders.real_folder() / "data-asset.yaml").read_text()
    lines = text.split("\n")
    i = next(n for n, line in enumerate(lines) if line.startswith("timezone:"))
    lines[i] = "   " + lines[i]
    path = tmp_path / "data-asset.yaml"
    path.write_text("\n".join(lines))
    asset_folders.complete(tmp_path)
    return path, i + 1


def _run(broken: Path, *args: str):
    return subprocess.run([sys.executable, "-c", _DRIVER, str(broken), *args],
                          cwd=ROOT, capture_output=True, text=True, timeout=120)


def test_a_slip_is_one_line_naming_the_file_and_line(tmp_path):
    broken, line = _broken_copy(tmp_path)
    result = _run(broken, "--help")
    assert result.returncode != 0
    out = (result.stdout + result.stderr).strip()
    assert "Traceback" not in out, out
    assert "data-asset.yaml" in out and f"line {line}" in out, out
    assert len(out.splitlines()) == 1, out


#: The data asset this module's tests act for, unless a test says otherwise
#: (C11, Keith 2026-11-02: every test module names its asset).
pytestmark = pytest.mark.asset("quarterly")
