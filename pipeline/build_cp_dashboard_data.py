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
from datetime import datetime

from pipeline import (acknowledgements, closed_slots, file_check_panel, recorded_arrival,
                      red_promoted, slot_timeline)
from qa_tools.common import amber_setting, census, drift_reference
from qa_tools.common import hierarchy, promotion_state, qa_store
from qa_tools.cp import cp_common
from qa_tools.cp.dataset_stats import AGGREGATE_SPEC
from qa_tools.common.validate_check_lifecycle import collect_checks
from pipeline.cadence import parse_cadence_from_contract
from qa_tools.common import asset_time
from pipeline.dashboard_check_labels import rank_for_headline, display_name, dashboard_status, pooled_url_key, tool_ref, url_key

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
# `evidently:row_count_growth` joined these 2026-09-29 (REQ-QAC-108
# criterion 1). "Did this supply arrive the right size" is the same
# question the three absolute row-count checks ask; this one asks it
# RELATIVE to the last promoted supply, which is the only version of it
# that keeps working on a table whose size legitimately changes.
_SUPPLY_LEVEL_CHECK_NAMES = {"row_count", "row_count[all]", "datacontract:row_count",
                              "evidently:row_count_growth"}

TABLE_META = {
    "cp_clients": "One row per child with a Child Protection casework history, per quarterly snapshot extract.",
    "cp_notifications": "One row per notification (a report of concern about a child) - 1-4 per client, more for children with a higher-risk history.",
    "cp_investigations": "One row per investigation opened from an escalated notification.",
    "cp_placements": "One row per out-of-home-care placement (0-2 per client; not every client has one).",
    "cp_carers": "One row per approved (or in-approval) carer available for placements.",
    "cp_case_workers": "One row per case worker who may be assigned notifications or lead investigations.",
}

# REQ-QAC-037 criteria 6 and 7. A cross-table check gets a pseudo-column
# of its own, the same mechanism REQ-DASH-033 gave supply-level and
# table-level checks - a `scope` makes the template render it as a
# SECTION rather than among the real columns, and being in `columns` at
# all is what folds its verdict into the dataset's status.
#
# WHY IT CANNOT JUST KEEP ITS OWN COLUMN NAME: a referential check
# declared on cp_notifications reads cp_client_id, which is a column of
# cp_notifications and not of cp_carers. Attaching the result to carers
# under that name would invent a cp_client_id column on a table that
# has none.
CROSS_TABLE_PSEUDO_COLUMN = "Cross-table checks"
CROSS_TABLE_META = (
    "cross-table",
    "Checks about the relationship between this table and another. A failure "
    "here is a disagreement between tables rather than a fault in either one "
    "alone, so it counts against every table the check reads.")

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


COLUMN_SCOPE_KEY[CROSS_TABLE_PSEUDO_COLUMN] = "cross-table"
for _table_meta in COLUMN_META.values():
    _table_meta[CROSS_TABLE_PSEUDO_COLUMN] = CROSS_TABLE_META


def _disambiguate_pooled_keys(cards: list[dict]) -> None:
    """Where two cards in one section share a URL key, prefix each with
    the dataset that DECLARES it (post-build-review #88).

    A pooled section gathers checks declared by several datasets, so
    `cp_client_id.relationships_dbt` arrives once from cp-investigations
    and once from cp-placements - two checks, one key, and the template
    resolves a key to its first match. Only colliding keys change, so
    every URL that was unambiguous yesterday still works today.
    """
    from qa_tools.common.check_id import try_parse

    counts: dict[str, int] = {}
    for card in cards:
        counts[card["key"]] = counts.get(card["key"], 0) + 1
    for card in cards:
        if counts[card["key"]] > 1:
            parsed = try_parse(card["check_id"])
            if parsed:
                card["key"] = f"{parsed.dataset}.{card['key']}"


def _cross_table_check_ids() -> set[str]:
    """Every check that reads a table other than its own.

    Read from the check definitions rather than from the results, so a
    check that happens to be absent from one run is still known to be
    cross-table - the alternative would move a check between sections
    depending on whether it ran.
    """
    from qa_tools.common import tables_read

    return set(tables_read.declared_by_check_id(collect_checks(None)))


def _value_counts(dataset_stats: dict, run_id: str):
    """concern_type's recorded distribution for a run, or None where that
    run could not read cp_notifications (REQ-PIPE-105)."""
    return ((dataset_stats.get(run_id) or {}).get("value_counts") or {}).get("concern_type")


