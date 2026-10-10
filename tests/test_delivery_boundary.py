"""qa_tools/common/delivery_boundary.py - what one delivery IS, stated
per source (REQ-PIPE-057 criteria 2 and 3).

The failure this prevents is a guess that looks like a fact. Files
landing within a minute of each other is a plausible delivery and also
what two unrelated suppliers look like on a busy morning - and a wrong
boundary is not cosmetic, because every arrival fact downstream is
derived from it.
"""
from __future__ import annotations

import pytest

from qa_tools.common import delivery_boundary, hierarchy


def _sources(monkeypatch, mapping: dict[str, str]):
    entries = [
        hierarchy.Dataset(
            data_asset_id="a", agency_id="ag", agency_name="Ag",
            collection_id=collection_id, collection_name=collection_id,
            dataset_id=f"{collection_id}-one", dataset_name="One", table="t",
            contract="c.yaml", arrival_pattern=r"t\.csv", delivery_boundary=boundary)
        for collection_id, boundary in mapping.items()
    ]
    monkeypatch.setattr(hierarchy, "all_datasets", lambda: entries)


class TestTheRealConfiguration:
    def test_every_source_states_what_a_delivery_is(self):
        found = delivery_boundary.check_all()
        assert set(found) == {"child-protection", "civil-registration"}
        assert set(found.values()) == {delivery_boundary.DIRECTORY}


class TestASourceThatSaysNothingFails:
    def test_it_does_not_default_to_the_convention_everyone_else_uses(self, monkeypatch):
        """The dangerous reading is the quiet one: today every source
        says the same thing, so a missing value would inherit a
        convention that may not apply to the source that omitted it."""
        _sources(monkeypatch, {"described": "directory", "silent": ""})
        with pytest.raises(delivery_boundary.DeliveryBoundaryError) as exc:
            delivery_boundary.check_all()
        assert "silent" in str(exc.value)
        assert "described" not in str(exc.value)

    def test_the_message_names_the_file_and_what_it_refuses_to_do(self, monkeypatch):
        _sources(monkeypatch, {"silent": ""})
        with pytest.raises(delivery_boundary.DeliveryBoundaryError) as exc:
            delivery_boundary.boundary_for("silent")
        message = str(exc.value)
        assert "data-asset.yaml" in message
        assert "timestamps" in message and "proximity" in message

    def test_every_silent_source_is_named_at_once(self, monkeypatch):
        """Somebody adding collections has usually forgotten the same
        key in all of them, and one at a time is three runs."""
        _sources(monkeypatch, {"a": "", "b": "", "c": "directory"})
        with pytest.raises(delivery_boundary.DeliveryBoundaryError) as exc:
            delivery_boundary.check_all()
        assert "'a'" in str(exc.value) and "'b'" in str(exc.value)


class TestAnUnknownBoundaryIsNotATransportNobodyBuilt:
    def test_a_typo_is_refused_rather_than_accepted_as_future_work(self, monkeypatch):
        _sources(monkeypatch, {"typo": "directroy"})
        with pytest.raises(delivery_boundary.DeliveryBoundaryError, match="directroy"):
            delivery_boundary.boundary_for("typo")


class TestNothingIsReadFromASourceThatHasNotSaid:
    def test_the_survey_fails_before_it_opens_anything(self, monkeypatch, tmp_path):
        """It fails on the CONFIGURATION rather than on whatever
        happened to be on disk, which is what makes the error
        actionable."""
        from qa_tools.common import delivery

        _sources(monkeypatch, {"silent": ""})
        monkeypatch.setattr(delivery, "DELIVERIES_DIR", tmp_path / "nothing-here")
        with pytest.raises(delivery_boundary.DeliveryBoundaryError):
            delivery.survey()
