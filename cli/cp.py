"""mothman cp - Child Protection commands (plans/tooling.md #1 Phases
1-2): generate-synthetic-data and the Quality Assurance flow against
Synthetic and Local files source modes. Same wizard/flags duality as
cli/bdm.py, adapted for CP's real differences from Birth Registrations:
a 6-table-per-run collection (not one CSV), no row-count-growth check
at all, and orchestrate_cp.run_single() needing all 6
tables already loaded into that run's warehouse (via
build_cp_warehouses.add_table_to_run()) before it's called at all.

The Local files mode (Phase 2) folds in qa_tools/cp/check_delivery.py's
own retired standalone-CLI logic verbatim (that module is gone - this is
now the only place it runs from, per CLAUDE.md's "mothman is the only
programmatic access point" convention) - same real dbt-core/Soda Core/
datacontract-cli/Evidently chain via orchestrate_cp.run_single(), just
reached from a browsable questionary.path() prompt or --folder/
--reference-folder flags instead of a positional folder argument."""
from __future__ import annotations
import dataclasses
import os
import sys
import tempfile
from datetime import date

import rich_click as click
from rich.console import Console
from rich.table import Table

from qa_tools.cp import build_cp_warehouses, cp_common, orchestrate_cp
from qa_tools.common import s3_source
from qa_tools.common.git_identity import get_run_by
from qa_tools.common import hand_filing, hierarchy
from qa_tools.common import supply_db
from qa_tools.common import trial as trial_mod
from qa_tools.common.qa_results_reader import list_run_ids

from . import common, filing_tui
from qa_tools.common import asset_time

AGENCY_ID = cp_common.AGENCY_ID
COLLECTION_ID = cp_common.COLLECTION_ID
TABLES = cp_common.TABLES
CONTRACT_PATH = os.path.join(os.path.dirname(__file__), "..", "contract", "child-protection-contract.yaml")

console = Console()


def s3_config() -> dict:
    """The real s3Source/localSource/arrivalPattern config off this
    dataset's own contract YAML - see qa_tools.common.s3_source.
    dataset_s3_config()'s own docstring for the full account of how this
    got safely wired into the real contract (Phase 3, 2026-09-19)."""
    return s3_source.dataset_s3_config(CONTRACT_PATH)


def arrival_path(run_id: str) -> str:
    """Where this run's six CSVs actually arrived.

    REPLACED raw_dir()/<run_id>/ (REQ-PIPE-102, 2026-09-27). CP staging
    used to keep a second copy of every delivered file under
    data/cp_raw/<run_id>/, and these paths read it back. The delivery
    is the arrival and always held the same six files; the copy existed
    only because the CP tools once read CSVs off disk.

    Raises rather than returning a path that is not there, because
    every caller is about to open six files in it.
    """
    from qa_tools.common import arrivals

    for arrival in arrivals.arrivals_for(COLLECTION_ID, "cp_run_"):
        if arrival.run_id == run_id:
            return str(arrival.path)
    raise click.ClickException(
        f"No arrival on disk for run_id={run_id!r} - run generate-synthetic-data first?")


def generated_output_dir() -> str:
    """Where `generate-synthetic-data` leaves its output, for the one
    line that reports it. CP writes deliveries and nothing else
    (REQ-PIPE-102); BDM's counterpart still has a raw drop alongside
    them, which is why this is a per-dataset accessor rather than one
    shared constant."""
    from generator import generate_cp_runs

    return str(generate_cp_runs.DELIVERIES_DIR)


def has_arrival(run_id: str) -> bool:
    """Is that run's delivery still on disk? Asked before offering a
    run as a reference, where the answer decides a fallback rather than
    an error."""
    try:
        arrival_path(run_id)
        return True
    except click.ClickException:
        return False



def generate_synthetic_data() -> None:
    """Runs the real generator directly - the same shape as cli/bdm.py's
    own generate_synthetic_data().

    THE TWO USED TO DIFFER. Birth Registrations went through
    pipeline.orchestrate, which also built a combined DuckDB warehouse of
    every run; Child Protection never had one. That warehouse is gone
    (REQ-PIPE-087 criterion 1), so both datasets now do the same thing
    here: generate, and let staging happen per arrival as QA runs
    (REQ-PIPE-068)."""
    from generator import generate_cp_runs
    generate_cp_runs.main()
    # THE MAP IS REBUILT IN THE SAME ACT (REQ-GEN-045 criterion 3).
    # A map regenerated separately is a map that disagrees with the
    # history the first time somebody regenerates one and not the
    # other - and it disagrees silently, because both files look
    # fine on their own.
    from qa_tools.common import scenario_map
    scenario_map.write_map()


def load_manifest() -> list[dict]:
    """Every arrival, RECOGNISED FROM DISK (REQ-GEN-043).

    Named `load_manifest` still because every caller here treats it as
    "the list of runs", but it no longer opens the generator's
    manifest.json - that is bookkeeping, and reading it would file
    supplies from a declaration rather than from what arrived.
    """
    from qa_tools.common import arrivals
    return [a.as_entry()
            for a in arrivals.arrivals_for("child-protection", "cp_run_")]


