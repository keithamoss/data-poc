"""REQ-PIPE-255 (the upload to Cloudflare Pages), REQ-PIPE-257 (checked to be
behind the sign-in before and after) and REQ-PIPE-354 criterion 5 (each asset
to its own project) - driven through `mothman dashboard publish` against the
stub wrangler and the local HTTP stub in tests/cloudflare_stub.py, with no
Cloudflare account, token or network (REQ-PIPE-255 criterion 30, REQ-PIPE-257
criterion 13).

THE BUILD IS RECORDED RATHER THAN RUN in all but the end-to-end class: what
these tests are about starts after the gate. TestEndToEnd builds the real
page from the deployment database, twice."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

import cloudflare_stub as cf
from cli import dashboard as dashboard_cli
from dashboard import access_check, hosting
from dashboard import snapshot_dashboard as snapshots


def _say(result) -> str:
    return " ".join(result.output.replace("│", " ").split())


@pytest.fixture
def publishing(monkeypatch):
    """The stated environment is the one that publishes (the sandbox,
    criterion 21)."""
    monkeypatch.setenv("MOTHMAN_ENVIRONMENT", "sandbox")


@pytest.fixture
def deployment_publishes(deployment_history, monkeypatch):
    """For a test publishing a build of the DEPLOYMENT'S history: the
    environment stays the one that database is marked for (the sandbox here,
    `ci` on a runner - REQ-PIPE-107 refuses any other), and that environment
    is the publishing one for this test. `publishing` would state the sandbox
    and be refused by CI's database before anything was built."""
    import dataclasses

    from qa_tools.common import environments

    real = environments.current

    def publishing_here(path=None):
        return dataclasses.replace(real(path), publishes=True)
    monkeypatch.setattr(environments, "current", publishing_here)
    return environments.current()


@pytest.fixture
def signed_in(monkeypatch):
    """The selected asset's own hosting, its placeholder sign-in domain
    replaced by the stub's - the one value the real configuration cannot have
    yet (Keith, 2026-11-21: a placeholder until his Access team exists)."""
    real = hosting.hosting

    def with_domain():
        found = real()
        return hosting.Hosting(found.pages_project, found.production_branch, found.address,
                               cf.SIGNIN_DOMAIN)
    monkeypatch.setattr(hosting, "hosting", with_domain)


@pytest.fixture
def built(tmp_path, monkeypatch):
    """A build recorded rather than run: a one-file page in a scratch build
    directory, the archive scratch too, and the steps recorded."""
    from qa_tools.common import build_output

    out = tmp_path / "out"
    # SET THROUGH monkeypatch FIRST, so what it restores is the value from
    # before the test (post-build-review #492): build_output.use() writes
    # os.environ itself, and the delenv this fixture ended with recorded the
    # scratch path as the value to put back - every later test in the process
    # then embedded into this test's dead folder.
    monkeypatch.setenv(build_output.OUT_DIR_ENV, str(out))
    build_output.use(out)
    monkeypatch.setattr(snapshots, "SNAPSHOTS_ROOT", tmp_path / "snapshots")
    monkeypatch.chdir(tmp_path)
    steps = []

    def page():
        steps.append("_embed")
        (out / "qa-reporting-dashboard.html").write_text(
            f"<html>{os.environ.get('PAGE_CONTENT', 'the page')}</html>\nconst SNAPSHOT_MANIFEST = [];\n")
    for name in ("_rebuild_results", "_build_data", "_check_renders"):
        monkeypatch.setattr(dashboard_cli, name, lambda _n=name: steps.append(_n))
    monkeypatch.setattr(dashboard_cli, "_embed", page)
    yield steps


def _publish(*args) -> object:
    return CliRunner().invoke(dashboard_cli.publish_command, list(args))


