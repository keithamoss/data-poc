"""What a collection's adapter carries (REQ-PIPE-240).

IDENTITY AND WHAT EACH SHARED MODULE READS. The per-tool sub-objects
(.dbt, .soda, .datacontract, .stats) are what qa_tools/tools/* read for this
collection (REQ-QAC-242, REQ-PIPE-243), and the `legacy` flags name the
behaviours Birth Registrations kept until REQ-PIPE-248 retired them. The
last temporary pointer, dashboard_json/dashboard_datasets, went with
REQ-PIPE-248: a collection's report files are named by the registry and
every dashboard file lists its datasets under `datasets`. The generator entry point and the target-trial datasets went with
REQ-GEN-246, which put both on the collection's generator provider
(generator/collections/<id>.py) - a real deployment's collections have no
synthetic generator, so an adapter is the wrong place for either.
"""
from __future__ import annotations

from dataclasses import dataclass, field


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
    #: column it is routed to. (A test whose failure names no row declares
    #: `names_no_row: true` in its own meta - REQ-PIPE-341.)
    singular_home: dict = field(default_factory=dict)
    singular_column: dict = field(default_factory=dict)
    #: A model-level generic test's column, by test type.
    model_level_column: dict = field(default_factory=dict)
    #: Each test type's dimension and cross-tool label.
    dimension_by_test: dict = field(default_factory=dict)
    label_by_test: dict = field(default_factory=dict)
    #: The collection's own GENERIC tests whose audit table holds one row per
    #: violation (REQ-QAC-297 criterion 2): each is recounted from that table
    #: AND sampled directly from it. One declaration serves both, because
    #: run_dbt's built-in sampled-directly set is its counted set - so a test
    #: named here is read exactly as dbt's own not_null is. run_dbt.py names
    #: none of them.
    row_counted_tests: frozenset = frozenset()


@dataclass(frozen=True)
class SodaSpec:
    #: The name the scan's data source goes by - it is in the raw output.
    data_source: str = "collection"
    #: A custom-named check's column, by its name: a `failed rows` check
    #: has none of its own.
    column_by_name: dict = field(default_factory=dict)
    #: A custom-named check's cross-tool label, by its name.
    label_by_name: dict = field(default_factory=dict)
    # A check's dimension is its own `category` in the checks file
    # (REQ-QAC-247), so there is no map of it here.
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
    #: Each table's failing-sample key, an ORDERED LIST of columns - one
    #: column a list of one (REQ-PIPE-341 criterion 1). Only these values ever
    #: leave a sampler - never full row content (plans/qa-pipeline.md #15);
    #: qa_tools/common/sample_keys.py says what a sample of one or several
    #: columns records.
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
    #: NAMED LEGACY FLAGS (REQ-QAC-242 criterion 4), ALL RETIRED: each
    #: preserved one place a collection's recorded output differed from the
    #: shared code's, and REQ-QAC-247 and REQ-PIPE-248 unified every one, so
    #: qa_tools/tools/legacy.py knows none and `mothman check` refuses any
    #: flag declared here. Kept as a field so that refusal can name it.
    legacy: frozenset = frozenset()
