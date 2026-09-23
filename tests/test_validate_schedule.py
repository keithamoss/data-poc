"""Tests for the schedule/asset configuration gate (REQ-PIPE-050).

Every test here breaks the configuration in ONE specific way and
requires the gate to say so. That shape is deliberate: a validator is
only worth the build it interrupts if it actually catches the thing it
claims to, and a gate tested only against valid input is a gate that
has never been shown to do anything.

The real committed configuration is the baseline every case starts
from, copied and then broken, rather than a hand-written minimal one.
A fixture config drifts from the real file's shape, and then the gate
gets tested against a shape nobody uses.
"""
from __future__ import annotations

import copy
from datetime import date
import shutil
from pathlib import Path

import pytest
import yaml

from qa_tools.common import validate_schedule
from qa_tools.common.validate_schedule import Source, validate

REAL_CONTRACT_DIR = Path(__file__).resolve().parent.parent / "contract"


@pytest.fixture
def config(tmp_path):
    """A writable copy of the real contract directory, and a helper that
    rewrites the asset file after mutating it."""
    contract_dir = tmp_path / "contract"
    shutil.copytree(REAL_CONTRACT_DIR, contract_dir)
    asset_path = contract_dir / "data-asset.yaml"
    src = Source(asset_path, contract_dir)

    def apply(mutate):
        doc = yaml.safe_load(asset_path.read_text())
        mutate(doc)
        asset_path.write_text(yaml.safe_dump(doc, sort_keys=False))
        return validate(src)

    apply.src = src
    apply.asset_path = asset_path
    apply.contract_dir = contract_dir
    return apply


def _messages(errors):
    return "\n".join(f"{e.scope or ''} {e.problem} {e.fix}" for e in errors)


def _datasets(doc):
    for agency in doc["hierarchy"]["agencies"]:
        for collection in agency["collections"]:
            yield from collection["datasets"]


def _dataset(doc, dataset_id):
    return next(d for d in _datasets(doc) if d["id"] == dataset_id)


def _calendar(doc, name):
    return next(c for c in doc["calendars"] if c["name"] == name)


class TestTheRealConfigurationPasses:
    def test_the_committed_configuration_is_valid(self):
        """The baseline. If this ever fails, the gate is reporting on
        the repo's own config, not on a test fixture."""
        assert validate() == []

    def test_an_untouched_copy_is_valid_too(self, config):
        """Proves the fixture itself introduces nothing - otherwise
        every test below could be passing for the wrong reason."""
        assert config(lambda doc: None) == []


class TestATypoCanNeverLeaveADatasetExpectingNothing:
    """The one sentence the whole gate exists for."""

    def test_a_misspelt_month_is_rejected(self):
        def mutate(doc):
            _dataset(doc, "cp-case-workers")["delivery_months"] = ["Febuary", "August"]
        errors = _run(mutate)
        assert any("Febuary" in e.problem for e in errors), _messages(errors)
        assert any("February" in e.fix for e in errors), "the fix must name a real month"

    def test_a_month_the_calendar_has_no_date_in_is_rejected(self):
        def mutate(doc):
            _dataset(doc, "cp-case-workers")["delivery_months"] = ["March", "August"]
        errors = _run(mutate)
        assert any("March" in e.problem and "no\n" not in e.problem for e in errors), _messages(errors)
        assert any("expects nothing in March" in e.fix for e in errors), _messages(errors)

    def test_a_calendar_the_asset_does_not_define_is_rejected(self):
        def mutate(doc):
            _dataset(doc, "cp-clients")["calendar"] = "quarterly-v2"
        errors = _run(mutate)
        assert any("quarterly-v2" in e.problem for e in errors), _messages(errors)
        assert any("expects nothing" in e.fix for e in errors), _messages(errors)

    def test_an_empty_delivery_months_list_is_rejected(self):
        def mutate(doc):
            _dataset(doc, "cp-case-workers")["delivery_months"] = []
        errors = _run(mutate)
        assert any("nothing in it" in e.problem for e in errors), _messages(errors)

    def test_not_expected_covering_every_period_is_rejected(self):
        """The combination no single rule catches: every month is real,
        every month is on the calendar, and every resulting period is
        then excluded."""
        def mutate(doc):
            dataset = _dataset(doc, "cp-case-workers")
            dates = _calendar(doc, "quarterly")["versions"][0]["dates"]
            months = {2: "February", 8: "August"}
            dataset["not_expected"] = [
                {"period": e["period"], "reason": "test"} for e in dates
                if int(e["date"].split("-")[1]) in months]
        errors = _run(mutate)
        assert any("expects no supply in any period" in e.problem for e in errors), _messages(errors)

    def test_a_dataset_expecting_nothing_is_reported_once_not_twice(self):
        """A dataset naming a calendar that does not exist already has a
        better error than "expects nothing" - saying both is two errors
        for one mistake."""
        def mutate(doc):
            _dataset(doc, "cp-clients")["calendar"] = "nope"
        errors = [e for e in _run(mutate) if e.scope == "dataset 'cp-clients'"]
        assert len(errors) == 1, _messages(errors)

    def test_a_version_with_neither_dates_nor_a_rule_is_rejected(self):
        def mutate(doc):
            version = _calendar(doc, "quarterly")["versions"][0]
            del version["dates"]
        errors = _run(mutate)
        assert any("neither" in e.problem for e in errors), _messages(errors)


