"""A malformed contract/data-asset.yaml stops every mothman command with
one line - the file, the line, what is wrong - and never a traceback
(REQ-PIPE-122 criterion 24, Keith 2026-10-05; post-build-review #107).

It used to crash every command, `--help` included, before the validator
could say anything: the file is read while the command modules import.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Imports cli.app the way the console script does, with the asset config
# pointed at a broken copy first - every reader takes the path from these
# two module constants.
_DRIVER = """
import sys, runpy
from pathlib import Path
from qa_tools.common import asset_time, hierarchy
broken = Path(sys.argv[1])
hierarchy.DATA_ASSET_YAML = broken
asset_time.DATA_ASSET_YAML = broken
sys.argv = ["mothman", *sys.argv[2:]]
runpy.run_module("cli.app", run_name="__main__")
"""


def _broken_copy(tmp_path: Path) -> Path:
    text = (ROOT / "contract" / "data-asset.yaml").read_text()
    lines = text.split("\n")
    i = next(n for n, line in enumerate(lines) if line.startswith("timezone:"))
    lines[i] = "   " + lines[i]
    path = tmp_path / "data-asset.yaml"
    path.write_text("\n".join(lines))
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
