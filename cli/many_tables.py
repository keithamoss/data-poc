"""The N-TABLE shape of a collection's commands (REQ-TEST-245): a supply is a
delivery folder holding one file per table. Child Protection today; any
collection whose hierarchy entry lists several datasets tomorrow. Moved from
cli/cp.py, with every constant read from the collection instead of written
down.

What differs from the one-table shape: every table must be present for a
trial (the cross-table checks cannot run on a partial set), each file is
attributed to its table by its dataset's ARRIVAL PATTERN, a table two files
claim is refused naming both, and a single-table resupply is checked beside
the other tables of the last promoted run. The Local files mode folds in the
retired qa_tools/cp/check_delivery.py.

Imports are deferred to the method that needs them (criterion 7).
"""
from __future__ import annotations

import dataclasses
import os
import sys
import tempfile
from datetime import date

import rich_click as click

from cli.collection_cli import CollectionCLI, console, refuse_a_broken_adapter, words
from cli import wording


class ManyTablesCLI(CollectionCLI):
    _SOURCE_SYNTHETIC = "Synthetic - pick or generate a run"
    _SOURCE_LOCAL_FOLDER = "Local files - a delivery folder you've already downloaded"
    _SOURCE_S3 = "S3 - browse the real raw-data bucket"
    _SOURCE_LOCAL_FILE = "Local file - a CSV you've already downloaded"

    def __init__(self, coll):
        super().__init__(coll)
        n = len(self.tables)
        self._DELIVERY_FULL = f"Full delivery - {wording.all_of(n, 'real tables')}"
        self._DELIVERY_SINGLE_TABLE = "Single table - a partial resupply (one table only)"
        #: What the messages have always called this collection's deliveries.
        self.upper = coll.short.upper()

    # ---- arrivals ----------------------------------------------------------

    def arrival_path(self, run_id: str) -> str:
        """Where this run's files actually arrived - the delivery itself
        (REQ-PIPE-102). Raises rather than returning a path that is not there,
        because every caller is about to open the files in it."""
        from qa_tools.common import arrivals

        for arrival in arrivals.arrivals_for(self.collection_id, self.run_prefix):
            if arrival.run_id == run_id:
                return str(arrival.path)
        raise click.ClickException(
            f"No arrival on disk for run_id={run_id!r} - run generate-synthetic-data first?")

    def has_arrival(self, run_id: str) -> bool:
        try:
            self.arrival_path(run_id)
            return True
        except click.ClickException:
            return False

    def load_manifest(self) -> list[dict]:
        """Every arrival, RECOGNISED FROM DISK (REQ-GEN-043). A CONTESTED
        table's files travel with the entry (REQ-PIPE-202 criterion 13): the
        picker marks it and picking it is refused, naming both."""
        from qa_tools.common import arrivals

        return [a.as_entry()
                | {"contested": {ds: sorted(a.files_by_dataset.get(ds, ())) for ds in a.contested}}
                for a in arrivals.arrivals_for(self.collection_id, self.run_prefix)]

    def default_reference(self, manifest: list[dict]) -> str:
        """The last promoted run whose delivery is still on disk, falling back
        to the first recognised arrival."""
        from qa_tools.common.qa_results_reader import list_run_ids

        promoted = list_run_ids(self.agency_id, self.collection_id)
        if promoted:
            candidate = promoted[-1]
            if self.has_arrival(candidate):
                return candidate
        return manifest[0]["run_id"]

    def picker_choices(self, manifest: list[dict]) -> list[str]:
        """Marked 'recorded' where its QA already is (REQ-PIPE-086 criterion 6)
        and 'two files for one table' where a table is contested (REQ-PIPE-202
        criterion 13): listed, so it does not vanish, and refused when
        picked."""
        from cli import common
        from qa_tools.common import asset_time

        recorded = common.recorded_runs(e["run_id"] for e in manifest)
        return [f'{e["run_id"]}  ({asset_time.local_date(e["received_at"])}, {e["delivery"]})'
                + ("  - recorded" if e["run_id"] in recorded else "")
                + ("  - two files for one table" if e.get("contested") else "")
                for e in manifest]

    # ---- the files of a delivery -------------------------------------------

    @staticmethod
    def _files_in(folder: str) -> list[str]:
        """Every file directly in a folder, sorted - what a person handed over."""
        return sorted(os.path.join(folder, n) for n in os.listdir(folder)
                      if os.path.isfile(os.path.join(folder, n)))

    def _all_by_pattern(self, folder: str, recorded: bool = False) -> dict[str, str]:
        """{table: path} for every table, each file ATTRIBUTED BY ITS
        DATASET'S ARRIVAL PATTERN (REQ-PIPE-202 criterion 8) - never by
        assuming `<table>.csv`. All tables and ONE file each: a table two files
        claim is contested and nothing here may choose (REQ-PIPE-059), so it is
        refused naming both files and where the pair is settled. Checked
        BEFORE anything is filed (REQ-PIPE-103)."""
        from qa_tools.common import delivery, hierarchy, supply_files

        found: dict[str, list[str]] = {}
        for path in self._files_in(folder):
            dataset_id = delivery.dataset_for_filename(os.path.basename(path))
            if dataset_id is not None and hierarchy.dataset(dataset_id).table in self.tables:
                found.setdefault(hierarchy.dataset(dataset_id).table, []).append(path)
        several = {t: sorted(os.path.basename(p) for p in ps) for t, ps in found.items()
                   if len(ps) > 1}
        if several:
            lines = []
            for table, names in sorted(several.items()):
                entry = next(d for d in self.datasets if d.table == table)
                count = "two" if len(names) == 2 else str(len(names))
                lines.append(f"{entry.dataset_name} ({entry.dataset_id}) has {count} files - "
                             f"{' and '.join(names)} - and nothing may choose between them")
            # WHAT THE PERSON CAN DO, BY ROUTE (criterion 8 as amended, Keith,
            # 2026-10-15): a folder is not filed, so its pair is never queued.
            where = supply_files.where_to_settle(entry.dataset_id)
            todo = (f"settle the pair in Filing decisions ('{where}')" if recorded
                    else f"remove all but one file, or keep the delivery and settle the pair "
                         f"in Filing decisions ('{where}')")
            raise click.ClickException(
                f"{folder}: " + "; ".join(lines) + f" - {todo}. Neither file was checked.")
        missing = [t for t in self.tables if t not in found]
        if missing:
            raise click.ClickException(
                f"{folder} is missing a file for: {', '.join(missing)} - {wording.a_or_an(self.upper)} "
                f"delivery needs {wording.all_of(len(self.tables), 'real tables')}, the cross-table checks can't run on "
                f"a partial set")
        return {table: paths[0] for table, paths in found.items()}

    def _require_all(self, folder: str) -> None:
        self._all_by_pattern(folder)

    def _load_delivery_from_folder(self, folder: str, run_id: str, received_at=None,
                                   recorded: bool = False) -> None:
        """Stage every table for one run id from an arbitrary folder."""
        from qa_tools.tools import stage

        paths = self._all_by_pattern(folder, recorded=recorded)
        for table in self.tables:
            stage.stage_table(self.collection_id, run_id, table, paths[table],
                              received_at=received_at)

    def _refuse_a_contested_arrival(self, entry: dict) -> None:
        """Refuse an arrival whose table two files claim, naming both and
        where the pair is settled (REQ-PIPE-202 criterion 13)."""
        from qa_tools.common import hierarchy, supply_files

        contested = entry.get("contested") or {}
        if not contested:
            return
        lines = [f"{hierarchy.dataset(ds).dataset_name} has "
                 f"{'two' if len(files) == 2 else len(files)} files - {' and '.join(files)} - "
                 f"settle the pair in Filing decisions ('{supply_files.where_to_settle(ds)}')"
                 for ds, files in sorted(contested.items())]
        raise click.ClickException(
            f"{entry['run_id']} carries two files for one table: " + "; ".join(lines)
            + ". Nothing may choose between them here, so neither was checked.")

    def _refuse_a_contested_run(self, run_id: str) -> None:
        """The refusal above, for a run picked by id - asked BEFORE 'keep or
        trial?' (post-build-review #203 F4)."""
        entry = next((e for e in self.load_manifest() if e["run_id"] == run_id), None)
        if entry is not None:
            self._refuse_a_contested_arrival(entry)

    def _load_delivery(self, run_id: str) -> None:
        self._load_delivery_from_folder(self.arrival_path(run_id), run_id, recorded=True)

    # ---- the check chain ---------------------------------------------------

    def run_check(self, run_id: str, run_by: str, reference_run_id: str | None = None,
                  on_step=None, *, keep: bool = True) -> tuple[list[dict], str]:
        """The real check chain for one recognised arrival - see
        cli/one_table.py's run_check() for the keep-or-trial reasoning. THE
        TRIAL IDENTITY IS SETTLED BEFORE THE LOAD: a run's staged tables are
        named for its run id, so staging under the arrival's own id and then
        taking a trial id left dbt looking for tables that did not exist."""
        from cli import common
        from qa_tools.common import trial as trial_mod
        from qa_tools.tools import orchestrate, stage

        manifest = self.load_manifest()
        if not any(e["run_id"] == run_id for e in manifest):
            raise click.ClickException(
                f"No manifest entry for run_id={run_id!r} - run generate-synthetic-data first?")
        entry = next(e for e in manifest if e["run_id"] == run_id)
        self._refuse_a_contested_arrival(entry)
        if reference_run_id is not None and not self.has_arrival(reference_run_id):
            raise click.ClickException(
                f"Reference run {reference_run_id!r}'s delivery isn't on disk - "
                f"run generate-synthetic-data first?")
        if keep:
            common.refuse_reference_for_kept(keep, reference_run_id, "--reference-run-id")
            arrival = common.kept_arrival(self.collection_id, self.run_prefix, run_id)
            common.record_delivery_of(arrival)
            stage.stage_arrival(self.collection_id, arrival)
            return (orchestrate.run_arrivals(self.collection_id, [arrival], run_by,
                                             on_step=on_step), run_id)
        recorded_run_id = trial_mod.trial_run_id()
        entry = {**entry, "run_id": recorded_run_id}
        # ONLY WHERE AN OPERATOR NAMED ONE: a resolved reference's
        # distribution comes from what that run recorded (REQ-QAC-088).
        if reference_run_id is not None:
            self._load_delivery(reference_run_id)
        self._load_delivery_from_folder(self.arrival_path(run_id), recorded_run_id,
                                        recorded=True)
        results = orchestrate.run_single(self.collection_id, entry,
                                         reference_run_id=reference_run_id, run_by=run_by,
                                         on_step=on_step)
        return results, recorded_run_id

    def _check_filed_delivery(self, filed, run_by: str, on_step=None) -> list[dict]:
        """Stage, file, check and promote every arrival of a filed delivery,
        in the batch's own order - from recognition, never the folder's own
        listing."""
        from qa_tools.common import hand_filing
        from qa_tools.tools import orchestrate, stage

        found = hand_filing.arrivals_of(filed, self.collection_id, self.run_prefix)
        for arrival in found:
            stage.stage_arrival(self.collection_id, arrival)
        return orchestrate.run_arrivals(self.collection_id, found, run_by, on_step=on_step)

    def run_check_local_folder(self, folder: str, reference_folder: str, run_by: str,
                               run_id: str | None = None, run_date: str | None = None,
                               on_step=None, keep: bool | None = None,
                               originally: str | None = None, route: str = "folder",
                               storage_times: dict | None = None):
        """The Local files mode's check body. KEEP OR TRIAL FIRST
        (REQ-PIPE-086 criterion 14). Kept: whatever recognition places in the
        folder is the delivery - one table or all of them - and the WHOLE
        FOLDER IS ONE DELIVERY (REQ-PIPE-103). A trial needs every table and a
        reference."""
        from cli import common
        from qa_tools.common import asset_time, delivery
        from qa_tools.tools import orchestrate

        run_date = run_date or asset_time.now().date().isoformat()
        keep = common.decide_keep(self._files_in(folder), keep=keep)
        common.refuse_reference_for_kept(keep, reference_folder, "--reference-folder")
        if keep:
            paths = [p for p in self._files_in(folder) if delivery.dataset_for_filename(
                os.path.basename(p)) is not None]
            # WHAT IS LEFT BEHIND IS NAMED (Keith, 2026-10-06, #120 Q4), not refused.
            left = sorted(os.path.basename(p) for p in self._files_in(folder) if p not in paths)
            if paths and left:
                console.print(
                    f"Not recognised as any dataset, so left behind: {', '.join(left)}. If one "
                    f"is a renamed extract, rename it to its dataset's file name and keep it "
                    f"again - it is not part of this delivery.", style="yellow", markup=False,
                    highlight=False)
            if not paths:
                raise click.ClickException(
                    f"nothing in {folder} matches any dataset's arrival pattern, so there is "
                    f"nothing to file. Pass --trial to check it without filing.")
        else:
            by_table = self._all_by_pattern(folder)
            common.require_reference_for_trial(reference_folder, "--reference-folder")
            paths = [by_table[t] for t in self.tables]
        filed = common.file_or_trial(
            paths, self.collection_id, self.run_prefix, keep=keep, route=route,
            originally=originally, storage_times=storage_times)
        if run_id is not None and not filed.delivery_name:
            filed = dataclasses.replace(filed, run_id=run_id)
        if filed.delivery_name:
            # KEPT: ONE ARRIVAL PER DATASET, exactly as the batch would process
            # them (REQ-PIPE-105 criterion 1; Keith, 2026-10-02).
            return self._check_filed_delivery(filed, run_by, on_step), filed
        run_id = filed.run_id
        folder = os.path.dirname(filed.paths[0])
        if reference_folder is None or len(filed.paths) != len(self.tables):
            # A KEPT FOLDER THAT FELL BACK TO A TRIAL: a trial needs every
            # table and its reference, which nobody was asked for.
            self._require_all(folder)
            reference_folder = common.reference_for_fallback_trial(
                reference_folder, "--reference-folder", "folder")
        reference_run_id = common.reference_run_id()
        self._load_delivery_from_folder(reference_folder, reference_run_id)
        self._load_delivery_from_folder(folder, run_id, received_at=filed.received_at)
        entry = {"run_id": run_id, "dirty_severity": None,
                 "received_at": asset_time.isoformat(
                     filed.received_at
                     or asset_time.start_of_day(date.fromisoformat(run_date)))}
        try:
            results = orchestrate.run_single(self.collection_id, entry,
                                             reference_run_id=reference_run_id, run_by=run_by,
                                             on_step=on_step)
        finally:
            common.discard_reference(reference_run_id)
        return results, filed

    def run_check_s3_delivery(self, bucket: str, delivery_prefix: str,
                              reference_delivery_prefix: str, run_by: str,
                              run_id: str | None = None, run_date: str | None = None,
                              s3_client=None, on_step=None, keep: bool | None = None,
                              originally: str | None = None):
        """S3 mode for a whole delivery: every object under one prefix,
        downloaded, then Local files mode. Decided before any download
        (REQ-PIPE-086 criterion 14)."""
        from cli import common
        from qa_tools.common import s3_source

        keep = common.decide_keep([delivery_prefix], keep=keep)
        common.refuse_reference_for_kept(keep, reference_delivery_prefix,
                                         "--s3-reference-delivery")
        if not keep:
            common.require_reference_for_trial(reference_delivery_prefix,
                                               "--s3-reference-delivery")
        staging_dir = tempfile.mkdtemp(prefix="mothman-s3-")
        s3_source.download_prefix(bucket, delivery_prefix, staging_dir, s3_client=s3_client)
        reference_staging_dir = None
        if reference_delivery_prefix is not None:
            reference_staging_dir = tempfile.mkdtemp(prefix="mothman-s3-ref-")
            s3_source.download_prefix(bucket, reference_delivery_prefix, reference_staging_dir,
                                      s3_client=s3_client)
        times = s3_source.last_modified(
            bucket, s3_source.list_keys(bucket, delivery_prefix, s3_client=s3_client),
            s3_client=s3_client)
        return self.run_check_local_folder(
            staging_dir, reference_staging_dir, run_by, run_id=run_id, run_date=run_date,
            on_step=on_step, keep=keep, originally=originally, route="s3", storage_times=times)

    def run_check_single_table(self, table: str, file_path: str, run_by: str,
                               run_id: str | None = None, run_date: str | None = None,
                               on_step=None, keep: bool | None = None,
                               originally: str | None = None, route: str = "table",
                               storage_times: dict | None = None):
        """A partial resupply: one table re-sent. Kept, it is a ONE-FILE
        DELIVERY (REQ-PIPE-103 criterion 7) through the pipeline's own
        lifecycle, its siblings read from the period it was filed to. A trial
        BORROWS the other tables from the last promoted run's delivery, as
        views, never re-staged - staging them under this arrival would record
        them as having arrived in a delivery that carried one."""
        from cli import common
        from qa_tools.common import asset_time, delivery, hierarchy, supply_db
        from qa_tools.tools import orchestrate, stage

        run_date = run_date or asset_time.now().date().isoformat()
        keep = common.decide_keep([file_path], keep=keep)
        recognised = delivery.dataset_for_filename(os.path.basename(file_path))
        if keep and recognised is not None and hierarchy.dataset(recognised).table != table:
            raise click.ClickException(
                f"{os.path.basename(file_path)} is recognised as "
                f"{hierarchy.dataset(recognised).table}, not {table} - nothing was filed.")
        filed = common.file_or_trial([file_path], self.collection_id, self.run_prefix,
                                     keep=keep, route=route, originally=originally,
                                     storage_times=storage_times)
        if filed.delivery_name:
            return self._check_filed_delivery(filed, run_by, on_step), filed

        others = len(self.tables) - 1
        manifest = self.load_manifest()
        other_tables_run_id = self.default_reference(manifest)
        if not self.has_arrival(other_tables_run_id):
            raise click.ClickException(
                f"No delivery on disk for run {other_tables_run_id!r} (the last Promoted/fallback "
                f"run) - run generate-synthetic-data first? A single-table trial needs a "
                f"known-good delivery already on disk to source the other {others} tables from.")
        if run_id is not None:
            filed = dataclasses.replace(filed, run_id=run_id)
        run_id = filed.run_id
        file_path = filed.paths[0]
        self._load_delivery(other_tables_run_id)
        stage.stage_table(self.collection_id, run_id, table, file_path,
                          received_at=filed.received_at)
        with supply_db.connect(label=f"mothman:{self.short}-single-table") as conn:
            borrowed = supply_db.borrow_views(
                conn, run_id, other_tables_run_id, [t for t in self.tables if t != table])
        missing = sorted({t for t in self.tables if t != table} - set(borrowed))
        if missing:
            raise click.ClickException(
                f"run {other_tables_run_id!r} has no resolved supply for "
                f"{', '.join(missing)}, so the other tables cannot be read from it - "
                f"{self.upper}'s cross-table checks need all {words(len(self.tables))}.")
        entry = {"run_id": run_id, "dirty_severity": None,
                 "received_at": asset_time.isoformat(
                     filed.received_at
                     or asset_time.start_of_day(date.fromisoformat(run_date)))}
        # THE BORROWED TABLES AND THE DRIFT REFERENCE ARE NOT THE SAME
        # QUESTION: the reference is resolved from the records (REQ-QAC-108).
        results = orchestrate.run_single(self.collection_id, entry, reference_run_id=None,
                                         run_by=run_by, on_step=on_step)
        return results, filed

    def run_check_s3_single_table(self, bucket: str, table: str, key: str, run_by: str,
                                  run_id: str | None = None, run_date: str | None = None,
                                  s3_client=None, on_step=None, keep: bool | None = None,
                                  originally: str | None = None):
        """Single-table mode from S3: download, then the local single-table
        check."""
        from qa_tools.common import s3_source

        staging_dir = tempfile.mkdtemp(prefix="mothman-s3-")
        local_path = s3_source.download_key(bucket, key, staging_dir, s3_client=s3_client)
        return self.run_check_single_table(
            table, local_path, run_by, run_id=run_id, run_date=run_date, on_step=on_step,
            keep=keep, originally=originally, route="s3",
            storage_times=s3_source.last_modified(bucket, [key], s3_client=s3_client))

    # ---- the interactive flow ----------------------------------------------

    def run_qa_interactive(self, commit_default: bool = False) -> None:
        """The Quality Assurance flow, from `mothman <short> qa` in a real
        terminal and from the TUI."""
        from cli import common
        from qa_tools.common.git_identity import get_run_by

        run_by = get_run_by()
        short = self.short
        delivery_scope = common.select(
            "Full delivery or single table?", [self._DELIVERY_FULL, self._DELIVERY_SINGLE_TABLE],
            flag_hint=f"mothman {short} qa --run-id <run_id> / mothman {short} qa --table <table> "
                      f"--file <csv>")
        if delivery_scope is None:
            return
        if delivery_scope == self._DELIVERY_SINGLE_TABLE:
            self._run_qa_interactive_single_table(run_by, commit_default)
            return
        source = common.select(
            "Which source?", [self._SOURCE_SYNTHETIC, self._SOURCE_LOCAL_FOLDER, self._SOURCE_S3],
            flag_hint=f"mothman {short} qa --run-id <run_id> / mothman {short} qa --folder <dir> "
                      f"--reference-folder <dir> / "
                      f"mothman {short} qa --s3-delivery <prefix> --s3-reference-delivery <prefix>")
        if source is None:
            return
        if source == self._SOURCE_LOCAL_FOLDER:
            self._run_qa_interactive_local_folder(run_by, commit_default)
            return
        if source == self._SOURCE_S3:
            self._run_qa_interactive_s3(run_by, commit_default)
            return

        if not self.manifest_exists():
            if not common.confirm("No synthetic data generated yet - generate it now?",
                                  yes=False, default=True):
                console.print("Nothing to check without synthetic data. Stopping.", style="yellow")
                return
            from generator import collections as providers

            note = getattr(providers.provider(self.collection_id), "generating_note", "")
            console.print(f"Generating synthetic data ({note})..." if note
                          else "Generating synthetic data...", style="dim")
            self.generate_synthetic_data()

        manifest = self.load_manifest()
        choice = common.select("Pick a run to check:", self.picker_choices(manifest),
                               flag_hint=f"mothman {short} qa --run-id <run_id>")
        if choice is None:
            return
        run_id = self.run_id_from_choice(choice)
        self._refuse_a_contested_run(run_id)
        keep = common.decide_record(run_id, keep=True if commit_default else None)
        console.print(f"Running the real dbt-core/Soda Core/datacontract-cli/Evidently chain "
                      f"for {run_id}...", style="dim")
        with common.chain_progress(run_id) as on_step:
            results, recorded_run_id = self.run_check(run_id, run_by, on_step=on_step, keep=keep)
        self._report_synthetic(results, recorded_run_id, keep, interactive=True)

    def _run_qa_interactive_local_folder(self, run_by: str, commit_default: bool) -> None:
        from cli import common

        short = self.short
        folder = common.path_prompt(
            "Path to the delivery folder you've already downloaded:",
            flag_hint=f"mothman {short} qa --folder <dir> [--trial --reference-folder <dir>]")
        if folder is None:
            return
        keep = common.decide_keep(self._files_in(folder), keep=True if commit_default else None)
        reference_folder = None
        if not keep:
            reference_folder = common.path_prompt(
                f"Path to a known-good reference delivery folder ({wording.all_of(len(self.tables), 'tables')}) "
                f"to compare against:",
                flag_hint=f"mothman {short} qa --folder <dir> --trial --reference-folder <dir>")
            if reference_folder is None:
                return
        console.print(f"Running the real dbt-core/Soda Core/datacontract-cli/Evidently chain "
                      f"for {folder}...", style="dim")
        with common.chain_progress(os.path.basename(folder.rstrip("/"))) as on_step:
            results, filed = self.run_check_local_folder(
                folder, reference_folder, run_by, on_step=on_step, keep=keep)
        self._finish_supply(results, filed)

    def _run_qa_interactive_s3(self, run_by: str, commit_default: bool) -> None:
        """Lists the delivery prefixes one level under the configured
        s3Source prefix, picks one (and a reference for a trial)."""
        from cli import common
        from qa_tools.common import s3_source

        bucket = common.raw_bucket_name()
        prefix = self.s3_config()["prefix"] or ""
        console.print(f"Listing deliveries under s3://{bucket}/{prefix} ...", style="dim")
        deliveries = s3_source.list_delivery_prefixes(bucket, prefix)
        if not deliveries:
            console.print(f"No deliveries under s3://{bucket}/{prefix}", style="yellow")
            return
        flag_hint = (f"mothman {self.short} qa --s3-delivery <prefix> "
                     f"--s3-reference-delivery <prefix>")
        chosen = common.select("Pick a delivery to check:", deliveries, flag_hint=flag_hint)
        if chosen is None:
            return
        keep = common.decide_keep([chosen], keep=True if commit_default else None)
        reference_delivery = None
        if not keep:
            reference_delivery = common.select("Pick a known-good reference delivery:",
                                               deliveries, flag_hint=flag_hint)
            if reference_delivery is None:
                return
        console.print(f"Downloading + running the real dbt-core/Soda Core/datacontract-cli/"
                      f"Evidently chain for s3://{bucket}/{chosen}...", style="dim")
        with common.chain_progress(chosen.rstrip("/").rsplit("/", 1)[-1]) as on_step:
            results, filed = self.run_check_s3_delivery(
                bucket, chosen, reference_delivery, run_by, on_step=on_step, keep=keep)
        self._finish_supply(results, filed)

    def _run_qa_interactive_single_table(self, run_by: str, commit_default: bool) -> None:
        """Picks a table, then Local file or S3 for just that table; the
        other tables and the drift reference come from the records."""
        from cli import common
        from qa_tools.common import s3_source

        short = self.short
        flag_hint = (f"mothman {short} qa --table <table> --file <csv> / "
                     f"mothman {short} qa --table <table> --s3-key <key>")
        table = common.select("Which table?", self.tables, flag_hint=flag_hint)
        if table is None:
            return
        source = common.select("Which source?", [self._SOURCE_LOCAL_FILE, self._SOURCE_S3],
                               flag_hint=flag_hint)
        if source is None:
            return
        if source == self._SOURCE_S3:
            bucket = common.raw_bucket_name()
            prefix = self.s3_config()["prefix"] or ""
            console.print(f"Listing s3://{bucket}/{prefix} ...", style="dim")
            keys = s3_source.list_keys(bucket, prefix)
            if not keys:
                console.print(f"No objects under s3://{bucket}/{prefix}", style="yellow")
                return
            key = common.select(f"Pick the {table} object to check:", keys, flag_hint=flag_hint)
            if key is None:
                return
            console.print(f"Downloading + running the real dbt-core/Soda Core/datacontract-cli/"
                          f"Evidently chain for s3://{bucket}/{key} (table: {table})...",
                          style="dim")
            with common.chain_progress(key.rsplit("/", 1)[-1]) as on_step:
                results, filed = self.run_check_s3_single_table(
                    bucket, table, key, run_by, on_step=on_step,
                    keep=True if commit_default else None)
        else:
            file_path = common.path_prompt(f"Path to the {table} CSV you've already downloaded:",
                                           flag_hint=flag_hint)
            if file_path is None:
                return
            console.print(f"Running the real dbt-core/Soda Core/datacontract-cli/Evidently chain "
                          f"for {file_path} (table: {table})...", style="dim")
            with common.chain_progress(os.path.basename(file_path)) as on_step:
                results, filed = self.run_check_single_table(
                    table, file_path, run_by, on_step=on_step,
                    keep=True if commit_default else None)
        self._finish_supply(results, filed)


