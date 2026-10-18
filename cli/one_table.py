"""The ONE-TABLE shape of a collection's commands (REQ-TEST-245): a supply is
one CSV. Birth Registrations today; any collection whose hierarchy entry
lists one dataset tomorrow. Moved from cli/bdm.py, with every constant read
from the collection instead of written down.

Every function is called from both the real Click command (flag-invocable,
scriptable) and the TUI menu (cli/app.py) - one implementation, two entry
paths. The Local files mode folds in the retired qa_tools/bdm/check_file.py:
the same real dbt-core/Soda Core/datacontract-cli/Evidently chain via
orchestrate.run_single_file(), reached from a questionary.path() prompt or
--file/--reference-file flags.

Imports are deferred to the method that needs them, so building the group -
which every `mothman --help` does - imports no QA tool (criterion 7).
"""
from __future__ import annotations

import dataclasses
import os
import sys
import tempfile

import rich_click as click

from cli.collection_cli import CollectionCLI, console, refuse_a_broken_adapter
from cli import wording


class OneTableCLI(CollectionCLI):
    _SOURCE_SYNTHETIC = "Synthetic - pick or generate a run"
    _SOURCE_LOCAL_FILE = "Local files - a CSV you've already downloaded"
    _SOURCE_S3 = "S3 - browse the real raw-data bucket"

    def __init__(self, coll):
        super().__init__(coll)
        self.dataset_id = coll.datasets[0].dataset_id
        self.table = coll.datasets[0].table

    # ---- the target trial (REQ-GEN-186) ----------------------------------

    def try_targets(self, collection_id: str | None = None, say=None) -> int:
        """Run the four real tools on every injected target the generator just
        wrote, against its last lead-in, through the same trial path
        `mothman <short> qa --trial` uses - recording nothing (REQ-GEN-186
        criterion 1). Returns how many were tried.

        A DISAGREEMENT FAILS GENERATION AND TAKES THE HISTORY WITH IT
        (criterion 2): every delivery just written is removed before the
        failure is raised. The verdict is the promotion gate's own reading of
        the trial's results (qa_tools/common/target_agreement.py), checked on
        the supply's own day. About nine seconds a trial (2026-10-11)."""
        from generator import collections as providers
        from generator import driver, targets
        from qa_tools.common import delivery, target_agreement

        provider = providers.provider(collection_id or self.collection_id)
        say = say or (lambda msg: console.print(msg, style="dim"))
        # WHERE THE GENERATOR JUST WROTE (targets.just_written) - never the
        # pipeline's view of data/.
        try:
            built, written_to = targets.just_written()
        except ValueError as exc:
            # A RECORD THAT DOES NOT ADD UP fails like any disagreement, not
            # as a traceback (post-build-review #157 finding 7).
            delivery.remove_deliveries(driver.previous_delivery_names(provider.dataset_id),
                                       driver.DELIVERIES_DIR, driver.RECEIPTS_DIR)
            raise self.TargetTrialFailed(f"what the generator built could not be read, so the "
                                         f"deliveries just written were removed: {exc}") from exc
        tried = [b for b in built if b.injected and b.dataset_id in provider.target_datasets]
        found = []
        for one in tried:
            say(f"Trying {one.label} against the real tools (built to {one.target})")
            if one.reference is None:
                found.append(target_agreement.Disagreement(
                    one.label, one.dataset_id, one.target, None,
                    ("it has no lead-in to be measured against",)))
                continue
            results, _filed = self.run_check_local_file(
                str(targets.csv_of(one.delivery, written_to, one.filename)),
                str(targets.csv_of(one.reference, written_to)),
                "target-trial", keep=False, run_date=one.day)
            disagreement = target_agreement.compare(one.dataset_id, results, one.target,
                                                    one.label, one.rules)
            if disagreement:
                found.append(disagreement)
        if found:
            removed = delivery.remove_deliveries(driver.previous_delivery_names(provider.dataset_id),
                                                 written_to, driver.RECEIPTS_DIR)
            raise self.TargetTrialFailed(
                f"{len(found)} of {len(tried)} injected target(s) did not read as built, so "
                f"the {removed} {self.label} deliveries just written were removed:\n"
                + "\n".join(f"  - {d}" for d in found))
        return len(tried)

    # ---- arrivals ----------------------------------------------------------

    def load_manifest(self) -> list[dict]:
        """Every arrival, RECOGNISED FROM DISK (REQ-GEN-043) - never the
        generator's bookkeeping. A CONTESTED arrival - two files for the
        dataset - is not pickable: nothing may choose between its files
        (REQ-PIPE-105 criterion 6)."""
        from qa_tools.common import arrivals

        return [a.as_entry() | {"csv_path": str(a.path_for(self.dataset_id))}
                for a in arrivals.arrivals_for(self.collection_id, self.run_prefix)
                if self.dataset_id not in a.contested]

    def picker_choices(self, manifest: list[dict]) -> list[str]:
        """The delivery each arrival came from, never an injected severity -
        and MARKED 'recorded' where its QA already is (REQ-PIPE-086 criterion
        6): picking one runs a trial, said before it starts."""
        from cli import common
        from qa_tools.common import asset_time

        recorded = common.recorded_runs(e["run_id"] for e in manifest)
        return [f'{e["run_id"]}  ({asset_time.local_date(e["received_at"])}, {e["delivery"]})'
                + ("  - recorded" if e["run_id"] in recorded else "")
                for e in manifest]

    # ---- the check chain ---------------------------------------------------

    def run_check(self, run_id: str, run_by: str, reference_run_id: str | None = None,
                  on_step=None, *, keep: bool = True) -> tuple[list[dict], str]:
        """The real check chain for one recognised arrival. Returns (results,
        recorded_run_id) - `run_id` itself when kept, a throwaway trial
        identity otherwise. KEEP OR TRIAL IS DECIDED BEFORE THE CHAIN RUNS
        (REQ-PIPE-089 criterion 8): results are recorded as the run completes,
        so a run the operator does not want kept runs as a TRIAL that records
        nothing (REQ-PIPE-103). There is no default reference (REQ-QAC-108
        criterion 4): `None` lets the orchestrator resolve it from what was
        recorded."""
        from cli import common
        from qa_tools.common import asset_time
        from qa_tools.common import trial as trial_mod
        from qa_tools.tools import orchestrate, stage

        manifest = self.load_manifest()
        entry = next((e for e in manifest if e["run_id"] == run_id), None)
        if entry is None:
            raise click.ClickException(
                f"No manifest entry for run_id={run_id!r} - run generate-synthetic-data first?")
        if reference_run_id is not None and not any(
                e["run_id"] == reference_run_id for e in manifest):
            raise click.ClickException(
                f"Reference run {reference_run_id!r} isn't among the arrivals recognised on disk - "
                f"run generate-synthetic-data first?")

        if keep:
            # A KEPT, UNRECORDED ARRIVAL GOES THROUGH THE PIPELINE'S OWN
            # LIFECYCLE (REQ-PIPE-086 criterion 9) - staged, filed, overlaid on
            # its period, checked and gated.
            common.refuse_reference_for_kept(keep, reference_run_id, "--reference-run-id")
            arrival = common.kept_arrival(self.collection_id, self.run_prefix, run_id)
            common.record_delivery_of(arrival)
            stage.stage_arrival(self.collection_id, arrival)
            return (orchestrate.run_arrivals(self.collection_id, [arrival], run_by,
                                             on_step=on_step), run_id)

        recorded_run_id = trial_mod.trial_run_id()
        results = self._run_single(
            recorded_run_id, entry["csv_path"],
            asset_time.local_date(entry["received_at"]).isoformat(),
            reference_run_id, run_by=run_by, on_step=on_step)
        return results, recorded_run_id

    def _run_single(self, run_id, *args, **kwargs) -> list[dict]:
        """orchestrate.run_single_file() for this collection's one table - the
        one seam the trial routes share."""
        from qa_tools.tools import orchestrate

        return orchestrate.run_single_file(self.collection_id, run_id, self.table,
                                           *args, **kwargs)

    def run_check_local_file(self, csv_path: str, reference_csv: str, run_by: str,
                             run_id: str | None = None, run_date: str | None = None,
                             on_step=None, keep: bool | None = None,
                             originally: str | None = None, route: str = "file",
                             storage_times: dict | None = None):
        """The Local files mode's check body. THE DECISION COMES FIRST
        (REQ-PIPE-103): keeping files the supply as a real delivery received
        now and takes its id from recognition; declining gives a TRIAL that
        leaves nothing behind. A kept supply is measured against the last
        promoted one (REQ-PIPE-086 criterion 14), so --reference-file applies
        to a trial only, and the reference is always a trial: filing it would
        record an arrival that never happened. Returns (results, filed)."""
        from cli import common
        from qa_tools.common import asset_time, hand_filing
        from qa_tools.tools import orchestrate, stage

        run_date = run_date or asset_time.now().date().isoformat()
        keep = common.decide_keep([csv_path], keep=keep)
        common.refuse_reference_for_kept(keep, reference_csv, "--reference-file")
        if not keep:
            common.require_reference_for_trial(reference_csv, "--reference-file")
        filed = common.file_or_trial([csv_path], self.collection_id, self.run_prefix, keep=keep,
                                     route=route, originally=originally,
                                     storage_times=storage_times)
        if run_id is not None and not filed.delivery_name:
            filed = dataclasses.replace(filed, run_id=run_id)
        if filed.delivery_name:
            # KEPT: AN ARRIVAL LIKE ANY OTHER, processed as the batch would
            # (REQ-PIPE-105; Keith, 2026-10-02).
            found = hand_filing.arrivals_of(filed, self.collection_id, self.run_prefix)
            for arrival in found:
                stage.stage_arrival(self.collection_id, arrival)
            return orchestrate.run_arrivals(self.collection_id, found, run_by,
                                            on_step=on_step), filed
        run_id = filed.run_id
        csv_path = filed.paths[0]
        # A KEPT FILE THAT FELL BACK TO A TRIAL still needs the trial's
        # reference, which nobody was asked for (#120 D5).
        reference_csv = common.reference_for_fallback_trial(reference_csv, "--reference-file",
                                                            "file")
        reference_run_id = common.reference_run_id()
        # THE REFERENCE IS STAGED TOO (REQ-PIPE-102), so it is checked against
        # the warehouse like every other supply.
        stage.stage_table(self.collection_id, reference_run_id, self.table, reference_csv)
        try:
            results = self._run_single(
                run_id, csv_path, run_date, reference_run_id=reference_run_id, run_by=run_by,
                on_step=on_step, received_at=filed.received_at)
        finally:
            common.discard_reference(reference_run_id)
        return results, filed

    def run_check_s3(self, bucket: str, key: str, reference_key: str, run_by: str,
                     run_id: str | None = None, run_date: str | None = None, s3_client=None,
                     on_step=None, keep: bool | None = None, originally: str | None = None):
        """S3 mode: download, then Local files mode - not a third check path.
        Keep or trial is DECIDED HERE, BEFORE ANY DOWNLOAD, so a missing or
        unwanted reference is named by the S3 flag the person typed
        (REQ-PIPE-086 criterion 14), and only a trial's reference is fetched."""
        from cli import common
        from qa_tools.common import s3_source

        keep = common.decide_keep([key], keep=keep)
        common.refuse_reference_for_kept(keep, reference_key, "--s3-reference-key")
        if not keep:
            common.require_reference_for_trial(reference_key, "--s3-reference-key")
        staging_dir = tempfile.mkdtemp(prefix="mothman-s3-")
        local_path = s3_source.download_key(bucket, key, staging_dir, s3_client=s3_client)
        local_reference_path = (s3_source.download_key(bucket, reference_key, staging_dir,
                                                       s3_client=s3_client)
                                if reference_key is not None else None)
        return self.run_check_local_file(
            local_path, local_reference_path, run_by, run_id=run_id, run_date=run_date,
            on_step=on_step, keep=keep, originally=originally, route="s3",
            storage_times=s3_source.last_modified(bucket, [key], s3_client=s3_client))

    # ---- the interactive flow ----------------------------------------------

    def run_qa_interactive(self, commit_default: bool = False) -> None:
        """The Quality Assurance flow, from `mothman <short> qa` in a real
        terminal and from the TUI. A real git identity is required up front,
        before the chain ever runs."""
        from cli import common
        from qa_tools.common.git_identity import get_run_by

        run_by = get_run_by()
        short = self.short
        source = common.select(
            "Which source?", [self._SOURCE_SYNTHETIC, self._SOURCE_LOCAL_FILE, self._SOURCE_S3],
            flag_hint=f"mothman {short} qa --run-id <run_id> / mothman {short} qa --file <csv> "
                      f"--reference-file <csv> / "
                      f"mothman {short} qa --s3-key <key> --s3-reference-key <key>")
        if source is None:
            return
        if source == self._SOURCE_LOCAL_FILE:
            self._run_qa_interactive_local_file(run_by, commit_default)
            return
        if source == self._SOURCE_S3:
            self._run_qa_interactive_s3(run_by, commit_default)
            return

        if not self.manifest_exists():
            if not common.confirm("No synthetic data generated yet - generate it now?",
                                  yes=False, default=True):
                console.print("Nothing to check without synthetic data. Stopping.", style="yellow")
                return
            console.print("Generating synthetic data...", style="dim")
            self.generate_synthetic_data()

        manifest = self.load_manifest()
        choice = common.select("Pick a run to check:", self.picker_choices(manifest),
                               flag_hint=f"mothman {short} qa --run-id <run_id>")
        if choice is None:
            return
        run_id = self.run_id_from_choice(choice)
        # ASKED BEFORE THE CHAIN, and before the "Running..." line
        # (REQ-PIPE-089 criterion 8).
        keep = common.decide_record(run_id, keep=True if commit_default else None)
        console.print(f"Running the real dbt-core/Soda Core/datacontract-cli/Evidently chain "
                      f"for {run_id}...", style="dim")
        with common.chain_progress(run_id) as on_step:
            results, recorded_run_id = self.run_check(run_id, run_by, on_step=on_step, keep=keep)
        self._report_synthetic(results, recorded_run_id, keep, interactive=True)

    def _run_qa_interactive_local_file(self, run_by: str, commit_default: bool) -> None:
        from cli import common

        short = self.short
        csv_path = common.path_prompt(
            "Path to the CSV you've already downloaded:",
            flag_hint=f"mothman {short} qa --file <csv> [--trial --reference-file <csv>]")
        if csv_path is None:
            return
        # KEEP OR TRIAL FIRST, AND A REFERENCE ONLY FOR A TRIAL (REQ-PIPE-086
        # criterion 14).
        keep = common.decide_keep([csv_path], keep=True if commit_default else None)
        reference_csv = None
        if not keep:
            reference_csv = common.path_prompt(
                "Path to a known-good reference CSV to compare against:",
                flag_hint=f"mothman {short} qa --file <csv> --trial --reference-file <csv>")
            if reference_csv is None:
                return
        console.print(f"Running the real dbt-core/Soda Core/datacontract-cli/Evidently chain "
                      f"for {csv_path}...", style="dim")
        with common.chain_progress(os.path.basename(csv_path)) as on_step:
            results, filed = self.run_check_local_file(csv_path, reference_csv, run_by,
                                                       on_step=on_step, keep=keep)
        self._finish_supply(results, filed)

    def _run_qa_interactive_s3(self, run_by: str, commit_default: bool) -> None:
        """Lists real object keys under the dataset's configured s3Source
        prefix, picks one (and a reference for a trial), then runs the same
        run_check_s3() the flags call."""
        from cli import common
        from qa_tools.common import s3_source

        bucket = common.raw_bucket_name()
        prefix = self.s3_config()["prefix"] or ""
        console.print(f"Listing s3://{bucket}/{prefix} ...", style="dim")
        keys = s3_source.list_keys(bucket, prefix)
        if not keys:
            console.print(f"No objects under s3://{bucket}/{prefix} - nothing to check.",
                          style="yellow")
            return
        flag_hint = f"mothman {self.short} qa --s3-key <key> --s3-reference-key <key>"
        key = common.select("Pick an object to check:", keys, flag_hint=flag_hint)
        if key is None:
            return
        keep = common.decide_keep([key], keep=True if commit_default else None)
        reference_key = None
        if not keep:
            reference_key = common.select("Pick a known-good reference object:", keys,
                                          flag_hint=flag_hint)
            if reference_key is None:
                return
        console.print(f"Downloading + running the real dbt-core/Soda Core/datacontract-cli/"
                      f"Evidently chain for s3://{bucket}/{key}...", style="dim")
        with common.chain_progress(os.path.basename(key)) as on_step:
            results, filed = self.run_check_s3(bucket, key, reference_key, run_by,
                                               on_step=on_step, keep=keep)
        self._finish_supply(results, filed)


