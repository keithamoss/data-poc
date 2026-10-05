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
    # THE CENSUS WARNING ON THE SANCTIONED PATH (REQ-PIPE-081 criterion 16,
    # #113): a WARNING, and the build still publishes.
    from qa_tools.common import census

    for line in census.build_warnings():
        console.print(line, style="yellow", markup=False)


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


def _validate_check_lifecycle(require_explanations: bool = False) -> None:
    from qa_tools.common.validate_check_lifecycle import main as validate_main
    if validate_main(require_explanations) != 0:
        raise click.ClickException("check-lifecycle validation failed - see output above.")


@dashboard_group.command("validate-check-lifecycle")
@click.option("--require-explanations", is_flag=True,
              help="Also fail if any check lacks a plain-English description, or "
                   "neither states what a failure indicates nor declares it "
                   "self-evident (REQ-QAC-025). Retired checks included.")
def validate_check_lifecycle_command(require_explanations: bool) -> None:
    """Gate: no check_id's config changed without a matching changelog entry (Thread D)."""
    _validate_check_lifecycle(require_explanations)


def _validate_hierarchy() -> None:
    from qa_tools.common.validate_hierarchy import main as validate_main
    if validate_main() != 0:
        raise click.ClickException("hierarchy validation failed - see output above.")


@dashboard_group.command("validate-hierarchy")
def validate_hierarchy_command() -> None:
    """Gate: every dataset contract agrees with the one hierarchy (REQ-QAC-039)."""
    _validate_hierarchy()


def _validate_requirements(path: str | None = None) -> None:
    from qa_tools.common.validate_requirements import main as validate_main
    if validate_main(path) != 0:
        raise click.ClickException("requirements validation failed - see output above.")


@dashboard_group.command("validate-requirements")
@click.option("--draft", "draft", metavar="PATH", default=None,
              help="Validate a DRAFT file of requirements instead of the real "
                   "register - for checking scoped requirements before they are "
                   "applied. A draft may be a bare list rather than a "
                   "'requirements:' mapping. Cross-reference errors against "
                   "requirements the draft does not itself contain are expected.")
def validate_requirements_command(draft: str | None) -> None:
    """Gate: requirements.yaml stays consistent with the real test files it references."""
    _validate_requirements(draft)


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


#: The branch GitHub Pages serves the published dashboard from
#: (REQ-PIPE-092 criteria 12 and 13). A branch rather than a directory on
#: the source branch, so a build output can never be staged or committed
#: alongside the code that produced it - the two share no working tree at
#: any point.
PAGES_BRANCH = "gh-pages"


def publish(*, dry_run: bool = False, branch: str | None = None) -> None:
    """Build the dashboard, gate it, and publish it. THE one publish path
    (REQ-PIPE-092 criteria 10, 11 and 15).

    EVERY ROUTE TO A PUBLISHED SITE COMES THROUGH HERE - the command
    below, `mothman pipeline run --publish`, and the prompt the QA wizard
    offers. Criterion 10 is that there is exactly one way to get content
    published, and criterion 15 that the prompt reaches the site by the
    same path the command uses. Three entry points to one function is
    that; three functions that each push would not be, however carefully
    they matched today.

    THE GATE IS NOT OPTIONAL AND CANNOT BE SKIPPED (criteria 4 and 5).
    It runs a real browser against the built artifact, here, where the
    build happened - it used to run in the GitHub Actions job that built
    it, and moved with the build rather than being dropped. Nothing is
    pushed unless it passes, which is why the render check sits between
    the build and the push rather than beside them.

    WHAT HAPPENS IF THE DATABASE IS UNREACHABLE (criterion 8): the build
    fails, this raises, and NOTHING is pushed - so the previously
    published dashboard stays exactly as it is. That is the behaviour
    worth having rather than a placeholder page: a stale dashboard whose
    build stamp says when it was built is honest, and an empty one that
    replaced it would not be.
    """
    branch = branch or PAGES_BRANCH
    from pathlib import Path as _Path

    from dashboard.snapshot_dashboard import prepare_deploy_site

    console.print("Rebuilding check results from the recorded QA history...", style="dim")
    _rebuild_results()
    console.print("Reshaping into dashboard JSON...", style="dim")
    _build_data()
    console.print("Embedding real data into the dashboard...", style="dim")
    _embed()

    console.print("Gate - dashboard structural + real-browser render check...", style="dim")
    _check_renders()

    # ONE SNAPSHOT PER PUBLISH (criterion 6), and the "per publish" is the
    # part worth stating. Snapshots used to be opt-in via
    # SNAPSHOT_DASHBOARD=1, because CI published on every relevant push and
    # archiving each one would have buried the archive. Publishing is a
    # deliberate act now, so archiving what was published is exactly the
    # criterion: a self-contained copy of what people were shown, openable
    # years later with nothing but a browser. That is also why
    # `dashboard/snapshots/*.html.gz` stays committed while everything else
    # moved into the database - a row in a database it cannot reach is not
    # openable with a browser.
    #
    # AFTER THE GATE, not before, so nothing is archived that was not good
    # enough to publish. And never on a dry run: a committed artifact is
    # not what "tell me what would happen" means.
    if not dry_run:
        from dashboard.snapshot_dashboard import take_snapshot
        console.print(f"Snapshot archived -> {take_snapshot()}", style="dim")

    site = _Path("_site")
    prepare_deploy_site(site_dir=site)
    _publish(site, branch=branch, dry_run=dry_run)


