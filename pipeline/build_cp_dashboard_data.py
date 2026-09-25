"""
Reshapes reports/results_cp.json (qa_tools/cp/orchestrate_cp.py's
output) into the exact JSON shape the QA reporting dashboard's drawer/chart
code expects - the Child Protection counterpart to build_dashboard_data.py.

Unlike Birth Registrations (one table -> one dataset), this produces a LIST
of 6 dataset objects, one per CP table, all sharing one collection
(Department for Child Protection and Family Support > Child Protection).

A check whose column_name is "(table)" - the 3 cross-table business rules
- is attached to a synthetic pseudo-column ("Table-level checks"), since
none of those are about a single column; the 7 FK checks land on their own
FK column instead (e.g. cp_client_id) since "this column's values must
reference another table" genuinely is a statement about that column. This
reuses the dashboard's existing column-tile/drawer UI as-is rather than
adding a new "table-level checks" section - see plans/dashboard.md #1
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

from qa_tools.common import hierarchy
from qa_tools.cp import cp_common
from qa_tools.cp.dataset_stats import AGGREGATE_SPEC
from qa_tools.common.validate_check_lifecycle import collect_checks
from pipeline.cadence import classify_arrival, parse_cadence_from_contract
from qa_tools.common import asset_time
from pipeline.dashboard_check_labels import rank_for_headline, display_name, dashboard_status, tool_ref, url_key

ROOT = os.path.join(os.path.dirname(__file__), "..")
RESULTS_PATH = os.path.join(ROOT, "reports", "results_cp.json")
OUT_PATH = os.path.join(ROOT, "reports", "child_protection_dashboard.json")
CONTRACT_PATH = os.path.join(ROOT, "contract", "child-protection-contract.yaml")


def _parse_extract_timestamp(s: str) -> datetime:
    """One committed arrival instant. Delegates to asset_time so a value
    stored without an offset fails loudly here rather than being read as
    UTC by whichever caller got to it first (REQ-PIPE-048)."""
    return asset_time.parse_instant(s, "arrival.earliest_extract in committed qa_results/")


def _run_date(entry: dict) -> str:
    """One manifest entry's receipt DATE, as a string.

    The manifest carries a receipt INSTANT since REQ-GEN-042 - the
    generator's own `received_at` - and the two axes it separates
    (which period a supply is for, when it actually turned up) are the
    point of that change. Everything below wants a date, for a cadence
    cycle or a row in a supply-history table, so it is derived here in
    one place rather than at eleven call sites.

    `run_date` survives as the DASHBOARD-FACING name deliberately. The
    vocabulary change is the generator's; renaming a presentation field
    the template, the JS tests and the e2e suite all key on would be
    churn this requirement did not ask for, and `run_date` is not one
    of the names it retires.
    """
    return asset_time.local_date(entry["received_at"]).isoformat()

ENGINE_SHORT = {
    "dbt-core 1.12 + dbt-duckdb": "dbt-core",
    "Soda Core 3.5": "Soda Core",
    "datacontract-cli 1.2.0": "datacontract-cli",
    "Evidently 0.7": "Evidently AI",
}

BUSINESS_RULE_PSEUDO_COLUMN = "Table-level checks"

# Row-count checks get their own home rather than sharing the one above
# (Keith, 2026-09-20): "is this supply the right size" is a different
# question from "do these tables agree with each other".
SUPPLY_LEVEL_PSEUDO_COLUMN = "Supply-level checks"
# The one definition of both slugs lives in the Birth Registrations
# builder; imported rather than restated so the two files cannot
# drift into disagreeing about what a URL segment says.
from pipeline.build_dashboard_data import COLUMN_SCOPE_KEY  # noqa: E402
SUPPLY_LEVEL_META = (
    "supply-level",
    "Checks on the supply as a whole rather than on any one column - whether it "
    "arrived the right size, and whether it is current.")
_SUPPLY_LEVEL_CHECK_NAMES = {"row_count", "row_count[all]", "datacontract:row_count"}

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
        SUPPLY_LEVEL_PSEUDO_COLUMN: SUPPLY_LEVEL_META,
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
        SUPPLY_LEVEL_PSEUDO_COLUMN: SUPPLY_LEVEL_META,
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
        SUPPLY_LEVEL_PSEUDO_COLUMN: SUPPLY_LEVEL_META,
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
        SUPPLY_LEVEL_PSEUDO_COLUMN: SUPPLY_LEVEL_META,
    },
    "cp_carers": {
        "carer_id": ("string · varchar(20)", "Primary key."),
        "given_name": ("string · varchar(200)", "Required."),
        "family_name": ("string · varchar(200)", "Required."),
        "carer_type": ("string · varchar(20)", "Closed value set."),
        "approval_status": ("string · varchar(20)", "Closed value set — what the placement/carer approval compliance rule checks placements against."),
        "extract_timestamp": ("timestamp", "When this snapshot was extracted from the casework system."),
        BUSINESS_RULE_PSEUDO_COLUMN: ("table-level", "No cross-table business rule is anchored on this table today."),
        SUPPLY_LEVEL_PSEUDO_COLUMN: SUPPLY_LEVEL_META,
    },
    "cp_case_workers": {
        "worker_id": ("string · varchar(20)", "Primary key."),
        "given_name": ("string · varchar(200)", "Required."),
        "family_name": ("string · varchar(200)", "Required."),
        "team_region": ("string · varchar(30)", "Closed value set."),
        "extract_timestamp": ("timestamp", "When this snapshot was extracted from the casework system."),
        BUSINESS_RULE_PSEUDO_COLUMN: ("table-level", "No cross-table business rule is anchored on this table today."),
        SUPPLY_LEVEL_PSEUDO_COLUMN: SUPPLY_LEVEL_META,
    },
}


def build_one_table(table: str, results: list[dict], manifest: list[dict], dataset_stats: dict,
                     lifecycle_by_id: dict) -> dict:
    dataset_id = hierarchy.dataset_for_table(table).dataset_id
    column_meta = COLUMN_META[table]
    all_columns = list(column_meta.keys())

    by_column: dict[str, dict[tuple, dict]] = {}
    for r in results:
        # Row-count checks used to be skipped outright here, and the
        # reason was real at the time: this check's severity is "warning"
        # so its fail_threshold is None, checks_out defaulted a missing
        # one to 0, and checkStatus() (current > fail) would read any
        # healthy positive row count as RED. Item 74 fixed that at the
        # source - checkStatus() now returns the tool's own
        # current_status first and only falls back to threshold maths -
        # so the workaround outlived its bug, and the cost of keeping it
        # was 12 real checks rendering nowhere
        # (REQ-DASH-032).
        if r["column_name"] == "(table)":
            col = (SUPPLY_LEVEL_PSEUDO_COLUMN if r["check_name"] in _SUPPLY_LEVEL_CHECK_NAMES
                   else BUSINESS_RULE_PSEUDO_COLUMN)
        else:
            col = r["column_name"]
        if col not in column_meta:
            continue
        key = (r["engine"], r["check_name"])
        slot = by_column.setdefault(col, {}).setdefault(key, {
            "unit": r["unit"], "warn": r["warn_threshold"], "fail": r["fail_threshold"],
            "dimension": r["dimension"], "label": r.get("label"), "check_id": r["check_id"],
            "by_run": {}, "row_count_total": {}, "row_count_invalid": {}, "failing_sample_keys": {},
            "status_by_run": {},
        })
        slot["by_run"][r["run_id"]] = r["metric_value"]
        # item 74 Bug A: the tool's own verdict, carried through rather
        # than dropped here and re-derived from thresholds downstream.
        slot["status_by_run"][r["run_id"]] = dashboard_status(r.get("status"))
        slot["row_count_total"][r["run_id"]] = r["row_count_total"]
        slot["row_count_invalid"][r["run_id"]] = r["row_count_invalid"]
        slot["failing_sample_keys"][r["run_id"]] = r.get("failing_sample_keys") or []

    run_ids_in_order = [m["run_id"] for m in manifest]
    latest_run, prev_run = run_ids_in_order[-1], run_ids_in_order[-2]
    # run_date alone can't key a run uniquely (see build_dashboard_data.
    # py's identical comment) - byRun below keys on run_id via each
    # history entry's own "run_id" field.
    row_count_by_run = {run_id: st["row_counts"][table] for run_id, st in dataset_stats.items()}

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
                    run_date = next(_run_date(m) for m in manifest if m["run_id"] == run_id)
                    aggregate_values = None
                    if attach_aggregate:
                        aggregate_values = dataset_stats[run_id]["check_aggregates"].get(f"{table}.{col}")
                    history.append({
                        "run_id": run_id, "run_date": run_date, "value": slot["by_run"][run_id],
                        "row_count_total": slot["row_count_total"].get(run_id),
                        "row_count_invalid": slot["row_count_invalid"].get(run_id),
                        "failing_sample_keys": slot["failing_sample_keys"].get(run_id) or [],
                        "aggregate_values": aggregate_values,
                        "status": slot["status_by_run"].get(run_id),
                    })
            if not history:
                continue
            engine_short = ENGINE_SHORT.get(engine, engine)
            lifecycle = lifecycle_by_id.get(slot["check_id"])
            checks_out.append({
                "check_id": slot["check_id"],
                # A hand-authored `name` in the check's own metadata wins
                # over the derived label (REQ-DASH-026).
                # The field already existed and was parsed but rendered
                # nowhere - 16 checks carried one, and they are exactly
                # the headings a reader wants: "Registered on or after
                # birth", "Carer approval compliance".
                "name": (lifecycle.name if lifecycle and lifecycle.name
                         else display_name(check_name, engine_short, slot["label"])),
                # The URL-facing identity, stable across heading rewrites
                # (REQ-DASH-026). Never `name`.
                "key": url_key(slot["check_id"]),
                # REQ-DASH-026: the terse "dbt:not_null" line under
                # the headline. Same string as `key` above, tool
                # moved to the front - deliberately, so the card and
                # the address bar agree.
                "tool_ref": tool_ref(slot["check_id"]),
                "dimension": slot["dimension"],
                "unit": slot["unit"],
                # item 74 Bug A: None stays None - it means "this check has
                # no bound of that kind" (e.g. rowCount's two-sided
                # mustBeBetween range), NOT "zero tolerance". Substituting
                # 0 here is what fabricated a red on every run.
                "warn": slot["warn"],
                "fail": slot["fail"],
                "current": slot["by_run"].get(latest_run, 0),
                "current_status": slot["status_by_run"].get(latest_run),
                "previous": slot["by_run"].get(prev_run, 0),
                "history": history,
                "note": f"Computed by {engine} against this run's real data — not a fabricated figure.",
                "retired_as_of": lifecycle.retired_as_of if lifecycle else None,
                "retired_reason": lifecycle.retired_reason if lifecycle else None,
                "description": lifecycle.description if lifecycle else None,
                # REQ-QAC-024. `description` is the plain-English WHAT;
                # this is the plain-English SO-WHAT - what a failure most
                # likely means happened upstream.
                #
                # `technical_note` is deliberately NOT here and must not
                # be added. It is the one authored field written for
                # contributors rather than viewers ("standing facts a
                # contributor needs and a viewer must not see"), and this
                # dict is published to a public site. Its absence is the
                # requirement being met, not an oversight.
                "failure_indicates": lifecycle.failure_indicates if lifecycle else None,
                "changelog": lifecycle.changelog if lifecycle else [],
            })

        if not checks_out:
            checks_out = [{
                # A REAL KEY, because everything downstream assumes one
                # (plans/post-build-review.md #5 and #12). Without it the
                # scope-section renderer wrote data-check="undefined",
                # the re-lookup matched nothing, and dereferencing the
                # result threw - taking out the rest of renderDataset()
                # AND, because navigate() renders before it pushes
                # history, the navigation itself. The check panel was
                # also un-deep-linkable and un-closable with Back, for
                # the same missing field.
                #
                # Unique within its column, which is the scope the
                # /check/<key> route resolves in - and this placeholder
                # is by definition the only check on its column.
                "key": "no_rule_defined",
                "name": "No automated quality rule defined",
                # This check is synthesized HERE, not produced by any real
                # tool - so it has to state its own status explicitly
                # (item 74). Without it, it would be the only thing left
                # in the whole app relying on the warn/fail fallback, and
                # a fallback with exactly one synthetic caller is a trap,
                # not a safety net: it keeps three status implementations
                # alive to serve data this file makes up.
                #
                # `inactive`, NOT green (post-build-review #4, Keith's
                # own direction: "a grey, as in a disabled kind of grey
                # colour - kind of speaks to it's inactive"). The old
                # comment here argued green was truthful BECAUSE the gap
                # was labelled in `note` - and `note` renders in exactly
                # one place, the check panel. So at every level a reader
                # actually looks, an unchecked column read as a healthy
                # one, and a table-scope placeholder rolled a whole
                # section to green on its own. Green is a VERDICT, and
                # nothing was checked here.
                "dimension": "", "unit": "count", "warn": None, "fail": None,
                "current": 0, "current_status": "inactive", "previous": 0,
                "history": [{"run_id": m["run_id"], "run_date": _run_date(m), "value": 0,
                             "status": "inactive"} for m in manifest],
                "note": "Neither the ODCS contract nor the Soda/dbt check files define a rule for this "
                        "column today — this is a real gap, not a hidden failure.",
            }]

        rank_for_headline(checks_out)

        total_latest = dataset_stats[latest_run]["row_counts"][table]
        total_prev = dataset_stats[prev_run]["row_counts"][table]

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
            # REQ-DASH-033 - see build_dashboard_data.py's own
            # COLUMN_SCOPE_KEY for why a column has a key distinct from
            # its name, and why only these two differ.
            "key": COLUMN_SCOPE_KEY.get(col, col),
            "scope": COLUMN_SCOPE_KEY.get(col),
            "checks": checks_out, "stats": stats,
        })

    # dataset-level arrival: extract_timestamp vs. that run's own real,
    # computable cadence (Phase 5j, plans/qa-pipeline.md) - previously
    # "extracted within 24h of the snapshot date" (a relative check, no
    # real clock time); CP now has the same real "an agreed hour of the
    # day" cadence model BDM does, just quarterly with a much larger
    # latency tolerance - see pipeline/cadence.py.
    latest_entry = next(m for m in manifest if m["run_id"] == latest_run)

    # Per DATASET, not per contract (REQ-PIPE-049). `table` is this
    # dataset's own element in a contract that holds six, so its own
    # expectedTime and latency win over the contract-wide defaults.
    # Before this the element was parsed and discarded, so all six
    # inherited cp_clients' values whether or not they had their own.
    cadence = parse_cadence_from_contract(CONTRACT_PATH, element=table)
    earliest_extract = dataset_stats[latest_run]["arrival"][table]["earliest_extract"]
    latest_status = classify_arrival(
        cadence, date.fromisoformat(_run_date(latest_entry)), _parse_extract_timestamp(str(earliest_extract)))

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
            cadence, date.fromisoformat(_run_date(m)), _parse_extract_timestamp(str(arrival["earliest_extract"])))
        arrival_by_run[run_id] = {
            "arrivedAt": str(arrival["earliest_extract"]), "arrivalStatus": status,
        }
        arrival_history.append({"run_id": run_id, "run_date": _run_date(m), "arrivalStatus": status})

    return {
        "id": dataset_id,
        "name": hierarchy.dataset_for_table(table).dataset_name,
        "provider": "Department for Child Protection and Family Support — Casework Management System",
        "deliveryFormat": "CSV (S3 drop)",
        "sla": {"cadence": cadence},
        "lastArrival": {
            "run_date": _run_date(latest_entry),
            "arrivedAt": str(earliest_extract),
            "arrivalStatus": latest_status,
        },
        "arrivalHistory": arrival_history,
        "arrivalByRun": arrival_by_run,
        "rowCount": dataset_stats[latest_run]["row_counts"][table],
        "prevRowCount": dataset_stats[prev_run]["row_counts"][table],
        # Per-run row counts aren't duplicated into their own dict here -
        # "runs" (below) already carries each arrival record per
        # entry, same as build_dashboard_data.py's identical comment.
        # Each run as the PAGE sees it: the manifest entry plus a
        # derived `run_date`. The manifest itself carries a receipt
        # INSTANT since REQ-GEN-042 (`received_at`), and the template,
        # the JS tests and the e2e suite all key supply history on a
        # date - so the date is derived once, here, at the last
        # transform before the page.
        #
        # Spread-then-add rather than a hand-listed copy, deliberately:
        # a hand-maintained allowlist silently drops every field added
        # later, which is CLAUDE.md's own standing lesson from item 74.
        "runs": [{**m, "run_date": _run_date(m)} for m in manifest],
        "columns": columns_out,
        "_provenance": f"Computed by qa_tools/cp/orchestrate_cp.py from real generated CSVs, the real "
                        f"child-protection-contract.yaml, the real child-protection-soda-checks.yml, a real "
                        f"dbt schema.yml, and real Evidently AI drift on concern_type — see README.md. "
                        f"({TABLE_META[table]})",
    }


def build() -> dict:
    with open(RESULTS_PATH) as f:
        payload = json.load(f)
    manifest = sorted(payload["runs"], key=_run_date)
    results = payload["results"]
    dataset_stats = payload["dataset_stats"]

    # Same retirement lookup as build_dashboard_data.py's identical block -
    # computed once here, not once per table.
    lifecycle_by_id = {c.check_id: c for c in collect_checks(None)}

    by_table = {t: [r for r in results if r["dataset_id"] == hierarchy.dataset_for_table(t).dataset_id]
                for t in cp_common.TABLES}
    datasets = [build_one_table(t, by_table[t], manifest, dataset_stats, lifecycle_by_id) for t in cp_common.TABLES]
    return {"datasets": datasets}


if __name__ == "__main__":
    data = build()
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"Wrote {OUT_PATH} ({len(data['datasets'])} datasets)")