class TestRefusedBeforeAnythingIsBuilt:
    """REQ-PIPE-255 criteria 5, 7 and 20; REQ-PIPE-372 criterion 2 as the
    hosting keys replaced its setting (criterion 5)."""

    def test_an_environment_that_does_not_publish(self, built, monkeypatch):
        monkeypatch.setenv("MOTHMAN_ENVIRONMENT", "local")
        got = _publish()
        assert got.exit_code != 0
        assert "The local environment does not publish" in _say(got) and "sandbox" in _say(got)
        assert built == []

    def test_each_missing_credential_is_named(self, built, publishing, monkeypatch, tmp_path):
        cf.stub_wrangler(tmp_path, monkeypatch)
        monkeypatch.delenv("CLOUDFLARE_API_TOKEN")
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", " ")
        got = _publish()
        assert got.exit_code != 0
        assert "CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID are not set" in _say(got)
        assert built == []

    def test_wrangler_not_installed_names_the_setup(self, built, publishing, monkeypatch, tmp_path):
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", cf.TOKEN)
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "a")
        monkeypatch.setenv("PATH", str(tmp_path / "nothing-here"))
        monkeypatch.setattr(hosting, "ROOT", tmp_path)
        got = _publish()
        assert got.exit_code != 0
        assert "wrangler is not installed here. Run `npm ci`" in _say(got)
        assert built == []

    def test_an_asset_with_no_hosting(self, built, publishing, monkeypatch):
        monkeypatch.setattr(hosting, "hosting", lambda: None)
        got = _publish()
        assert got.exit_code != 0
        assert "declares no hosting" in _say(got) and "`mothman dashboard rebuild`" in _say(got)
        assert built == []


class TestAnUnpinnedWranglerIsNeverRun:
    """Criterion 4: refused before anything is archived or uploaded."""

    def test_a_different_version_is_refused(self, built, publishing, signed_in, monkeypatch, tmp_path):
        log = cf.stub_wrangler(tmp_path, monkeypatch, version="3.0.0")
        with cf.access_stub() as (base, _):
            cf.route(monkeypatch, base)
            got = _publish()
        assert got.exit_code != 0
        assert f"not the {cf.PINNED} package.json pins" in _say(got)
        assert [c["argv"] for c in cf.calls(log)] == [["--version"]], "only asked its version"
        assert not (tmp_path / "snapshots").exists(), "nothing archived"


class TestTheUpload:
    """Criteria 1, 2, 9, 10, 12, 16, 17 and 25; REQ-PIPE-257 criteria 9 and 11."""

    def test_it_uploads_the_site_to_the_assets_project_as_production(
            self, built, publishing, signed_in, monkeypatch, tmp_path):
        log = cf.stub_wrangler(tmp_path, monkeypatch)
        monkeypatch.setattr(dashboard_cli, "_short_sha", lambda: "abc1234")
        with cf.access_stub() as (base, _):
            cf.route(monkeypatch, base)
            got = _publish()
        assert got.exit_code == 0, got.output
        deploys = [c for c in cf.calls(log) if c["argv"][:2] == ["pages", "deploy"]]
        assert len(deploys) == 1
        argv = deploys[0]["argv"]
        assert argv[argv.index("--project-name") + 1] == "data-poc-quarterly"
        assert argv[argv.index("--branch") + 1] == "main"
        assert argv[argv.index("--commit-hash") + 1] == "abc1234"
        assert Path(argv[2]).name == "_site" and (Path(argv[2]) / "index.html").is_file()
        assert cf.TOKEN not in " ".join(argv), "the token never reaches a command line"
        assert deploys[0]["env"] == {"CLOUDFLARE_API_TOKEN": cf.TOKEN,
                                     "CLOUDFLARE_ACCOUNT_ID": "account-123",
                                     "WRANGLER_SEND_METRICS": "false"}
        said = _say(got)
        assert "https://abc123.data-poc-quarterly.pages.dev" in said
        assert "production: https://data-poc-quarterly.pages.dev" in said
        assert len(list((tmp_path / "snapshots" / "quarterly").glob("*.html.gz"))) == 1

    def test_an_unchanged_second_publish_invokes_wrangler_zero_times(
            self, built, publishing, signed_in, monkeypatch, tmp_path):
        """Criteria 24, 27 and 30: nothing archived, nothing uploaded, exit 0."""
        log = cf.stub_wrangler(tmp_path, monkeypatch)
        with cf.access_stub() as (base, _):
            cf.route(monkeypatch, base)
            assert _publish().exit_code == 0
            before = len(cf.calls(log))
            again = _publish()
        assert again.exit_code == 0, again.output
        assert "The dashboard is unchanged since the snapshot published" in _say(again)
        assert len(cf.calls(log)) == before, "the stub was invoked"
        assert len(list((tmp_path / "snapshots" / "quarterly").glob("*.html.gz"))) == 1

    def test_a_changed_build_publishes_again(self, built, publishing, signed_in, monkeypatch, tmp_path):
        log = cf.stub_wrangler(tmp_path, monkeypatch)
        with cf.access_stub() as (base, _):
            cf.route(monkeypatch, base)
            assert _publish().exit_code == 0
            # A SNAPSHOT IS NAMED TO THE SECOND, so the second is taken in another.
            import time
            time.sleep(1.1)
            monkeypatch.setenv("PAGE_CONTENT", "a changed page")
            assert _publish().exit_code == 0
        assert len([c for c in cf.calls(log) if c["argv"][:2] == ["pages", "deploy"]]) == 2
        assert len(list((tmp_path / "snapshots" / "quarterly").glob("*.html.gz"))) == 2

    @pytest.mark.parametrize("asset", [pytest.param("quarterly", marks=pytest.mark.asset("quarterly")),
                                       pytest.param("daily", marks=pytest.mark.asset("daily"))])
    def test_each_asset_publishes_to_its_own_project(self, asset, built, publishing, signed_in,
                                                     monkeypatch, tmp_path):
        """REQ-PIPE-354 criterion 5."""
        log = cf.stub_wrangler(tmp_path, monkeypatch)
        with cf.access_stub() as (base, _):
            cf.route(monkeypatch, base)
            got = _publish()
        assert got.exit_code == 0, got.output
        argv = next(c["argv"] for c in cf.calls(log) if c["argv"][:2] == ["pages", "deploy"])
        assert argv[argv.index("--project-name") + 1] == f"data-poc-{asset}"

    def test_a_failed_upload_shows_wranglers_error_redacted_and_is_not_retried(
            self, built, publishing, signed_in, monkeypatch, tmp_path):
        """Criteria 11 and 15."""
        log = cf.stub_wrangler(tmp_path, monkeypatch, fail=True)
        with cf.access_stub() as (base, _):
            cf.route(monkeypatch, base)
            got = _publish()
        assert got.exit_code != 0
        said = _say(got)
        assert "The upload failed, and was not retried" in said
        assert cf.TOKEN not in got.output and hosting.REDACTED in said
        assert len([c for c in cf.calls(log) if c["argv"][:2] == ["pages", "deploy"]]) == 1