@dashboard_group.command("publish")
@click.option("--dry-run", is_flag=True,
              help="Build and gate, and say what would be pushed without pushing it.")
@click.option("--branch", default=None,
              help=f"The branch GitHub Pages serves. Default: {PAGES_BRANCH}.")
def publish_command(dry_run: bool, branch: str | None) -> None:
    """Build the dashboard from the recorded QA history, gate it, and publish it."""
    publish(dry_run=dry_run, branch=branch)


def _publish(site_dir, branch: str, dry_run: bool) -> None:
    """Push a built, gated site to the branch GitHub Pages serves.

    WHY A BRANCH AT ALL (REQ-PIPE-092 criterion 12). The dashboard used to
    reach Pages through a GitHub Actions job that built it and called
    actions/deploy-pages. That job cannot build it any more: the QA results
    are in a PostgreSQL database and a runner has no route to it, and
    giving one a database credential is exactly the wrong thing to build.
    So the build happens where the data is and the ARTIFACT travels, by the
    one mechanism GitHub Pages will serve without running anything: a
    branch it reads directly.

    WHY A WORKTREE rather than checking the branch out here (criterion 13).
    The published content and the source must never share a working tree -
    not for tidiness, but because every other arrangement puts a build
    output somewhere `git add -A` on the source branch can reach it, and
    this project has already had that exact problem with a committed
    dashboard build. A detached worktree cannot: the source branch's index
    is untouched throughout, so there is no moment when the two are
    confusable.

    ORPHAN HISTORY, deliberately. The published branch shares no ancestry
    with the source branch and each publish is one commit replacing the
    last, because its history answers a different question - "what was
    published, and when" - and interleaving it with the code's history
    would make both harder to read. GitHub Pages serves the tip and cares
    about nothing else.
    """
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path

    site_dir = Path(site_dir)
    index = site_dir / "index.html"
    if not index.is_file():
        raise click.ClickException(
            f"{index} is missing - a publish must follow a real build, and nothing was built here.")

    sha = _short_sha()
    message = f"Publish the dashboard{f' built from {sha}' if sha else ''}"

    if dry_run:
        files = sum(1 for p in site_dir.rglob("*") if p.is_file())
        console.print(f"--dry-run: would push {files} file(s) from {site_dir} to "
                       f"{branch!r} as {message!r}.", style="yellow")
        return

    worktree = Path(tempfile.mkdtemp(prefix="mothman-publish-"))
    try:
        # A worktree with no branch and no history, populated from the
        # built site alone - so nothing from the source tree can ride
        # along even by accident.
        _git("worktree", "add", "--detach", str(worktree))
        _git("checkout", "--orphan", branch, cwd=worktree)
        _git("rm", "-rf", "--quiet", ".", cwd=worktree, allow_failure=True)
        for child in site_dir.iterdir():
            dst = worktree / child.name
            shutil.copytree(child, dst) if child.is_dir() else shutil.copy2(child, dst)
        # .nojekyll, because Pages otherwise runs the content through
        # Jekyll, which silently drops any file or directory beginning with
        # an underscore. Nothing in the site starts with one today; a
        # published page that vanished for that reason would be very hard
        # to diagnose from the outside.
        (worktree / ".nojekyll").write_text("")
        _git("add", "-A", cwd=worktree)
        if not subprocess.run(["git", "diff", "--cached", "--quiet"],
                               cwd=worktree).returncode:
            console.print("Nothing changed since the last publish - nothing pushed.", style="dim")
            return
        _git("commit", "--quiet", "-m", message, cwd=worktree)
        _git("push", "--force", "origin", f"HEAD:refs/heads/{branch}", cwd=worktree)
        console.print(f"Published -> {branch} ({message})", style="green")
    finally:
        shutil.rmtree(worktree, ignore_errors=True)
        _git("worktree", "prune", allow_failure=True)


def _git(*args: str, cwd=None, allow_failure: bool = False) -> str:
    import subprocess

    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if result.returncode and not allow_failure:
        raise click.ClickException(
            f"git {' '.join(args)} failed: {(result.stderr or result.stdout).strip()}")
    return result.stdout.strip()


def _short_sha() -> str | None:
    from qa_tools.common.github_links import current_commit_sha

    try:
        return current_commit_sha()[:7]
    except Exception:
        return None