def manifest_exists() -> bool:
    """Is there anything to pick from? A real question now: with no
    deliveries on disk there are no arrivals, which is what the picker
    needs to know."""
    return bool(load_manifest())


def default_reference(manifest: list[dict]) -> str:
    """The last Promoted run for this collection, falling back to the
    manifest's own first (always-clean-by-construction) entry - same
    reasoning as cli/bdm.py's default_reference(), except CP has no
    per-reference CSV filename to check for (a reference run's six
    tables are its delivery's own files, checked directly rather than
    inferred from a manifest `file` field CP's manifest doesn't
    have)."""
    promoted = list_run_ids(AGENCY_ID, COLLECTION_ID)
    if promoted:
        candidate = promoted[-1]
        if has_arrival(candidate):
            return candidate
    return manifest[0]["run_id"]


def _require_all_six(folder: str) -> None:
    """A CP delivery needs all 6 real tables - the cross-table checks
    cannot run on a partial set. Checked BEFORE anything is filed
    (REQ-PIPE-103), so an incomplete folder never becomes a delivery
    record of an arrival that could not be checked."""
    missing = [t for t in TABLES if not os.path.isfile(os.path.join(folder, f"{t}.csv"))]
    if missing:
        raise click.ClickException(
            f"{folder} is missing: {', '.join(f'{t}.csv' for t in missing)} - "
            f"a CP delivery needs all 6 real tables, the cross-table checks can't run on a partial set")


def _load_delivery_from_folder(folder: str, run_id: str, received_at=None) -> None:
    """Loads all 6 real tables for one run_id from an arbitrary folder
    into that run's warehouse - the retired qa_tools/cp/check_delivery.py
    CLI's own _load_delivery() logic, folded in here verbatim (Phase 2).
    Used by both Synthetic mode (_load_delivery(), pointed at the
    delivery this run arrived in) and Local files mode
    (run_check_local_folder(), pointed at whatever folder the operator
    browsed to)."""
    _require_all_six(folder)
    for table in TABLES:
        build_cp_warehouses.add_table_to_run(
            run_id, table, os.path.join(folder, f"{table}.csv"),
            received_at=received_at)


def _load_delivery(run_id: str) -> None:
    """Synthetic mode's own delivery loader - a thin wrapper around
    _load_delivery_from_folder() pointed at the delivery this run
    actually arrived in (REQ-PIPE-102; it used to be pointed at a
    second copy under data/cp_raw/<run_id>/)."""
    _load_delivery_from_folder(arrival_path(run_id), run_id)


def run_check(run_id: str, run_by: str, reference_run_id: str | None = None,
              on_step=None, *, keep: bool = True) -> tuple[list[dict], str]:
    """Runs the real check chain for one existing Synthetic manifest
    entry. Returns (results, recorded_run_id) - `run_id` itself when kept,
    a throwaway trial identity otherwise. See cli/bdm.py's run_check() for
    why it no longer writes into a throwaway directory first.

    Unlike BDM, orchestrate_cp.run_single() has no manifest-clobbering
    side effect to guard against (CP's manifest isn't touched by the
    real tool chain at all) - but it DOES require both this run's and
    the reference run's 6 tables already loaded into their own per-run
    warehouses before it's called, which _load_delivery() above does for
    each."""
    manifest = load_manifest()
    if not any(e["run_id"] == run_id for e in manifest):
        raise click.ClickException(
            f"No manifest entry for run_id={run_id!r} - run generate-synthetic-data first?")
    entry = next(e for e in manifest if e["run_id"] == run_id)

    # NO DEFAULT REFERENCE ANY MORE - see cli/bdm.py's run_check() for
    # the full note (REQ-QAC-108 criterion 4).
    if reference_run_id is not None and not has_arrival(reference_run_id):
        raise click.ClickException(
            f"Reference run {reference_run_id!r}'s delivery isn't on disk - "
            f"run generate-synthetic-data first?")

    # KEEP OR TRIAL IS DECIDED BEFORE ANYTHING IS STAGED - see cli/bdm.py's
    # run_check() for the whole reasoning (REQ-PIPE-089 criterion 8).
    #
    # AND BEFORE, NOT AFTER, THE LOAD - which is a real bug this had for
    # one commit. A run's staged tables are named for its run id
    # (`staging.cp_clients__<run_id>`), so taking the trial identity after
    # _load_delivery() had already staged under the manifest's own id left
    # dbt looking for six tables that did not exist under that name. The
    # identity has to be settled before the first thing that uses it.
    recorded_run_id = run_id if keep else trial_mod.trial_run_id()
    entry = {**entry, "run_id": recorded_run_id}

    # ONLY WHERE AN OPERATOR NAMED ONE. A resolved reference's
    # distribution comes from what that run RECORDED (REQ-QAC-088), so
    # its rows do not need staging; a run somebody named by hand may
    # never have been checked here, which is what this load is for.
    if reference_run_id is not None:
        _load_delivery(reference_run_id)
    _load_delivery_from_folder(arrival_path(run_id), recorded_run_id)

    results = orchestrate_cp.run_single(entry, reference_run_id=reference_run_id, run_by=run_by,
                                        on_step=on_step)
    return results, recorded_run_id


