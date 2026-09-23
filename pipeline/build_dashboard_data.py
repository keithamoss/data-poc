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
path's 630), so the merge logic is gone too. See plans/wider.md #3
for the full history.

Output: reports/birth_registrations_dashboard.json, embedded into the HTML
by embed_dashboard_data.py as a JS const.
"""
from __future__ import annotations
import json
import os
from datetime import date, datetime

from qa_tools.bdm.dataset_stats import AGGREGATE_SPEC
from qa_tools.common.validate_check_lifecycle import collect_checks
from pipeline.cadence import classify_arrival, parse_cadence_from_contract
from qa_tools.common import asset_time
from qa_tools.common import hierarchy
from pipeline.dashboard_check_labels import rank_for_headline, display_name, dashboard_status, tool_ref, url_key

ROOT = os.path.join(os.path.dirname(__file__), "..")
REAL_RESULTS_PATH = os.path.join(ROOT, "reports", "results_bdm.json")
OUT_PATH = os.path.join(ROOT, "reports", "birth_registrations_dashboard.json")
CONTRACT_PATH = os.path.join(ROOT, "contract", "bdm-birth-registrations-contract.yaml")


def _parse_extract_timestamp(s: str) -> datetime:
    """One committed arrival instant. Delegates to asset_time so a value
    stored without an offset fails loudly here rather than being read as
    UTC by whichever caller got to it first (REQ-PIPE-048)."""
    return asset_time.parse_instant(s, "arrival.earliest_extract in committed qa_results/")

ENGINE_SHORT = {
    # Same short-name convention as build_cp_dashboard_data.py's own
    # ENGINE_SHORT for these 4 tags. No "(real)" suffix on the tag itself
    # any more - there's nothing left to distinguish it from since
    # engines/*.py was removed (see plans/qa-pipeline.md #84's follow-up).
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

# Two pseudo-columns, so a check that belongs to the whole table rather
# than to any one column still has somewhere to live. Before these, the
# builder dropped every "(table)" result on the floor - 13 real checks
# across both datasets, carrying prose nobody could read
# (REQ-DASH-032).
#
# Deliberately TWO rather than one (Keith, 2026-09-20). "Is this supply
# the right size and current enough" is a different question from "do
# these tables agree with each other", and lumping them together made a
# grab-bag. Child Protection already had the second one under this exact
# name, so that name is reused rather than invented.
SUPPLY_LEVEL_PSEUDO_COLUMN = "Supply-level checks"
TABLE_LEVEL_PSEUDO_COLUMN = "Table-level checks"

# REQ-DASH-033. These two stopped being columns-in-disguise and became
# real sections of the dataset page, so they need a name a person reads
# (above) and a slug a URL carries (here) - which a bracketed
# "(supply-level checks)" was doing badly as both: it rendered as a
# column called something no column is called, and it encoded into
# %28supply-level%20checks%29 in the address bar.
#
# Every column carries a `key` now, equal to its own name for a real
# one, so nothing about real column URLs changes. Only these two differ
# from their display name.
COLUMN_SCOPE_KEY = {
    SUPPLY_LEVEL_PSEUDO_COLUMN: "supply",
    TABLE_LEVEL_PSEUDO_COLUMN: "table",
}

COLUMN_META[SUPPLY_LEVEL_PSEUDO_COLUMN] = (
    "supply-level",
    "Checks on the supply as a whole rather than on any one column - whether it "
    "arrived the right size, and whether it is current.")
COLUMN_META[TABLE_LEVEL_PSEUDO_COLUMN] = (
    "table-level",
    "Rules that span the whole table rather than any one column.")

# datacontract-cli and Soda each spell the row-count check differently.
_SUPPLY_LEVEL_CHECK_NAMES = {"row_count", "row_count[all]", "datacontract:row_count"}
_PSEUDO_COLUMNS = (SUPPLY_LEVEL_PSEUDO_COLUMN, TABLE_LEVEL_PSEUDO_COLUMN)


def _pseudo_column_for(check_name: str) -> str:
    return (SUPPLY_LEVEL_PSEUDO_COLUMN if check_name in _SUPPLY_LEVEL_CHECK_NAMES
            else TABLE_LEVEL_PSEUDO_COLUMN)


ALL_COLUMNS = list(COLUMN_META.keys())


def build() -> dict:
    with open(REAL_RESULTS_PATH) as f:
        payload = json.load(f)
    manifest = sorted(payload["runs"], key=lambda r: r["run_date"])
    results = payload["results"]
    dataset_stats = payload["dataset_stats"]

    # check_id -> CheckMetadata, from every real check definition (active +
    # retired) across all 4 tools x both datasets - Phase 5b's retired-
    # checks toggle (plans/publishing-and-history.md Thread D). Static
    # config-file parsing only (schema.yml/soda YAML/contract YAML/
    # evidently_check_lifecycle*.py), no live data/DuckDB access, so this
    # is safe for CI same as any other "read committed history" path.
    lifecycle_by_id = {c.check_id: c for c in collect_checks(None)}

    # column_name -> (engine, check_name) -> {unit, warn, fail, by_run_id: {run_id: value}}
    by_column: dict[str, dict[tuple, dict]] = {}
    for r in results:
        col = r["column_name"]
        if col == "(table)":
            col = _pseudo_column_for(r["check_name"])
        # Keyed on check_id, NOT (engine, check_name). Those two are a
        # DISPLAY name, and two different checks can genuinely share one:
        # datacontract-cli reports every `type: sql` rule as
        # "datacontract:custom_sql", so date_of_birth's range check and
        # its freshness check collided here and one silently swallowed
        # the other - while both kept writing into the survivor's own
        # by_run values, which disagree on 166 of the 352 committed runs.
        # check_id is the identity this system already guarantees unique
        # (REQ-QAC-023's grammar and tail-uniqueness gates).
        key = r["check_id"]
        slot = by_column.setdefault(col, {}).setdefault(key, {
            "unit": r["unit"], "warn": r["warn_threshold"], "fail": r["fail_threshold"],
            "dimension": r["dimension"], "label": r.get("label"), "check_id": r["check_id"],
            "engine": r["engine"], "check_name": r["check_name"],
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
        for slot in checks_for_col.values():
            engine, check_name = slot["engine"], slot["check_name"]
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

        if not checks_out and col in _PSEUDO_COLUMNS:
            # A real column with no checks says so honestly below. A
            # pseudo-column with none simply does not exist for this
            # dataset, and an empty tile would be noise.
            continue
        if not checks_out:
            # honest placeholder - no rule anywhere covers this column today
            checks_out = [{
                "name": "No automated quality rule defined",
                # This check is synthesized HERE, not produced by any real
                # tool - so it has to state its own status explicitly
                # (item 74). Without it, it would be the only thing left
                # in the whole app relying on the warn/fail fallback, and
                # a fallback with exactly one synthetic caller is a trap,
                # not a safety net: it keeps three status implementations
                # alive to serve data this file makes up. "No rule
                # defined" is a real gap, honestly labelled in `note` -
                # it is not a failure, so green is the truthful answer.
                "dimension": "", "unit": "count", "warn": None, "fail": None,
                "current": 0, "current_status": "green", "previous": 0,
                "history": [{"run_id": m["run_id"], "run_date": m["run_date"], "value": 0,
                             "status": "green"} for m in manifest],
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

        # (Removed 2026-09-19, plans/qa-pipeline.md item 74's follow-up: a
        # `worst` column rollup used to be computed here, from each real
        # engine's own `status` - the right idea - and then never used.
        # `columns_out.append()` below never carried it, and nothing else
        # in this file read it. Ruff couldn't flag it either: `worst` is
        # read inside its own accumulating loop, so F841 never fires. The
        # dashboard does this rollup client-side instead, because it has
        # to - the as-of picker re-rolls status for an arbitrary date the
        # viewer picks in the browser, which no build-time value can
        # answer. Deleted rather than wired up for that reason.)

        columns_out.append({
            "name": col, "logicalType": logical_type, "description": desc,
            # The URL-facing identity of a column, same split `key` vs
            # `name` REQ-DASH-026 gave a check. Equal to the name for a
            # real column, so no real column URL moves.
            "key": COLUMN_SCOPE_KEY.get(col, col),
            # Present only on the two section pseudo-columns, and what
            # the dataset view keys its own split on - never a string
            # match against a display name, which is what the bracketed
            # names were being used for before.
            "scope": COLUMN_SCOPE_KEY.get(col),
            "checks": checks_out, "stats": stats,
        })

    # dataset-level: row counts + arrival, from the real generated manifest
    # and extract_timestamp data.
    latest_entry = next(m for m in manifest if m["run_id"] == latest_run)
    prev_entry = next(m for m in manifest if m["run_id"] == prev_run)

    # Named explicitly even though this contract holds one dataset -
    # its slaProperties carry `element: birth_registrations`, and since
    # REQ-PIPE-049 that means something rather than being ignored.
    cadence = parse_cadence_from_contract(CONTRACT_PATH, element=hierarchy.dataset("birth-registrations").table)

    max_lag_hours = dataset_stats[latest_run]["arrival"]["max_lag_hours"]
    earliest_extract = dataset_stats[latest_run]["arrival"]["earliest_extract"]
    latest_status = classify_arrival(
        cadence, date.fromisoformat(latest_entry["run_date"]), _parse_extract_timestamp(earliest_extract))

    # Genuinely per-run now, not a hardcoded True for every run but the
    # latest - every run's own max_lag_hours/earliest_extract already
    # exists in its committed dataset_stats.json (Phase 3), just not
    # previously surfaced here. arrival_by_run mirrors stats["byRun"]
    # above (run_id-keyed, for Thread C's as-of UI); arrival_history
    # keeps its existing array shape (one entry per run, in order).
    # arrivalStatus (Phase 5j, replacing the old onTime boolean) is a
    # real 3-state classify_arrival() result against this run's own
    # cadence-derived expected moment - see pipeline/cadence.py.
    arrival_by_run = {}
    arrival_history = []
    for m in manifest:
        run_id = m["run_id"]
        arrival = dataset_stats[run_id]["arrival"]
        status = classify_arrival(
            cadence, date.fromisoformat(m["run_date"]), _parse_extract_timestamp(arrival["earliest_extract"]))
        arrival_by_run[run_id] = {
            "arrivedAt": arrival["earliest_extract"], "arrivalStatus": status,
            "maxLagHours": round(arrival["max_lag_hours"], 1),
        }
        arrival_history.append({"run_id": run_id, "run_date": m["run_date"], "arrivalStatus": status})

    return {
        "id": "birth-registrations",
        "name": "Birth Registrations",
        "provider": "Registry of Births, Deaths & Marriages (BDM)",
        "deliveryFormat": "CSV (S3 drop) — Parquet planned",
        "sla": {"cadence": cadence},
        "lastArrival": {
            "run_date": latest_entry["run_date"],
            "arrivedAt": earliest_extract,
            "arrivalStatus": latest_status,
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
