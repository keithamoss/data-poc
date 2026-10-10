"""The pipeline refuses a dataset whose judged past changed without a
declared correction (REQ-PIPE-173).

Recorded verdicts come from real filings against the real cp-clients
agreement (2023-Q3 dated 2023-08-01, due 09:00 Perth, 8h grace); the
configuration is then changed in a copy and compared.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest
import yaml

import filing_support
from qa_tools.common import (agreement, agreement_drift, agreement_freeze, asset_time,
                             assignment, qa_store, supply_db)

PERTH = timezone(timedelta(hours=8))
DATASET = "cp-clients"
RECEIVED = datetime(2023, 8, 1, 12, tzinfo=PERTH)


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-agreement-drift") as c:
        qa_store.ensure_schema(c)
        c.execute(f'TRUNCATE "{qa_store.SCHEMA}".filing CASCADE')
        filing_support.file(assignment.Assignment(
            dataset_id=DATASET, supply_id="drift-s", slot="2023-Q3",
            branch=assignment.OPEN_UNFILLED, considered=("2023-Q3",), received_at=RECEIVED))
        yield c


def _docs():
    cal = copy.deepcopy(yaml.safe_load(agreement.CALENDAR_YAML.read_text()))
    asset = copy.deepcopy(yaml.safe_load(asset_time.DATA_ASSET_YAML.read_text()))
    return cal, asset


def _clients(cal):
    entry = next(d for d in cal["datasets"] if d["id"] == DATASET)
    entry["participation"]["versions"] = copy.deepcopy(entry["participation"]["versions"])
    return entry


def _refusal(conn, cal, asset):
    return agreement_drift.refusal_for(conn, DATASET, cal_doc=cal, asset_doc=asset)


class TestWhatIsCompared:
    """Criterion 1."""

    def test_the_agreement_that_judged_it_refuses_nothing(self, conn):
        assert _refusal(conn, *_docs()) is None

    def test_an_appended_future_date_refuses_nothing(self, conn):
        cal, asset = _docs()
        q = next(c for c in cal["calendars"] if c["name"] == "quarterly")
        q["versions"][-1]["dates"].append({"period": "2028-Q1", "date": "2028-02-01"})
        assert _refusal(conn, cal, asset) is None


class TestAnUndeclaredChangeIsRefused:
    """Criteria 2 and 5."""

    def test_a_changed_grace_names_the_item_and_both_values(self, conn):
        cal, asset = _docs()
        _clients(cal)["participation"]["versions"][0]["grace"] = "1h"
        found = _refusal(conn, cal, asset)
        assert found is not None
        text = found.message()
        assert "grace_seconds was 28800, is now 3600" in text
        assert "2023-Q3" in text
        assert "restore the recorded value" in text and "declare the change" in text
        assert "configuration problem on our side" in text

    def test_a_moved_date_is_refused(self, conn):
        cal, asset = _docs()
        q = next(c for c in cal["calendars"] if c["name"] == "quarterly")
        for d in q["versions"][-1]["dates"]:
            if d["period"] == "2023-Q3":
                d["date"] = "2023-07-25"
        found = _refusal(conn, cal, asset)
        assert "period_date was '2023-08-01', is now '2023-07-25'" in found.message()

    def test_a_changed_timezone_is_refused_too(self, conn, monkeypatch):
        cal, asset = _docs()
        asset["timezone"]["versions"][0]["zone"] = "Australia/Sydney"
        monkeypatch.setattr(asset_time, "timezone_versions",
                            lambda: asset_time.parse_timezone_versions(asset))
        found = _refusal(conn, cal, asset)
        assert "timezone was 'Australia/Perth', is now 'Australia/Sydney'" in found.message()


class TestADeclaredCorrectionAccountsForIt:
    """Criterion 2's other half, and REQ-PIPE-170 criterion 22: a merged
    correction awaiting the asset manager refuses nothing."""

    def test_a_correction_naming_the_version_with_its_new_value(self, conn):
        cal, asset = _docs()
        entry = _clients(cal)
        entry["participation"]["versions"][0]["grace"] = "1h"
        key = "dataset cp-clients participation 2023-01-01"
        now = agreement_freeze.flatten(cal, asset)[key].value
        entry["corrections"] = [{"change_reference": "CAB-1", "date": "2026-10-11",
                                 "author": "a test", "approver": "keithamoss",
                                 "reason": "grace was agreed as one hour",
                                 "changes": [{"item": key, "old": None, "new": now}]}]
        assert _refusal(conn, cal, asset) is None

    def test_a_correction_to_something_else_does_not(self, conn):
        cal, asset = _docs()
        entry = _clients(cal)
        entry["participation"]["versions"][0]["grace"] = "1h"
        entry["corrections"] = [{"change_reference": "CAB-1", "date": "2026-10-11",
                                 "author": "a test", "approver": "keithamoss", "reason": "r",
                                 "changes": [{"item": "calendar quarterly period 2027-Q1",
                                              "old": "2027-02-01", "new": "2027-02-02"}]}]
        assert _refusal(conn, cal, asset) is not None


class TestOneDatasetNeverStopsAnother:
    """Criterion 3, NFR 1."""

    def test_only_the_changed_dataset_is_refused(self, conn, monkeypatch):
        cal, asset = _docs()
        _clients(cal)["participation"]["versions"][0]["grace"] = "1h"
        monkeypatch.setattr(agreement_drift, "_load_docs", lambda: (cal, asset))
        found = agreement_drift.refusals(conn, ["cp-clients", "cp-carers"])
        assert set(found) == {"cp-clients"}
        assert "1 dataset refused" in agreement_drift.pass_line(found)


class TestTheRemedy:
    def test_a_synthetic_asset_names_regenerating(self, conn):
        """Criterion 8."""
        cal, asset = _docs()
        asset["synthetic"] = True
        _clients(cal)["participation"]["versions"][0]["grace"] = "1h"
        assert "mothman env reset-synthetic" in _refusal(conn, cal, asset).remedy

    def test_a_real_asset_does_not(self, conn):
        cal, asset = _docs()
        asset["synthetic"] = False
        _clients(cal)["participation"]["versions"][0]["grace"] = "1h"
        assert "reset-synthetic" not in _refusal(conn, cal, asset).remedy


def test_it_reads_recorded_metadata_and_configuration_only():
    """Criterion 6."""
    import inspect

    source = inspect.getsource(agreement_drift)
    for forbidden in ("staging", "period_tables", "supply_rows", "SELECT"):
        assert forbidden not in source


class TestTheCommandAndThePass:
    """Criteria 2-4 through the routes a person and a scheduler see."""

    def test_check_agreement_names_the_change_and_exits_1(self, conn, monkeypatch):
        from click.testing import CliRunner

        from cli import schedule as schedule_cli
        cal, asset = _docs()
        _clients(cal)["participation"]["versions"][0]["grace"] = "1h"
        monkeypatch.setattr(agreement_drift, "_load_docs", lambda: (cal, asset))
        got = CliRunner().invoke(schedule_cli.schedule_group,
                                 ["check-agreement", "--dataset", DATASET])
        assert got.exit_code == 1
        assert "grace_seconds was 28800" in got.output

    def test_nothing_refused_exits_0(self, conn):
        from click.testing import CliRunner

        from cli import schedule as schedule_cli
        got = CliRunner().invoke(schedule_cli.schedule_group,
                                 ["check-agreement", "--dataset", DATASET])
        assert got.exit_code == 0, got.output

    def test_a_refused_datasets_new_supply_is_held_and_others_file(self, conn, monkeypatch):
        """Criteria 2 and 3: held at filing, naming the refusal; the
        dataset beside it in the same arrival files as usual."""
        from types import SimpleNamespace

        from qa_tools.common import filing, supply_holds
        cal, asset = _docs()
        _clients(cal)["participation"]["versions"][0]["grace"] = "1h"
        monkeypatch.setattr(agreement_drift, "_load_docs", lambda: (cal, asset))
        at = datetime(2023, 11, 1, 10, tzinfo=PERTH)
        filing_support.ensure_delivery("pytest-drift", "cp-clients", at)
        filing_support.ensure_delivery("pytest-drift", "cp-carers", at, "cp-carers.csv")
        arrival = SimpleNamespace(
            files_by_dataset={"cp-clients": ["a"], "cp-carers": ["b"]}, received_at=at,
            delivery_name="pytest-drift", run_id="drift-run")
        monkeypatch.setattr(filing, "_supply_id_for",
                            lambda arr, ds: f"{ds}@drift")
        written = {a.dataset_id: a for a in filing.file_arrivals([arrival])}
        assert written["cp-clients"].is_held and written["cp-clients"].agreement_refused
        assert not written["cp-carers"].is_held
        held = [h for h in supply_holds.outstanding(conn) if h.supply_id == "cp-clients@drift"]
        assert held and held[0].agreement_refused
        assert "grace_seconds was 28800" in held[0].describe()

    def test_once_restored_the_held_supply_is_filed_by_the_rule(self, conn, monkeypatch):
        from types import SimpleNamespace

        from qa_tools.common import filing, supply_holds
        cal, asset = _docs()
        _clients(cal)["participation"]["versions"][0]["grace"] = "1h"
        monkeypatch.setattr(agreement_drift, "_load_docs", lambda: (cal, asset))
        at = datetime(2023, 11, 1, 10, tzinfo=PERTH)
        filing_support.ensure_delivery("pytest-drift2", "cp-clients", at)
        arrival = SimpleNamespace(files_by_dataset={"cp-clients": ["a"]}, received_at=at,
                                  delivery_name="pytest-drift2", run_id="drift-run-2")
        monkeypatch.setattr(filing, "_supply_id_for", lambda arr, ds: f"{ds}@drift2")
        filing.file_arrivals([arrival])
        monkeypatch.setattr(agreement_drift, "_load_docs", _docs)   # restored
        done = agreement_drift.refile_cleared(say=lambda *_: None)
        assert ("cp-clients", "cp-clients@drift2", "2023-Q4") in done
        assert not [h for h in supply_holds.outstanding(conn)
                    if h.supply_id == "cp-clients@drift2"]


def test_the_pass_summary_states_a_refusal_and_a_cleared_refile(capsys):
    """Criterion 4: the pass's own summary says which datasets were refused."""
    from cli import pipeline
    from qa_tools.common import processing_pass

    pipeline._say_pass(processing_pass.PassReport(
        refused=["cp-clients"], refiled_cleared=[("cp-carers", "s", "2030-Q1")]))
    out = capsys.readouterr().out
    assert "REFUSED 1 dataset(s)" in out and "cp-clients" in out
    assert "held while their dataset was refused were filed" in out