def _check_filed_delivery(filed, run_by: str, on_step=None) -> list[dict]:
    """Stage, file, check and promote every arrival of a filed delivery,
    one at a time in the batch's own order - see
    orchestrate_cp.run_arrivals(). The arrivals come back from
    recognition, never from the folder's own listing."""
    found = hand_filing.arrivals_of(filed, "child-protection", "cp_run_")
    for arrival in found:
        (dataset_id, names), = arrival.files_by_dataset.items()
        table = hierarchy.dataset(dataset_id).table
        for ordinal, name in enumerate(sorted(names), start=1):
            build_cp_warehouses.add_table_to_run(
                arrival.run_id, table, str(arrival.path / name),
                ordinal=ordinal if len(names) > 1 else 0,
                received_at=arrival.received_at, dataset_id=dataset_id,
                delivery_name=arrival.delivery_name)
    return orchestrate_cp.run_arrivals(found, run_by, on_step=on_step)


def run_check_local_folder(folder: str, reference_folder: str, run_by: str,
                            run_id: str | None = None, run_date: str | None = None,
                            on_step=None, keep: bool | None = None,
                            originally: str | None = None, route: str = "folder",
                            storage_times: dict | None = None
                            ) -> tuple[list[dict], str, "hand_filing.Filed"]:
    """The Local files QA source mode's real check-running body (plans/
    tooling.md #1 Phase 2) - folds in qa_tools/cp/check_delivery.py's own
    retired logic: loads both folder and reference_folder's 6 real
    tables (an arbitrary, already-downloaded delivery - not tied to any
    Synthetic manifest entry) via _load_delivery_from_folder(), then
    reuses orchestrate_cp.run_single(), same entry point the Synthetic
    flow above and Thread B's Lambda handler call. Returns (results,
    tmp_results_dir) - same tmp-dir-first Promote pattern as run_check()."""
    run_date = run_date or asset_time.now().date().isoformat()
    # THE WHOLE FOLDER IS ONE DELIVERY (REQ-PIPE-103). Its six files
    # arrived together, and a delivery is the transport unit - filing
    # one delivery per file would invent six arrivals out of one.
    _require_all_six(folder)
    filed = common.file_or_trial(
        [os.path.join(folder, f"{t}.csv") for t in TABLES],
        "child-protection", "cp_run_", keep=keep, route=route, originally=originally,
        storage_times=storage_times)
    if run_id is not None and not filed.delivery_name:
        filed = dataclasses.replace(filed, run_id=run_id)
    if filed.delivery_name:
        # KEPT: SIX ARRIVALS, SIX RUNS, exactly as the batch would process
        # them (REQ-PIPE-105 criterion 1; Keith, 2026-10-02). Each is
        # staged under its own id, filed, overlaid on its period, checked
        # and promoted - and the drift reference comes from the recorded
        # history the way it does for any arrival, so --reference-folder
        # applies to a trial only.
        return _check_filed_delivery(filed, run_by, on_step), filed
    run_id = filed.run_id
    folder = os.path.dirname(filed.paths[0])
    reference_run_id = common.reference_run_id()

    _load_delivery_from_folder(reference_folder, reference_run_id)
    _load_delivery_from_folder(folder, run_id, received_at=filed.received_at)

    entry = {"run_id": run_id, "dirty_severity": None,
             "received_at": asset_time.isoformat(
                 filed.received_at
                 or asset_time.start_of_day(date.fromisoformat(run_date)))}
    try:
        results = orchestrate_cp.run_single(entry, reference_run_id=reference_run_id,
                                            run_by=run_by, on_step=on_step)
    finally:
        common.discard_reference(reference_run_id)
    return results, filed


def run_check_s3_delivery(bucket: str, delivery_prefix: str, reference_delivery_prefix: str, run_by: str,
                           run_id: str | None = None, run_date: str | None = None,
                           s3_client=None,
                                on_step=None, keep: bool | None = None,
                                originally: str | None = None
                                ) -> tuple[list[dict], str, "hand_filing.Filed"]:
    """The S3 QA source mode's real check-running body for Child
    Protection (plans/tooling.md #1 Phase 3) - a delivery here is all 6
    real table CSVs landing together under one shared S3 prefix
    (<s3Source><delivery_id>/), not a single flat key the way BDM's is.
    Downloads every object under delivery_prefix/reference_delivery_prefix
    (real boto3, via qa_tools.common.s3_source) into their own fresh
    local staging dirs, then reuses run_check_local_folder() exactly as
    if a human had downloaded the whole delivery themselves: S3 mode is
    "download, then Local files mode", not a third parallel
    check-running code path. Returns (results, tmp_results_dir) - same
    tmp-dir-first Promote pattern as run_check_local_folder()."""
    staging_dir = tempfile.mkdtemp(prefix="mothman-s3-")
    reference_staging_dir = tempfile.mkdtemp(prefix="mothman-s3-ref-")
    s3_source.download_prefix(bucket, delivery_prefix, staging_dir, s3_client=s3_client)
    s3_source.download_prefix(bucket, reference_delivery_prefix, reference_staging_dir, s3_client=s3_client)
    times = s3_source.last_modified(
        bucket, s3_source.list_keys(bucket, delivery_prefix, s3_client=s3_client),
        s3_client=s3_client)
    return run_check_local_folder(staging_dir, reference_staging_dir, run_by, run_id=run_id, run_date=run_date,
                                   on_step=on_step, keep=keep, originally=originally, route="s3",
                                   storage_times=times)