class TestAFailedPublishLeavesNoSnapshot:
    """REQ-PIPE-255 criterion 25 as amended (Keith, 2026-11-21; post-build-review
    #492): a publish that stops after archiving - a failed upload, a site over the
    limit - removes the snapshot it archived, so a retry publishes again rather
    than reading the build as unchanged and uploading nothing."""

    def _snapshots(self, tmp_path):
        return sorted(p.name for p in (tmp_path / "snapshots" / "quarterly").glob("*.html.gz"))

    def test_a_retry_after_a_failed_upload_uploads(self, built, publishing, signed_in,
                                                   monkeypatch, tmp_path):
        log = cf.stub_wrangler(tmp_path, monkeypatch, fail=True)
        with cf.access_stub() as (base, _):
            cf.route(monkeypatch, base)
            first = _publish()
            assert first.exit_code != 0
            assert self._snapshots(tmp_path) == [], "the failed publish left its snapshot"
            log = cf.stub_wrangler(tmp_path, monkeypatch, fail=False)
            second = _publish()
        assert second.exit_code == 0, _say(second)
        assert "unchanged" not in _say(second)
        # One deploy that failed, then the retry's - the same call log for both.
        assert len([c for c in cf.calls(log) if c["argv"][:2] == ["pages", "deploy"]]) == 2
        assert len(self._snapshots(tmp_path)) == 1

    def test_a_site_over_the_limit_leaves_no_snapshot(self, built, publishing, signed_in,
                                                      monkeypatch, tmp_path):
        log = cf.stub_wrangler(tmp_path, monkeypatch)
        # Past the page's own check (criterion 13, before archiving), so it is
        # the site's check after archiving that refuses - the case that left a
        # snapshot behind.
        monkeypatch.setattr(dashboard_cli, "_refuse_oversized_page", lambda page: None)
        monkeypatch.setattr(hosting, "LIMIT_BYTES", 10)
        with cf.access_stub() as (base, _):
            cf.route(monkeypatch, base)
            got = _publish()
        assert got.exit_code != 0 and "Cloudflare Pages serves no file over 25 MiB" in _say(got)
        assert "Snapshot withdrawn" in _say(got), "precondition: a snapshot was archived first"
        assert self._snapshots(tmp_path) == []
        assert not [c for c in cf.calls(log) if c["argv"][:2] == ["pages", "deploy"]]


