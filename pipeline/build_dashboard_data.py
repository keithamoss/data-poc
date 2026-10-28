"""
One dashboard builder for every collection (REQ-DASH-244).

Reshapes a collection's results file (reports/<collection.results_file>, the
shared orchestrator's real dbt-core/Soda Core/datacontract-cli/Evidently
output, rebuilt from recorded history) into the JSON the dashboard's
drawer and chart code reads, one dataset object per dataset the hierarchy
declares, and writes it to reports/<collection.dashboard_file>.

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
- nothing differs by collection id (criterion 11): the places Birth
  Registrations' output differed were legacy flags, all retired by
  REQ-QAC-247 and REQ-PIPE-248.

A BUILD MAY READ RECORDED QA RESULTS, NEVER ACTUAL DATA, AND NEVER ANYTHING
ELSE (Keith, 2026-09-27): every input below is a results file, a decision
or filing the pipeline recorded, or configuration.

A COLLECTION WITH NO RECORDED RUNS is built too (criterion 6): each of its
declared datasets is written with an empty history, which the page renders
as never supplied or not owed yet - never as a missing collection.
"""
from __future__ import annotations

import json
import os

from pipeline import (acknowledgements, closed_slots, corrections, cross_table_grid,
                      cross_table_notices, excuses, held_back_notices,
                      file_check_panel, owed_nothing, placements, promotion_timeline,
                      recorded_arrival, red_promoted, slot_timeline, warehouse_counts)
from pipeline.dashboard_check_labels import (dashboard_status, display_name, measure, pooled_url_key,
                                             rank_for_headline, tool_ref, url_key)
from qa_tools import collections
from qa_tools.common import (agreement, amber_setting, asset_time, build_output, carry_forward, census,
                             config_yaml, drift_reference, hierarchy, qa_store, root_cause,
                             schedule_ended, supply_db, supply_status, turned_off)
from qa_tools.common.validate_check_lifecycle import collect_checks

ROOT = os.path.join(os.path.dirname(__file__), "..")
REPORTS = os.path.join(ROOT, "reports")


def results_path(collection_id: str) -> str:
    return os.path.join(build_output.reports_dir(REPORTS), collections.by_id(collection_id).results_file)


def out_path(collection_id: str) -> str:
    """The collection's dashboard file - in the real `reports/`, or under
    `--out-dir` in the build's own (REQ-TEST-281)."""
    return os.path.join(build_output.reports_dir(REPORTS), collections.by_id(collection_id).dashboard_file)


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

def _contract(contract: str) -> dict:
    """A collection's contract, beside the hierarchy that names it."""
    return _contract_at(str(hierarchy.DATA_ASSET_YAML.parent / contract))


def _contract_at(path: str) -> dict:
    """The contract as it reads now, parsed only when its text has changed,
    and the caller's own copy (REQ-PIPE-254) - through config_yaml, which
    keys the parse on the content and deep-copies what it hands out."""
    return config_yaml.load(path)


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
    meta[TABLE_LEVEL_PSEUDO_COLUMN] = table_level
    meta[SUPPLY_LEVEL_PSEUDO_COLUMN] = SUPPLY_LEVEL_META
    meta[CROSS_TABLE_PSEUDO_COLUMN] = CROSS_TABLE_META
    return meta


def table_description(coll, dataset) -> str:
    return (_element(coll, dataset).get("description") or "").strip()


def _presented(coll) -> dict:
    from qa_tools.common import presentation

    return presentation.for_collection(coll.id)


# ---- the statistics, in the one recorded shape (REQ-PIPE-248) ---------------

def _row_count(stats: dict | None, table: str):
    """A run's recorded row count for `table` - absent, never zero, where the
    run could not read it (REQ-PIPE-105)."""
    return ((stats or {}).get("row_counts") or {}).get(table)


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


def _declaring_dataset(check_id: str) -> str | None:
    """The dataset a check is declared on, by the check id's own layout
    (asset.agency.collection.dataset.column.check_tool) - one reading of it,
    for every caller (functional critic on 7093c20)."""
    parts = check_id.split(".")
    return parts[3] if len(parts) >= 5 else None


