"""mothman debug - per-tool debug runners, Tier 3 (plans/tooling.md #1
Phase 4's own "Per-tool debug runners" group - Keith's own framing: "if
it wasn't in the CLI, how would a human debug it?"). Runs one real tool
in isolation against a run already on disk, or one of the other
lower-level building blocks (a per-run warehouse, the combined
warehouse, one dataset's changelog feed).

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
from qa_tools.common import asset_time

console = Console()


def _one_table(short: str) -> bool:
    """Whether the collection is the one-table shape, whose arrivals carry
    the csv a run id guards (REQ-TEST-245: by shape, never by name)."""
    from qa_tools import collections

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
    from qa_tools import collections
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
    from qa_tools import collections
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
    from qa_tools import collections
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
    from qa_tools import collections
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


@debug_group.command("build-warehouses")
@common.short_collection_option(required=True, help="{legend}.")
def build_warehouses_command(collection: str) -> None:
    """Build every per-run DuckDB warehouse for one dataset's real synthetic manifest."""
    from qa_tools import collections
    from qa_tools.tools import stage

    stage.build_all(collections.by_short(collection).id)
    console.print("Built.", style="green")


@debug_group.command("changelog")
@click.option("--agency", required=True, help="e.g. registry-services")
@click.option("--dataset", required=True, help="e.g. birth-registrations")
def changelog_command(agency: str, dataset: str) -> None:
    """Print one dataset's real "who QA'd what, when" changelog feed (from committed qa_results/ history)."""
    import json
    from qa_tools.common.changelog import build_changelog
    click.echo(json.dumps(build_changelog(agency, dataset), indent=2))


@debug_group.command("capture-arrival-golden")
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
def capture_arrival_golden_command(yes: bool) -> None:
    """Re-capture tests/fixtures/arrival_semantics_golden.json from the built reports.

    THE PIN, NOT A CONVENIENCE. That fixture is the characterization
    measurement REQ-PIPE-048 was refactored against - every arrival in
    committed history, with its instant and its early/onTime/late
    verdict. Re-capturing it makes a failing test pass by definition,
    so it is only ever legitimate when the committed history itself has
    been rebuilt, and never to quiet a diff. A moved verdict on
    unchanged history is the finding.

    It exists as a real command because it used to be an ad-hoc
    throwaway script, which meant the one operation that can silently
    destroy the pin was also the one with no recorded procedure.
    """
    import json
    from pathlib import Path

    from . import common

    root = Path(__file__).resolve().parent.parent
    golden = root / "tests" / "fixtures" / "arrival_semantics_golden.json"
    from qa_tools import collections

    reports = [c.dashboard_file for c in collections.all_collections()]

    missing = [r for r in reports if not (root / "reports" / r).exists()]
    if missing:
        raise click.ClickException(
            f"{', '.join(missing)} not built - run `mothman dashboard build-data` first.")

    if not common.confirm(
            "Re-capture the arrival golden? Only correct if committed history was legitimately rebuilt.",
            yes=yes, default=False):
        console.print("Not re-captured.", style="yellow")
        return

    captured: dict[str, dict] = {}
    for name in reports:
        doc = json.loads((root / "reports" / name).read_text())
        for ds in doc["datasets"]:
            by_run = ds.get("arrivalByRun") or {}
            captured[ds["id"]] = {
                a["run_id"]: {"arrivalStatus": a["arrivalStatus"],
                              # From arrivalByRun, not from the history
                              # row - the history row carries no instant,
                              # and capturing None here is what made the
                              # "did the instant move" half of the pin
                              # measure nothing at all.
                              "arrivedAt": (by_run.get(a["run_id"]) or {}).get("arrivedAt")}
                for a in ds.get("arrivalHistory") or []}

    golden.write_text(json.dumps(captured, indent=2, sort_keys=True) + "\n")
    n = sum(len(v) for v in captured.values())
    console.print(f"Captured {n} arrivals across {len(captured)} datasets -> {golden}", style="green")


@debug_group.group("equivalence")
def equivalence_group() -> None:
    """Capture a commit and compare two captures (REQ-TEST-239).

    \b
    Surfaces:
      S1 recorded-results  every row of every qa table, normalised
      S4 generated-files   path and sha256 of every generated file
      S5 reports           every results and dashboard JSON, generated_at removed
      S7 help-and-menus    every --help text and the TUI's menu screens
    """


@equivalence_group.command("capture")
@click.option("--ref", required=True, help="The commit (or branch, tag) to capture.")
@click.option("--label", required=True,
              help="Names the baseline file and its scratch database (a-z, 0-9, - and _).")
@click.option("--yes", is_flag=True, help="Replace a baseline with this label if one exists.")
def equivalence_capture_command(ref: str, label: str, yes: bool) -> None:
    """Check REF out into a worktree of its own, bootstrap it from empty into a
    scratch database, build it, and record S1, S4, S5 and S7 as one baseline.
    A full bootstrap: budget about half an hour."""
    from qa_tools.common import equivalence

    try:
        path = equivalence.capture(ref, label, yes=yes, say=console.print)
    except equivalence.Refused as exc:
        raise click.ClickException(str(exc)) from None
    except equivalence.StageFailed as exc:
        raise click.ClickException(
            f"{exc} - the scratch database was dropped and no baseline was written") from None
    console.print(f"Baseline written: {path}", style="green")


@equivalence_group.command("compare")
@click.argument("a")
@click.argument("b")
@click.option("--surfaces", "surfaces", multiple=True, metavar="SURFACE",
              help="Compare only these, by code or name (S1 recorded-results, S4 "
                   "generated-files, S5 reports, S7 help-and-menus). Repeatable; all "
                   "four when absent.")
@click.option("--renamed-by", default=None, metavar="REQUIREMENT",
              help="Map the report files this requirement renamed, old name to new, before "
                   "comparing S5. Only REQ-PIPE-248 has any.")
def equivalence_compare_command(a: str, b: str, surfaces: tuple[str, ...],
                                renamed_by: str | None) -> None:
    """Compare baselines A and B (labels or paths) surface by surface. Exits
    non-zero if any compared surface differs."""
    from qa_tools.common import equivalence

    try:
        codes = equivalence.surface_codes(surfaces)
        ba, bb = equivalence.load(a), equivalence.load(b)
        diffs = equivalence.compare(ba, bb, codes, renamed_by=renamed_by)
    except equivalence.Refused as exc:
        raise click.ClickException(str(exc)) from None
    between = equivalence.commits_between(ba["commit"], bb["commit"])
    console.print(f"A: {ba['label']} at {ba['commit'][:10]}   B: {bb['label']} at "
                  f"{bb['commit'][:10]}   commits between: "
                  f"{between if between is not None else 'unknown'}")
    ta, tb = ba.get("bootstrap_seconds"), bb.get("bootstrap_seconds")
    if ta is not None and tb is not None:
        console.print(f"bootstrap: A {ta:.0f}s, B {tb:.0f}s, difference {tb - ta:+.0f}s "
                      f"(A {ba.get('timings') or {}}, B {bb.get('timings') or {}})")
    names = {code: name for code, name, _ in equivalence.SURFACES}
    differing = []
    for code in codes:
        lines = diffs[code]
        console.print(f"{code} {names[code]}: " + ("same" if not lines else
                                                     f"DIFFERS ({len(lines)} line(s))"),
                      style="green" if not lines else "red", highlight=False)
        for line in lines:
            console.print(line, highlight=False, markup=False)
        if lines:
            differing.append(code)
    if differing:
        raise SystemExit(1)
