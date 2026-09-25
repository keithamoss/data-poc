"""qa_tools/common/arrival_patterns.py and its configuration gate
(REQ-PIPE-058).

The claim is about attribution - which dataset a delivered file belongs
to - so these run against the REAL declared patterns wherever the answer
should not depend on a fixture, and against hand-built ones only where
the point is a configuration that does not exist in this repo (a
collision, a dataset with no pattern, a pattern that will not compile).
"""
from __future__ import annotations

import json
import re

import pytest

from qa_tools.common import arrival_patterns, delivery, hierarchy, validate_arrival_patterns


@pytest.fixture(autouse=True)
def _fresh_patterns():
    """compiled_patterns() is cached for the life of the process, which
    is right in production and wrong across tests that rewrite the
    configuration."""
    arrival_patterns.compiled_patterns.cache_clear()
    yield
    arrival_patterns.compiled_patterns.cache_clear()


def _patterns(monkeypatch, mapping: dict[str, str]):
    """Stand in a hand-built set of dataset patterns."""
    entries = [
        hierarchy.Dataset(
            data_asset_id="a", agency_id="ag", agency_name="Ag",
            collection_id="col", collection_name="Col",
            dataset_id=dataset_id, dataset_name=dataset_id, table=dataset_id.replace("-", "_"),
            contract="contract.yaml", arrival_pattern=pattern)
        for dataset_id, pattern in mapping.items()
    ]
    monkeypatch.setattr(hierarchy, "all_datasets", lambda: entries)
    arrival_patterns.compiled_patterns.cache_clear()
    return entries


class TestTheRealDeclaredPatterns:
    """Against the configuration this repo actually ships, because the
    thing worth knowing is whether TODAY's files attribute correctly."""

    @pytest.mark.parametrize("filename,expected", [
        ("birth_registrations_2026-09-07.csv", "birth-registrations"),
        ("cp_clients.csv", "cp-clients"),
        ("cp_case_workers.csv", "cp-case-workers"),
        ("cp_notifications.csv", "cp-notifications"),
    ])
    def test_a_real_delivered_filename_attributes_to_its_dataset(self, filename, expected):
        assert arrival_patterns.attribute(filename).dataset_id == expected

    def test_every_dataset_declares_one(self):
        """Criterion 3, against the real tree rather than the gate's own
        reimplementation of it."""
        missing = [d.dataset_id for d in hierarchy.all_datasets() if not d.arrival_pattern]
        assert missing == []

    def test_no_real_filename_is_claimed_by_two_datasets(self):
        for filename in ("birth_registrations_2026-09-07.csv", "cp_clients.csv",
                         "cp_carers.csv", "cp_placements.csv", "cp_investigations.csv",
                         "cp_case_workers.csv", "cp_notifications.csv"):
            assert not arrival_patterns.attribute(filename).is_contested, filename

    def test_a_covering_note_is_unrecognised_rather_than_guessed_at(self):
        """Criterion 10. A supplier sending a PDF alongside the extract
        is ordinary, and attributing it by elimination - "the only other
        file in a Birth Registrations delivery must be Birth
        Registrations" - is how a garbage file becomes a supply."""
        found = arrival_patterns.attribute("covering note.pdf")
        assert found.is_unrecognised and found.dataset_id is None


class TestTheMatchIsOnTheFilenameAlone:
    def test_a_path_is_not_a_filename(self, monkeypatch):
        """Criterion 2. The delivery's own directory name is arbitrary
        by design, so it cannot be any part of the match."""
        _patterns(monkeypatch, {"d": r"data\.csv"})
        assert arrival_patterns.attribute("some-delivery/data.csv").dataset_ids == ()

    def test_a_pattern_matches_the_whole_name_or_nothing(self, monkeypatch):
        """Criterion 5, and it holds whether or not the author
        remembered to anchor - re.fullmatch does it structurally."""
        _patterns(monkeypatch, {"d": r"clients\.csv"})
        assert arrival_patterns.attribute("clients.csv").dataset_id == "d"
        assert arrival_patterns.attribute("old_clients.csv").dataset_ids == ()
        assert arrival_patterns.attribute("clients.csv.bak").dataset_ids == ()

    def test_an_author_anchoring_by_hand_still_works(self, monkeypatch):
        _patterns(monkeypatch, {"d": r"^clients\.csv$"})
        assert arrival_patterns.attribute("clients.csv").dataset_id == "d"

    def test_an_absurdly_long_name_is_refused_before_it_is_matched(self, monkeypatch):
        """The ReDoS residual Keith accepted is bounded mechanically
        rather than by trusting whoever wrote the pattern. Anything over
        255 characters is not a real filename on any filesystem this
        runs on."""
        _patterns(monkeypatch, {"d": r".*\.csv"})
        long_name = "x" * (arrival_patterns.MAX_FILENAME_LENGTH + 1) + ".csv"
        assert arrival_patterns.attribute(long_name).dataset_ids == ()


