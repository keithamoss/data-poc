"""A delivery agreement's past changes only by a declared correction
(REQ-PIPE-111).

Each test takes the real committed contract/calendar.yaml and
contract/data-asset.yaml as the PREVIOUS state, applies one change, and
asks `agreement_freeze.check` whether it is allowed - with the commit
instant fixed, so "is this frozen yet" never depends on when the suite
runs. The approvers are the real contract/people.yaml's.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from qa_tools.common import agreement_freeze as freeze

CONTRACT = Path(__file__).resolve().parent.parent / "contract"
PERTH = timezone(timedelta(hours=8))
#: The night this was built.
NOW = datetime(2026, 10, 11, 3, 0, tzinfo=PERTH)
KEITH = "fpycnkgvmt@privaterelay.appleid.com"


def _load(name):
    return yaml.safe_load((CONTRACT / name).read_text())


#: The real committed .github/CODEOWNERS, as the base (REQ-GHUB-174).
CODEOWNERS = (CONTRACT.parent / ".github" / "CODEOWNERS").read_text()


@pytest.fixture
def state():
    return _load("calendar.yaml"), _load("data-asset.yaml"), _load("people.yaml")


def _check(state, change_cal=None, change_asset=None, at=NOW, people=None,
           codeowners=CODEOWNERS):
    old_cal, old_asset, base_people = state
    new_cal, new_asset = copy.deepcopy(old_cal), copy.deepcopy(old_asset)
    if change_cal:
        change_cal(new_cal)
    if change_asset:
        change_asset(new_asset)
    return freeze.check(old_cal, new_cal, old_asset, new_asset,
                        people if people is not None else base_people,
                        instant_of=lambda key: at, today=at.date(),
                        base_codeowners=codeowners)


def _quarterly(doc):
    return next(c for c in doc["calendars"] if c["name"] == "quarterly")


def _date_entry(doc, period):
    for version in _quarterly(doc)["versions"]:
        for entry in version.get("dates") or []:
            if entry["period"] == period:
                return version, entry
    raise KeyError(period)


def _entry(doc, dataset_id):
    return next(d for d in doc["datasets"] if d["id"] == dataset_id)


def _text(findings):
    return "\n".join(f"{f.file} | {f.scope} | {f.problem} | {f.fix}" for f in findings)


def _correction(owner_list, *changes, approver=KEITH, ref="CAB-1"):
    owner_list.setdefault("corrections", []).append({
        "change_reference": ref, "date": "2026-10-11", "author": "a test",
        "approver": approver, "reason": "the agreed date was mistyped",
        "changes": [{"item": i, "old": o, "new": n} for i, o, n in changes]})


PAST = "2024-Q1"
PAST_KEY_PREFIX = "calendar quarterly version "


def _past_key(doc):
    version, _ = _date_entry(doc, PAST)
    return f"calendar quarterly period {PAST}"


class TestNothingToRefuse:
    def test_an_unchanged_file_passes(self, state):
        assert _check(state) == []

    def test_no_previous_state_passes(self, state):
        """Criterion 14 - a first commit or a shallow checkout."""
        _, asset, people = state
        assert freeze.check(None, state[0], None, asset, people,
                            base_codeowners=CODEOWNERS) == []

    def test_reordering_the_file_refuses_nothing(self, state):
        """Criterion 18 - parsed entries, not text."""
        def mutate(doc):
            doc["datasets"].reverse()
            doc["calendars"].reverse()
        assert _check(state, mutate) == []

    def test_a_future_date_is_freely_editable(self, state):
        """Criterion 10."""
        def mutate(doc):
            _date_entry(doc, "2027-Q4")[1]["date"] = "2027-11-02"
        assert _check(state, mutate) == []


class TestAFrozenItemChangesOnlyByCorrection:
    def test_moving_a_past_date_is_refused(self, state):
        """Criterion 3, with criterion 15's refusal."""
        def mutate(doc):
            _date_entry(doc, PAST)[1]["date"] = "2024-02-05"
        found = _check(state, mutate)
        assert len(found) == 1, _text(found)
        f = found[0]
        assert f.scope == _past_key(state[0])
        assert "Nothing was committed" in f.problem
        assert "change_reference" in f.fix and _past_key(state[0]) in f.fix
        assert "old: '2024-02-01'" in f.fix and "new: '2024-02-05'" in f.fix
        assert KEITH in f.fix, "it lists who may approve"
        assert "REQ-PIPE-169" in f.fix, "it names the impact preview"

    def test_a_changelog_line_is_no_licence(self, state):
        """Criterion 6 - REQ-PIPE-050's route is gone."""
        def mutate(doc):
            version, entry = _date_entry(doc, PAST)
            entry["date"] = "2024-02-05"
            version["changelog"].append({"date": "2026-10-11", "author": "a test",
                                         "change": "moved Q1 2024"})
        assert _check(state, mutate)

    def test_removing_a_past_date_is_refused(self, state):
        def mutate(doc):
            version, entry = _date_entry(doc, PAST)
            version["dates"].remove(entry)
        found = _check(state, mutate)
        assert any("removed" in f.problem for f in found), _text(found)

    def test_a_declared_correction_allows_it(self, state):
        """Criteria 3 and 4."""
        key = _past_key(state[0])

        def mutate(doc):
            _date_entry(doc, PAST)[1]["date"] = "2024-02-05"
            _correction(_quarterly(doc), (key, "2024-02-01", "2024-02-05"))
        assert _check(state, mutate) == []

    def test_a_correction_that_does_not_match_says_what_the_file_had(self, state):
        """Criterion 5."""
        key = _past_key(state[0])

        def mutate(doc):
            _date_entry(doc, PAST)[1]["date"] = "2024-02-05"
            _correction(_quarterly(doc), (key, "2024-02-01", "2024-02-06"))
        found = _check(state, mutate)
        assert any("you declared" in f.problem and "the file had" in f.problem
                   for f in found), _text(found)

    def test_declaring_a_change_the_file_does_not_make_is_refused(self, state):
        def mutate(doc):
            _correction(_quarterly(doc), (_past_key(state[0]), "2024-02-01", "2024-02-05"))
        found = _check(state, mutate)
        assert any("no change" in f.problem for f in found), _text(found)

    def test_a_correction_on_the_wrong_owner_is_refused(self, state):
        key = _past_key(state[0])

        def mutate(doc):
            _date_entry(doc, PAST)[1]["date"] = "2024-02-05"
            _correction(_entry(doc, "cp-clients"), (key, "2024-02-01", "2024-02-05"))
        found = _check(state, mutate)
        assert any("belongs to" in f.problem for f in found), _text(found)

    def test_a_change_before_its_freeze_point_is_free(self, state):
        """Criterion 12's clock: introduced before the date's claim window
        opened, the same edit needs nothing."""
        def mutate(doc):
            _date_entry(doc, PAST)[1]["date"] = "2024-02-05"
        assert _check(state, mutate, at=datetime(2023, 12, 1, tzinfo=PERTH)) == []


