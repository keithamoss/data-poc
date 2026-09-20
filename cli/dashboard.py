"""mothman dashboard - the dashboard rebuild chain, Tier 2 (plans/
tooling.md #1 Phase 4's "Dashboard rebuild chain" group). Every command
here calls the real, unmodified function each retired bare-script
invocation already called - this is a reorg of entry points, not a
rewrite of what they do. CI-safe: none of this ever opens data/raw/,
data/cp_raw/, or any DuckDB warehouse - every number comes from
committed qa_results/ history (qa_tools.{bdm,cp}.build_results_from_
history) or from files these commands themselves just wrote."""
from __future__ import annotations

import rich_click as click
from rich.console import Console

console = Console()


@click.group("dashboard")
def dashboard_group() -> None:
    """Dashboard rebuild chain - Tier 2 (CI/automation)."""


def _rebuild_results() -> None:
    from qa_tools.bdm.build_results_from_history import build_results_from_history as build_bdm
    from qa_tools.cp.build_results_from_history import build_results_from_history as build_cp
    build_bdm()
    build_cp()


@dashboard_group.command("rebuild-results")
def rebuild_results_command() -> None:
    """Rebuild reports/results_bdm.json and results_cp.json purely from committed qa_results/ history."""
    _rebuild_results()


def _build_data() -> None:
    import json
    import os

    from pipeline import build_dashboard_data, build_cp_dashboard_data

    for module in (build_dashboard_data, build_cp_dashboard_data):
        data = module.build()
        os.makedirs(os.path.dirname(module.OUT_PATH), exist_ok=True)
        with open(module.OUT_PATH, "w") as f:
            json.dump(data, f, indent=2, default=str)
        console.print(f"Wrote {module.OUT_PATH}", style="green")


@dashboard_group.command("build-data")
def build_data_command() -> None:
    """Reshape results_bdm.json/results_cp.json into the dashboard's own JSON shape."""
    _build_data()


def _embed() -> None:
    from dashboard.embed_dashboard_data import embed
    embed()


@dashboard_group.command("embed")
def embed_command() -> None:
    """Embed real data (dashboard JSON, contract config, changelog/plans/requirements) into the built dashboard HTML."""
    _embed()


def _validate_check_lifecycle(require_failure_indicates: bool = False) -> None:
    from qa_tools.common.validate_check_lifecycle import main as validate_main
    if validate_main(require_failure_indicates) != 0:
        raise click.ClickException("check-lifecycle validation failed - see output above.")


@dashboard_group.command("validate-check-lifecycle")
@click.option("--require-failure-indicates", is_flag=True,
              help="Also fail if an active check has no failure_indicates "
                   "(REQ-QAC-024). Off until every active check is authored.")
def validate_check_lifecycle_command(require_failure_indicates: bool) -> None:
    """Gate: no check_id's config changed without a matching changelog entry (Thread D)."""
    _validate_check_lifecycle(require_failure_indicates)


def _validate_requirements() -> None:
    from qa_tools.common.validate_requirements import main as validate_main
    if validate_main() != 0:
        raise click.ClickException("requirements validation failed - see output above.")


@dashboard_group.command("validate-requirements")
def validate_requirements_command() -> None:
    """Gate: requirements.yaml stays consistent with the real test files it references."""
    _validate_requirements()


def _validate_changelog() -> None:
    from qa_tools.common.validate_changelog import main as validate_main
    if validate_main() != 0:
        raise click.ClickException("changelog validation failed - see output above.")


@dashboard_group.command("validate-changelog")
def validate_changelog_command() -> None:
    """Gate: CHANGELOG.yaml's schema and component tags stay valid."""
    _validate_changelog()


INDEX_PATH = "plans/INDEX.md"


def _plans_index(check: bool = False) -> None:
    """Regenerates plans/INDEX.md, or (with --check) fails if the committed
    copy has gone stale. Same shape as this group's other gates - a
    generated artifact that IS committed needs something that notices when
    it stops matching its source, or it quietly becomes a lie."""
    from pathlib import Path
    from dashboard.plans_index import build_index

    generated = build_index("plans")
    path = Path(INDEX_PATH)
    current = path.read_text() if path.exists() else None
    if check:
        if current != generated:
            raise click.ClickException(
                f"{INDEX_PATH} is out of date with plans/*.md - "
                "run `mothman dashboard plans-index` and commit the result.")
        console.print(f"{INDEX_PATH} is current.", style="green")
        return
    path.write_text(generated)
    console.print(f"Wrote {INDEX_PATH} ({len(generated.splitlines())} lines).", style="green")


@dashboard_group.command("plans-index")
@click.option("--check", is_flag=True, help="Fail if the committed index is stale; don't rewrite it.")
def plans_index_command(check: bool) -> None:
    """Regenerate plans/INDEX.md, the one-line-per-entry table of contents."""
    _plans_index(check=check)


def _check_renders() -> None:
    from dashboard.check_dashboard_renders import main as check_main
    if check_main() != 0:
        raise click.ClickException("dashboard render check failed - see output above.")


@dashboard_group.command("check-renders")
def check_renders_command() -> None:
    """Gate: the built dashboard HTML is structurally valid and renders with zero real browser console errors."""
    _check_renders()


@dashboard_group.command("snapshot")
@click.option("--prepare-site", "site_dir", default=None, type=click.Path(),
              help="CI's own entry point: decompress every committed dashboard/snapshots/*.html.gz into "
                   "<site_dir>/snapshots/ for the real GitHub Pages deploy artifact.")
def snapshot_command(site_dir: str | None) -> None:
    """Sync local snapshot copies for offline viewing (default), take a new one if SNAPSHOT_DASHBOARD=1 is
    set, or (--prepare-site) decompress every committed snapshot into a deploy site directory."""
    from pathlib import Path
    from dashboard.snapshot_dashboard import prepare_deploy_site, sync_local_snapshots, take_snapshot
    import os

    if site_dir is not None:
        prepare_deploy_site(site_dir=Path(site_dir))
        console.print(f"Site prepared -> {site_dir}", style="green")
        return

    synced = sync_local_snapshots()
    if synced:
        console.print(f"Synced {len(synced)} local snapshot copy/copies for offline viewing.", style="dim")

    if os.environ.get("SNAPSHOT_DASHBOARD") != "1":
        console.print("SNAPSHOT_DASHBOARD not set to 1 - skipping the dashboard snapshot "
                       "(pass SNAPSHOT_DASHBOARD=1 to take one for this run).", style="dim")
        return
    out_path = take_snapshot()
    console.print(f"Dashboard snapshot written -> {out_path}", style="green")


@dashboard_group.command("rebuild")
def rebuild_command() -> None:
    """Human-facing convenience: rebuild-results -> build-data -> embed -> validate-check-lifecycle ->
    validate-requirements -> validate-changelog -> check-renders, in one go. CI calls the individual steps above instead, for
    clear per-step pass/fail in the Actions log - this is for a local "just make my dashboard current"."""
    console.print("Rebuilding check results from committed qa_results/ history...", style="dim")
    _rebuild_results()
    console.print("Reshaping into dashboard JSON...", style="dim")
    _build_data()
    console.print("Embedding real data into the dashboard...", style="dim")
    _embed()
    console.print("Gate - check-lifecycle validation...", style="dim")
    _validate_check_lifecycle()
    console.print("Gate - requirements validation...", style="dim")
    _validate_requirements()
    _validate_changelog()
    console.print("Gate - dashboard structural + real-browser render check...", style="dim")
    _check_renders()
    console.print("Rebuilt -> dashboard/qa-reporting-dashboard.html", style="green")