def run_check_single_table(table: str, file_path: str, run_by: str,
                            run_id: str | None = None, run_date: str | None = None,
                            on_step=None, keep: bool | None = None,
                            originally: str | None = None, route: str = "table",
                            storage_times: dict | None = None
                            ) -> tuple[list[dict], str, "hand_filing.Filed"]:
    """Single-table Child Protection QA (plans/tooling.md #1's own
    "Single-table Child Protection QA" design, Phase 3.5) - a real
    partial-resupply scenario (one table re-sent after a fix, the other
    5 unchanged) modeled at check-running time the same way
    generator/resupply.py already models it at data-generation time.

    CP's real dbt models need all 6 real tables present (ref()/
    source()), so a check against just one freshly-arrived table can't
    run a reduced set - it auto-pulls the OTHER 5 tables from the most
    recent Promoted run's own delivery, which holds all six of its
    tables exactly as the supplier sent them, via the exact same
    default_reference() the Synthetic flow already uses to pick its own
    reference run. That same run doubles as the Evidently drift baseline
    too - a real, known-good, already-Promoted 6-table delivery is
    exactly what a drift baseline needs anyway, so no separate reference
    flag is required here the way full-delivery Local files/S3 mode
    needs one.

    Requires at least one CP run already generated/Promoted locally
    (falls back to the manifest's own first entry, same as
    default_reference()) - there's no "other 5 tables" to pull from
    otherwise, a real and clearly-reported limitation, not a silent
    wrong answer."""
    manifest = load_manifest()
    other_tables_run_id = default_reference(manifest)
    if not has_arrival(other_tables_run_id):
        raise click.ClickException(
            f"No delivery on disk for run {other_tables_run_id!r} (the last Promoted/fallback run) - "
            f"run generate-synthetic-data first? Single-table mode needs a known-good delivery "
            f"already on disk to source the other 5 tables from.")

    run_date = run_date or asset_time.now().date().isoformat()
    # ONE FILE IS A ONE-FILE DELIVERY (REQ-PIPE-103 criterion 7), which
    # is what a partial resupply actually is: the supplier re-sent one
    # table and nothing else.
    filed = common.file_or_trial([file_path], "child-protection", "cp_run_", keep=keep,
                                 route=route, originally=originally,
                                 storage_times=storage_times)
    if run_id is not None and not filed.delivery_name:
        filed = dataclasses.replace(filed, run_id=run_id)
    run_id = filed.run_id
    file_path = filed.paths[0]

    _load_delivery(other_tables_run_id)  # full 6-table warehouse, doubles as the Evidently reference

    build_cp_warehouses.add_table_to_run(run_id, table, file_path,
                                          received_at=filed.received_at)
    # THE OTHER FIVE ARE BORROWED, NEVER RE-STAGED (REQ-PIPE-103). They
    # were staged when they really arrived, in the run this one is
    # reading them from; staging them again under THIS arrival would
    # record five tables as having arrived in a delivery that carried
    # one. supply_db.borrow_views() gives the run a view onto each
    # instead, which is exactly what "unchanged since last time"
    # means.
    with supply_db.connect(label="mothman:cp-single-table") as conn:
        borrowed = supply_db.borrow_views(
            conn, run_id, other_tables_run_id, [t for t in TABLES if t != table])
    missing = sorted({t for t in TABLES if t != table} - set(borrowed))
    if missing:
        raise click.ClickException(
            f"run {other_tables_run_id!r} has no resolved supply for "
            f"{', '.join(missing)}, so the other tables cannot be read from it - "
            f"CP's cross-table checks need all six.")

    entry = {"run_id": run_id, "dirty_severity": None,
             "received_at": asset_time.isoformat(
                 filed.received_at
                 or asset_time.start_of_day(date.fromisoformat(run_date)))}
    # THE BORROWED TABLES AND THE DRIFT REFERENCE ARE NOT THE SAME
    # QUESTION, and they used to share an answer. other_tables_run_id
    # is which run's other five tables this single-table check stands
    # beside; the drift reference is which period's supply it is
    # measured against, which the orchestrator now resolves from the
    # records (REQ-QAC-108).
    results = orchestrate_cp.run_single(entry, reference_run_id=None, run_by=run_by,
                                        on_step=on_step)
    return results, filed