class TestTheApprover:
    """Criterion 22, both halves: the asset's manager in people.yaml and
    (REQ-GHUB-174 criterion 2) a code owner of the file in CODEOWNERS,
    both as they stood at the base."""

    def _corrected(self, state, approver, people=None, codeowners=CODEOWNERS):
        key = _past_key(state[0])

        def mutate(doc):
            _date_entry(doc, PAST)[1]["date"] = "2024-02-05"
            _correction(_quarterly(doc), (key, "2024-02-01", "2024-02-05"), approver=approver)
        return _check(state, mutate, people=people, codeowners=codeowners)

    def test_the_approver_may_be_named_by_github_account(self, state):
        assert self._corrected(state, "keithamoss") == []

    def test_a_manager_who_is_not_a_code_owner_may_not(self, state):
        """REQ-GHUB-174 criterion 2: GitHub could not require their review."""
        others = "/contract/calendar.yaml @someone-else\n"
        found = self._corrected(state, KEITH, codeowners=others)
        assert any("not a code owner of contract/calendar.yaml" in f.problem
                   for f in found), _text(found)

    def test_no_codeowners_at_the_base_refuses_every_correction(self, state):
        found = self._corrected(state, KEITH, codeowners=None)
        assert any("no .github/CODEOWNERS before this change" in f.problem
                   for f in found), _text(found)

    def test_the_last_matching_codeowners_line_wins(self, state):
        """As on GitHub: a later line un-owns the file."""
        later = CODEOWNERS + "\n/contract/ @someone-else\n"
        found = self._corrected(state, KEITH, codeowners=later)
        assert any("not a code owner" in f.problem for f in found), _text(found)

    def test_a_real_manager_may_approve(self, state):
        assert self._corrected(state, KEITH) == []

    def test_a_placeholder_may_not(self, state):
        found = self._corrected(state, "arthur.pendragon@example.com")
        assert any("approver" in f.problem for f in found), _text(found)

    def test_someone_without_the_role_may_not(self, state):
        found = self._corrected(state, "brian.cohen@example.com")
        assert any("approver" in f.problem for f in found), _text(found)

    def test_an_approver_the_same_change_adds_does_not_count(self, state):
        """The base's people.yaml decides - here the base has nobody."""
        found = self._corrected(state, KEITH, people={"people": []})
        assert any("approver" in f.problem for f in found), _text(found)


