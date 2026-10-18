"""REQ-PIPE-092 - the dashboard is built where the data is, and GitHub
never holds a database credential.

WHAT IS WORTH TESTING HERE, and it is not "does it push". The push is one
git command and a test that mocked it would assert that a mock was called.
What can actually go wrong is quieter:

  - A SECOND publish path appearing (criterion 10). Three entry points
    reach the site today - the command, `pipeline run --publish` and the
    wizard's prompt - and the moment one of them pushes for itself rather
    than calling the one function, they can drift and nobody would notice
    until two builds differed.
  - PUBLISHING WITHOUT THE GATE (criteria 4 and 5). The render check moved
    out of GitHub Actions with the build, and a publish that skipped it
    would put a broken page on a public site.
  - PUBLISHING WHEN NOBODY ASKED (criterion 16). This is the one with an
    audience outside the tool.
  - A CREDENTIAL REACHING GITHUB (criterion 2), which is the thing the
    whole requirement exists to prevent.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from cli import dashboard as dashboard_cli

ROOT = Path(__file__).resolve().parents[1]


class TestThereIsExactlyOnePublishPath:
    """Criterion 10, and criterion 15 for the prompt specifically."""

    @staticmethod
    def _through_the_command(monkeypatch):
        from click.testing import CliRunner

        result = CliRunner().invoke(dashboard_cli.publish_command, [])
        assert result.exit_code == 0, result.output

    @staticmethod
    def _through_pipeline_run(monkeypatch):
        """`pipeline run --publish` with everything before the publish
        stubbed out - the real run regenerates and checks every supply."""
        import contextlib

        from click.testing import CliRunner

        from cli import pipeline
        from dashboard import snapshot_dashboard
        from qa_tools.common import bootstrap, processing_pass

        monkeypatch.setattr(bootstrap, "holds_history", lambda conn: False)
        monkeypatch.setattr(processing_pass, "pass_lock",
                            lambda *a, **k: contextlib.nullcontext())
        monkeypatch.setattr(pipeline, "_run_collection", lambda coll, sequential: None)
        monkeypatch.setattr(bootstrap, "_confirm_corrections", lambda say: None)
        monkeypatch.setattr(bootstrap, "targets_agree", lambda names: [])
        monkeypatch.setattr(dashboard_cli, "_build_data", lambda: None)
        monkeypatch.setattr(dashboard_cli, "_embed", lambda: None)
        monkeypatch.setattr(snapshot_dashboard, "sync_local_snapshots", lambda: [])
        result = CliRunner().invoke(pipeline.run_command, ["--publish"])
        assert result.exit_code == 0, result.output

    @staticmethod
    def _through_the_wizards_prompt(monkeypatch):
        """Criterion 15 in as many words: the prompt reaches the site by
        the same path the command uses, and by no other."""
        from cli import common

        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        monkeypatch.setattr(common, "confirm", lambda *a, **k: True)
        common.offer_to_publish()

    @pytest.mark.parametrize("route", ["_through_the_command", "_through_pipeline_run",
                                       "_through_the_wizards_prompt"])
    def test_every_route_publishes_through_the_one_function(self, route, monkeypatch, tmp_path):
        """Each of the three entry points reaches the site by calling
        dashboard.publish() once - so none of them can push for itself."""
        monkeypatch.chdir(tmp_path)
        calls = []
        monkeypatch.setattr(dashboard_cli, "publish", lambda **kwargs: calls.append(kwargs))

        getattr(self, route)(monkeypatch)

        assert len(calls) == 1, f"{route} reached publish() {len(calls)} times"

    def test_only_one_function_in_the_cli_pushes_anything(self):
        """The structural version of the same claim - so a fourth entry
        point added later cannot quietly bring its own push."""
        pushers = []
        for path in sorted((ROOT / "cli").glob("*.py")):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                body = ast.get_source_segment(path.read_text(), node) or ""
                if '"push"' in body:
                    pushers.append(f"{path.name}::{node.name}")
        assert pushers == ["dashboard.py::_publish"], pushers


class TestTheGateCannotBeSkipped:
    """Criteria 4 and 5: the render check runs where the build runs, and
    only a build that passed it is published."""

    @staticmethod
    def _record_the_steps(monkeypatch, tmp_path, *, gate_fails=False):
        from dashboard import snapshot_dashboard

        monkeypatch.chdir(tmp_path)
        steps = []

        def step(name, fail=False):
            def _run(*a, **k):
                steps.append(name)
                if fail:
                    raise RuntimeError("the render check failed")
            return _run

        for name in ("_rebuild_results", "_build_data", "_embed", "_publish"):
            monkeypatch.setattr(dashboard_cli, name, step(name))
        monkeypatch.setattr(dashboard_cli, "_check_renders", step("_check_renders", gate_fails))
        monkeypatch.setattr(snapshot_dashboard, "take_snapshot", step("take_snapshot"))
        monkeypatch.setattr(snapshot_dashboard, "prepare_deploy_site", step("prepare_deploy_site"))
        return steps

    def test_it_runs_the_check_after_the_build_and_before_it_publishes(self, monkeypatch, tmp_path):
        """Order, not presence. A gate after the push is not a gate."""
        steps = self._record_the_steps(monkeypatch, tmp_path)
        dashboard_cli.publish()
        assert steps == ["_rebuild_results", "_build_data", "_embed", "_check_renders",
                         "take_snapshot", "prepare_deploy_site", "_publish"]

    def test_a_failed_render_check_publishes_nothing(self, monkeypatch, tmp_path):
        steps = self._record_the_steps(monkeypatch, tmp_path, gate_fails=True)
        with pytest.raises(RuntimeError, match="render check"):
            dashboard_cli.publish()
        assert "_check_renders" in steps, "test precondition - the gate must have run"
        assert "_publish" not in steps and "take_snapshot" not in steps

    def test_a_publish_with_nothing_built_refuses(self, tmp_path):
        """Criterion 5 from the other side. _publish() is reachable with a
        site directory that was never built - by a caller getting the order
        wrong - and it must not push an empty tree over a real site."""
        import click

        with pytest.raises(click.ClickException, match="missing"):
            dashboard_cli._publish(tmp_path, branch="gh-pages", dry_run=True)


class TestPublishingIsAlwaysAsked:
    def test_pipeline_run_does_not_publish_by_default(self):
        """Criterion 16. The default matters more than the flag: a
        debugging run, a batch and a scheduled run must not publish a
        dashboard nobody asked for."""
        from cli import pipeline

        import click

        publish_opt = next(p for p in pipeline.run_command.params if p.name == "do_publish")
        assert publish_opt.is_flag
        # ASKED OF CLICK, not of the stored attribute. A flag's `.default`
        # is an UNSET sentinel that click resolves later, and that sentinel
        # is truthy - so asserting on it directly passes for the wrong
        # reason or fails for one. This asks what the callback actually
        # receives.
        with click.Context(pipeline.run_command) as ctx:
            assert publish_opt.get_default(ctx) is False

    def test_the_prompt_defaults_to_not_publishing(self, monkeypatch):
        """Criterion 14: a prompt they answer, and the answer that changes
        what the public sees is not the default one."""
        from cli import common

        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        asked = []
        monkeypatch.setattr(common.questionary, "confirm",
                            lambda message, **kwargs: asked.append(kwargs) or object())
        monkeypatch.setattr(common, "_ask", lambda question: False)

        def _never(**_k):
            raise AssertionError("published although the answer was no")

        monkeypatch.setattr(dashboard_cli, "publish", _never)
        common.offer_to_publish()

        assert len(asked) == 1, "the person was not asked"
        assert asked[0]["default"] is False

    def test_the_prompt_says_nothing_with_no_terminal(self, monkeypatch, capsys):
        """There is nobody to ask, and the safe answer to "shall I change
        what the public sees" asked of nobody is no - silently, since a
        scripted caller has not done anything wrong."""
        from cli import common

        monkeypatch.setattr("sys.stdin.isatty", lambda: False)

        def _never():
            raise AssertionError("published without being asked")

        monkeypatch.setattr(dashboard_cli, "publish", _never)
        common.offer_to_publish()
        assert capsys.readouterr().out == ""


class TestGitHubHoldsNoCredentialAndRunsNoBuild:
    """Criterion 2, and criterion 9 for what CI keeps."""

    def _workflows(self):
        return sorted((ROOT / ".github" / "workflows").glob("*.yml"))

    def test_no_workflow_can_reach_a_database_off_the_runner(self):
        """The rule is REACHABILITY, not a variable name - and it was a
        variable name until 2026-09-28, which is how it broke CI.

        WHAT HAPPENED, because it is the more useful half. This test used
        to assert that no workflow anywhere named MOTHMAN_SUPPLY_DSN, on
        the reasoning that test.yml needs only MOTHMAN_TEST_DSN. That was
        simply untrue: `mothman pipeline bootstrap` connects to the
        WAREHOUSE, so the step test.yml runs to give ~167 tests something
        to drive cannot work without one. The workflow was written to obey
        this test, so every run died on "MOTHMAN_SUPPLY_DSN is not set"
        before a single test ran - red for three pushes while every local
        gate was green.

        So the rule now says what it always meant, and what the sibling
        test below already spelled out: a workflow may stand up its own
        throwaway PostgreSQL and talk to it, and may never reach a
        database that outlives the job. A host is what decides that, so a
        host is what this checks - and it catches a real deployment DSN
        pasted in, which the name check never would have.
        """
        import re

        allowed_hosts = {"localhost", "127.0.0.1"}
        for path in self._workflows():
            text = path.read_text()
            for dsn in re.findall(r"postgresql://[^\s'\"]+", text):
                host = dsn.split("@")[-1].split(":")[0].split("/")[0]
                assert host in allowed_hosts, (
                    f"{path.name} names a database at {host!r}. A workflow may only "
                    f"reach a service container inside its own job - anything else "
                    f"outlives the run and is this deployment's data.")

    def test_no_workflow_reads_a_database_credential_from_a_secret(self):
        """The other half of the same rule, and the one a name check could
        never see. A throwaway container's password is written inline
        BECAUSE it guards nothing; a secrets reference means somebody
        stored a credential to something real."""
        for path in self._workflows():
            text = path.read_text().lower()
            for line in text.splitlines():
                if "secrets." not in line:
                    continue
                assert not any(word in line for word in ("dsn", "postgres", "database")), (
                    f"{path.name} reads a database credential from a secret: "
                    f"{line.strip()}")

    def test_no_workflow_publishes_the_dashboard(self):
        """The line is PUBLISHING, not building, and the distinction is
        worth stating because it is the one somebody would later "tidy"
        wrongly.

        test.yml legitimately builds a dashboard: it stands up its own
        throwaway PostgreSQL service container, bootstraps synthetic data
        into it, and builds so that ~167 tests have something to drive. That
        is a test fixture, and its DSN is a credential to nothing real.
        What no workflow may do is reach THIS DEPLOYMENT'S database or put
        the result in front of the public."""
        for path in self._workflows():
            # EXECUTABLE LINES ONLY. A comment naming the workflow that used
            # to publish is history, and a test that failed on history would
            # force the history to be deleted to make it pass.
            lines = [line for line in path.read_text().splitlines()
                      if line.strip() and not line.strip().startswith("#")]
            body = "\n".join(lines)
            for command in ("dashboard publish", "deploy-pages", "upload-pages-artifact",
                             "configure-pages"):
                assert command not in body, \
                    f"{path.name} still runs {command!r} - publishing left GitHub with the build"

    def test_the_configuration_gates_still_run_in_ci(self):
        """Criterion 9: everything that needs no database stays runnable
        where no data is reachable. Dropping these with the build would
        have been the easy mistake - they were in the same workflow."""
        text = (ROOT / ".github" / "workflows" / "validate-config.yml").read_text()
        for gate in ("validate-hierarchy", "schedule validate", "validate-check-lifecycle",
                      "validate-requirements", "validate-changelog", "plans-index --check"):
            assert gate in text, f"validate-config.yml no longer runs {gate!r}"


class TestTheArtifactSaysWhereItCameFrom:
    """Criteria 7 and 17."""

    TEMPLATE = ROOT / "dashboard" / "qa-reporting-dashboard.template.html"

    def test_the_template_carries_the_placeholder_unset(self):
        assert "const BUILD_PROVENANCE = null;" in self.TEMPLATE.read_text(), \
            "the raw template must claim no environment - it was never built"

    @staticmethod
    def _embedded_provenance(monkeypatch, tmp_path) -> dict:
        """Run the real embed() into tmp and read BUILD_PROVENANCE back
        out of the page it wrote. The two dashboard JSON inputs are stubbed:
        they are build artefacts, and what is under test is the stamp."""
        import json
        import re

        from dashboard import embed_dashboard_data as edd
        from pipeline import corrections

        targets = []
        for collection_id, _real in edd.collection_targets():
            stub = tmp_path / f"{collection_id}.json"
            stub.write_text(json.dumps({"datasets": []}))
            targets.append((collection_id, str(stub)))
        monkeypatch.setattr(edd, "collection_targets", lambda: targets)
        monkeypatch.setattr(corrections, "applied_feed", lambda: [])
        # The sprint graph re-parses requirements.yaml several times over,
        # which is most of embed()'s cost and nothing to do with the stamp.
        monkeypatch.setattr(edd, "dependency_data", lambda: {"sprints": [], "stale": []})
        monkeypatch.setattr(edd, "DASHBOARD_HTML", tmp_path / "out.html")

        edd.embed()

        found = re.search(r"const BUILD_PROVENANCE = (.*?);\n",
                          (tmp_path / "out.html").read_text())
        assert found, "BUILD_PROVENANCE was not embedded at all"
        return json.loads(found.group(1))

    def test_the_embed_fills_it_with_the_environment_and_the_commit(self, monkeypatch, tmp_path):
        from types import SimpleNamespace

        from dashboard import embed_dashboard_data as edd

        sha = "0123456789abcdef0123456789abcdef01234567"
        monkeypatch.setattr(edd, "current_commit_sha", lambda *a, **k: sha)
        monkeypatch.setattr(edd.environments, "current_or_none", lambda: SimpleNamespace(
            id="sandbox", label="A sandbox", publishes=False))

        assert self._embedded_provenance(monkeypatch, tmp_path) == {
            "environment": {"id": "sandbox", "label": "A sandbox", "publishes": False},
            "commit": sha}

    def test_absence_of_either_is_tolerated_rather_than_invented(self, monkeypatch, tmp_path):
        """An environment is unset on a checkout nobody configured, and a
        commit is unavailable in a container built from a tarball. Both are
        ordinary; claiming a value for either would not be."""
        from dashboard import embed_dashboard_data as edd

        # ONLY THE FIRST ASK FAILS, which is the provenance stamp's. The
        # GitHub-links step asks again later and does NOT tolerate a
        # missing commit - so a build with no repository at all still
        # fails there, which is a separate matter from what the stamp
        # claims. If the order ever changed, the stamp would get the sha
        # and this would fail rather than pass quietly.
        asked = []

        def no_repository_the_first_time(*_a, **_k):
            asked.append(1)
            if len(asked) == 1:
                raise FileNotFoundError("git")
            return "f" * 40

        monkeypatch.setattr(edd, "current_commit_sha", no_repository_the_first_time)
        monkeypatch.setattr(edd.environments, "current_or_none", lambda: None)

        assert self._embedded_provenance(monkeypatch, tmp_path) == {
            "environment": None, "commit": None}


class TestThePublishedContentCannotMixWithTheSource:
    """Criterion 13."""

    def test_it_publishes_to_a_branch_of_its_own(self):
        assert dashboard_cli.PAGES_BRANCH == "gh-pages"

    def test_it_publishes_from_a_worktree_the_source_never_shares(self, tmp_path, monkeypatch):
        """A real publish, into a throwaway repository whose `origin` is a
        local bare one. The source branch's HEAD, index and working tree
        are untouched, and the published branch is an orphan holding the
        built site alone.

        The reason is not tidiness: every other arrangement puts a build
        output somewhere `git add -A` on the source branch can reach, and
        this project has already had a committed dashboard build for that
        reason. And `.nojekyll` is there because Pages otherwise runs the
        content through Jekyll, which silently drops anything beginning
        with an underscore."""
        import subprocess

        def git(*args, cwd):
            return subprocess.run(["git", *args], cwd=cwd, check=True,
                                  capture_output=True, text=True).stdout.strip()

        origin, source, site = tmp_path / "origin.git", tmp_path / "source", tmp_path / "site"
        git("init", "--bare", "--quiet", str(origin), cwd=tmp_path)
        source.mkdir()
        git("init", "--quiet", "-b", "main", cwd=source)
        git("config", "user.email", "tests@example.gov.au", cwd=source)
        git("config", "user.name", "tests", cwd=source)
        (source / "code.py").write_text("print('source')\n")
        git("add", "-A", cwd=source)
        git("commit", "--quiet", "-m", "source", cwd=source)
        git("remote", "add", "origin", str(origin), cwd=source)
        site.mkdir()
        (site / "index.html").write_text("<p>built</p>")
        head_before = git("rev-parse", "HEAD", cwd=source)

        monkeypatch.chdir(source)
        monkeypatch.setattr(dashboard_cli, "_short_sha", lambda: "abc1234")
        dashboard_cli._publish(site, branch="gh-pages", dry_run=False)

        assert git("rev-parse", "HEAD", cwd=source) == head_before
        assert git("rev-parse", "--abbrev-ref", "HEAD", cwd=source) == "main"
        assert git("status", "--porcelain", cwd=source) == "", \
            "the publish left something in the source working tree or index"
        published = git("ls-tree", "-r", "--name-only", "gh-pages", cwd=origin).splitlines()
        assert sorted(published) == [".nojekyll", "index.html"]
        assert git("rev-list", "--count", "gh-pages", cwd=origin) == "1", \
            "the published branch shares history with the source"
        assert len(git("worktree", "list", cwd=source).splitlines()) == 1, \
            "the publish worktree was left registered"


class TestTheWorkflowCarriesEveryVariableThePipelineNeeds:
    """Three CI-only failures in one night, each the same shape.

    `mothman pipeline bootstrap` in test.yml died three times in a row on a
    variable the runner did not have - MOTHMAN_SUPPLY_DSN, then a git
    identity, then MOTHMAN_ENVIRONMENT. Every one was green locally,
    because a developer's shell and this repo's gitignored `.env` have all
    of them; every one cost a push and a five-minute run to discover.

    SO THIS ASSERTS THE CLASS RATHER THAN THE THREE INSTANCES. What it
    checks is that every variable the pipeline refuses to run without is
    named in the workflow that runs it - which is a question answerable
    locally, and the reason the next one will fail here instead of on the
    runner.

    IT READS THE REFUSALS FROM THE CODE, not from a list kept beside it: a
    hand-maintained list is the thing that goes stale, and going stale
    here means the gate stops covering the variable somebody just added.
    """

    WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"

    def _required(self) -> set[str]:
        """Every environment variable something in the pipeline refuses to
        run without, by the constant each module names it with."""
        from qa_tools.common import environments, supply_db

        return {supply_db.SUPPLY_DSN_ENV, environments.ENVIRONMENT_ENV}

    def test_the_test_workflow_names_each_one(self):
        text = self.WORKFLOW.read_text()
        missing = sorted(name for name in self._required() if name not in text)
        assert not missing, (
            f"test.yml runs the real pipeline and does not set {', '.join(missing)}. "
            f"Every one of these has no default on purpose - the pipeline refuses "
            f"rather than guessing - so a runner without it fails before any test "
            f"runs, and passes locally where a shell or .env has it.")

    def test_it_also_names_the_test_dsn_it_creates_databases_with(self):
        """Separate from the list above because it is required by the SUITE
        rather than by the pipeline: conftest raises a UsageError without
        it rather than skipping, on the reasoning that a suite silently
        skipping its warehouse tests reports green having checked
        nothing."""
        from tests.conftest import TEST_DSN_ENV

        assert TEST_DSN_ENV in self.WORKFLOW.read_text()

    def test_the_environment_it_claims_to_be_is_one_the_asset_defines(self):
        """A value nobody defined would fail at run time with a list of the
        real ones - which is the right error and a slow way to find it."""
        import re

        from qa_tools.common import environments

        text = self.WORKFLOW.read_text()
        found = re.search(r"MOTHMAN_ENVIRONMENT:\s*(\S+)", text)
        assert found, "test.yml does not set MOTHMAN_ENVIRONMENT"
        assert found.group(1) in {e.id for e in environments.all_environments()}

    def test_the_environment_it_claims_publishes_nothing(self):
        """A runner must never be an environment whose build is the
        published one - it has no route to a real database, and
        REQ-PIPE-092 moved publishing out of Actions entirely."""
        import re

        from qa_tools.common import environments

        claimed = re.search(r"MOTHMAN_ENVIRONMENT:\s*(\S+)",
                             self.WORKFLOW.read_text()).group(1)
        by_id = {e.id: e for e in environments.all_environments()}
        assert by_id[claimed].publishes is False


class TestNeitherHalfOfCIQuietlyStopsCovering:
    """The split CI depends on, asserted here rather than trusted
    (plans/tooling.md #27).

    CI runs `-m "not needs_deployment"` in one job and `-m
    needs_deployment` in another, and the marker is what decides. Two
    ways that goes wrong, and only one of them is loud: a test in the
    WRONG half either fails outright (fine, somebody fixes it) or
    SKIPS - which is the failure `.github/workflows/test.yml`'s own
    bootstrap comment records having hit before, ten tests quietly
    skipping in CI while passing locally.

    So this checks the marker covers what it has to, mechanically. The
    fixture half needs no checking - conftest derives it - and the half
    that needs it is the five modules reading `reports/` files, where
    nothing in a signature says so.
    """

    WORKFLOW = ROOT / "tests"

    #: The GENERATED artefacts a test can only read where something has
    #: bootstrapped first. `reports/` was the whole list until
    #: 2026-09-29, when CI found `data/scenario_placements.json` the
    #: expensive way - a test rebuilding SCENARIOS.md from it had been
    #: passing only because the single job bootstrapped before running
    #: anything.
    #:
    #: A LIST OF KNOWN ARTEFACTS, not a general proof, and worth being
    #: honest about: nothing here can tell in general whether a path is
    #: read from the real tree or a redirected one. CI running the fast
    #: half against an empty deployment is the real check; this is the
    #: cheap one that catches the known shapes before a push.
    GENERATED = (r'["\']reports["\']\s*/', r"reports/[\w-]+\.json",
                 r"scenario_placements")

    def _modules_reading_reports(self) -> set[str]:
        """Test modules that name a generated artefact."""
        import re

        found = set()
        for path in sorted((ROOT / "tests").glob("test_*.py")):
            text = path.read_text()
            if any(re.search(pattern, text) for pattern in self.GENERATED):
                found.add(path.name)
        return found

    def test_every_module_reading_reports_carries_the_marker(self):
        # FOUR WAYS TO BE COVERED, and only one is visible as a mark.
        # conftest marks anything requesting `deployment_history`; a
        # module may carry the mark itself or on one class or test; and
        # a module that REDIRECTS the artefact away from the real tree
        # never reads the real one at all, which is a stronger form of
        # covered than any mark.
        #
        # THE LAST ONE WAS ADDED AFTER THIS GUARD FALSELY ACCUSED
        # test_generate_runs.py, which mentions the placements path
        # precisely BECAUSE it redirects it. A guard that cries wolf is
        # one somebody disables - and the wrong fix here would have been
        # to add a mark it does not need, pushing a fast test into the
        # slow half to quiet a check.
        covered = ("pytestmark = pytest.mark.needs_deployment",
                   "@pytest.mark.needs_deployment",
                   "deployment_history",
                   "generator_isolation",
                   "PLACEMENTS_PATH\",",
                   # A module that builds its own reports/ under a temporary
                   # or copied tree and reads only that one says so.
                   "READS ONLY ITS OWN REPORTS")
        missing = {
            name for name in self._modules_reading_reports()
            if not any(mark in (ROOT / "tests" / name).read_text()
                       for mark in covered)
        }
        assert missing == set(), (
            f"{sorted(missing)} read a built reports/ file but would run in "
            f"CI's fast half, which never builds one - where they would skip "
            f"rather than fail. Add "
            f"`pytestmark = pytest.mark.needs_deployment`.")

    def test_the_marker_is_registered(self):
        """An unregistered marker makes a typo in `-m` select nothing,
        silently - a green job that ran no tests at all."""
        text = (ROOT / "pyproject.toml").read_text()
        assert "needs_deployment:" in text

    def test_both_halves_are_named_in_the_workflow(self):
        text = (ROOT / ".github" / "workflows" / "test.yml").read_text()
        assert '-m "not needs_deployment"' in text
        assert "-m needs_deployment" in text

    def test_the_coverage_gate_still_runs_over_both(self):
        """Splitting the suite splits the measurement, so `fail_under`
        has to be enforced on the combination - not on either half,
        where it would be meaningless."""
        text = (ROOT / ".github" / "workflows" / "test.yml").read_text()
        assert "coverage combine" in text
        assert text.count("--cov-fail-under=0") == 2, (
            "each half must defer the threshold to the combine")
