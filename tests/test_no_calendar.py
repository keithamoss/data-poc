"""A dataset can exist before any supply is agreed (REQ-PIPE-106).

TWO SHAPES, ONE MECHANISM. A dataset receiving SAMPLE DATA while somebody
develops checks against it has no schedule YET and will graduate. A
one-off extraction for a project has supplies and no cadence AT ALL, and
criterion 3 is explicit that it must never be made to graduate. They look
identical in the data and mean opposite things to a reader: one is waiting
for something somebody has to do, the other is finished.

THESE TESTS DRIVE A FIXTURE HIERARCHY rather than adding a sample dataset
to contract/data-asset.yaml, which is deliberate and recorded on the
requirement: criterion 12 asks the system to SUPPORT any number of them,
not to ship one, and shipping one would drag a contract, checks and
generated data behind it for no additional coverage of this requirement.
"""
from __future__ import annotations

import yaml

import pytest

import agreement_split
from qa_tools.common import schedule


def _asset_with(datasets: list[dict], tmp_path, monkeypatch):
    """The real contract/data-asset.yaml with its datasets replaced.

    Built from the REAL file rather than a hand-written stub, so the
    calendars, the claim windows and the hierarchy shape are the real
    ones - a stub would test this code against an asset that does not
    exist.
    """
    doc = agreement_split.merged_view(agreement_split.REAL_CONTRACT_DIR)
    agency = doc["hierarchy"]["agencies"][0]
    agency["collections"] = [{
        "id": "civil-registration", "name": "Civil Registration",
        "contract": "bdm-birth-registrations-contract.yaml",
        "delivery_boundary": "directory",
        "datasets": datasets,
    }]
    doc["hierarchy"]["agencies"] = [agency]
    return agreement_split.repoint(monkeypatch, tmp_path, doc)


def _clear():
    """Every cache holding a parsed copy of either file - the
    agreement (contract/calendar.yaml) and the hierarchy - since missing one
    is how a fixture silently tests the real asset instead of its own.
    """
    from qa_tools.common import hierarchy as hierarchy_mod

    agreement_split.clear_caches()
    hierarchy_mod._load.cache_clear()


@pytest.fixture(autouse=True)
def _clear_caches():
    _clear()
    yield
    _clear()


SAMPLE = {"id": "cp-referrals", "name": "Referrals", "table": "cp_referrals",
          "no_calendar": "not-yet-agreed", "arrival_pattern": r"cp_referrals\.csv"}
PROJECT = {"id": "one-off-extract", "name": "A Project Extract",
           "table": "one_off_extract", "no_calendar": "never",
           "arrival_pattern": r"one_off_extract\.csv"}
AGREED = {"id": "birth-registrations", "name": "Birth Registrations",
          "table": "birth_registrations", "calendar": "daily",
          "arrival_pattern": r"birth_registrations_[^/]+\.csv"}