class TestCorrectionsAreAppendOnly:
    def test_editing_a_committed_correction_is_refused(self, state):
        """Criterion 21."""
        key = _past_key(state[0])
        old_cal, old_asset, people = state
        old_cal = copy.deepcopy(old_cal)
        _date_entry(old_cal, PAST)[1]["date"] = "2024-02-05"
        _correction(_quarterly(old_cal), (key, "2024-02-01", "2024-02-05"))

        def mutate(doc):
            _quarterly(doc)["corrections"][0]["reason"] = "rewritten"
        found = _check((old_cal, old_asset, people), mutate)
        assert any("append-only" in f.problem for f in found), _text(found)


class TestAppendingAfterTheLastDate:
    """Criterion 8 - extending an exhausted schedule needs no ceremony."""

    def test_next_years_dates_appended_late_need_nothing(self, state):
        def mutate(doc):
            _quarterly(doc)["versions"][-1]["dates"].extend([
                {"period": "2028-Q1", "date": "2028-02-01"},
                {"period": "2028-Q2", "date": "2028-05-01"}])
        # Committed in June 2028: both already past, still allowed.
        assert _check(state, mutate, at=datetime(2028, 6, 1, tzinfo=PERTH)) == []

    def test_an_appended_date_that_would_move_a_filed_supply_is_refused(self, state):
        """A date so soon after the last that its window opens before the
        last period's slot closed."""
        def mutate(doc):
            _quarterly(doc)["versions"][-1]["dates"].append(
                {"period": "2027-Q5", "date": "2027-11-05"})
        found = _check(state, mutate, at=datetime(2028, 6, 1, tzinfo=PERTH))
        assert any("2027-Q5" in (f.scope or "") for f in found), _text(found)


class TestNotExpected:
    def test_adding_one_for_a_period_already_open_is_refused(self, state):
        """It erases an obligation already owed - and the refusal names
        marking the period not supplied as the after-the-fact route."""
        def mutate(doc):
            _entry(doc, "cp-clients")["not_expected"] = [
                {"period": "2025-Q2", "reason": "agency shutdown"}]
        found = _check(state, mutate)
        assert found and "mark-not-supplied" in found[0].fix, _text(found)

    def test_adding_one_ahead_of_its_period_is_free(self, state):
        def mutate(doc):
            _entry(doc, "cp-clients")["not_expected"] = [
                {"period": "2027-Q3", "reason": "agency shutdown"}]
        assert _check(state, mutate) == []


