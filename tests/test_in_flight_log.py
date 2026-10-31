"""qa_tools/common/in_flight_log.py - what a run observed in flight
(REQ-PIPE-057 criteria 5 and 7).

The subject of the record is the RUN, not the delivery, and that is
what made the problem solvable rather than a detail of phrasing:
committing "delivery X is in flight" is a permanent record about
something we have not accepted, while "the run at 14:32 observed these"
is a record about something that genuinely happened.
"""
from __future__ import annotations

import json

from qa_tools.common import delivery, in_flight_log


def _entry(name, files):
    return delivery.InFlight(name=name, files=tuple(files))


class TestWhatGetsCommitted:
    def test_the_record_is_about_the_run_and_names_the_files(self, tmp_path):
        path = in_flight_log.record(
            "civil-registration", "2026-09-25T14:32:00+08:00",
            [_entry("uploading", ["a.csv", "b.csv"])], observations_dir=tmp_path)
        record = json.loads(path.read_text())
        assert record["observed_at"] == "2026-09-25T14:32:00+08:00"
        assert record["observed_by"] == "civil-registration"
        assert record["in_flight"] == [{"delivery": "uploading", "files": ["a.csv", "b.csv"]}]

    def test_filenames_not_a_count(self, tmp_path):
        """A count answers "is anything in flight"; the question worth
        asking is "is anything STUCK", and a list going 2, 4, 6 across
        runs reads as an upload progressing."""
        path = in_flight_log.record("c", "t", [_entry("d", ["one.csv"])],
                                     observations_dir=tmp_path)
        assert "one.csv" in path.read_text()

    def test_nothing_in_flight_writes_nothing(self, tmp_path):
        """"The run saw nothing" is the ordinary state of most runs, and
        a file per run saying so would be churn carrying no signal."""
        assert in_flight_log.record("c", "t", [], observations_dir=tmp_path) is None
        assert list(tmp_path.glob("*.json")) == []

    def test_a_later_run_does_not_overwrite_an_earlier_observation(self, tmp_path):
        """These records CHURN - an in-flight delivery's file list
        legitimately differs run to run, and that difference IS the
        signal. Collapsing them would erase it."""
        in_flight_log.record("c", "2026-09-25T10:00:00+08:00",
                              [_entry("d", ["one.csv"])], observations_dir=tmp_path)
        in_flight_log.record("c", "2026-09-25T11:00:00+08:00",
                              [_entry("d", ["one.csv", "two.csv"])], observations_dir=tmp_path)
        seen = in_flight_log.observations(tmp_path)
        assert [len(r["in_flight"][0]["files"]) for r in seen] == [2, 1]

    def test_a_run_timestamp_becomes_a_safe_filename(self, tmp_path):
        path = in_flight_log.record("civil-registration", "2026-09-25T14:32:00+08:00",
                                     [_entry("d", [])], observations_dir=tmp_path)
        assert ":" not in path.name and "+" not in path.name


class TestReadingThemBack:
    def test_newest_first(self, tmp_path):
        for hour in ("09", "11", "10"):
            in_flight_log.record("c", f"2026-09-25T{hour}:00:00+08:00",
                                  [_entry("d", [])], observations_dir=tmp_path)
        seen = in_flight_log.observations(tmp_path)
        assert [r["observed_at"][11:13] for r in seen] == ["11", "10", "09"]

    def test_no_observations_at_all_is_not_an_error(self, tmp_path):
        assert in_flight_log.observations(tmp_path / "nothing-here") == []

    def test_a_malformed_record_is_skipped_rather_than_fatal(self, tmp_path):
        """This is a report ABOUT something odd; one that cannot be
        rendered should not take the page down with it."""
        (tmp_path / "broken.json").write_text("{not json")
        in_flight_log.record("c", "2026-09-25T10:00:00+08:00", [_entry("d", [])],
                              observations_dir=tmp_path)
        assert len(in_flight_log.observations(tmp_path)) == 1
