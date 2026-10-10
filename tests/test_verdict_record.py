"""An arrival verdict is a recorded fact naming the agreement that judged
it, and a correction re-judges it visibly (REQ-PIPE-168).

Against the real cp-clients agreement: 2023-Q3 is dated 2023-08-01, due
09:00 Perth with 8h grace and a 14-day claim window. A supply received at
12:00 that day is ON TIME; a correction cutting grace to one hour makes
it LATE - which is the re-judgement these tests drive.
"""
from __future__ import annotations

import copy
import inspect
from datetime import datetime, timedelta, timezone

import pytest
import yaml

import filing_support
from qa_tools.common import agreement, assignment, filing, qa_store, supply_db, verdict
from qa_tools.common import arrival_classification as classify_mod

PERTH = timezone(timedelta(hours=8))
DATASET = "cp-clients"
SLOT = "2023-Q3"
RECEIVED = datetime(2023, 8, 1, 12, tzinfo=PERTH)


@pytest.fixture
def clean(supply_dsn):
    with supply_db.connect(label="test-verdict-record") as conn:
        qa_store.ensure_schema(conn)
        conn.execute(f'TRUNCATE "{qa_store.SCHEMA}".filing CASCADE')
        yield conn


def _file(slot=SLOT, supply_id="s", received_at=RECEIVED):
    return filing_support.file(assignment.Assignment(
        dataset_id=DATASET, supply_id=supply_id, slot=slot,
        branch=assignment.OPEN_UNFILLED, considered=(slot,), received_at=received_at))


def _agreement(mutate):
    """The committed agreement with one change made to a copy."""
    doc = yaml.safe_load(agreement.CALENDAR_YAML.read_text())
    doc = copy.deepcopy(doc)
    mutate(doc)
    return agreement.from_doc(doc)


def _cp_clients(doc):
    entry = next(d for d in doc["datasets"] if d["id"] == DATASET)
    # The YAML anchor shares one dict between datasets; give this one its own.
    entry["participation"]["versions"] = copy.deepcopy(entry["participation"]["versions"])
    return entry["participation"]["versions"][0]


def _grace_one_hour(doc):
    _cp_clients(doc)["grace"] = "1h"


def _append_a_future_date(doc):
    quarterly = next(c for c in doc["calendars"] if c["name"] == "quarterly")
    quarterly["versions"][-1]["dates"].append({"period": "2028-Q1", "date": "2028-02-01"})


class TestRecordedWithItsInputs:
    """Criterion 1."""

    def test_a_filing_records_a_verdict_with_the_slots_resolved_inputs(self, clean):
        _file()
        got = verdict.current(clean, DATASET, "s")
        assert got["classification"] == classify_mod.ON_TIME
        assert got["inputs"] == {
            "period_date": "2023-08-01", "due_date": "2023-08-01", "expected_time": "09:00",
            "days_before": 0, "grace_seconds": 8 * 3600,
            "claim_window_seconds": 14 * 86400, "timezone": "Australia/Perth",
            "due_at": "2023-08-01T09:00:00+08:00", "late_after": "2023-08-01T17:00:00+08:00",
            "claim_opens_at": "2023-07-18T09:00:00+08:00"}
        assert got["fingerprint"]

    def test_never_the_closing_instant_nor_the_calendars_dates(self, clean):
        _file()
        inputs = verdict.current(clean, DATASET, "s")["inputs"]
        assert "closes_at" not in inputs
        assert not {"dates", "periods"} & set(inputs)

    def test_appending_a_future_date_leaves_the_fingerprint_alone(self):
        """B3: an append is the commonest legitimate change, and a
        fingerprint it moved would make REQ-PIPE-173 refuse every dataset."""
        from datetime import date

        before = verdict.resolved(DATASET, date(2023, 8, 1))[1]
        after = verdict.resolved(DATASET, date(2023, 8, 1),
                                 _agreement(_append_a_future_date))[1]
        assert before == after

    def test_changing_the_version_that_judged_it_changes_the_fingerprint(self):
        from datetime import date

        before = verdict.resolved(DATASET, date(2023, 8, 1))[1]
        after = verdict.resolved(DATASET, date(2023, 8, 1), _agreement(_grace_one_hour))[1]
        assert before != after

    def test_a_held_supply_records_unfiled_with_no_inputs(self, clean):
        filing_support.file(assignment.Assignment(
            dataset_id=DATASET, supply_id="held", slot=None, branch=assignment.HELD,
            considered=(), received_at=RECEIVED))
        got = verdict.current(clean, DATASET, "held")
        assert got["classification"] == classify_mod.UNFILED
        assert got["inputs"] is None and got["fingerprint"] is None


