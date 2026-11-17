"""REQ-PIPE-378: a date before a calendar's first version raises for every
caller, the cadence check is made per round only, configuration errors are
not swallowed, and a period's round is required.

Each test here was seen failing against the behaviour before it (criterion
21): the fallback to the first calendar version, the check against the
calendar's current version, and DatasetPeriod's optional round.
"""
from __future__ import annotations

import dataclasses
from datetime import date

import pytest

import agreement_split
from asset_model import schedule


def _doc(*versions, participation=None, dataset_extra=None):
    dataset = {"id": "d", "name": "D", "table": "t"}
    if participation is not None:
        dataset["participation"] = participation
    dataset.update(dataset_extra or {})
    return {"data_asset_id": "data-asset-1",
            "calendars": [{"name": "c", "versions": list(versions)}],
            "hierarchy": {"agencies": [{"id": "a", "name": "A", "collections": [
                {"id": "col", "name": "Col", "contract": "c.yaml", "datasets": [dataset]}]}]}}


def _authored(effective_from="2023-01-01", **extra):
    v = {"effective_from": effective_from, "changelog": [f"{effective_from}: v"],
         "claim_window": "14d",
         "dates": [{"period": "2023-Q1", "date": "2023-02-01"},
                   {"period": "2023-Q2", "date": "2023-05-01"}]}
    v.update(extra)
    return v


def _repoint(tmp_path, monkeypatch, doc):
    agreement_split.repoint(monkeypatch, tmp_path, doc, base={})


class TestNoFallbackToTheFirstVersion:
    """Criterion 1: one function answers which calendar version is in force,
    and it raises before the first version; the fallback is gone."""

    def test_the_error_names_the_calendar_the_date_and_the_earliest(self, tmp_path, monkeypatch):
        _repoint(tmp_path, monkeypatch, _doc(_authored()))
        cal = schedule.calendar("c")
        with pytest.raises(schedule.ScheduleConfigError) as raised:
            cal.version_in_force(date(2020, 1, 1))
        said = str(raised.value)
        assert "'c'" in said and "2020-01-01" in said and "2023-01-01" in said, said


class TestTheClaimWindow:
    """Criterion 3: before the calendar's first version, with no participation
    version stating a window, claim_window raises rather than borrowing the
    first version's."""

    def test_before_the_first_version_it_raises(self, tmp_path, monkeypatch):
        _repoint(tmp_path, monkeypatch, _doc(_authored()))
        with pytest.raises(schedule.ScheduleConfigError, match="2023-01-01"):
            schedule.claim_window("d", on=date(2020, 6, 1))

    def test_inside_a_version_it_answers_as_before(self, tmp_path, monkeypatch):
        from datetime import timedelta

        _repoint(tmp_path, monkeypatch, _doc(_authored()))
        assert schedule.claim_window("d", on=date(2023, 3, 1)) == timedelta(days=14)


class TestTheCadenceCheckIsPerRoundOnly:
    """Criterion 12: months are checked against the version in force on each
    round's own date, never against the calendar's current version. A
    calendar authored then switched to a cadence rule must not refuse a
    dataset whose months were named while it was authored."""

    def test_a_later_cadence_version_does_not_refuse_earlier_months(self, tmp_path, monkeypatch):
        later = {"effective_from": "2024-01-01", "changelog": ["2024-01-01: daily"],
                 "claim_window": "4h", "cadence": {"rule": "daily"}}
        doc = _doc(_authored(), later, dataset_extra={"delivery_months": ["February"]})
        _repoint(tmp_path, monkeypatch, doc)
        got = schedule.periods_for_dataset("d", until=date(2023, 12, 31))
        assert [p.period.name for p in got] == ["2023-Q1"]

    def test_an_unbounded_ask_of_a_cadence_rule_still_refuses(self, tmp_path, monkeypatch):
        rule = {"effective_from": "2023-01-01", "changelog": ["2023-01-01: daily"],
                "claim_window": "4h", "cadence": {"rule": "daily"}}
        _repoint(tmp_path, monkeypatch, _doc(rule))
        with pytest.raises(schedule.ScheduleConfigError, match="until"):
            schedule.periods_for_dataset("d")


class TestTheRoundsCadenceCheck:
    """Criterion 4: the per-round months check raises for a round before the
    calendar's first version, rather than judging it by the first."""

    def test_a_round_before_the_first_version_raises(self, tmp_path, monkeypatch):
        doc = _doc(_authored(), dataset_extra={"delivery_months": ["February"]})
        _repoint(tmp_path, monkeypatch, doc)
        with pytest.raises(schedule.ScheduleConfigError, match="2023-01-01"):
            schedule.supplies_in_round("d", date(2020, 2, 1))


