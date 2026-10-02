"""The docs-* agents' read and write guards, and the before/after
snapshot (REQ-DOCS-124).

Written before the module, as the architect review asked: every bypass
here is a real way an agent's path could escape its scope, and each
one fails against a guard that only compares strings.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from qa_tools.common import docs_guard as g


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A small tree shaped like the real one, so the guards can be
    driven against real paths rather than strings."""
    for rel in [
        "requirements.yaml",
        ".env",
        ".env.local",
        "data/deliveries/x.csv",
        "reports/results_bdm.json",
        ".claude/skills/explain/evals/01-jargon/page.md",
        ".claude/skills/docs-house-style/SKILL.md",
        ".claude/settings.json",
        "docs/explainers/glossary.yaml",
        "docs/explainers/glossary.md",
        "docs/explainers/concept-map.yaml",
        "docs/explainers/2-calendar/sources.yaml",
        "docs/explainers/2-calendar/periods-and-slots.md",
        "docs/explainers/_work/2026-09-29-periods/brief.md",
        "contract/data-asset.yaml",
    ]:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
    return tmp_path


def _call(tool: str, **tool_input) -> str:
    return json.dumps({"tool_name": tool, "tool_input": tool_input})


class TestReadGuard:
    @pytest.mark.parametrize("rel", [
        "requirements.yaml",
        "contract/data-asset.yaml",
        "docs/explainers/2-calendar/periods-and-slots.md",
        ".claude/skills/docs-house-style/SKILL.md",
    ])
    def test_ordinary_repository_files_are_readable(self, repo, rel):
        assert g.guard_read("docs-writer", _call("Read", file_path=str(repo / rel)), repo).allowed

    @pytest.mark.parametrize("rel", [
        ".env", ".env.local", "data/deliveries/x.csv", "reports/results_bdm.json",
        ".claude/skills/explain/evals/01-jargon/page.md",
    ])
    def test_denied_locations_are_refused(self, repo, rel):
        d = g.guard_read("docs-writer", _call("Read", file_path=str(repo / rel)), repo)
        assert not d.allowed

    def test_a_parent_reference_cannot_climb_into_a_denied_location(self, repo):
        sneaky = repo / "docs" / ".." / "data" / "deliveries" / "x.csv"
        assert not g.guard_read("docs-writer", _call("Read", file_path=str(sneaky)), repo).allowed

    def test_a_symlink_into_a_denied_location_is_refused(self, repo):
        link = repo / "docs" / "innocent.txt"
        os.symlink(repo / ".env", link)
        assert not g.guard_read("docs-writer", _call("Read", file_path=str(link)), repo).allowed

    def test_a_path_outside_the_repository_is_refused(self, repo, tmp_path_factory):
        outside = tmp_path_factory.mktemp("elsewhere") / "secret"
        outside.write_text("x")
        assert not g.guard_read("docs-writer", _call("Read", file_path=str(outside)), repo).allowed

    def test_a_relative_path_is_resolved_against_the_repository(self, repo):
        assert not g.guard_read("docs-writer", _call("Read", file_path=".env"), repo).allowed
        assert g.guard_read("docs-writer", _call("Read", file_path="requirements.yaml"), repo).allowed

    def test_a_search_rooted_above_a_denied_location_is_refused(self, repo):
        """Grep with no path searches the whole repository, which
        contains the denied locations - so it is refused, with a
        message saying to search a narrower directory."""
        d = g.guard_read("docs-writer", _call("Grep", pattern="password"), repo)
        assert not d.allowed and "narrower" in d.reason
        assert not g.guard_read("docs-writer", _call("Glob", pattern="**/*", path=str(repo / ".claude")), repo).allowed

    def test_a_search_inside_an_allowed_directory_is_allowed(self, repo):
        assert g.guard_read("docs-writer", _call("Grep", pattern="slot", path=str(repo / "contract")), repo).allowed
        assert g.guard_read("docs-writer", _call("Glob", pattern="*.yaml", path=str(repo / "docs")), repo).allowed

    @pytest.mark.parametrize("rel,allowed", [
        ("requirements.yaml", True), ("contract/data-asset.yaml", True),
        (".env", False), ("data/deliveries/x.csv", False), (".claude/skills/explain/evals/jargon.expected.yaml", False),
    ])
    def test_the_finding_checker_reads_sources_but_not_secrets_data_or_answers(self, repo, rel, allowed):
        """REQ-DOCS-133 criteria 2, 3 and 18: read-only like the fact-checker."""
        assert g.guard_read("docs-finding-checker", _call("Read", file_path=str(repo / rel)), repo).allowed is allowed

    def test_the_critic_may_read_nothing_at_all(self, repo):
        d = g.guard_read("docs-critic", _call("Read", file_path=str(repo / "requirements.yaml")), repo)
        assert not d.allowed

    @pytest.mark.parametrize("payload", ["", "not json", "{}", json.dumps({"tool_name": "Read"}),
                                         json.dumps({"tool_name": "Read", "tool_input": {}})])
    def test_anything_it_cannot_understand_is_refused(self, repo, payload):
        assert not g.guard_read("docs-writer", payload, repo).allowed

    def test_an_unknown_agent_is_refused(self, repo):
        assert not g.guard_read("somebody-else", _call("Read", file_path=str(repo / "requirements.yaml")), repo).allowed


