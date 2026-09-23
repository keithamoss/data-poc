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
from qa_tools.common import asset_time

console = Console()


def _bdm_manifest_entry(run_id: str) -> dict:
    from . import bdm
    entry = next((e for e in bdm.load_manifest() if e["run_id"] == run_id), None)
    if entry is None:
        raise click.ClickException(f"No BDM manifest entry for run_id={run_id!r}.")
    return entry


def _bdm_manifest_first_entry() -> dict:
    from . import bdm
    return bdm.load_manifest()[0]


def _cp_manifest_first_run_id() -> str:
    from . import cp
    return cp.load_manifest()[0]["run_id"]


def _print_results(results: list[dict], run_id: str) -> None:
    from . import bdm
    console.print(bdm.report_table(results, run_id))


@click.group("debug")
def debug_group() -> None:
    """Per-tool debug runners - Tier 3 (developer debugging)."""


@debug_group.command("run-dbt")
@click.option("--dataset", type=click.Choice(["bdm", "cp"]), required=True)
@click.option("--run-id", required=True, help="An existing manifest run_id already on disk.")
def run_dbt_command(dataset: str, run_id: str) -> None:
    """Run real dbt-core in isolation against one run already on disk."""
    run_timestamp = asset_time.now().isoformat()
    if dataset == "bdm":
        from qa_tools.bdm.run_dbt_bdm import evaluate_dbt_bdm
        results = evaluate_dbt_bdm(run_id, run_timestamp)
    else:
        from qa_tools.cp.run_dbt_cp import evaluate_dbt_cp
        results = evaluate_dbt_cp(run_id, run_timestamp)
    _print_results(results, run_id)


@debug_group.command("run-soda")
@click.option("--dataset", type=click.Choice(["bdm", "cp"]), required=True)
@click.option("--run-id", required=True, help="An existing manifest run_id already on disk.")
def run_soda_command(dataset: str, run_id: str) -> None:
    """Run real Soda Core in isolation against one run already on disk."""
    run_timestamp = asset_time.now().isoformat()
    if dataset == "bdm":
        from qa_tools.bdm.run_soda_bdm import evaluate_soda_bdm
        results = evaluate_soda_bdm(run_id, run_timestamp)
    else:
        from qa_tools.cp.run_soda_cp import evaluate_soda_cp
        results = evaluate_soda_cp(run_id, run_timestamp)
    _print_results(results, run_id)


@debug_group.command("run-datacontract")
@click.option("--dataset", type=click.Choice(["bdm", "cp"]), required=True)
@click.option("--run-id", required=True, help="An existing manifest run_id already on disk.")
def run_datacontract_command(dataset: str, run_id: str) -> None:
    """Run real datacontract-cli in isolation against one run already on disk."""
    run_timestamp = asset_time.now().isoformat()
    if dataset == "bdm":
        from qa_tools.bdm.run_datacontract_bdm import evaluate_datacontract_bdm
        entry = _bdm_manifest_entry(run_id)
        results = evaluate_datacontract_bdm(run_id, entry["csv_path"], run_timestamp)
    else:
        from qa_tools.cp.run_datacontract_cp import evaluate_datacontract_cp
        results = evaluate_datacontract_cp(run_id, run_timestamp)
    _print_results(results, run_id)


@debug_group.command("run-evidently")
@click.option("--dataset", type=click.Choice(["bdm", "cp"]), required=True)
@click.option("--run-id", required=True, help="An existing manifest run_id already on disk.")
@click.option("--reference-run-id", default=None,
              help="Defaults to the manifest's own first (clean-by-construction) entry.")
def run_evidently_command(dataset: str, run_id: str, reference_run_id: str | None) -> None:
    """Run real Evidently AI in isolation against one run already on disk."""
    run_timestamp = asset_time.now().isoformat()
    if dataset == "bdm":
        from qa_tools.bdm.run_evidently_bdm import evaluate_evidently_bdm
        entry = _bdm_manifest_entry(run_id)
        ref_entry = _bdm_manifest_entry(reference_run_id) if reference_run_id else _bdm_manifest_first_entry()
        results = evaluate_evidently_bdm(run_id, entry["csv_path"], run_timestamp,
                                          reference_run_id=ref_entry["run_id"], reference_csv=ref_entry["csv_path"])
    else:
        from qa_tools.cp.run_evidently_cp import evaluate_evidently_cp
        reference_run_id = reference_run_id or _cp_manifest_first_run_id()
        results = evaluate_evidently_cp(run_id, run_timestamp, reference_run_id=reference_run_id)
    _print_results(results, run_id)


@debug_group.command("build-warehouses")
@click.option("--dataset", type=click.Choice(["bdm", "cp"]), required=True)
def build_warehouses_command(dataset: str) -> None:
    """Build every per-run DuckDB warehouse for one dataset's real synthetic manifest."""
    if dataset == "bdm":
        from qa_tools.bdm.build_per_run_warehouses import build_all
    else:
        from qa_tools.cp.build_cp_warehouses import build_all
    build_all()
    console.print("Built.", style="green")


@debug_group.command("load-warehouse")
def load_warehouse_command() -> None:
    """Load the combined BDM warehouse (data/warehouse.duckdb) from data/raw/."""
    from pipeline.load import load_all
    load_all()


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
    reports = ["birth_registrations_dashboard.json", "child_protection_dashboard.json"]

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
        for ds in (doc["datasets"] if "datasets" in doc else [doc]):
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