class TestAppendOnly:
    """Criterion 2."""

    @pytest.mark.parametrize("statement", [
        'UPDATE "{s}".verdict SET classification = \'late\'',
        'DELETE FROM "{s}".verdict'])
    def test_a_recorded_verdict_cannot_be_changed_or_deleted(self, clean, statement):
        _file()
        with pytest.raises(Exception, match="append-only"):
            clean.execute(statement.format(s=qa_store.SCHEMA))


def _refile(to_slot):
    with supply_db.connect(label="test-verdict-refile") as conn:
        return filing.refile(conn, DATASET, "s", to_slot, decision_id=1)


class TestTheNewestForTheCurrentFiling:
    """Criterion 6."""

    def test_a_refile_brings_its_own_verdict_and_keeps_the_old_one(self, clean):
        _file()
        _refile("2023-Q2")
        assert verdict.current(clean, DATASET, "s")["classification"] == classify_mod.LATE
        assert filing.filing_for(DATASET, "s")["classification"] == classify_mod.LATE
        assert [v["classification"] for v in verdict.history(clean, DATASET, "s")] == [
            classify_mod.ON_TIME, classify_mod.LATE]


class TestReJudgement:
    """Criteria 4, 7 and 8, and NFR 2."""

    def test_nothing_to_rejudge_under_the_agreement_that_judged_it(self, clean):
        _file()
        assert verdict.rejudged(clean, DATASET) == []

    def test_nor_after_an_appended_date(self, clean):
        _file()
        assert verdict.rejudged(clean, DATASET, _agreement(_append_a_future_date)) == []

    def test_a_correction_to_the_version_rejudges_the_supply(self, clean):
        _file()
        [found] = verdict.rejudged(clean, DATASET, _agreement(_grace_one_hour))
        assert found.supply_id == "s" and found.slot == SLOT
        assert found.old["classification"] == classify_mod.ON_TIME
        assert found.new.classification == classify_mod.LATE
        assert found.new.inputs["grace_seconds"] == 3600

    def test_it_is_computed_not_recorded(self, clean):
        _file()
        verdict.rejudged(clean, DATASET, _agreement(_grace_one_hour))
        assert len(verdict.history(clean, DATASET, "s")) == 1

    def test_recording_it_names_the_correction_and_what_it_replaced(self, clean):
        _file()
        before = verdict.current(clean, DATASET, "s")
        [found] = verdict.rejudged(clean, DATASET, _agreement(_grace_one_hour))
        verdict.record_rejudgement(clean, found, correction_ref="CHG-1",
                                   correction_changelog="grace cut to 1h",
                                   recorded_at=datetime(2026, 10, 11, tzinfo=PERTH))
        now = verdict.current(clean, DATASET, "s")
        assert now["classification"] == classify_mod.LATE
        assert (now["correction_ref"], now["correction_changelog"], now["supersedes"]) == (
            "CHG-1", "grace cut to 1h", before["id"])
        # every reader of "the" classification sees it (criterion 6)
        assert filing.filing_for(DATASET, "s")["classification"] == classify_mod.LATE
        # and the earlier verdict is still there to read
        assert [v["classification"] for v in verdict.history(clean, DATASET, "s")] == [
            classify_mod.ON_TIME, classify_mod.LATE]

    def test_a_rejudgement_moves_nothing(self, clean):
        """Criterion 7: the same filing, the same slot, no new filing row."""
        _file()
        before = filing.filing_for(DATASET, "s")
        [found] = verdict.rejudged(clean, DATASET, _agreement(_grace_one_hour))
        verdict.record_rejudgement(clean, found, correction_ref="CHG-1",
                                   correction_changelog="c", recorded_at=RECEIVED)
        after = filing.filing_for(DATASET, "s")
        assert {k: v for k, v in after.items() if k != "classification"} == \
            {k: v for k, v in before.items() if k != "classification"}
        rows = clean.execute(f'SELECT count(*) FROM "{qa_store.SCHEMA}".filing').fetchall()
        assert rows == [(1,)]

    def test_a_rejudgement_with_no_correction_named_is_refused(self, clean):
        _file()
        [found] = verdict.rejudged(clean, DATASET, _agreement(_grace_one_hour))
        with pytest.raises(ValueError, match="change reference"):
            verdict.record_rejudgement(clean, found, correction_ref="",
                                       correction_changelog="c", recorded_at=RECEIVED)

    def test_the_database_refuses_a_half_named_rejudgement(self, clean):
        _file()
        v = verdict.current(clean, DATASET, "s")
        with pytest.raises(Exception, match="check"):
            verdict.record(clean, v["filing_id"], DATASET, "s",
                           verdict.Judged("late", None, None), recorded_at=RECEIVED,
                           correction_ref="CHG-1", correction_changelog="c")

    def test_one_computed_against_a_verdict_since_replaced_is_refused(self, clean):
        _file()
        [found] = verdict.rejudged(clean, DATASET, _agreement(_grace_one_hour))
        _refile("2023-Q2")
        with pytest.raises(ValueError, match="compute it again"):
            verdict.record_rejudgement(clean, found, correction_ref="CHG-1",
                                       correction_changelog="c", recorded_at=RECEIVED)

    def test_the_configuration_is_resolved_once_per_period_not_per_supply(self, clean,
                                                                          monkeypatch):
        """NFR 2: years of daily history must not mean one resolution per
        supply."""
        for i in range(5):
            _file(supply_id=f"s{i}", received_at=RECEIVED + timedelta(minutes=i))
        calls = []
        real = verdict.resolved
        monkeypatch.setattr(verdict, "resolved",
                            lambda *a, **k: calls.append(a[1]) or real(*a, **k))
        assert len(verdict.rejudged(clean, DATASET, _agreement(_grace_one_hour))) == 5
        assert len(calls) == 1

    def test_it_reads_recorded_metadata_and_configuration_only(self):
        """Criterion 8: never supply rows."""
        source = inspect.getsource(verdict.rejudged)
        for table in ("filing_current", "supply_receipt", "{TABLE}"):
            assert table in source
        for forbidden in ("staging", "period_tables", "rows_of", "supply_rows"):
            assert forbidden not in source