class TestWriteGuard:
    @pytest.mark.parametrize("rel", [
        "docs/explainers/2-calendar/periods-and-slots.md",
        "docs/explainers/2-calendar/a-new-page.md",
        "docs/explainers/glossary.yaml",
        "docs/explainers/_work/2026-09-29-periods/brief.md",
    ])
    def test_the_writer_may_write_pages_glossary_and_work(self, repo, rel):
        assert g.guard_write("docs-writer", _call("Write", file_path=str(repo / rel)), repo).allowed

    @pytest.mark.parametrize("rel", [
        "docs/explainers/glossary.md",
        "docs/explainers/concept-map.yaml",
        "docs/explainers/2-calendar/sources.yaml",
        ".claude/skills/docs-house-style/SKILL.md",
        ".claude/settings.json",
        ".gitignore",
        "docs/explainers/.gitignore",
        "docs/explainers/2-calendar/.gitignore",
        "docs/explainers/2-calendar/diagram.svg",
        "requirements.yaml",
        "docs/explainers2/page.md",
    ])
    def test_the_writer_may_not_write_anywhere_else(self, repo, rel):
        assert not g.guard_write("docs-writer", _call("Write", file_path=str(repo / rel)), repo).allowed

    def test_the_illustrator_may_write_pages_and_work_but_not_the_glossary(self, repo):
        page = repo / "docs/explainers/2-calendar/periods-and-slots.md"
        work = repo / "docs/explainers/_work/2026-09-29-periods/diagrams.md"
        assert g.guard_write("docs-illustrator", _call("Edit", file_path=str(page)), repo).allowed
        assert g.guard_write("docs-illustrator", _call("Write", file_path=str(work)), repo).allowed
        assert not g.guard_write("docs-illustrator", _call("Edit", file_path=str(repo / "docs/explainers/glossary.yaml")), repo).allowed

    @pytest.mark.parametrize("agent", ["docs-critic", "docs-fact-checker", "docs-finding-checker", "unknown"])
    def test_nobody_else_writes_anything(self, repo, agent):
        page = repo / "docs/explainers/2-calendar/periods-and-slots.md"
        assert not g.guard_write(agent, _call("Write", file_path=str(page)), repo).allowed

    def test_a_parent_reference_cannot_climb_out(self, repo):
        sneaky = repo / "docs/explainers/2-calendar/../../../.claude/settings.json"
        assert not g.guard_write("docs-writer", _call("Write", file_path=str(sneaky)), repo).allowed

    def test_a_symlinked_page_pointing_outside_its_scope_is_refused(self, repo):
        link = repo / "docs/explainers/2-calendar/linked.md"
        os.symlink(repo / "requirements.yaml", link)
        assert not g.guard_write("docs-writer", _call("Edit", file_path=str(link)), repo).allowed

    def test_an_absolute_path_outside_the_repository_is_refused(self, repo):
        home = Path(os.path.expanduser("~")) / ".bashrc"
        assert not g.guard_write("docs-writer", _call("Write", file_path=str(home)), repo).allowed

    def test_multiedit_and_notebookedit_are_guarded_too(self, repo):
        bad = str(repo / "requirements.yaml")
        assert not g.guard_write("docs-writer", _call("MultiEdit", file_path=bad), repo).allowed
        assert not g.guard_write("docs-writer", _call("NotebookEdit", notebook_path=bad), repo).allowed

    @pytest.mark.parametrize("payload", ["", "garbage", json.dumps({"tool_name": "Write", "tool_input": {}})])
    def test_anything_it_cannot_understand_is_refused(self, repo, payload):
        assert not g.guard_write("docs-writer", payload, repo).allowed


