"""
Reshapes reports/results_cp.json (qa_tools/cp/orchestrate_cp.py's
output) into the exact JSON shape the QA reporting dashboard's drawer/chart
code expects - the Child Protection counterpart to build_dashboard_data.py.

Unlike Birth Registrations (one table -> one dataset), this produces a LIST
of 6 dataset objects, one per CP table, all sharing one collection
(Department for Child Protection and Family Support > Child Protection).

A check whose column_name is "(table)" - the 3 cross-table business rules
- is attached to a synthetic pseudo-column ("(table-level checks)"), since
none of those are about a single column; the 7 FK checks land on their own
FK column instead (e.g. cp_client_id) since "this column's values must
reference another table" genuinely is a statement about that column. This
reuses the dashboard's existing column-tile/drawer UI as-is rather than
adding a new "table-level checks" section - see plans/wider.md action 2
for why that trade-off was made.

row_count checks (from both Soda and datacontract-cli) are excluded from
every column entirely, same as build_dashboard_data.py's birth-
registrations equivalent - see the row_count skip below for why (a real
display bug, found by actually rendering this in a browser).

Output: reports/child_protection_dashboard.json, embedded into the HTML by
embed_dashboard_data.py as a second JS const (REAL_CP_DATA).
"""
from __future__ import annotations
import json
import os
from datetime import date, datetime

from qa_tools.cp import cp_common
from qa_tools.cp.dataset_stats import AGGREGATE_SPEC
from qa_tools.common.validate_check_lifecycle import collect_checks
from pipeline.cadence import classify_arrival, parse_cadence_from_contract
from pipeline.dashboard_check_labels import rank_for_headline, display_name

ROOT = os.path.join(os.path.dirname(__file__), "..")
RESULTS_PATH = os.path.join(ROOT, "reports", "results_cp.json")
OUT_PATH = os.path.join(ROOT, "reports", "child_protection_dashboard.json")
CONTRACT_PATH = os.path.join(ROOT, "contract", "child-protection-contract.yaml")


def _parse_extract_timestamp(s: str) -> datetime:
    return datetime.fromisoformat(s.replace(" ", "T"))

ENGINE_SHORT = {
    "dbt-core 1.12 + dbt-duckdb": "dbt-core",
    "Soda Core 3.5": "Soda Core",
    "datacontract-cli 1.2.0": "datacontract-cli",
    "Evidently 0.7": "Evidently AI",
}

BUSINESS_RULE_PSEUDO_COLUMN = "(table-level checks)"

TABLE_META = {
    "cp_clients": "One row per child with a Child Protection casework history, per quarterly snapshot extract.",
    "cp_notifications": "One row per notification (a report of concern about a child) - 1-4 per client, more for children with a higher-risk history.",
    "cp_investigations": "One row per investigation opened from an escalated notification.",
    "cp_placements": "One row per out-of-home-care placement (0-2 per client; not every client has one).",
    "cp_carers": "One row per approved (or in-approval) carer available for placements.",
    "cp_case_workers": "One row per case worker who may be assigned notifications or lead investigations.",
}

