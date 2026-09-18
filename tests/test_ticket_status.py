"""Tests for qa_tools/common/ticket_status.py - the GitHub Issues ->
dashboard reshaping logic (item 76's UI integration follow-up,
plans/qa-pipeline.md). A pure function of already-fetched `gh issue
list --json ...` output - no real `gh` invocation or network access
here, same reasoning as tests/test_ticket_sync.py's own FakeGh."""
from __future__ import annotations

from qa_tools.common.ticket_status import parse_open_tickets


def _issue(number, dataset_id, url=None, title="Birth Registrations is red", updated_at="2026-09-18T00:00:00Z"):
    labels = [{"name": "qa-ticket"}]
    if dataset_id is not None:
        labels.append({"name": f"dataset:{dataset_id}"})
    return {
        "number": number,
        "title": title,
        "url": url or f"https://github.com/o/r/issues/{number}",
        "labels": labels,
        "updatedAt": updated_at,
    }


def test_empty_list_gives_empty_mapping():
    assert parse_open_tickets([]) == {}


def test_single_issue_keyed_by_its_dataset_label():
    result = parse_open_tickets([_issue(42, "birth-registrations")])
    assert result == {
        "birth-registrations": {
            "number": 42,
            "url": "https://github.com/o/r/issues/42",
            "title": "Birth Registrations is red",
            "updated_at": "2026-09-18T00:00:00Z",
        }
    }


def test_multiple_issues_across_different_datasets():
    result = parse_open_tickets([_issue(1, "birth-registrations"), _issue(2, "cp-clients")])
    assert set(result) == {"birth-registrations", "cp-clients"}
    assert result["cp-clients"]["number"] == 2


def test_issue_without_a_dataset_label_is_skipped_not_raised():
    result = parse_open_tickets([_issue(1, None)])
    assert result == {}


def test_missing_updated_at_defaults_to_none():
    issue = _issue(1, "birth-registrations")
    del issue["updatedAt"]
    result = parse_open_tickets([issue])
    assert result["birth-registrations"]["updated_at"] is None
