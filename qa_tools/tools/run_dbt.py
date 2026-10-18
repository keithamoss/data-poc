"""Runs REAL dbt-core for any collection (REQ-QAC-242): `dbt build` over the
collection's own staging models and its singular tests, once per run, against
the run's own view schema - genuinely shelling out to the `dbt` CLI and
reading what it reports (target/manifest.json, target/run_results.json), not
a reimplementation of dbt's test logic.

ONLY THIS COLLECTION'S NODES (criterion 3): the models for the tables in the
collection's hierarchy, `stg_<table>`, and the singular tests its adapter
homes on them - an explicit node list rather than a graph selector, so this
never pulls in another collection's test if the project's DAG changes.

BUILT FROM CHILD PROTECTION'S COPY: N tables, each test's dataset from the
model dbt attaches it to, and REQ-PIPE-078's handling of a model the run
cannot build. What differs between collections is read from the adapter's
`.dbt`; REQ-QAC-247 retired the legacy flags this module read.

THE AUDIT TABLE, NOT dbt's OWN COUNT (_AUDIT_*). A confirmed dbt-core bug
(failures hardcoded to 0 whenever a test lands on "Pass", dbt-labs/
dbt-core#11312, unmerged in the installed 1.12.4) and a separate,
still-unexplained nondeterminism both report a count the audit table does not
hold (plans/qa-pipeline.md #34). So every test of a covered shape is recounted
from its own `--store-failures` audit table: dbt still ran the real check,
and this only stops trusting the summary fields known to be unreliable. It
counts whatever dbt decided was a failing row - never a copy of the check's
own condition (Keith's redline, item 28).

Up to 5 example failing rows' keys are captured per check from the same audit
tables (dbt_common) - the table's key column only, never full row content
(plans/qa-pipeline.md #15). `relationships` is a named gap: its audit table
carries only the offending FK value.
"""
from __future__ import annotations

import functools
import json
import os

from qa_tools import collections
from qa_tools.common import asked_for, hierarchy, left_out, supply_db
from qa_tools.common.check_lifecycle import dbt_check_id_lookup
from qa_tools.common.dbt_common import (
    ENGINE_TAG, NothingLeftToBuild, exclude_unreadable, failing_sample_keys_direct,
    failing_sample_keys_via_values, names_by_check_id, parse_threshold, parsed_test_nodes,
    run_dbt, selection, test_nodes,
)
from qa_tools.common.qa_results_writer import write_qa_result

__all__ = ["ENGINE_TAG", "evaluate", "selection_for", "test_names_by_check_id"]

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
DBT_PROJECT_DIR = os.path.join(ROOT, "dbt_project")
PROFILES_DIR = os.path.join(os.path.dirname(__file__), "..", "dbt_profiles")

#: Row-shaped audit tables (the full failing row kept) are counted; the
#: value-aggregated ones (accepted_values, unique: (value, n_records) pairs,
#: see schema.yml) are summed. Every singular test is row-shaped.
_AUDIT_COUNTED = frozenset({"not_null", "accepted_range", "matches_regex", "expression_is_true"})
_AUDIT_SUMMED = frozenset({"accepted_values", "unique"})
#: The generic shapes whose audit rows carry the key directly.
_SAMPLED_DIRECTLY = _AUDIT_COUNTED


def _models(coll) -> list[str]:
    return [f"stg_{d.table}" for d in coll.datasets]


@functools.lru_cache(maxsize=None)
def _check_ids(schema_path: str) -> dict:
    """Built once per schema file from the file itself, not the compiled
    manifest - see dbt_check_id_lookup(). Only the ACTIVE file: a retired
    check never produces a result."""
    return dbt_check_id_lookup(schema_path)


def _table_for_test(coll, spec, node: dict) -> str | None:
    """Which of this collection's tables a test is about - the model dbt
    attaches a generic test to, or the adapter's home for a singular test,
    which has none. None for another collection's test."""
    tables = {d.table for d in coll.datasets}
    if node.get("test_metadata") is None:
        table = spec.singular_home.get(node["name"])
    else:
        model = (node.get("attached_node") or "").split(".")[-1]
        table = model.removeprefix("stg_") if model.startswith("stg_") else None
    return table if table in tables else None