class TestHostingIsReadWholeOrRefused:
    def test_an_incomplete_hosting_block_names_what_is_missing(self, monkeypatch):
        """post-build-review #492: never a bare KeyError."""
        from asset_model import config_yaml

        monkeypatch.setattr(config_yaml, "load", lambda path: {"hosting": {"pages_project": "p"}})
        with pytest.raises(hosting.PublishRefused, match="production_branch, address, access_domain"):
            hosting.hosting()

    def test_the_deployment_address_is_this_projects(self, monkeypatch, tmp_path):
        """A pages.dev address of another project in wrangler's words is not
        this upload's deployment."""
        import subprocess

        where = hosting.Hosting("p", "main", "https://p.pages.dev", "x")
        said = ("See https://abc.other.pages.dev\nDeployment complete! https://def.p.pages.dev")
        monkeypatch.setattr(hosting, "wrangler", lambda: "w")
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, said, ""))
        assert hosting.upload(tmp_path, where, None).url == "https://def.p.pages.dev"


class TestSizesThroughThePublish:
    """REQ-PIPE-255 criteria 13 and 14 through publish() itself, not only
    hosting.measure() (post-build-review #492 F4)."""

    def test_a_page_over_the_limit_is_refused_before_anything_is_archived(
            self, built, publishing, signed_in, monkeypatch, tmp_path):
        log = cf.stub_wrangler(tmp_path, monkeypatch)
        monkeypatch.setattr(hosting, "LIMIT_BYTES", 10)
        with cf.access_stub() as (base, _):
            cf.route(monkeypatch, base)
            got = _publish()
        said = _say(got)
        assert got.exit_code != 0 and "Not uploaded - Cloudflare Pages serves no file over 25 MiB" in said
        assert "Snapshot archived" not in said
        assert not list((tmp_path / "snapshots").rglob("*.html.gz"))
        assert not [c for c in cf.calls(log) if c["argv"][:2] == ["pages", "deploy"]]

    def test_a_file_near_the_limit_is_warned_about_and_still_published(
            self, built, publishing, signed_in, monkeypatch, tmp_path):
        log = cf.stub_wrangler(tmp_path, monkeypatch)
        monkeypatch.setattr(hosting, "WARN_BYTES", 10)
        with cf.access_stub() as (base, _):
            cf.route(monkeypatch, base)
            got = _publish()
        assert got.exit_code == 0, _say(got)
        assert "near Cloudflare Pages' 25 MiB limit per file" in _say(got)
        assert len([c for c in cf.calls(log) if c["argv"][:2] == ["pages", "deploy"]]) == 1


class TestTheSignInIsCheckedBeforeAndAfter:
    """REQ-PIPE-257 criteria 9 to 11: nothing uploaded unless the production
    address redirects to the configured sign-in, and a deployment reachable
    without it exits non-zero."""

    @pytest.mark.parametrize("answer,words", [("open", "is reachable without sign-in"),
                                              ("elsewhere", "redirects somewhere other than the sign-in"),
                                              ("missing", "could not be checked")])
    def test_an_unprotected_production_address_uploads_nothing(
            self, answer, words, built, publishing, signed_in, monkeypatch, tmp_path):
        log = cf.stub_wrangler(tmp_path, monkeypatch)
        with cf.access_stub() as (base, _):
            cf.route(monkeypatch, base, production=answer)
            got = _publish()
        assert got.exit_code != 0
        assert "Not uploaded" in _say(got) and words in _say(got)
        assert not [c for c in cf.calls(log) if c["argv"][:2] == ["pages", "deploy"]]
        assert not (tmp_path / "snapshots").exists(), "no snapshot left behind"

    def test_the_placeholder_sign_in_domain_refuses_every_publish(
            self, built, publishing, monkeypatch, tmp_path):
        """Until Keith's Access team exists the configured domain is a
        placeholder, so even a properly protected site is refused - nothing
        can be made public by accident."""
        log = cf.stub_wrangler(tmp_path, monkeypatch)
        with cf.access_stub() as (base, _):
            cf.route(monkeypatch, base)
            got = _publish()
        assert got.exit_code != 0 and "Not uploaded" in _say(got)
        assert "CHANGE-ME.cloudflareaccess.com" in _say(got)
        assert not [c for c in cf.calls(log) if c["argv"][:2] == ["pages", "deploy"]]

    def test_a_deployment_reachable_without_sign_in_exits_non_zero(
            self, built, publishing, signed_in, monkeypatch, tmp_path):
        cf.stub_wrangler(tmp_path, monkeypatch)
        with cf.access_stub() as (base, _):
            cf.route(monkeypatch, base, deployment="open")
            got = _publish()
        assert got.exit_code != 0
        assert "https://abc123.data-poc-quarterly.pages.dev is reachable without sign-in" in _say(got)


