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


# Fixture check_ids are real-shaped (REQ-QAC-023). They used to read
# "a.b.c.not_null", which is shorter but does not match the grammar every
# one of the repo's 258 real check_ids satisfies - and once the grammar
# became a CI gate, a fixture that could never exist in the real repo
# started failing it. Made realistic rather than exempted: a gate that
# the tests exercising it are excused from is not really a gate.
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
                        category: completeness
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

    (repo / "schema.yml").write_text(_dbt_schema("data-asset-1.agency.dataset.tbl.col.not_null_dbt"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "introduce the check")

    old_checks = vcl.collect_checks("HEAD")
    new_checks = vcl.collect_checks(None)

    assert [c.check_id for c in old_checks] == ["data-asset-1.agency.dataset.tbl.col.not_null_dbt"]
    assert [c.check_id for c in new_checks] == ["data-asset-1.agency.dataset.tbl.col.not_null_dbt"]


def test_collect_checks_treats_a_missing_source_at_the_working_tree_as_no_checks(tmp_path, monkeypatch):
    """A source path missing entirely at `ref=None` (the working tree)
    reads as "no checks from it", not an error - each tool's own
    `-retired` sibling file is genuinely optional until a real project's
    first check ever gets retired (see collect_checks()'s own docstring)."""
    repo = _init_repo(tmp_path)
    monkeypatch.setattr(vcl, "ROOT", repo)
    monkeypatch.setattr(vcl, "_YAML_SOURCES", [
        ("schema.yml", vcl.cl.parse_dbt_check_metadata),
        ("schema-retired.yml", vcl.cl.parse_dbt_check_metadata),  # deliberately never created
    ])
    monkeypatch.setattr(vcl, "_EVIDENTLY_SOURCES", [
        "evidently_check_lifecycle_retired.py",  # deliberately never created
    ])

    (repo / "schema.yml").write_text(_dbt_schema("data-asset-1.agency.dataset.tbl.col.not_null_dbt"))

    checks = vcl.collect_checks(None)

    assert [c.check_id for c in checks] == ["data-asset-1.agency.dataset.tbl.col.not_null_dbt"]


def test_main_fails_on_an_undocumented_config_change(tmp_path, monkeypatch, capsys):
    repo = _init_repo(tmp_path)
    monkeypatch.setattr(vcl, "ROOT", repo)
    monkeypatch.setattr(vcl, "_YAML_SOURCES", [("schema.yml", vcl.cl.parse_dbt_check_metadata)])
    monkeypatch.setattr(vcl, "_EVIDENTLY_SOURCES", [])

    (repo / "schema.yml").write_text(_dbt_schema("data-asset-1.agency.dataset.tbl.col.not_null_dbt"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "introduce the check")

    # change a real config value (error_if) with no new changelog entry,
    # committed - the exact scenario the CI gate exists to catch
    (repo / "schema.yml").write_text(_dbt_schema("data-asset-1.agency.dataset.tbl.col.not_null_dbt", extra_config="error_if: \">95\""))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "tighten the threshold, forgot the changelog")

    exit_code = vcl.main()

    assert exit_code == 1
    assert "changed without a new changelog entry" in capsys.readouterr().err


def test_main_fails_when_a_check_id_is_deleted_outright(tmp_path, monkeypatch, capsys):
    """Keith's call, 2026-09-16: a check_id, once introduced, must never
    be deleted or renamed, even once retired - only ever moved to its
    own tool's -retired sibling file (see check_lifecycle.py's
    find_disappeared_check_ids()). This is the gate actually catching a
    genuine deletion, real end to end through main() and real git
    history, not just the unit-level function in isolation."""
    repo = _init_repo(tmp_path)
    monkeypatch.setattr(vcl, "ROOT", repo)
    monkeypatch.setattr(vcl, "_YAML_SOURCES", [
        ("schema.yml", vcl.cl.parse_dbt_check_metadata),
        ("schema-retired.yml", vcl.cl.parse_dbt_check_metadata),
    ])
    monkeypatch.setattr(vcl, "_EVIDENTLY_SOURCES", [])

    (repo / "schema.yml").write_text(_dbt_schema("data-asset-1.agency.dataset.tbl.col.not_null_dbt"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "introduce the check")

    # deleted outright, not moved anywhere - the exact mistake the rule exists to catch
    (repo / "schema.yml").write_text("models: []\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "oops, deleted the whole check")

    exit_code = vcl.main()

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "disappeared" in stderr
    assert "data-asset-1.agency.dataset.tbl.col.not_null_dbt" in stderr


def test_main_passes_when_a_check_is_properly_retired(tmp_path, monkeypatch, capsys):
    """The legitimate counterpart to the deletion test above: moving a
    check's metadata into its tool's own -retired sibling file (with
    retired_as_of/retired_reason added) is real retirement, not a
    disappearance - main() must pass clean."""
    repo = _init_repo(tmp_path)
    monkeypatch.setattr(vcl, "ROOT", repo)
    monkeypatch.setattr(vcl, "_YAML_SOURCES", [
        ("schema.yml", vcl.cl.parse_dbt_check_metadata),
        ("schema-retired.yml", vcl.cl.parse_dbt_check_metadata),
    ])
    monkeypatch.setattr(vcl, "_EVIDENTLY_SOURCES", [])

    (repo / "schema.yml").write_text(_dbt_schema("data-asset-1.agency.dataset.tbl.col.not_null_dbt"))
    (repo / "schema-retired.yml").write_text("models: []\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "introduce the check")

    # moved from the active file to the retired one, with retirement fields set
    (repo / "schema.yml").write_text("models: []\n")
    retired_schema = textwrap.dedent("""\
        models:
          - name: m
            columns:
              - name: c
                tests:
                  - not_null:
                      meta:
                        check_id: data-asset-1.agency.dataset.tbl.col.not_null_dbt
                        category: completeness
                        changelog: []
                        retired_as_of: "2026-09-16"
                        retired_reason: "superseded by a stricter check"
                      config:
                        warn_if: ">90"
        """)
    (repo / "schema-retired.yml").write_text(retired_schema)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "retire the check properly")

    exit_code = vcl.main()

    assert exit_code == 0
    assert "zero errors" in capsys.readouterr().out


def test_main_passes_when_nothing_changed(tmp_path, monkeypatch, capsys):
    repo = _init_repo(tmp_path)
    monkeypatch.setattr(vcl, "ROOT", repo)
    monkeypatch.setattr(vcl, "_YAML_SOURCES", [("schema.yml", vcl.cl.parse_dbt_check_metadata)])
    monkeypatch.setattr(vcl, "_EVIDENTLY_SOURCES", [])

    (repo / "schema.yml").write_text(_dbt_schema("data-asset-1.agency.dataset.tbl.col.not_null_dbt"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "introduce the check")

    assert vcl.main() == 0
    assert "zero errors" in capsys.readouterr().out


def test_evidently_dict_from_source_evals_the_module_source():
    source = textwrap.dedent("""\
        CHECK_LIFECYCLE = {
            "data-asset-1.agency.dataset.tbl.col.drift_psi_evidently": {"introduced_date": "2026-01-01", "changelog": []},
        }
        """)

    result = vcl._evidently_dict_from_source(source, "fake_evidently_check_lifecycle.py")

    assert result == {"data-asset-1.agency.dataset.tbl.col.drift_psi_evidently": {"introduced_date": "2026-01-01", "changelog": []}}


# ---------------------------------------------------------------------
# REQ-QAC-024: the failure_indicates gate.
#
# Built before the authoring pass that makes it satisfiable, so it ships
# OFF - a count rather than a gate. That is the part worth testing
# carefully: a gate nobody can turn on yet is easy to write wrong and
# discover months later, when turning it on is urgent.
# ---------------------------------------------------------------------

DEFAULT_DESC = "This value must never be empty."


def _dbt_schema_with_prose(check_id: str, failure_indicates: str | None,
                           description: str | None = DEFAULT_DESC) -> str:
    fi = "" if failure_indicates is None else f"\n                        failure_indicates: {failure_indicates}"
    desc = "" if description is None else f"\n                        description: {description}"
    return textwrap.dedent(f"""\
        models:
          - name: m
            columns:
              - name: c
                tests:
                  - not_null:
                      meta:
                        check_id: {check_id}
                        category: completeness
                        changelog: []{desc}{fi}
                      config:
                        warn_if: ">90"
        """)


def _one_check(tmp_path, monkeypatch, failure_indicates, description=DEFAULT_DESC):
    """A repo holding exactly one check with the given prose."""
    repo = _init_repo(tmp_path)
    monkeypatch.setattr(vcl, "ROOT", repo)
    monkeypatch.setattr(vcl, "_YAML_SOURCES", [("schema.yml", vcl.cl.parse_dbt_check_metadata)])
    monkeypatch.setattr(vcl, "_EVIDENTLY_SOURCES", [])
    (repo / "schema.yml").write_text(
        _dbt_schema_with_prose("data-asset-1.ag.ds.m.c.not_null_dbt",
                               failure_indicates, description))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "one")
    return vcl.collect_checks(None)


def test_an_active_check_with_no_failure_indicates_is_an_error(tmp_path, monkeypatch):
    errors = vcl._explanation_errors(_one_check(tmp_path, monkeypatch, None))
    assert len(errors) == 1
    # The message has to be actionable on its own: whoever trips this is
    # looking at a check definition, not at this requirement.
    assert "no failure_indicates" in errors[0]
    assert "self-evident" in errors[0]
    assert "docs/check-authoring-rules.md" in errors[0]


def test_the_self_evident_sentinel_satisfies_the_gate(tmp_path, monkeypatch):
    # The sentinel's whole purpose: an explicit decision that reads as
    # authored, not as a field nobody filled in.
    assert vcl._explanation_errors(_one_check(tmp_path, monkeypatch, "self-evident")) == []


def test_a_folded_scalar_sentinel_still_satisfies_the_gate(tmp_path, monkeypatch):
    # docs/check-authoring-rules.md tells authors to use `>` block
    # scalars, and a folded scalar clips a trailing newline on. The gate
    # itself would accept that for a trivial reason - any non-empty
    # value passes - so what this really guards is that the trailing
    # newline does not make it read as a sentinel NEAR-MISS and get
    # rejected by the rule below.
    assert vcl._explanation_errors(
        _one_check(tmp_path, monkeypatch, ">\n                          self-evident")) == []


def test_a_near_miss_spelling_of_the_sentinel_is_rejected(tmp_path, monkeypatch):
    # The hole this closes: the gate accepts ANY non-empty value, so
    # "self evident" satisfies it and then renders verbatim under a
    # heading on a public page - the same leak the template's own
    # normalisation prevents for the correct spelling. The gate is the
    # only layer that can tell a typo from prose someone meant.
    for typo in ['"self evident"', '"Self_Evident"', '"selfevident"', '"Self-evident."']:
        errors = vcl._explanation_errors(_one_check(tmp_path, monkeypatch, typo))
        assert len(errors) == 1, typo
        assert "reads as the sentinel but is not it" in errors[0]


def test_real_prose_is_never_mistaken_for_a_near_miss(tmp_path, monkeypatch):
    # The rule above must not fire on an authored sentence that happens
    # to use the words - otherwise it blocks legitimate prose.
    assert vcl._explanation_errors(_one_check(
        tmp_path, monkeypatch,
        '"The cause is self-evident once you see which column failed."')) == []


def test_real_authored_prose_satisfies_the_gate(tmp_path, monkeypatch):
    assert vcl._explanation_errors(
        _one_check(tmp_path, monkeypatch, "The upstream extract ran before the day closed.")) == []


def test_a_whitespace_only_value_is_not_authored(tmp_path, monkeypatch):
    # Same reasoning requirements.yaml applies to its own blank fields:
    # absent and empty look identical once stripped, but a blank value
    # is someone who started and stopped.
    assert len(vcl._explanation_errors(_one_check(tmp_path, monkeypatch, '"   "'))) == 1


def test_a_retired_check_is_held_to_the_same_terms(tmp_path, monkeypatch):
    """REQ-QAC-025 says so in as many words, and an earlier version of
    this gate got it backwards - it exempted retired checks, reasoning
    they were history nobody reads. They are not: a retired check still
    renders behind the dashboard's retired-checks toggle, so a reader
    can still meet its prose."""
    checks = _one_check(tmp_path, monkeypatch, None)
    checks[0].retired_as_of = "2026-01-01"
    assert len(vcl._explanation_errors(checks)) == 1

    second = tmp_path / "b"
    second.mkdir()
    authored = _one_check(second, monkeypatch, "self-evident")
    authored[0].retired_as_of = "2026-01-01"
    assert vcl._explanation_errors(authored) == []


def test_a_check_with_no_description_is_an_error(tmp_path, monkeypatch):
    """The other half of REQ-QAC-025, and the half the first version of
    this gate missed entirely: it only ever looked at
    failure_indicates."""
    errors = vcl._explanation_errors(
        _one_check(tmp_path, monkeypatch, "self-evident", description=None))
    assert len(errors) == 1
    assert "no description" in errors[0]
    assert "docs/check-authoring-rules.md" in errors[0]


def test_both_halves_are_reported_in_one_run(tmp_path, monkeypatch):
    """REQ-QAC-025: report every offending check in one run rather than
    stopping at the first - which applies within a check too."""
    errors = vcl._explanation_errors(
        _one_check(tmp_path, monkeypatch, None, description=None))
    assert len(errors) == 2


def test_the_gate_is_off_by_default_and_fatal_only_when_asked(tmp_path, monkeypatch, capsys):
    repo = _init_repo(tmp_path)
    monkeypatch.setattr(vcl, "ROOT", repo)
    monkeypatch.setattr(vcl, "_YAML_SOURCES", [("schema.yml", vcl.cl.parse_dbt_check_metadata)])
    monkeypatch.setattr(vcl, "_EVIDENTLY_SOURCES", [])
    (repo / "schema.yml").write_text(
        _dbt_schema_with_prose("data-asset-1.ag.ds.m.c.not_null_dbt", None))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "one")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "two")

    assert vcl.main() == 0
    assert "plain-English explanation(s) missing" in capsys.readouterr().err

    assert vcl.main(require_explanations=True) == 1
    assert "no failure_indicates" in capsys.readouterr().err