def _not_evaluated_reason(record: dict) -> str | None:
    """Why a record's check could not be evaluated, or None for a real
    verdict. Read from the reason each pseudo-tool writes -
    `unrunnable_reason` (REQ-PIPE-105 criterion 13) and `held_reason`
    (REQ-PIPE-078 criterion 10) - so a real tool's result can never be
    mistaken for one."""
    return (record.get("unrunnable_reason") or record.get("held_reason")
            # REQ-QAC-108 criterion 9: red, not evaluated, under Evidently.
            or (record.get("reference_reason") if record.get("reference_not_evaluated")
                else None)
            or None)


def own_runs(manifest: list[dict], table: str) -> list[dict]:
    """The runs that are FOR this table (REQ-PIPE-105).

    One file is one arrival and a run id is its staged table's spelling,
    so a Child Protection delivery is six runs and each belongs to one
    table. A dataset's page shows its own arrivals - which is also what
    its arrival history always meant. A run whose id names no table (a
    fixture's, a trial's) belongs to every table, as every run did before.
    """
    from qa_tools.common.qa_results_writer import run_owner

    return [m for m in manifest
            if (owner := run_owner(m["run_id"])) is None or owner[1] == table]


def build_one_table(table: str, results: list[dict], manifest: list[dict], dataset_stats: dict,
                     lifecycle_by_id: dict) -> dict:
    dataset_id = hierarchy.dataset_for_table(table).dataset_id
    column_meta = COLUMN_META[table]
    all_columns = list(column_meta.keys())

    cross_table_ids = _cross_table_check_ids()
    by_column: dict[str, dict[tuple, dict]] = {}
    # A CHECK THAT COULD NOT BE EVALUATED (plans/post-build-review.md #77,
    # gap 1) arrives under a pseudo-tool - `unrunnable` or `held` - with a
    # check_name of its own, so keying it like a real result would open a
    # SECOND card for the same check. Real results go first so every
    # check's card exists, and each can't-run record then joins the card
    # with its check_id, as that run's red with its reason.
    results = ([r for r in results if not _not_evaluated_reason(r)]
               + [r for r in results if _not_evaluated_reason(r)])
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
        if r["check_id"] in cross_table_ids:
            # Ahead of the column_name branches below, deliberately: a
            # cross-table check has a column name of its own and it
            # means nothing on the tables it READS.
            col = CROSS_TABLE_PSEUDO_COLUMN
        elif r["column_name"] == "(table)":
            col = (SUPPLY_LEVEL_PSEUDO_COLUMN if r["check_name"] in _SUPPLY_LEVEL_CHECK_NAMES
                   else BUSINESS_RULE_PSEUDO_COLUMN)
        else:
            col = r["column_name"]
        if col not in column_meta:
            continue
        # KEYED BY check_id - a check's identity (post-build-review #88).
        # It was (engine, check_name), which merged two DIFFERENT checks
        # sharing a name into one card: cp-clients' cross-table section
        # drew cp-placements' relationship verdicts on cp-investigations'
        # check. It also gives a can't-run record (REQ-PIPE-105 criterion
        # 13) its real check's card without a lookup, since it carries the
        # same check_id under a pseudo-tool and a prose name of its own;
        # real records come first, so the card keeps the real name.
        slot = by_column.setdefault(col, {}).setdefault(r["check_id"], {
            "engine": r["engine"], "check_name": r["check_name"],
            "unit": r["unit"], "warn": r["warn_threshold"], "fail": r["fail_threshold"],
            "dimension": r["dimension"], "label": r.get("label"), "check_id": r["check_id"],
            "by_run": {}, "row_count_total": {}, "row_count_invalid": {}, "failing_sample_keys": {},
            "status_by_run": {}, "reference": {}, "not_evaluated": {},
        })
        slot["not_evaluated"][r["run_id"]] = _not_evaluated_reason(r)
        slot["by_run"][r["run_id"]] = r["metric_value"]
        # item 74 Bug A: the tool's own verdict, carried through rather
        # than dropped here and re-derived from thresholds downstream.
        slot["status_by_run"][r["run_id"]] = dashboard_status(r.get("status"))
        # WHAT IT WAS COMPARED WITH, AND THE MEASURED VERDICT BESIDE A GAP'S
        # RED (REQ-QAC-108 criteria 14 and 16).
        slot["reference"][r["run_id"]] = drift_reference.reference_note(r, dashboard_status)
        slot["row_count_total"][r["run_id"]] = r["row_count_total"]
        slot["row_count_invalid"][r["run_id"]] = r["row_count_invalid"]
        slot["failing_sample_keys"][r["run_id"]] = r.get("failing_sample_keys") or []

    run_ids_in_order = [m["run_id"] for m in manifest]
    # THE NEWEST RUNS THAT MEASURED THIS TABLE, not simply the newest
    # runs (REQ-PIPE-105). A run whose own table was contested or held
    # has nothing of its own to show, and stats it could not take are
    # absent rather than zero - so "current" is the newest run that has
    # a number, which is what a reader means by it.
    measured = [r for r in run_ids_in_order
                if (dataset_stats.get(r) or {}).get("row_counts", {}).get(table) is not None]
    measured = measured or run_ids_in_order
    latest_run, prev_run = measured[-1], (measured[-2] if len(measured) > 1 else measured[-1])
    # run_date alone can't key a run uniquely (see build_dashboard_data.
    # py's identical comment) - byRun below keys on run_id via each
    # history entry's own "run_id" field.
    # A run measures only what it could read (REQ-PIPE-105), so a table
    # can be missing from a run's counts - absent here, never zero.
    row_count_by_run = {run_id: st.get("row_counts", {}).get(table)
                        for run_id, st in dataset_stats.items()}

    columns_out = []
    for col in all_columns:
        logical_type, desc = column_meta[col]
        checks_for_col = by_column.get(col, {})
        agg_spec = AGGREGATE_SPEC.get((table, col))

        checks_out = []
        for slot in checks_for_col.values():
            engine, check_name = slot["engine"], slot["check_name"]
            attach_aggregate = agg_spec is not None and check_name in agg_spec["check_names"]
            history = []
            for run_id in run_ids_in_order:
                if run_id in slot["by_run"]:
                    run_date = next(_run_date(m) for m in manifest if m["run_id"] == run_id)
                    aggregate_values = None
                    if attach_aggregate:
                        aggregate_values = (dataset_stats.get(run_id) or {}).get(
                            "check_aggregates", {}).get(f"{table}.{col}")
                    history.append({
                        "run_id": run_id, "run_date": run_date, "value": slot["by_run"][run_id],
                        "row_count_total": slot["row_count_total"].get(run_id),
                        "row_count_invalid": slot["row_count_invalid"].get(run_id),
                        "failing_sample_keys": slot["failing_sample_keys"].get(run_id) or [],
                        "aggregate_values": aggregate_values,
                        "status": slot["status_by_run"].get(run_id),
                        "reference": slot["reference"].get(run_id),
                        # Why this run's check could NOT be evaluated, or
                        # None for a real verdict - never a value or a pass.
                        "not_evaluated": slot["not_evaluated"].get(run_id),
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
                # pooled_url_key() in a scope section, where checks
                # from several real columns share one pseudo-column and
                # a bare tail is no longer unique. See its own docstring.
                "key": (pooled_url_key(slot["check_id"]) if col in COLUMN_SCOPE_KEY
                        else url_key(slot["check_id"])),
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

        _disambiguate_pooled_keys(checks_out)
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

        total_latest = row_count_by_run.get(latest_run) or 0
        total_prev = row_count_by_run.get(prev_run) or 0

        stats = {
            "current": {"total": total_latest, "invalid": 0, "valid": total_latest, "valueCounts": None},
            "previous": {"total": total_prev, "invalid": 0, "valid": total_prev, "valueCounts": None},
        }
        if checks_out:
            primary_unit = checks_out[0]["unit"]
            for label, total, val in (("current", total_latest, checks_out[0]["current"]),
                                       ("previous", total_prev, checks_out[0]["previous"])):
                # A run whose check could not be evaluated has no value
                # (post-build-review #77) - nothing was counted, so
                # nothing is reported invalid, rather than a crash.
                if val is None:
                    continue
                n_invalid = int(round(total * val / 100)) if primary_unit == "%" else int(round(val))
                stats[label]["invalid"] = max(0, n_invalid)
                stats[label]["valid"] = max(0, total - stats[label]["invalid"])

        if col == "concern_type":
            stats["current"]["valueCounts"] = _value_counts(dataset_stats, latest_run)
            stats["previous"]["valueCounts"] = _value_counts(dataset_stats, prev_run)

        # Full per-run fidelity, keyed by run_id - see build_dashboard_
        # data.py's identical comment on stats["byRun"] for the full
        # rationale (additive, current/previous unchanged, for Thread
        # C's as-of UI).
        primary_unit = checks_out[0]["unit"]
        stats_by_run = {}
        for h in checks_out[0]["history"]:
            run_id = h["run_id"]
            total = row_count_by_run.get(run_id)
            if total is None:
                # A run that did not measure this table - a sibling's run
                # whose cross-table result is shared here - has no count
                # of it to divide by.
                continue
            if h["value"] is None:
                continue  # not evaluated in this run - see the comment above
            n_invalid = int(round(total * h["value"] / 100)) if primary_unit == "%" else int(round(h["value"]))
            n_invalid = max(0, n_invalid)
            stats_by_run[run_id] = {
                "total": total, "invalid": n_invalid, "valid": max(0, total - n_invalid),
                "valueCounts": _value_counts(dataset_stats, run_id) if col == "concern_type" else None,
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

    # READ, NOT COMPUTED (REQ-PIPE-080 criteria 1 and 2) - see
    # build_dashboard_data.py's identical block for the full account of
    # what cadence.classify_arrival() got wrong and why it is gone.
    arrival_by_run = {}
    arrival_history = []
    for m in manifest:
        run_id = m["run_id"]
        block = recorded_arrival.for_run(dataset_id, m["received_at"])
        arrival_by_run[run_id] = block
        arrival_history.append({"run_id": run_id, "run_date": _run_date(m),
                                 **block})
    latest_block = arrival_by_run[latest_run]

    return {
        "id": dataset_id,
        "name": hierarchy.dataset_for_table(table).dataset_name,
        "provider": "Department for Child Protection and Family Support — Casework Management System",
        "deliveryFormat": "CSV (S3 drop)",
        "sla": {"cadence": cadence},
        # WHETHER ANYBODY HAS AGREED A SCHEDULE FOR THIS DATASET
        # (REQ-PIPE-106). None for every dataset that has a calendar, so
        # the page renders nothing extra in the ordinary case - which is
        # the point at 30 datasets: a marker on every tile is noise that
        # trains people to stop reading markers.
        "scheduleNotAgreed": _schedule_not_agreed(dataset_id),
        "lastArrival": {"run_date": _run_date(latest_entry), **latest_block},
        # WHAT ARRIVED VERSUS WHAT IS PROMOTED (REQ-DASH-056). From
        # the recorded filing and the recorded decision, never from
        # supply rows - both are facts somebody WROTE DOWN, which is
        # what criterion 5 protects. Quiet when they agree: `differs`
        # is False in the ordinary case and the page renders nothing
        # extra, which is the point at thirty datasets.
        # WHAT EACH SLOT HELD, AND WHEN THAT CHANGED (REQ-PIPE-081
        # criteria 1, 2, 3 and 6). The ANSWERS, not the rule - see
        # pipeline/slot_timeline.py for why the page must not be taught
        # to derive these for itself. Read from the decision log, with
        # each entry tied to the run that checked it.
        "slotTimeline": slot_timeline.with_runs(
            slot_timeline.for_dataset(dataset_id), dataset_id),
        # EACH RUN'S SUPPLY, PROMOTED, AWAITING OR WITHDRAWN OVER TIME
        # (REQ-PIPE-081 criteria 1, 2 and 8 as amended 2026-10-05): the
        # page's verdict is the newest supply promoted or awaiting on the
        # date on show. Answers from the decision log, looked up there.
        "runStates": slot_timeline.run_states(dataset_id),
        # HOW EACH PROMOTED SUPPLY HAS DONE SINCE (REQ-DASH-126): the status
        # it was promoted on and its status after each run that read it, so
        # the page can say "red promoted" on the dates it was, and when and
        # after what it turned. See pipeline/red_promoted.py.
        "promotedHealth": red_promoted.for_dataset(dataset_id),
        # REQ-DASH-097: the file checks, BESIDE `columns` - never inside
        # them, which is what keeps them out of every roll-up.
        "fileChecks": file_check_panel.for_dataset(dataset_id),
        # EVERY PERIOD THAT CLOSED WITH NO SUPPLY, and the instants that
        # decide what it reads as on any date (REQ-DASH-133 criteria 9 and
        # 10) - see pipeline/closed_slots.py. The page compares instants;
        # it never re-derives closing.
        "closedSlots": closed_slots.for_dataset(dataset_id),
        # A SLOT LATE BUT STILL OPEN (REQ-DASH-133, Keith 2026-10-05): every
        # slot that was ever late while open, so the page can name today's
        # late file beside an older gap.
        "lateSlots": closed_slots.late_slots(dataset_id),
        # REQ-PIPE-081 criteria 14 and 15 - see build_dashboard_data.py.
        "census": census.for_datasets({dataset_id}),
        # REQ-PIPE-122 NFR 1: the amber setting in force over time, in
        # words, from configuration only - the page shows the one in force
        # on the date on show.
        "amberSetting": amber_setting.timeline(dataset_id),
        # WHICH PROMOTED AMBER SUPPLIES WERE ACKNOWLEDGED (REQ-PIPE-122
        # criterion 21), keyed by run - see pipeline/acknowledgements.py.
        "acknowledgements": acknowledgements.for_dataset(dataset_id),
        "promotionState": promotion_state.state_for(dataset_id).as_record(),
        "arrivalHistory": arrival_history,
        "arrivalByRun": arrival_by_run,
        "rowCount": row_count_by_run.get(latest_run),
        "prevRowCount": row_count_by_run.get(prev_run),
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


def _schedule_not_agreed(dataset_id: str) -> str | None:
    """Whether this dataset has declared it has no delivery calendar, and
    which kind (REQ-PIPE-106 criteria 3, 8 and 9).

    Carried onto the dataset so the page can say so IN WORDS beside the
    dataset's own real verdict, and so every rollup above it can leave it
    out. Read from CONFIGURATION, which is what makes it safe here: this
    build may read recorded QA results and never supply rows, and a
    declaration in contract/data-asset.yaml is neither.

    None for every dataset that has a calendar, which today is all seven.
    """
    from qa_tools.common import schedule

    return schedule.no_calendar(dataset_id)


def share_cross_table_results(results: list[dict], by_table: dict[str, list[dict]]) -> None:
    """Give each cross-table result to every table it reads.

    PULLED OUT OF build() so the exclusion below is testable without a
    whole reports/results_cp.json - the rule it carries is one a test
    should be able to state in four records.
    """
    # REQ-QAC-037 criteria 6 and 7: a cross-table result belongs to
    # EVERY table it reads, not only to the one it happened to be
    # declared on. Which table that was is an artefact of where
    # somebody wrote the check down - a referential check between
    # placements and carers is equally about both - and letting it
    # decide who sees the result, and whose status carries it, is the
    # arbitrariness this requirement removes.
    #
    # THE RESULT IS SHARED, NOT COPIED. The same record object is added
    # to each participant's list, and it is recorded once under the
    # reserved scope; criterion 2 forbids a second record, not a second
    # reader.
    from qa_tools.common import tables_read

    reads = tables_read.declared_by_check_id(collect_checks(None))
    for r in results:
        for other in reads.get(r.get("check_id")) or ():
            if other not in by_table or r in by_table[other]:
                continue
            # BUT AN IN-DEVELOPMENT RESULT IS NOT SHARED WITH AN AGREED
            # PARTICIPANT (REQ-PIPE-106 criterion 15). A cross-table check
            # spanning a dataset nobody has agreed a schedule for and one
            # that has a calendar is ALLOWED - Keith, 2026-09-27: "allow it,
            # but don't let it affect the agreed data set" - and it is
            # recorded as in-development by whoever wrote it, because ANY
            # unagreed participant makes the whole verdict one. Sharing it
            # here would put that verdict into the agreed table's own
            # status, which is the one thing criterion 15 forbids and the
            # exact way an unagreed dataset could turn an agreed one red.
            #
            # THE CHECK IS STILL RUN, RECORDED AND REPORTED - on the
            # calendar-less participant's page, which is where somebody
            # developing the check is looking. Refusing the check outright
            # would block the strongest case for developing one early: a new
            # dataset joining an existing collection.
            if r.get("supply_state") == qa_store.IN_DEVELOPMENT and \
                    not _schedule_not_agreed(hierarchy.dataset_for_table(other).dataset_id):
                continue
            by_table[other].append(r)


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
    share_cross_table_results(results, by_table)
    datasets = [build_one_table(t, by_table[t], own_runs(manifest, t), dataset_stats, lifecycle_by_id)
                for t in cp_common.TABLES]
    return {"datasets": datasets}


if __name__ == "__main__":
    data = build()
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"Wrote {OUT_PATH} ({len(data['datasets'])} datasets)")
    # Criterion 16: a WARNING, and the build still publishes.
    for line in census.build_warnings():
        print(line)