class TestADatasetMaySayItHasNoCalendar:
    """Criteria 1 and 2."""

    def test_a_deliberate_declaration_is_accepted(self, tmp_path, monkeypatch):
        _asset_with([AGREED, SAMPLE], tmp_path, monkeypatch)
        assert schedule.no_calendar("cp-referrals") == schedule.NOT_YET_AGREED

    def test_asking_for_its_calendar_raises_a_DISTINCT_exception(
            self, tmp_path, monkeypatch):
        """NOT a ScheduleConfigError, and the difference is criterion 1. A
        config error means somebody got it wrong and the pipeline should
        stop; this means the configuration is exactly as intended and
        there is no period arithmetic to do."""
        _asset_with([AGREED, SAMPLE], tmp_path, monkeypatch)
        with pytest.raises(schedule.NoCalendarAgreed) as raised:
            schedule.calendar_for_dataset("cp-referrals")
        assert not isinstance(raised.value, schedule.ScheduleConfigError)
        assert "cp-referrals" in str(raised.value)

    def test_the_message_says_which_kind_it_is(self, tmp_path, monkeypatch):
        _asset_with([AGREED, SAMPLE, PROJECT], tmp_path, monkeypatch)
        with pytest.raises(schedule.NoCalendarAgreed) as sample:
            schedule.calendar_for_dataset("cp-referrals")
        with pytest.raises(schedule.NoCalendarAgreed) as project:
            schedule.calendar_for_dataset("one-off-extract")
        assert "yet" in str(sample.value)
        assert "never" in str(project.value)

    def test_a_dataset_that_MERELY_OMITS_a_calendar_still_fails(
            self, tmp_path, monkeypatch):
        """The requirement's own second NFR, and the reason a declaration
        exists at all: allowing absence would destroy a gate that catches a
        real class of error, because a typo'd calendar name leaves a
        dataset silently expecting nothing - and a dataset expecting
        nothing never reports a missing supply."""
        _asset_with([AGREED, {"id": "cp-referrals", "name": "Referrals",
                               "table": "cp_referrals",
                               "arrival_pattern": r"cp_referrals\.csv"}],
                     tmp_path, monkeypatch)
        with pytest.raises(schedule.ScheduleConfigError, match="names no"):
            schedule.calendar_for_dataset("cp-referrals")

    def test_declaring_BOTH_is_refused_rather_than_resolved(
            self, tmp_path, monkeypatch):
        """One of them is wrong and this will not guess which."""
        both = {**SAMPLE, "calendar": "daily"}
        _asset_with([AGREED, both], tmp_path, monkeypatch)
        with pytest.raises(schedule.ScheduleConfigError, match="both"):
            schedule.no_calendar("cp-referrals")

    def test_an_unrecognised_value_is_refused(self, tmp_path, monkeypatch):
        """Not read as "not yet agreed" by accident, which would be the
        quiet direction: a dataset would owe nothing because somebody
        mistyped."""
        _asset_with([AGREED, {**SAMPLE, "no_calendar": "maybe"}],
                     tmp_path, monkeypatch)
        with pytest.raises(schedule.ScheduleConfigError, match="not one of"):
            schedule.no_calendar("cp-referrals")

    def test_an_ordinary_dataset_reads_as_having_a_calendar(
            self, tmp_path, monkeypatch):
        _asset_with([AGREED], tmp_path, monkeypatch)
        assert schedule.no_calendar("birth-registrations") is None
        assert schedule.calendar_for_dataset("birth-registrations").name == "daily"


class TestNotYetAgreedIsNotTheSameAsNever:
    """Criterion 3. Presenting a one-off extraction as waiting for a
    schedule would put a permanent item on somebody's list."""

    def test_sample_data_will_graduate(self, tmp_path, monkeypatch):
        _asset_with([AGREED, SAMPLE], tmp_path, monkeypatch)
        assert schedule.will_graduate("cp-referrals") is True

    def test_a_one_off_extraction_never_will(self, tmp_path, monkeypatch):
        _asset_with([AGREED, PROJECT], tmp_path, monkeypatch)
        assert schedule.will_graduate("one-off-extract") is False

    def test_a_dataset_with_a_calendar_is_neither(self, tmp_path, monkeypatch):
        _asset_with([AGREED], tmp_path, monkeypatch)
        assert schedule.will_graduate("birth-registrations") is False
        assert schedule.no_calendar("birth-registrations") is None


class TestItOwesNoSupply:
    """Criterion 1's observable half - and the one that matters, because a
    dataset reported as owing a supply nobody agreed puts a permanent red
    on somebody's dashboard."""

    def test_it_owes_nothing(self, tmp_path, monkeypatch):
        from qa_tools.common import slots

        _asset_with([AGREED, SAMPLE], tmp_path, monkeypatch)
        assert slots.is_owed_supplies("cp-referrals") is False
        assert slots.is_owed_supplies("birth-registrations") is True

    def test_it_cannot_run_out_of_runway(self, tmp_path, monkeypatch):
        """Warning that it has none would be asking somebody to author
        dates for a schedule nobody has agreed - or, for a one-off
        extraction, will ever agree."""
        from qa_tools.common import runway

        _asset_with([AGREED, SAMPLE, PROJECT], tmp_path, monkeypatch)
        exhausted = runway.exhausted_datasets(__import__("datetime").date(2030, 1, 1))
        assert "cp-referrals" not in exhausted
        assert "one-off-extract" not in exhausted

    def test_it_is_on_no_calendar_as_far_as_runway_is_concerned(
            self, tmp_path, monkeypatch):
        from qa_tools.common import runway

        _asset_with([AGREED, SAMPLE], tmp_path, monkeypatch)
        assert runway._calendar_name("cp-referrals") is None
        assert runway._calendar_name("birth-registrations") == "daily"