def _move_q3_to_july_25(doc):
    quarterly = next(c for c in doc["calendars"] if c["name"] == "quarterly")
    for version in quarterly["versions"]:
        for d in version.get("dates") or []:
            if d["period"] == "2023-Q3":
                d["date"] = "2023-07-25"


def _grace_seven_hours(doc):
    _cp_clients(doc)["grace"] = "7h"


class TestCriticFindingsOn168:
    """delivery-critic on REQ-PIPE-168 (51df202), post-build-review #143.
    Each failed before its fix."""

    def test_H1_a_corrected_date_is_rejudged(self, clean):
        """A correction moving 2023-Q3 to 2023-07-25 makes the 12:00 supply
        late (late after 07-25 17:00) - it was skipped, because the old
        date resolved to the same fingerprint."""
        _file()
        [found] = verdict.rejudged(clean, DATASET, _agreement(_move_q3_to_july_25))
        assert found.new.classification == classify_mod.LATE
        assert found.new.inputs["period_date"] == "2023-07-25"

    def test_M1_only_a_changed_verdict_is_listed(self, clean):
        """Grace 8h -> 7h leaves the 12:00 supply on time: nothing changes."""
        _file()
        assert verdict.rejudged(clean, DATASET, _agreement(_grace_seven_hours)) == []

    def test_M3_a_second_verdict_must_name_a_correction(self, clean):
        _file()
        v = verdict.current(clean, DATASET, "s")
        with pytest.raises(Exception, match="verdict_first_once|duplicate key"):
            verdict.record(clean, v["filing_id"], DATASET, "s",
                           verdict.Judged("late", None, None), recorded_at=RECEIVED)

    def test_M3_a_verdict_names_its_own_filings_supply(self, clean):
        _file()
        v = verdict.current(clean, DATASET, "s")
        with pytest.raises(Exception, match="does not match its filing"):
            verdict.record(clean, v["filing_id"], "birth-registrations", "zzz",
                           verdict.Judged("late", None, None), recorded_at=RECEIVED,
                           correction_ref="C", correction_changelog="c", supersedes=v["id"])

    def test_M3_it_supersedes_a_verdict_of_the_same_filing_once(self, clean):
        _file(supply_id="a")
        _file(supply_id="b", received_at=RECEIVED + timedelta(minutes=1))
        a, b = (verdict.current(clean, DATASET, s) for s in ("a", "b"))
        with pytest.raises(Exception, match="does not match its filing"):
            verdict.record(clean, a["filing_id"], DATASET, "a",
                           verdict.Judged("late", None, None), recorded_at=RECEIVED,
                           correction_ref="C", correction_changelog="c", supersedes=b["id"])
        verdict.record(clean, a["filing_id"], DATASET, "a", verdict.Judged("late", None, None),
                       recorded_at=RECEIVED, correction_ref="C", correction_changelog="c",
                       supersedes=a["id"])
        with pytest.raises(Exception, match="verdict_supersedes_once|duplicate key"):
            verdict.record(clean, a["filing_id"], DATASET, "a",
                           verdict.Judged("late", None, None), recorded_at=RECEIVED,
                           correction_ref="D", correction_changelog="d", supersedes=a["id"])

    def test_M3_an_empty_reference_is_refused_by_the_database(self, clean):
        _file()
        v = verdict.current(clean, DATASET, "s")
        with pytest.raises(Exception, match="check"):
            verdict.record(clean, v["filing_id"], DATASET, "s",
                           verdict.Judged("late", None, None), recorded_at=RECEIVED,
                           correction_ref="", correction_changelog="c", supersedes=v["id"])
