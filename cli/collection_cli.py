"""One factory for every collection's `mothman <short>` group (REQ-TEST-245).

WHAT IT REPLACED: cli/bdm.py and cli/cp.py, one hand-written module per
collection, about 1,700 lines between them and most of it the same code
twice. A thirtieth collection would have been a thirtieth copy.

WHAT STILL DIFFERS, AND HOW: only the SHAPE of a supply, read from the
hierarchy - never the collection's name.
- A ONE-TABLE collection (Birth Registrations) is one CSV: its `qa` takes
  --file/--reference-file and an S3 key (cli/one_table.py).
- An N-TABLE collection (Child Protection) is a delivery folder: its `qa`
  takes --folder/--reference-folder, an S3 delivery prefix, and --table for
  a single-table resupply, choosing from the hierarchy's tables
  (cli/many_tables.py).
The label follows the same rule (criterion 2): a one-table collection by its
dataset's name, an N-table one by its collection's name - which is exactly
what people read today. Whether the target trial is offered is the
generator provider's one declaration (criterion 4).

CHEAP TO BUILD (criterion 7): building every group reads the hierarchy and
the providers' declarations only. Nothing here imports a QA tool, pandas or
numpy; each command imports what it runs when it runs.

A BROKEN ADAPTER TAKES DOWN ONLY ITS OWN COMMANDS (criterion 8): a command
loads its collection's adapter first and refuses, naming the collection and
the error, without a traceback; every other command is untouched.
"""
from __future__ import annotations

import functools
import os

import rich_click as click

from qa_tools.common import assets
from rich.console import Console

console = Console()

ROOT = os.path.join(os.path.dirname(__file__), "..")

_STATUS_STYLE = {"pass": "green", "warn": "yellow", "fail": "red", "error": "bold red"}

#: The number words the multi-table messages have always used ("all six").
_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
          8: "eight", 9: "nine", 10: "ten"}


def words(n: int) -> str:
    return _WORDS.get(n, str(n))


class TargetTrialFailed(click.ClickException):
    """The real tools did not read an injected target as it was built
    (REQ-GEN-186 criterion 2)."""


def label(coll) -> str:
    """A one-table collection by its dataset's name, an N-table one by its
    collection's name (criterion 2)."""
    return coll.label


def _provider(coll):
    from generator import collections as providers

    try:
        return providers.provider(coll.id)
    except providers.NoProviderError:
        return None


