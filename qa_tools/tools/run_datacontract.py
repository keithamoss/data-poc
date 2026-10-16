"""Runs REAL datacontract-cli for any collection (REQ-QAC-242), against that
collection's ODCS contract - its Python DataContract API, not a
reimplementation - over the run's own per-run view schema.

BUILT FROM CHILD PROTECTION'S COPY, which had grown past Birth
Registrations': N tables rather than one, each check's dataset from the
model datacontract-cli says it belongs to, and REQ-PIPE-078's handling of a
table the run cannot read. What still differs between collections is read
from the adapter's `.datacontract` (labels, sample keys) and its legacy
flags (qa_tools/tools/legacy.py) - never from the collection's id.

THE WAREHOUSE, NOT THE FILE (REQ-QAC-088): every schema object becomes a
real view on one connection, so a contract's cross-table `type: sql` rules
genuinely join. Up to 5 example failing rows' keys are captured per check
through datacontract-cli's own include_failed_samples (datacontract_common),
restricted to the table's key column - never full row content
(plans/qa-pipeline.md #15). custom_sql rules are not covered by it, a real
gap noted rather than hidden.
"""
from __future__ import annotations

import functools
import os

from qa_tools import collections
from qa_tools.common import asked_for, hierarchy, left_out, supply_db
from qa_tools.common.check_lifecycle import name_by_check_id, parse_contract_check_metadata
from qa_tools.common.datacontract_common import (
    DIMENSION_BY_METRIC, ENGINE_TAG, LABEL_BY_METRIC, SAMPLEABLE_METRICS,
    check_id_from_quality_definition, fail_threshold_from_quality_definition,
    failing_sample_keys, run_against_warehouse, selection_for,
)
from qa_tools.common.qa_results_writer import _declared_reads_tables, run_owner, write_qa_result

__all__ = ["ENGINE_TAG", "evaluate"]

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")

# The quality-rule-driven check types a contract produces (metric:
# nullValues/invalidValues/duplicateValues/rowCount and type: sql rules) -
# excluding the schema-derived field_present/field_required/field_unique
# checks datacontract-cli generates from `required`/`unique` flags, which
# duplicate these.
_QUALITY_CHECK_TYPES = {
    "field_null_values", "field_invalid_values", "field_duplicate_values",
    "field_quality_sql", "model_quality_sql", "row_count",
}


def contract_path(collection_id: str) -> str:
    return os.path.join(ROOT, collections.by_id(collection_id).check_file("contract"))


@functools.lru_cache(maxsize=None)
def _authored_names(path: str) -> dict:
    """Each SQL rule's authored display name, read once per contract from the
    same parse category_by_check_id() uses (REQ-QAC-023)."""
    return name_by_check_id(parse_contract_check_metadata(path))


def _unreadable_in(run_id: str, tables) -> frozenset[str]:
    """The logical tables this run has no view for - see
    supply_db.readable_in() for why the schema rather than the record."""
    conn = supply_db.connect(read_only=True, label="mothman:datacontract-readable")
    try:
        return frozenset(tables) - supply_db.readable_in(conn, run_id)
    finally:
        conn.close()


