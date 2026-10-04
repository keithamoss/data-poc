"""mothman bdm - Birth Registrations commands (plans/tooling.md #1
Phase 1/2): generate-synthetic-data and the Quality Assurance flow
against Synthetic and Local files source modes. Every function here is
called from both the real Click command (flag-invocable, scriptable)
and the TUI menu (cli/app.py) - one real implementation, two entry
paths, per the wizard/flags duality plans/tooling.md #1 itself was
designed around.

The Local files mode (Phase 2) folds in qa_tools/bdm/check_file.py's own
retired standalone-CLI logic verbatim (that module is gone - this is now
the only place it runs from, per CLAUDE.md's "mothman is the only
programmatic access point" convention) - same real dbt-core/Soda Core/
datacontract-cli/Evidently chain via orchestrate_bdm.run_single(), just
reached from a browsable questionary.path() prompt or --file/
--reference-file flags instead of a positional CSV argument."""
from __future__ import annotations
import dataclasses
import os
import sys
import tempfile

import rich_click as click
from rich.console import Console
from rich.table import Table

from qa_tools.bdm import build_per_run_warehouses, orchestrate_bdm
from qa_tools.common import s3_source
from qa_tools.common.git_identity import get_run_by
from qa_tools.common import trial as trial_mod
from qa_tools.common import hand_filing

from . import common, filing_tui
from qa_tools.common import asset_time

AGENCY_ID = orchestrate_bdm.AGENCY_ID
COLLECTION_ID = orchestrate_bdm.COLLECTION_ID
CONTRACT_PATH = os.path.join(os.path.dirname(__file__), "..", "contract", "bdm-birth-registrations-contract.yaml")

console = Console()


def s3_config() -> dict:
    """The real s3Source/localSource/arrivalPattern config off this
    dataset's own contract YAML - see qa_tools.common.s3_source.
    dataset_s3_config()'s own docstring for the full account of how this
    got safely wired into the real contract (Phase 3, 2026-09-19)."""
    return s3_source.dataset_s3_config(CONTRACT_PATH)


def generated_output_dir() -> str:
    """Where `generate-synthetic-data` leaves its output.

    THE DELIVERY TREE, since REQ-PIPE-102 - the generator writes one
    copy of a supply and that is it. This used to return data/raw/,
    which held a second flat copy of every generated run.
    """
    from generator import generate_runs

    return str(generate_runs.DELIVERIES_DIR)



def generate_synthetic_data() -> None:
    """Runs the real generator directly - the same shape as cli/cp.py's
    own generate_synthetic_data(), which is new.

    IT USED TO BUILD A DUCKDB WAREHOUSE TOO. This wrapped
    pipeline.orchestrate.prepare_warehouse(), which generated the runs
    and then loaded every one of them into one combined DuckDB file at
    data/warehouse.duckdb. That file had exactly one reader - the
    dashboard build's own direct chart queries - and it lost that reader
    in Phase 3 of plans/publishing-and-history.md, when the build became
    a pure function of committed results. It kept being written for
    another year of project time with nothing reading it, which is the
    quiet kind of legacy: no error, no failing test, just a generator
    step paying for a warehouse nobody opens.

    REQ-PIPE-087 criterion 1 is what finally removed it - all supply data
    lives in the one PostgreSQL database and none of it in a DuckDB file -
    and staging now happens where it belongs, per arrival, as QA runs
    (REQ-PIPE-068). Generating synthetic data is generating synthetic
    data again."""
    from generator import generate_runs
    generate_runs.main()
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
    # A CONTESTED arrival - two files for the dataset - is not pickable:
    # nothing may choose between its files, so there is no one csv_path
    # to offer (REQ-PIPE-105 criterion 6; it was REQ-PIPE-059's hold).
    return [a.as_entry()
                | {"csv_path": str(a.path_for("birth-registrations"))}
            for a in arrivals.arrivals_for("civil-registration", "run_")
            if "birth-registrations" not in a.contested]


def manifest_exists() -> bool:
    """Is there anything to pick from? A real question now: with no
    deliveries on disk there are no arrivals, which is what the picker
    needs to know."""
    return bool(load_manifest())


