"""What a collection's adapter carries (REQ-PIPE-240).

IDENTITY, WHAT EACH SHARED MODULE READS, AND THE LAST TEMPORARY POINTER.
The per-tool sub-objects (.dbt, .soda, .datacontract, .stats) are what
qa_tools/tools/* read for this collection (REQ-QAC-242, REQ-PIPE-243), the
`legacy` flags name the behaviours Birth Registrations kept, and the one
pointer left - dashboard_json/dashboard_datasets - names the requirement
that removes it (REQ-PIPE-248); REQ-TEST-249 criterion 9 asserts none is
left. The generator entry point and the target-trial datasets went with
REQ-GEN-246, which put both on the collection's generator provider
(generator/collections/<id>.py) - a real deployment's collections have no
synthetic generator, so an adapter is the wrong place for either.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


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
class StatsSpec:
    """What the shared dataset statistics read (REQ-PIPE-243 criterion 2).

    Pure data, so an adapter stays importable without a QA tool library
    (criterion 5): the SQL is a condition string, run by
    qa_tools/tools/dataset_stats.py."""
    #: Per (table, column): `kind` (categorical or numeric_date), the
    #: `invalid_condition` the real checks flag, a `classification`, and the
    #: `check_names` the dashboard attaches the aggregate to.
    aggregates: dict = field(default_factory=dict)
    #: Per (table, column): the known values of a value-count distribution,
    #: in display order; anything else counts as "(invalid code)".
    value_counts: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CollectionAdapter:
    collection_id: str
    #: How the bootstrap names this collection's work when it reports it -
    #: the words it has always used, so nothing it prints changes.
    label: str
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
    stats: StatsSpec = field(default_factory=StatsSpec)
    #: The dataset whose claim window applies when an arrival names none of
    #: its own (REQ-PIPE-243 criterion 2); None means no window, never a
    #: borrowed one.
    claim_window_dataset: str | None = None
    #: The results file under reports/ the batch and the rebuild write
    #: (REQ-PIPE-243); REQ-PIPE-248 names every collection's from its id.
    results_json: str = ""
    #: NAMED LEGACY FLAGS (REQ-QAC-242 criterion 4): each preserves one place
    #: this collection's recorded output differs from what the shared code
    #: would produce. Every name is in qa_tools/tools/legacy.py, which says
    #: what it preserves; `mothman check` refuses one that is not.
    legacy: frozenset = frozenset()