class CollectionCLI:
    """What every collection's commands share; cli/one_table.py and
    cli/many_tables.py add what their shape needs."""

    TargetTrialFailed = TargetTrialFailed

    def __init__(self, coll):
        self.coll = coll
        self.collection_id = coll.id
        self.agency_id = coll.agency_id
        self.short = coll.short
        self.run_prefix = coll.run_prefix
        self.datasets = list(coll.datasets)
        self.tables = [d.table for d in coll.datasets]
        self.label = label(coll)
        self.contract_path = os.path.join(ROOT, assets.folder_rel(), coll.contract)

    # ---- its commands ----------------------------------------------------------

    @functools.cached_property
    def group(self) -> click.Group:
        """This collection's `mothman <short>` group, as make_group() builds it."""
        return make_group(self.coll)

    @property
    def qa_command(self) -> click.Command:
        return self.group.commands["qa"]

    @property
    def generate_synthetic_data_command(self) -> click.Command:
        return self.group.commands["generate-synthetic-data"]

    # ---- shared --------------------------------------------------------------

    def s3_config(self) -> dict:
        """The real s3Source/localSource/arrivalPattern config off this
        collection's own contract YAML (qa_tools.common.s3_source)."""
        from qa_tools.common import s3_source

        return s3_source.dataset_s3_config(self.contract_path)

    def generated_output_dir(self) -> str:
        """Where `generate-synthetic-data` leaves its output: the delivery tree
        (REQ-PIPE-102)."""
        from generator import driver

        return str(driver.deliveries_dir())

    @property
    def has_target_trial(self) -> bool:
        provider = _provider(self.coll)
        return bool(provider and provider.target_trial)

    def generate_synthetic_data(self, trial: bool | None = None) -> None:
        """Generate through the shared driver (REQ-GEN-246), then the target
        trial where the provider declares one, then the scenario map -
        cli/pipeline.py's generate_collection(). The trial defaults to what
        the provider declares; asking it of a collection without one is
        refused by name."""
        from cli.pipeline import generate_collection

        generate_collection(self.collection_id,
                            trial=self.has_target_trial if trial is None else trial)

    # ---- the target trial (REQ-GEN-186; REQ-GEN-298 criterion 10) ----------

    def try_targets(self, collection_id: str | None = None, say=None) -> int:
        """Run the four real tools on every supply the generator just wrote to a
        target it tries - every injected target, and for a provider recording
        planned verdicts every amber, red and scenario supply (REQ-GEN-298
        criterion 13) - recording nothing (REQ-GEN-186 criterion 1). Returns
        how many were tried.

        ONE METHOD FOR EVERY COLLECTION, naming none (REQ-GEN-298 criterion
        10), moved from cli/one_table.py. EACH SUPPLY FROM ITS OWN RECORD
        (criterion 12): its dataset, table, file and reference, never the
        command's one dataset. A collection whose checks read another
        collection's tables tries each supply IN ITS SLOT'S PERIOD, in
        parallel (cli/target_trial.py); one whose checks read only its own
        tries each as a local file, as it always has.

        A DISAGREEMENT FAILS GENERATION AND TAKES THE HISTORY WITH IT
        (REQ-GEN-186 criterion 2): every delivery just written - every stream's
        - is removed before the failure is raised, naming every disagreement.
        The verdict is the promotion gate's own reading of the trial's results
        (qa_tools/common/target_agreement.py), checked on the supply's own day."""
        from cli import target_trial
        from generator import collections as providers
        from generator import driver, targets
        from qa_tools.common import delivery, run_reads, target_agreement

        provider = providers.provider(collection_id or self.collection_id)
        say = say or (lambda msg: console.print(msg, style="dim"))
        # WHERE THE GENERATOR JUST WROTE (targets.just_written) - never the
        # pipeline's view of data/.
        try:
            built, written_to = targets.just_written()
        except ValueError as exc:
            # A RECORD THAT DOES NOT ADD UP fails like any disagreement, not
            # as a traceback (post-build-review #157 finding 7).
            delivery.remove_deliveries(driver.provider_delivery_names(provider),
                                       driver.deliveries_dir(), driver.receipts_dir())
            raise self.TargetTrialFailed(f"what the generator built could not be read, so the "
                                         f"deliveries just written were removed: {exc}") from exc
        tried = [b for b in built if (b.injected or b.tried)
                 and b.dataset_id in provider.target_datasets]
        found = []
        ready = []
        for one in tried:
            if one.reference is None:
                found.append(target_agreement.Disagreement(
                    one.label, one.dataset_id, one.target, None,
                    ("it has no lead-in to be measured against",)))
            else:
                ready.append(one)
        if run_reads.reads_for(provider.collection_id).foreign:
            specs = []
            for one in ready:
                # A SUPPLY WHOSE FILES CANNOT BE FOUND IS ITS OWN DISAGREEMENT,
                # never the end of every other trial.
                try:
                    specs.append(target_trial.spec_of(one, written_to))
                except ValueError as exc:
                    found.append(target_agreement.ReadDisagreement(
                        one.label, one.dataset_id, (str(exc),)))
            disagreements, took, workers = target_trial.try_all(provider.collection_id,
                                                                specs, say=say)
            found += disagreements
            # MEASURED AND SAID (criterion 13), with REQ-PIPE-296's measurement.
            say(f"Tried {len(specs)} supplies in their slots' periods in {took:.0f}s on "
                f"{workers} worker(s)")
        else:
            for one in ready:
                say(f"Trying {one.label} against the real tools (built to {one.target})")
                results, _filed = self.run_check_local_file(
                    str(targets.csv_of(one.delivery, written_to, one.filename,
                                       dataset_id=one.dataset_id)),
                    str(targets.csv_of(one.reference, written_to, dataset_id=one.dataset_id)),
                    target_trial.RUN_BY, keep=False, run_date=one.day)
                disagreement = target_agreement.compare(one.dataset_id, results, one.target,
                                                        one.label, one.rules)
                if disagreement:
                    found.append(disagreement)
        if found:
            removed = delivery.remove_deliveries(driver.provider_delivery_names(provider),
                                                 written_to, driver.receipts_dir())
            raise self.TargetTrialFailed(
                f"{len(found)} disagreement(s) among {len(tried)} tried supplies: they did not "
                f"read as built, so the {removed} {self.label} deliveries just written were "
                f"removed:\n" + "\n".join(f"  - {d}" for d in found))
        return len(tried)

    def manifest_exists(self) -> bool:
        """Is there anything to pick from? With no deliveries on disk there
        are no arrivals, which is what the picker needs to know."""
        return bool(self.load_manifest())

    def report_table(self, results: list[dict], run_id: str):
        from rich.table import Table

        from cli import common

        table = Table(title=f"Quality Assurance report - {run_id}")
        table.add_column("Tool")
        table.add_column("Check")
        table.add_column("Status")
        for r in results:
            style = _STATUS_STYLE.get(r.get("status"), "")
            status = r.get("status", "?")
            cell = f"[{style}]{status}[/{style}]" if style else status
            table.add_row(r.get("engine", "?"), common.check_label(r),
                          cell + common.reference_suffix(r))
        n_fail = sum(1 for r in results if r.get("status") in ("fail", "error"))
        n_warn = sum(1 for r in results if r.get("status") == "warn")
        n_pass = sum(1 for r in results if r.get("status") == "pass")
        table.caption = (f"{n_pass} pass / {n_warn} warn / {n_fail} fail-or-error, "
                         f"{len(results)} checks total")
        return table

    @staticmethod
    def has_failures(results: list[dict]) -> bool:
        return any(r.get("status") in ("fail", "error") for r in results)

    def arrivals_kept(self, run_id: str) -> list:
        """The kept synthetic arrival, for the gate's part of the exit status."""
        from cli import common

        try:
            return [common.kept_arrival(self.collection_id, self.run_prefix, run_id)]
        except click.ClickException:
            return []

    def arrivals_filed(self, filed) -> list:
        """The arrivals a kept hand-filed supply became - none for a trial."""
        from qa_tools.common import hand_filing

        if not getattr(filed, "delivery_name", None):
            return []
        return hand_filing.arrivals_of(filed, self.collection_id, self.run_prefix)

    def exit_status(self, results: list[dict], arrivals=()) -> int:
        """`mothman <short> qa`'s exit status, FED BY THE GATE (REQ-PIPE-276
        criterion 3): its own run's results, and - for a kept run - whether
        a supply of its package ends held back on a red, a re-check against
        the warehouse included, whose results it prints as a table headed
        're-checked against the warehouse'. 1 where anything is red, else 0;
        a failed stage has already exited 2. NEVER 3 (PROVISIONAL, option B
        of the post-build critic's call): exit 3's meanings are not widened
        to qa - an agreement backstop refusal is said by the run's own output
        and by `mothman pipeline process` - so qa never asks the backstop."""
        from qa_tools.common import gate, processing_pass, supply_db

        red = self.has_failures(results)
        if arrivals:
            try:
                with supply_db.connect(read_only=True, label="mothman:qa-exit") as conn:
                    got = gate.touched(conn, gate.supplies_of_arrivals(
                        conn, arrivals, with_package=True))
            except Exception as exc:  # noqa: BLE001 - the run's own results still say red
                console.print(f"The gate's outcome could not be read ({exc}); the exit "
                              f"status is the run's own results'.", style="yellow",
                              markup=False, highlight=False)
                got = gate.Touched()
            if got.rechecks:
                console.print(self.report_table(got.rechecks,
                                                "re-checked against the warehouse"))
            red = red or got.red
        return processing_pass.EXIT_RED if red else processing_pass.EXIT_OK

    @staticmethod
    def run_id_from_choice(choice: str) -> str:
        return choice.split()[0]

    def _report_synthetic(self, results: list[dict], recorded_run_id: str, keep: bool,
                          *, interactive: bool) -> None:
        """Report a Synthetic-mode check, and say what became of it. The
        keep-or-trial question was asked before the chain ran (REQ-PIPE-089
        criterion 8), because results are recorded as the run completes."""
        from cli import common, filing_tui

        console.print(self.report_table(results, recorded_run_id))
        if not keep:
            console.print(f"TRIAL {recorded_run_id} - the real tools ran against the same rows "
                          "and nothing was recorded.", style="dim")
        elif interactive:
            common.report_recorded(recorded_run_id, len(results))
            common.report_kept_arrival(self.collection_id, self.run_prefix, recorded_run_id)
            # A SUPPLY LEFT WAITING ON A PERSON IS OFFERED ITS DECISION HERE
            # (REQ-GHUB-082 criterion 17), before the publish offer - promoting
            # changes what a publish would publish.
            filing_tui.offer_after_run(self.collection_id, recorded_run_id)
            common.offer_to_publish()
        else:
            # The scriptable form keeps its one line: a panel is noise in a
            # pipeline and a blocking keypress would be a hang.
            console.print(f"Recorded {len(results)} results for {recorded_run_id}", style="green")
            common.report_kept_arrival(self.collection_id, self.run_prefix, recorded_run_id)

    def _finish_supply(self, results: list[dict], filed, all_checks: bool = False) -> None:
        """Report a hand-supplied check and what the operator already decided
        (REQ-PIPE-103 criterion 8): the decision was taken before anything
        ran, so there is no second question."""
        from cli import common, filing_tui

        common.finish_kept(results, filed, collection_id=self.collection_id,
                           run_id_prefix=self.run_prefix, table=self.report_table,
                           all_checks=all_checks)
        # A KEPT run that left its supply waiting offers the decision here
        # (REQ-GHUB-082 criterion 17; post-build-review #82).
        if filed.delivery_name:
            filing_tui.offer_after_run(self.collection_id, filed.run_id)


