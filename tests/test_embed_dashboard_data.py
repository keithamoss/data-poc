"""Tests for dashboard/embed_dashboard_data.py's Phase 5a addition -
_build_changelog_feed()'s merge/label/sort/cap logic. build_changelog()
itself (real qa_results/ + git history) already has its own tests
(tests/test_changelog.py) - this only covers what this module adds on
top: merging multiple dataset scopes into one feed, attaching a
display label, sorting newest-committed-first, and capping depth.

Also covers item 76's UI-integration follow-up (2026-09-18): embed()'s
own handling of OPEN_TICKETS_JSON, the file only .github/workflows/
deploy-pages.yml's real `gh issue list` step ever writes - present vs.
absent (a local ./run_pipeline.sh build has no real token, so this must
degrade gracefully, not crash). parse_open_tickets() itself already has
its own tests (tests/test_ticket_status.py); this only covers embed()'s
own read-file-or-default-to-empty-list wiring."""
from __future__ import annotations

import json
import re

from dashboard import embed_dashboard_data as edd


def _entry(dataset, committed_at, run_timestamp="2026-01-01T00:00:00+00:00", run_by="a@b.com"):
    return {
        "agency": "some-agency", "dataset": dataset, "run_timestamp": run_timestamp,
        "run_by": run_by, "commit_sha": "abc123", "committed_at": committed_at,
    }


def test_build_changelog_feed_merges_all_sources_with_labels(monkeypatch):
    monkeypatch.setattr(edd, "CHANGELOG_SOURCES", [
        ("agency-a", "dataset-a", "Dataset A"),
        ("agency-b", "dataset-b", "Dataset B"),
    ])
    monkeypatch.setattr(edd, "build_changelog", lambda agency, dataset: {
        ("agency-a", "dataset-a"): [_entry("dataset-a", "2026-01-01T10:00:00+00:00")],
        ("agency-b", "dataset-b"): [_entry("dataset-b", "2026-01-01T09:00:00+00:00")],
    }[(agency, dataset)])

    feed = edd._build_changelog_feed()

    assert [e["label"] for e in feed] == ["Dataset A", "Dataset B"]


def test_build_changelog_feed_sorts_newest_committed_first(monkeypatch):
    monkeypatch.setattr(edd, "CHANGELOG_SOURCES", [("agency-a", "dataset-a", "Dataset A")])
    monkeypatch.setattr(edd, "build_changelog", lambda agency, dataset: [
        _entry("dataset-a", "2026-01-01T09:00:00+00:00"),
        _entry("dataset-a", "2026-01-03T09:00:00+00:00"),
        _entry("dataset-a", "2026-01-02T09:00:00+00:00"),
    ])

    feed = edd._build_changelog_feed()

    assert [e["committed_at"] for e in feed] == [
        "2026-01-03T09:00:00+00:00", "2026-01-02T09:00:00+00:00", "2026-01-01T09:00:00+00:00",
    ]


def test_build_changelog_feed_puts_missing_committed_at_last(monkeypatch):
    monkeypatch.setattr(edd, "CHANGELOG_SOURCES", [("agency-a", "dataset-a", "Dataset A")])
    monkeypatch.setattr(edd, "build_changelog", lambda agency, dataset: [
        _entry("dataset-a", None),
        _entry("dataset-a", "2026-01-01T09:00:00+00:00"),
    ])

    feed = edd._build_changelog_feed()

    assert feed[0]["committed_at"] == "2026-01-01T09:00:00+00:00"
    assert feed[1]["committed_at"] is None


def test_build_changelog_feed_caps_to_changelog_depth(monkeypatch):
    monkeypatch.setattr(edd, "CHANGELOG_SOURCES", [("agency-a", "dataset-a", "Dataset A")])
    monkeypatch.setattr(edd, "CHANGELOG_DEPTH", 2)
    monkeypatch.setattr(edd, "build_changelog", lambda agency, dataset: [
        _entry("dataset-a", f"2026-01-0{i}T09:00:00+00:00") for i in range(1, 6)
    ])

    feed = edd._build_changelog_feed()

    assert len(feed) == 2
    assert feed[0]["committed_at"] == "2026-01-05T09:00:00+00:00"