def run_check(run_id: str, run_by: str, reference_run_id: str | None = None,
              on_step=None, *, keep: bool = True) -> tuple[list[dict], str]:
    """Runs the real check chain for one existing Synthetic manifest entry.
    Returns (results, recorded_run_id) - the second is `run_id` itself for
    a kept run, and a throwaway trial identity when `keep` is False.

    IT USED TO WRITE INTO A THROWAWAY DIRECTORY and hand the caller a
    path to promote into the committed qa_results/ tree. REQ-PIPE-089
    removed the tree, and with it the idea that a run can be held
    somewhere provisional until somebody accepts it: results are recorded
    as the run completes, so the keep-or-not decision moved to before the
    chain rather than after the report. See the body for the whole
    reasoning.

    This used to do two extra things, both of which REQ-GEN-043 removed
    the NEED for rather than the code for, which is worth saying so the
    absence does not read as an oversight. It backed up and restored
    raw_dir()'s manifest.json around the call, because run_single()
    overwrote it with its own synthetic one (a real bug, found live: a
    manual smoke test corrupted the real data/raw/manifest.json from 176
    entries down to 1). And it passed the immediately-preceding manifest
    entry down as previous_run_id/previous_csv, so the row-count-growth
    check had a previous run to compare against.

    Neither exists now. run_single() writes no manifest, and the
    row-count-growth check finds the preceding arrival from the
    deliveries RECOGNISED on disk - which is the same answer this used
    to hand it, arrived at without anyone declaring it."""
    manifest = load_manifest()
    idx = next((i for i, e in enumerate(manifest) if e["run_id"] == run_id), None)
    if idx is None:
        raise click.ClickException(
            f"No manifest entry for run_id={run_id!r} - run generate-synthetic-data first?")
    entry = manifest[idx]

    # NO DEFAULT REFERENCE ANY MORE (REQ-QAC-108 criterion 4,
    # 2026-09-29). `None` is passed straight through, and the
    # orchestrator resolves the reference from what was RECORDED - the
    # last period a supply was really promoted into. default_reference()
    # picked the last run whose results existed, falling back to the
    # manifest's first entry, which is the anchor receding into the past
    # that criterion 4 forbids. An operator naming one explicitly is a
    # different thing and still honoured.
    if reference_run_id is not None and not any(
            e["run_id"] == reference_run_id for e in manifest):
        raise click.ClickException(
            f"Reference run {reference_run_id!r} isn't among the arrivals recognised on disk - "
            f"run generate-synthetic-data first?")

    csv_path = entry["csv_path"]

    # KEEP OR TRIAL IS DECIDED BEFORE THE CHAIN RUNS, and it used to be
    # decided afterwards (REQ-PIPE-089 criterion 8). The old shape wrote
    # every run's results to a throwaway directory and then asked
    # "promote?" - so declining meant deleting files nobody had read. A
    # recorded result is visible the moment its run completes, so there
    # is no afterwards to ask in: a run the operator does not want kept
    # runs under a TRIAL identity instead, which records nothing that
    # survives it (REQ-PIPE-103). Same choice, moved to the only place it
    # can still be made.
    recorded_run_id = run_id if keep else trial_mod.trial_run_id()

    results = _run_single_preserving_manifest(
        recorded_run_id, csv_path, asset_time.local_date(entry["received_at"]).isoformat(),
        reference_run_id, run_by=run_by,
        on_step=on_step,
    )
    return results, recorded_run_id


def _run_single_preserving_manifest(*args, **kwargs) -> list[dict]:
    """Calls orchestrate_bdm.run_single(*args, **kwargs).

    THIS USED TO BACK UP AND RESTORE raw_dir()'s manifest.json around
    the call, because run_single() overwrote it with its own synthetic
    one - correct for its Lambda use case, a real collision against the
    batch manifest this CLI's run picker read from.

    REQ-GEN-043 removed the cause rather than the symptom: run_single()
    writes no manifest at all now, and the picker recognises arrivals
    from disk instead of reading one. The wrapper is kept as a single
    named seam for the two callers that share it, and because deleting
    it would spread orchestrate_bdm.run_single() across two more call
    sites for no gain.
    """
    return orchestrate_bdm.run_single(*args, **kwargs)


