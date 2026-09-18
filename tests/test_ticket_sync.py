"""Tests for qa_tools/common/ticket_sync.py - the GitHub Issues
ticketing MVP's real create/dedup/update decision logic (item 76,
plans/qa-pipeline.md). Every test monkeypatches `_run_gh` (the module's
own single subprocess boundary) - this deliberately never invokes a
real `gh` CLI call or touches a real GitHub repo, since (unlike dbt/
Soda/datacontract-cli, which are all safe to actually re-run locally)
opening or commenting on a real GitHub Issue is a genuine external side
effect with real visibility, exactly the kind of thing a test suite
must never actually do."""
from __future__ import annotations

import json

import pytest

from qa_tools.common import ticket_sync
from qa_tools.common.ticket_sync import DatasetScope, sync_dataset


class FakeGh:
    """Records every real `gh` CLI invocation this module would have
    made, and returns a scripted response - a fake at the one real I/O
    boundary (_run_gh), not a deeper mock, so the test still exercises
    this module's own real argument-building/parsing logic."""

    def __init__(self, list_response: list[dict] | None = None, create_url: str | None = None):
        self.calls: list[list[str]] = []
        self.list_response = list_response if list_response is not None else []
        self.create_url = create_url or "https://github.com/o/r/issues/42"

    def __call__(self, args: list[str]) -> str:
        self.calls.append(args)
        if args[:2] == ["issue", "list"]:
            return json.dumps(self.list_response)
        if args[:2] == ["issue", "create"]:
            return self.create_url + "\n"
        if args[:2] == ["issue", "comment"]:
            return ""
        if args[:2] == ["label", "create"]:
            return ""
        raise AssertionError(f"unexpected gh invocation: {args}")


def _green_dataset():
    return {"columns": [{"checks": [{"current": 0, "warn": 1, "fail": 2, "retired_as_of": None}]}]}


def _red_dataset():
    return {"columns": [{"checks": [{"current": 5, "warn": 1, "fail": 2, "retired_as_of": None}]}]}


def _amber_dataset():
    return {"columns": [{"checks": [{"current": 1.5, "warn": 1, "fail": 2, "retired_as_of": None}]}]}


@pytest.fixture
def scope():
    return DatasetScope(id="birth-registrations", name="Birth Registrations", agency_id="registry-services")


def test_no_open_ticket_and_red_opens_a_new_one(monkeypatch, scope):
    fake = FakeGh(list_response=[])
    monkeypatch.setattr(ticket_sync, "_run_gh", fake)

    result = sync_dataset("o", "r", scope, _red_dataset())

    assert result == "birth-registrations: opened #42 (red)"
    create_call = next(c for c in fake.calls if c[:2] == ["issue", "create"])
    assert "--label" in create_call
    label_value = create_call[create_call.index("--label") + 1]
    assert "qa-ticket" in label_value
    assert "dataset:birth-registrations" in label_value


def test_no_open_ticket_and_amber_opens_a_new_one(monkeypatch, scope):
    """2026-09-18 (running-thoughts.md #6): amber-only datasets used to
    get no real ticket at all ("no ticket, amber/green -> nothing to
    do") - nowhere for a human to comment /accept on. Now amber opens
    one too, same as red always has."""
    fake = FakeGh(list_response=[])
    monkeypatch.setattr(ticket_sync, "_run_gh", fake)

    result = sync_dataset("o", "r", scope, _amber_dataset())

    assert result == "birth-registrations: opened #42 (amber)"
    create_call = next(c for c in fake.calls if c[:2] == ["issue", "create"])
    title = create_call[create_call.index("--title") + 1]
    assert title == "Birth Registrations is amber"
    body = create_call[create_call.index("--body") + 1]
    assert "/accept" in body


def test_opening_a_ticket_with_a_real_assignee_passes_gh_assignee(monkeypatch, scope):
    """running-thoughts.md #2, 2026-09-18: a dataset with real people
    assigned (contract/people.yaml, via qa_tools/common/people.py's own
    dataset-then-agency resolution) gets a real GitHub --assignee on
    the ticket it opens."""
    fake = FakeGh(list_response=[])
    monkeypatch.setattr(ticket_sync, "_run_gh", fake)
    people_config = {
        "people": {},
        "agency_assignments": {"registry-services": [{"email": "keith@example.com", "github": "keithamoss", "role": "qa"}]},
        "dataset_assignments": {},
    }

    ticket_sync.sync_dataset("o", "r", scope, _red_dataset(), people_config)

    create_call = next(c for c in fake.calls if c[:2] == ["issue", "create"])
    assert "--assignee" in create_call
    assert create_call[create_call.index("--assignee") + 1] == "keithamoss"


