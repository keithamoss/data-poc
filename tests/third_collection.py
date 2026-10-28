"""A third collection, for REQ-PIPE-240 criterion 6's one test per site.

ONE SMALL FIXTURE SHARED ACROSS SITES (the requirement's TEST COST NFR):
a copy of contract/data-asset.yaml with one more agency and collection,
an adapter, and a generator provider (REQ-GEN-246) whose plan only records
that it was asked for and writes no supply. Nothing here bootstraps
anything. `without_adapter` adds a fourth collection that
declares no adapter at all, for the refusal half of the criterion.
"""
from __future__ import annotations

import shutil
import sys
import types

import pytest
import yaml

from qa_tools import collections
from qa_tools.collections.base import CollectionAdapter, DatacontractSpec
from qa_tools.common import hierarchy

FAKE_ID, FAKE_SHORT, FAKE_PREFIX = "fake-collection", "fk", "fk_run_"
FAKE_DATASET, FAKE_TABLE = "fake-things", "fake_things"
BARE_ID, BARE_SHORT = "bare-collection", "bare"

#: Since REQ-PIPE-243 the orchestrator, dataset stats and results rebuild
#: are shared, so a site test records what the SHARED code was asked for by
#: patching qa_tools.tools.orchestrate. Since REQ-GEN-246 generation is
#: shared too: the fake provider's plan() records each call.
PROVIDER_MODULE = "generator.collections.fake_collection"
#: Its declared seeds, well clear of the real providers'.
FAKE_SEEDS = ((900_000, 901_000),)


def _hierarchy(tmp_path, *, bare: bool) -> None:
    """contract/ under tmp_path, laid out as the real one (REQ-QAC-241):
    every collection's check files in its agency's folder."""
    doc = yaml.safe_load(hierarchy.DATA_ASSET_YAML.read_text())
    contract_dir = tmp_path / "contract"
    for c in collections.all_collections():
        for kind in ("contract", "soda", "evidently"):
            dest = tmp_path / c.check_file(kind)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(hierarchy.DATA_ASSET_YAML.parent.parent / c.check_file(kind), dest)
    agencies = doc["hierarchy"]["agencies"]
    stems = [("fake-things", True)] + ([("bare-things", True)] if bare else [])
    (contract_dir / "fake-agency").mkdir()
    for stem, _ in stems:
        shutil.copy(hierarchy.DATA_ASSET_YAML.parent / collections.by_id("child-protection").contract,
                    contract_dir / "fake-agency" / f"{stem}-contract.yaml")
        for kind in ("soda-checks", "evidently-checks"):
            (contract_dir / "fake-agency" / f"{stem}-{kind}.yml").write_text("checks: []\n")
    agencies.append({"id": "fake-agency", "name": "Fake Agency", "short": "fka", "collections": [{
        "id": FAKE_ID, "name": "Fake Collection", "short": FAKE_SHORT,
        "run_prefix": FAKE_PREFIX, "contract": "fake-agency/fake-things-contract.yaml",
        "delivery_boundary": "directory",
        "datasets": [{"id": FAKE_DATASET, "name": "Fake Things", "table": FAKE_TABLE,
                      "arrival_pattern": r"fake_things[^/]*\.csv"}]}]})
    if bare:
        agencies[-1]["collections"].append({
            "id": BARE_ID, "name": "Bare Collection", "short": BARE_SHORT,
            "run_prefix": "bare_run_", "contract": "fake-agency/bare-things-contract.yaml",
            "delivery_boundary": "directory",
            "datasets": [{"id": "bare-things", "name": "Bare Things", "table": "bare_things",
                          "arrival_pattern": r"bare_things[^/]*\.csv"}]})
    (contract_dir / "data-asset.yaml").write_text(yaml.safe_dump(doc, sort_keys=False))
    # ITS CALENDAR, as a real collection declares one (REQ-PIPE-262 criterion
    # 9 refuses a bootstrap of a collection whose calendar cannot be
    # resolved): the quarterly one, so it replays in Child Protection's stream.
    from qa_tools.common import agreement

    cal = yaml.safe_load(agreement.CALENDAR_YAML.read_text())
    for cid in [FAKE_ID] + ([BARE_ID] if bare else []):
        cal["collections"].append({"id": cid, "calendar": "quarterly"})
    (contract_dir / "calendar.yaml").write_text(yaml.safe_dump(cal, sort_keys=False))
    # How the dashboard describes the asset sits beside the hierarchy
    # (REQ-DASH-244); the third collection has no entry until a test gives it one.
    shutil.copy(hierarchy.DATA_ASSET_YAML.parent / "presentation.yaml",
                contract_dir / "presentation.yaml")


def _provider(calls: list) -> types.ModuleType:
    """A real Provider subclass the shared driver can run: one slot-free
    plan over no periods, recorded when asked for."""
    from generator.collections.base import Plan, Provider

    class Fake(Provider):
        collection_id = FAKE_ID
        dataset_id = FAKE_DATASET
        seed_ranges = FAKE_SEEDS
        target_datasets = (FAKE_DATASET,)

        def seed_schedule(self):
            return [("the fake slot", 900_001, 900_010)]

        def generated_periods(self):
            return []

        def plan(self):
            calls.append(("generate", self.collection_id))
            return Plan(jobs=[])

    module = types.ModuleType(PROVIDER_MODULE)
    module.PROVIDER = Fake()
    return module


def _install(monkeypatch, tmp_path, *, bare: bool) -> list:
    _hierarchy(tmp_path, bare=bare)
    monkeypatch.setattr(hierarchy, "DATA_ASSET_YAML", tmp_path / "contract" / "data-asset.yaml")
    from qa_tools.common import agreement

    monkeypatch.setattr(agreement, "CALENDAR_YAML", tmp_path / "contract" / "calendar.yaml")
    calls: list = []
    monkeypatch.setitem(sys.modules, PROVIDER_MODULE, _provider(calls))
    adapter = types.ModuleType("qa_tools.collections.fake_collection")
    adapter.ADAPTER = CollectionAdapter(
        collection_id=FAKE_ID, label="Fake Things",
        datacontract=DatacontractSpec(labels_by_check_tail={"pair_datacontract": "Fake pair"}),
        sample_key={FAKE_TABLE: "fake_id"})
    monkeypatch.setitem(sys.modules, "qa_tools.collections.fake_collection", adapter)
    return calls


@pytest.fixture
def third_collection(monkeypatch, tmp_path):
    """The hierarchy with a third collection that has an adapter. Yields the
    list every call into its code is recorded in."""
    calls = _install(monkeypatch, tmp_path, bare=False)
    yield calls


@pytest.fixture
def without_adapter(monkeypatch, tmp_path):
    """As third_collection, plus a fourth collection with no adapter."""
    calls = _install(monkeypatch, tmp_path, bare=True)
    yield calls