class TestTheAccessCheckAgainstAStub:
    """REQ-PIPE-257 criterion 13: each answer, against a local HTTP stub."""

    @pytest.mark.parametrize("path,kind", [("signin", access_check.SIGNIN), ("open", access_check.OPEN),
                                           ("elsewhere", access_check.ELSEWHERE),
                                           ("missing", access_check.UNREACHABLE)])
    def test_each_answer(self, path, kind):
        with cf.access_stub() as (base, _):
            got = access_check.check(f"{base}/{path}", cf.SIGNIN_DOMAIN)
        assert got.kind == kind, got
        assert got.protected is (kind == access_check.SIGNIN)

    def test_a_refused_connection(self):
        with cf.access_stub() as (_, refused):
            got = access_check.check(refused, cf.SIGNIN_DOMAIN, timeout=2)
        assert got.kind == access_check.UNREACHABLE and not got.protected


class TestVerifyAccess:
    """REQ-PIPE-257 criterion 12: the production address and the newest
    deployment, uploading nothing."""

    def test_an_asset_with_no_hosting_is_refused(self, publishing, monkeypatch):
        """post-build-review #492 F5: each failure path, in its own words."""
        monkeypatch.setattr(hosting, "hosting", lambda: None)
        got = CliRunner().invoke(dashboard_cli.verify_access_command, [])
        assert got.exit_code != 0 and "declares no hosting" in " ".join(got.output.split())

    def test_missing_credentials_are_named(self, signed_in, monkeypatch):
        monkeypatch.delenv(hosting.TOKEN_ENV, raising=False)
        monkeypatch.delenv(hosting.ACCOUNT_ENV, raising=False)
        got = CliRunner().invoke(dashboard_cli.verify_access_command, [])
        assert got.exit_code != 0
        assert hosting.TOKEN_ENV in got.output and hosting.ACCOUNT_ENV in got.output

    def test_a_deployment_list_that_fails_is_said(self, signed_in, monkeypatch, tmp_path):
        cf.stub_wrangler(tmp_path, monkeypatch)

        def failing(where):
            raise hosting.UploadFailed("wrangler could not list the deployments.")
        monkeypatch.setattr(hosting, "latest_deployment_url", failing)
        got = CliRunner().invoke(dashboard_cli.verify_access_command, [])
        assert got.exit_code != 0 and "could not list the deployments" in got.output

    def test_no_deployment_listed_checks_the_production_address_alone(
            self, signed_in, monkeypatch, tmp_path):
        cf.stub_wrangler(tmp_path, monkeypatch)
        monkeypatch.setattr(hosting, "latest_deployment_url", lambda where: None)
        with cf.access_stub() as (base, _):
            cf.route(monkeypatch, base)
            got = CliRunner().invoke(dashboard_cli.verify_access_command, [])
        assert got.exit_code == 0, got.output
        assert "No deployment was listed" in got.output

    def test_both_behind_the_sign_in_passes(self, signed_in, monkeypatch, tmp_path):
        log = cf.stub_wrangler(tmp_path, monkeypatch)
        with cf.access_stub() as (base, _):
            cf.route(monkeypatch, base)
            got = CliRunner().invoke(dashboard_cli.verify_access_command, [])
        assert got.exit_code == 0, got.output
        assert not [c for c in cf.calls(log) if c["argv"][:2] == ["pages", "deploy"]]
        assert any(c["argv"][:3] == ["pages", "deployment", "list"] for c in cf.calls(log))

    def test_an_open_deployment_fails(self, signed_in, monkeypatch, tmp_path):
        cf.stub_wrangler(tmp_path, monkeypatch)
        with cf.access_stub() as (base, _):
            cf.route(monkeypatch, base, deployment="open")
            got = CliRunner().invoke(dashboard_cli.verify_access_command, [])
        assert got.exit_code != 0
        assert "is reachable without sign-in" in _say(got)


class TestTheDryRun:
    """Criterion 18: built, gated and prepared; says what it would upload, with
    every credential elided; invokes wrangler not at all and archives nothing."""

    def test_it_reports_and_invokes_nothing(self, built, publishing, monkeypatch, tmp_path):
        log = cf.stub_wrangler(tmp_path, monkeypatch)
        got = _publish("--dry-run")
        assert got.exit_code == 0, got.output
        said = _say(got)
        assert "the content has changed since nothing - no snapshot is archived yet" in said
        assert "Would upload" in said and "the largest is" in said
        assert "--project-name data-poc-quarterly --branch main" in said
        assert "CLOUDFLARE_API_TOKEN=<elided>" in said and cf.TOKEN not in got.output
        assert cf.calls(log) == []
        assert not (tmp_path / "snapshots").exists()