class TestAMistypedKeyFailsToo:
    """Not just a mistyped VALUE. A silently-dropped delivery_months key
    gives a dataset every quarterly date when its author meant two, and
    nothing about the result looks wrong."""

    def test_an_unknown_dataset_key_is_rejected(self):
        def mutate(doc):
            dataset = _dataset(doc, "cp-case-workers")
            dataset["delivery_month"] = dataset.pop("delivery_months")
        errors = _run(mutate)
        assert any("delivery_month" in e.problem for e in errors), _messages(errors)
        assert any("not a key" in e.problem for e in errors), _messages(errors)

    def test_an_unknown_top_level_key_is_rejected(self):
        errors = _run(lambda doc: doc.update({"timzone": "Australia/Perth"}))
        assert any("timzone" in e.problem for e in errors), _messages(errors)

    def test_a_missing_required_value_is_rejected(self):
        def mutate(doc):
            del _dataset(doc, "cp-clients")["table"]
        errors = _run(mutate)
        assert any("required" in e.problem for e in errors), _messages(errors)


class TestCalendarIntegrity:
    def test_duplicate_calendar_names_are_rejected(self):
        def mutate(doc):
            doc["calendars"].append(copy.deepcopy(_calendar(doc, "daily")))
        errors = _run(mutate)
        assert any("defined 2 times" in e.problem for e in errors), _messages(errors)

    def test_a_duplicate_period_name_is_rejected(self):
        def mutate(doc):
            dates = _calendar(doc, "quarterly")["versions"][0]["dates"]
            dates.append({"period": dates[0]["period"], "date": "2028-02-01"})
        errors = _run(mutate)
        assert any("2 times" in e.problem and "period" in e.problem for e in errors), _messages(errors)

    def test_a_duplicate_date_is_rejected(self):
        def mutate(doc):
            dates = _calendar(doc, "quarterly")["versions"][0]["dates"]
            dates.append({"period": "2028-Q9", "date": dates[0]["date"]})
        errors = _run(mutate)
        assert any("carries the date" in e.problem for e in errors), _messages(errors)

    def test_out_of_order_versions_are_rejected(self):
        def mutate(doc):
            cal = _calendar(doc, "quarterly")
            later = copy.deepcopy(cal["versions"][0])
            later["effective_from"] = "2020-01-01"
            cal["versions"].append(later)
        errors = _run(mutate)
        assert any("not after" in e.problem for e in errors), _messages(errors)

    def test_versions_sharing_an_effective_date_are_rejected(self):
        def mutate(doc):
            cal = _calendar(doc, "quarterly")
            cal["versions"].append(copy.deepcopy(cal["versions"][0]))
        errors = _run(mutate)
        assert any("not after" in e.problem for e in errors), _messages(errors)

    def test_an_unparseable_date_is_rejected(self):
        def mutate(doc):
            _calendar(doc, "quarterly")["versions"][0]["dates"][0]["date"] = "1 Feb 2023"
        errors = _run(mutate)
        assert any("not a date" in e.problem for e in errors), _messages(errors)


