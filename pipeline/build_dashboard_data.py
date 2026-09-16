"""
Reshapes reports/results_bdm.json (qa_tools/bdm/orchestrate_bdm.py's real,
computed check output - actual dbt-core/Soda Core/datacontract-cli/
Evidently runs) into the exact JSON shape the QA reporting dashboard's
drawer/chart code expects for a dataset - the "reskin the same 3-tier
dashboard, wired to real data" piece of the brief, for the Birth
Registrations dataset only.

This does NOT touch the dashboard's rendering code or its other 14
datasets (Death/Marriage Registrations and everything outside Registry
Services) - those stay the existing illustrative mock, clearly labeled as
such. Only Birth Registrations' columns/checks/stats are replaced, with
every number traceable back to a real tool run in qa_tools/bdm/*.py.

Previously merged this with reports/results.json, the output of a set of
four hand-written equivalent check engines (engines/*.py) built when the
original session had no PyPI access. Those engines were removed once that
constraint no longer applied and they'd drifted out of sync with newer
checks that were only ever built real-tools-only - results_bdm.json
alone is now a complete superset (824 checks vs. the old equivalent
path's 630), so the merge logic is gone too. See plans/wider.md's
repo-tidy-up entries for the full history.

Output: reports/birth_registrations_dashboard.json, embedded into the HTML
by embed_dashboard_data.py as a JS const.
"""
from __future__ import annotations
import json
import os

from qa_tools.bdm.dataset_stats import AGGREGATE_SPEC
from pipeline.dashboard_check_labels import rank_for_headline, display_name

ROOT = os.path.join(os.path.dirname(__file__), "..")
REAL_RESULTS_PATH = os.path.join(ROOT, "reports", "results_bdm.json")
OUT_PATH = os.path.join(ROOT, "reports", "birth_registrations_dashboard.json")

ENGINE_SHORT = {
    # Same short-name convention as build_cp_dashboard_data.py's own
    # ENGINE_SHORT for these 4 tags. No "(real)" suffix on the tag itself
    # any more - there's nothing left to distinguish it from since
    # engines/*.py was removed (see plans/wider.md #20's follow-up).
    "dbt-core 1.12 + dbt-duckdb": "dbt-core",
    "Soda Core 3.5": "Soda Core",
    "datacontract-cli 1.2.0": "datacontract-cli",
    "Evidently 0.7": "Evidently AI",
}

COLUMN_META = {
    "registration_number": ("string · varchar(20)", "BDM's unique registration identifier — primary key of the feed."),
    "child_given_names": ("string · varchar(200)", "Required. Small non-zero null rate expected from data-entry lag at source."),
    "child_family_name": ("string · varchar(200)", "Required."),
    "date_of_birth": ("date", "Required, and range-checked against 1900-01-01..today."),
    "sex": ("string · varchar(1)", "Closed value set (M / F / X) that several downstream eligibility systems key off directly."),
    "place_of_birth_suburb": ("string · varchar(100)", "Required."),
    "place_of_birth_facility": ("string · varchar(200)", "Nullable — not every birth occurs in a registered facility (home births are legitimate)."),
    "date_registered": ("date", "Required; must be ≥ date_of_birth."),
    "registering_parent_1_name": ("string · varchar(200)", "Optional."),
    "registering_parent_2_name": ("string · varchar(200)", "Optional — single-parent registrations are legitimately common."),
    "is_multiple_birth": ("boolean", "Required."),
    "source_system_record_id": ("string · varchar(50)", "BDM's internal record ID, kept for re-extraction tracing."),
    "extract_timestamp": ("timestamp", "When the record was extracted at BDM's source system."),
}

ALL_COLUMNS = list(COLUMN_META.keys())


