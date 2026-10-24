"""Runs REAL Soda Core for any collection (REQ-QAC-242), against that
collection's SodaCL checks file and the run's own per-run view schema.

BUILT FROM CHILD PROTECTION'S COPY: N tables, each check's dataset from its
own table, and REQ-PIPE-078's handling of a table the run cannot read.
What differs between collections is read from the adapter's `.soda` (the
data source's name, a custom-named check's column, label and dimension, and
which metrics count invalid rows) and its legacy flags
(qa_tools/tools/legacy.py) - never from the collection's id.

Captures up to 5 example failing rows' keys per check through a custom
Sampler (soda_common.CaptureSampler: Soda's own computes samples then
discards them) - the table's key column only, never full row content
(plans/qa-pipeline.md #15). A metric check needs `samples limit:` in the
checks file; a `failed rows` check samples automatically.
"""
from __future__ import annotations

import os

from qa_tools import collections
from qa_tools.common import asked_for, hierarchy, left_out, supply_db
from qa_tools.common.qa_results_writer import write_qa_result
from qa_tools.common.soda_common import (
    ENGINE_TAG, CaptureSampler, check_id_from_resource_attributes, execute_scan,
    failing_sample_keys, left_out_checks, not_evaluated_record, readable_checks_yaml,
    resource_attribute, threshold, unreported_checks,
)

__all__ = ["ENGINE_TAG", "evaluate"]

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")

#: A short, human-readable phrase for what a metric check measures, written
#: where the result is built rather than guessed later from its name.
_LABEL_BY_METRIC = {
    "missing_count": "Null rate", "missing_percent": "Null rate",
    "invalid_percent": "Invalid values", "row_count": "Row count",
    "duplicate_count": "Duplicate rate", "reference": "Referential integrity",
}


def checks_path(collection_id: str) -> str:
    return os.path.join(ROOT, collections.by_id(collection_id).check_file("soda"))