def evaluate(collection_id: str, run_id: str, run_timestamp: str) -> list[dict]:
    coll = collections.by_id(collection_id)
    adapter = collections.adapter(coll)
    spec = adapter.datacontract
    tables = [d.table for d in coll.datasets]
    path = contract_path(collection_id)
    # WHAT THIS TOOL IS ASKED FOR, on record before it runs (REQ-PIPE-188).
    asked = asked_for.ask(run_id, run_timestamp, coll.agency_id, coll.id, "datacontract")
    scoped = "datacontract" in asked_for.SCOPED
    if scoped and not asked:
        # NOTHING ASKED RUNS NOTHING - see run_dbt.evaluate().
        write_qa_result(coll.agency_id, coll.id, run_id, run_timestamp,
                        "datacontract", {"asked": []}, verified=[])
        return []
    # ITS OWN OPTIONS, NEVER A PRUNED CONTRACT (REQ-PIPE-190): the run's
    # rules by id, and their model where they all sit on one. Neither for a
    # run whose id names no table, which asks for the whole contract.
    options = (selection_for(path, asked)
               if scoped and run_owner(run_id) is not None else {})
    run = run_against_warehouse(path, supply_db.run_schema(run_id), **options)
    reads_unreadable = "datacontract.reads_unreadable_tables" in adapter.legacy
    unreadable = frozenset() if reads_unreadable else _unreadable_in(run_id, tables)
    declared = {} if reads_unreadable else _declared_reads_tables()
    names = _authored_names(path)

    results = []
    left = []
    for c in run.checks:
        if c.type not in _QUALITY_CHECK_TYPES:
            continue
        table = c.model
        if table not in tables:
            continue
        # A RULE OVER A TABLE THIS RUN CANNOT READ WAS NOT RUN, and is left
        # out rather than recorded (2026-10-02). datacontract-cli runs every
        # rule it is asked for whatever the schema holds, so such a rule
        # comes back `failed` - a FALSE RED about our own timing, now that
        # one file is one arrival and a sibling can be absent (REQ-PIPE-105).
        # dbt and Soda leave the same checks out before running; here it is
        # done after, against the same declaration they use.
        if table in unreadable or unreadable & set(
                declared.get(check_id_from_quality_definition(c.qualityDefinition), ())):
            # SAID, so the run can reconcile it (REQ-PIPE-115 criterion 17).
            left.append(check_id_from_quality_definition(c.qualityDefinition))
            continue

        diag = c.diagnostics or {}
        metric = diag.get("metric", c.type)
        is_pct = "percent" in diag
        value = diag.get("percent") if is_pct else diag.get("value")
        row_count_invalid = None if metric == "row_count" else diag.get("value")

        check_id = check_id_from_quality_definition(c.qualityDefinition)
        if check_id is None:
            raise ValueError(f"no check_id found in qualityDefinition for datacontract check {c.name!r} "
                             f"(type={c.type!r}) - the contract is missing customProperties.check_id for this rule")

        if metric == "custom_sql":
            # The AUTHORED name, never the rule's own prose (REQ-QAC-023): a
            # rule with none is an authoring gap, and failing loudly beats
            # falling back to the description.
            authored = names.get(check_id)
            if not authored:
                raise ValueError(
                    f"datacontract SQL rule {check_id!r} has no authored "
                    f"customProperties `name` - add one rather than letting its "
                    f"display name come from its description")
            check_name = f"datacontract:sql: {authored}"
            # The cross-tool label from the check id's own tail - structure,
            # never words in the description. `label` ties equivalent checks
            # together across tools, so it is only ever an exact tail.
            label = next((lbl for tail, lbl in spec.labels_by_check_tail.items()
                          if check_id.endswith(tail)), None)
        else:
            check_name = f"datacontract:{metric}"
            label = LABEL_BY_METRIC.get(metric)

        results.append({
            "agency_id": coll.agency_id,
            "collection_id": coll.id,
            "dataset_id": hierarchy.dataset_for_table(table).dataset_id,
            "check_id": check_id,
            "column_name": c.field or "(table)",
            "check_name": check_name,
            "dimension": c.dimension or DIMENSION_BY_METRIC.get(metric, ""),
            "label": label,
            "run_id": run_id,
            "run_timestamp": run_timestamp,
            "metric_value": value,
            "unit": "%" if is_pct else "count",
            # ODCS severity is single-tier - see README.md's known-disagreements.
            "warn_threshold": None,
            "fail_threshold": fail_threshold_from_quality_definition(c.qualityDefinition, diag.get("severity")),
            "status": {"passed": "pass", "failed": "fail", "warning": "warn"}.get(c.result.value, c.result.value),
            "on_fail_action": "quarantine" if diag.get("severity") == "error" else "flag",
            "row_count_total": diag.get("row_count"),
            "row_count_invalid": row_count_invalid,
            "failing_sample_keys": (failing_sample_keys(c, spec.sample_key[table])
                                    if metric in SAMPLEABLE_METRICS else []),
            "engine": ENGINE_TAG,
        })

    # No live-query correction needed (row_count is already in the raw
    # output's own diagnostics); `verified` is still written, for uniformity
    # with the other three tools.
    if not reads_unreadable:
        left_out.note(run_id, "datacontract", left)
    write_qa_result(coll.agency_id, coll.id, run_id, run_timestamp,
                    "datacontract", run.model_dump(), verified=results)
    return results