class TestWhenItGraduated:
    """Criterion 16's record. CONFIGURATION rather than an observed event,
    because graduation IS the configuration change - a calendar gets
    named - so the date it took effect is authored beside it and reviewed
    with it. An observed "when did we first see a calendar appear" would
    date the graduation to whenever the pipeline next happened to run.
    """

    def test_a_graduated_dataset_records_when(self, tmp_path, monkeypatch):
        import datetime

        _asset_with([{**AGREED, "owes_from": "2026-11-01"}], tmp_path, monkeypatch)
        assert schedule.owes_from("birth-registrations") == datetime.date(2026, 11, 1)

    def test_a_dataset_always_on_a_calendar_owes_from_its_first_participation(
            self, tmp_path, monkeypatch):
        """REQ-PIPE-110 criterion 27, amending REQ-PIPE-106 criterion 16:
        there is no separate owes_from any more, and the date a dataset
        began owing is its first participation version's effective_from -
        authored, never a guess at its first period."""
        import datetime

        _asset_with([AGREED], tmp_path, monkeypatch)
        assert schedule.owes_from("birth-registrations") == datetime.date(2026, 8, 24)

    def test_a_date_that_is_not_a_date_is_refused(self, tmp_path, monkeypatch):
        _asset_with([{**AGREED, "owes_from": "November"}], tmp_path, monkeypatch)
        with pytest.raises(schedule.ScheduleConfigError, match="not an ISO date"):
            schedule.owes_from("birth-registrations")


class TestTheConfigGateAcceptsItAndStaysStrict:
    """Criterion 2, at the gate. `mothman check`'s schedule gate is what
    keeps a typo from leaving a dataset silently expecting nothing, and
    this requirement must not weaken it."""

    def _errors(self, datasets, tmp_path, monkeypatch):
        from qa_tools.common import validate_schedule

        path = _asset_with(datasets, tmp_path, monkeypatch)
        # A REAL `Source`, pointing at the temporary asset and the REAL
        # contracts beside it - which is what the dataclass's own docstring
        # asks for: redirecting one and not the other validates a
        # temporary hierarchy against real contracts and reports nonsense.
        return validate_schedule.validate(validate_schedule.Source(
            path, validate_schedule.CONTRACT_DIR))

    def test_a_deliberate_declaration_passes_the_gate(self, tmp_path, monkeypatch):
        found = self._errors([AGREED, SAMPLE, PROJECT], tmp_path, monkeypatch)
        assert [e for e in found if "cp-referrals" in (e.scope or "")] == []
        assert [e for e in found if "one-off-extract" in (e.scope or "")] == []

    def test_a_bare_omission_still_fails_the_gate(self, tmp_path, monkeypatch):
        found = self._errors(
            [AGREED, {"id": "cp-referrals", "name": "Referrals", "table": "cp_referrals",
                       "arrival_pattern": r"cp_referrals\.csv"}],
            tmp_path, monkeypatch)
        assert [e for e in found if "cp-referrals" in (e.scope or "")], \
            "a dataset that merely omits a calendar must still fail"

    def test_the_omission_message_names_the_declaration_as_the_way_out(
            self, tmp_path, monkeypatch):
        found = self._errors(
            [AGREED, {"id": "cp-referrals", "name": "Referrals", "table": "cp_referrals",
                       "arrival_pattern": r"cp_referrals\.csv"}],
            tmp_path, monkeypatch)
        message = " ".join(f"{e.problem} {e.fix}" for e in found if "cp-referrals" in (e.scope or ""))
        assert schedule.NO_CALENDAR_KEY in message
        assert schedule.NOT_YET_AGREED in message

    def test_an_unknown_calendar_name_still_fails_the_gate(self, tmp_path, monkeypatch):
        found = self._errors([AGREED, {**SAMPLE, "no_calendar": None,
                                        "calendar": "quartrly"}],
                              tmp_path, monkeypatch)
        assert [e for e in found if "cp-referrals" in (e.scope or "")], \
            "a typo'd calendar name must still fail - that is the gate's whole job"

    def test_declaring_both_fails_the_gate(self, tmp_path, monkeypatch):
        found = self._errors([AGREED, {**SAMPLE, "calendar": "daily"}],
                              tmp_path, monkeypatch)
        assert any("BOTH" in e.problem for e in found if "cp-referrals" in (e.scope or ""))

    def test_subsetting_a_calendar_it_does_not_have_fails_the_gate(
            self, tmp_path, monkeypatch):
        """`delivery_months:` and `dates:` both describe which of a
        calendar's periods this dataset takes part in, and there is no
        calendar here to take part in."""
        found = self._errors(
            [AGREED, {**SAMPLE, "delivery_months": ["February"]}], tmp_path, monkeypatch)
        assert [e for e in found if "cp-referrals" in (e.scope or "")]

    def test_an_unrecognised_declaration_fails_the_gate(self, tmp_path, monkeypatch):
        found = self._errors([AGREED, {**SAMPLE, "no_calendar": "soon"}],
                              tmp_path, monkeypatch)
        assert [e for e in found if "cp-referrals" in (e.scope or "")]

    def test_the_real_asset_still_passes(self):
        """The shipped configuration, unmodified. A gate loosened enough to
        accept the declaration could also start accepting the real asset's
        own mistakes, and this is the assertion that would notice."""
        from qa_tools.common import validate_schedule

        assert validate_schedule.validate() == []