def run_check_local_file(csv_path: str, reference_csv: str, run_by: str,
                          run_id: str | None = None, run_date: str | None = None,
                          on_step=None, keep: bool | None = None
                          ) -> tuple[list[dict], str, "hand_filing.Filed"]:
    """The Local files QA source mode's real check-running body (plans/
    tooling.md #1 Phase 2) - folds in qa_tools/bdm/check_file.py's own
    retired logic: stages the reference CSV under a real run_id
    (there's no synthetic manifest[0] to fall back on for a real,
    manually-downloaded file - a real reference is required, not
    defaulted), then reuses orchestrate_bdm.run_single(), same entry
    point both the Synthetic flow above and Thread B's Lambda handler
    call.

    THE DECISION COMES FIRST (REQ-PIPE-103). Keeping this supply files
    it as a real delivery received now and gives the run an id from
    recognition, before any check runs; declining gives a TRIAL, whose
    id comes from the clock and which leaves nothing behind. Returns
    `(results, tmp_results_dir, filed)` - the third is what the caller
    needs to say which of the two it did.

    THE REFERENCE IS ALWAYS A TRIAL, whichever way the supply went: it
    is a known-good file the operator already had, and filing it would
    record an arrival that never happened.
    """
    run_date = run_date or asset_time.now().date().isoformat()
    filed = common.file_or_trial([csv_path], "civil-registration", "run_", keep=keep)
    if run_id is not None and not filed.delivery_name:
        filed = dataclasses.replace(filed, run_id=run_id)
    if filed.delivery_name:
        # KEPT: AN ARRIVAL LIKE ANY OTHER, processed as the batch would -
        # staged, filed, overlaid on its period, checked, promoted - with
        # its drift reference from the recorded history (REQ-PIPE-105;
        # Keith, 2026-10-02). --reference-file applies to a trial only.
        found = hand_filing.arrivals_of(filed, "civil-registration", "run_")
        for arrival in found:
            for ordinal, name in enumerate(sorted(arrival.files_by_dataset[
                    build_per_run_warehouses.DATASET_ID]), start=1):
                build_per_run_warehouses.build_one(
                    arrival.run_id, str(arrival.path / name),
                    asset_time.local_date(arrival.received_at).isoformat(),
                    ordinal=ordinal if len(arrival.files_by_dataset[
                        build_per_run_warehouses.DATASET_ID]) > 1 else 0,
                    received_at=arrival.received_at,
                    delivery_name=arrival.delivery_name)
        return orchestrate_bdm.run_arrivals(found, run_by, on_step=on_step), filed
    run_id = filed.run_id
    csv_path = filed.paths[0]
    reference_run_id = common.reference_run_id()

    # THE REFERENCE IS STAGED TOO (REQ-PIPE-102, 2026-09-27), which is
    # what lets data/raw/ go. It used to be copied into that directory
    # so Evidently could find it by name, leaving it the one supply in
    # this flow that was checked against a file rather than the
    # warehouse. Child Protection's own local-folder mode already
    # staged both sides; this is BDM catching up.
    build_per_run_warehouses.build_one(reference_run_id, reference_csv, run_date)

    try:
        results = _run_single_preserving_manifest(
            run_id, csv_path, run_date,
            reference_run_id=reference_run_id, run_by=run_by,
            on_step=on_step, received_at=filed.received_at,
        )
    finally:
        common.discard_reference(reference_run_id)
    return results, filed


def run_check_s3(bucket: str, key: str, reference_key: str, run_by: str,
                  run_id: str | None = None, run_date: str | None = None, s3_client=None,
                  on_step=None, keep: bool | None = None
                  ) -> tuple[list[dict], str, "hand_filing.Filed"]:
    """The S3 QA source mode's real check-running body (plans/tooling.md
    #1 Phase 3) - downloads key/reference_key (real boto3, via
    qa_tools.common.s3_source) into a fresh local staging dir, then
    reuses run_check_local_file() exactly as if a human had downloaded
    them themselves: S3 mode is "download, then Local files mode", not a
    third parallel check-running code path. Returns (results,
    tmp_results_dir) - same tmp-dir-first Promote pattern as
    run_check_local_file()."""
    staging_dir = tempfile.mkdtemp(prefix="mothman-s3-")
    local_path = s3_source.download_key(bucket, key, staging_dir, s3_client=s3_client)
    local_reference_path = s3_source.download_key(bucket, reference_key, staging_dir, s3_client=s3_client)
    return run_check_local_file(local_path, local_reference_path, run_by, run_id=run_id, run_date=run_date,
                                 on_step=on_step, keep=keep)


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
    # The delivery it came from, not an injected severity - the picker
    # shows what arrived, and severity is generator bookkeeping the CLI
    # has no business reading (REQ-GEN-043).
    return [f'{e["run_id"]}  ({asset_time.local_date(e["received_at"])}, {e["delivery"]})'
            for e in manifest]