class TestCriticFindingsOn173:
    """delivery-critic on REQ-PIPE-173 (534a398), post-build-review #146.
    Each failed before its fix."""

    def _grace_one_hour(self):
        cal, asset = _docs()
        _clients(cal)["participation"]["versions"][0]["grace"] = "1h"
        return cal, asset

    def _correction(self, item, new, date="2026-10-11"):
        return {"change_reference": "OLD-1", "date": date, "author": "a test",
                "approver": "keithamoss", "reason": "r",
                "changes": [{"item": item, "old": None, "new": new}]}

    def test_1_an_old_timezone_correction_does_not_silence_a_grace_change(self, conn):
        cal, asset = self._grace_one_hour()
        asset["timezone"]["corrections"] = [
            self._correction("timezone version 1970-01-01", "Australia/Perth")]
        assert _refusal(conn, cal, asset) is not None

    def test_1_a_membership_correction_does_not_either(self, conn):
        cal, asset = self._grace_one_hour()
        _clients(cal)["corrections"] = [self._correction("dataset cp-clients calendar",
                                                         "quarterly")]
        assert _refusal(conn, cal, asset) is not None

    def test_1_a_correction_declared_before_the_verdict_accounts_for_nothing(self, conn):
        """Corrections are append-only: one in force when the verdict was
        recorded was part of the terms it was judged under."""
        cal, asset = self._grace_one_hour()
        key = "dataset cp-clients participation 2023-01-01"
        now = agreement_freeze.flatten(cal, asset)[key].value
        _clients(cal)["corrections"] = [self._correction(key, now, date="2020-01-01")]
        assert _refusal(conn, cal, asset) is not None

    def test_4_a_supply_the_rule_would_hold_anyway_keeps_its_own_hold(self, conn, monkeypatch):
        """Past the schedule's end: held as schedule-ended, which says how it
        is fixed - not as refused, which would never clear."""
        from types import SimpleNamespace

        from qa_tools.common import filing, supply_holds
        cal, asset = self._grace_one_hour()
        monkeypatch.setattr(agreement_drift, "_load_docs", lambda: (cal, asset))
        at = datetime(2035, 3, 1, 10, tzinfo=PERTH)
        filing_support.ensure_delivery("pytest-drift-2035", "cp-clients", at)
        arrival = SimpleNamespace(files_by_dataset={"cp-clients": ["a"]}, received_at=at,
                                  delivery_name="pytest-drift-2035", run_id="drift-2035")
        monkeypatch.setattr(filing, "_supply_id_for", lambda arr, ds: f"{ds}@drift2035")
        [decided] = filing.file_arrivals([arrival])
        assert decided.is_held and not decided.agreement_refused
        [held] = [h for h in supply_holds.outstanding(conn)
                  if h.supply_id == "cp-clients@drift2035"]
        assert held.schedule_ended and not held.agreement_refused

    def test_9_a_dataset_that_cannot_be_evaluated_is_said_not_skipped(self, conn, monkeypatch):
        cal, asset = self._grace_one_hour()
        monkeypatch.setattr(agreement_drift, "_load_docs", lambda: (cal, asset))
        monkeypatch.setattr(agreement_drift, "refusal_for",
                            lambda *a, **k: (_ for _ in ()).throw(ValueError("bad grace")))
        errors = []
        assert agreement_drift.refusals(conn, ["cp-clients"], errors=errors) == {}
        assert errors and "bad grace" in str(errors[0][1])

    def test_9_check_agreement_refuses_an_unknown_dataset(self):
        from click.testing import CliRunner

        from cli import schedule as schedule_cli
        got = CliRunner().invoke(schedule_cli.schedule_group,
                                 ["check-agreement", "--dataset", "no-such-dataset"])
        assert got.exit_code != 0 and "no-such-dataset" in got.output

    def test_10_a_missing_slot_reads_plainly(self, conn):
        cal, asset = _docs()
        q = next(c for c in cal["calendars"] if c["name"] == "quarterly")
        q["versions"][-1]["dates"] = [d for d in q["versions"][-1]["dates"]
                                      if d["period"] != "2023-Q3"]
        text = _refusal(conn, cal, asset).message()
        assert "2023-Q3: no longer a period of its schedule (it was dated 2023-08-01)" in text

    def test_10_a_refusal_only_pass_does_not_say_a_result_is_red(self, capsys):
        from cli import pipeline
        from qa_tools.common import processing_pass

        report = processing_pass.PassReport(refused=["cp-clients"])
        pipeline._say_pass(report)
        assert "recorded result is red" not in capsys.readouterr().out
        assert report.exit_status == processing_pass.EXIT_RED
