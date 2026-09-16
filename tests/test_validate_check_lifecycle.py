"""Tests for qa_tools/common/validate_check_lifecycle.py - Phase 3's CI
gate step for Thread D (plans/publishing-and-history.md): diffing check
definitions between the current working tree and the immediately-
previous git commit. Uses a real temp git repo (not a mocked
subprocess) since the git-history-reading mechanism (`git show
HEAD~1:<path>`, including "the path didn't exist at that ref yet") is
exactly the part worth testing for real, not the already-covered
parsing logic in qa_tools/common/check_lifecycle.py itself."""
from __future__ import annotations

import subprocess
import textwrap

from qa_tools.common import validate_check_lifecycle as vcl


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _init_repo(tmp_path):
    repo = tmp_path
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    return repo


def _dbt_schema(check_id: str, extra_config: str = "") -> str:
    return textwrap.dedent(f"""\
        models:
          - name: m
            columns:
              - name: c
                tests:
                  - not_null:
                      meta:
                        check_id: {check_id}
                        changelog: []
                      config:
                        warn_if: ">90"
                        {extra_config}
        """)


def test_old_file_content_returns_none_before_the_file_existed(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    monkeypatch.setattr(vcl, "ROOT", repo)
    (repo / "empty.txt").write_text("placeholder\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "initial commit, no schema.yml yet")

    assert vcl._old_file_content("schema.yml", "HEAD") is None


def test_old_file_content_returns_the_content_at_that_ref(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    monkeypatch.setattr(vcl, "ROOT", repo)
    (repo / "schema.yml").write_text("version: 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add schema.yml")
    (repo / "schema.yml").write_text("version: 2\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "bump version")

    assert vcl._old_file_content("schema.yml", "HEAD~1") == "version: 1\n"
    assert vcl._old_file_content("schema.yml", "HEAD") == "version: 2\n"


def test_collect_checks_reads_old_and_new_from_real_git_history(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    monkeypatch.setattr(vcl, "ROOT", repo)
    monkeypatch.setattr(vcl, "_YAML_SOURCES", [("schema.yml", vcl.cl.parse_dbt_check_metadata)])
    monkeypatch.setattr(vcl, "_EVIDENTLY_SOURCES", [])

    (repo / "schema.yml").write_text(_dbt_schema("a.b.c.not_null"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "introduce the check")

    old_checks = vcl.collect_checks("HEAD")
    new_checks = vcl.collect_checks(None)

    assert [c.check_id for c in old_checks] == ["a.b.c.not_null"]
    assert [c.check_id for c in new_checks] == ["a.b.c.not_null"]


def test_main_fails_on_an_undocumented_config_change(tmp_path, monkeypatch, capsys):
    repo = _init_repo(tmp_path)
    monkeypatch.setattr(vcl, "ROOT", repo)
    monkeypatch.setattr(vcl, "_YAML_SOURCES", [("schema.yml", vcl.cl.parse_dbt_check_metadata)])
    monkeypatch.setattr(vcl, "_EVIDENTLY_SOURCES", [])

    (repo / "schema.yml").write_text(_dbt_schema("a.b.c.not_null"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "introduce the check")

    # change a real config value (error_if) with no new changelog entry,
    # committed - the exact scenario the CI gate exists to catch
    (repo / "schema.yml").write_text(_dbt_schema("a.b.c.not_null", extra_config="error_if: \">95\""))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "tighten the threshold, forgot the changelog")

    exit_code = vcl.main()

    assert exit_code == 1
    assert "changed without a new changelog entry" in capsys.readouterr().err


def test_main_passes_when_nothing_changed(tmp_path, monkeypatch, capsys):
    repo = _init_repo(tmp_path)
    monkeypatch.setattr(vcl, "ROOT", repo)
    monkeypatch.setattr(vcl, "_YAML_SOURCES", [("schema.yml", vcl.cl.parse_dbt_check_metadata)])
    monkeypatch.setattr(vcl, "_EVIDENTLY_SOURCES", [])

    (repo / "schema.yml").write_text(_dbt_schema("a.b.c.not_null"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "introduce the check")

    assert vcl.main() == 0
    assert "zero errors" in capsys.readouterr().out


def test_evidently_dict_from_source_evals_the_module_source():
    source = textwrap.dedent("""\
        CHECK_LIFECYCLE = {
            "a.b.c.drift_psi": {"introduced_date": "2026-01-01", "changelog": []},
        }
        """)

    result = vcl._evidently_dict_from_source(source, "fake_evidently_check_lifecycle.py")

    assert result == {"a.b.c.drift_psi": {"introduced_date": "2026-01-01", "changelog": []}}
