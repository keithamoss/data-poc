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
import inspect
from pathlib import Path

import pytest

from cli import dashboard as dashboard_cli

ROOT = Path(__file__).resolve().parents[1]


class TestThereIsExactlyOnePublishPath:
    """Criterion 10, and criterion 15 for the prompt specifically."""

    def test_the_command_delegates_rather_than_pushing_for_itself(self):
        source = inspect.getsource(dashboard_cli.publish_command.callback)
        assert "publish(" in source
        # The git ARGUMENT, not the word - "push" appears in help text and
        # prose, and a test that matched those would fail for describing
        # itself.
        assert '"push"' not in source

    def test_pipeline_run_publish_calls_the_same_function(self):
        from cli import pipeline

        source = inspect.getsource(pipeline.run_command.callback)
        assert "dashboard_cli.publish()" in source, \
            "pipeline run --publish does not go through the one publish path"
        assert '"push"' not in source

    def test_the_wizards_prompt_calls_the_same_function(self):
        """Criterion 15 in as many words: the prompt reaches the site by
        the same path the command uses, and by no other."""
        from cli import common

        source = inspect.getsource(common.offer_to_publish)
        assert "dashboard_cli.publish()" in source
        assert '"push"' not in source

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

    def test_publish_runs_the_render_check(self):
        source = inspect.getsource(dashboard_cli.publish)
        assert "_check_renders()" in source

    def test_it_runs_the_check_before_it_publishes(self):
        """Order, not presence. A gate after the push is not a gate."""
        source = inspect.getsource(dashboard_cli.publish)
        assert source.index("_check_renders()") < source.index("_publish(")

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

    def test_the_prompt_defaults_to_not_publishing(self):
        """Criterion 14: a prompt they answer, and the answer that changes
        what the public sees is not the default one."""
        from cli import common

        source = inspect.getsource(common.offer_to_publish)
        assert "default=False" in source

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

    def test_the_embed_fills_it_with_the_environment_and_the_commit(self):
        from dashboard import embed_dashboard_data

        body = inspect.getsource(embed_dashboard_data.embed)
        assert "BUILD_PROVENANCE" in body
        assert "environments.current_or_none()" in body
        assert "current_commit_sha()" in body

    def test_absence_of_either_is_tolerated_rather_than_invented(self):
        """An environment is unset on a checkout nobody configured, and a
        commit is unavailable in a container built from a tarball. Both are
        ordinary; claiming a value for either would not be."""
        from dashboard import embed_dashboard_data

        body = inspect.getsource(embed_dashboard_data.embed)
        assert "except Exception:" in body
        assert 'commit = None' in body

    def test_the_page_renders_both_into_the_build_stamp(self):
        text = self.TEMPLATE.read_text()
        stamp = text[text.index("function renderBuildStamp()"):]
        stamp = stamp[:stamp.index("renderBuildStamp();")]
        assert "BUILD_PROVENANCE.environment" in stamp
        assert "BUILD_PROVENANCE.commit" in stamp
        assert ".slice(0, 7)" in stamp, "a reader does not read a forty-character sha"


class TestThePublishedContentCannotMixWithTheSource:
    """Criterion 13."""

    def test_it_publishes_to_a_branch_of_its_own(self):
        assert dashboard_cli.PAGES_BRANCH == "gh-pages"

    def test_it_uses_a_detached_worktree_rather_than_checking_the_branch_out(self):
        """The reason is not tidiness: every other arrangement puts a build
        output somewhere `git add -A` on the source branch can reach, and
        this project has already had a committed dashboard build for that
        reason."""
        source = inspect.getsource(dashboard_cli._publish)
        assert "worktree" in source
        assert "--detach" in source
        assert "--orphan" in source

    def test_it_writes_nojekyll(self):
        """Pages otherwise runs the content through Jekyll, which silently
        drops anything beginning with an underscore - a failure that would
        be very hard to diagnose from the outside."""
        assert ".nojekyll" in inspect.getsource(dashboard_cli._publish)
