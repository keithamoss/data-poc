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

import pytest

from dashboard import embed_dashboard_data as edd

# NEEDS A BOOTSTRAPPED DEPLOYMENT (plans/tooling.md #27). This module
# reads `reports/*.json`, which is built from the deployment's recorded
# QA history - so it belongs in the CI job that bootstraps one. Nothing
# in a signature says so, which is why the mark is here rather than
# derived; tests/test_publish.py asserts it is not forgotten.
pytestmark = pytest.mark.needs_deployment



@pytest.fixture(autouse=True)
def _isolate_embed_data_targets(monkeypatch, tmp_path):
    """plans/tooling.md #10 - every test here drives the real embed(),
    which reads edd.TARGETS: the real, repo-relative
    reports/birth_registrations_dashboard.json and
    child_protection_dashboard.json. Those are BUILD ARTIFACTS, rewritten
    from scratch by tests/test_dashboard_e2e.py's own session-scoped
    built_dashboard_html fixture - so under pytest-xdist the two modules
    land on different workers and this one reads a 6.5MB file mid-rewrite,
    getting a truncated JSON and a failure that vanishes on a re-run.

    Nothing in this module asserts anything about those two files'
    CONTENTS - they're unit tests of embed()'s own wiring (changelog feed
    merging, ticket status, leaderboard, amber decisions), and embed()
    only json.loads each target and substitutes it into a const. So
    pointing them at tiny local stubs is both the real isolation fix and
    strictly more honest about what's under test. Every other real file
    embed() touches was already monkeypatched per-test; TARGETS was the
    one shared read nobody had covered."""
    stub = tmp_path / "targets"
    stub.mkdir()
    targets = []
    for const_name, real_path in edd.TARGETS:
        p = stub / f"{const_name}.json"
        p.write_text(json.dumps({"stub": const_name}))
        targets.append((const_name, str(p)))
    monkeypatch.setattr(edd, "TARGETS", targets)


