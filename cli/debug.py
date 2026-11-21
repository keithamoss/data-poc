"""mothman debug - per-tool debug runners, Tier 3 (plans/tooling.md #1
Phase 4's own "Per-tool debug runners" group - Keith's own framing: "if
it wasn't in the CLI, how would a human debug it?"). Runs one real tool
in isolation against a run already on disk, plus the worktree snapshot
safety net.

The 4 run-* commands replace 8 retired bare scripts (run_{dbt,soda,
datacontract,evidently}_{bdm,cp}.py) with one real dataset-parameterized
command per tool - real, parameterized debugging against any manifest
run_id, not the 3 hardcoded example run_ids each retired script's own
__main__ block used to replay.

CAUTION - not a side-effect-free dry run: each evaluate_*() function
these commands call ends by writing its result to committed qa_results/
history via write_qa_result() (same as a real orchestrate_{bdm,cp}.py
run - this is pre-existing behaviour of those functions, not specific
to this CLI). Running `debug run-*` against a run_id that already has
committed qa_results/ history for real OVERWRITES that file with this
debug invocation's own fresh timestamp/output. Safe for a run_id with
no committed history yet; for one that already has real history, expect
`git status` to show a modified qa_results/ file afterward - `git
checkout -- <path>` to discard it if the debug run wasn't meant to
become part of the real record."""
from __future__ import annotations

import rich_click as click
from rich.console import Console

from cli import common
from asset_model import asset_time

console = Console()


def _one_table(short: str) -> bool:
    """Whether the collection is the one-table shape, whose arrivals carry
    the csv a run id guards (REQ-TEST-245: by shape, never by name)."""
    from asset_model import collections

    return len(collections.by_short(short).datasets) == 1


def _manifest_entry(short: str, run_id: str) -> dict:
    from .collection_cli import of
    entry = next((e for e in of(short).load_manifest() if e["run_id"] == run_id), None)
    if entry is None:
        raise click.ClickException(
            f"No {short.upper()} manifest entry for run_id={run_id!r}.")
    return entry


def _manifest_first_entry(short: str) -> dict:
    from .collection_cli import of
    return of(short).load_manifest()[0]


def _refuse_an_evaluated_run(run_id: str) -> None:
    """Refuse, before any tool runs, a run the orchestrator already evaluated
    (REQ-PIPE-279 criterion 8): writing into it would replace its recorded
    results under its old run_seq with no attempt of its own. The writer
    refuses the write too; this says so before a tool has spent its time.

    AND A RUN BEING EVALUATED RIGHT NOW (post-build-review #262 F5): another
    process holds its attempt lock, so the store would accept this write as
    if it were that attempt's own."""
    from qa_tools.common import qa_store, supply_db

    with supply_db.connect(read_only=True, label="mothman:debug-guard") as conn:
        if not conn.execute(f"SELECT to_regclass('{qa_store.SCHEMA}.run')").fetchall()[0][0]:
            return
        if qa_store.attempt_running(conn, run_id):
            raise click.ClickException(
                f"run {run_id!r} is being evaluated by another process, which holds its "
                "attempt - a debug runner would write into that attempt's results. Run it "
                "once that attempt has ended.")
        try:
            qa_store.refuse_outside_an_attempt(conn, run_id)
        except qa_store.NoOpenAttempt as exc:
            raise click.ClickException(str(exc)) from exc


def _print_results(results: list[dict], run_id: str, short: str) -> None:
    from .collection_cli import of
    console.print(of(short).report_table(results, run_id))


@click.group("debug")
def debug_group() -> None:
    """Per-tool debug runners - Tier 3 (developer debugging)."""


@debug_group.command("run-dbt")
@common.short_collection_option(required=True, help="{legend}.")
@click.option("--run-id", required=True, help="An existing manifest run_id already on disk.")
def run_dbt_command(collection: str, run_id: str) -> None:
    """Run real dbt-core in isolation against one run already on disk."""
    _refuse_an_evaluated_run(run_id)
    run_timestamp = asset_time.now().isoformat()
    from asset_model import collections
    from qa_tools.tools import run_dbt
    results = run_dbt.evaluate(collections.by_short(collection).id, run_id, run_timestamp)
    _print_results(results, run_id, collection)