def _check_id_for(coll, spec, node: dict) -> str | None:
    """The check id a test node is recorded under, or None for a node that is
    not this collection's - the lookup the results loop makes, and the one
    the selection is computed through (REQ-PIPE-189 NFR 1)."""
    table = _table_for_test(coll, spec, node)
    if table is None:
        return None
    meta = node.get("test_metadata")
    return _check_ids(os.path.join(ROOT, coll.dbt_schema)).get(
        (f"stg_{table}" if meta else None, (node["column_name"] or None) if meta else None,
         meta["name"] if meta else node["name"]))


def test_names_by_check_id(collection_id: str) -> dict[str, list[str]]:
    """check id -> this collection's test node names, from the parsed project
    through `_check_id_for` (REQ-PIPE-189 NFR 1)."""
    coll = collections.by_id(collection_id)
    spec = collections.adapter(coll).dbt
    return names_by_check_id(parsed_test_nodes(PROFILES_DIR, DBT_PROJECT_DIR),
                             lambda node: _check_id_for(coll, spec, node))


def selection_for(collection_id: str, check_ids) -> list[str]:
    """`--select` for exactly these checks and the models they read."""
    return selection(check_ids, test_names_by_check_id(collection_id))


def _status_for(count: int, warn_t: float | None, fail_t: float | None) -> str:
    if fail_t is not None and count > fail_t:
        return "fail"
    if warn_t is not None and count > warn_t:
        return "warn"
    return "pass"


def _unreadable_in(run_id: str) -> frozenset[str]:
    """The logical tables this run has no view for - asked of the recorded
    resolution, which says WHY; a run that cannot connect fails on its own
    terms rather than here, which is why nothing is caught."""
    conn = supply_db.connect(read_only=True, label="mothman:dbt-readable")
    try:
        return frozenset(supply_db.resolution_for(conn, run_id).unreadable)
    finally:
        conn.close()


def _failing_sample_keys(conn, adapter, test_name, column, table, node, status, built) -> list[str]:
    if status not in ("warn", "fail"):
        return []
    relation_name = node.get("relation_name")
    if not relation_name:
        return []
    key, model = adapter.sample_key[table], f"stg_{table}"
    if built and model not in built:
        return []
    singular = node.get("test_metadata") is None
    if (test_name in _SAMPLED_DIRECTLY
            or (singular and test_name not in adapter.dbt.singular_unsampled)):
        return failing_sample_keys_direct(conn, relation_name, key)
    if test_name in ("unique", "accepted_values"):
        value_column = "unique_field" if test_name == "unique" else "value_field"
        return failing_sample_keys_via_values(conn, relation_name, value_column, model, column, key)
    return []  # relationships - see the module docstring


