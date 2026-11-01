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

import json
import os
from types import MappingProxyType

from qa_tools import collections
from qa_tools.common import (asked_for, config_yaml, hierarchy, left_out, list_setting_members,
                             sample_keys, supply_db)
from qa_tools.common.check_lifecycle import dbt_check_id_lookup
from qa_tools.common.dbt_common import (
    ENGINE_TAG, NothingLeftToBuild, exclude_unreadable, failing_sample_keys_direct,
    failing_sample_keys_via_values, names_by_check_id, parse_threshold, parsed_test_nodes,
    run_dbt, selection, test_nodes,
)
from qa_tools.common.qa_results_writer import write_qa_result

__all__ = ["ENGINE_TAG", "evaluate", "selection_for", "test_names_by_check_id"]

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
PROFILES_DIR = os.path.join(os.path.dirname(__file__), "..", "dbt_profiles")

def _project_dir() -> str:
    """The selected asset's dbt project, resolved now and refused before dbt
    is invoked when its packages are not installed (REQ-QAC-368 criteria 3
    and 6). It was the import-time constant DBT_PROJECT_DIR."""
    from qa_tools.common import assets

    return str(assets.dbt_project_ready())


#: Row-shaped audit tables (the full failing row kept) are counted; the
#: value-aggregated ones (accepted_values, unique: (value, n_records) pairs,
#: see schema.yml) are summed. Every singular test is row-shaped.
_AUDIT_COUNTED = frozenset({"not_null", "accepted_range", "matches_regex", "expression_is_true"})
_AUDIT_SUMMED = frozenset({"accepted_values", "unique"})
#: The generic shapes whose audit rows carry the key directly - the counted
#: set, so an adapter's row_counted_tests (DbtSpec) extends both at once.
_SAMPLED_DIRECTLY = _AUDIT_COUNTED


def _counted(spec) -> frozenset:
    """The counted and directly-sampled tests: dbt's own, and those the
    collection's adapter declares (REQ-QAC-297 criterion 2)."""
    return _AUDIT_COUNTED | frozenset(getattr(spec, "row_counted_tests", ()) or ())


def _reads_declared_set(node: dict) -> bool:
    """Whether a test reads the run's declared-set relation - a set-member
    test, found by what it depends on, never by its name."""
    return any(n.split(".")[-1] == list_setting_members.RELATION
               and n.startswith("source.")
               for n in ((node.get("depends_on") or {}).get("nodes") or ()))


def _models(coll) -> list[str]:
    return [f"stg_{d.table}" for d in coll.datasets]


_CHECK_IDS = config_yaml.Built()