class TestSampleDataLivesInItsOwnSchema:
    """Criteria 4 and 5. A SCHEMA rather than a flag is the whole
    mechanism: a flag can be forgotten in one WHERE clause out of thirty,
    and the failure is silent and in the dangerous direction - sample data
    counting toward a real dataset's quality history.
    """

    def test_the_schema_exists_and_is_none_of_the_others(self, supply_dsn):
        from qa_tools.common import supply_db

        with supply_db.connect(label="test-sample-schema") as conn:
            supply_db.ensure_schemas(conn)
            found = {row[0] for row in conn.execute(
                "SELECT nspname FROM pg_namespace").fetchall()}
        assert supply_db.SAMPLE_SCHEMA in found
        assert supply_db.SAMPLE_SCHEMA not in (
            supply_db.STAGING_SCHEMA, supply_db.REJECTED_SCHEMA)

    def test_it_is_not_a_period_schema(self):
        """A period schema holds what was promoted into a period, and this
        data belongs to no period - so it must not be mistaken for one by
        anything that walks them."""
        from qa_tools.common import period_schema, supply_db

        assert not supply_db.SAMPLE_SCHEMA.startswith(period_schema.PERIOD_SCHEMA_PREFIX)

    def test_the_publisher_can_never_read_it(self, supply_dsn):
        """Criterion 5 reaching the dashboard: sample rows are supply rows,
        so the publisher must not reach them - and it does not, because the
        prefix is in the named list rather than derived."""
        from qa_tools.common import qa_store, supply_db

        assert any(supply_db.SAMPLE_SCHEMA.startswith(p)
                    for p in qa_store.SUPPLY_SCHEMA_PREFIXES)