# ---- the registry of command objects ------------------------------------------

#: One command object per collection for the life of the process, by id. A
#: plain dict rather than functools.cache so a test can evict the collections
#: it registered without replacing the real ones other modules hold
#: (post-build-review #228).
COMMANDS: dict[str, CollectionCLI] = {}


def _cached(collection_id: str) -> CollectionCLI:
    found = COMMANDS.get(collection_id)
    if found is not None:
        return found
    from qa_tools import collections

    coll = collections.by_id(collection_id)
    if len(coll.datasets) == 1:
        from cli.one_table import OneTableCLI

        made = OneTableCLI(coll)
    else:
        from cli.many_tables import ManyTablesCLI

        made = ManyTablesCLI(coll)
    return COMMANDS.setdefault(collection_id, made)


def of(value: str) -> CollectionCLI:
    """The collection's command object, by id, short or run prefix - one per
    collection for the life of the process."""
    from qa_tools import collections

    return _cached(collections.resolve(value).id)


def refuse_a_broken_adapter(coll) -> None:
    """Load the collection's adapter, or refuse naming the collection and the
    error - no traceback (criterion 8)."""
    from qa_tools import collections

    try:
        collections.adapter(coll)
    except Exception as exc:  # noqa: BLE001 - any failure to load is refused, by name
        raise click.ClickException(
            f"{coll.id} cannot run: its adapter could not be loaded - {exc}") from None


def make_group(coll) -> click.Group:
    """The `mothman <short>` group for one collection (criterion 1)."""
    from cli import many_tables, one_table

    shape = one_table if len(coll.datasets) == 1 else many_tables
    name = label(coll)

    # ABOVE N_LIST EACH LINE NAMES ITS AGENCY TOO (REQ-TEST-252 criterion 3),
    # so two similarly named collections can be told apart from the list.
    from cli import common

    about = f"{name} ({coll.agency_name})" if common.many_collections() else name

    @click.group(coll.short, help=f"{about} - Tier 1 commands.")
    def group() -> None:
        pass

    # A PROVIDER THAT WILL NOT LOAD offers no trial here rather than taking
    # every command down (criterion 8); generating then says why.
    try:
        provider = _provider(coll)
    except Exception:  # noqa: BLE001
        provider = None
    shape.add_commands(group, coll, with_target_trial=bool(provider and provider.target_trial))
    return group


def qa_hint(coll) -> str:
    """How a collection's `qa` is invoked by flag, for the TUI's hints."""
    return (f"mothman {coll.short} qa [--run-id/--file]" if len(coll.datasets) == 1
            else f"mothman {coll.short} qa [--run-id/--folder]")