class TestAgreementDriftKeys:
    """Criterion 8: no calendar version governed a period before the first,
    so its keys leave out the calendar-version key and keep the period key."""

    def test_no_version_key_before_the_first_version(self, tmp_path, monkeypatch):
        from qa_tools.common import agreement_drift

        _repoint(tmp_path, monkeypatch, _doc(_authored()))
        agr = schedule.agreement_to_read(None)
        keys = agreement_drift._sources("d", "2020-Q1", date(2020, 2, 1), agr, None)
        assert "calendar c period 2020-Q1" in keys, keys
        assert not any(k.startswith("calendar c version") for k in keys), keys

    def test_both_keys_inside_a_version(self, tmp_path, monkeypatch):
        from qa_tools.common import agreement_drift

        _repoint(tmp_path, monkeypatch, _doc(_authored()))
        agr = schedule.agreement_to_read(None)
        keys = agreement_drift._sources("d", "2023-Q1", date(2023, 2, 1), agr, None)
        assert "calendar c version 2023-01-01" in keys and "calendar c period 2023-Q1" in keys


class TestScheduleShowBeforeTheFirstVersion:
    """Criterion 9 (CLI review finding 9): `mothman schedule show` on a date
    before the calendar's first version, where the dataset's participation is
    already in force, exits 0 showing the claim window as stated by no
    calendar version on that date, naming the earliest, with no source date
    and no traceback. (No real dataset reaches this today: each one's
    participation starts on or after its calendar's first version.)"""

    def test_the_real_command(self, tmp_path, monkeypatch):
        from click.testing import CliRunner

        from cli.app import cli

        # A GRACE format_duration can write back (a 0h one has no authored
        # form to show); its participation in force from 1970, before the
        # calendar's first version.
        agreement_split.repoint(monkeypatch, tmp_path, _doc(_authored()),
                                base=agreement_split.participation("d", grace="2h"))
        got = CliRunner().invoke(cli, ["schedule", "show", "--dataset", "d",
                                       "--on", "2020-06-01"])
        out = " ".join(got.output.replace("│", " ").split())
        assert got.exit_code == 0, got.output
        assert "Traceback" not in out, out
        assert "stated by no calendar version on 2020-06-01" in out, out
        assert "2023-01-01" in out, out


class TestAVerdictBeforeTheFirstVersion:
    """Criterion 7: verdict.resolved raises before the calendar's first
    version, and its callers keep their handling - verdict.judge records the
    classification with no inputs and no fingerprint (it never raises)."""

    def test_resolved_raises_naming_the_earliest(self, tmp_path, monkeypatch):
        from qa_tools.common import verdict

        _repoint(tmp_path, monkeypatch, _doc(_authored()))
        with pytest.raises(schedule.ScheduleConfigError, match="2023-01-01"):
            verdict.resolved("d", date(2020, 2, 1))

    def test_judge_records_no_inputs(self, tmp_path, monkeypatch):
        from datetime import datetime, timezone
        from types import SimpleNamespace

        from asset_model import arrival_classification
        from qa_tools.common import verdict

        _repoint(tmp_path, monkeypatch, _doc(_authored()))
        monkeypatch.setattr(arrival_classification, "classify", lambda received, slot: "on-time")
        slot = SimpleNamespace(round_date=date(2020, 2, 1),
                               period=SimpleNamespace(name="2020-Q1"))
        judged = verdict.judge("d", slot, datetime(2020, 2, 1, tzinfo=timezone.utc))
        assert judged == verdict.Judged("on-time", None, None)


class TestALinkageReleaseBeforeTheFirstVersion:
    """Criterion 10: the Linkage Products provider refuses to time a release
    against a borrowed window, naming the release and the date."""

    def test_it_refuses_naming_the_release_and_the_date(self, tmp_path, monkeypatch):
        import collection_modules

        lp = collection_modules.provider_module("linkage-products")
        _repoint(tmp_path, monkeypatch, _doc(_authored()))
        with pytest.raises(lp.CannotGenerate) as refused:
            lp._release_window("d", date(2020, 2, 1), "the 2020-Q1 linkage release")
        said = str(refused.value)
        assert "the 2020-Q1 linkage release" in said and "2020-02-01" in said, said


