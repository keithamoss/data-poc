"""mothman dashboard - the dashboard rebuild chain, Tier 2 (plans/
tooling.md #1 Phase 4's "Dashboard rebuild chain" group). Every command
here calls the real, unmodified function each retired bare-script
invocation already called - this is a reorg of entry points, not a
rewrite of what they do. CI-safe: none of this ever opens data/raw/,
data/cp_raw/, or any DuckDB warehouse - every number comes from
recorded QA history (qa_tools.tools.results_history) or from files
these commands themselves just wrote."""
from __future__ import annotations

import rich_click as click
from rich.console import Console

console = Console()


@click.group("dashboard")
def dashboard_group() -> None:
    """Dashboard rebuild chain - Tier 2 (CI/automation)."""


def _out_dir_option(command):
    """`--out-dir DIR`: write this build to DIR - `DIR/reports/`, the page at
    `DIR/qa-reporting-dashboard.html` with its data/, fonts/ and vendor/ beside
    it - reading the reports an earlier step wrote there, never touching the
    real tree's (REQ-TEST-281). Every step of one build takes the same DIR."""
    def _use(ctx, param, value):
        if value:
            from qa_tools.common import build_output
            build_output.use(value)
        return value

    return click.option("--out-dir", type=click.Path(file_okay=False), default=None,
                        expose_value=False, callback=_use, is_eager=True,
                        help="Write this build to DIR instead of the real reports/ and dashboard/ "
                             "(reports under DIR/reports, the page at DIR/qa-reporting-dashboard.html).")(command)


def _rebuild_results() -> None:
    from asset_model import collections
    from qa_tools.tools import results_history

    for coll in collections.all_collections():
        results_history.build_results_from_history(coll.id)


@dashboard_group.command("rebuild-results")
@_out_dir_option
def rebuild_results_command() -> None:
    """Rebuild every collection's results file under reports/ from its QA history recorded in the database."""
    _rebuild_results()


def _build_data() -> None:
    from pipeline import build_dashboard_data
    from asset_model import collections

    # EVERY REGISTERED COLLECTION, through the one builder (REQ-DASH-244
    # criteria 1 and 9).
    for coll in collections.all_collections():
        try:
            written = build_dashboard_data.write(coll.id)
        except build_dashboard_data.MissingResultsFile as exc:
            raise click.ClickException(str(exc)) from None  # post-build-review #233
        console.print(f"Wrote {written}", style="green")
    # THE CENSUS WARNING ON THE SANCTIONED PATH (REQ-PIPE-081 criterion 16,
    # #113): a WARNING, and the build still publishes.
    from qa_tools.common import census

    for line in census.build_warnings():
        console.print(line, style="yellow", markup=False)


@dashboard_group.command("build-data")
@_out_dir_option
def build_data_command() -> None:
    """Reshape every collection's results file into the dashboard's own JSON shape."""
    _build_data()


def _embed() -> None:
    from dashboard.embed_dashboard_data import embed, output_paths
    embed()
    # EVERY BUILD SAYS HOW BIG IT IS (REQ-PIPE-255 criterion 26): embed,
    # rebuild, pipeline run and the publish all end here.
    report_built_sizes(output_paths()[0])


@dashboard_group.command("embed")
@_out_dir_option
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


@dashboard_group.command("validate-reads-columns")
def validate_reads_columns_command() -> None:
    """Gate: every SQL-bodied check names the columns its SQL reads, in the
    contract's own table names (REQ-GEN-183 criterion 9)."""
    from qa_tools.common.validate_reads_columns import main as validate_main
    if validate_main() != 0:
        raise click.ClickException("reads_columns validation failed - see output above.")


@dashboard_group.command("validate-soda")
def validate_soda_command() -> None:
    """Gate: every active SodaCL check parses and can be evaluated without
    Soda Cloud (the road-testing sweep's #7, 2026-10-06)."""
    from qa_tools.common.validate_soda import main as validate_main
    if validate_main() != 0:
        raise click.ClickException("Soda check validation failed - see output above.")


@dashboard_group.command("validate-imports")
def validate_imports_command() -> None:
    """Gate: no import, or load by path, across a forbidden edge between the
    shared reading code, the real pipeline, the generator, scenarios, the
    bootstrap and the CLI, outside imports-allowlist.yaml (REQ-TEST-384)."""
    from qa_tools.common.validate_imports import main as validate_main
    if validate_main() != 0:
        raise click.ClickException("imports validation failed - see output above.")