def _run_embed_and_extract_ticket_status(monkeypatch, tmp_path, raw_issues=None):
    out_html = tmp_path / "out.html"
    monkeypatch.setattr(edd, "DASHBOARD_HTML", out_html)
    if raw_issues is None:
        monkeypatch.setattr(edd, "OPEN_TICKETS_JSON", tmp_path / "does_not_exist.json")
    else:
        tickets_path = tmp_path / "open_tickets.json"
        tickets_path.write_text(json.dumps(raw_issues))
        monkeypatch.setattr(edd, "OPEN_TICKETS_JSON", tickets_path)

    edd.embed()

    html = out_html.read_text()
    match = re.search(r"const TICKET_STATUS = (.*?);\n", html)
    assert match, "TICKET_STATUS const not found in built output"
    return json.loads(match.group(1))


def test_embed_defaults_to_empty_ticket_status_when_file_absent(monkeypatch, tmp_path):
    """Real scenario: a local ./run_pipeline.sh build has no GH token, so
    .github/workflows/deploy-pages.yml's own OPEN_TICKETS_JSON-writing
    step never ran - embed() must degrade to {} rather than crash."""
    assert _run_embed_and_extract_ticket_status(monkeypatch, tmp_path) == {}


def test_embed_reads_real_open_tickets_json_when_present(monkeypatch, tmp_path):
    raw_issues = [{
        "number": 42, "title": "Birth Registrations is red",
        "url": "https://github.com/o/r/issues/42",
        "labels": [{"name": "qa-ticket"}, {"name": "dataset:birth-registrations"}],
        "updatedAt": "2026-09-18T00:00:00Z",
    }]
    ticket_status = _run_embed_and_extract_ticket_status(monkeypatch, tmp_path, raw_issues)
    assert ticket_status == {
        "birth-registrations": {
            "number": 42, "url": "https://github.com/o/r/issues/42",
            "title": "Birth Registrations is red", "updated_at": "2026-09-18T00:00:00Z",
        }
    }


def _run_embed_and_extract_leaderboard(monkeypatch, tmp_path, raw_ticket_resolutions=None):
    out_html = tmp_path / "out.html"
    monkeypatch.setattr(edd, "DASHBOARD_HTML", out_html)
    if raw_ticket_resolutions is None:
        monkeypatch.setattr(edd, "TICKET_RESOLUTIONS_JSON", tmp_path / "does_not_exist.json")
    else:
        path = tmp_path / "ticket_resolutions.json"
        path.write_text(json.dumps(raw_ticket_resolutions))
        monkeypatch.setattr(edd, "TICKET_RESOLUTIONS_JSON", path)

    edd.embed()

    html = out_html.read_text()
    match = re.search(r"const LEADERBOARD = (.*?);\n", html)
    assert match, "LEADERBOARD const not found in built output"
    return json.loads(match.group(1))


def test_embed_defaults_to_empty_leaderboard_when_file_absent(monkeypatch, tmp_path):
    """Real scenario, same as TICKET_STATUS/ACCEPTANCES above: a local
    ./run_pipeline.sh build has no GH token, so .github/workflows/
    deploy-pages.yml's own TICKET_RESOLUTIONS_JSON-writing step (qa_tools/
    common/leaderboard.py's own real `gh` boundary) never ran - embed()
    must degrade to [] rather than crash."""
    assert _run_embed_and_extract_leaderboard(monkeypatch, tmp_path) == []


def test_embed_reads_real_ticket_resolutions_json_when_present(monkeypatch, tmp_path):
    raw_tickets = [{
        "number": 1, "labels": [{"name": "dataset:birth-registrations"}],
        "events": [{"event": "closed", "actor": "knownperson", "created_at": "2026-01-01T09:00:00Z"}],
    }]
    monkeypatch.setattr(edd, "parse_people_config", lambda path: {
        "people": {"known@example.com": {"name": "Known Person", "nickname": "KP", "github": "knownperson"}},
        "agency_assignments": {}, "dataset_assignments": {},
    })
    leaderboard_rows = _run_embed_and_extract_leaderboard(monkeypatch, tmp_path, raw_tickets)
    assert leaderboard_rows == [{
        "dataset_id": "birth-registrations", "name": "Known Person", "nickname": "KP",
        "github": "knownperson", "streak": 1,
    }]