def _check_ids(schema_path: str) -> "MappingProxyType":
    """Built from the schema file itself, not the compiled manifest - see
    dbt_check_id_lookup() - and keyed on the file's content (REQ-PIPE-254),
    so an edited schema file is read for what it says now. Read-only, since
    every caller shares it. Only the ACTIVE file: a retired check never
    produces a result."""
    return _CHECK_IDS.from_file(schema_path, lambda text: MappingProxyType(
        dbt_check_id_lookup(schema_path, text=text)))


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
    return names_by_check_id(parsed_test_nodes(PROFILES_DIR, _project_dir()),
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


def _failing_sample_keys(conn, adapter, test_name, column, table, node, status, built) -> list:
    sampled_directly = _counted(adapter.dbt)
    if status not in ("warn", "fail"):
        return []
    # A TEST WHOSE FAILURE NAMES NO ROW declares it in its own meta - the one
    # `names_no_row` declaration every tool honours (REQ-PIPE-341); it replaced
    # the adapter's singular_unsampled list.
    if sample_keys.names_no_row(((node.get("config") or {}).get("meta") or {}).get("names_no_row")):
        return []
    relation_name = node.get("relation_name")
    if not relation_name:
        return []
    key, model = adapter.sample_key[table], f"stg_{table}"
    if built and model not in built:
        return []
    singular = node.get("test_metadata") is None
    if test_name in sampled_directly or singular:
        return failing_sample_keys_direct(conn, relation_name, key, check=test_name, table=table)
    if test_name in ("unique", "accepted_values"):
        value_column = "unique_field" if test_name == "unique" else "value_field"
        return failing_sample_keys_via_values(conn, relation_name, value_column, model, column, key,
                                              check=test_name, table=table)
    return []  # relationships - see the module docstring


def _no_declared_set(run_id: str) -> bool:
    conn = supply_db.connect(read_only=True, label="mothman:dbt-declared-set")
    try:
        return not list_setting_members.exists(conn, supply_db.run_schema(run_id))
    finally:
        conn.close()


def _set_judged_against(conn, run_id: str, table: str, node: dict) -> dict:
    setting = ((node.get("test_metadata") or {}).get("kwargs") or {}).get("member_setting")
    if not setting or not _reads_declared_set(node):
        return {}
    found = list_setting_members.read(conn, supply_db.run_schema(run_id), table, setting)
    return found.as_record() if found is not None else {}


def _not_evaluated_for_want_of_a_period(coll, spec, run_id: str, run_timestamp: str,
                                         asked) -> list[dict]:
    """One not-evaluated record per set-member check in the run's scope -
    red, could not run, with its structured reason (REQ-QAC-297 criterion 4);
    no data with a trial's reason for a staged-only trial, which decides
    nothing (post-build-review #299 item 3)."""
    from qa_tools.common import trial

    wanted = None if asked is None else set(asked)
    in_trial = trial.is_trial(run_id)
    code, reason, status = (
        (list_setting_members.TRIAL_NO_PERIOD, list_setting_members.TRIAL_NO_PERIOD_REASON, "nodata")
        if in_trial else
        (list_setting_members.NO_PERIOD, list_setting_members.NO_PERIOD_REASON, "fail"))
    out, seen = [], set()
    for node in parsed_test_nodes(PROFILES_DIR, _project_dir()).values():
        if not _reads_declared_set(node):
            continue
        table = _table_for_test(coll, spec, node)
        check_id = _check_id_for(coll, spec, node) if table else None
        if check_id is None or check_id in seen or (wanted is not None and check_id not in wanted):
            continue
        seen.add(check_id)
        meta = node["test_metadata"]
        out.append({
            "agency_id": coll.agency_id, "collection_id": coll.id,
            "dataset_id": hierarchy.dataset_for_table(table).dataset_id,
            "check_id": check_id, "column_name": node.get("column_name") or "(table)",
            "check_name": f"dbt:{meta['name']}", "dimension": "completeness",
            "label": "Not evaluated - the supply has no period",
            "run_id": run_id, "run_timestamp": run_timestamp, "status": status,
            "metric_value": None, "unit": None, "warn_threshold": None, "fail_threshold": None,
            "on_fail_action": "flag", "row_count_total": None, "row_count_invalid": None,
            "engine": ENGINE_TAG,
            "not_evaluated_code": code,
            "not_evaluated_reason": reason,
        })
    return out


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

    # A RUN FILED TO NO PERIOD HAS NO DECLARED SET (REQ-QAC-297 criterion 4):
    # the relation is built only with the period's views, so every test
    # reading it is left out of the selection - dbt finds them as the
    # relation's dependents - and recorded not evaluated, with its reason.
    no_period = _no_declared_set(run_id)
    if no_period:
        exclude = [*(exclude or []), f"source:raw.{list_setting_members.RELATION}+"]
    not_evaluated = _not_evaluated_for_want_of_a_period(
        coll, spec, run_id, run_timestamp, asked if scoped else None) if no_period else []

    run_dbt("build", selection_for(coll.id, asked) if scoped else models + list(spec.singular_home),
            target_path, PROFILES_DIR, _project_dir(), ROOT,
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
        # A set-member test left out for want of a period is not among them:
        # it carries its own not-evaluated record (REQ-QAC-297 criterion 4).
        left_out.note(run_id, "dbt", [
            _check_id_for(coll, spec, node) for uid, node in nodes.items()
            if uid not in ran and _table_for_test(coll, spec, node) is not None
            and _check_id_for(coll, spec, node) in wanted
            and not (no_period and _reads_declared_set(node))])

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
            if test_name in _counted(spec) or test_name in _AUDIT_SUMMED or meta is None:
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
                # EVERY KEY COLUMN, AND THEIR NAMES WHERE THERE ARE SEVERAL
                # (REQ-PIPE-341 criteria 2 and 9).
                **sample_keys.recorded(adapter.sample_key[table], sample),
                # THE SET IT WAS JUDGED AGAINST (REQ-QAC-300 criterion 9), from
                # the same relation the test read - never re-resolved.
                **_set_judged_against(conn, run_id, table, node),
                "engine": ENGINE_TAG,
            })
    finally:
        conn.close()
    results.extend(not_evaluated)
    write_qa_result(coll.agency_id, coll.id, run_id, run_timestamp, "dbt", run_results,
                    verified=results)
    return results