@dashboard_group.command("validate-dbt-packages")
def validate_dbt_packages_command() -> None:
    """Gate: every asset's dbt project declares the same dbt packages and
    versions - packages.yml and package-lock.yml, compared parsed (REQ-TEST-388)."""
    from qa_tools.common.validate_dbt_packages import main as validate_main
    if validate_main() != 0:
        raise click.ClickException("dbt packages validation failed - see output above.")


@dashboard_group.command("validate-layout")
def validate_layout_command() -> None:
    """Gate: only environments.yaml and asset folders at the top of assets/,
    and no collection's file in the shared code tree (REQ-PIPE-342 criterion
    10, REQ-PIPE-364 criterion 5). Repository-wide: it reads no asset."""
    from qa_tools.common.validate_layout import main as validate_main
    if validate_main() != 0:
        raise click.ClickException("layout validation failed - see output above.")


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


def _validate_feedback() -> None:
    from qa_tools.common.validate_feedback import main as validate_main
    if validate_main() != 0:
        raise click.ClickException("feedback validation failed - see output above.")


@dashboard_group.command("validate-feedback")
def validate_feedback_command() -> None:
    """Gate: every road-testing entry carries a well-formed feedback card (REQ-DOCS-219)."""
    _validate_feedback()


@dashboard_group.command("validate-provisional")
@click.option("--write-baseline", is_flag=True,
              help="Write provisional-baseline.yaml from the register. Once only - "
                   "refused when the file exists.")
@click.option("--prune", is_flag=True,
              help="Take answered or reworded entries off the baseline. Never adds one.")
def validate_provisional_command(write_baseline: bool, prune: bool) -> None:
    """Gate: warn on every unanswered PROVISIONAL choice in a built requirement (REQ-TEST-374)."""
    from qa_tools.common.validate_provisional import main as validate_main
    argv = (["--write-baseline"] if write_baseline else []) + (["--prune"] if prune else [])
    raise SystemExit(validate_main(argv))


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
@_out_dir_option
def check_renders_command() -> None:
    """Gate: the built dashboard HTML is structurally valid and renders with zero real browser console errors."""
    _check_renders()


@dashboard_group.command("rebuild")
@_out_dir_option
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
    from dashboard.check_dashboard_renders import built_page
    console.print(f"Rebuilt -> {built_page()}", style="green")


def publish_refusal(*, dry_run: bool = False) -> str | None:
    """Why this publish may not run, said before anything is built, written or
    uploaded - or None where it may. Every route to a publish asks it: the
    command, `mothman pipeline run --publish`, the post-QA prompt and any
    automated job, which can only publish through publish() (REQ-PIPE-372
    criterion 3).

    IN THIS ORDER: the stated environment publishes (REQ-PIPE-255 criterion
    20); the selected asset declares where it is hosted (criterion 8; it
    replaced REQ-PIPE-372's publish_to_gh_pages, criterion 5); and, unless
    this is a dry run, which uploads nothing, the credentials are set
    (criterion 7) and the pinned wrangler is installed (criteria 4 and 5)."""
    from asset_model import assets
    from dashboard import hosting
    from qa_tools.common import environments

    env = environments.current()
    if not env.publishes:
        publishers = [e.id for e in environments.all_environments() if e.publishes]
        return (f"The {env.id} environment does not publish - the dashboard is published only "
                f"from {', '.join(publishers) or 'no environment'} (assets/environments.yaml). "
                f"`mothman dashboard rebuild` builds it for viewing here.")
    if hosting.hosting() is None:
        return (f"The {assets.selected().name} asset declares no hosting: its data-asset.yaml has no "
                f"`hosting:` block naming its Cloudflare Pages project, production branch, address "
                f"and sign-in domain (docs/dashboard-hosting.md). `mothman dashboard rebuild` builds "
                f"it for viewing here.")
    if dry_run:
        return None
    missing = hosting.credentials_refusal()
    if missing:
        return missing
    try:
        hosting.find_wrangler()
    except hosting.PublishRefused as refused:
        return str(refused)
    return None