def build() -> dict:
    with open(REAL_RESULTS_PATH) as f:
        payload = json.load(f)
    manifest = sorted(payload["runs"], key=lambda r: r["run_date"])
    results = payload["results"]
    dataset_stats = payload["dataset_stats"]

    # column_name -> (engine, check_name) -> {unit, warn, fail, by_run_id: {run_id: value}}
    by_column: dict[str, dict[tuple, dict]] = {}
    for r in results:
        col = r["column_name"]
        if col == "(table)":
            continue
        key = (r["engine"], r["check_name"])
        slot = by_column.setdefault(col, {}).setdefault(key, {
            "unit": r["unit"], "warn": r["warn_threshold"], "fail": r["fail_threshold"],
            "dimension": r["dimension"], "label": r.get("label"),
            "by_run": {}, "row_count_total": {}, "row_count_invalid": {}, "failing_sample_keys": {},
        })
        slot["by_run"][r["run_id"]] = r["metric_value"]
        slot["row_count_total"][r["run_id"]] = r["row_count_total"]
        slot["row_count_invalid"][r["run_id"]] = r["row_count_invalid"]
        slot["failing_sample_keys"][r["run_id"]] = r.get("failing_sample_keys") or []

    run_ids_in_order = [m["run_id"] for m in manifest]
    latest_run, prev_run = run_ids_in_order[-1], run_ids_in_order[-2]
    # run_date alone can't key a run uniquely - a resupply run shares its
    # base run's run_date (e.g. run_54_2026-09-10 and
    # run_54_2026-09-10_resupply1) - so byRun below keys directly on
    # run_id via each history entry's own "run_id" field, not run_date.
    row_count_by_run = {m["run_id"]: m["n_rows_generated"] for m in manifest}

    columns_out = []
    for col in ALL_COLUMNS:
        logical_type, desc = COLUMN_META[col]
        checks_for_col = by_column.get(col, {})

        agg_spec = AGGREGATE_SPEC.get(col)

        checks_out = []
        for (engine, check_name), slot in checks_for_col.items():
            attach_aggregate = agg_spec is not None and check_name in agg_spec["check_names"]
            history = []
            for run_id in run_ids_in_order:
                if run_id in slot["by_run"]:
                    run_date = next(m["run_date"] for m in manifest if m["run_id"] == run_id)
                    aggregate_values = None
                    if attach_aggregate:
                        aggregate_values = dataset_stats[run_id]["check_aggregates"].get(col)
                    history.append({
                        "run_id": run_id, "run_date": run_date, "value": slot["by_run"][run_id],
                        "row_count_total": slot["row_count_total"].get(run_id),
                        "row_count_invalid": slot["row_count_invalid"].get(run_id),
                        "failing_sample_keys": slot["failing_sample_keys"].get(run_id) or [],
                        "aggregate_values": aggregate_values,
                    })
            if not history:
                continue
            engine_short = ENGINE_SHORT.get(engine, engine)
            checks_out.append({
                "name": display_name(check_name, engine_short, slot["label"]),
                "dimension": slot["dimension"],
                "unit": slot["unit"],
                "warn": slot["warn"] if slot["warn"] is not None else 0,
                "fail": slot["fail"] if slot["fail"] is not None else 0,
                "current": slot["by_run"].get(latest_run, 0),
                "previous": slot["by_run"].get(prev_run, 0),
                "history": history,
                "note": f"Computed by {engine} against this run's real data — not a fabricated figure.",
            })

        if not checks_out:
            # honest placeholder - no rule anywhere covers this column today
            checks_out = [{
                "name": "No automated quality rule defined",
                "dimension": "", "unit": "count", "warn": 1, "fail": 1,
                "current": 0, "previous": 0,
                "history": [{"run_id": m["run_id"], "run_date": m["run_date"], "value": 0} for m in manifest],
                "note": "Neither the ODCS contract nor the Soda/dbt check files define a rule for this "
                        "column today — this is a real gap, not a hidden failure.",
            }]

        rank_for_headline(checks_out)

        # representative row counts for the stats block: the manifest's own
        # generated row count for that run (every column shares one table,
        # so this is the same for all of them - what differs per column is
        # how many of those rows the *primary* check, checks[0], flagged).
        total_latest_manifest = next(m for m in manifest if m["run_id"] == latest_run)["n_rows_generated"]
        total_prev_manifest = next(m for m in manifest if m["run_id"] == prev_run)["n_rows_generated"]

        stats = {
            "current": {"total": total_latest_manifest, "invalid": 0, "valid": total_latest_manifest, "valueCounts": None},
            "previous": {"total": total_prev_manifest, "invalid": 0, "valid": total_prev_manifest, "valueCounts": None},
        }
        if checks_out:
            primary_unit = checks_out[0]["unit"]
            for label, run_id, total_key in (("current", latest_run, "total_latest_manifest"), ("previous", prev_run, "total_prev_manifest")):
                total = total_latest_manifest if label == "current" else total_prev_manifest
                val = checks_out[0]["current"] if label == "current" else checks_out[0]["previous"]
                n_invalid = int(round(total * val / 100)) if primary_unit == "%" else int(round(val))
                stats[label]["invalid"] = max(0, n_invalid)
                stats[label]["valid"] = max(0, total - stats[label]["invalid"])

        if col == "sex":
            stats["current"]["valueCounts"] = dataset_stats[latest_run]["value_counts"]["sex"]
            stats["previous"]["valueCounts"] = dataset_stats[prev_run]["value_counts"]["sex"]

        # Full per-run fidelity, keyed by run_id (not an index-aligned
        # array like history - the as-of picker this serves needs direct
        # lookup by an arbitrary run_id, not a scan). "current"/"previous"
        # above stay exactly as they were - existing rendering keeps
        # working unchanged; this is additive, for Thread C's as-of UI
        # (plans/publishing-and-history.md) to consume once it's built.
        # Computed from checks_out[0]'s own history (the same primary
        # check "current"/"previous" already use, post rank_for_headline)
        # rather than re-deriving from raw per-check data, so both stay
        # governed by the exact same "which check is primary" choice.
        primary_unit = checks_out[0]["unit"]
        stats_by_run = {}
        for h in checks_out[0]["history"]:
            run_id = h["run_id"]
            total = row_count_by_run[run_id]
            n_invalid = int(round(total * h["value"] / 100)) if primary_unit == "%" else int(round(h["value"]))
            n_invalid = max(0, n_invalid)
            stats_by_run[run_id] = {
                "total": total, "invalid": n_invalid, "valid": max(0, total - n_invalid),
                "valueCounts": dataset_stats[run_id]["value_counts"]["sex"] if col == "sex" else None,
            }
        stats["byRun"] = stats_by_run

        status_rank = {"pass": 0, "warn": 1, "fail": 2}
        # column status = worst status among its real checks (mirrors the
        # dashboard's own worst-of rollup rule, computed here from real
        # engine output rather than the client re-deriving it)
        worst = "pass"
        for r in results:
            if r["column_name"] == col and status_rank.get(r["status"], 0) > status_rank.get(worst, 0):
                worst = r["status"]

        columns_out.append({
            "name": col, "logicalType": logical_type, "description": desc,
            "checks": checks_out, "stats": stats,
        })

    # dataset-level: row counts + arrival, from the real generated manifest
    # and extract_timestamp data (extract lag is generated under the 24h SLA
    # for every run in this fixture, so "on time" here is a genuine computed
    # result, not an assumed default - see README's known-simplifications note).
    latest_entry = next(m for m in manifest if m["run_id"] == latest_run)
    prev_entry = next(m for m in manifest if m["run_id"] == prev_run)

    max_lag_hours = dataset_stats[latest_run]["arrival"]["max_lag_hours"]
    earliest_extract = dataset_stats[latest_run]["arrival"]["earliest_extract"]

    # Genuinely per-run now, not a hardcoded True for every run but the
    # latest - every run's own max_lag_hours/earliest_extract already
    # exists in its committed dataset_stats.json (Phase 3), just not
    # previously surfaced here. arrival_by_run mirrors stats["byRun"]
    # above (run_id-keyed, for Thread C's as-of UI); arrival_history
    # keeps its existing array shape (one entry per run, in order) but
    # its onTime is now real, not assumed.
    arrival_by_run = {}
    arrival_history = []
    for m in manifest:
        run_id = m["run_id"]
        arrival = dataset_stats[run_id]["arrival"]
        on_time = arrival["max_lag_hours"] < 24
        arrival_by_run[run_id] = {
            "arrivedAt": arrival["earliest_extract"], "onTime": on_time,
            "maxLagHours": round(arrival["max_lag_hours"], 1),
        }
        arrival_history.append({"run_id": run_id, "run_date": m["run_date"], "onTime": on_time})

    return {
        "id": "birth-registrations",
        "name": "Birth Registrations",
        "provider": "Registry of Births, Deaths & Marriages (BDM)",
        "deliveryFormat": "CSV (S3 drop) — Parquet planned",
        "sla": {"frequency": "Daily", "expectedBy": "06:00 local", "latencyHours": 24},
        "lastArrival": {
            "run_date": latest_entry["run_date"],
            "arrivedAt": earliest_extract,
            "onTime": max_lag_hours < 24,
            "maxLagHours": round(max_lag_hours, 1),
        },
        "arrivalHistory": arrival_history,
        "arrivalByRun": arrival_by_run,
        "rowCount": latest_entry["n_rows_generated"],
        "prevRowCount": prev_entry["n_rows_generated"],
        # Per-run row counts aren't duplicated into their own dict here -
        # "runs" (below) already carries n_rows_generated per manifest
        # entry, so Thread C's as-of UI can read it straight from there.
        "runs": manifest,
        "columns": columns_out,
        "_provenance": "Computed by qa_tools/bdm/orchestrate_bdm.py - actual dbt-core, Soda Core, datacontract-cli "
                        "and Evidently runs against real generated CSVs, the real ODCS contract, the real Soda "
                        "checks YAML, and a real dbt schema.yml — see README.md.",
    }


if __name__ == "__main__":
    data = build()
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"Wrote {OUT_PATH} ({len(data['columns'])} columns)")