class TestVersions:
    def test_changing_a_past_participation_version_is_refused(self, state):
        """Decision 6: a due time re-judges history as a date does."""
        def mutate(doc):
            _entry(doc, "cp-clients")["participation"]["versions"][0]["expected_time"] = "10:00"
        found = _check(state, mutate)
        assert any("participation" in (f.scope or "") for f in found), _text(found)

    def _add_version(self, eff):
        def mutate(doc):
            versions = _entry(doc, "cp-clients")["participation"]["versions"]
            versions.append({**versions[0], "effective_from": eff, "expected_time": "10:00",
                             "changelog": [{"date": "2026-10-11", "author": "a test",
                                            "change": "later"}]})
        return mutate

    def test_adding_a_future_participation_version_is_free(self, state):
        assert _check(state, self._add_version("2027-01-01")) == []

    def test_adding_a_past_dated_one_needs_a_correction(self, state):
        def not_synthetic(doc):
            doc["synthetic"] = False
        old_cal, old_asset, people = state
        old_asset = dict(old_asset, synthetic=False)
        found = _check((old_cal, old_asset, people), self._add_version("2025-01-01"),
                       not_synthetic)
        assert any("added" in f.problem for f in found), _text(found)

    def test_a_synthetic_asset_may_add_a_past_dated_version(self, state):
        """Criterion 9 - synthetic before and after."""
        assert state[1].get("synthetic") is True
        assert _check(state, self._add_version("2025-01-01")) == []

    def test_a_cadence_rule_versions_rule_applies(self, state):
        """Criterion 17: the daily calendar has no dated entries, and its
        version is frozen like any other."""
        def mutate(doc):
            daily = next(c for c in doc["calendars"] if c["name"] == "daily")
            daily["versions"][0]["claim_window"] = "6h"
        found = _check(state, mutate)
        assert any("calendar daily version" in (f.scope or "") for f in found), _text(found)


class TestTheTimezone:
    def test_changing_a_past_timezone_version_is_refused_on_the_timezone(self, state):
        def mutate(asset):
            asset["timezone"]["versions"][0]["zone"] = "Australia/Sydney"
        found = _check(state, change_asset=mutate)
        assert found and found[0].file == "data-asset.yaml", _text(found)
        assert "the timezone in contract/data-asset.yaml" in found[0].fix


