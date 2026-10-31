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
    (tmp_path / "generator").mkdir(exist_ok=True)
    return tmp_path


PLANTED = {
    "an lru_cache through the module": "import functools\n\n@functools.lru_cache(maxsize=1)\ndef planted():\n    return 1\n",
    "a cache through the module": "import functools\n\n@functools.cache\ndef planted():\n    return 1\n",
    "a bare cache from functools": "from functools import cache\n\n@cache\ndef planted():\n    return 1\n",
    "an aliased module": "import functools as ft\n\n@ft.lru_cache()\ndef planted():\n    return 1\n",
    "an aliased name": "from functools import lru_cache as memo\n\n@memo\ndef planted():\n    return 1\n",
    "a wrap by assignment": "import functools\n\ndef _g():\n    return 1\n\nplanted = functools.cache(_g)\n",
    # post-build-review #282 (L5 critic, 1): four spellings the first gate
    # read past.
    "a star import": "from functools import *\n\n@cache\ndef planted():\n    return 1\n",
    "an alias by assignment": "import functools\n\nmemo = functools.lru_cache\n\n@memo\ndef planted():\n    return 1\n",
    "an annotated wrap": "import functools\nfrom typing import Callable\n\ndef _g():\n    return 1\n\nplanted: Callable = functools.cache(_g)\n",
    "a wrap onto an attribute": "import functools\n\nclass A:\n    pass\n\ndef _g():\n    return 1\n\nA.planted = functools.lru_cache(maxsize=2)(_g)\n",
}


class TestItFailsOnAPlantedCache:

    @pytest.mark.parametrize("source", PLANTED.values(), ids=PLANTED.keys())
    @pytest.mark.parametrize("where", ["qa_tools/common/planted.py", "pipeline/planted.py",
                                       "generator/planted.py"])
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


#: post-build-review #282 (7), Keith 2026-10-29, option (a): a value BUILT
#: FROM CONFIGURATION AT IMPORT is held for the process as surely as a cache -
#: ticket_sync.DATASET_SCOPE was the hierarchy as it stood when the module was
#: first imported.
IMPORT_TIME = {
    "a comprehension over the hierarchy": "from qa_tools.common import hierarchy\n\n"
        "SCOPE = {d.dataset_id: d.agency_id for d in hierarchy.all_datasets()}\n",
    "a plain call into the registry": "from qa_tools import collections\n\n"
        "PLANTED = collections.all_collections()\n",
    "an annotated read of the calendar": "from qa_tools.common import agreement\n\n"
        "PLANTED: object = agreement.current()\n",
}


class TestItFailsOnAValueBuiltFromConfigurationAtImport:

    @pytest.mark.parametrize("source", IMPORT_TIME.values(), ids=IMPORT_TIME.keys())
    @pytest.mark.parametrize("where", ["qa_tools/common/planted.py", "generator/planted.py"])
    def test_it_fails_naming_the_line_and_its_file(self, tree, where, source):
        (tree / where).write_text(source)
        done = _gate(tree)
        assert done.returncode == 1, done.stdout + done.stderr
        assert f"{where}:3" in done.stdout and "at import" in done.stdout, done.stdout

    def test_a_read_inside_a_function_is_not_one(self, tree):
        (tree / "qa_tools/common/planted.py").write_text(
            "from qa_tools.common import hierarchy\n\n"
            "def scope():\n    return {d.dataset_id for d in hierarchy.all_datasets()}\n"
            "PLANTED = lambda: hierarchy.all_datasets()\n"
            "if __name__ == \"__main__\":\n    print(hierarchy.all_datasets())\n")
        done = _gate(tree)
        assert done.returncode == 0, done.stdout

    def test_a_content_keyed_store_is_not_one(self, tree):
        (tree / "qa_tools/common/planted.py").write_text(
            "from qa_tools.common import config_yaml\n\n_BUILT = config_yaml.Built()\n")
        assert _gate(tree).returncode == 0


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


class TestTheValuesTheWideningFoundFollowTheirFile:
    """post-build-review #282 (7), Keith 2026-10-29, option (a): the three
    values the widened gate found held configuration for the process. Each
    now answers for its file as it stands when asked."""

    def test_emergency_departments_run_plan_follows_the_calendar(self, monkeypatch):
        from generator.collections import emergency_department as ed

        monkeypatch.setattr(ed, "generated_periods", lambda: list(range(12)))
        first = len(ed.run_plan())
        monkeypatch.setattr(ed, "generated_periods", lambda: list(range(20)))
        assert (first, len(ed.run_plan())) == (12, 20)

    def test_ticket_syncs_dataset_scope_follows_the_hierarchy(self, monkeypatch):
        from types import SimpleNamespace

        from qa_tools.common import hierarchy, ticket_sync

        assert ticket_sync.DATASET_SCOPE, "precondition - the real hierarchy has datasets"
        planted = [SimpleNamespace(dataset_id="planted-ds", agency_id="planted-agency",
                                   collection_id="planted-collection")]
        monkeypatch.setattr(hierarchy, "all_datasets", lambda: planted)
        assert ticket_sync.DATASET_SCOPE == {"planted-ds": ("planted-agency",
                                                             "planted-collection")}
        assert ticket_sync.DATASET_AGENCY == {"planted-ds": "planted-agency"}

    def test_child_protections_tables_follow_the_hierarchy(self, monkeypatch):
        from types import SimpleNamespace

        from generator.collections import child_protection as cp
        from qa_tools.common import hierarchy

        assert "cp_clients" in cp.TABLES, "precondition - the real hierarchy's tables"
        monkeypatch.setattr(hierarchy, "datasets_in_collection",
                            lambda collection_id: [SimpleNamespace(table="planted_table")])
        assert cp.TABLES == ["planted_table"]