def publish(*, dry_run: bool = False) -> None:
    """Build the dashboard, gate it, and upload it to the selected asset's
    Cloudflare Pages project. THE one publish path (REQ-PIPE-092 criteria 10,
    11 and 15; REQ-PIPE-255 criterion 2 - the upload replaced the push to the
    gh-pages branch, criterion 31).

    THE GATE IS NOT OPTIONAL AND CANNOT BE SKIPPED (REQ-PIPE-092 criteria 4
    and 5; REQ-PIPE-255 criterion 3): a real browser runs against the built
    page here, where it was built, and nothing is uploaded that did not pass.

    NOTHING CHANGED, NOTHING PUBLISHED (criteria 22 to 25, 27): the build's
    fingerprint is compared with the newest archived snapshot's BEFORE
    anything is archived, so an unchanged build leaves no snapshot and makes
    no deployment - and no flag overrides that.

    WHAT HAPPENS IF THE DATABASE IS UNREACHABLE (REQ-PIPE-092 criterion 8):
    the build fails, this raises, and nothing is uploaded - the previous
    deployment keeps serving.
    """
    from datetime import datetime
    from pathlib import Path as _Path

    from dashboard import access_check, hosting
    from dashboard import snapshot_dashboard as snapshots
    from dashboard.embed_dashboard_data import output_paths

    # REFUSED BEFORE ANYTHING IS BUILT, WRITTEN OR UPLOADED, and non-zero
    # (REQ-PIPE-372 criterion 2): a script or a loop over assets must not
    # read a refusal as a publish.
    refused = publish_refusal(dry_run=dry_run)
    if refused:
        raise click.ClickException(refused)
    where = hosting.hosting()

    console.print("Rebuilding check results from the recorded QA history...", style="dim")
    _rebuild_results()
    console.print("Reshaping into dashboard JSON...", style="dim")
    _build_data()
    console.print("Embedding real data into the dashboard...", style="dim")
    _embed()
    console.print("Gate - dashboard structural + real-browser render check...", style="dim")
    _check_renders()

    # THE PAGE THIS BUILD WROTE, wherever it wrote it (`--out-dir`, a test's
    # scratch directory), never a path bound when this module was imported.
    page = _Path(output_paths()[0])
    newest = snapshots.newest_snapshot()
    unchanged = newest is not None and \
        snapshots.snapshot_fingerprint(newest[0]) == snapshots.page_fingerprint(page)
    if unchanged:
        taken = datetime.fromisoformat(newest[1]["taken_at"])
        console.print(f"The dashboard is unchanged since the snapshot published "
                      f"{taken:%Y-%m-%d %H:%M} UTC ({newest[0].name}) - nothing archived or uploaded.",
                      style="green")
        return

    from qa_tools.common import build_output

    site = _Path(build_output.out_dir() or ".") / "_site"
    sha = _short_sha()
    if dry_run:
        snapshots.prepare_deploy_site(site_dir=site, html_path=page)
        size = hosting.measure(site)
        console.print(f"--dry-run: the content has changed since "
                      f"{'the newest archived snapshot' if newest else 'nothing - no snapshot is archived yet'}. "
                      f"Would upload {size.files} file(s), {hosting.mib(size.total_bytes)} in all; the "
                      f"largest is {size.largest[0]} at {hosting.mib(size.largest[1])}.", style="yellow")
        console.print("--dry-run: would run wrangler " + " ".join(hosting.deploy_args(site, where, sha))
                      + f" with {hosting.TOKEN_ENV}=<elided> and {hosting.ACCOUNT_ENV}=<elided> in its "
                        f"environment; nothing invoked, nothing archived.", style="yellow")
        _size_warnings(size)
        return

    # BEHIND THE SIGN-IN BEFORE ANYTHING IS UPLOADED (REQ-PIPE-257 criteria 9
    # and 10) - and before a snapshot is archived, so a refusal leaves none.
    before = access_check.check(f"https://{where.production_host}/", where.access_domain)
    if not before.protected:
        raise click.ClickException(
            f"Not uploaded: {before.words()} A publish uploads only to a site whose address "
            f"redirects to the sign-in at {where.access_domain} (docs/dashboard-hosting.md).")
    _refuse_oversized_page(page)
    # THE PINNED WRANGLER, asked before anything is archived (criterion 4).
    try:
        hosting.wrangler()
    except hosting.PublishRefused as refused:
        raise click.ClickException(str(refused)) from None

    console.print(f"Snapshot archived -> {snapshots.take_snapshot(html_path=page)}", style="dim")
    snapshots.prepare_deploy_site(site_dir=site, html_path=page)
    size = hosting.measure(site)
    if size.over_limit:
        raise click.ClickException(_too_big(size.over_limit))
    _size_warnings(size)
    try:
        done = hosting.upload(site, where, sha)
    except hosting.PublishRefused as refused:
        raise click.ClickException(str(refused)) from None
    except hosting.UploadFailed as failed:
        raise click.ClickException(f"The upload failed, and was not retried:\n{failed}") from None
    console.print(f"Published -> {done.url} (production: {done.production_url})", style="green")

    after = access_check.check(done.url, where.access_domain)
    if not after.protected:
        raise click.ClickException(
            f"{done.url} is reachable without sign-in: {after.words()} Fix its Access application "
            f"before anyone shares the address (docs/dashboard-hosting.md).")