COLUMN_META = {
    "cp_clients": {
        "cp_client_id": ("string · varchar(20)", "This agency's unique client identifier — primary key of this table."),
        "given_name": ("string · varchar(200)", "Required."),
        "family_name": ("string · varchar(200)", "Required."),
        "date_of_birth": ("date", "Required."),
        "sex": ("string · varchar(1)", "Closed value set (M / F / X)."),
        "suburb": ("string · varchar(100)", "Required."),
        "postcode": ("string · varchar(4)", "Required."),
        "case_opened_date": ("date", "Required."),
        "case_status": ("string · varchar(10)", "Open or Closed — derived from investigation state, not independently random (see child_protection.py)."),
        "extract_timestamp": ("timestamp", "When this snapshot was extracted from the casework system."),
        BUSINESS_RULE_PSEUDO_COLUMN: ("table-level", "No cross-table business rule is anchored on this table today."),
    },
    "cp_notifications": {
        "notification_id": ("string · varchar(20)", "Primary key. dirty(amber/red) presets inject near-duplicates here."),
        "cp_client_id": ("string · varchar(20)", "Foreign key → cp_clients.cp_client_id."),
        "notification_date": ("date", "Required."),
        "source_type": ("string · varchar(30)", "Closed value set."),
        "concern_type": ("string · varchar(50)", "Closed value set — the traffic-light demo column for this collection, same role sex plays for Birth Registrations."),
        "risk_rating": ("string · varchar(10)", "Closed value set."),
        "assigned_worker_id": ("string · varchar(20)", "Foreign key → cp_case_workers.worker_id."),
        "outcome": ("string · varchar(30)", "Closed value set — 'Investigation opened' is what the escalation-completeness rule checks."),
        "extract_timestamp": ("timestamp", "When this snapshot was extracted from the casework system."),
        BUSINESS_RULE_PSEUDO_COLUMN: ("table-level", "Escalation completeness — see that check's own note for the real numbers."),
    },
    "cp_investigations": {
        "investigation_id": ("string · varchar(20)", "Primary key."),
        "notification_id": ("string · varchar(20)", "Foreign key → cp_notifications.notification_id."),
        "cp_client_id": ("string · varchar(20)", "Foreign key → cp_clients.cp_client_id."),
        "start_date": ("date", "Required."),
        "end_date": ("date", "Nullable — the investigation may still be open (~12% of them are, by generator design)."),
        "substantiated": ("string · varchar(20)", "Closed value set."),
        "lead_worker_id": ("string · varchar(20)", "Foreign key → cp_case_workers.worker_id."),
        "extract_timestamp": ("timestamp", "When this snapshot was extracted from the casework system."),
        BUSINESS_RULE_PSEUDO_COLUMN: ("table-level", "Closed-case investigation hygiene — see that check's own note for the real numbers."),
    },
    "cp_placements": {
        "placement_id": ("string · varchar(20)", "Primary key."),
        "cp_client_id": ("string · varchar(20)", "Foreign key → cp_clients.cp_client_id."),
        "placement_type": ("string · varchar(30)", "Closed value set."),
        "carer_id": ("string · varchar(20)", "Foreign key → cp_carers.carer_id."),
        "placement_start": ("date", "Required."),
        "placement_end": ("date", "Nullable — the placement may still be ongoing (~22% of them are, by generator design)."),
        "placement_suburb": ("string · varchar(100)", "Required."),
        "extract_timestamp": ("timestamp", "When this snapshot was extracted from the casework system."),
        BUSINESS_RULE_PSEUDO_COLUMN: ("table-level", "Placement/carer approval compliance — see that check's own note for the real numbers."),
    },
    "cp_carers": {
        "carer_id": ("string · varchar(20)", "Primary key."),
        "given_name": ("string · varchar(200)", "Required."),
        "family_name": ("string · varchar(200)", "Required."),
        "carer_type": ("string · varchar(20)", "Closed value set."),
        "approval_status": ("string · varchar(20)", "Closed value set — what the placement/carer approval compliance rule checks placements against."),
        "extract_timestamp": ("timestamp", "When this snapshot was extracted from the casework system."),
        BUSINESS_RULE_PSEUDO_COLUMN: ("table-level", "No cross-table business rule is anchored on this table today."),
    },
    "cp_case_workers": {
        "worker_id": ("string · varchar(20)", "Primary key."),
        "given_name": ("string · varchar(200)", "Required."),
        "family_name": ("string · varchar(200)", "Required."),
        "team_region": ("string · varchar(30)", "Closed value set."),
        "extract_timestamp": ("timestamp", "When this snapshot was extracted from the casework system."),
        BUSINESS_RULE_PSEUDO_COLUMN: ("table-level", "No cross-table business rule is anchored on this table today."),
    },
}