def test_opening_a_ticket_with_no_people_configured_omits_assignee_entirely(monkeypatch, scope):
    fake = FakeGh(list_response=[])
    monkeypatch.setattr(ticket_sync, "_run_gh", fake)

    ticket_sync.sync_dataset("o", "r", scope, _red_dataset())

    create_call = next(c for c in fake.calls if c[:2] == ["issue", "create"])
    assert "--assignee" not in create_call


def test_opening_a_ticket_ensures_both_real_labels_exist_first(monkeypatch, scope):
    """Real bug, 2026-09-18 (plans/qa-pipeline.md item 79): `gh issue
    create --label` fails outright if the label isn't already a real
    repo label - unlike `gh issue list --label`, which just silently
    matches nothing. The very first real push-triggered run hit this
    for real (neither qa-ticket nor any dataset:<id> label had ever
    been created)."""
    fake = FakeGh(list_response=[])
    monkeypatch.setattr(ticket_sync, "_run_gh", fake)

    ticket_sync.open_ticket("o", "r", scope, "red")

    label_create_calls = [c for c in fake.calls if c[:2] == ["label", "create"]]
    created_names = {c[2] for c in label_create_calls}
    assert created_names == {"qa-ticket", "dataset:birth-registrations"}
    for call in label_create_calls:
        assert "--force" in call
    # both labels must exist before the issue is actually created
    create_index = fake.calls.index(next(c for c in fake.calls if c[:2] == ["issue", "create"]))
    assert all(fake.calls.index(c) < create_index for c in label_create_calls)


def test_no_open_ticket_and_not_red_does_nothing(monkeypatch, scope):
    fake = FakeGh(list_response=[])
    monkeypatch.setattr(ticket_sync, "_run_gh", fake)

    result = sync_dataset("o", "r", scope, _green_dataset())

    assert result == "birth-registrations: green, no open ticket - nothing to do"
    assert not any(c[:2] == ["issue", "create"] for c in fake.calls)
    assert not any(c[:2] == ["issue", "comment"] for c in fake.calls)


def test_open_ticket_still_red_gets_a_still_red_comment_not_a_new_ticket(monkeypatch, scope):
    fake = FakeGh(list_response=[{"number": 7}])
    monkeypatch.setattr(ticket_sync, "_run_gh", fake)

    result = sync_dataset("o", "r", scope, _red_dataset())

    assert result == "birth-registrations: #7 still red, commented"
    assert not any(c[:2] == ["issue", "create"] for c in fake.calls)
    comment_call = next(c for c in fake.calls if c[:2] == ["issue", "comment"])
    assert comment_call[2] == "7"
    body = comment_call[comment_call.index("--body") + 1]
    assert "still" in body.lower() and "red" in body.lower()


def test_open_ticket_resolved_gets_a_resolved_comment_and_is_never_closed(monkeypatch, scope):
    fake = FakeGh(list_response=[{"number": 7}])
    monkeypatch.setattr(ticket_sync, "_run_gh", fake)

    result = sync_dataset("o", "r", scope, _green_dataset())

    assert result == "birth-registrations: #7 resolved to green, commented (not closed)"
    comment_call = next(c for c in fake.calls if c[:2] == ["issue", "comment"])
    body = comment_call[comment_call.index("--body") + 1]
    assert "resolved" in body.lower()
    assert "not auto-close" in body.lower() or "not" in body.lower()
    # closing is always a human decision - this module never passes
    # `issue close`/`--state closed` under any circumstance.
    assert not any(c[:2] == ["issue", "close"] for c in fake.calls)


def test_find_open_ticket_returns_none_for_an_empty_list(monkeypatch):
    fake = FakeGh(list_response=[])
    monkeypatch.setattr(ticket_sync, "_run_gh", fake)
    assert ticket_sync.find_open_ticket("o", "r", "birth-registrations") is None


def test_find_open_ticket_returns_the_real_issue_number(monkeypatch):
    fake = FakeGh(list_response=[{"number": 99}])
    monkeypatch.setattr(ticket_sync, "_run_gh", fake)
    assert ticket_sync.find_open_ticket("o", "r", "birth-registrations") == 99


def test_open_ticket_parses_the_issue_number_from_gh_own_url_output(monkeypatch, scope):
    fake = FakeGh(create_url="https://github.com/o/r/issues/123")
    monkeypatch.setattr(ticket_sync, "_run_gh", fake)
    assert ticket_sync.open_ticket("o", "r", scope, "red") == 123