class TestDurationsAreNeverCoerced:
    @pytest.mark.parametrize("value", ["14", "14 days", "P14D", "fortnight"])
    def test_a_claim_window_without_a_recognised_unit_is_rejected(self, value):
        def mutate(doc):
            _calendar(doc, "quarterly")["versions"][0]["claim_window"] = value
        errors = _run(mutate)
        assert any("not a duration" in e.problem for e in errors), f"{value!r}: {_messages(errors)}"

    def test_a_negative_claim_window_is_rejected(self):
        def mutate(doc):
            _calendar(doc, "quarterly")["versions"][0]["claim_window"] = "-14d"
        errors = _run(mutate)
        assert any("negative" in e.problem or "not a duration" in e.problem
                    for e in errors), _messages(errors)


class TestSubsettingAndOverridingAreDifferentActs:
    def test_a_dataset_cannot_do_both(self):
        def mutate(doc):
            _dataset(doc, "cp-case-workers")["dates"] = [
                {"period": "2026-Q1", "date": "2026-02-01"}]
        errors = _run(mutate)
        assert any("BOTH" in e.problem for e in errors), _messages(errors)

    def test_delivery_months_against_a_cadence_rule_calendar_is_rejected(self):
        def mutate(doc):
            _dataset(doc, "birth-registrations")["delivery_months"] = ["February"]
        errors = _run(mutate)
        assert any("cadence RULE" in e.problem for e in errors), _messages(errors)
        assert any("cannot honour" in e.fix for e in errors), _messages(errors)


class TestTheContractsOnTheOtherSide:
    def test_a_collection_naming_a_contract_that_does_not_exist_is_rejected(self):
        def mutate(doc):
            doc["hierarchy"]["agencies"][0]["collections"][0]["contract"] = "nope.yaml"
        errors = _run(mutate)
        assert any("does not exist" in e.problem for e in errors), _messages(errors)

    def test_a_contract_no_collection_names_is_rejected(self, config):
        def mutate(doc):
            pass
        shutil.copy(config.contract_dir / "child-protection-contract.yaml",
                     config.contract_dir / "orphan-contract.yaml")
        errors = config(mutate)
        assert any(e.file == "orphan-contract.yaml" for e in errors), _messages(errors)
        assert any("checked by nothing" in e.fix for e in errors), _messages(errors)

    def test_a_negative_grace_allowance_is_rejected(self, config):
        path = config.contract_dir / "child-protection-contract.yaml"
        doc = yaml.safe_load(path.read_text())
        for item in doc["slaProperties"]:
            if item.get("property") == "latency":
                item["value"] = -30
                break
        path.write_text(yaml.safe_dump(doc, sort_keys=False))
        errors = config(lambda d: None)
        assert any("negative" in e.problem for e in errors), _messages(errors)
        assert any("late\nbefore it is due" in e.fix or "before it is due" in e.fix
                    for e in errors), _messages(errors)


class TestHowItReports:
    def test_every_offending_item_is_reported_individually(self):
        """Keith's own call, 2026-09-23, against a recommendation to
        suppress errors caused by an earlier one: nothing is hidden and
        the count in the header is the true count."""
        def mutate(doc):
            for dataset in _datasets(doc):
                dataset["calendar"] = "no-such-calendar"
        errors = _run(mutate)
        named = {e.scope for e in errors if e.scope}
        assert len(named) == 7, f"expected one error per dataset, got {len(named)}: {named}"

    def test_it_does_not_stop_at_the_first_error(self):
        def mutate(doc):
            _dataset(doc, "cp-case-workers")["delivery_months"] = ["Febuary"]
            _calendar(doc, "quarterly")["versions"][0]["claim_window"] = "14"
        errors = _run(mutate)
        assert len(errors) >= 2, _messages(errors)
        assert any("Febuary" in e.problem for e in errors)
        assert any("not a duration" in e.problem for e in errors)

    def test_every_error_names_a_correction_not_only_the_rule(self):
        def mutate(doc):
            _dataset(doc, "cp-case-workers")["delivery_months"] = ["Febuary"]
            _dataset(doc, "cp-clients")["calendar"] = "nope"
            _calendar(doc, "daily")["versions"][0]["claim_window"] = "4"
        errors = _run(mutate)
        assert errors
        for error in errors:
            assert error.fix.strip(), f"no correction offered for: {error.problem}"

    def test_errors_carry_the_file_and_the_thing_to_open(self):
        def mutate(doc):
            _dataset(doc, "cp-clients")["calendar"] = "nope"
        errors = _run(mutate)
        assert all(e.file for e in errors)
        assert any(e.scope == "dataset 'cp-clients'" for e in errors), _messages(errors)


