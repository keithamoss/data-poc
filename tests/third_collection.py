"""A third collection, for REQ-PIPE-240 criterion 6's one test per site.

ONE SMALL FIXTURE SHARED ACROSS SITES (the requirement's TEST COST NFR):
a copy of contract/data-asset.yaml with one more agency and collection,
and an adapter whose code only records what it was asked to do. Nothing
here bootstraps anything. `without_adapter` adds a fourth collection that
declares no adapter at all, for the refusal half of the criterion.
"""
from __future__ import annotations

import shutil
import sys
import types

import pytest
import yaml

from qa_tools import collections
from qa_tools.collections.base import CollectionAdapter
from qa_tools.common import hierarchy

FAKE_ID, FAKE_SHORT, FAKE_PREFIX = "fake-collection", "fk", "fk_run_"
FAKE_DATASET, FAKE_TABLE = "fake-things", "fake_things"
BARE_ID, BARE_SHORT = "bare-collection", "bare"

#: The module the fake adapter's pointers name; every call is recorded.
CODE = "tests_third_collection_code"


def _hierarchy(tmp_path, *, bare: bool) -> None:
    doc = yaml.safe_load(hierarchy.DATA_ASSET_YAML.read_text())
    contract = "child-protection-contract.yaml"
    shutil.copy(hierarchy.DATA_ASSET_YAML.parent / contract, tmp_path / contract)
    for c in collections.all_collections():
        if not (tmp_path / c.contract).exists():
            shutil.copy(hierarchy.DATA_ASSET_YAML.parent / c.contract, tmp_path / c.contract)
    agencies = doc["hierarchy"]["agencies"]
    agencies.append({"id": "fake-agency", "name": "Fake Agency", "collections": [{
        "id": FAKE_ID, "name": "Fake Collection", "short": FAKE_SHORT,
        "run_prefix": FAKE_PREFIX, "contract": contract, "delivery_boundary": "directory",
        "datasets": [{"id": FAKE_DATASET, "name": "Fake Things", "table": FAKE_TABLE,
                      "arrival_pattern": r"fake_things[^/]*\.csv"}]}]})
    if bare:
        agencies[-1]["collections"].append({
            "id": BARE_ID, "name": "Bare Collection", "short": BARE_SHORT,
            "run_prefix": "bare_run_", "contract": contract, "delivery_boundary": "directory",
            "datasets": [{"id": "bare-things", "name": "Bare Things", "table": "bare_things",
                          "arrival_pattern": r"bare_things[^/]*\.csv"}]})
    (tmp_path / "data-asset.yaml").write_text(yaml.safe_dump(doc, sort_keys=False))


def _code(calls: list) -> types.ModuleType:
    code = types.ModuleType(CODE)
    code.TABLES = [FAKE_TABLE]
    code.run_pipeline = lambda **kw: calls.append(("run_pipeline", kw))
    code.build_results_from_history = lambda: calls.append(("rebuild",))
    code.generate = lambda *, trial: calls.append(("generate", trial))
    code._run_one = lambda entry, now, run_by, on_step=None: calls.append(("run_one", entry)) or []
    code._discard_this_runs_schemas = lambda run_key: calls.append(("discard", run_key))
    return code


def _install(monkeypatch, tmp_path, *, bare: bool) -> list:
    _hierarchy(tmp_path, bare=bare)
    monkeypatch.setattr(hierarchy, "DATA_ASSET_YAML", tmp_path / "data-asset.yaml")
    hierarchy._load.cache_clear()
    collections._load.cache_clear()
    calls: list = []
    monkeypatch.setitem(sys.modules, CODE, _code(calls))
    adapter = types.ModuleType("qa_tools.collections.fake_collection")
    adapter.ADAPTER = CollectionAdapter(
        collection_id=FAKE_ID, label="Fake Things", orchestrator=CODE,
        run_pipeline_function="run_pipeline", warehouse_builder=CODE, warehouse_tables="TABLES",
        results_rebuild=CODE, generator=f"{CODE}:generate", target_datasets=(FAKE_DATASET,),
        dashboard_json="fake_collection_dashboard.json",
        dashboard_datasets=lambda doc: list(doc["datasets"]))
    monkeypatch.setitem(sys.modules, "qa_tools.collections.fake_collection", adapter)
    return calls


@pytest.fixture
def third_collection(monkeypatch, tmp_path):
    """The hierarchy with a third collection that has an adapter. Yields the
    list every call into its code is recorded in."""
    calls = _install(monkeypatch, tmp_path, bare=False)
    yield calls
    hierarchy._load.cache_clear()
    collections._load.cache_clear()


@pytest.fixture
def without_adapter(monkeypatch, tmp_path):
    """As third_collection, plus a fourth collection with no adapter."""
    calls = _install(monkeypatch, tmp_path, bare=True)
    yield calls
    hierarchy._load.cache_clear()
    collections._load.cache_clear()
