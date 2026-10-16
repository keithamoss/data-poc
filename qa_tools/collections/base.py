"""What a collection's adapter carries (REQ-PIPE-240).

IDENTITY PLUS TEMPORARY POINTERS, FOR NOW. The protocol grows step by step,
as per-tool sub-objects (.dbt, .soda, .datacontract, .evidently, .staging,
.stats, .present) in the requirements that follow. Here it carries only
what the five surviving dispatch sites need, and every pointer to a
collection's existing code names the requirement that removes it -
REQ-TEST-249 criterion 9 asserts none is left.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Callable


def _attr(path: str):
    """`package.module:name` -> the object."""
    module, _, name = path.partition(":")
    return getattr(importlib.import_module(module), name)


# ---- per-tool sub-objects (REQ-QAC-242 criterion 2) ------------------------
#
# Each shared module in qa_tools/tools/ reads only its own part of an
# adapter. Everything a sub-object holds is a difference between collections
# that is data, not code: a tool's behaviour that differs by collection is a
# legacy flag (`legacy` below), never a comparison of ids.


@dataclass(frozen=True)
class DatacontractSpec:
    #: A SQL rule's cross-tool label, by the tail its check id ends with.
    labels_by_check_tail: dict = field(default_factory=dict)
    #: Each table's key column, the only value a failing-row sample keeps.
    sample_key: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CollectionAdapter:
    collection_id: str
    #: How the bootstrap names this collection's work when it reports it -
    #: the words it has always used, so nothing it prints changes.
    label: str
    #: TEMPORARY POINTER (1), removed by REQ-PIPE-243: the collection's own
    #: orchestrator module, and its whole-history run function.
    orchestrator: str
    run_pipeline_function: str
    #: TEMPORARY POINTER (2), removed by REQ-QAC-242 (shared staging), gone by
    #: REQ-PIPE-243 in any case: the per-run warehouse builder, and the name of
    #: its table list there (a bare name or a list).
    warehouse_builder: str
    warehouse_tables: str
    #: TEMPORARY POINTER (3), removed by REQ-PIPE-243: the results-from-history
    #: rebuild.
    results_rebuild: str
    #: TEMPORARY POINTER (4), removed by REQ-GEN-246: the generator entry point.
    generator: str
    #: TEMPORARY POINTER (5), removed by REQ-GEN-246, which moves it to the
    #: provider: which datasets' targets this collection's replay records.
    target_datasets: tuple[str, ...]
    #: TEMPORARY POINTER (6), found at build and removed by REQ-PIPE-248, which
    #: gives every collection one dashboard JSON shape under a name from its id:
    #: the built dashboard file, and how its datasets are listed in it.
    dashboard_json: str
    dashboard_datasets: Callable[[dict], list[dict]] = field(compare=False)
    #: What each shared tool module reads (REQ-QAC-242 criterion 2).
    datacontract: DatacontractSpec = field(default_factory=DatacontractSpec)
    #: NAMED LEGACY FLAGS (REQ-QAC-242 criterion 4): each preserves one place
    #: this collection's recorded output differs from what the shared code
    #: would produce. Every name is in qa_tools/tools/legacy.py, which says
    #: what it preserves; `mothman check` refuses one that is not.
    legacy: frozenset = frozenset()

    def orchestrator_module(self):
        return importlib.import_module(self.orchestrator)

    def builder_module(self):
        return importlib.import_module(self.warehouse_builder)

    def tables(self) -> list[str]:
        tables = getattr(self.builder_module(), self.warehouse_tables)
        return [tables] if isinstance(tables, str) else list(tables)

    def run_pipeline(self, **kwargs):
        return getattr(self.orchestrator_module(), self.run_pipeline_function)(**kwargs)

    def rebuild_results(self):
        return _attr(f"{self.results_rebuild}:build_results_from_history")()

    def generate(self, *, trial: bool) -> None:
        _attr(self.generator)(trial=trial)