# ---- the commands ---------------------------------------------------------------

def add_commands(group: click.Group, coll, *, with_target_trial: bool) -> None:
    """`generate-synthetic-data` and `qa` for an N-table collection. Options and
    help read from the collection - --table chooses from the hierarchy's own
    tables (criterion 3) - so the text is today's exactly."""
    from cli import collection_cli

    name = collection_cli.label(coll)
    tables = [d.table for d in coll.datasets]
    others = len(tables) - 1
    me = lambda: collection_cli.of(coll.id)  # noqa: E731 - resolved when the command runs

    def generate(yes: bool, skip_target_trial: bool = False) -> None:
        from cli import common

        refuse_a_broken_adapter(coll)
        cli_ = me()
        if cli_.manifest_exists() and not common.confirm(
                f"This will regenerate the {name} deliveries "
                "(deterministic - same content either way). Continue?",
                yes=yes, default=True):
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
        generate.__click_params__.reverse()
    group.command("generate-synthetic-data",
                  help=f"Generate (or deterministically regenerate) the full synthetic {name} "
                       f"collection.")(generate)

    prefix = coll.run_prefix

    @group.command("qa", help=f"Run the real QA check chain against {wording.a_or_an(name)} run - Synthetic "
                              f"(--run-id), Local files (--folder/--reference-folder), S3 "
                              f"(--s3-delivery/--s3-reference-delivery), or single-table "
                              f"(--table plus --file or --s3-key) source mode.")
    @click.option("--run-id", default=None,
                  help=f"Synthetic mode: an existing manifest run_id (e.g. {prefix}05_2024-...). "
                       f"Omit to pick interactively.")
    @click.option("--reference-run-id", default=None,
                  help="Synthetic mode, a trial's only: a run to compare distribution drift "
                       "against. There is no default; a kept run is measured against the last "
                       "promoted supply.")
    @click.option("--folder", "folder_path", default=None,
                  type=click.Path(exists=True, file_okay=False),
                  help=f"Local files mode: an already-downloaded delivery folder (instead of "
                       f"--run-id). Kept, whatever recognition places in it is the delivery; a "
                       f"trial needs {wording.all_of(len(tables), 'tables')}.")
    @click.option("--reference-folder", default=None, type=click.Path(exists=True, file_okay=False),
                  help="Local files mode: a known-good reference delivery folder to compare "
                       "distribution drift against. A trial's only: a kept supply is measured "
                       "against the last promoted one.")
    @click.option("--s3-delivery", default=None,
                  help="S3 mode: a delivery prefix under the dataset's s3Source prefix to check "
                       "(instead of --run-id/--folder).")
    @click.option("--s3-reference-delivery", default=None,
                  help="S3 mode: a known-good reference delivery prefix to compare distribution "
                       "drift against. A trial's only: a kept supply is measured against the "
                       "last promoted one.")
    @click.option("--table", type=click.Choice(tables), default=None,
                  help=f"Single-table mode (plans/tooling.md #1 Phase 3.5): check just this one "
                       f"table (a real partial resupply). Kept, it is one arrival, read beside "
                       f"whatever is filed for its period; as a trial the other {others} tables "
                       f"come from the last promoted run. Required together with --file or "
                       f"--s3-key.")
    @click.option("--file", "table_file", default=None, type=click.Path(exists=True, dir_okay=False),
                  help="Single-table mode: an already-downloaded CSV for --table (instead of "
                       "--folder/--run-id).")
    @click.option("--s3-key", default=None,
                  help="Single-table mode: an object key under the dataset's s3Source prefix "
                       "for --table (instead of --s3-delivery).")
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
    def qa(run_id, reference_run_id, folder_path, reference_folder, s3_delivery,
           s3_reference_delivery, table, table_file, s3_key, commit, originally_received, trial,
           all_checks) -> None:
        from cli import common
        from qa_tools.common.git_identity import get_run_by

        refuse_a_broken_adapter(coll)
        cli_ = me()
        if table is None and (table_file is not None or s3_key is not None):
            raise click.ClickException(
                "--file/--s3-key need --table (single-table mode) to know which table they're for.")
        if table is not None:
            if run_id is not None or folder_path is not None or s3_delivery is not None:
                raise click.ClickException(
                    "Pass --table only with --file or --s3-key (single-table mode) - not "
                    "--run-id/--folder/--s3-delivery (those are full-delivery modes).")
            if (table_file is None) == (s3_key is None):
                raise click.ClickException("--table requires exactly one of --file or --s3-key.")
            run_by = get_run_by() if commit else "trial:not-recorded"
            keep = common.keep_from_flags(commit, trial)
            if table_file is not None:
                with common.chain_progress(os.path.basename(table_file)) as on_step:
                    results, filed = cli_.run_check_single_table(
                        table, table_file, run_by, on_step=on_step, keep=keep,
                        originally=originally_received)
            else:
                bucket = common.raw_bucket_name()
                with common.chain_progress(s3_key.rsplit("/", 1)[-1]) as on_step:
                    results, filed = cli_.run_check_s3_single_table(
                        bucket, table, s3_key, run_by, on_step=on_step, keep=keep,
                        originally=originally_received)
            cli_._finish_supply(results, filed, all_checks)
            sys.exit(cli_.exit_status(results, cli_.arrivals_filed(filed)))

        if s3_delivery is not None:
            if run_id is not None or folder_path is not None:
                raise click.ClickException(
                    "Pass exactly one of --run-id (Synthetic mode), --folder (Local files mode), "
                    "or --s3-delivery (S3 mode).")
            common.refuse_reference_for_kept(common.keep_from_flags(commit, trial),
                                             s3_reference_delivery, "--s3-reference-delivery")
            bucket = common.raw_bucket_name()
            run_by = get_run_by() if commit else "trial:not-recorded"
            with common.chain_progress(s3_delivery.rstrip("/").rsplit("/", 1)[-1]) as on_step:
                results, filed = cli_.run_check_s3_delivery(
                    bucket, s3_delivery, s3_reference_delivery, run_by, on_step=on_step,
                    keep=common.keep_from_flags(commit, trial), originally=originally_received)
            cli_._finish_supply(results, filed, all_checks)
            sys.exit(cli_.exit_status(results, cli_.arrivals_filed(filed)))

        if folder_path is not None:
            if run_id is not None:
                raise click.ClickException(
                    "Pass either --run-id (Synthetic mode) or --folder (Local files mode), not "
                    "both.")
            run_by = get_run_by() if commit else "trial:not-recorded"
            with common.chain_progress(os.path.basename(folder_path.rstrip("/"))) as on_step:
                results, filed = cli_.run_check_local_folder(
                    folder_path, reference_folder, run_by, on_step=on_step,
                    keep=common.keep_from_flags(commit, trial), originally=originally_received)
            cli_._finish_supply(results, filed, all_checks)
            sys.exit(cli_.exit_status(results, cli_.arrivals_filed(filed)))

        if run_id is None:
            if not (sys.stdin.isatty() and sys.stdout.isatty()):
                raise click.ClickException(
                    "Not a real terminal - pass --run-id or --folder explicitly.")
            cli_.run_qa_interactive(commit_default=commit)
            return

        cli_._refuse_a_contested_run(run_id)
        keep = common.decide_record(run_id, keep=common.keep_from_flags(commit, trial))
        run_by = get_run_by() if keep else "trial:not-recorded"
        with common.chain_progress(run_id) as on_step:
            results, recorded_run_id = cli_.run_check(
                run_id, run_by, reference_run_id=reference_run_id, on_step=on_step, keep=keep)
        cli_._report_synthetic(results, recorded_run_id, keep, interactive=False)
        sys.exit(cli_.exit_status(results, cli_.arrivals_kept(recorded_run_id) if keep else ()))