def run_id_from_choice(choice: str) -> str:
    return choice.split()[0]


_SOURCE_SYNTHETIC = "Synthetic - pick or generate a run"
_SOURCE_LOCAL_FILE = "Local files - a CSV you've already downloaded"
_SOURCE_S3 = "S3 - browse the real raw-data bucket"


def _report_synthetic(results: list[dict], recorded_run_id: str, keep: bool,
                       *, interactive: bool) -> None:
    """Report a Synthetic-mode check, and say what became of it.

    IT USED TO ASK "Promote this run into the real, permanent qa_results/
    history?" here, with the report already on screen. That question is
    gone rather than reworded (REQ-PIPE-089 criterion 8): the results were
    recorded as the run completed, so by the time anything could be asked
    the answer is already true. The same decision is now taken before the
    chain runs, which is the only place it can still change anything.

    NOTHING SAYS "commit and push to publish" ANY MORE either, and that
    absence is the point rather than an omission - publishing was a git
    push, and it is now REQ-PIPE-092's own step.
    """
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
        # The scriptable form keeps its one line, for the same reason the
        # panel it replaces kept its own: a panel is noise in a pipeline
        # and a blocking keypress would be a hang.
        console.print(f"Recorded {len(results)} results for {recorded_run_id}", style="green")


def _finish_supply(results: list[dict], filed) -> None:
    """Report a hand-supplied check, and say what the operator already
    decided (REQ-PIPE-103 criterion 8).

    NO SECOND QUESTION. The decision was taken before anything ran,
    because a supply has to be filed BEFORE it can take its identity
    from recognition - so asking "promote?" afterwards would be
    offering a choice that was already made, with only half of it
    still available.

    THAT REASONING NOW GOVERNS EVERY MODE, which is what REQ-PIPE-089
    criterion 8 changed. This path already asked before the run; the
    Synthetic path asked after, and could only do so because results
    were parked in a temp directory until somebody accepted them. With
    the results recorded as the run completes, this is the only shape
    left - so the copy-then-commit step this used to end with is gone.
    """
    console.print(report_table(results, filed.run_id))
    common.say_what_it_did(filed.run_id, filed.delivery_name)
    # A KEPT run that left its supply waiting offers the decision here
    # (REQ-GHUB-082 criterion 17), as the synthetic route always did -
    # post-build-review #82 found the hand-filed routes never asking. A
    # trial filed nothing, so there is nothing of its own to decide.
    if filed.delivery_name:
        filing_tui.offer_after_run(COLLECTION_ID, filed.run_id)


def run_qa_interactive(commit_default: bool = False) -> None:
    """The Quality Assurance flow's real body, called from both `mothman
    bdm qa` (no --run-id/--file given, a real terminal) and the TUI main
    menu - one real implementation across both the Synthetic and Local
    files source modes (plans/tooling.md #1 Phases 1-2). A real git
    identity is required upfront here (not deferred to Promote time):
    the flow always asks "Promote?" only after the report is already
    shown, so run_by has to be resolved - and correct - before the real
    tool chain ever runs, or a later "yes, promote" would copy a
    placeholder identity into permanent history."""
    run_by = get_run_by()

    source = common.select(
        "Which source?", [_SOURCE_SYNTHETIC, _SOURCE_LOCAL_FILE, _SOURCE_S3],
        flag_hint="mothman bdm qa --run-id <run_id> / mothman bdm qa --file <csv> --reference-file <csv> / "
                   "mothman bdm qa --s3-key <key> --s3-reference-key <key>")
    if source is None:
        return

    if source == _SOURCE_LOCAL_FILE:
        _run_qa_interactive_local_file(run_by, commit_default)
        return

    if source == _SOURCE_S3:
        _run_qa_interactive_s3(run_by, commit_default)
        return

    if not manifest_exists():
        if not common.confirm("No synthetic data generated yet - generate it now?", yes=False, default=True):
            console.print("Nothing to check without synthetic data. Stopping.", style="yellow")
            return
        console.print("Generating synthetic data...", style="dim")
        generate_synthetic_data()

    manifest = load_manifest()
    choice = common.select("Pick a run to check:", picker_choices(manifest),
                            flag_hint="mothman bdm qa --run-id <run_id>")
    if choice is None:
        return
    run_id = run_id_from_choice(choice)

    # ASKED BEFORE THE CHAIN, not after the report (REQ-PIPE-089
    # criterion 8) - and before the "Running..." line too, so the
    # question never appears to interrupt a run already under way.
    keep = common.decide_record(run_id, keep=True if commit_default else None)

    # plans/tooling.md #13 - this used to print the line below and then
    # go completely silent for ~13.5s while the real chain ran.
    console.print(f"Running the real dbt-core/Soda Core/datacontract-cli/Evidently chain for {run_id}...",
                  style="dim")
    with common.chain_progress(run_id) as on_step:
        results, recorded_run_id = run_check(run_id, run_by, on_step=on_step, keep=keep)
    _report_synthetic(results, recorded_run_id, keep, interactive=True)


