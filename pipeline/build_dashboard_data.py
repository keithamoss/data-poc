"""
One dashboard builder for every collection (REQ-DASH-244).

Reshapes a collection's results file (reports/<adapter.results_json>, the
shared orchestrator's real dbt-core/Soda Core/datacontract-cli/Evidently
output, rebuilt from recorded history) into the JSON the dashboard's
drawer and chart code reads, one dataset object per dataset the hierarchy
declares, and writes it to reports/<adapter.dashboard_json>.

WHAT USED TO BE TWO MODULES. Birth Registrations and Child Protection
each had a builder of their own, about 1,400 lines between them and most
of it the same code twice, with every column's type and note typed into
Python. Nothing about a collection is code here any more:

- a column's and a table's TYPE AND DESCRIPTION come from the collection's
  ODCS contract (criterion 1), in the words the contract holds it to; the
  builders' notes were moved into the contracts first (criterion 2);
- who supplies a collection and how, and each dataset's provenance note,
  come from contract/presentation.yaml (criterion 10);
- which value-count distribution and aggregates a column shows come from
  the adapter's .stats, the same table the statistics are computed from;
- the few places Birth Registrations' output has always differed are
  named legacy flags on its adapter (qa_tools/tools/legacy.py), never a
  comparison of collection ids (criterion 11).

A BUILD MAY READ RECORDED QA RESULTS, NEVER ACTUAL DATA, AND NEVER ANYTHING
ELSE (Keith, 2026-09-27): every input below is a results file, a decision
or filing the pipeline recorded, or configuration.

A COLLECTION WITH NO RECORDED RUNS is built too (criterion 6): each of its
declared datasets is written with an empty history, which the page renders
as never supplied or not owed yet - never as a missing collection.
"""
from __future__ import annotations

import functools
import json
import os

import yaml

from pipeline import (acknowledgements, closed_slots, corrections, excuses, file_check_panel,
                      owed_nothing, placements, promotion_timeline, recorded_arrival, red_promoted,
                      slot_timeline)
from pipeline.dashboard_check_labels import (dashboard_status, display_name, measure, pooled_url_key,
                                             rank_for_headline, tool_ref, url_key)
from qa_tools import collections
from qa_tools.common import (agreement, amber_setting, asset_time, census, drift_reference, hierarchy,
                             qa_store, schedule_ended, turned_off)
from qa_tools.common.validate_check_lifecycle import collect_checks

ROOT = os.path.join(os.path.dirname(__file__), "..")
REPORTS = os.path.join(ROOT, "reports")


def results_path(collection_id: str) -> str:
    return os.path.join(REPORTS, collections.adapter(collection_id).results_json)


def out_path(collection_id: str) -> str:
    return os.path.join(REPORTS, collections.adapter(collection_id).dashboard_json)


def _run_date(entry: dict) -> str:
    """One manifest entry's receipt DATE, as a string.

    The manifest carries a receipt INSTANT since REQ-GEN-042 - the
    generator's own `received_at` - and everything below wants a date, for
    a cadence cycle or a row in a supply-history table, so it is derived
    here in one place. `run_date` survives as the DASHBOARD-FACING name
    deliberately: the template, the JS tests and the e2e suite all key on
    it.
    """
    return asset_time.local_date(entry["received_at"]).isoformat()


ENGINE_SHORT = {
    "dbt-core 1.12 + dbt-duckdb": "dbt-core",
    "dbt-core 1.12 + dbt-postgres": "dbt-core",
    "Soda Core 3.5": "Soda Core",
    "datacontract-cli 1.2.0": "datacontract-cli",
    "Evidently 0.7": "Evidently AI",
}