def _between(check_id: str, reads: dict | None) -> dict | None:
    """The tables a cross-table check is between, by dataset id (post-build-
    review #253, Keith 2026-10-19): "Client reference" on the Client
    Register's page is three checks, one per table that reads it, and the
    row names which. From the tables its results RECORDED reading
    (REQ-PIPE-279 criterion 18), less the declaring dataset's own. None for a
    check that read only its own table."""
    if not reads:
        return None
    declared_on = _declaring_dataset(check_id)
    others = sorted({hierarchy.dataset_for_table(t).dataset_id for t in reads}
                    - {declared_on})
    return {"declared_on": declared_on, "reads": others} if others else None


def _supply_read(record: dict, table: str) -> str | None:
    """The supply of `table` a cross-table result is about (qa.check_read,
    REQ-PIPE-279 criterion 1): the one it READ, or the HELD one it was refused
    (criterion 15) - None where it had none, absent or no supply at all."""
    read = (record.get("reads") or {}).get(table) or {}
    return read.get("supply_id") if read.get("state") in (qa_store.READ, qa_store.HELD) else None


#: The recorded states a cross-table result is shown under on a page that is
#: not its declaring dataset's (REQ-PIPE-279 criteria 14 and 15, K2 = A).
_SHOWN_ELSEWHERE = (qa_store.READ, qa_store.HELD)


def _contested_read(read: dict | None) -> bool:
    """An ABSENT read of a table two files claim, naming them - about that
    contested pair, so it reaches the pair's page as REQ-DASH-264 criterion 3's
    "held or contested" asks, which REQ-PIPE-279 criteria 14 and 15 left out
    (PROVISIONAL, 2026-10-23, for Keith). Every other ABSENT read stays off."""
    read = read or {}
    return (read.get("state") == qa_store.ABSENT and bool(read.get("contested"))
            and bool(read.get("contested_files")))


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


def own_runs(manifest: list[dict], dataset_id: str, facts: dict[str, dict]) -> list[dict]:
    """The runs that are FOR this dataset (REQ-PIPE-105): one file is one
    arrival, so a six-table delivery is six runs and each belongs to one
    dataset - the one qa.run records it for (REQ-PIPE-279 criterion 17),
    never the one its id happens to spell. A run recorded for no dataset (a
    fixture's, a trial's) belongs to every dataset, as every run did before.
    """
    return [m for m in manifest
            if facts[m["run_id"]]["dataset_id"] in (None, dataset_id)]


