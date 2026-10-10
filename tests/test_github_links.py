"""Tests for qa_tools/common/github_links.py (running-thoughts.md #8,
2026-09-18 - "deep links from the dashboard back into GitHub"). Runs
against this repo's own real, committed check-definition files (not a
mocked fixture) - the whole point of this module is resolving REAL
check_ids to REAL lines in REAL files, so a fixture-based test would
only prove the algorithm works on data written to match it."""
from __future__ import annotations

import subprocess

from qa_tools.common import github_links


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_current_commit_sha_prefers_github_sha_env_var(monkeypatch):
    monkeypatch.setenv("GITHUB_SHA", "deadbeef" * 5)
    assert github_links.current_commit_sha() == "deadbeef" * 5


def test_current_commit_sha_falls_back_to_git_rev_parse_head(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "f.txt").write_text("x")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "initial")
    expected = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path,
                               capture_output=True, text=True, check=True).stdout.strip()
    assert github_links.current_commit_sha(root=tmp_path) == expected


def test_build_check_source_links_covers_every_real_check_id():
    links = github_links.build_check_source_links(sha="abc123")
    from qa_tools.common.validate_check_lifecycle import collect_checks
    real_check_ids = {c.check_id for c in collect_checks(None)}
    assert real_check_ids, "no real checks found - has check_lifecycle.py's source list changed?"
    assert set(links) == real_check_ids


def test_a_real_known_check_id_resolves_to_its_real_source_line():
    """registration_number's matches_regex dbt check - a real, stable
    check_id (dbt_project/models/staging/schema.yml) - verified against
    the file's own real content at the URL's own #L<n> anchor, not a
    hardcoded line number (which would make this test fragile against
    unrelated edits to that file)."""
    check_id = "data-asset-1.registry-services.civil-registration.birth-registrations.registration_number.matches_regex_dbt"
    links = github_links.build_check_source_links(sha="abc123")
    url = links[check_id]
    assert url.startswith("https://github.com/keithamoss/data-poc/blob/abc123/dbt_project/models/staging/schema.yml#L")

    line_no = int(url.rsplit("#L", 1)[1])
    lines = (github_links.ROOT / "dbt_project/models/staging/schema.yml").read_text().splitlines()
    assert check_id in lines[line_no - 1]


def test_a_real_contract_check_id_resolves_to_its_real_source_line():
    """The ODCS contract's own customProperties shape (- property:
    check_id / value: <id>) is a genuinely different YAML layout from
    dbt/soda's inline `check_id: <value>` - covers that the same plain
    text-scan approach still finds the right line for it."""
    check_id = "data-asset-1.registry-services.civil-registration.birth-registrations.registration_number.nullValues_datacontract"
    links = github_links.build_check_source_links(sha="abc123")
    url = links[check_id]
    assert "contract/bdm-birth-registrations-contract.yaml#L" in url

    line_no = int(url.rsplit("#L", 1)[1])
    lines = (github_links.ROOT / "contract/bdm-birth-registrations-contract.yaml").read_text().splitlines()
    assert check_id in lines[line_no - 1]


def test_a_real_evidently_check_id_resolves_to_its_real_source_line():
    """Evidently's own shape (a plain Python constant assignment, no
    YAML at all) - a third real format the line-scan needs to handle."""
    check_id = "data-asset-1.registry-services.civil-registration.birth-registrations.sex.drift_psi_evidently"
    links = github_links.build_check_source_links(sha="abc123")
    url = links[check_id]
    assert "qa_tools/bdm/evidently_check_lifecycle.py#L" in url

    line_no = int(url.rsplit("#L", 1)[1])
    lines = (github_links.ROOT / "qa_tools/bdm/evidently_check_lifecycle.py").read_text().splitlines()
    assert check_id in lines[line_no - 1]


def test_build_folder_links_covers_every_real_agency_and_dataset():
    folders = github_links.build_folder_links(sha="abc123")
    assert folders["agencies"]["registry-services"].endswith("/qa_tools/bdm")
    assert folders["agencies"]["child-protection-family-support"].endswith("/qa_tools/cp")
    assert folders["datasets"]["birth-registrations"].endswith("/qa_tools/bdm")
    for cp_dataset in ("cp-clients", "cp-notifications", "cp-investigations", "cp-placements", "cp-carers", "cp-case-workers"):
        assert folders["datasets"][cp_dataset].endswith("/qa_tools/cp")