# THREE SECTION PSEUDO-COLUMNS (REQ-DASH-033, REQ-QAC-037), so a check that
# belongs to the whole table, the whole supply or two tables at once still
# has somewhere to live. Deliberately separate (Keith, 2026-09-20): "is
# this supply the right size and current enough" is a different question
# from "do these tables agree with each other".
SUPPLY_LEVEL_PSEUDO_COLUMN = "Supply-level checks"
TABLE_LEVEL_PSEUDO_COLUMN = "Table-level checks"
# A cross-table check cannot keep its own column name: a referential check
# declared on cp_notifications reads cp_client_id, which is a column of
# cp_notifications and not of cp_carers.
CROSS_TABLE_PSEUDO_COLUMN = "Cross-table checks"

#: A section's URL slug - a column's `key` is its own name for a real one,
#: so only these differ from their display name.
COLUMN_SCOPE_KEY = {
    SUPPLY_LEVEL_PSEUDO_COLUMN: "supply",
    TABLE_LEVEL_PSEUDO_COLUMN: "table",
    CROSS_TABLE_PSEUDO_COLUMN: "cross-table",
}
_PSEUDO_COLUMNS = tuple(COLUMN_SCOPE_KEY)

SUPPLY_LEVEL_META = (
    "supply-level",
    "Checks on the supply as a whole rather than on any one column - whether it "
    "arrived the right size, and whether it is current.")
#: A table's own note on its Table-level section is the contract's
#: `tableLevelChecksNote` custom property; this is the note where it has none.
TABLE_LEVEL_DEFAULT_NOTE = "Rules that span the whole table rather than any one column."
CROSS_TABLE_META = (
    "cross-table",
    "Checks about the relationship between this table and another. A failure "
    "here is a disagreement between tables rather than a fault in either one "
    "alone, so it counts against every table the check reads.")

# datacontract-cli and Soda each spell the row-count check differently, and
# `evidently:row_count_growth` asks the same question relative to the last
# promoted supply (REQ-QAC-108 criterion 1).
_SUPPLY_LEVEL_CHECK_NAMES = {"row_count", "datacontract:row_count", "evidently:row_count_growth"}


# ---- what differs by collection, read from configuration --------------------

def _legacy(coll) -> frozenset:
    return collections.adapter(coll).legacy


def _contract(contract: str) -> dict:
    """A collection's contract, beside the hierarchy that names it."""
    return _contract_at(str(hierarchy.DATA_ASSET_YAML.parent / contract))