class TestFileSizes:
    """Criteria 13, 14 and 26: the per-file 25 MiB ceiling, warned at 20."""

    def test_over_the_limit_and_near_it(self, tmp_path):
        site = tmp_path / "site"
        site.mkdir()
        for name, size in (("big.js", 26 * hosting.MIB), ("near.js", 21 * hosting.MIB), ("ok.js", 10)):
            with open(site / name, "wb") as f:
                f.truncate(size)
        got = hosting.measure(site)
        assert [n for n, _ in got.over_limit] == ["big.js"]
        assert [n for n, _ in got.over_warning] == ["near.js"]
        assert got.largest[0] == "big.js" and got.files == 3

    def test_every_build_reports_its_sizes_and_warns_near_the_limit(self, tmp_path, monkeypatch, capsys):
        page = tmp_path / "qa-reporting-dashboard.html"
        with open(page, "wb") as f:
            f.write(b"<html></html>")
            f.truncate(21 * hosting.MIB)
        printed = []
        monkeypatch.setattr(dashboard_cli.console, "print", lambda t="", *a, **k: printed.append(str(t)))
        dashboard_cli.report_built_sizes(page)
        assert printed[0].startswith("Built sizes: qa-reporting-dashboard.html 21.00 MiB")
        assert any(p.startswith("warning: qa-reporting-dashboard.html is 21.00 MiB") for p in printed)


class TestAFailedPublishAfterARunKeepsTheRun:
    """Criterion 29."""

    def test_it_says_the_results_are_kept_and_names_the_retry(self, monkeypatch):
        import click

        def fails():
            raise click.ClickException("Not uploaded: the site is open.")
        monkeypatch.setattr(dashboard_cli, "publish", fails)
        with pytest.raises(click.ClickException) as raised:
            dashboard_cli.publish_after_a_run()
        said = raised.value.format_message()
        assert "The run's results are recorded" in said and "the published site is unchanged" in said
        assert "Not uploaded: the site is open." in said
        assert "`mothman dashboard publish` retries the publish alone" in said


@pytest.mark.needs_deployment
class TestEndToEnd:
    """Criteria 23 and 30 on the real build: the same recorded results build to
    the same fingerprint twice, and the second publish of an unchanged real
    build invokes the stub wrangler zero times."""

    def test_the_real_build_twice_fingerprints_the_same(self, deployment_history, tmp_path, monkeypatch):
        from qa_tools.common import build_output

        prints = []
        for n in (1, 2):
            monkeypatch.setenv(build_output.OUT_DIR_ENV, str(tmp_path / f"build{n}"))
            build_output.use(tmp_path / f"build{n}")
            dashboard_cli._rebuild_results()
            dashboard_cli._build_data()
            dashboard_cli._embed()
            prints.append(snapshots.page_fingerprint(tmp_path / f"build{n}" / "qa-reporting-dashboard.html"))
        assert prints[0] == prints[1]

    def test_an_unchanged_real_publish_uploads_nothing(self, deployment_publishes, signed_in,
                                                        monkeypatch, tmp_path):
        from qa_tools.common import build_output

        monkeypatch.setenv(build_output.OUT_DIR_ENV, str(tmp_path / "out"))
        build_output.use(tmp_path / "out")
        monkeypatch.setattr(snapshots, "SNAPSHOTS_ROOT", tmp_path / "snapshots")
        monkeypatch.chdir(tmp_path)
        # The render gate is the browser module's business; here it is the
        # transport after it.
        monkeypatch.setattr(dashboard_cli, "_check_renders", lambda: None)
        log = cf.stub_wrangler(tmp_path, monkeypatch)
        with cf.access_stub() as (base, _):
            cf.route(monkeypatch, base)
            first = _publish()
            assert first.exit_code == 0, first.output
            before = len(cf.calls(log))
            second = _publish()
        assert second.exit_code == 0, second.output
        assert "unchanged since the snapshot published" in _say(second)
        assert len(cf.calls(log)) == before


#: The data asset this module's tests act for, unless a test says otherwise
#: (C11, Keith 2026-11-02: every test module names its asset).
pytestmark = pytest.mark.asset("quarterly")