class TestItIsInNoRollup:
    """Criteria 8 and 9, at the shared rule both implementations use.

    THE PYTHON SIDE IS NOT OPTIONAL, which this project has a scar for:
    plans/qa-pipeline.md item 74 shipped a correct data layer and a
    dashboard whose own transform disagreed with it, rendering a check with
    14 real violations green. There are two implementations of dataset
    status on purpose - the dashboard's in a browser, and this one in a
    GitHub Action with no JS runtime - so anything one knows, the other has
    to.
    """

    @staticmethod
    def _ds(dataset_id, status, **extra):
        return {"id": dataset_id, "name": dataset_id,
                "columns": [{"name": "a", "status": status}], **extra}

    def test_a_red_unagreed_dataset_does_not_turn_its_collection(self):
        from qa_tools.common import dataset_status as ds

        assert ds.rollup_datasets([
            self._ds("agreed", "green"),
            self._ds("sample", "red", scheduleNotAgreed="not-yet-agreed"),
        ]) == "green", "a dataset nobody agreed turned an agreed one's status"

    def test_it_keeps_its_own_real_verdict(self):
        """Criterion 7. Developing a check means seeing whether it passes,
        so its own tile is never softened to a quiet state."""
        from qa_tools.common import dataset_status as ds

        sample = self._ds("sample", "red", scheduleNotAgreed="not-yet-agreed")
        assert ds.in_no_rollup(sample) is True
        assert ds.rollup_statuses([c["status"] for c in sample["columns"]]) == "red"

    def test_a_collection_of_only_unagreed_datasets_reads_not_counted(self):
        """NEVER GREEN (post-build-review #135, Keith 2026-10-10). This test
        used to assert green, which pinned the false green itself: a group
        with nothing counted said 'healthy'. It now reads `notcounted` - a
        quiet status of its own, with a line saying why - which still says
        nothing about the asset's quality, the reason the datasets are left
        out (criterion 9), without claiming the group is fine."""
        from qa_tools.common import dataset_status as ds

        assert ds.rollup_datasets([
            self._ds("a", "red", scheduleNotAgreed="not-yet-agreed"),
            self._ds("b", "amber", scheduleNotAgreed="never"),
        ]) == "notcounted"

    def test_an_exhausted_schedule_still_comes_back(self):
        """The contrast, asserted so the new exclusion cannot be mistaken
        for the old one."""
        from qa_tools.common import dataset_status as ds

        assert ds.rollup_datasets(
            [{"id": "x", "columns": [], "scheduleExhausted": "quarterly"}]) == "exhausted"

    def test_an_ordinary_dataset_is_unaffected(self):
        from qa_tools.common import dataset_status as ds

        assert ds.in_no_rollup(self._ds("agreed", "red")) is False
        assert ds.rollup_datasets(
            [self._ds("agreed", "red"), self._ds("other", "green")]) == "red"

    def test_the_two_implementations_agree(self):
        """The one assertion that would have caught item 74. Same inputs,
        both sides, compared - rather than each suite checking its own.
        """
        import json
        import subprocess
        from pathlib import Path

        from qa_tools.common import dataset_status as ds

        cases = [
            [self._ds("a", "green"), self._ds("b", "red", scheduleNotAgreed="not-yet-agreed")],
            [self._ds("a", "red"), self._ds("b", "green", scheduleNotAgreed="never")],
            [self._ds("a", "amber", scheduleNotAgreed="not-yet-agreed")],
            [self._ds("a", "green"), self._ds("b", "amber")],
        ]
        mine = [ds.rollup_datasets(c) for c in cases]

        root = Path(__file__).resolve().parent.parent
        script = (
            "import {loadDashboard} from './tests-js/support/loadDashboard.js';"
            f"const cases = {json.dumps(cases)};"
            "const d = loadDashboard(); const w = d.window;"
            "console.log(JSON.stringify(cases.map(c => w.rollup(c)))); d.close();"
        )
        (root / "node_modules").exists() or __import__("pytest").skip("npm not installed")
        out = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=root, capture_output=True, text=True)
        assert out.returncode == 0, out.stderr[-2000:]
        theirs = json.loads(out.stdout.strip().splitlines()[-1])
        assert mine == theirs, f"python {mine} != dashboard {theirs}"


def test_ci_installs_what_the_rollup_comparison_runs():
    """The comparison above skips without node_modules - which it did on
    every CI run until 2026-10-06. The no-deployment job must install the
    dashboard's JS dependencies before its tests, or it checks nothing."""
    from pathlib import Path


    workflow = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "test.yml"
    steps = yaml.safe_load(workflow.read_text())["jobs"]["test"]["steps"]
    runs = [s.get("run", "") for s in steps]
    npm = next(i for i, r in enumerate(runs) if r.strip() == "npm ci")
    tests = next(i for i, r in enumerate(runs) if 'pytest -m "not needs_deployment"' in r)
    assert npm < tests