@functools.cache
def _contract_at(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _type(prop: dict) -> str:
    """How the page states a column's type, from the contract: the logical
    type alone where the two agree, `string · <physical>` for a string, and
    otherwise the physical type, which is the more specific of the two."""
    logical, physical = prop.get("logicalType"), prop.get("physicalType")
    if logical == physical or not physical:
        return logical or ""
    return f"{logical} · {physical}" if logical == "string" else physical


def _element(coll, dataset) -> dict:
    """The dataset's table in its collection's contract."""
    for el in _contract(coll.contract).get("schema") or []:
        if el.get("name") == dataset.table:
            return el
    raise ValueError(f"{coll.contract} has no schema entry for {dataset.dataset_id}'s table "
                     f"{dataset.table!r}")


def column_meta(coll, dataset) -> dict[str, tuple[str, str]]:
    """Each column the page shows, in order, as (type, description) - the
    contract's real columns, then the section pseudo-columns."""
    el = _element(coll, dataset)
    meta = {p["name"]: (_type(p), (p.get("description") or "").strip())
            for p in el.get("properties") or []}
    note = next((p.get("value") for p in el.get("customProperties") or []
                 if p.get("property") == "tableLevelChecksNote"), None)
    table_level = ("table-level", note or TABLE_LEVEL_DEFAULT_NOTE)
    if "dashboard.supply_section_first" in _legacy(coll):
        meta[SUPPLY_LEVEL_PSEUDO_COLUMN] = SUPPLY_LEVEL_META
        meta[TABLE_LEVEL_PSEUDO_COLUMN] = table_level
    else:
        meta[TABLE_LEVEL_PSEUDO_COLUMN] = table_level
        meta[SUPPLY_LEVEL_PSEUDO_COLUMN] = SUPPLY_LEVEL_META
    meta[CROSS_TABLE_PSEUDO_COLUMN] = CROSS_TABLE_META
    return meta


def table_description(coll, dataset) -> str:
    return (_element(coll, dataset).get("description") or "").strip()


def _presented(coll) -> dict:
    from qa_tools.common import presentation

    return presentation.for_collection(coll.id)


# ---- the statistics, in either recorded shape --------------------------------

def _row_count(stats: dict | None, table: str, single: bool):
    """A run's recorded row count for `table` - absent, never zero, where the
    run could not read it (REQ-PIPE-105)."""
    stats = stats or {}
    return stats.get("row_count") if single else (stats.get("row_counts") or {}).get(table)


def _aggregate_key(table: str, col: str, single: bool) -> str:
    return col if single else f"{table}.{col}"


def _value_counts(dataset_stats: dict, run_id: str, col: str):
    """A column's recorded distribution for a run, or None where that run
    could not read its table (REQ-PIPE-105)."""
    return ((dataset_stats.get(run_id) or {}).get("value_counts") or {}).get(col)


# ---- the per-check helpers --------------------------------------------------

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
    """Every check that reads a table other than its own, read from the
    check definitions rather than the results, so a check absent from one
    run is still known to be cross-table."""
    from qa_tools.common import tables_read

    return set(tables_read.declared_by_check_id(collect_checks(None)))


def _not_evaluated_reason(record: dict) -> str | None:
    """Why a record's check could not be evaluated, or None for a real
    verdict. Read from the reason each pseudo-tool writes -
    `unrunnable_reason` (REQ-PIPE-105 criterion 13) and `held_reason`
    (REQ-PIPE-078 criterion 10) - so a real tool's result can never be
    mistaken for one."""
    return (record.get("unrunnable_reason") or record.get("held_reason")
            # A real tool that could not evaluate a check it was handed
            # (Soda leaving it out of its results - the road-testing
            # sweep's #7, 2026-10-06).
            or record.get("not_evaluated_reason")
            # REQ-QAC-108 criterion 9: red, not evaluated, under Evidently.
            or (record.get("reference_reason") if record.get("reference_not_evaluated")
                else None)
            or None)


def own_runs(manifest: list[dict], table: str) -> list[dict]:
    """The runs that are FOR this table (REQ-PIPE-105).

    One file is one arrival and a run id is its staged table's spelling,
    so a six-table delivery is six runs and each belongs to one table. A
    run whose id names no table (a fixture's, a trial's) belongs to every
    table, as every run did before.
    """
    from qa_tools.common.qa_results_writer import run_owner

    return [m for m in manifest
            if (owner := run_owner(m["run_id"])) is None or owner[1] == table]


def _schedule_not_agreed(dataset_id: str) -> str | None:
    """Whether this dataset has declared it has no delivery calendar, and
    which kind (REQ-PIPE-106 criteria 3, 8 and 9) - configuration, so safe
    here. None for every dataset that has a calendar."""
    from qa_tools.common import schedule

    return schedule.no_calendar(dataset_id)


def _agreement_refusal(dataset_id: str) -> dict | None:
    """This dataset's REQ-PIPE-173 refusal as the page renders it, or None."""
    from qa_tools.common import agreement_drift

    found = agreement_drift.refusals(dataset_ids=[dataset_id]).get(dataset_id)
    return found.as_record() if found else None


def share_cross_table_results(results: list[dict], by_table: dict[str, list[dict]]) -> None:
    """Give each cross-table result to every table it reads.

    REQ-QAC-037 criteria 6 and 7: a cross-table result belongs to EVERY
    table it reads, not only to the one it happened to be declared on. THE
    RESULT IS SHARED, NOT COPIED: the same record object is added to each
    participant's list, and it is recorded once under the reserved scope.
    """
    from qa_tools.common import tables_read

    reads = tables_read.declared_by_check_id(collect_checks(None))
    for r in results:
        for other in reads.get(r.get("check_id")) or ():
            if other not in by_table or r in by_table[other]:
                continue
            # BUT AN IN-DEVELOPMENT RESULT IS NOT SHARED WITH AN AGREED
            # PARTICIPANT (REQ-PIPE-106 criterion 15, Keith 2026-09-27: "allow
            # it, but don't let it affect the agreed data set"). It is still
            # run, recorded and reported on the calendar-less participant's
            # page, which is where somebody developing the check is looking.
            if r.get("supply_state") == qa_store.IN_DEVELOPMENT and \
                    not _schedule_not_agreed(hierarchy.dataset_for_table(other).dataset_id):
                continue
            by_table[other].append(r)


# ---- one dataset ------------------------------------------------------------

def build_one_table(coll, dataset, results: list[dict], manifest: list[dict], dataset_stats: dict,
                    lifecycle_by_id: dict) -> dict:
    table, dataset_id = dataset.table, dataset.dataset_id
    legacy = _legacy(coll)
    single = "stats.single_table_shape" in legacy
    meta = column_meta(coll, dataset)
    all_columns = list(meta)
    stats_spec = collections.adapter(coll).stats
    aggregates = stats_spec.aggregates
    value_count_cols = {col for (t, col) in stats_spec.value_counts if t == table}

    cross_table_ids = _cross_table_check_ids()
    by_column: dict[str, dict[str, dict]] = {}
    # A CHECK THAT COULD NOT BE EVALUATED (post-build-review #77) arrives
    # under a pseudo-tool with a check_name of its own, so keying it like
    # a real result would open a SECOND card for the same check. Real
    # results go first so every check's card exists, and each can't-run
    # record then joins the card with its check_id.
    results = ([r for r in results if not _not_evaluated_reason(r)]
               + [r for r in results if _not_evaluated_reason(r)])
    for r in results:
        if r["check_id"] in cross_table_ids:
            # Ahead of the column_name branches below, deliberately: a
            # cross-table check has a column name of its own and it means
            # nothing on the tables it READS.
            col = CROSS_TABLE_PSEUDO_COLUMN
        elif r["column_name"] == "(table)":
            col = (SUPPLY_LEVEL_PSEUDO_COLUMN if r["check_name"] in _SUPPLY_LEVEL_CHECK_NAMES
                   else TABLE_LEVEL_PSEUDO_COLUMN)
        else:
            col = r["column_name"]
        if col not in meta:
            continue
        # KEYED BY check_id - a check's identity (post-build-review #88). The
        # display name (engine, check_name) is not unique: datacontract-cli
        # reports every `type: sql` rule as "datacontract:custom_sql".
        slot = by_column.setdefault(col, {}).setdefault(r["check_id"], {
            "engine": r["engine"], "check_name": r["check_name"],
            "unit": r["unit"], "warn": r["warn_threshold"], "fail": r["fail_threshold"],
            "dimension": r["dimension"], "label": r.get("label"), "check_id": r["check_id"],
            "by_run": {}, "row_count_total": {}, "row_count_invalid": {}, "failing_sample_keys": {},
            "status_by_run": {}, "reference": {}, "not_evaluated": {},
        })
        slot["not_evaluated"][r["run_id"]] = _not_evaluated_reason(r)
        slot["by_run"][r["run_id"]] = r["metric_value"]
        # item 74 Bug A: the tool's own verdict, carried through rather than
        # dropped here and re-derived from thresholds downstream.
        slot["status_by_run"][r["run_id"]] = dashboard_status(r.get("status"))
        # WHAT IT WAS COMPARED WITH, AND THE MEASURED VERDICT BESIDE A GAP'S
        # RED (REQ-QAC-108 criteria 14 and 16).
        slot["reference"][r["run_id"]] = drift_reference.reference_note(r, dashboard_status)
        slot["row_count_total"][r["run_id"]] = r["row_count_total"]
        slot["row_count_invalid"][r["run_id"]] = r["row_count_invalid"]
        slot["failing_sample_keys"][r["run_id"]] = r.get("failing_sample_keys") or []

    run_ids_in_order = [m["run_id"] for m in manifest]
    run_date_by_id = {m["run_id"]: _run_date(m) for m in manifest}
    # THE NEWEST RUNS THAT MEASURED THIS TABLE, not simply the newest runs
    # (REQ-PIPE-105): a run whose table was contested or held has nothing of
    # its own to show. None for a dataset never supplied (criterion 6).
    measured = [r for r in run_ids_in_order
                if _row_count(dataset_stats.get(r), table, single) is not None]
    measured = measured or run_ids_in_order
    latest_run = measured[-1] if measured else None
    prev_run = measured[-2] if len(measured) > 1 else latest_run
    # A run measures only what it could read (REQ-PIPE-105), so a table can
    # be missing from a run's counts - absent here, never zero.
    row_count_by_run = {run_id: _row_count(st, table, single)
                        for run_id, st in dataset_stats.items()}

    columns_out = []
    for col in all_columns:
        logical_type, desc = meta[col]
        checks_for_col = by_column.get(col, {})
        agg_spec = aggregates.get((table, col))

        checks_out = []
        for slot in checks_for_col.values():
            engine, check_name = slot["engine"], slot["check_name"]
            attach_aggregate = agg_spec is not None and check_name in agg_spec["check_names"]
            history = []
            for run_id in run_ids_in_order:
                if run_id not in slot["by_run"]:
                    continue
                aggregate_values = None
                if attach_aggregate:
                    aggregate_values = (dataset_stats.get(run_id) or {}).get(
                        "check_aggregates", {}).get(_aggregate_key(table, col, single))
                # Why this run's check could NOT be evaluated, or None for a
                # real verdict - never a value or a pass.
                not_evaluated = slot["not_evaluated"].get(run_id)
                history.append({
                    "run_id": run_id, "run_date": run_date_by_id[run_id],
                    "value": slot["by_run"][run_id],
                    "row_count_total": slot["row_count_total"].get(run_id),
                    "row_count_invalid": slot["row_count_invalid"].get(run_id),
                    "failing_sample_keys": slot["failing_sample_keys"].get(run_id) or [],
                    "aggregate_values": aggregate_values,
                    "status": slot["status_by_run"].get(run_id),
                    "reference": slot["reference"].get(run_id),
                    "not_evaluated": not_evaluated,
                })
            if not history:
                continue
            engine_short = ENGINE_SHORT.get(engine, engine)
            lifecycle = lifecycle_by_id.get(slot["check_id"])
            checks_out.append({
                "check_id": slot["check_id"],
                # A hand-authored `name` in the check's own metadata wins
                # over the derived label (REQ-DASH-026).
                "name": (lifecycle.name if lifecycle and lifecycle.name
                         else display_name(check_name, engine_short, slot["label"])),
                # The URL-facing identity, stable across heading rewrites
                # (REQ-DASH-026) - pooled_url_key() in a section, where checks
                # from several real columns share one pseudo-column.
                "key": (pooled_url_key(slot["check_id"]) if col in COLUMN_SCOPE_KEY
                        else url_key(slot["check_id"])),
                "tool_ref": tool_ref(slot["check_id"]),
                "dimension": slot["dimension"],
                "unit": slot["unit"],
                # REQ-DASH-228: the chart's axis title and table header.
                "measure": measure(slot["check_id"], slot["unit"]),
                # item 74 Bug A: None stays None - it means "this check has no
                # bound of that kind", NOT "zero tolerance".
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
                # REQ-QAC-024: the plain-English SO-WHAT. `technical_note` is
                # deliberately NOT here: it is written for contributors, and
                # this dict is published to a public site.
                "failure_indicates": lifecycle.failure_indicates if lifecycle else None,
                "changelog": lifecycle.changelog if lifecycle else [],
            })

        _disambiguate_pooled_keys(checks_out)
        if not checks_out and col == CROSS_TABLE_PSEUDO_COLUMN and len(coll.datasets) == 1:
            # A ONE-TABLE COLLECTION HAS NO CROSS-TABLE GAP TO REPORT
            # (REQ-QAC-247, Keith 2026-10-18). Every other empty section says
            # so below, Table-level included, because a missing rule is
            # something a reader should see.
            continue
        if not checks_out:
            checks_out = [{
                # A REAL KEY, because everything downstream assumes one
                # (post-build-review #5 and #12), unique within its column,
                # which is the scope the /check/<key> route resolves in.
                "key": "no_rule_defined",
                "name": "No automated quality rule defined",
                # `inactive`, NOT green (post-build-review #4, Keith: "a grey,
                # as in a disabled kind of grey colour"). Green is a VERDICT,
                # and nothing was checked here. Stated explicitly because this
                # check is synthesized here, not produced by any real tool.
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
        primary_unit = checks_out[0]["unit"]
        for label, total, val in (("current", total_latest, checks_out[0]["current"]),
                                   ("previous", total_prev, checks_out[0]["previous"])):
            # A run whose check could not be evaluated has no value - nothing
            # was counted, so nothing is reported invalid, rather than a crash.
            if val is None:
                continue
            n_invalid = int(round(total * val / 100)) if primary_unit == "%" else int(round(val))
            stats[label]["invalid"] = max(0, n_invalid)
            stats[label]["valid"] = max(0, total - stats[label]["invalid"])

        if col in value_count_cols:
            stats["current"]["valueCounts"] = _value_counts(dataset_stats, latest_run, col)
            stats["previous"]["valueCounts"] = _value_counts(dataset_stats, prev_run, col)

        # Full per-run fidelity, keyed by run_id for the as-of picker, from
        # the same primary check "current"/"previous" use.
        stats_by_run = {}
        for h in checks_out[0]["history"]:
            run_id = h["run_id"]
            total = row_count_by_run.get(run_id)
            # NO NUMBER FOR THIS RUN - a run that did not measure this table,
            # or a check not evaluated - is no byRun entry, never a crash.
            if total is None or h["value"] is None:
                continue
            n_invalid = int(round(total * h["value"] / 100)) if primary_unit == "%" else int(round(h["value"]))
            n_invalid = max(0, n_invalid)
            stats_by_run[run_id] = {
                "total": total, "invalid": n_invalid, "valid": max(0, total - n_invalid),
                "valueCounts": _value_counts(dataset_stats, run_id, col) if col in value_count_cols else None,
            }
        stats["byRun"] = stats_by_run

        columns_out.append({
            "name": col, "logicalType": logical_type, "description": desc,
            # The URL-facing identity of a column, equal to its name for a
            # real one; `scope` is present only on the section pseudo-columns
            # and is what the dataset view keys its split on.
            "key": COLUMN_SCOPE_KEY.get(col, col),
            "scope": COLUMN_SCOPE_KEY.get(col),
            "checks": checks_out, "stats": stats,
        })

    # From the dataset's participation in contract/calendar.yaml (REQ-PIPE-110).
    cadence = agreement.cadence(dataset_id)

    # READ, NOT COMPUTED (REQ-PIPE-080 criteria 1 and 2): the arrival verdict
    # is recorded against the filing, keyed on the run's own `received_at`.
    arrival_by_run = {}
    arrival_history = []
    for m in manifest:
        run_id = m["run_id"]
        block = recorded_arrival.for_run(dataset_id, m["received_at"],
                                         supply=recorded_arrival.stated_supply(m, dataset_id))
        arrival_by_run[run_id] = block
        arrival_history.append({"run_id": run_id, "run_date": _run_date(m), **block})
    latest_entry = next((m for m in manifest if m["run_id"] == latest_run), None)
    last_arrival = ({"run_date": _run_date(latest_entry), "run_id": latest_entry.get("run_id"),
                     **arrival_by_run[latest_run]} if latest_entry else None)

    presented = _presented(coll)
    # What each slot held, read once and shared by two embeds below.
    slot_timeline_raw = slot_timeline.for_dataset(dataset_id)
    return {
        "id": dataset_id,
        "name": dataset.dataset_name,
        "provider": presented["provider"],
        "deliveryFormat": presented["delivery_format"],
        # THE DELIVERY TIME IN FORCE ON EACH DATE, and every period owed
        # nothing up to now (REQ-DASH-182): configuration only.
        "sla": {"cadence": cadence, **owed_nothing.sla_timeline(dataset_id)},
        # Each person's placement of a held supply (REQ-DASH-175).
        "placements": placements.for_dataset(dataset_id),
        "owedNothing": owed_nothing.for_dataset(dataset_id, until=asset_time.now().date()),
        # WHETHER ANYBODY HAS AGREED A SCHEDULE FOR THIS DATASET
        # (REQ-PIPE-106). None in the ordinary case, so the page renders
        # nothing extra - a marker on every tile is noise at 30 datasets.
        "scheduleNotAgreed": _schedule_not_agreed(dataset_id),
        "lastArrival": last_arrival,
        # WHAT EACH SLOT HELD, AND WHEN THAT CHANGED (REQ-PIPE-081 criteria
        # 1, 2, 3 and 6): the ANSWERS, from the decision log, never the rule.
        "slotTimeline": slot_timeline.with_runs(slot_timeline_raw, dataset_id),
        # EACH RUN'S SUPPLY, PROMOTED, AWAITING OR WITHDRAWN OVER TIME.
        "runStates": slot_timeline.run_states(dataset_id),
        # HOW EACH PROMOTED SUPPLY HAS DONE SINCE (REQ-DASH-126).
        "promotedHealth": red_promoted.for_dataset(dataset_id),
        # REQ-DASH-097: the file checks, BESIDE `columns` - never inside them,
        # which is what keeps them out of every roll-up.
        "fileChecks": file_check_panel.for_dataset(dataset_id),
        # EVERY PERIOD THAT CLOSED WITH NO SUPPLY (REQ-DASH-133 criteria 9, 10).
        "closedSlots": closed_slots.for_dataset(dataset_id),
        # A SLOT LATE BUT STILL OPEN (REQ-DASH-133, Keith 2026-10-05).
        "lateSlots": closed_slots.late_slots(dataset_id),
        # HELD BECAUSE ITS SCHEDULE ENDED (REQ-DASH-155).
        "scheduleEndedHolds": schedule_ended.for_dataset(dataset_id),
        # EVERY TURN-OFF IT READS (REQ-PIPE-179 criterion 41), configuration only.
        "turnOffs": turned_off.timeline(dataset_id),
        # REQ-PIPE-081 criteria 14 and 15: what the RECORDED census found.
        "census": census.for_datasets({dataset_id}),
        # REQ-PIPE-122 NFR 1: the amber setting in force over time.
        "amberSetting": amber_setting.timeline(dataset_id),
        # WHICH PROMOTED AMBER SUPPLIES WERE ACKNOWLEDGED (REQ-PIPE-122 c21).
        "acknowledgements": acknowledgements.for_dataset(dataset_id),
        # WHICH LATE SUPPLIES A PERSON EXCUSED (REQ-DASH-162).
        "excuses": excuses.for_dataset(dataset_id),
        # REQ-DASH-172: corrections and what they re-judged.
        "corrections": corrections.for_dataset(dataset_id),
        # REFUSED BY THE AGREEMENT BACKSTOP (REQ-PIPE-173 criterion 4).
        "agreementRefusal": _agreement_refusal(dataset_id),
        # WHAT WAS PROMOTED AND WHAT HAD ARRIVED, AS AT EACH DATE (REQ-DASH-197,
        # REQ-DASH-198): change points, one walk of the slot timeline above.
        "promotionTimeline": promotion_timeline.for_dataset(dataset_id, slot_timeline_raw),
        "arrivalHistory": arrival_history,
        "arrivalByRun": arrival_by_run,
        "rowCount": row_count_by_run.get(latest_run),
        "prevRowCount": row_count_by_run.get(prev_run),
        # Each run as the PAGE sees it: the manifest entry plus a derived
        # `run_date`. Spread-then-add rather than a hand-listed copy: a
        # hand-maintained allowlist silently drops every field added later
        # (CLAUDE.md's standing lesson from item 74).
        "runs": [{**m, "run_date": _run_date(m)} for m in manifest],
        "columns": columns_out,
        "_provenance": presented["provenance"].format(
            table_description=table_description(coll, dataset)),
    }


# ---- one collection ---------------------------------------------------------

class MissingResultsFile(FileNotFoundError):
    """A collection's results file is not there to build from - refused,
    naming the collection and the command that writes it."""


def _payload(collection_id: str) -> dict:
    """The collection's results file. A collection with no recorded runs has
    one too - the rebuild always writes it, empty - so it is built with an
    empty history (criterion 6). A MISSING file is refused (Keith,
    2026-10-18; post-build-review #233): read as 'no runs', it published a
    collection with real history as never supplied whenever `build-data`
    ran before `rebuild-results`."""
    path = results_path(collection_id)
    if not os.path.exists(path):
        raise MissingResultsFile(
            f"{collection_id} has no results file at {path} to build its dashboard from - "
            f"run `mothman dashboard rebuild-results` first, which writes one for every "
            f"collection, an empty one where nothing is recorded")
    with open(path) as f:
        return json.load(f)


def build_datasets(collection_id: str) -> list[dict]:
    """Every dataset the hierarchy declares for the collection, in order."""
    coll = collections.by_id(collection_id)
    payload = _payload(collection_id)
    manifest = sorted(payload["runs"], key=_run_date)
    results = payload["results"]
    dataset_stats = payload["dataset_stats"]

    # Every real check definition, active and retired - config-file parsing
    # only, no supply rows, so safe for any read-committed-history path.
    lifecycle_by_id = {c.check_id: c for c in collect_checks(None)}

    by_table = {d.table: [r for r in results if r["dataset_id"] == d.dataset_id]
                for d in coll.datasets}
    share_cross_table_results(results, by_table)
    return [build_one_table(coll, d, by_table[d.table], own_runs(manifest, d.table), dataset_stats,
                            lifecycle_by_id)
            for d in coll.datasets]


def build(collection_id: str) -> dict:
    """The collection's dashboard document, in the shape its file has always
    had - Birth Registrations' one dataset as the document itself (legacy
    flag), every other collection's under `datasets`."""
    datasets = build_datasets(collection_id)
    if "dashboard.single_dataset_document" in _legacy(collection_id):
        return datasets[0]
    return {"datasets": datasets}


def write(collection_id: str) -> str:
    """Build and write the collection's dashboard file, whole or not at all
    (another process may be reading it - CI, 2026-10-11)."""
    path = out_path(collection_id)
    data = build(collection_id)
    from qa_tools.common import atomic_file

    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_file.write_json(path, data)
    return path


if __name__ == "__main__":
    for _coll in collections.all_collections():
        print(f"Wrote {write(_coll.id)}")
    # Criterion 16 of REQ-PIPE-081: a WARNING, and the build still publishes.
    for line in census.build_warnings():
        print(line)