# ---- the commands ---------------------------------------------------------------

def add_commands(group: click.Group, coll, *, with_target_trial: bool) -> None:
    """`generate-synthetic-data` and `qa` for a one-table collection. Options
    and help read from the collection, so the text is today's exactly."""
    from cli import collection_cli

    name = collection_cli.label(coll)
    me = lambda: collection_cli.of(coll.id)  # noqa: E731 - resolved when the command runs

    def generate(yes: bool, skip_target_trial: bool = False) -> None:
        from cli import common

        refuse_a_broken_adapter(coll)
        cli_ = me()
        if cli_.manifest_exists() and not common.confirm(
                "This will regenerate the synthetic deliveries (deterministic - same content either way). "
                "Continue?", yes=yes, default=True):
            console.print("Not regenerated.", style="yellow")
            return
        cli_.generate_synthetic_data(trial=with_target_trial and not skip_target_trial)
        console.print(f"Generated -> {cli_.generated_output_dir()}", style="green")

    generate = click.option("--yes", is_flag=True, help="Skip the overwrite confirmation.")(generate)
    if with_target_trial:
        # OFFERED ONLY WHERE THE PROVIDER DECLARES A TRIAL (criterion 4).
        generate = click.option(
            "--skip-target-trial", is_flag=True,
            help="Do not try each injected target against the real tools after "
                 "generating (about nine seconds each). A bootstrap still compares "
                 "every targeted supply after its replay.")(generate)
        # click applies decorators bottom-up; --yes was added first, so it
        # lists first, as it always has.
        generate.__click_params__.reverse()
    group.command("generate-synthetic-data",
                  help=f"Generate (or deterministically regenerate) the full synthetic {name} "
                       f"batch.")(generate)

    prefix = coll.run_prefix

    @group.command("qa", help=f"Run the real QA check chain against {wording.a_or_an(name)} run - Synthetic "
                              f"(--run-id), Local files (--file/--reference-file), or S3 "
                              f"(--s3-key/--s3-reference-key) source mode.")
    @click.option("--run-id", default=None,
                  help=f"Synthetic mode: an existing manifest run_id (e.g. {prefix}005_2026-...). "
                       f"Omit to pick interactively.")
    @click.option("--reference-run-id", default=None,
                  help="Synthetic mode, a trial's only: a run to compare distribution drift "
                       "against. There is no default; a kept run is measured against the last "
                       "promoted supply.")
    @click.option("--file", "file_path", default=None, type=click.Path(exists=True, dir_okay=False),
                  help="Local files mode: an already-downloaded CSV to check (instead of "
                       "--run-id).")
    @click.option("--reference-file", default=None, type=click.Path(exists=True, dir_okay=False),
                  help="Local files mode: a known-good CSV to compare distribution drift "
                       "against. A trial's only: a kept supply is measured against the last "
                       "promoted one.")
    @click.option("--s3-key", default=None,
                  help="S3 mode: an object key under the dataset's s3Source prefix to check "
                       "(instead of --run-id/--file).")
    @click.option("--s3-reference-key", default=None,
                  help="S3 mode: a known-good reference object key to compare distribution "
                       "drift against. A trial's only: a kept supply is measured against the "
                       "last promoted one.")
    @click.option("--all-checks", is_flag=True,
                  help="List every check in full. By default a kept delivery that became "
                       "several arrivals shows failing and warning checks in full and passing "
                       "ones as a count per dataset.")
    @click.option("--commit", is_flag=True,
                  help="Keep it: file the supply as a real delivery received now, and record "
                       "this run in the dataset's QA history.")
    @click.option("--originally-received", "originally_received", default=None,
                  help="Keeping a supply: when it was ORIGINALLY received - the email's "
                       "arrival, say - as a time (read on the asset's own clock unless it "
                       "carries an offset), `not-known`, or `storage` for each S3 object's own "
                       "time. Recorded beside our receipt; never used to file or judge the "
                       "supply.")
    @click.option("--trial", is_flag=True,
                  help="Run it as a TRIAL: the same four tools against the same rows, filed "
                       "nowhere and recorded nowhere. The opposite of --commit, stated so a "
                       "script never relies on a default it cannot see.")
    def qa(run_id, reference_run_id, file_path, reference_file, s3_key, s3_reference_key,
           commit, originally_received, trial, all_checks) -> None:
        from cli import common
        from qa_tools.common.git_identity import get_run_by

        refuse_a_broken_adapter(coll)
        cli_ = me()
        if s3_key is not None:
            if run_id is not None or file_path is not None:
                raise click.ClickException(
                    "Pass exactly one of --run-id (Synthetic mode), --file (Local files mode), "
                    "or --s3-key (S3 mode).")
            common.refuse_reference_for_kept(common.keep_from_flags(commit, trial),
                                             s3_reference_key, "--s3-reference-key")
            bucket = common.raw_bucket_name()
            run_by = get_run_by() if commit else "trial:not-recorded"
            with common.chain_progress(os.path.basename(s3_key)) as on_step:
                results, filed = cli_.run_check_s3(
                    bucket, s3_key, s3_reference_key, run_by, on_step=on_step,
                    keep=common.keep_from_flags(commit, trial), originally=originally_received)
            cli_._finish_supply(results, filed, all_checks)
            sys.exit(1 if cli_.has_failures(results) else 0)

        if file_path is not None:
            if run_id is not None:
                raise click.ClickException(
                    "Pass either --run-id (Synthetic mode) or --file (Local files mode), not both.")
            run_by = get_run_by() if commit else "trial:not-recorded"
            with common.chain_progress(os.path.basename(file_path)) as on_step:
                results, filed = cli_.run_check_local_file(
                    file_path, reference_file, run_by, on_step=on_step,
                    keep=common.keep_from_flags(commit, trial), originally=originally_received)
            cli_._finish_supply(results, filed, all_checks)
            sys.exit(1 if cli_.has_failures(results) else 0)

        if run_id is None:
            if not (sys.stdin.isatty() and sys.stdout.isatty()):
                raise click.ClickException("Not a real terminal - pass --run-id or --file explicitly.")
            cli_.run_qa_interactive(commit_default=commit)
            return

        keep = common.decide_record(run_id, keep=common.keep_from_flags(commit, trial))
        run_by = get_run_by() if keep else "trial:not-recorded"
        with common.chain_progress(run_id) as on_step:
            results, recorded_run_id = cli_.run_check(
                run_id, run_by, reference_run_id=reference_run_id, on_step=on_step, keep=keep)
        cli_._report_synthetic(results, recorded_run_id, keep, interactive=False)
        sys.exit(1 if cli_.has_failures(results) else 0)