def run_check_s3_single_table(bucket: str, table: str, key: str, run_by: str,
                               run_id: str | None = None, run_date: str | None = None,
                               s3_client=None,
                                on_step=None, keep: bool | None = None,
                                originally: str | None = None
                                ) -> tuple[list[dict], str, "hand_filing.Filed"]:
    """Single-table Child Protection QA's S3 source mode (Phase 3.5) -
    downloads the one real table object (real boto3, via
    qa_tools.common.s3_source), then reuses run_check_single_table()
    exactly as if a human had downloaded it themselves - S3 mode is
    "download, then Local files mode" here too, same as the full-delivery
    S3 mode above."""
    staging_dir = tempfile.mkdtemp(prefix="mothman-s3-")
    local_path = s3_source.download_key(bucket, key, staging_dir, s3_client=s3_client)
    return run_check_single_table(table, local_path, run_by, run_id=run_id, run_date=run_date,
                                   on_step=on_step, keep=keep, originally=originally, route="s3",
                                   storage_times=s3_source.last_modified(
                                       bucket, [key], s3_client=s3_client))


_STATUS_STYLE = {"pass": "green", "warn": "yellow", "fail": "red", "error": "bold red"}


def report_table(results: list[dict], run_id: str) -> Table:
    table = Table(title=f"Quality Assurance report - {run_id}")
    table.add_column("Tool")
    table.add_column("Check")
    table.add_column("Status")
    for r in results:
        style = _STATUS_STYLE.get(r.get("status"), "")
        status = r.get("status", "?")
        table.add_row(r.get("engine", "?"), r.get("check_id") or r.get("name", "?"),
                      f"[{style}]{status}[/{style}]" if style else status)
    n_fail = sum(1 for r in results if r.get("status") in ("fail", "error"))
    n_warn = sum(1 for r in results if r.get("status") == "warn")
    n_pass = sum(1 for r in results if r.get("status") == "pass")
    table.caption = f"{n_pass} pass / {n_warn} warn / {n_fail} fail-or-error, {len(results)} checks total"
    return table


def has_failures(results: list[dict]) -> bool:
    return any(r.get("status") in ("fail", "error") for r in results)


def picker_choices(manifest: list[dict]) -> list[str]:
    # See cli/bdm.py's identical picker.
    return [f'{e["run_id"]}  ({asset_time.local_date(e["received_at"])}, {e["delivery"]})'
            for e in manifest]


def run_id_from_choice(choice: str) -> str:
    return choice.split()[0]


_SOURCE_SYNTHETIC = "Synthetic - pick or generate a run"
_SOURCE_LOCAL_FOLDER = "Local files - a delivery folder you've already downloaded"
_SOURCE_S3 = "S3 - browse the real raw-data bucket"
_SOURCE_LOCAL_FILE = "Local file - a CSV you've already downloaded"

_DELIVERY_FULL = "Full delivery - all 6 real tables"
_DELIVERY_SINGLE_TABLE = "Single table - a partial resupply (one table only)"


def _report_synthetic(results: list[dict], recorded_run_id: str, keep: bool,
                       *, interactive: bool) -> None:
    """Report a Synthetic-mode check and say what became of it - see
    cli/bdm.py's counterpart for why the "Promote this run?" question
    this replaces could not survive REQ-PIPE-089 criterion 8."""
    console.print(report_table(results, recorded_run_id))
    if not keep:
        console.print(f"TRIAL {recorded_run_id} - the real tools ran against the same rows and "
                       "nothing was recorded.", style="dim")
    elif interactive:
        common.report_recorded(recorded_run_id, len(results))
        # AND IF THIS RUN LEFT ITS SUPPLY WAITING ON A PERSON, OFFER THE
        # DECISION HERE (REQ-GHUB-082 criterion 17), through the same
        # implementation the standing queue uses. Before the publish
        # offer, because promoting a supply changes what a publish would
        # publish - asking the other way round would republish the state
        # the operator was about to change.
        filing_tui.offer_after_run(COLLECTION_ID, recorded_run_id)
        # AND THEN, ONLY THEN, THE OFFER (REQ-PIPE-092 criterion 14).
        # After the panel rather than before it: the operator has just
        # been told what was recorded, which is what they need in order
        # to answer this.
        common.offer_to_publish()
    else:
        console.print(f"Recorded {len(results)} results for {recorded_run_id}", style="green")


def _finish_supply(results: list[dict], filed) -> None:
    """Report a hand-supplied check, and say what the operator already
    decided (REQ-PIPE-103 criterion 8) - see cli/bdm.py's counterpart for
    why there is no second question, and why the copy-into-the-tree step
    this used to end with is gone."""
    console.print(report_table(results, filed.run_id))
    common.say_what_it_did(filed.run_id, filed.delivery_name)
    # A KEPT run that left its supply waiting offers the decision here
    # (REQ-GHUB-082 criterion 17), as the synthetic route always did -
    # post-build-review #82 found the hand-filed routes never asking. A
    # trial filed nothing, so there is nothing of its own to decide.
    if filed.delivery_name:
        filing_tui.offer_after_run(COLLECTION_ID, filed.run_id)