def publish_after_a_run() -> None:
    """publish(), reached after a QA run whose results are already recorded -
    `mothman pipeline run --publish` and the post-QA prompt (REQ-PIPE-255
    criterion 29): a failure keeps the results and the local dashboard, says
    so, names the retry and exits non-zero."""
    try:
        publish()
    except (click.ClickException, Exception) as failed:
        why = failed.format_message() if isinstance(failed, click.ClickException) else \
            f"{type(failed).__name__}: {failed}"
        raise click.ClickException(
            f"The run's results are recorded and the dashboard is built here, but the publish "
            f"failed, so the published site is unchanged: {why} `mothman dashboard publish` "
            f"retries the publish alone.") from None


def _too_big(files) -> str:
    from dashboard import hosting

    return "Not uploaded - Cloudflare Pages serves no file over 25 MiB: " + "; ".join(
        f"{name} is {hosting.mib(n)}" for name, n in files) + "."


def _size_warnings(size) -> None:
    from dashboard import hosting

    for name, n in size.over_warning:
        console.print(f"warning: {name} is {hosting.mib(n)}, near Cloudflare Pages' 25 MiB "
                      f"limit per file.", style="yellow")


def _refuse_oversized_page(page) -> None:
    """Criterion 13 on the built page and its data files, before anything is
    archived."""
    from dashboard import hosting

    over = [(name, n) for name, n in built_sizes(page) if n > hosting.LIMIT_BYTES]
    if over:
        raise click.ClickException(_too_big(over))


def built_sizes(html_path) -> list[tuple[str, int]]:
    """The built page and every data file and part it references, with their
    sizes (REQ-PIPE-255 criterion 26)."""
    from pathlib import Path as _Path

    from dashboard import data_files

    html_path = _Path(html_path)
    page = html_path.read_bytes().decode("utf-8")
    found = data_files.read_page(page, html_path.parent)
    out = [(html_path.name, html_path.stat().st_size)]
    out += [(f"{data_files.DATA_DIR}/{e['name']}", len(found.contents.get(e["name"], b"")))
            for e in (found.manifest or {}).get("files", [])]
    return out


def report_built_sizes(html_path) -> None:
    """Printed at the end of every build (REQ-PIPE-255 criterion 26), with a
    warning for any file of 20 MiB or more, so the per-file ceiling is watched
    while developing rather than first met at a publish."""
    from dashboard import hosting

    sizes = built_sizes(html_path)
    console.print("Built sizes: " + ", ".join(f"{name} {hosting.mib(n)}" for name, n in sizes),
                  style="dim")
    for name, n in sizes:
        if n >= hosting.WARN_BYTES:
            console.print(f"warning: {name} is {hosting.mib(n)}, near Cloudflare Pages' 25 MiB "
                          f"limit per file.", style="yellow")


@dashboard_group.command("publish")
@click.option("--dry-run", is_flag=True,
              help="Build, gate and prepare the site, and say what would be uploaded, without "
                   "uploading it or archiving a snapshot.")
def publish_command(dry_run: bool) -> None:
    """Build the dashboard from the recorded QA history, gate it, and upload it to this
    asset's Cloudflare Pages project - only when its content has changed."""
    publish(dry_run=dry_run)


@dashboard_group.command("verify-access")
def verify_access_command() -> None:
    """Check that this asset's published dashboard - its production address and its
    most recent deployment's own address - needs a sign-in, uploading nothing
    (REQ-PIPE-257 criterion 12)."""
    from dashboard import access_check, hosting

    where = hosting.hosting()
    if where is None:
        raise click.ClickException(publish_refusal(dry_run=True) or "This asset declares no hosting.")
    missing = hosting.credentials_refusal()
    if missing:
        raise click.ClickException(missing)
    try:
        latest = hosting.latest_deployment_url(where)
    except (hosting.PublishRefused, hosting.UploadFailed) as failed:
        raise click.ClickException(str(failed)) from None
    verdicts = [access_check.check(f"https://{where.production_host}/", where.access_domain)]
    if latest:
        verdicts.append(access_check.check(latest, where.access_domain))
    for v in verdicts:
        console.print(v.words(), style="green" if v.protected else "red")
    if not latest:
        console.print("No deployment was listed to check beyond the production address.", style="yellow")
    if not all(v.protected for v in verdicts):
        raise click.ClickException("Reachable without sign-in, or not checkable - see above.")


def _short_sha() -> str | None:
    from qa_tools.common.github_links import current_commit_sha

    try:
        return current_commit_sha()[:7]
    except Exception:
        return None