def evaluate(collection_id: str, run_id: str, run_timestamp: str) -> list[dict]:
    coll = collections.by_id(collection_id)
    adapter = collections.adapter(coll)
    spec = adapter.soda
    tables = [d.table for d in coll.datasets]
    path = checks_path(collection_id)
    # WHAT THIS TOOL IS ASKED FOR, on record before it runs (REQ-PIPE-188).
    asked = asked_for.ask(run_id, run_timestamp, coll.agency_id, coll.id, "soda")
    # ONLY THE ASKED-FOR CHECKS ARE HANDED (REQ-PIPE-191), removed by check
    # id exactly as an unreadable table's are.
    keep = set(asked) if "soda" in asked_for.SCOPED else None
    if keep is not None and not keep:
        # NOTHING ASKED RUNS NOTHING - see run_dbt.evaluate().
        write_qa_result(coll.agency_id, coll.id, run_id, run_timestamp,
                        "soda", {"asked": []}, verified=[])
        return []
    from soda.scan import Scan

    # READ-ONLY: a reader that cannot write what it is measuring
    # (REQ-PIPE-087). CLOSED IN A `finally` - a Soda scan raising is exactly
    # the case nobody is watching.
    conn = supply_db.connect(read_only=True)
    try:
        # The run's own view schema on the search path - one arrival's rows,
        # resolved only where exactly one staged table claims the name.
        conn.execute(f'SET search_path TO "{supply_db.run_schema(run_id)}"')
        # ONLY WHAT THIS RUN CAN READ - see soda_common.readable_checks_yaml().
        # Asked of the run's OWN SCHEMA rather than the recorded resolution:
        # what Soda can query is exactly what has a view.
        unreadable = set(tables) - supply_db.readable_in(conn, run_id)
        n_total_by_table = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                            for t in tables if t not in unreadable}

        scan = Scan()
        scan.set_data_source_name(spec.data_source)
        # CONFIGURED RATHER THAN HANDED A CONNECTION (REQ-PIPE-087):
        # soda-core-postgres has no way in for one, so the run's view schema
        # reaches Soda as its data source's own `schema`.
        scan.add_configuration_yaml_str(supply_db.soda_config_yaml(
            spec.data_source, supply_db.run_schema(run_id)))
        handed = readable_checks_yaml(path, unreadable, keep=keep)
        scan.add_sodacl_yaml_str(handed)
        left_out.note(run_id, "soda", left_out_checks(path, unreadable, keep=keep))
        sampler = CaptureSampler()
        scan.sampler = sampler
        scan.disable_telemetry()
        # RUN IT THROUGH THE HELPER, never `scan.execute()` directly - see
        # execute_scan() for the two things a bare scan leaves behind.
        scan_results = execute_scan(scan)
        metric_name_by_id = {m["identity"]: m["metricName"] for m in scan_results["metrics"]}

        results = []
        for c in scan_results["checks"]:
            table = c["table"]
            if table not in tables:
                continue  # not this collection's table (shouldn't happen - guard anyway)
            diagnostics = c["diagnostics"]
            value = diagnostics.get("value")
            # The real check type comes from the metric it reads, not from
            # parsing its name: a custom-named check (a scoped filter check,
            # or a `failed rows` check with no metric at all) has a `name:`
            # that does not follow the generic pattern.
            base_check = metric_name_by_id.get(c["metrics"][0], c["name"]) if c["metrics"] else c["name"]
            # Soda's generated name is the whole check line ("... warn when >
            # 0"); a real custom `name:` reads as a short label with no "when".
            is_custom_name = "when" not in c["name"]
            check_name = c["name"] if is_custom_name else base_check
            column = (c["column"] or (spec.column_by_name.get(c["name"]) if is_custom_name else None)
                      or "(table)")

            check_id = check_id_from_resource_attributes(c)
            if check_id is None:
                raise ValueError(f"no check_id found in resourceAttributes for soda check {c['name']!r} - "
                                 f"the checks YAML is missing attributes.check_id for this check")

            row_count_invalid = None
            if diagnostics.get("blocks"):
                # TWO BLOCK SHAPES (post-build-review #226): a metric check's
                # failedRowsAnalysis carries totalFailingRows, a custom
                # `failed rows` check's `file` block carries file.totalRowCount.
                block = diagnostics["blocks"][0]
                row_count_invalid = (block["file"].get("totalRowCount")
                                     if block.get("type") == "file"
                                     else block.get("totalFailingRows"))
            elif base_check == "row_count":
                row_count_invalid = 0
            elif base_check in spec.invalid_count_metrics:
                row_count_invalid = int(value) if value is not None else None

            # THE DIMENSION IS THE CHECK'S OWN `category` (REQ-QAC-247, Keith
            # 2026-10-18), written beside it in the checks file - never a
            # second copy kept in the adapter, which is how Child
            # Protection's 52 checks came to be recorded with none.
            dimension = resource_attribute(c, "category") or ""
            label = (spec.label_by_name.get(c["name"]) if is_custom_name
                     else _LABEL_BY_METRIC.get(base_check))

            results.append({
                "agency_id": coll.agency_id,
                "collection_id": coll.id,
                "dataset_id": hierarchy.dataset_for_table(table).dataset_id,
                "check_id": check_id,
                "column_name": column,
                "check_name": check_name,
                "dimension": dimension,
                "label": label,
                "run_id": run_id,
                "run_timestamp": run_timestamp,
                "metric_value": value,
                "unit": "%" if base_check.endswith("percent") else "count",
                "warn_threshold": threshold(diagnostics.get("warn")),
                "fail_threshold": threshold(diagnostics.get("fail")),
                "status": c["outcome"],
                "on_fail_action": "flag",
                "row_count_total": n_total_by_table[table],
                "row_count_invalid": row_count_invalid,
                "failing_sample_keys": failing_sample_keys(sampler.captured, c["name"],
                                                           adapter.sample_key[table], table),
                "engine": ENGINE_TAG,
            })

        # EVERY DECLARED CHECK SODA DID NOT REPORT IS RED, never absent (the
        # road-testing sweep's #7): Soda leaves a check it cannot evaluate
        # out of its results entirely. Only what was HANDED to the scan - a
        # check left out for an unreadable table is left_out's to record.
        for missing in unreported_checks(handed, scan_results, scan):
            if missing["table"] not in tables:
                # NEVER SKIPPED QUIETLY (#131 D6): a check this runner cannot
                # attribute is a configuration fault, and dropping it would be
                # the very false green this record exists to prevent.
                raise ValueError(
                    f"Soda check {missing['check_id']!r} is declared on "
                    f"{missing['table']!r}, which is not one of {coll.name}'s tables - it "
                    f"could not be evaluated and cannot be recorded against a dataset")
            results.append(not_evaluated_record(
                missing, agency_id=coll.agency_id, collection_id=coll.id,
                dataset_id=hierarchy.dataset_for_table(missing["table"]).dataset_id,
                run_id=run_id, run_timestamp=run_timestamp,
                row_count_total=n_total_by_table.get(missing["table"]), engine=ENGINE_TAG))
    finally:
        conn.close()
    # Committed only now, after row_count_total's own live query - the scan's
    # results never carry it (qa_results_writer.py on `verified`).
    write_qa_result(coll.agency_id, coll.id, run_id, run_timestamp, "soda", scan_results,
                    verified=results)
    return results