def run_qa_interactive(commit_default: bool = False) -> None:
    """The Quality Assurance flow's real body for Child Protection,
    called from both `mothman cp qa` (no --run-id/--folder given, a real
    terminal) and the TUI main menu - one real implementation across
    both the Synthetic and Local files source modes (plans/tooling.md #1
    Phases 1-2), same upfront-git-identity reasoning as cli/bdm.py's own
    run_qa_interactive()."""
    run_by = get_run_by()

    delivery_scope = common.select(
        "Full delivery or single table?", [_DELIVERY_FULL, _DELIVERY_SINGLE_TABLE],
        flag_hint="mothman cp qa --run-id <run_id> / mothman cp qa --table <table> --file <csv>")
    if delivery_scope is None:
        return

    if delivery_scope == _DELIVERY_SINGLE_TABLE:
        _run_qa_interactive_single_table(run_by, commit_default)
        return

    source = common.select(
        "Which source?", [_SOURCE_SYNTHETIC, _SOURCE_LOCAL_FOLDER, _SOURCE_S3],
        flag_hint="mothman cp qa --run-id <run_id> / mothman cp qa --folder <dir> --reference-folder <dir> / "
                   "mothman cp qa --s3-delivery <prefix> --s3-reference-delivery <prefix>")
    if source is None:
        return

    if source == _SOURCE_LOCAL_FOLDER:
        _run_qa_interactive_local_folder(run_by, commit_default)
        return

    if source == _SOURCE_S3:
        _run_qa_interactive_s3(run_by, commit_default)
        return

    if not manifest_exists():
        if not common.confirm("No synthetic data generated yet - generate it now?", yes=False, default=True):
            console.print("Nothing to check without synthetic data. Stopping.", style="yellow")
            return
        console.print("Generating synthetic data (population=70,000, 15 quarterly snapshots)...", style="dim")
        generate_synthetic_data()

    manifest = load_manifest()
    choice = common.select("Pick a run to check:", picker_choices(manifest),
                            flag_hint="mothman cp qa --run-id <run_id>")
    if choice is None:
        return
    run_id = run_id_from_choice(choice)

    # ASKED BEFORE THE CHAIN, and before the "Running..." line - see
    # cli/bdm.py's counterpart (REQ-PIPE-089 criterion 8).
    keep = common.decide_record(run_id, keep=True if commit_default else None)

    console.print(f"Running the real dbt-core/Soda Core/datacontract-cli/Evidently chain for {run_id}...",
                  style="dim")
    with common.chain_progress(run_id) as on_step:
        results, recorded_run_id = run_check(run_id, run_by, on_step=on_step, keep=keep)
    _report_synthetic(results, recorded_run_id, keep, interactive=True)


def _run_qa_interactive_local_folder(run_by: str, commit_default: bool) -> None:
    """The Local files source mode's TUI body (plans/tooling.md #1 Phase
    2) - browses via questionary.path() (real tab-completion, no
    hand-built file picker), then runs the exact same
    run_check_local_folder() the flag-invocable --folder/--reference-folder
    form below also calls."""
    folder = common.path_prompt(
        "Path to the delivery folder you've already downloaded (all 6 real CP tables):",
        flag_hint="mothman cp qa --folder <dir> --reference-folder <dir>")
    if folder is None:
        return
    reference_folder = common.path_prompt(
        "Path to a known-good reference delivery folder (for distribution-drift comparison):",
        flag_hint="mothman cp qa --folder <dir> --reference-folder <dir>")
    if reference_folder is None:
        return

    console.print(f"Running the real dbt-core/Soda Core/datacontract-cli/Evidently chain for {folder}...",
                  style="dim")
    with common.chain_progress(os.path.basename(folder.rstrip("/"))) as on_step:
        results, filed = run_check_local_folder(
            folder, reference_folder, run_by, on_step=on_step,
            keep=True if commit_default else None)
    _finish_supply(results, filed)


def _run_qa_interactive_s3(run_by: str, commit_default: bool) -> None:
    """The S3 source mode's TUI body for Child Protection (plans/
    tooling.md #1 Phase 3) - lists real "delivery" prefixes one level
    under the dataset's own configured s3Source prefix (contract/
    child-protection-contract.yaml's own customProperties), via S3's
    own Delimiter="/" folder-like grouping, picks two of them, then runs
    the exact same run_check_s3_delivery() the flag-invocable
    --s3-delivery/--s3-reference-delivery form below also calls."""
    bucket = common.raw_bucket_name()
    prefix = s3_config()["prefix"] or ""
    console.print(f"Listing deliveries under s3://{bucket}/{prefix} ...", style="dim")
    deliveries = s3_source.list_delivery_prefixes(bucket, prefix)
    if not deliveries:
        console.print(f"No deliveries under s3://{bucket}/{prefix}", style="yellow")
        return

    flag_hint = "mothman cp qa --s3-delivery <prefix> --s3-reference-delivery <prefix>"
    delivery = common.select("Pick a delivery to check:", deliveries, flag_hint=flag_hint)
    if delivery is None:
        return
    reference_delivery = common.select("Pick a known-good reference delivery:", deliveries, flag_hint=flag_hint)
    if reference_delivery is None:
        return

    console.print(f"Downloading + running the real dbt-core/Soda Core/datacontract-cli/Evidently chain "
                  f"for s3://{bucket}/{delivery}...", style="dim")
    with common.chain_progress(delivery.rstrip("/").rsplit("/", 1)[-1]) as on_step:
        results, filed = run_check_s3_delivery(
            bucket, delivery, reference_delivery, run_by, on_step=on_step,
            keep=True if commit_default else None)
    _finish_supply(results, filed)


