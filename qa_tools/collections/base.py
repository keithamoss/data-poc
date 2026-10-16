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


@dataclass(frozen=True)
class DbtSpec:
    #: Each singular test's home table - it has no attached model - and the
    #: column it is routed to; the singular tests whose audit table holds no
    #: row keys to sample.
    singular_home: dict = field(default_factory=dict)
    singular_column: dict = field(default_factory=dict)
    singular_unsampled: frozenset = frozenset()
    #: A model-level generic test's column, by test type.
    model_level_column: dict = field(default_factory=dict)
    #: Each test type's dimension and cross-tool label.
    dimension_by_test: dict = field(default_factory=dict)
    label_by_test: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SodaSpec:
    #: The name the scan's data source goes by - it is in the raw output.
    data_source: str = "collection"
    #: A custom-named check's column, by its name: a `failed rows` check
    #: has none of its own.
    column_by_name: dict = field(default_factory=dict)
    #: A custom-named check's cross-tool label, by its name.
    label_by_name: dict = field(default_factory=dict)
    #: A check's dimension: a custom-named one's by its name (with
    #: `name_dimension_default` where it has none), any other by its metric.
    dimension_by_name: dict = field(default_factory=dict)
    name_dimension_default: str | None = ""
    dimension_by_metric: dict = field(default_factory=dict)
    #: The metrics whose own value is the count of invalid rows.
    invalid_count_metrics: frozenset = frozenset()


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
    #: Each table's key column, the only value a failing-row sample keeps -
    #: never full row content (plans/qa-pipeline.md #15).
    sample_key: dict = field(default_factory=dict)
    #: What each shared tool module reads (REQ-QAC-242 criterion 2).
    dbt: DbtSpec = field(default_factory=DbtSpec)
    datacontract: DatacontractSpec = field(default_factory=DatacontractSpec)
    soda: SodaSpec = field(default_factory=SodaSpec)
    #: NAMED LEGACY FLAGS (REQ-QAC-242 criterion 4): each preserves one place
    #: this collection's recorded output differs from what the shared code
    #: would produce. Every name is in qa_tools/tools/legacy.py, which says
    #: what it preserves; `mothman check` refuses one that is not.
    legacy: frozenset = frozenset()

    def orchestrator_module(self):
        return importlib.import_module(self.orchestrator)

    def run_pipeline(self, **kwargs):
        return getattr(self.orchestrator_module(), self.run_pipeline_function)(**kwargs)

    def rebuild_results(self):
        return _attr(f"{self.results_rebuild}:build_results_from_history")()

    def generate(self, *, trial: bool) -> None:
        _attr(self.generator)(trial=trial)