@debug_group.command("run-soda")
@common.short_collection_option(required=True, help="{legend}.")
@click.option("--run-id", required=True, help="An existing manifest run_id already on disk.")
def run_soda_command(collection: str, run_id: str) -> None:
    """Run real Soda Core in isolation against one run already on disk."""
    _refuse_an_evaluated_run(run_id)
    run_timestamp = asset_time.now().isoformat()
    from asset_model import collections
    from qa_tools.tools import run_soda
    results = run_soda.evaluate(collections.by_short(collection).id, run_id, run_timestamp)
    _print_results(results, run_id, collection)


@debug_group.command("run-datacontract")
@common.short_collection_option(required=True, help="{legend}.")
@click.option("--run-id", required=True, help="An existing manifest run_id already on disk.")
def run_datacontract_command(collection: str, run_id: str) -> None:
    """Run real datacontract-cli in isolation against one run already on disk."""
    _refuse_an_evaluated_run(run_id)
    run_timestamp = asset_time.now().isoformat()
    from asset_model import collections
    from qa_tools.tools import run_datacontract
    if _one_table(collection):
        # LOOKED UP AS A GUARD, not for a path (REQ-PIPE-102). The
        # tool reads the run's own view schema and never a file, so
        # nothing here needs the arrival's csv_path - but an
        # unrecognised run id must still fail HERE, clearly, rather
        # than several frames down inside a tool that has already
        # written partial results into real history. Dropping this
        # call did exactly that, and left two `does_not_exist/`
        # directories in qa_results/ to prove it.
        _manifest_entry(collection, run_id)
    results = run_datacontract.evaluate(collections.by_short(collection).id, run_id, run_timestamp)
    _print_results(results, run_id, collection)


@debug_group.command("run-evidently")
@common.short_collection_option(required=True, help="{legend}.")
@click.option("--run-id", required=True, help="An existing manifest run_id already on disk.")
@click.option("--reference-run-id", default=None,
              help="Defaults to the manifest's own first (clean-by-construction) entry.")
def run_evidently_command(collection: str, run_id: str, reference_run_id: str | None) -> None:
    """Run real Evidently AI in isolation against one run already on disk."""
    _refuse_an_evaluated_run(run_id)
    run_timestamp = asset_time.now().isoformat()
    from asset_model import collections
    from qa_tools.tools import run_evidently
    if _one_table(collection):
        _manifest_entry(collection, run_id)  # a guard, as above
        ref_entry = (_manifest_entry(collection, reference_run_id) if reference_run_id
                     else _manifest_first_entry(collection))
        reference_run_id = ref_entry["run_id"]
    else:
        reference_run_id = reference_run_id or _manifest_first_entry(collection)["run_id"]
    results = run_evidently.evaluate(collections.by_short(collection).id, run_id, run_timestamp,
                                     reference_run_id=reference_run_id)
    _print_results(results, run_id, collection)


@debug_group.command("snapshot-worktrees")
@click.option("--remote", default="origin", show_default=True,
              help="The remote the snapshots are pushed to.")
@click.option("--dry-run", is_flag=True,
              help="Build each snapshot but push nothing.")
def snapshot_worktrees_command(remote: str, dry_run: bool) -> None:
    """Copy every worktree's uncommitted work to wip/<branch>-snap on the remote.

    A safety net for long agent builds (plans/running-thoughts.md #135): each
    worktree's uncommitted state, untracked files included, is committed in a
    throwaway index and pushed by sha, so a lost container costs minutes, not
    a day. The worktree's own branch, staging and files are never touched. A
    worktree with nothing uncommitted pushes nothing."""
    from pathlib import Path

    from cli import worktree_snapshot

    repo = Path(__file__).resolve().parent.parent
    for snap in worktree_snapshot.snapshot_all(repo, remote, push=not dry_run):
        if snap.sha is None:
            console.print(f"{snap.branch}: no uncommitted changes", highlight=False)
        else:
            where = "built, not pushed" if dry_run else f"pushed to wip/{snap.branch}-snap"
            console.print(f"{snap.branch}: snapshot {snap.sha[:7]} {where}", highlight=False)