class TestOrderNeverDecidesAnything:
    """Criterion 6. Stopping at the first match would make attribution
    depend on declaration order AND hide the two-datasets-one-file case
    entirely - the very thing worth finding."""

    COLLIDING = {"first": r"shared\.csv", "second": r"shared\.csv"}

    def test_both_claimants_are_reported_not_the_first(self, monkeypatch):
        _patterns(monkeypatch, self.COLLIDING)
        found = arrival_patterns.attribute("shared.csv")
        assert found.dataset_ids == ("first", "second")
        assert found.is_contested

    def test_reversing_the_declaration_order_changes_nothing(self, monkeypatch):
        _patterns(monkeypatch, dict(reversed(list(self.COLLIDING.items()))))
        assert arrival_patterns.attribute("shared.csv").dataset_ids == ("first", "second")

    def test_a_contested_file_belongs_to_nobody(self, monkeypatch):
        """Not to the first, and not to whichever sorted lowest. A
        choice made invisibly is the failure this prevents."""
        _patterns(monkeypatch, self.COLLIDING)
        assert arrival_patterns.attribute("shared.csv").dataset_id is None
        assert arrival_patterns.dataset_for_filename("shared.csv") is None


class TestOneDatasetMayClaimSeveralFiles:
    """Criterion 11, and the opposite case to the one above - a split
    extract is legitimate, two datasets claiming one file never is."""

    def test_both_files_are_kept(self, monkeypatch, tmp_path):
        _patterns(monkeypatch, {"d": r"clients(_part\d+)?\.csv"})
        d = delivery.Delivery(name="drop", path=tmp_path,
                              files=("clients.csv", "clients_part2.csv"),
                              received_at=None, anomalies=())
        found = delivery.files_by_dataset(d)
        assert found.by_dataset == {"d": ["clients.csv", "clients_part2.csv"]}
        assert found.unmatched == [] and found.contested == {}


class TestABadPatternIsANamedConfigError:
    def test_an_unusable_regex_names_the_dataset(self, monkeypatch):
        """Rather than a stack trace out of `re` in the middle of
        recognising a delivery, which says nothing about which
        configuration is wrong."""
        _patterns(monkeypatch, {"broken": r"clients(\.csv"})
        with pytest.raises(arrival_patterns.ArrivalPatternError, match="broken"):
            arrival_patterns.compiled_patterns()

    def test_a_blank_pattern_is_an_error_rather_than_a_pattern(self, monkeypatch):
        """Whitespace where a pattern should be is somebody who started
        and stopped, and the dangerous reading is the quiet one: treat
        it as "declares none" and the dataset silently attributes
        nothing for ever. (The config loader strips, so a blank YAML
        value never reaches here as whitespace - this covers anything
        that builds a Dataset directly.)"""
        _patterns(monkeypatch, {"blank": "   "})
        with pytest.raises(arrival_patterns.ArrivalPatternError, match="blank"):
            arrival_patterns.compiled_patterns()