def _run_qa_interactive_local_file(run_by: str, commit_default: bool) -> None:
    """The Local files source mode's TUI body (plans/tooling.md #1 Phase
    2) - browses via questionary.path() (real tab-completion, no
    hand-built file picker), then runs the exact same
    run_check_local_file() the flag-invocable --file/--reference-file
    form below also calls."""
    csv_path = common.path_prompt("Path to the CSV you've already downloaded:",
                                   flag_hint="mothman bdm qa --file <csv> --reference-file <csv>")
    if csv_path is None:
        return
    reference_csv = common.path_prompt(
        "Path to a known-good reference CSV (for distribution-drift comparison):",
        flag_hint="mothman bdm qa --file <csv> --reference-file <csv>")
    if reference_csv is None:
        return

    # THE DECISION IS TAKEN INSIDE run_check_local_file(), before it
    # stages anything - see its own docstring. So there is no run id
    # to label the progress bar with yet, and the file's name is what
    # the operator is actually watching.
    keep = True if commit_default else None
    console.print(f"Running the real dbt-core/Soda Core/datacontract-cli/Evidently chain for {csv_path}...",
                  style="dim")
    with common.chain_progress(os.path.basename(csv_path)) as on_step:
        results, filed = run_check_local_file(csv_path, reference_csv, run_by,
                                                        on_step=on_step, keep=keep)
    _finish_supply(results, filed)


def _run_qa_interactive_s3(run_by: str, commit_default: bool) -> None:
    """The S3 source mode's TUI body (plans/tooling.md #1 Phase 3) -
    lists real object keys under the dataset's own configured s3Source
    prefix (contract/bdm-birth-registrations-contract.yaml's own
    customProperties), picks two of them, then runs the exact same
    run_check_s3() the flag-invocable --s3-key/--s3-reference-key form
    below also calls."""
    bucket = common.raw_bucket_name()
    prefix = s3_config()["prefix"] or ""
    console.print(f"Listing s3://{bucket}/{prefix} ...", style="dim")
    keys = s3_source.list_keys(bucket, prefix)
    if not keys:
        console.print(f"No objects under s3://{bucket}/{prefix} - nothing to check.", style="yellow")
        return

    flag_hint = "mothman bdm qa --s3-key <key> --s3-reference-key <key>"
    key = common.select("Pick an object to check:", keys, flag_hint=flag_hint)
    if key is None:
        return
    reference_key = common.select("Pick a known-good reference object:", keys, flag_hint=flag_hint)
    if reference_key is None:
        return

    keep = True if commit_default else None
    console.print(f"Downloading + running the real dbt-core/Soda Core/datacontract-cli/Evidently chain "
                  f"for s3://{bucket}/{key}...", style="dim")
    with common.chain_progress(os.path.basename(key)) as on_step:
        results, filed = run_check_s3(bucket, key, reference_key, run_by,
                                                on_step=on_step, keep=keep)
    _finish_supply(results, filed)


@click.group("bdm")
def bdm_group() -> None:
    """Birth Registrations - Tier 1 commands."""