class TestAFileThatDoesNotParse:
    def test_it_names_the_location_and_reports_nothing_else(self, config):
        """A file that did not parse has no values to be missing, and
        reporting every one of them as absent buries the one thing that
        is actually wrong."""
        config.asset_path.write_text("calendars:\n  - name: quarterly\n   bad_indent: true\n")
        errors = validate(config.src)
        assert len(errors) == 1, _messages(errors)
        assert "could not be parsed" in errors[0].problem
        assert "line" in errors[0].problem
        assert errors[0].file == "data-asset.yaml"

    def test_a_missing_file_says_so_once(self, config):
        config.asset_path.unlink()
        errors = validate(config.src)
        assert len(errors) == 1
        assert "does not exist" in errors[0].problem


class TestItTouchesNoData:
    def test_validating_opens_nothing_under_data(self, monkeypatch):
        """The standing CI rule, asserted rather than assumed - this
        gate runs on every push, and a config validator that reached
        into data/ would be exactly the accident the rule exists for."""
        opened = []
        real_open = Path.open

        def watching(self, *args, **kwargs):
            opened.append(str(self))
            return real_open(self, *args, **kwargs)

        monkeypatch.setattr(Path, "open", watching)
        validate()
        assert not [p for p in opened if "/data/" in p or p.endswith("duckdb")], opened


def _run(mutate):
    """Apply one mutation to a throwaway copy of the real configuration
    and validate it. Module-level so the class-based tests above read as
    one line each."""
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    contract_dir = tmp / "contract"
    shutil.copytree(REAL_CONTRACT_DIR, contract_dir)
    asset_path = contract_dir / "data-asset.yaml"
    doc = yaml.safe_load(asset_path.read_text())
    mutate(doc)
    asset_path.write_text(yaml.safe_dump(doc, sort_keys=False))
    try:
        return validate(Source(asset_path, contract_dir))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_the_module_reports_through_a_real_mothman_command():
    """Criterion: invoked as a mothman subcommand, in a group that is
    not documented as non-human-facing."""
    from cli.schedule import schedule_group

    assert "validate" in schedule_group.commands
    assert validate_schedule.main() == 0