def _entry(dataset, published_at, run_timestamp="2026-01-01T00:00:00+00:00", run_by="a@b.com"):
    """One feed entry as build_changelog() produces it.

    IT USED TO CARRY commit_sha AND committed_at. Both went with the git
    walk and its vocabulary (REQ-PIPE-089, REQ-PIPE-090): a result is
    visible the moment its run completes, so there is no commit in the
    path and `published_at` IS that completion.
    """
    return {
        "agency": "some-agency", "dataset": dataset, "run_timestamp": run_timestamp,
        "run_by": run_by, "published_at": published_at,
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

    assert [e["published_at"] for e in feed] == [
        "2026-01-03T09:00:00+00:00", "2026-01-02T09:00:00+00:00", "2026-01-01T09:00:00+00:00",
    ]


def test_build_changelog_feed_puts_a_missing_instant_last(monkeypatch):
    monkeypatch.setattr(edd, "CHANGELOG_SOURCES", [("agency-a", "dataset-a", "Dataset A")])
    monkeypatch.setattr(edd, "build_changelog", lambda agency, dataset: [
        _entry("dataset-a", None),
        _entry("dataset-a", "2026-01-01T09:00:00+00:00"),
    ])

    feed = edd._build_changelog_feed()

    assert feed[0]["published_at"] == "2026-01-01T09:00:00+00:00"
    assert feed[1]["published_at"] is None


def test_build_changelog_feed_caps_to_changelog_depth(monkeypatch):
    monkeypatch.setattr(edd, "CHANGELOG_SOURCES", [("agency-a", "dataset-a", "Dataset A")])
    monkeypatch.setattr(edd, "CHANGELOG_DEPTH", 2)
    monkeypatch.setattr(edd, "build_changelog", lambda agency, dataset: [
        _entry("dataset-a", f"2026-01-0{i}T09:00:00+00:00") for i in range(1, 6)
    ])

    feed = edd._build_changelog_feed()

    assert len(feed) == 2
    assert feed[0]["published_at"] == "2026-01-05T09:00:00+00:00"


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


def test_embed_defaults_to_every_assigned_person_at_zero_when_file_absent(monkeypatch, tmp_path):
    """Real scenario, same as TICKET_STATUS/AMBER_DECISIONS above: a local
    build has no GH token, so .github/workflows/deploy-pages.yml's own
    TICKET_RESOLUTIONS_JSON-writing step (qa_tools/common/leaderboard.py's
    own real `gh` boundary) never ran, so there's no real ticket-close
    history to compute a streak from - but this no longer means an
    empty leaderboard (Keith's own 2026-09-19 ask, after seeing exactly
    this on the real published page despite contract/people.yaml
    already having real people in it): every real person currently
    assigned to a dataset still appears, at streak=0, resolved against
    this repo's own real, committed contract/people.yaml (not mocked
    here, unlike the next test - this one exercises the real file)."""
    rows = _run_embed_and_extract_leaderboard(monkeypatch, tmp_path)
    assert len(rows) > 0
    assert all(row["streak"] == 0 for row in rows)


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


def _run_embed_and_extract_demo_cast(monkeypatch, tmp_path, cast_text=None):
    out_html = tmp_path / "out.html"
    monkeypatch.setattr(edd, "DASHBOARD_HTML", out_html)
    if cast_text is None:
        monkeypatch.setattr(edd, "DEMO_CAST_PATH", tmp_path / "does_not_exist.cast")
    else:
        cast_path = tmp_path / "qa_wizard.cast"
        cast_path.write_text(cast_text)
        monkeypatch.setattr(edd, "DEMO_CAST_PATH", cast_path)

    edd.embed()

    html = out_html.read_text()
    match = re.search(r"const DEMO_CAST = (.*?);\n", html)
    assert match, "DEMO_CAST const not found in built output"
    return json.loads(match.group(1))


def test_embed_defaults_to_null_demo_cast_when_file_absent(monkeypatch, tmp_path):
    """Real scenario, same as TICKET_STATUS/LEADERBOARD above: a local
    build where nobody's run scripts/dev/record_cast.py yet (or a fresh
    clone before dashboard/demos/qa_wizard.cast exists) - embed() must
    degrade to null and the Demo tab's own renderDemo() guard shows a
    real "not built yet" message, not crash."""
    assert _run_embed_and_extract_demo_cast(monkeypatch, tmp_path) is None


def test_embed_reads_the_real_committed_cast_file_when_present(monkeypatch, tmp_path):
    # A real, multi-line asciinema v2 .cast file (header + event lines) -
    # embedded as a single JSON STRING (not parsed/reshaped), since the
    # player consumes this exact raw text via its own "asciicast" parser.
    cast_text = (
        '{"version":2,"width":100,"height":28,"timestamp":1,"env":{}}\n'
        '[0.1,"o","hello\\r\\n"]\n'
    )
    embedded = _run_embed_and_extract_demo_cast(monkeypatch, tmp_path, cast_text)
    assert embedded == cast_text


# ---------------------------------------------------------------------------
# PERIOD_SEQUENCES - REQ-DASH-054 criteria 1, 2 and 3.
#
# The page's period arithmetic is a LOOKUP against these now, replacing a
# JS port of pipeline/cadence.py's cycle_start(). What the port could never
# do is the reason the embed exists: a cadence RULE cannot produce an
# AUTHORED date list, and the quarterly calendar is one (Feb/May/Aug/Nov,
# deliberately not calendar quarters), so "which quarter is this date in"
# had no answer at all for Child Protection.
# ---------------------------------------------------------------------------
def _run_embed_and_extract_period_sequences(monkeypatch, tmp_path):
    out_html = tmp_path / "out.html"
    monkeypatch.setattr(edd, "DASHBOARD_HTML", out_html)
    edd.embed()
    match = re.search(r"const PERIOD_SEQUENCES = (.*?);\n", out_html.read_text())
    assert match, "PERIOD_SEQUENCES const not found in built output"
    return json.loads(match.group(1))


def test_the_embed_carries_every_named_calendar_and_which_one_each_dataset_follows(
        monkeypatch, tmp_path):
    """Criterion 1, both halves. The sequences alone are unusable: the page
    is asked about a DATASET's period, and without the mapping it would
    have to guess which calendar to look in - or merge them, which is
    silently wrong for whichever calendar lost."""
    from qa_tools.common import hierarchy, schedule

    sequences = _run_embed_and_extract_period_sequences(monkeypatch, tmp_path)

    assert set(sequences["calendars"]) == {c.name for c in schedule.calendars()}
    assert set(sequences["datasetCalendar"]) == {
        d.dataset_id for d in hierarchy.all_datasets()}
    for name, periods in sequences["calendars"].items():
        assert periods, f"{name} embedded no periods at all"
        assert all({"period", "date"} == set(p) for p in periods)


def test_a_dataset_with_no_calendar_is_recorded_as_having_none(monkeypatch, tmp_path):
    """REQ-PIPE-106's subject reaching the embed. It is a real state - a
    dataset can exist before any supply is agreed - so the mapping says
    null rather than the build failing or the dataset being left out.
    Omitting it would be worse than either: a missing key and a null key
    read identically in JavaScript, so the page could not tell "no
    calendar" from "not a dataset"."""
    sequences = _run_embed_and_extract_period_sequences(monkeypatch, tmp_path)
    # Every value is either a real calendar name or an explicit null.
    known = set(sequences["calendars"])
    for dataset_id, calendar in sequences["datasetCalendar"].items():
        assert calendar is None or calendar in known, \
            f"{dataset_id} points at a calendar that was not embedded: {calendar!r}"


def test_the_embedded_dates_come_from_the_authored_calendar_rather_than_a_rule(
        monkeypatch, tmp_path):
    """Criterion 2, positively. The quarterly calendar's own anchor is
    February, so its periods must be Feb/May/Aug/Nov - a rule producing
    calendar quarters would give Jan/Apr/Jul/Oct, which is the exact
    mistake this replaces."""
    sequences = _run_embed_and_extract_period_sequences(monkeypatch, tmp_path)
    months = {int(p["date"][5:7]) for p in sequences["calendars"]["quarterly"]}
    assert months <= {2, 5, 8, 11}, f"quarterly periods fell outside the authored months: {months}"


def test_nothing_that_has_not_begun_is_embedded(monkeypatch, tmp_path):
    """Criterion 3, and Keith's own question behind it: "why would we be
    able to choose a date in the future? nothing has happened yet, so why
    project forward?" The as-of picker asks about the past, so a date with
    nothing behind it has no answer to give - which removes the horizon
    question rather than answering it.

    ON THE ASSET'S CLOCK, not this machine's. Perth is eight hours ahead of
    UTC, so for a third of every day the two are on different calendar
    dates - and a test that took `today` from date.today() would go red in
    that window for no reason about the code."""
    from qa_tools.common import asset_time

    today = asset_time.now().date().isoformat()
    sequences = _run_embed_and_extract_period_sequences(monkeypatch, tmp_path)
    for name, periods in sequences["calendars"].items():
        future = [p["date"] for p in periods if p["date"] > today]
        assert not future, f"{name} embedded {len(future)} period(s) that have not begun: {future[:3]}"


def test_the_current_period_IS_embedded_because_it_has_begun(monkeypatch, tmp_path):
    """The other side of criterion 3, and the one a naive "drop anything
    not in the past" filter gets wrong. A quarterly period that began six
    weeks ago is the period a viewer asking about today is in; dropping it
    would make today unpickable on that calendar."""
    from qa_tools.common import asset_time, schedule

    today = asset_time.now().date()
    sequences = _run_embed_and_extract_period_sequences(monkeypatch, tmp_path)
    for name in sequences["calendars"]:
        expected = [p.date.isoformat()
                     for p in schedule.periods_for_calendar(name, until=today)]
        assert [p["date"] for p in sequences["calendars"][name]] == expected


def test_deriving_the_sequences_opens_nothing_under_data(monkeypatch, tmp_path):
    """Criterion 2's real constraint, asserted rather than reasoned about.

    A schedule is CONFIGURATION, so this derivation is entitled to read
    contract/ and nothing else - and a new embed into the dashboard build
    is exactly the shape CLAUDE.md's never-read-data rule exists to catch.
    Asserted by watching the real `open` for a path under data/, which is
    the mechanism rather than a promise about it.

    SCOPED TO THE DERIVATION, not to embed() as a whole, and the narrower
    claim is the honest one: embed() reads a dozen other things whose own
    entitlements are their own requirements' business, and a test that
    swept them all up here would go red for a reason that had nothing to do
    with period sequences. What this holds is that the two calls the embed
    makes for THIS const - periods_for_calendar() and
    calendar_for_dataset() - touch configuration only."""
    import builtins
    from pathlib import Path

    from qa_tools.common import hierarchy, schedule

    root = Path(edd.__file__).resolve().parent.parent
    data_dir = root / "data"
    opened: list[str] = []
    real_open = builtins.open

    def watched(file, *args, **kwargs):
        try:
            resolved = Path(file).resolve()
        except TypeError:                     # a file descriptor, not a path
            resolved = None
        if resolved is not None and data_dir in resolved.parents:
            opened.append(str(resolved))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", watched)
    today = __import__("datetime").date(2026, 9, 27)
    for cal in schedule.calendars():
        schedule.periods_for_calendar(cal.name, until=today)
    for entry in hierarchy.all_datasets():
        try:
            schedule.calendar_for_dataset(entry.dataset_id)
        except Exception:
            pass

    assert opened == [], f"the schedule read {len(opened)} file(s) under data/: {opened[:3]}"


def test_the_schedule_ended_notice_names_the_file_dates_are_authored_in(monkeypatch, tmp_path):
    """REQ-PIPE-154 criterion 3 on the page, after REQ-PIPE-110: the
    exhausted-schedule notice tells a person which file to edit, and the
    calendars live in contract/calendar.yaml now. The embed hardcoded
    contract/data-asset.yaml, so the notice sent people to a file that no
    longer holds a single delivery date."""
    from qa_tools.common import supply_holds

    out_html = tmp_path / "out.html"
    monkeypatch.setattr(edd, "DASHBOARD_HTML", out_html)
    edd.embed()
    match = re.search(r"const SCHEDULE_RUNWAY = (.*?);\n", out_html.read_text())
    assert match, "SCHEDULE_RUNWAY const not found in built output"
    assert json.loads(match.group(1))["configFile"] == "contract/calendar.yaml"
    assert supply_holds.SCHEDULE_FILE == "contract/calendar.yaml"


def test_slot_due_dates_carry_only_the_slots_due_off_their_period_date(monkeypatch, tmp_path):
    """REQ-PIPE-167 criterion 5: the page is told a slot's own due date
    wherever it differs from the period's date - and today, with no
    dataset due ahead of its period, that is nowhere."""
    out_html = tmp_path / "out.html"
    monkeypatch.setattr(edd, "DASHBOARD_HTML", out_html)
    edd.embed()
    match = re.search(r"const SLOT_DUE_DATES = (.*?);\n", out_html.read_text())
    assert match, "SLOT_DUE_DATES const not found in built output"
    assert json.loads(match.group(1)) == {}


def test_slot_due_dates_name_a_following_period_datasets_due_date():
    from qa_tools.common import slots

    class Slot:
        def __init__(self, period_date, due):
            from datetime import date, datetime, timezone
            self.date = date.fromisoformat(period_date)
            self.due_at = datetime.fromisoformat(due).replace(tzinfo=timezone.utc)

    got = edd._slot_due_dates({"cp-early": [Slot("2026-02-01", "2026-01-04T01:00:00"),
                                            Slot("2026-05-01", "2026-05-01T01:00:00")]})
    assert got == {"cp-early": {"2026-02-01": "2026-01-04"}}
    assert slots  # imported for the shape the real call passes