class TestTheSlotHelpersStopSwallowing:
    """Criteria 13 and 14: slots.is_owed_supplies and slots.period_claimed_at
    raise a ScheduleConfigError rather than answering False or None; a
    schedule not yet agreed keeps its quiet answer ('nothing owed'), and an
    unknown dataset its answer as today. Criterion 15: their callers let it
    stop the step - arrivals.recognise's unexpected-table test is one."""

    @pytest.fixture
    def broken(self, monkeypatch):
        from asset_model import slots

        def refuse(dataset_id, *a, **k):
            raise schedule.ScheduleConfigError(f"calendar for {dataset_id} is broken")
        monkeypatch.setattr(schedule, "calendar_for_dataset", refuse)
        monkeypatch.setattr(slots, "slots_for_dataset", refuse)
        return slots

    def test_is_owed_supplies_raises(self, broken):
        with pytest.raises(schedule.ScheduleConfigError, match="is broken"):
            broken.is_owed_supplies("cp-clients")

    def test_period_claimed_at_raises(self, broken):
        from datetime import datetime, timezone

        with pytest.raises(schedule.ScheduleConfigError, match="is broken"):
            broken.period_claimed_at("cp-clients", datetime(2026, 2, 1, tzinfo=timezone.utc))

    def test_no_calendar_agreed_is_still_nothing_owed(self, monkeypatch):
        from datetime import datetime, timezone

        from asset_model import slots

        def not_agreed(dataset_id, *a, **k):
            raise schedule.NoCalendarAgreed(dataset_id, "never")
        monkeypatch.setattr(schedule, "calendar_for_dataset", not_agreed)
        monkeypatch.setattr(slots, "slots_for_dataset", not_agreed)
        assert slots.is_owed_supplies("cp-clients") is False
        assert slots.period_claimed_at("cp-clients",
                                       datetime(2026, 2, 1, tzinfo=timezone.utc)) is None

    def test_an_unknown_dataset_answers_as_today(self):
        from datetime import datetime, timezone

        from asset_model import slots

        assert slots.is_owed_supplies("no-such-dataset") is False
        assert slots.period_claimed_at("no-such-dataset",
                                       datetime(2026, 2, 1, tzinfo=timezone.utc)) is None


class TestTheOrchestratorsShortestWindow:
    """Criterion 6 (378 Q2 (a), SETTLED by Keith): a dataset whose window
    cannot be read on the receipt date is left out of the shortest-window
    minimum, answering none if none remain - never a borrowed one."""

    @pytest.fixture
    def arrival(self):
        from datetime import datetime, timezone
        from types import SimpleNamespace

        return SimpleNamespace(received_at=datetime(2026, 2, 1, 1, tzinfo=timezone.utc),
                               files_by_dataset={"cp-clients": [], "cp-carers": []})

    def test_the_broken_one_is_left_out(self, monkeypatch, arrival):
        from datetime import timedelta

        from qa_tools.tools import orchestrate

        def window(dataset_id, on=None, **k):
            if dataset_id == "cp-carers":
                raise schedule.ScheduleConfigError("no version in force")
            return timedelta(days=14)
        monkeypatch.setattr(schedule, "claim_window", window)
        assert orchestrate._claim_window("child-protection", arrival) == timedelta(days=14)

    def test_none_when_none_remain(self, monkeypatch, arrival):
        from qa_tools.tools import orchestrate

        def window(dataset_id, on=None, **k):
            raise schedule.ScheduleConfigError("no version in force")
        monkeypatch.setattr(schedule, "claim_window", window)
        assert orchestrate._claim_window("child-protection", arrival) is None


class TestTheDashboardBuildRefuses:
    """Criterion 16 (Dash A): the dashboard build refuses a dataset whose
    schedule configuration is broken, naming it and the asset's calendar
    file, rather than publishing it as having no slots; a schedule not yet
    agreed keeps its quiet answer."""

    @pytest.fixture
    def broken(self, monkeypatch):
        from asset_model import slots

        def refuse(dataset_id, *a, **k):
            raise schedule.ScheduleConfigError("no version in force on 2026-02-01")
        monkeypatch.setattr(slots, "slots_for_dataset", refuse)

    def test_the_period_slots_build_step(self, broken):
        from pipeline import period_slots

        with pytest.raises(period_slots.ScheduleRefusesBuild) as refused:
            period_slots.for_dataset("cp-clients")
        said = str(refused.value)
        assert "cp-clients" in said and "calendar.yaml" in said, said

    def test_the_embed_step(self, broken):
        from dashboard import embed_dashboard_data
        from pipeline import period_slots

        with pytest.raises(period_slots.ScheduleRefusesBuild, match="calendar.yaml"):
            embed_dashboard_data._slots_by_dataset()

    def test_no_calendar_agreed_stays_quiet(self, monkeypatch):
        from asset_model import slots
        from dashboard import embed_dashboard_data

        def not_agreed(dataset_id, *a, **k):
            raise schedule.NoCalendarAgreed(dataset_id, "never")
        monkeypatch.setattr(slots, "slots_for_dataset", not_agreed)
        assert embed_dashboard_data._slots_by_dataset() == {}


