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
from pathlib import Path

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
    which reads every collection's real, repo-relative dashboard file under
    reports/ (edd.collection_targets(), REQ-DASH-244). Those are BUILD ARTIFACTS, rewritten
    from scratch by tests/test_dashboard_e2e.py's own session-scoped
    built_dashboard_html fixture - so under pytest-xdist the two modules
    land on different workers and this one reads a 6.5MB file mid-rewrite,
    getting a truncated JSON and a failure that vanishes on a re-run.
    (Since REQ-TEST-281 that build writes a directory of each worker's
    own, never the real reports/, so the race itself is gone; the stubs
    stay because they are the honest input for what this module tests.)

    Nothing in this module asserts anything about those two files'
    CONTENTS - they're unit tests of embed()'s own wiring (changelog feed
    merging, ticket status, leaderboard, amber decisions), and embed()
    only json.loads each target and substitutes it into a const. So
    pointing them at tiny local stubs is both the real isolation fix and
    strictly more honest about what's under test. Every other real file
    embed() touches was already monkeypatched per-test; TARGETS was the
    one shared read nobody had covered (it was edd.TARGETS until REQ-DASH-244)."""
    stub = tmp_path / "targets"
    stub.mkdir()
    targets = []
    for collection_id, _real_path in edd.collection_targets():
        p = stub / f"{collection_id}.json"
        p.write_text(json.dumps({"datasets": []}))
        targets.append((collection_id, str(p)))
    monkeypatch.setattr(edd, "collection_targets", lambda: targets)


@pytest.fixture(autouse=True)
def _no_applied_corrections_read(monkeypatch):
    """The feed also lists each applied calendar correction (REQ-DASH-172),
    read from the database. These are unit tests of the merge, so that read
    is stubbed: on a fresh worker database with no qa schema it failed every
    one of them in CI (94f1ea6) while passing locally, where an earlier
    module on the same worker had created the schema."""
    from pipeline import corrections

    monkeypatch.setattr(corrections, "applied_feed", lambda: [])


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
    February, so its periods are Feb/May/Aug/Nov - a rule producing
    calendar quarters would give Jan/Apr/Jul/Oct, which is the exact
    mistake this replaces. AUTHORED DATES ARE THE REFERENCE, not a month
    set: REQ-GEN-205's correction authors 2013-Q4 and 2014-Q3 in October
    and July, and the embedded dates must be exactly those."""
    from qa_tools.common import schedule

    sequences = _run_embed_and_extract_period_sequences(monkeypatch, tmp_path)
    embedded = {(p["period"], p["date"][:10]) for p in sequences["calendars"]["quarterly"]}
    authored = {(p.name, p.date.isoformat())
                for v in schedule.calendar("quarterly").versions for p in v.periods}
    assert embedded and embedded <= authored, sorted(embedded - authored)[:5]
    assert {int(d[5:7]) for _n, d in embedded} >= {2, 5, 8, 11}


def _furthest_open_period(name, now):
    """The furthest period date a slot whose claim window has opened by
    `now` fills, across the datasets on calendar `name`."""
    from datetime import timedelta

    from qa_tools.common import hierarchy, schedule, slots

    reach = None
    for entry in hierarchy.all_datasets():
        try:
            if schedule.calendar_for_dataset(entry.dataset_id).name != name:
                continue
            found = slots.slots_for_dataset(entry.dataset_id, until=now.date() + timedelta(days=400))
        except (schedule.NoCalendarAgreed, schedule.ScheduleConfigError):
            continue
        for slot in found:
            if slot.claim_opens_at <= now and (reach is None or slot.period.date > reach):
                reach = slot.period.date
    return reach


def test_nothing_no_slot_has_opened_for_is_embedded(monkeypatch, tmp_path):
    """Criterion 3 as amended by REQ-DASH-326 (Keith's own question behind
    the original: "why would we be able to choose a date in the future?").
    The sequence ends at the later of today's period and the furthest period
    a slot already open fills - at files_go_to_period 1 a quarter that has not
    begun - and holds nothing beyond it.

    ON THE ASSET'S CLOCK, not this machine's: Perth is eight hours ahead of
    UTC, so for a third of every day the two are on different dates."""
    from qa_tools.common import asset_time

    now = asset_time.now()
    today = now.date().isoformat()
    sequences = _run_embed_and_extract_period_sequences(monkeypatch, tmp_path)
    for name, periods in sequences["calendars"].items():
        reach = _furthest_open_period(name, now)
        bound = max(today, reach.isoformat()) if reach else today
        beyond = [p["date"] for p in periods if p["date"] > bound]
        assert not beyond, f"{name} embedded {len(beyond)} period(s) no slot has opened for: {beyond[:3]}"