def build_one_table(table: str, results: list[dict], manifest: list[dict], dataset_stats: dict,
                     lifecycle_by_id: dict) -> dict:
    dataset_id = cp_common.TABLE_DATASET_ID[table]
    column_meta = COLUMN_META[table]
    all_columns = list(column_meta.keys())

    by_column: dict[str, dict[tuple, dict]] = {}
    for r in results:
        if r["check_name"] in ("row_count", "datacontract:row_count"):
            # excluded from the per-column checks, same as
            # build_dashboard_data.py's birth-registrations equivalent:
            # rowCount only ever feeds the dataset's own rowCount/
            # prevRowCount fields below, never a column tile. Necessary
            # here specifically (birth-registrations never hit this) -
            # this check's severity is "warning" not "error", so its real
            # fail_threshold is None, and the dashboard's checks_out
            # construction defaults a missing fail_threshold to 0 - which
            # would make checkStatus() (current > fail) read any healthy
            # positive row count as red. A real display bug, caught by
            # actually rendering this in a browser before calling Phase 3
            # done, not a fabricated concern.
            continue
        col = BUSINESS_RULE_PSEUDO_COLUMN if r["column_name"] == "(table)" else r["column_name"]
        if col not in column_meta:
            continue
        key = (r["engine"], r["check_name"])
        slot = by_column.setdefault(col, {}).setdefault(key, {
            "unit": r["unit"], "warn": r["warn_threshold"], "fail": r["fail_threshold"],
            "dimension": r["dimension"], "label": r.get("label"), "check_id": r["check_id"],
            "by_run": {}, "row_count_total": {}, "row_count_invalid": {}, "failing_sample_keys": {},
        })
        slot["by_run"][r["run_id"]] = r["metric_value"]
        slot["row_count_total"][r["run_id"]] = r["row_count_total"]
        slot["row_count_invalid"][r["run_id"]] = r["row_count_invalid"]
        slot["failing_sample_keys"][r["run_id"]] = r.get("failing_sample_keys") or []

    run_ids_in_order = [m["run_id"] for m in manifest]
    latest_run, prev_run = run_ids_in_order[-1], run_ids_in_order[-2]
    # run_date alone can't key a run uniquely (see build_dashboard_data.
    # py's identical comment) - byRun below keys on run_id via each
    # history entry's own "run_id" field.
    row_count_by_run = {m["run_id"]: m["row_counts"][table] for m in manifest}

    columns_out = []
    for col in all_columns:
        logical_type, desc = column_meta[col]
        checks_for_col = by_column.get(col, {})
        agg_spec = AGGREGATE_SPEC.get((table, col))

        checks_out = []
        for (engine, check_name), slot in checks_for_col.items():
            attach_aggregate = agg_spec is not None and check_name in agg_spec["check_names"]
            history = []
            for run_id in run_ids_in_order:
                if run_id in slot["by_run"]:
                    run_date = next(m["run_date"] for m in manifest if m["run_id"] == run_id)
                    aggregate_values = None
                    if attach_aggregate:
                        aggregate_values = dataset_stats[run_id]["check_aggregates"].get(f"{table}.{col}")
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
            lifecycle = lifecycle_by_id.get(slot["check_id"])
            checks_out.append({
                "check_id": slot["check_id"],
                "name": display_name(check_name, engine_short, slot["label"]),
                "dimension": slot["dimension"],
                "unit": slot["unit"],
                "warn": slot["warn"] if slot["warn"] is not None else 0,
                "fail": slot["fail"] if slot["fail"] is not None else 0,
                "current": slot["by_run"].get(latest_run, 0),
                "previous": slot["by_run"].get(prev_run, 0),
                "history": history,
                "note": f"Computed by {engine} against this run's real data — not a fabricated figure.",
                "retired_as_of": lifecycle.retired_as_of if lifecycle else None,
                "retired_reason": lifecycle.retired_reason if lifecycle else None,
                "description": lifecycle.description if lifecycle else None,
                "changelog": lifecycle.changelog if lifecycle else [],
            })

        if not checks_out:
            checks_out = [{
                "name": "No automated quality rule defined",
                "dimension": "", "unit": "count", "warn": 1, "fail": 1,
                "current": 0, "previous": 0,
                "history": [{"run_id": m["run_id"], "run_date": m["run_date"], "value": 0} for m in manifest],
                "note": "Neither the ODCS contract nor the Soda/dbt check files define a rule for this "
                        "column today — this is a real gap, not a hidden failure.",
            }]

        rank_for_headline(checks_out)

        total_latest = next(m for m in manifest if m["run_id"] == latest_run)["row_counts"][table]
        total_prev = next(m for m in manifest if m["run_id"] == prev_run)["row_counts"][table]

        stats = {
            "current": {"total": total_latest, "invalid": 0, "valid": total_latest, "valueCounts": None},
            "previous": {"total": total_prev, "invalid": 0, "valid": total_prev, "valueCounts": None},
        }
        if checks_out:
            primary_unit = checks_out[0]["unit"]
            for label, total, val in (("current", total_latest, checks_out[0]["current"]),
                                       ("previous", total_prev, checks_out[0]["previous"])):
                n_invalid = int(round(total * val / 100)) if primary_unit == "%" else int(round(val))
                stats[label]["invalid"] = max(0, n_invalid)
                stats[label]["valid"] = max(0, total - stats[label]["invalid"])

        if col == "concern_type":
            stats["current"]["valueCounts"] = dataset_stats[latest_run]["value_counts"]["concern_type"]
            stats["previous"]["valueCounts"] = dataset_stats[prev_run]["value_counts"]["concern_type"]

        # Full per-run fidelity, keyed by run_id - see build_dashboard_
        # data.py's identical comment on stats["byRun"] for the full
        # rationale (additive, current/previous unchanged, for Thread
        # C's as-of UI).
        primary_unit = checks_out[0]["unit"]
        stats_by_run = {}
        for h in checks_out[0]["history"]:
            run_id = h["run_id"]
            total = row_count_by_run[run_id]
            n_invalid = int(round(total * h["value"] / 100)) if primary_unit == "%" else int(round(h["value"]))
            n_invalid = max(0, n_invalid)
            stats_by_run[run_id] = {
                "total": total, "invalid": n_invalid, "valid": max(0, total - n_invalid),
                "valueCounts": dataset_stats[run_id]["value_counts"]["concern_type"] if col == "concern_type" else None,
            }
        stats["byRun"] = stats_by_run

        columns_out.append({
            "name": col, "logicalType": logical_type, "description": desc,
            "checks": checks_out, "stats": stats,
        })

    # dataset-level arrival: extract_timestamp vs. that run's own real,
    # computable cadence (Phase 5j, plans/qa-pipeline.md) - previously
    # "extracted within 24h of the snapshot date" (a relative check, no
    # real clock time); CP now has the same real "an agreed hour of the
    # day" cadence model BDM does, just quarterly with a much larger
    # latency tolerance - see pipeline/cadence.py.
    latest_entry = next(m for m in manifest if m["run_id"] == latest_run)
    prev_entry = next(m for m in manifest if m["run_id"] == prev_run)

    cadence = parse_cadence_from_contract(CONTRACT_PATH)

    max_lag_hours = dataset_stats[latest_run]["arrival"][table]["max_lag_hours"]
    earliest_extract = dataset_stats[latest_run]["arrival"][table]["earliest_extract"]
    latest_status = classify_arrival(
        cadence, date.fromisoformat(latest_entry["run_date"]), _parse_extract_timestamp(str(earliest_extract)))

    # Genuinely per-run now, not a hardcoded True for every run but the
    # latest - see build_dashboard_data.py's identical comment.
    # arrivalStatus (replacing the old onTime boolean) is a real 3-state
    # classify_arrival() result.
    arrival_by_run = {}
    arrival_history = []
    for m in manifest:
        run_id = m["run_id"]
        arrival = dataset_stats[run_id]["arrival"][table]
        status = classify_arrival(
            cadence, date.fromisoformat(m["run_date"]), _parse_extract_timestamp(str(arrival["earliest_extract"])))
        arrival_by_run[run_id] = {
            "arrivedAt": str(arrival["earliest_extract"]), "arrivalStatus": status,
            "maxLagHours": round(arrival["max_lag_hours"], 1),
        }
        arrival_history.append({"run_id": run_id, "run_date": m["run_date"], "arrivalStatus": status})

    return {
        "id": dataset_id,
        "name": cp_common.TABLE_DATASET_NAME[table],
        "provider": "Department for Child Protection and Family Support — Casework Management System",
        "deliveryFormat": "CSV (S3 drop)",
        "sla": {"cadence": cadence},
        "lastArrival": {
            "run_date": latest_entry["run_date"],
            "arrivedAt": str(earliest_extract),
            "arrivalStatus": latest_status,
            "maxLagHours": round(max_lag_hours, 1),
        },
        "arrivalHistory": arrival_history,
        "arrivalByRun": arrival_by_run,
        "rowCount": latest_entry["row_counts"][table],
        "prevRowCount": prev_entry["row_counts"][table],
        # Per-run row counts aren't duplicated into their own dict here -
        # "runs" (below) already carries row_counts[table] per manifest
        # entry, same as build_dashboard_data.py's identical comment.
        "runs": manifest,
        "columns": columns_out,
        "_provenance": f"Computed by qa_tools/cp/orchestrate_cp.py from real generated CSVs, the real "
                        f"child-protection-contract.yaml, the real child-protection-soda-checks.yml, a real "
                        f"dbt schema.yml, and real Evidently AI drift on concern_type — see README.md. "
                        f"({TABLE_META[table]})",
    }


def build() -> dict:
    with open(RESULTS_PATH) as f:
        payload = json.load(f)
    manifest = sorted(payload["runs"], key=lambda r: r["run_date"])
    results = payload["results"]
    dataset_stats = payload["dataset_stats"]

    # Same retirement lookup as build_dashboard_data.py's identical block -
    # computed once here, not once per table.
    lifecycle_by_id = {c.check_id: c for c in collect_checks(None)}

    by_table = {t: [r for r in results if r["dataset_id"] == cp_common.TABLE_DATASET_ID[t]] for t in cp_common.TABLES}
    datasets = [build_one_table(t, by_table[t], manifest, dataset_stats, lifecycle_by_id) for t in cp_common.TABLES]
    return {"datasets": datasets}


if __name__ == "__main__":
    data = build()
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"Wrote {OUT_PATH} ({len(data['datasets'])} datasets)")