class TestTheConfigurationGate:
    """Criteria 7 and 8."""

    def test_missing_patterns_really_runs_against_the_real_tree(self):
        """Written after monkeypatching it out hid a real bug for an
        hour: this function called a `slots_for_dataset` that does not
        exist, and nothing noticed, because every real dataset declares
        a pattern so the line never executed."""
        assert validate_arrival_patterns.missing_patterns() == []

    def test_a_dataset_owed_supplies_with_no_pattern_is_found(self, monkeypatch):
        """The real function, against a dataset that declares none."""
        entries = [hierarchy.Dataset(
            data_asset_id="a", agency_id="ag", agency_name="Ag",
            collection_id="child-protection", collection_name="CP",
            dataset_id="cp-carers", dataset_name="Carers", table="cp_carers",
            contract="c.yaml", arrival_pattern="", delivery_boundary="directory")]
        monkeypatch.setattr(hierarchy, "all_datasets", lambda: entries)
        assert validate_arrival_patterns.missing_patterns() == ["cp-carers"]

    def test_a_dataset_owed_supplies_with_no_pattern_fails(self, monkeypatch):
        monkeypatch.setattr(validate_arrival_patterns, "missing_patterns",
                             lambda: ["cp-carers"])
        with pytest.raises(validate_arrival_patterns.ArrivalPatternConfigError) as exc:
            validate_arrival_patterns.validate()
        assert "cp-carers" in str(exc.value)
        assert "arrival_pattern" in str(exc.value)

    def test_a_filename_two_datasets_claim_fails_and_names_both(self, monkeypatch, tmp_path):
        """The gate's message is read by somebody under pressure who
        writes these rarely - "conflict detected" sends them diffing
        seven regexes."""
        _patterns(monkeypatch, {"alpha": r"shared\.csv", "beta": r"shared\.csv"})
        (tmp_path / "d1.json").write_text(json.dumps({"files": ["shared.csv"]}))
        with pytest.raises(validate_arrival_patterns.ArrivalPatternConfigError) as exc:
            validate_arrival_patterns.validate(log_dir=tmp_path)
        message = str(exc.value)
        assert "shared.csv" in message
        assert "alpha" in message and "beta" in message

    def test_it_says_when_it_has_no_corpus_rather_than_reporting_success(self, tmp_path):
        """A check with no corpus is not a check that passed. It has
        one now - REQ-PIPE-069's delivery log, which fills as the
        pipeline runs - but an empty one still has to say so, because
        a fresh clone has no deliveries yet."""
        line = validate_arrival_patterns.validate(log_dir=tmp_path / "nothing-here")
        assert "no delivery has been logged yet" in line

    def test_the_real_corpus_is_the_committed_delivery_log(self, real_committed_history):
        """The gate reads what REQ-PIPE-069 wrote, not data/ - which is
        what lets it run in CI at all.

        One of the few tests that genuinely wants the REAL committed
        tree, so it asks for it by name - conftest redirects those trees
        for every other test, to stop a run writing into or pruning
        project history."""
        line = validate_arrival_patterns.validate()
        assert "recorded filename(s)" in line, line

    def test_a_real_corpus_is_counted(self, tmp_path):
        (tmp_path / "d1.json").write_text(json.dumps(
            {"files": ["cp_clients.csv", "cp_carers.csv"]}))
        line = validate_arrival_patterns.validate(log_dir=tmp_path)
        assert "2 recorded filename(s)" in line

    def test_the_real_configuration_passes_its_own_gate(self):
        assert "OK" in validate_arrival_patterns.validate()

    def test_a_filename_that_stopped_matching_is_not_a_failure(self, tmp_path):
        """NOT a history gate, and that was rejected deliberately: one
        would force a dataset's old naming to be carried in its pattern
        for ever, punishing exactly the change that should be cheap -
        a supplier renaming their extract."""
        (tmp_path / "d1.json").write_text(json.dumps(
            {"files": ["an_old_naming_scheme_nobody_uses.csv"]}))
        assert "OK" in validate_arrival_patterns.validate(log_dir=tmp_path)


class TestTheTransportMatcherIsADifferentThing:
    def test_the_filename_matcher_no_longer_lives_in_delivery(self):
        """Criterion 4, as a real check rather than a note: the
        keyPattern-as-filename matcher is retired, and file_arrival.py's
        S3 key matcher legitimately survives. Saying which one goes is
        what stops somebody deleting the wrong one."""
        assert not hasattr(delivery, "_filename_pattern_to_regex")

        from qa_tools.common import file_arrival
        assert hasattr(file_arrival, "_pattern_to_regex")

    def test_the_contract_keypattern_is_not_what_attributes_a_file(self):
        """The contract still declares `bdm/birth_registrations_{date}.csv`
        for the transport, and a file named after that whole key must
        not attribute - the pattern is matched against a bare filename."""
        assert arrival_patterns.attribute(
            "bdm/birth_registrations_2026-09-07.csv").dataset_ids == ()


class TestWhatWasAttributedIsRecorded:
    def test_the_grouping_says_which_dataset_claimed_each_file(self, monkeypatch, tmp_path):
        """Criterion 12. The record is the grouping itself - a file
        appears under the dataset whose pattern claimed it, so there is
        no separate bookkeeping to fall out of step."""
        _patterns(monkeypatch, {"alpha": r"a\.csv", "beta": r"b\.csv"})
        d = delivery.Delivery(name="drop", path=tmp_path,
                              files=("a.csv", "b.csv", "notes.pdf"),
                              received_at=None, anomalies=())
        found = delivery.files_by_dataset(d)
        assert found.by_dataset == {"alpha": ["a.csv"], "beta": ["b.csv"]}
        assert found.unmatched == ["notes.pdf"]


class TestAContestedFileIsHeldRatherThanFiled:
    """Criterion 9: held for a human, attributed to nobody, reported at
    no lower than warning, and it does NOT fail the delivery - one bad
    pattern must not stop every other supply in the same drop."""

    def test_it_warns_and_keeps_going(self, monkeypatch, tmp_path):
        from qa_tools.common import arrivals

        _patterns(monkeypatch, {"alpha": r"shared\.csv", "beta": r"shared\.csv"})
        monkeypatch.setattr(hierarchy, "dataset",
                             lambda d: hierarchy.Dataset(
                                 data_asset_id="a", agency_id="ag", agency_name="Ag",
                                 collection_id="col", collection_name="Col",
                                 dataset_id=d, dataset_name=d, table=d,
                                 contract="c.yaml", arrival_pattern=""))
        d = delivery.Delivery(name="drop", path=tmp_path, files=("shared.csv",),
                              received_at=None, anomalies=())
        with pytest.warns(UserWarning, match=re.escape("shared.csv")):
            found = arrivals.recognise(d)
        assert found.by_dataset == {} and found.unmatched == ()
        assert found.contested == {"shared.csv": ("alpha", "beta")}
        assert found.is_unplaceable