def test_the_period_an_open_slot_fills_IS_embedded(monkeypatch, tmp_path):
    """The other side of criterion 3. Today's period is embedded because it
    has begun, and so is the period a slot already open fills - Child
    Protection's next quarter - or a supply filed to it would have no period
    to sit under and its deep link would read Period not found (REQ-DASH-326
    criterion 10, the dashboard review's F1)."""
    from qa_tools.common import asset_time, schedule

    now = asset_time.now()
    sequences = _run_embed_and_extract_period_sequences(monkeypatch, tmp_path)
    for name in sequences["calendars"]:
        reach = _furthest_open_period(name, now)
        until = max(now.date(), reach) if reach else now.date()
        expected = [p.date.isoformat() for p in schedule.periods_for_calendar(name, until=until)]
        assert [p["date"] for p in sequences["calendars"][name]] == expected
    assert sequences["today"] == now.date().isoformat()


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
    wherever it differs from the period's date - today, exactly Birth
    Registrations' twelve evening-before days (REQ-GEN-044, 2026-06-18 to
    2026-06-29), each due the day before, and nowhere else."""
    out_html = tmp_path / "out.html"
    monkeypatch.setattr(edd, "DASHBOARD_HTML", out_html)
    edd.embed()
    match = re.search(r"const SLOT_DUE_DATES = (.*?);\n", out_html.read_text())
    assert match, "SLOT_DUE_DATES const not found in built output"
    from datetime import date, timedelta
    era = [date(2026, 6, 18) + timedelta(days=n) for n in range(12)]
    assert json.loads(match.group(1)) == {
        "birth-registrations": {d.isoformat(): (d - timedelta(days=1)).isoformat() for d in era}}


def test_slot_due_dates_are_only_for_a_cadence_rule_calendar():
    """REQ-DASH-326 criteria 3 and 4: an authored calendar's headings read
    its embedded slots ('For <period> · due <instant>'), so only a cadence
    rule's day-before slots travel this way - a slot due off its period's
    date on the quarterly calendar is carried by periodSlots instead."""

    class Slot:
        def __init__(self, period_date, due):
            from datetime import date, datetime, timezone
            self.date = date.fromisoformat(period_date)
            self.due_at = datetime.fromisoformat(due).replace(tzinfo=timezone.utc)

    got = edd._slot_due_dates({
        "cp-clients": [Slot("2026-05-01", "2026-02-01T01:00:00")],
        "birth-registrations": [Slot("2026-06-18", "2026-06-17T06:00:00"),
                                Slot("2026-06-30", "2026-06-30T06:00:00")]})
    assert got == {"birth-registrations": {"2026-06-18": "2026-06-17"}}


def test_applied_corrections_are_listed_outside_the_cap(monkeypatch):
    """REQ-DASH-172 criterion 8 (delivery-critic on 172, #7): rare, so never
    pushed out by thirty publishes."""
    from pipeline import corrections

    monkeypatch.setattr(edd, "CHANGELOG_SOURCES", [("agency-a", "dataset-a", "Dataset A")])
    monkeypatch.setattr(edd, "build_changelog", lambda agency, dataset: [
        _entry("dataset-a", f"2026-01-{d:02d}T09:00:00+00:00")
        for d in range(1, edd.CHANGELOG_DEPTH + 6)])
    monkeypatch.setattr(corrections, "applied_feed", lambda: [{
        "kind": "correction", "reference": "CAB-1", "published_at": "2025-01-01T00:00:00+00:00"}])
    feed = edd._build_changelog_feed()
    assert [e.get("reference") for e in feed if e.get("kind") == "correction"] == ["CAB-1"]
    assert len([e for e in feed if e.get("kind") != "correction"]) == edd.CHANGELOG_DEPTH


def test_an_embedded_const_cannot_close_its_script_element():
    """post-build-review #187: json.dumps leaves '</script>' as it is, and
    inside a <script> that ends the element - every const was exposed."""
    from dashboard.embed_dashboard_data import _replace_const
    html = _replace_const("<script>\nconst X = null;\n</script>", "X",
                          json.dumps({"t": "</script><img src=x onerror=alert(1)>"}))
    assert html.count("</script>") == 1
    assert "<\\/script>" in html


# --- REQ-DASH-291 and REQ-DASH-293: the data files embed() writes ---------

def _embed_to(monkeypatch, tmp_path, name="out.html"):
    out_html = tmp_path / name
    monkeypatch.setattr(edd, "DASHBOARD_HTML", str(out_html))
    edd.embed()
    return out_html


class TestTheDataFiles:
    """REQ-DASH-291 criteria 1, 2, 4, 6, 11 and 16."""

    def test_one_file_per_collection_and_one_for_requirements_and_plans(self, monkeypatch, tmp_path):
        from dashboard import data_files

        page = _embed_to(monkeypatch, tmp_path)
        manifest = data_files.page_manifest(page.read_text())
        keys = [e["key"] for e in manifest["files"]]
        expected = [data_files.collection_key(c) for c, _ in edd.collection_targets()]
        assert expected, "the registry must hold collections for this to mean anything"
        assert keys == expected + [data_files.REQUIREMENTS_PLANS_KEY]
        on_disk = sorted(p.name for p in (tmp_path / "data").iterdir())
        assert on_disk == sorted(e["name"] for e in manifest["files"])

    def test_the_page_loads_collections_by_classic_script_and_requirements_on_demand(
            self, monkeypatch, tmp_path):
        from dashboard import data_files

        html = _embed_to(monkeypatch, tmp_path).read_text()
        manifest = data_files.page_manifest(html)
        main_script = html.index('<script>\n"use strict";')
        for e in manifest["files"]:
            tag = (f'<script src="data/{e["name"]}" data-mothman-key="{e["key"]}" '
                   f'data-mothman-file="{e["name"]}"></script>')
            if e["kind"] == "collection":
                assert html.count(tag) == 1 and html.index(tag) < main_script
            else:
                assert e["name"] not in html.replace(json.dumps(manifest, separators=(",", ":")), "")
        assert "const COLLECTION_DATA = assembleCollectionData();\n" in html
        assert "let REQUIREMENTS = [];\n" in html and "let PLANS = {items:[], threads:[]};\n" in html

    def test_every_other_const_stays_inline(self, monkeypatch, tmp_path):
        html = _embed_to(monkeypatch, tmp_path).read_text()
        for name in ("HIERARCHY", "BUILD_PROVENANCE", "OUTSTANDING", "FEEDBACK",
                     "SPRINT_DEPENDENCIES", "RELEASE_NOTES", "SCHEDULE_RUNWAY"):
            m = re.search(rf"const {name} = (.*?);\n", html)
            assert m and m.group(1) not in ("null", "[]", "{}"), name

    def test_the_files_carry_the_payloads(self, monkeypatch, tmp_path):
        from dashboard import data_files

        page = _embed_to(monkeypatch, tmp_path)
        got = data_files.read_page(page.read_text(), page.parent)
        assert got.problems == []
        assert got.collections == edd.collection_data()
        assert got.requirements == edd.parse_requirements(edd.REQUIREMENTS_YAML)
        assert got.plans == edd.parse_plans(edd.PLANS_DIR)

    def test_files_are_written_before_the_page_and_stale_ones_pruned_after(self, monkeypatch, tmp_path):
        from dashboard import data_files

        data = tmp_path / "data"
        data.mkdir()
        (data / "collection-gone.0123456789ab.js").write_text("stale")
        (tmp_path / "beside.txt").write_text("not ours")
        out_html = tmp_path / "out.html"
        seen = {}
        real_write, real_prune = data_files.write, data_files.prune

        def write(files, data_dir):
            seen["page_existed_at_write"] = out_html.exists()
            return real_write(files, data_dir)

        def prune(data_dir, keep):
            seen["page_existed_at_prune"] = out_html.exists()
            return real_prune(data_dir, keep)

        monkeypatch.setattr(data_files, "write", write)
        monkeypatch.setattr(data_files, "prune", prune)
        _embed_to(monkeypatch, tmp_path)
        assert seen == {"page_existed_at_write": False, "page_existed_at_prune": True}
        assert not (data / "collection-gone.0123456789ab.js").exists()
        assert (tmp_path / "beside.txt").exists()

    def test_two_builds_write_the_same_names_and_bytes(self, monkeypatch, tmp_path):
        first = tmp_path / "one"
        second = tmp_path / "two"
        first.mkdir()
        second.mkdir()
        _embed_to(monkeypatch, first)
        _embed_to(monkeypatch, second)
        read = lambda d: {p.name: p.read_bytes() for p in (d / "data").iterdir()}  # noqa: E731
        assert read(first) and read(first) == read(second)


def test_every_build_prints_each_files_size_and_warns_at_the_budget(monkeypatch, tmp_path, capsys):
    """REQ-DASH-293 criteria 1, 2 and 4, REQ-PIPE-255 criterion 26: a payload
    over the budget is written as parts within it, each named in the
    page's list in order, and every file's size is printed."""
    from dashboard import data_files

    monkeypatch.setattr(data_files, "BUDGET_BYTES", 300 * 1024)
    page = _embed_to(monkeypatch, tmp_path)
    out = capsys.readouterr().out
    manifest = data_files.page_manifest(page.read_text())
    parted = [e for e in manifest["files"] if e["parts"] > 1]
    assert parted, "the Requirements and Plans payload is several MiB, so it must be in parts here"
    for e in manifest["files"]:
        assert e["bytes"] <= 300 * 1024
        assert f"{e['name']}: " in out
    assert f"{page.name}: " in out
    key = parted[0]["key"]
    assert [e["part"] for e in manifest["files"] if e["key"] == key] == \
        list(range(1, parted[0]["parts"] + 1))
    got = data_files.read_page(page.read_text(), page.parent)
    assert got.problems == [] and got.requirements == edd.parse_requirements(edd.REQUIREMENTS_YAML)
    # The page itself is far over a 300 KiB budget, so it is the one warned about.
    assert re.search(rf"WARNING: {re.escape(page.name)} is .* budget", out), out[-2000:]


class TestABuildUnderAnOutDir:
    """REQ-TEST-281: `--out-dir` sends a whole build to a directory of its own,
    reading the reports an earlier step wrote there and writing nothing in the
    real tree."""

    def test_the_page_its_files_and_its_assets_land_in_the_out_dir(self, monkeypatch, tmp_path):
        from qa_tools.common import build_output

        real_page = tmp_path / "real" / "qa-reporting-dashboard.html"
        monkeypatch.setattr(edd, "DASHBOARD_HTML", real_page)
        out = tmp_path / "build"
        (out / "reports").mkdir(parents=True)
        (out / "reports" / "open_tickets.json").write_text(json.dumps([{
            "number": 7, "title": "red", "url": "https://github.com/o/r/issues/7",
            "labels": [{"name": "qa-ticket"}, {"name": "dataset:birth-registrations"}],
            "updatedAt": "2026-10-24T00:00:00Z"}]))
        monkeypatch.setenv(build_output.OUT_DIR_ENV, str(out))

        edd.embed()

        page = out / "qa-reporting-dashboard.html"
        assert page.is_file() and not real_page.exists()
        assert any((out / "data").iterdir())
        for name in ("fonts", "vendor"):
            shipped = sorted(p.name for p in (Path(edd.ROOT) / "dashboard" / name).iterdir())
            assert shipped, name
            assert sorted(p.name for p in (out / name).iterdir()) == shipped, name
        status = json.loads(re.search(r"const TICKET_STATUS = (.*?);\n", page.read_text()).group(1))
        assert status["birth-registrations"]["number"] == 7

    def test_every_reports_path_of_the_chain_is_the_out_dirs(self, monkeypatch, tmp_path):
        from pipeline import build_dashboard_data as bdd
        from qa_tools import collections
        from qa_tools.common import build_output
        from qa_tools.tools import results_history

        monkeypatch.setenv(build_output.OUT_DIR_ENV, str(tmp_path))
        everything = collections.all_collections()
        assert everything
        for c in everything:
            assert results_history.results_path(c.id) == str(tmp_path / "reports" / c.results_file)
            assert bdd.results_path(c.id) == str(tmp_path / "reports" / c.results_file)
            assert bdd.out_path(c.id) == str(tmp_path / "reports" / c.dashboard_file)