def superseded_runs(facts: dict[str, dict], manifest: list[dict]) -> dict[str, dict]:
    """{run id: {replaced_by, supply_run}} for every run a newer run of the
    same supply replaced (post-build-review #266, Keith 2026-10-24, answer
    A): `replaced_by` the supply's next run, `supply_run` its current one -
    the run the page lists it by. By the recorded supply (qa.run's dataset
    and supply) and the opening order (rank) alone, never a run id's text or
    a day (REQ-PIPE-279 criterion 19). A readers-only run is about other
    supplies, so it replaces nothing and is replaced by nothing."""
    listed = {m["run_id"] for m in manifest}
    runs_of: dict[tuple[str, str], list[str]] = {}
    for run_id, fact in sorted(facts.items(), key=lambda item: item[1]["rank"]):
        if fact["supply_id"] is None or fact["scope"] == "readers":
            continue
        runs_of.setdefault((fact["dataset_id"], fact["supply_id"]), []).append(run_id)
    out: dict[str, dict] = {}
    for runs in runs_of.values():
        current = [r for r in runs if r in listed]
        if not current:
            continue
        for older, newer in zip(runs, runs[1:]):
            if older in listed:
                break
            out[older] = {"replaced_by": newer, "supply_run": current[-1]}
    return out


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

    THE TABLES IT RECORDED READING (REQ-PIPE-279 criterion 18), never the
    checkout's current declarations - so editing what a check declares it
    reads re-places nothing already recorded. AND ONLY THOSE IT READ OR WAS
    HELD FROM (criterion 14, K2 = A): a result that read no supply of a table
    - ABSENT or NO-SUPPLY - is not about that table, so it stays on the page
    of the dataset it is declared on and goes nowhere else.
    """
    for r in results:
        for other, read in sorted((r.get("reads") or {}).items()):
            if read.get("state") not in _SHOWN_ELSEWHERE and not _contested_read(read):
                continue
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
                    lifecycle_by_id: dict, *, facts: dict[str, dict],
                    all_runs: list[dict] | None = None,
                    warehouse_cache: dict | None = None,
                    superseded: dict[str, dict] | None = None,
                    not_in_agreement: dict[str, dict] | None = None) -> dict:
    """One dataset's page. `manifest` is its own runs; `all_runs` is every
    run in the collection, so a result recorded under another table's run -
    a re-check re-running this table's cross-table checks - is placed and
    named (post-build-review #253). `facts` is the results file's run_facts:
    each run's dataset, scope, supply, cause and rank, from qa.run
    (REQ-PIPE-279 criteria 16 and 17) - what every placement and ordering
    below reads, never a run id, a day or a recording time (criterion 19).
    `warehouse_cache` is shared across the collection's pages: every
    dataset's slot timeline and the owed re-evaluations, read once, the first
    time a cross-table card needs its counted points (REQ-PIPE-269,
    pipeline.warehouse_counts). `superseded` is superseded_runs(): each
    card carries those runs' entries apart from its history, for the page to
    show while they were current and for its counted points to count from.
    """

    table, dataset_id = dataset.table, dataset.dataset_id
    view = {} if warehouse_cache is None else warehouse_cache
    slot_timelines = view.setdefault("timelines", {})

    def counted_points(check_id: str, history: list[dict]) -> dict:
        """The card's counted points, the collection's warehouse read the
        first time a card asks (a one-table collection never does)."""
        if "warehouse" not in view:
            for d in coll.datasets:
                if d.dataset_id not in slot_timelines:
                    slot_timelines[d.dataset_id] = slot_timeline.for_dataset(d.dataset_id)
            view["warehouse"] = supply_status.HoldingsTimeline(slot_timelines)
            with supply_db.connect(read_only=True, label="mothman:warehouse-counts") as conn:
                view["owed"] = supply_status.owing(conn)
        return warehouse_counts.points(dataset_id, check_id, history,
                                       warehouse=view["warehouse"], owed=view["owed"])
    meta = column_meta(coll, dataset)
    all_columns = list(meta)
    stats_spec = collections.adapter(coll).stats
    aggregates = stats_spec.aggregates
    value_count_cols = {col for (t, col) in stats_spec.value_counts if t == table}

    by_column: dict[str, dict[str, dict]] = {}
    # A CHECK THAT COULD NOT BE EVALUATED (post-build-review #77) arrives
    # under a pseudo-tool with a check_name of its own, so keying it like
    # a real result would open a SECOND card for the same check. Real
    # results go first so every check's card exists, and each can't-run
    # record then joins the card with its check_id.
    results = ([r for r in results if not _not_evaluated_reason(r)]
               + [r for r in results if _not_evaluated_reason(r)])
    for r in results:
        if r.get("reads"):
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
            "status_by_run": {}, "reference": {}, "not_evaluated": {}, "at": {}, "reads": {},
            "unreadable": {}, "due_at": {},
        })
        slot["reads"][r["run_id"]] = r.get("reads")
        slot["at"][r["run_id"]] = r.get("run_timestamp")
        slot["not_evaluated"][r["run_id"]] = _not_evaluated_reason(r)
        # WHICH TABLE IT COULD NOT READ, AND WHY, from the record's structured
        # fields (REQ-DASH-204 criterion 10) - the one reading root_cause has.
        if slot["not_evaluated"][r["run_id"]]:
            slot["unreadable"][r["run_id"]] = root_cause.blocking_tables(r) or None
            slot["due_at"][r["run_id"]] = r.get("unrunnable_due_at")
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

    def rank(run_id: str) -> int:
        return facts[run_id]["rank"]

    # IN RANK ORDER, the order the runs were opened (REQ-PIPE-279 criteria 16
    # and 19) - it was the receipt date, then run_index, then the run id.
    run_ids_in_order = sorted((m["run_id"] for m in manifest), key=rank)
    own_ids = set(run_ids_in_order)
    # THE OWN RUN OF EACH SUPPLY, so a result recorded under another table's
    # run is placed on the run of the supply it read.
    own_by_supply = {facts[r]["supply_id"]: r for r in run_ids_in_order
                     if facts[r]["supply_id"] is not None}
    # EVERY RUN'S DATE, the dataset's own and the rest (#253), for display.
    all_runs = manifest if all_runs is None else all_runs
    run_date_by_id = {m["run_id"]: _run_date(m) for m in all_runs}
    other_run_ids = [m["run_id"] for m in all_runs if m["run_id"] not in own_ids]
    # THE RUNS A NEWER RUN OF THE SAME SUPPLY REPLACED (post-build-review
    # #266), in rank order, each dated as the run its supply is listed by.
    superseded = superseded or {}
    replaced_ids = sorted(superseded, key=rank)
    for run_id in replaced_ids:
        run_date_by_id.setdefault(run_id, run_date_by_id.get(superseded[run_id]["supply_run"]))
    # THE NEWEST RUNS THAT MEASURED THIS TABLE, not simply the newest runs
    # (REQ-PIPE-105): a run whose table was contested or held has nothing of
    # its own to show. None for a dataset never supplied (criterion 6).
    measured = [r for r in run_ids_in_order
                if _row_count(dataset_stats.get(r), table) is not None]
    measured = measured or run_ids_in_order
    latest_run = measured[-1] if measured else None
    prev_run = measured[-2] if len(measured) > 1 else latest_run
    # A run measures only what it could read (REQ-PIPE-105), so a table can
    # be missing from a run's counts - absent here, never zero.
    row_count_by_run = {run_id: _row_count(st, table)
                        for run_id, st in dataset_stats.items()}

    columns_out = []
    for col in all_columns:
        logical_type, desc = meta[col]
        checks_for_col = by_column.get(col, {})
        agg_spec = aggregates.get((table, col))

        checks_out = []
        # A CHECK WHOSE ONLY RESULT HERE IS A CONTESTED READ STILL GETS ITS
        # CARD (Keith, 2026-10-24, reversing provisional #22) - here, BESIDE
        # the column's checks rather than among them, so no count, status,
        # headline or column statistic ever reads it (criterion 14). The page
        # shows it only while that pair blocks the table.
        contested_only = []
        for slot in checks_for_col.values():
            engine, check_name = slot["engine"], slot["check_name"]
            attach_aggregate = agg_spec is not None and check_name in agg_spec["check_names"]
            history, elsewhere, contested_reads, replaced = [], [], [], []
            for run_id in run_ids_in_order + other_run_ids + replaced_ids:
                if run_id not in slot["by_run"]:
                    continue
                was = superseded.get(run_id)
                own = (run_id in own_ids if was is None
                       else facts[run_id]["dataset_id"] == dataset_id)
                if was is not None and not own and (
                        _contested_read((slot["reads"].get(run_id) or {}).get(table))
                        or run_date_by_id.get(run_id) is None):
                    continue
                aggregate_values = None
                if attach_aggregate:
                    aggregate_values = (dataset_stats.get(run_id) or {}).get(
                        "check_aggregates", {}).get(f"{table}.{col}")
                # Why this run's check could NOT be evaluated, or None for a
                # real verdict - never a value or a pass.
                not_evaluated = slot["not_evaluated"].get(run_id)
                fact = facts[run_id]
                read = _supply_read({"reads": slot["reads"].get(run_id)}, table)
                this_read = (slot["reads"].get(run_id) or {}).get(table)
                # A CONTESTED PAIR'S READ IS KEPT APART (PROVISIONAL, see
                # _contested_read): never in the history or a count, which
                # criterion 14 keeps for what read a supply of this table -
                # only for the page to show while that pair blocks it.
                into = (replaced if was is not None else history if own
                        else contested_reads if _contested_read(this_read) else elsewhere)
                into.append({
                    # A REPLACED RUN'S ENTRY names what replaced it and the run
                    # its supply is listed by (post-build-review #266).
                    **({"replaced_by": was["replaced_by"], "supply_run": was["supply_run"]}
                       if was is not None else {}),
                    "run_id": run_id, "run_date": run_date_by_id[run_id],
                    # ITS PLACE, ITS SUPPLY, ITS CAUSE AND WHAT IT READ, from the
                    # record (REQ-PIPE-279 criterion 16): the rank orders, the
                    # supply is this dataset's that the result is about.
                    "rank": fact["rank"],
                    "supply_id": fact["supply_id"] if own else read,
                    "cause": fact["cause"],
                    "reads": slot["reads"].get(run_id),
                    # THIS TABLE'S STATE IN IT, for a held table's page to show
                    # the rows that met its held supply (criterion 15).
                    "read_state": None if own else (
                        (slot["reads"].get(run_id) or {}).get(table) or {}).get("state"),
                    # WHEN IT WAS RECORDED - for its date, never its order -
                    # AND UNDER WHOSE RUN where that is another table's
                    # (post-build-review #253): qa.run's dataset (criterion 17).
                    "recorded_at": slot["at"].get(run_id),
                    "recorded_by": None if own else fact["dataset_id"],
                    # WHICH OWN RUN IT IS ABOUT: the run of the supply it
                    # recorded reading (REQ-PIPE-279 criterion 19).
                    "read_run": None if own else own_by_supply.get(read),
                    # WHICH KIND OF RUN (REQ-DASH-264 criterion 7), by qa.run's
                    # scope: only a re-check is said to be one on the page.
                    "recorded_in": None if own else (
                        "arrival" if fact["scope"] == "arrival" else "re-check"),
                    "value": slot["by_run"][run_id],
                    "row_count_total": slot["row_count_total"].get(run_id),
                    "row_count_invalid": slot["row_count_invalid"].get(run_id),
                    "failing_sample_keys": slot["failing_sample_keys"].get(run_id) or [],
                    "aggregate_values": aggregate_values,
                    "status": slot["status_by_run"].get(run_id),
                    "reference": slot["reference"].get(run_id),
                    "not_evaluated": not_evaluated,
                    # THE TABLES IT COULD NOT READ AND THEIR CODES, and when a
                    # not-yet-due one falls due (REQ-DASH-204 criterion 10).
                    **({"unreadable": slot["unreadable"][run_id]}
                       if slot["unreadable"].get(run_id) else {}),
                    **({"due_at": slot["due_at"][run_id]} if slot["due_at"].get(run_id) else {}),
                    **({"contested_files": this_read["contested_files"]}
                       if into is contested_reads else {}),
                })
            history = sorted(history + elsewhere, key=lambda h: h["rank"])
            if not history and not contested_reads and not replaced:
                continue
            # THE NEWEST RESULT IS CURRENT, whichever run recorded it (#253):
            # the dataset's newest measured run unless a result recorded
            # under another table's run is newer - by rank (REQ-PIPE-279).
            current_value = slot["by_run"].get(latest_run, 0)
            current_status = slot["status_by_run"].get(latest_run)
            own_rank = rank(latest_run) if latest_run in slot["by_run"] else None
            newer = [h for h in elsewhere if own_rank is None or h["rank"] > own_rank]
            if newer:
                newest = max(newer, key=lambda h: h["rank"])
                current_value, current_status = newest["value"], newest["status"]
            engine_short = ENGINE_SHORT.get(engine, engine)
            lifecycle = lifecycle_by_id.get(slot["check_id"])
            (checks_out if history or replaced else contested_only).append({
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
                "current": current_value,
                "current_status": current_status,
                "between": (_between(slot["check_id"],
                                     {t for got in slot["reads"].values() for t in (got or ())})
                            if col == CROSS_TABLE_PSEUDO_COLUMN else None),
                "previous": slot["by_run"].get(prev_run, 0),
                "history": history,
                # THE REPLACED RUNS' ENTRIES, apart from the history so nothing
                # that reads it whole counts a supply twice: the page shows one
                # from when it was recorded until the run that replaced it was
                # (post-build-review #266, Keith 2026-10-24, answer A).
                **({"superseded": replaced} if replaced else {}),
                # WHICH OF THEM COUNTS TOWARD THE SUPPLY ON SHOW, ON EACH DATE
                # (REQ-PIPE-269; post-build-review #262 R4) - worked out here
                # by the gate's own function, looked up by the page - from
                # every run about it, as results_about reads them.
                **({"counted": counted_points(
                    slot["check_id"], sorted(history + replaced, key=lambda h: h["rank"]))}
                   if col == CROSS_TABLE_PSEUDO_COLUMN else {}),
                "contested_reads": sorted(contested_reads, key=lambda h: h["rank"]),
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

        _disambiguate_pooled_keys(checks_out + contested_only)
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
                # RANKED LIKE EVERY OTHER ENTRY (REQ-PIPE-279 criterion 16), on
                # its run's own point - an unranked entry among ranked ones
                # leaves the page's points in no order at all.
                "history": [{"run_id": m["run_id"], "run_date": _run_date(m), "value": 0,
                             "status": "inactive", "rank": rank(m["run_id"]),
                             "supply_id": facts[m["run_id"]]["supply_id"],
                             "cause": facts[m["run_id"]]["cause"]}
                            for m in sorted(manifest, key=lambda m: rank(m["run_id"]))],
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
            **({"contested_only": contested_only} if contested_only else {}),
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

    # THE LINES SAYING ANOTHER TABLE COULD NOT BE READ (REQ-DASH-204), per
    # supply and date, from the cards above and the decision log.
    if "log" not in view:
        with supply_db.connect(read_only=True, label="mothman:cross-table-notices") as conn:
            view["log"] = cross_table_notices.read_log(conn, coll.id)
    cross_cards = [ck for c in columns_out if c["name"] == CROSS_TABLE_PSEUDO_COLUMN
                   for ck in c["checks"] if ck.get("check_id")
                   and _declaring_dataset(ck["check_id"]) == dataset_id]
    own_cards = [ck for c in columns_out if c["name"] != CROSS_TABLE_PSEUDO_COLUMN
                 for ck in c["checks"] if ck.get("check_id")]
    period_of = {facts[r]["supply_id"]: arrival_by_run.get(r, {}).get("slot")
                 for r in run_ids_in_order if facts[r]["supply_id"] is not None}
    no_promoted = cross_table_notices.no_promoted(dataset_id, table, cross_cards, own_cards,
                                                  period_of, view["log"])

    # WHERE EACH CROSS-TABLE RESULT SITS, WHAT IT READ, AND THE WAREHOUSE'S
    # STATUS ON AN AWAITING LINE (REQ-DASH-272), as at every date: placed on
    # each entry, the owed re-check's words on each counted point, the clause
    # per supply - from the slot timelines and the decision log.
    for d in coll.datasets:
        if d.dataset_id not in slot_timelines:
            slot_timelines[d.dataset_id] = slot_timeline.for_dataset(d.dataset_id)
    if "slots" not in view:
        view["slots"] = cross_table_grid.Slots(slot_timelines)
        view["receipts"] = cross_table_grid.Receipts(view["log"].receipts)
    page_cross = [ck for c in columns_out if c["name"] == CROSS_TABLE_PSEUDO_COLUMN
                  for ck in c["checks"] if ck.get("check_id")]
    phrases = cross_table_grid.Phrases()
    cross_table_grid.place_entries(dataset_id, table, page_cross, period_of, slots=view["slots"],
                                   log=view["log"], receipts=view["receipts"], phrases=phrases)
    for ck in page_cross:
        cross_table_grid.owed_words(ck, view["log"], view["receipts"])
    if "runs_by_supply" not in view:
        view["runs_by_supply"] = {}
        for fact in facts.values():
            if fact.get("supply_id"):
                view["runs_by_supply"].setdefault(fact["supply_id"], []).append(fact)
    promotion_words = cross_table_grid.promotion_words(
        dataset_id, period_of, log=view["log"], slots=view["slots"], receipts=view["receipts"],
        runs=view["runs_by_supply"],
        related={d for ck in page_cross for b in [ck.get("between") or {}]
                 for d in [b.get("declared_on"), *(b.get("reads") or ())] if d and d != dataset_id})
    # HELD BACK WITH ITS DELIVERY (REQ-DASH-275): the notice, the chain to its
    # root and what a root holds back, per supply and date, from the decision
    # log's 'promotion-withheld' entries.
    if "involvement" not in view:
        view["involvement"] = held_back_notices.involved(view["log"])
    held_back = held_back_notices.for_dataset(dataset_id, list(period_of), view["log"],
                                              view["receipts"], view["involvement"])
    # OFF THE HISTORY ENTRIES BEFORE THEY ARE WRITTEN: the page reads every
    # entry on every date it draws (the weekly trends), and entries of more
    # than one shape cost it twice the time - so each card carries its
    # entries' placements BESIDE them, by rank, and the structured fields only
    # the build reads go no further.
    for c in columns_out:
        for ck in c["checks"]:
            side = {}
            for h in [*ck.get("history", []), *ck.get("superseded", []),
                      *ck.get("contested_reads", [])]:
                if "placed" in h:
                    side[str(h["rank"])] = h.pop("placed")
                h.pop("unreadable", None)
                h.pop("due_at", None)
            if side:
                ck["placed"] = side
    health = red_promoted.for_dataset(dataset_id)
    raw_slots = slot_timelines.get(dataset_id) or slot_timeline.for_dataset(dataset_id)
    panel = promotion_timeline.for_dataset(dataset_id, raw_slots)
    warehouse_clause = cross_table_grid.clause_points(
        dataset_id, period_of, timeline=panel, health=health, run_of=own_by_supply,
        log=view["log"], receipts=view["receipts"])

    presented = _presented(coll)
    # What each slot held, read once and shared by the embeds below.
    slot_timeline_raw = slot_timelines.get(dataset_id)
    if slot_timeline_raw is None:
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
        "promotedHealth": health,
        # THE AWAITING LINE'S WAREHOUSE CLAUSE (REQ-DASH-272 criteria 1 to 5):
        # {supply: [{on, clause, status, tail}]}, looked up by date.
        "warehouseClause": warehouse_clause,
        # A JOINT OR RE-CHECKED RULE PROMOTION'S HISTORY ROW (REQ-DASH-272
        # criterion 20): {decision id: segments}.
        "promotionWords": promotion_words,
        # THE GRID'S NOTES AND SENTENCES, each once (REQ-DASH-272): a cell's
        # `placed` point names them by index.
        "xtPhrases": phrases.items,
        # HELD BACK WITH ITS DELIVERY (REQ-DASH-275): {supply: [{on, notice,
        # holding}]}, looked up by date.
        "heldBack": held_back,
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
        "promotionTimeline": panel,
        # A NEWER SUPPLY THAT COULD BE CARRIED FORWARD (REQ-PIPE-271 criterion
        # 7): each warning with the days it stood, its words worked out here.
        "carryForwardWarnings": carry_forward.for_dashboard(dataset_id),
        # CHECKS LEFT OUT OF A RUN BECAUSE A TABLE THEY READ IS NOT PART OF THE
        # AGREEMENT FOR ITS PERIOD (REQ-PIPE-270 criterion 9): neither red nor a
        # result, so the page says why each did not run - per run of this
        # dataset, by check, with its period and the recorded reason.
        # ANOTHER TABLE THIS SUPPLY'S CROSS-TABLE CHECKS COULD NOT READ
        # (REQ-DASH-204): {supply: [{on, lines, ownRed}]}, looked up by date.
        "noPromoted": no_promoted,
        "notInAgreement": [
            {"runId": run_id, "supplyId": facts[run_id]["supply_id"], "checkId": check,
             "reason": why}
            for run_id, checks in sorted((not_in_agreement or {}).items(),
                                         key=lambda kv: facts.get(kv[0], {}).get("rank", 0))
            if run_id in facts and facts[run_id]["dataset_id"] == dataset_id
            for check, why in checks.items()],
        "arrivalHistory": arrival_history,
        "arrivalByRun": arrival_by_run,
        "rowCount": row_count_by_run.get(latest_run),
        "prevRowCount": row_count_by_run.get(prev_run),
        # Each run as the PAGE sees it: the manifest entry plus a derived
        # `run_date`. Spread-then-add rather than a hand-listed copy: a
        # hand-maintained allowlist silently drops every field added later
        # (CLAUDE.md's standing lesson from item 74). Its rank too, which the
        # supply history orders by (post-build-review #262 F5).
        "runs": [{**m, "run_date": _run_date(m), "rank": rank(m["run_id"]),
                  # ITS SUPPLY (qa.run.supply_id), which a cross-table card's
                  # counted points are keyed by (REQ-PIPE-269).
                  "supply_id": facts[m["run_id"]]["supply_id"]} for m in manifest],
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
    # WHAT EACH RUN IS (REQ-PIPE-279 criteria 16 and 17), refused where the
    # file predates it rather than read as runs that are nothing.
    if "run_facts" not in payload:
        raise ValueError(
            f"{coll.id}: the results file has no run_facts - written before REQ-PIPE-279. "
            f"Rebuild it: `mothman dashboard rebuild-results`.")
    facts = payload["run_facts"]
    manifest = sorted(payload["runs"], key=lambda m: facts[m["run_id"]]["rank"])
    results = payload["results"]
    dataset_stats = payload["dataset_stats"]
    # ONE RECORDED SHAPE (REQ-PIPE-248): a record without `row_counts` was
    # written before it, and read as this shape it would say every table
    # measured nothing (post-build-review #236).
    for run_id, stats in dataset_stats.items():
        if "row_counts" not in stats:
            raise ValueError(
                f"{coll.id}: run {run_id}'s dataset stats have no row_counts - recorded in the "
                f"shape before REQ-PIPE-248. Regenerate the history: `mothman env "
                f"reset-synthetic`, then `mothman pipeline bootstrap`.")

    # Every real check definition, active and retired - config-file parsing
    # only, no supply rows, so safe for any read-committed-history path.
    lifecycle_by_id = {c.check_id: c for c in collect_checks(None)}

    by_table = {d.table: [r for r in results if r["dataset_id"] == d.dataset_id]
                for d in coll.datasets}
    share_cross_table_results(results, by_table)
    # WHAT EVERY PERIOD HELD, AND WHAT DECISIONS STILL OWE - read once for the
    # collection, the first time a card asks, so each card's counted points
    # are a walk in memory.
    cache: dict = {}
    # A READERS-ONLY RE-CHECK RECORDS NO dataset_stats (the knock-on's, REQ-PIPE-140
    # criterion 2), so it is not among the file's runs - and its results were
    # placed nowhere, leaving a page on the verdict it replaced (post-build-review
    # #264). It is a run of the collection all the same, dated by when it ran.
    known = {m["run_id"] for m in manifest}
    readers_runs: dict[str, dict] = {}
    for r in results:
        run_id = r.get("run_id")
        if (run_id not in known and run_id not in readers_runs and run_id in facts
                and facts[run_id]["scope"] == "readers"):
            readers_runs[run_id] = {"run_id": run_id, "received_at": r["run_timestamp"]}
    all_runs = sorted([*manifest, *readers_runs.values()],
                      key=lambda m: facts[m["run_id"]]["rank"])
    superseded = superseded_runs(facts, manifest)
    return [build_one_table(coll, d, by_table[d.table], own_runs(manifest, d.dataset_id, facts),
                            dataset_stats, lifecycle_by_id, facts=facts, all_runs=all_runs,
                            warehouse_cache=cache, superseded=superseded,
                            not_in_agreement=payload.get("not_in_agreement") or {})
            for d in coll.datasets]


def build(collection_id: str) -> dict:
    """The collection's dashboard document: its datasets under `datasets`,
    one shape for every collection (REQ-PIPE-248 criterion 2)."""
    return {"datasets": build_datasets(collection_id)}


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