class TestSnapshot:
    def test_an_unchanged_tree_reports_nothing(self, repo, tmp_path_factory):
        snap = tmp_path_factory.mktemp("s") / "snap.json"
        g.take_snapshot(repo, snap)
        assert g.verify_changes("docs-writer", repo, snap).out_of_scope == []

    def test_a_write_inside_scope_is_listed_but_allowed(self, repo, tmp_path_factory):
        snap = tmp_path_factory.mktemp("s") / "snap.json"
        g.take_snapshot(repo, snap)
        (repo / "docs/explainers/2-calendar/periods-and-slots.md").write_text("changed, longer")
        (repo / "docs/explainers/glossary.yaml").write_text("changed, longer")
        report = g.verify_changes("docs-writer", repo, snap)
        assert report.out_of_scope == []
        assert "docs/explainers/glossary.yaml" in report.named

    @pytest.mark.parametrize("rel", [
        ".venv/lib/python3.11/site-packages/evil.pth",
        "node_modules/x/index.js",
        "data/new.csv",
        ".claude/settings.json",
    ])
    def test_a_write_anywhere_else_is_caught_including_ignored_paths(self, repo, tmp_path_factory, rel):
        (repo / ".venv/lib/python3.11/site-packages").mkdir(parents=True)
        (repo / "node_modules/x").mkdir(parents=True)
        snap = tmp_path_factory.mktemp("s") / "snap.json"
        g.take_snapshot(repo, snap)
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("new content that differs")
        assert rel in g.verify_changes("docs-writer", repo, snap).out_of_scope

    def test_a_deletion_outside_scope_is_caught(self, repo, tmp_path_factory):
        snap = tmp_path_factory.mktemp("s") / "snap.json"
        g.take_snapshot(repo, snap)
        (repo / "requirements.yaml").unlink()
        assert "requirements.yaml" in g.verify_changes("docs-writer", repo, snap).out_of_scope

    def test_the_critic_changing_anything_is_out_of_scope(self, repo, tmp_path_factory):
        snap = tmp_path_factory.mktemp("s") / "snap.json"
        g.take_snapshot(repo, snap)
        (repo / "docs/explainers/2-calendar/periods-and-slots.md").write_text("critic edited this")
        assert g.verify_changes("docs-critic", repo, snap).out_of_scope

    def test_git_internals_are_not_walked(self, repo, tmp_path_factory):
        (repo / ".git").mkdir()
        snap = tmp_path_factory.mktemp("s") / "snap.json"
        g.take_snapshot(repo, snap)
        (repo / ".git" / "index").write_text("git changes this all the time")
        assert g.verify_changes("docs-writer", repo, snap).out_of_scope == []