@bdm_group.command("generate-synthetic-data")
@click.option("--yes", is_flag=True, help="Skip the overwrite confirmation.")
def generate_synthetic_data_command(yes: bool) -> None:
    """Generate (or deterministically regenerate) the full synthetic Birth Registrations batch."""
    if manifest_exists() and not common.confirm(
            "This will regenerate data/raw/ (deterministic - same content either way). Continue?",
            yes=yes, default=True):
        console.print("Not regenerated.", style="yellow")
        return
    generate_synthetic_data()
    console.print(f"Generated -> {generated_output_dir()}", style="green")


@bdm_group.command("qa")
@click.option("--run-id", default=None, help="Synthetic mode: an existing manifest run_id "
                                              "(e.g. run_005_2026-...). Omit to pick interactively.")
@click.option("--reference-run-id", default=None,
              help="Synthetic mode: defaults to the last Promoted run, or the manifest's own first (clean) entry.")
@click.option("--file", "file_path", default=None, type=click.Path(exists=True, dir_okay=False),
              help="Local files mode: an already-downloaded CSV to check (instead of --run-id).")
@click.option("--reference-file", default=None, type=click.Path(exists=True, dir_okay=False),
              help="Local files mode: a known-good CSV to compare distribution drift against. "
                   "Required together with --file.")
@click.option("--s3-key", default=None,
              help="S3 mode: an object key under the dataset's s3Source prefix to check "
                   "(instead of --run-id/--file).")
@click.option("--s3-reference-key", default=None,
              help="S3 mode: a known-good reference object key to compare distribution drift against. "
                   "Required together with --s3-key.")
@click.option("--commit", is_flag=True,
              help="Keep it: file the supply as a real delivery received now, and record "
                   "this run in the dataset's QA history.")
@click.option("--trial", is_flag=True,
              help="Run it as a TRIAL: the same four tools against the same rows, filed "
                   "nowhere and recorded nowhere. The opposite of --commit, stated so a "
                   "script never relies on a default it cannot see.")
def qa_command(run_id: str | None, reference_run_id: str | None, file_path: str | None,
               reference_file: str | None, s3_key: str | None, s3_reference_key: str | None,
               commit: bool, trial: bool) -> None:
    """Run the real QA check chain against a Birth Registrations run - Synthetic (--run-id),
    Local files (--file/--reference-file), or S3 (--s3-key/--s3-reference-key) source mode."""
    if s3_key is not None:
        if run_id is not None or file_path is not None:
            raise click.ClickException(
                "Pass exactly one of --run-id (Synthetic mode), --file (Local files mode), "
                "or --s3-key (S3 mode).")
        if s3_reference_key is None:
            raise click.ClickException(
                "--s3-key requires --s3-reference-key (a known-good object key to compare against).")
        bucket = common.raw_bucket_name()
        run_by = get_run_by() if commit else "trial:not-recorded"
        with common.chain_progress(os.path.basename(s3_key)) as on_step:
            results, filed = run_check_s3(bucket, s3_key, s3_reference_key, run_by,
                                                    on_step=on_step,
                                                    keep=common.keep_from_flags(commit, trial))
        _finish_supply(results, filed)
        sys.exit(1 if has_failures(results) else 0)

    if file_path is not None:
        if run_id is not None:
            raise click.ClickException("Pass either --run-id (Synthetic mode) or --file (Local files mode), not both.")
        if reference_file is None:
            raise click.ClickException("--file requires --reference-file (a known-good CSV to compare against).")
        run_by = get_run_by() if commit else "trial:not-recorded"
        with common.chain_progress(os.path.basename(file_path)) as on_step:
            results, filed = run_check_local_file(file_path, reference_file, run_by,
                                                            on_step=on_step,
                                                            keep=common.keep_from_flags(commit, trial))
        _finish_supply(results, filed)
        sys.exit(1 if has_failures(results) else 0)

    if run_id is None:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            raise click.ClickException("Not a real terminal - pass --run-id or --file explicitly.")
        run_qa_interactive(commit_default=commit)
        return

    keep = common.keep_from_flags(commit, trial)
    run_by = get_run_by() if keep else "trial:not-recorded"
    with common.chain_progress(run_id) as on_step:
        results, recorded_run_id = run_check(run_id, run_by, reference_run_id=reference_run_id,
                                              on_step=on_step, keep=keep)
    _report_synthetic(results, recorded_run_id, keep, interactive=False)
    sys.exit(1 if has_failures(results) else 0)