class TestConfigurationOnly:
    def test_it_opens_nothing_under_data(self, state, monkeypatch):
        """Criterion 16."""
        import builtins

        opened = []
        real = builtins.open

        def watching(file, *args, **kwargs):
            opened.append(str(file))
            return real(file, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", watching)

        def mutate(doc):
            _date_entry(doc, PAST)[1]["date"] = "2024-02-05"
        _check(state, mutate)
        assert not [p for p in opened if "/data/" in p], opened


class TestTheSettingsGuardDatesByTheCommitter:
    """REQ-PIPE-111 criterion 28, fixing REQ-PIPE-122's built guard
    (plans/post-build-review.md #139): it dated a settings version by the
    commit's AUTHOR date, which a person can set to anything."""

    def test_it_asks_git_for_the_committer_instant_floored_at_the_base(self, monkeypatch):
        import subprocess
        from datetime import date

        from qa_tools.common import validate_schedule as vs

        base = datetime(2026, 10, 10, 12, 0, tzinfo=PERTH)
        monkeypatch.setattr(freeze, "committer_instant", lambda ref, root=None: base)
        asked = []

        class Done:
            returncode = 0
            # A backdated stamp, a week before the base commit.
            stdout = "abc123 2026-10-03T09:00:00+08:00\n"

        def fake_run(argv, **kwargs):
            asked.append(argv)
            return Done()

        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setattr(vs, "_content_at", lambda rel, ref: yaml.safe_dump({
            "amber_setting": {"versions": [{"effective_from": "2026-10-01", "value": "hold",
                                            "changelog": []}]}}))
        got = vs._version_added_on("contract/data-asset.yaml", "BASE", "2026-10-01")
        assert any("--format=%H %cI" in a for a in asked), asked
        assert got == date(2026, 10, 10), got


def test_inside_a_pre_commit_hook_the_base_is_head(monkeypatch):
    """Criterion 13: the hook compares the staged file against HEAD."""
    from qa_tools.common import diff_base

    monkeypatch.delenv(diff_base.ENV_VAR, raising=False)
    monkeypatch.setenv("PRE_COMMIT", "1")
    assert diff_base.diff_base() == "HEAD"
    monkeypatch.delenv("PRE_COMMIT")
    assert diff_base.diff_base() == diff_base.FALLBACK


class TestCriticFindingsOn111:
    """delivery-critic, 2026-10-11, on REQ-PIPE-111 as built (100fd0d).
    Each test failed before its fix."""

    def test_a_past_version_taking_later_dates_out_of_force_is_a_removal(self, state):
        """H1: the old version's later dates stop governing; that is a change
        to frozen items whether or not any entry was edited."""
        old_cal, old_asset, people_doc = state
        old_asset = dict(old_asset, synthetic=False)

        def mutate(doc):
            _quarterly(doc)["versions"].append({
                "effective_from": "2025-06-01", "claim_window": "14d",
                "changelog": [{"date": "2026-10-11", "author": "a", "change": "new"}],
                "dates": [{"period": "2025-Q3x", "date": "2025-08-04"}]})

        def keep_unsynthetic(asset):
            asset["synthetic"] = False
        found = _check((old_cal, old_asset, people_doc), mutate, keep_unsynthetic)
        assert any("2025-Q4" in (f.scope or "") and "removed" in f.problem
                   for f in found), _text(found)

    def test_moving_a_dataset_to_another_calendar_is_frozen(self, state):
        """H2, PROVISIONAL: a dataset's calendar membership freezes once its
        first slot could be filed."""
        def mutate(doc):
            _entry(doc, "cp-clients")["calendar"] = "daily"
        found = _check(state, mutate)
        assert any(f.scope == "dataset cp-clients calendar" for f in found), _text(found)

    def test_moving_a_whole_collection_is_frozen_for_each_dataset(self, state):
        def mutate(doc):
            next(c for c in doc["collections"] if c["id"] == "child-protection")["calendar"] = \
                "daily"
        found = _check(state, mutate)
        assert {f.scope for f in found} >= {"dataset cp-clients calendar",
                                             "dataset cp-carers calendar"}, _text(found)

    def test_the_paste_ready_entry_round_trips_for_a_removal(self, state):
        """M1: pasting what the refusal printed must clear it."""
        def remove(doc):
            version, entry = _date_entry(doc, PAST)
            version["dates"].remove(entry)
        found = _check(state, remove)
        (refusal,) = found
        block = refusal.fix.split("corrections:\n", 1)[1].split("\nMay approve")[0]
        entry = yaml.safe_load(block)[0]
        entry.update(change_reference="CAB-9", author="a test", approver=KEITH,
                     reason="the date was never agreed")

        def remove_and_declare(doc):
            remove(doc)
            _quarterly(doc).setdefault("corrections", []).append(entry)
        assert _check(state, remove_and_declare) == []

    def test_a_missing_previous_calendar_alone_passes(self, state):
        """M2 (criterion 14): a new asset whose data-asset.yaml predates its
        calendar.yaml - the calendar has no previous state to compare."""
        cal, asset, people_doc = state
        asset = dict(asset, synthetic=False)
        assert freeze.check(None, cal, asset, asset, people_doc,
                            instant_of=lambda key: NOW, base_codeowners=CODEOWNERS) == []

    def test_corrections_cannot_vanish_with_their_owner(self, state):
        """L4: removing an owner that carries corrections removes the record."""
        key = _past_key(state[0])
        old_cal, old_asset, people_doc = copy.deepcopy(state)
        _date_entry(old_cal, PAST)[1]["date"] = "2024-02-05"
        _correction(_entry(old_cal, "cp-carers"), (key, "2024-02-01", "2024-02-05"))

        def mutate(doc):
            doc["datasets"] = [d for d in doc["datasets"] if d["id"] != "cp-carers"]
        found = _check((old_cal, old_asset, people_doc), mutate)
        assert any("append-only" in f.problem for f in found), _text(found)

    def test_own_dates_are_frozen(self, state):
        """Coverage the critic found missing: a dataset's own dates."""
        old_cal, old_asset, people_doc = copy.deepcopy(state)
        _entry(old_cal, "cp-carers")["dates"] = {"versions": [{
            "effective_from": "2023-01-01",
            "changelog": [{"date": "2023-01-01", "author": "a", "change": "own"}],
            "dates": [{"period": "own-2024", "date": "2024-03-03"}]}]}

        def mutate(doc):
            _entry(doc, "cp-carers")["dates"]["versions"][0]["dates"][0]["date"] = "2024-03-09"
        found = _check((old_cal, old_asset, people_doc), mutate)
        assert any("own-2024" in (f.scope or "") for f in found), _text(found)
