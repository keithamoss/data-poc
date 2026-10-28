"""The guard against an unreviewed process-long cache (REQ-PIPE-254
criteria 16 to 18): `mothman check`'s `caches` gate."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from cli import check as check_cli
from qa_tools.common import validate_caches

ROOT = Path(__file__).resolve().parent.parent


def _gate(root: Path) -> subprocess.CompletedProcess:
    """The gate as `mothman check` runs it, against `root`."""
    return subprocess.run([sys.executable, "-m", "qa_tools.common.validate_caches",
                           "--root", str(root)], cwd=ROOT, capture_output=True, text=True)


@pytest.fixture
def tree(tmp_path) -> Path:
    """A tree with the committed allowlisted caches in it, so only what a
    test plants is off the list."""
    for rel, _ in validate_caches.ALLOWLIST:
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text((ROOT / rel).read_text())
    (tmp_path / "pipeline").mkdir(exist_ok=True)
    return tmp_path


PLANTED = {
    "an lru_cache through the module": "import functools\n\n@functools.lru_cache(maxsize=1)\ndef planted():\n    return 1\n",
    "a cache through the module": "import functools\n\n@functools.cache\ndef planted():\n    return 1\n",
    "a bare cache from functools": "from functools import cache\n\n@cache\ndef planted():\n    return 1\n",
    "an aliased module": "import functools as ft\n\n@ft.lru_cache()\ndef planted():\n    return 1\n",
    "an aliased name": "from functools import lru_cache as memo\n\n@memo\ndef planted():\n    return 1\n",
    "a wrap by assignment": "import functools\n\ndef _g():\n    return 1\n\nplanted = functools.cache(_g)\n",
}


class TestItFailsOnAPlantedCache:

    @pytest.mark.parametrize("source", PLANTED.values(), ids=PLANTED.keys())
    @pytest.mark.parametrize("where", ["qa_tools/common/planted.py", "pipeline/planted.py"])
    def test_it_fails_naming_the_function_and_its_file(self, tree, where, source):
        (tree / where).write_text(source)
        done = _gate(tree)
        assert done.returncode == 1, done.stdout + done.stderr
        assert where in done.stdout and "planted()" in done.stdout

    def test_cached_property_is_not_a_cache_it_fails(self, tree):
        (tree / "qa_tools/common/planted.py").write_text(
            "from functools import cached_property\n\nclass A:\n"
            "    @cached_property\n    def planted(self):\n        return 1\n")
        assert _gate(tree).returncode == 0

    def test_an_allowlist_entry_that_excuses_nothing_fails(self, tree):
        rel, _ = next(iter(validate_caches.ALLOWLIST))
        (tree / rel).write_text("def nothing():\n    return 1\n")
        done = _gate(tree)
        assert done.returncode == 1 and "excuses" in done.stdout and rel in done.stdout


class TestItPassesOnTheCommittedTree:

    def test_the_scan_is_not_empty_and_every_cache_is_allowlisted(self):
        found = validate_caches.scan(ROOT)
        assert found, "the committed tree holds allowlisted caches, so the scan saw something"
        assert {(rel, name) for rel, name, _ in found} == set(validate_caches.ALLOWLIST)
        done = _gate(ROOT)
        assert done.returncode == 0, done.stdout

    def test_none_of_the_nine_is_on_the_allowlist(self):
        nine = {"_load", "compiled_patterns", "timezone_versions", "current", "_load_once",
                "_check_ids", "_authored_names", "_contract_at"}
        assert not {name for _, name in validate_caches.ALLOWLIST} & nine

    def test_mothman_check_runs_it(self):
        [argv] = [argv for label, argv, *_ in check_cli._GATES if label == "caches"]
        assert argv[-1] == "qa_tools.common.validate_caches"