class TestAPastDateCannotMoveQuietly:
    """REQ-PIPE-050's reopened question, settled 2026-09-23: build it.

    Thread E's rule is that config must never be edited to make red
    history disappear. Move last February's agreed date forward and
    every supply that was late for it becomes on time, retroactively
    and silently.

    Half these tests are about what the guard must stay QUIET for. A
    gate that fires on legitimate work gets turned off, and authoring
    next year's dates is the single most ordinary thing anyone does to
    this file.
    """

    CAL = "quarterly"

    def _edit(self, old_doc, mutate):
        """Compare a mutated document against `old_doc` directly, rather
        than against git - the rule is about what changed, and reaching
        for a real commit would test git rather than the rule."""
        new_doc = copy.deepcopy(old_doc)
        mutate(new_doc)
        return new_doc

    def _run(self, monkeypatch, tmp_path, mutate, today=None):
        from qa_tools.common import validate_schedule as mod

        real = yaml.safe_load((REAL_CONTRACT_DIR / "data-asset.yaml").read_text())
        new_doc = self._edit(real, mutate)
        monkeypatch.setattr(mod, "_content_at",
                             lambda rel_path, ref: yaml.safe_dump(real, sort_keys=False))
        path = tmp_path / "data-asset.yaml"
        path.write_text(yaml.safe_dump(new_doc, sort_keys=False))
        src = Source(mod.ROOT / "contract" / "data-asset.yaml", REAL_CONTRACT_DIR)
        return mod._retrospective_edit_errors(new_doc, src,
                                               today=today or date(2026, 9, 23))

    def _version(self, doc):
        return _calendar(doc, self.CAL)["versions"][0]

    def _period_entry(self, doc, period):
        return next(e for e in self._version(doc)["dates"] if e["period"] == period)

    def test_moving_a_past_date_without_saying_so_is_rejected(self, monkeypatch, tmp_path):
        def mutate(doc):
            self._period_entry(doc, "2026-Q1")["date"] = "2026-02-15"
        errors = self._run(monkeypatch, tmp_path, mutate)
        assert len(errors) == 1, _messages(errors)
        assert "2026-Q1" in errors[0].problem
        assert "already in the past" in errors[0].problem
        assert "rewrites whether" in errors[0].fix

    def test_removing_a_past_date_is_rejected_too(self, monkeypatch, tmp_path):
        def mutate(doc):
            version = self._version(doc)
            version["dates"] = [e for e in version["dates"] if e["period"] != "2026-Q1"]
        errors = self._run(monkeypatch, tmp_path, mutate)
        assert len(errors) == 1, _messages(errors)
        assert "has been removed" in errors[0].problem

    def test_a_changelog_entry_clears_it(self, monkeypatch, tmp_path):
        """A "say what you did" gate, not a freeze. Thread E allows a
        correction; it just will not have one happen quietly."""
        def mutate(doc):
            self._period_entry(doc, "2026-Q1")["date"] = "2026-02-15"
            self._version(doc)["changelog"].append(
                "2026-09-23: Q1 moved to the 15th at the agency's request.")
        assert self._run(monkeypatch, tmp_path, mutate) == []

    def test_editing_a_future_date_is_silent(self, monkeypatch, tmp_path):
        """The most ordinary edit anyone makes to this file - it is what
        `mothman schedule candidate-dates` exists to produce."""
        def mutate(doc):
            self._period_entry(doc, "2027-Q2")["date"] = "2027-05-03"
        assert self._run(monkeypatch, tmp_path, mutate) == []

    def test_adding_future_dates_is_silent(self, monkeypatch, tmp_path):
        def mutate(doc):
            self._version(doc)["dates"].append({"period": "2028-Q1", "date": "2028-02-01"})
        assert self._run(monkeypatch, tmp_path, mutate) == []

    def test_authoring_a_new_version_is_silent(self, monkeypatch, tmp_path):
        """The sanctioned way to change a schedule. A date differing
        between versions is the mechanism working, not history moving."""
        def mutate(doc):
            cal = _calendar(doc, self.CAL)
            new_version = copy.deepcopy(cal["versions"][0])
            new_version["effective_from"] = "2027-01-01"
            new_version["changelog"] = ["2027-01-01: Moved to the 15th from 2027."]
            for entry in new_version["dates"]:
                entry["date"] = entry["date"].replace("-01", "-15")
            cal["versions"].append(new_version)
        assert self._run(monkeypatch, tmp_path, mutate) == []

    def test_an_unchanged_file_is_silent(self, monkeypatch, tmp_path):
        assert self._run(monkeypatch, tmp_path, lambda doc: None) == []

    def test_no_previous_commit_is_not_a_finding(self, monkeypatch, tmp_path):
        """A shallow checkout or a first commit is not a violation, and
        failing on one would make the gate unrunnable in exactly the
        places it is least expected."""
        from qa_tools.common import validate_schedule as mod

        monkeypatch.setattr(mod, "_content_at", lambda rel_path, ref: None)
        real = yaml.safe_load((REAL_CONTRACT_DIR / "data-asset.yaml").read_text())
        src = Source(mod.ROOT / "contract" / "data-asset.yaml", REAL_CONTRACT_DIR)
        assert mod._retrospective_edit_errors(real, src) == []

    def test_an_unparseable_previous_version_is_not_a_finding(self, monkeypatch, tmp_path):
        from qa_tools.common import validate_schedule as mod

        monkeypatch.setattr(mod, "_content_at", lambda rel_path, ref: "{{ not yaml")
        real = yaml.safe_load((REAL_CONTRACT_DIR / "data-asset.yaml").read_text())
        src = Source(mod.ROOT / "contract" / "data-asset.yaml", REAL_CONTRACT_DIR)
        assert mod._retrospective_edit_errors(real, src) == []

    def test_it_reads_one_file_at_one_ref_not_a_history_walk(self, monkeypatch):
        """The whole reason this was reopened. The version put to Keith
        and rejected needed a deep clone; this is the single `git show`
        validate_check_lifecycle.py already runs at the fetch-depth CI
        already uses."""
        from qa_tools.common import validate_schedule as mod

        calls = []
        real_run = mod.subprocess.run

        def watching(argv, **kwargs):
            calls.append(argv)
            return real_run(argv, **kwargs)

        monkeypatch.setattr(mod.subprocess, "run", watching)
        validate()
        git_calls = [c for c in calls if c and c[0] == "git"]
        assert len(git_calls) == 1, git_calls
        assert git_calls[0][1] == "show"
        assert git_calls[0][2].startswith("HEAD~1:")