def evaluate(collection_id: str, run_id: str, run_timestamp: str) -> list[dict]:
    coll = collections.by_id(collection_id)
    adapter = collections.adapter(coll)
    spec = adapter.dbt
    models = _models(coll)
    tables = [d.table for d in coll.datasets]
    # WHAT THIS TOOL IS ASKED FOR, on record before it runs (REQ-PIPE-188).
    asked = asked_for.ask(run_id, run_timestamp, coll.agency_id, coll.id, "dbt")
    scoped = "dbt" in asked_for.SCOPED
    if scoped and not asked:
        # NOTHING ASKED RUNS NOTHING: no build, and the empty ask on record.
        write_qa_result(coll.agency_id, coll.id, run_id, run_timestamp,
                        "dbt", {"asked": []}, verified=[])
        return []
    target_path = str(supply_db.dbt_target_path(run_id))

    # A MODEL THIS RUN CANNOT READ IS NOT BUILT (REQ-PIPE-078): an errored
    # node takes the whole run down, so its model and every test reading it
    # are excluded before dbt starts.
    try:
        exclude = exclude_unreadable(models=models, unreadable=_unreadable_in(run_id))
    except NothingLeftToBuild as exc:
        print(f"note: {run_id}: {exc}")
        return []

    run_dbt("build", selection_for(coll.id, asked) if scoped else models + list(spec.singular_home),
            target_path, PROFILES_DIR, DBT_PROJECT_DIR, ROOT,
            run_schema=supply_db.run_schema(run_id), run_id=run_id, exclude=exclude,
            indirect_selection="empty" if scoped else None)

    with open(os.path.join(target_path, "manifest.json")) as f:
        manifest = json.load(f)
    with open(os.path.join(target_path, "run_results.json")) as f:
        run_results = json.load(f)

    nodes = test_nodes(manifest)
    if exclude:
        # SAID, so the run can reconcile it (REQ-PIPE-115 criterion 17).
        ran = {r["unique_id"] for r in run_results["results"]}
        wanted = set(asked)
        left_out.note(run_id, "dbt", [
            _check_id_for(coll, spec, node) for uid, node in nodes.items()
            if uid not in ran and _table_for_test(coll, spec, node) is not None
            and _check_id_for(coll, spec, node) in wanted])

    conn = supply_db.connect_dbt(run_id)
    try:
        built = {row[0] for row in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
            [supply_db.dbt_schema(run_id)]).fetchall()}
        n_total_by_table = {
            t: (conn.execute(f"SELECT COUNT(*) FROM stg_{t}").fetchone()[0]
                if f"stg_{t}" in built else None)
            for t in tables}

        results = []
        for r in run_results["results"]:
            node = nodes.get(r["unique_id"])
            if node is None:
                continue
            table = _table_for_test(coll, spec, node)
            if table is None:
                continue  # another collection's test, out of scope here

            meta = node.get("test_metadata")
            test_name = meta["name"] if meta else node["name"]
            if meta and node["column_name"]:
                column = node["column_name"]
            elif meta:
                column = spec.model_level_column.get(test_name, "(table)")
            else:
                column = spec.singular_column.get(node["name"], "(table)")
            config = node.get("config", {})
            status = r["status"]
            failures = r.get("failures") or 0
            warn_t = parse_threshold(config.get("warn_if"))
            fail_t = parse_threshold(config.get("error_if"))

            relation_name = node.get("relation_name")
            unaudited = ("error", "skipped")
            model_built = f"stg_{table}" in built
            if test_name in _AUDIT_COUNTED or test_name in _AUDIT_SUMMED or meta is None:
                if relation_name and status not in unaudited and model_built:
                    aggregate = ("COALESCE(SUM(n_records), 0)" if test_name in _AUDIT_SUMMED
                                 else "COUNT(*)")
                    verified_count = int(conn.execute(
                        f"SELECT {aggregate} FROM {relation_name}").fetchone()[0] or 0)
                    failures = verified_count
                    if warn_t is not None or fail_t is not None:
                        status = _status_for(verified_count, warn_t, fail_t)
                    else:
                        status = "fail" if verified_count > 0 else "pass"

            sample = _failing_sample_keys(conn, adapter, test_name, column, table, node, status,
                                          frozenset(built))
            check_id = _check_id_for(coll, spec, node)
            if check_id is None:
                raise ValueError(
                    f"no check_id found for dbt test {test_name!r} "
                    f"(model={f'stg_{table}' if meta else None!r}, "
                    f"column={(node['column_name'] or None) if meta else None!r}) - schema.yml "
                    f"is missing meta.check_id or this test isn't declared there")

            results.append({
                "agency_id": coll.agency_id,
                "collection_id": coll.id,
                "dataset_id": hierarchy.dataset_for_table(table).dataset_id,
                "check_id": check_id,
                "column_name": column,
                "check_name": f"dbt:{test_name}",
                "dimension": spec.dimension_by_test.get(test_name, ""),
                "label": spec.label_by_test.get(test_name),
                "run_id": run_id,
                "run_timestamp": run_timestamp,
                "metric_value": failures,
                "unit": "count",
                "warn_threshold": warn_t,
                "fail_threshold": fail_t,
                "status": status,
                "on_fail_action": "flag",
                "row_count_total": n_total_by_table[table],
                "row_count_invalid": failures,
                "failing_sample_keys": sample,
                "engine": ENGINE_TAG,
            })
    finally:
        conn.close()
    write_qa_result(coll.agency_id, coll.id, run_id, run_timestamp, "dbt", run_results,
                    verified=results)
    return results