def _run_qa_interactive_single_table(run_by: str, commit_default: bool) -> None:
    """Single-table Child Protection QA's TUI body (plans/tooling.md #1
    Phase 3.5) - picks a table, then Local file or S3 as the source for
    just that one table's data. The other 5 tables and the Evidently
    reference both come automatically from the last Promoted run
    (run_check_single_table()'s own docstring has the full account) - no
    separate reference prompt needed here, unlike full-delivery mode."""
    flag_hint = "mothman cp qa --table <table> --file <csv> / mothman cp qa --table <table> --s3-key <key>"
    table = common.select("Which table?", TABLES, flag_hint=flag_hint)
    if table is None:
        return

    source = common.select("Which source?", [_SOURCE_LOCAL_FILE, _SOURCE_S3], flag_hint=flag_hint)
    if source is None:
        return

    if source == _SOURCE_S3:
        bucket = common.raw_bucket_name()
        prefix = s3_config()["prefix"] or ""
        console.print(f"Listing s3://{bucket}/{prefix} ...", style="dim")
        keys = s3_source.list_keys(bucket, prefix)
        if not keys:
            console.print(f"No objects under s3://{bucket}/{prefix}", style="yellow")
            return
        key = common.select(f"Pick the {table} object to check:", keys, flag_hint=flag_hint)
        if key is None:
            return
        console.print(f"Downloading + running the real dbt-core/Soda Core/datacontract-cli/Evidently chain "
                      f"for s3://{bucket}/{key} (table: {table})...", style="dim")
        with common.chain_progress(key.rsplit("/", 1)[-1]) as on_step:
            results, filed = run_check_s3_single_table(
                bucket, table, key, run_by, on_step=on_step,
                keep=True if commit_default else None)
    else:
        file_path = common.path_prompt(f"Path to the {table} CSV you've already downloaded:", flag_hint=flag_hint)
        if file_path is None:
            return
        console.print(f"Running the real dbt-core/Soda Core/datacontract-cli/Evidently chain for {file_path} "
                      f"(table: {table})...", style="dim")
        with common.chain_progress(os.path.basename(file_path)) as on_step:
            results, filed = run_check_single_table(
                table, file_path, run_by, on_step=on_step,
                keep=True if commit_default else None)

    _finish_supply(results, filed)


@click.group("cp")
def cp_group() -> None:
    """Child Protection - Tier 1 commands."""


@cp_group.command("generate-synthetic-data")
@click.option("--yes", is_flag=True, help="Skip the overwrite confirmation.")
def generate_synthetic_data_command(yes: bool) -> None:
    """Generate (or deterministically regenerate) the full synthetic Child Protection collection."""
    if manifest_exists() and not common.confirm(
            "This will regenerate the Child Protection deliveries "
            "(deterministic - same content either way). Continue?",
            yes=yes, default=True):
        console.print("Not regenerated.", style="yellow")
        return
    generate_synthetic_data()
    from generator import generate_cp_runs

    console.print(f"Generated -> {generate_cp_runs.DELIVERIES_DIR}", style="green")


@cp_group.command("qa")
@click.option("--run-id", default=None, help="Synthetic mode: an existing manifest run_id "
                                              "(e.g. cp_run_05_2024-...). Omit to pick interactively.")
@click.option("--reference-run-id", default=None,
              help="Synthetic mode: defaults to the last Promoted run, or the manifest's own first (clean) entry.")
@click.option("--folder", "folder_path", default=None, type=click.Path(exists=True, file_okay=False),
              help="Local files mode: an already-downloaded delivery folder, all 6 real tables "
                   "(instead of --run-id).")
@click.option("--reference-folder", default=None, type=click.Path(exists=True, file_okay=False),
              help="Local files mode: a known-good reference delivery folder to compare distribution drift "
                   "against. Required together with --folder.")
@click.option("--s3-delivery", default=None,
              help="S3 mode: a delivery prefix under the dataset's s3Source prefix to check "
                   "(instead of --run-id/--folder).")
@click.option("--s3-reference-delivery", default=None,
              help="S3 mode: a known-good reference delivery prefix to compare distribution drift against. "
                   "Required together with --s3-delivery.")
@click.option("--table", type=click.Choice(cp_common.TABLES), default=None,
              help="Single-table mode (plans/tooling.md #1 Phase 3.5): check just this one table (a real "
                   "partial resupply) - the other 5 tables auto-pull from the last Promoted run. "
                   "Required together with --file or --s3-key.")
@click.option("--file", "table_file", default=None, type=click.Path(exists=True, dir_okay=False),
              help="Single-table mode: an already-downloaded CSV for --table (instead of --folder/--run-id).")