class TestARefusalAtTheCommandLine:
    """Criterion 17: a ScheduleConfigError reaching a `mothman` command is a
    one-paragraph refusal with exit 1, never a traceback, naming the asset's
    calendar file and ending with the remedy. Criterion 18: a pipeline step
    stopped on one says what was recorded before the stop and that it will
    stop the same way on every pass until the configuration is fixed."""

    def test_the_real_command_refuses(self, tmp_path, monkeypatch):
        from click.testing import CliRunner

        from cli.app import cli

        agreement_split.repoint(monkeypatch, tmp_path, _doc(_authored()),
                                base=agreement_split.participation("d", grace="2h"))

        def broken(*a, **k):
            raise schedule.ScheduleConfigError(
                "calendar 'c' has no version in force on 2020-02-01 - its earliest is 2023-01-01")
        monkeypatch.setattr(schedule, "periods_for_dataset", broken)
        got = CliRunner().invoke(cli, ["schedule", "show", "--dataset", "d"])
        out = " ".join(got.output.replace("│", " ").replace("╰", " ").replace("─", " ")
                       .replace("╯", " ").split())
        assert got.exit_code == 1, got.output
        assert "Traceback" not in out and got.exception is None or \
            isinstance(got.exception, SystemExit), got.exception
        assert "calendar.yaml" in out and "2020-02-01" in out and "2023-01-01" in out, out
        assert out.rstrip().endswith(
            "Fix the configuration, then `mothman schedule validate` checks it."), out

    def test_any_command_refuses_through_the_group(self, monkeypatch):
        """The catch is the group's (cli/app.py _MothmanGroup.invoke), so a
        command with no catch of its own refuses the same way."""
        import rich_click as click
        from click.testing import CliRunner

        from cli.app import cli

        @click.command("raise-schedule-error")
        def boom():
            raise schedule.ScheduleConfigError(
                "calendar 'quarterly' has no version in force on 2012-06-01 - "
                "its earliest is 2013-01-01")
        monkeypatch.setitem(cli.commands, "raise-schedule-error", boom)
        got = CliRunner().invoke(cli, ["raise-schedule-error"])
        out = " ".join(got.output.replace("│", " ").split())
        assert got.exit_code == 1, (got.output, got.exception)
        assert "calendar.yaml" in out and "mothman schedule validate" in out, out

    def test_a_stopped_step_says_it_will_stop_again(self, monkeypatch):
        from cli import lifecycle_report
        from qa_tools.common import arrival_lifecycle

        said = []
        monkeypatch.setattr(lifecycle_report.console, "print",
                            lambda text="", *a, **k: said.append(str(text)))
        exc = arrival_lifecycle.StageFailed(
            "cp_run_001", "filing", ("staging",),
            schedule.ScheduleConfigError("calendar 'c' has no version in force on 2020-02-01"))
        lifecycle_report.stage_failure(exc)
        text = " ".join(said)
        assert "Completed before it: staging." in text, text
        assert "every pass" in text and "calendar.yaml" in text, text


class TestAPeriodsRoundIsRequired:
    """Criterion 19: DatasetPeriod.round has no default."""

    def test_round_has_no_default(self):
        field = {f.name: f for f in dataclasses.fields(schedule.DatasetPeriod)}["round"]
        assert field.default is dataclasses.MISSING
        assert field.default_factory is dataclasses.MISSING


#: The data asset this module's tests act for, unless a test says otherwise
#: (C11, Keith 2026-11-02: every test module names its asset).
pytestmark = pytest.mark.asset("quarterly")


class TestAZeroDurationHasAnAuthoredForm:
    """post-build-review #470: `0h` parses (a grace of nothing), but
    format_duration refused timedelta(0), so `mothman schedule show` failed
    on any dataset whose grace was 0h. It writes back the form it reads."""

    def test_it_round_trips(self):
        from datetime import timedelta

        assert schedule.format_duration(schedule.parse_duration("0h", "x")) == "0h"
        assert schedule.format_duration(timedelta(0)) == "0h"