@click.option("--s3-key", default=None,
              help="Single-table mode: an object key under the dataset's s3Source prefix for --table "
                   "(instead of --s3-delivery).")
@click.option("--commit", is_flag=True,
              help="Keep it: file the supply as a real delivery received now, and record "
                   "this run in the dataset's QA history.")
@click.option("--originally-received", "originally_received", default=None,
              help="Keeping a supply: when it was ORIGINALLY received - the email's arrival, "
                   "say - as a time (read on the asset's own clock unless it carries an "
                   "offset), `not-known`, or `storage` for each S3 object's own time. "
                   "Recorded beside our receipt; never used to file or judge the supply.")
@click.option("--trial", is_flag=True,
              help="Run it as a TRIAL: the same four tools against the same rows, filed "
                   "nowhere and recorded nowhere. The opposite of --commit, stated so a "
                   "script never relies on a default it cannot see.")
def qa_command(run_id: str | None, reference_run_id: str | None, folder_path: str | None,
               reference_folder: str | None, s3_delivery: str | None, s3_reference_delivery: str | None,
               table: str | None, table_file: str | None, s3_key: str | None, commit: bool,
               originally_received: str | None, trial: bool) -> None:
    """Run the real QA check chain against a Child Protection run - Synthetic (--run-id),
    Local files (--folder/--reference-folder), S3 (--s3-delivery/--s3-reference-delivery), or
    single-table (--table plus --file or --s3-key) source mode."""
    if table is None and (table_file is not None or s3_key is not None):
        raise click.ClickException(
            "--file/--s3-key need --table (single-table mode) to know which table they're for.")

    if table is not None:
        if run_id is not None or folder_path is not None or s3_delivery is not None:
            raise click.ClickException(
                "Pass --table only with --file or --s3-key (single-table mode) - not --run-id/--folder/"
                "--s3-delivery (those are full-delivery modes).")
        if (table_file is None) == (s3_key is None):
            raise click.ClickException("--table requires exactly one of --file or --s3-key.")
        run_by = get_run_by() if commit else "trial:not-recorded"
        keep = common.keep_from_flags(commit, trial)
        if table_file is not None:
            with common.chain_progress(os.path.basename(table_file)) as on_step:
                results, filed = run_check_single_table(
                    table, table_file, run_by, on_step=on_step, keep=keep,
                    originally=originally_received)
        else:
            bucket = common.raw_bucket_name()
            with common.chain_progress(s3_key.rsplit("/", 1)[-1]) as on_step:
                results, filed = run_check_s3_single_table(
                    bucket, table, s3_key, run_by, on_step=on_step, keep=keep,
                    originally=originally_received)
        _finish_supply(results, filed)
        sys.exit(1 if has_failures(results) else 0)

    if s3_delivery is not None:
        if run_id is not None or folder_path is not None:
            raise click.ClickException(
                "Pass exactly one of --run-id (Synthetic mode), --folder (Local files mode), "
                "or --s3-delivery (S3 mode).")
        if s3_reference_delivery is None:
            raise click.ClickException(
                "--s3-delivery requires --s3-reference-delivery (a known-good delivery prefix to compare against).")
        bucket = common.raw_bucket_name()
        run_by = get_run_by() if commit else "trial:not-recorded"
        with common.chain_progress(s3_delivery.rstrip("/").rsplit("/", 1)[-1]) as on_step:
            results, filed = run_check_s3_delivery(
                bucket, s3_delivery, s3_reference_delivery, run_by, on_step=on_step,
                keep=common.keep_from_flags(commit, trial), originally=originally_received)
        _finish_supply(results, filed)
        sys.exit(1 if has_failures(results) else 0)

    if folder_path is not None:
        if run_id is not None:
            raise click.ClickException(
                "Pass either --run-id (Synthetic mode) or --folder (Local files mode), not both.")
        if reference_folder is None:
            raise click.ClickException(
                "--folder requires --reference-folder (a known-good delivery folder to compare against).")
        run_by = get_run_by() if commit else "trial:not-recorded"
        with common.chain_progress(os.path.basename(folder_path.rstrip("/"))) as on_step:
            results, filed = run_check_local_folder(
                folder_path, reference_folder, run_by, on_step=on_step,
                keep=common.keep_from_flags(commit, trial), originally=originally_received)
        _finish_supply(results, filed)
        sys.exit(1 if has_failures(results) else 0)

    if run_id is None:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            raise click.ClickException("Not a real terminal - pass --run-id or --folder explicitly.")
        run_qa_interactive(commit_default=commit)
        return

    keep = common.keep_from_flags(commit, trial)
    run_by = get_run_by() if keep else "trial:not-recorded"
    with common.chain_progress(run_id) as on_step:
        results, recorded_run_id = run_check(run_id, run_by, reference_run_id=reference_run_id,
                                              on_step=on_step, keep=keep)
    _report_synthetic(results, recorded_run_id, keep, interactive=False)
    sys.exit(1 if has_failures(results) else 0)
