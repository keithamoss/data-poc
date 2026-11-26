"""REQ-QAC-387: one shared file-checks default beside dbt_shared/ applies to
every asset, which an asset may add to, override by check name, or retire for
itself in its own file-checks.yaml.

Driven through the readers the pipeline uses - file_check_definitions'
definitions()/active() (what file_checks.evaluate runs), the lifecycle
parser and validate(), and the collections gate's main().
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from asset_model import check_lifecycle as cl
from asset_model import file_check_definitions as fcd
from asset_model import hierarchy

SIX = ["encoding", "delimiter", "header_row", "header_names_unique", "fields_per_row",
       "column_order"]


def _shared() -> dict:
    return yaml.safe_load((Path(fcd.assets.ROOT) / fcd.FILE).read_text())


def _entry(doc: dict, name: str) -> dict:
    return next(e for e in doc["checks"] if e["check"] == name)


def _write(path: Path, entries: list[dict]) -> Path:
    path.write_text(yaml.safe_dump({"checks": entries}, sort_keys=False))
    return path


class TestTheSharedDefault:
    def test_an_asset_with_no_file_of_its_own_runs_exactly_todays_six(self, tmp_path):
        """Criteria 1 and 5: the shared file holds the six, and neither asset
        folder holds a copy any more."""
        assert [e["check"] for e in _shared()["checks"]] == SIX
        assert not fcd.definitions_path().exists()
        found = fcd.definitions(tmp_path / "none.yaml")
        assert [d.check for d in found] == SIX
        assert {d.check: d.severity for d in found}["column_order"] == "warning"
        assert [d.check for d in fcd.active()] == SIX

    def test_an_asset_adds_a_check_of_its_own(self, tmp_path, monkeypatch):
        """Criterion 3: a name the default does not hold runs for that asset."""
        shared = _shared()
        added = _entry(shared, "column_order")
        shared["checks"] = [e for e in shared["checks"] if e["check"] != "column_order"]
        shared_file = _write(tmp_path / "shared.yaml", shared["checks"])
        monkeypatch.setattr(fcd, "shared_path", lambda: shared_file)
        own = _write(tmp_path / "own.yaml", [added])

        assert [d.check for d in fcd.definitions(tmp_path / "none.yaml")] == SIX[:-1]
        assert [d.check for d in fcd.definitions(own)] == SIX

    def test_an_added_name_with_no_evaluator_is_refused_by_the_gate(self, tmp_path, monkeypatch):
        """Criterion 3, the gap the post-build critic reproduced: an asset's
        own entry may only name a check the code can evaluate. Accepted, it
        passed `mothman check` and then failed every file with 'no evaluator
        for this check'; the gate now refuses it, naming the entry and the
        names there are (Keith, 2026-11-18)."""
        own = _write(tmp_path / "own.yaml", [{"check": "bom_absent", "severity": "failure"}])
        monkeypatch.setattr(fcd, "definitions_path", lambda: own)
        found = fcd.problems()
        assert len(found) == 1 and "bom_absent" in found[0], found
        assert "no file check of that name exists" in found[0], found
        for name in fcd.NAMES:
            assert name in found[0], (name, found)

    def test_an_override_is_taken_whole(self, tmp_path):
        """Criterion 2 (Q3, Keith 2026-11-14): a field the override leaves
        out is not taken from the shared entry."""
        shared = _entry(_shared(), "column_order")
        override = {k: v for k, v in shared.items() if k not in ("name", "formats")}
        override["severity"] = "failure"
        override["changelog"] = [{"date": "2026-11-18", "change": "refused, not warned"}]
        own = _write(tmp_path / "own.yaml", [override])

        found = {d.check: d for d in fcd.definitions(own)}["column_order"]
        assert found.severity == "failure"
        assert found.name == "column_order", "the shared entry's name was inherited"
        assert found.formats == ("csv",)

    def test_an_asset_retires_a_shared_check_while_another_still_runs_it(self, tmp_path):
        """Criterion 4: the override's retired_as_of stops it for that asset
        only; an asset without the override still runs it."""
        override = dict(_entry(_shared(), "column_order"), retired_as_of="2026-11-18",
                        retired_reason="this asset's supplier reorders columns by design")
        own = _write(tmp_path / "own.yaml", [override])

        assert "column_order" not in [d.check for d in fcd.active(path=own)]
        assert "column_order" in [d.check for d in fcd.active(path=tmp_path / "none.yaml")]


class TestTheCollectionsGateRefuses:
    @pytest.mark.parametrize("entries, said", [
        ([{"check": "encoding", "severity": "warning"}, {"check": "encoding", "severity": "failure"}],
         "names 'encoding' a second time"),
        ([{"check": "encoding", "severity": "warning", "colour": "red"}],
         "names colour, which no file check allows"),
    ], ids=["named-twice", "unknown-key"])
    def test_a_bad_asset_file_is_refused(self, entries, said, tmp_path, monkeypatch, capsys):
        """Criterion 10: naming the asset's file and the entry."""
        from qa_tools.common import validate_collections

        own = _write(tmp_path / fcd.FILE, entries)
        monkeypatch.setattr(fcd, "definitions_path", lambda: own)
        assert validate_collections.main() == 1
        out = capsys.readouterr().out
        assert said in out and str(own) in out and "checks[" in out


class TestTheLifecycleGate:
    def test_an_override_changing_a_check_needs_its_own_changelog_entry(self, tmp_path):
        """Criterion 8: the gate fails naming the asset (in the id) and the
        check; with an entry of its own it passes."""
        none = tmp_path / "none.yaml"
        old = cl.parse_file_check_metadata(none)
        override = dict(_entry(_shared(), "column_order"), severity="failure")
        changed = cl.parse_file_check_metadata(_write(tmp_path / "own.yaml", [override]))
        errors = cl.validate(old, changed)
        asset = hierarchy.all_datasets()[0].data_asset_id
        assert errors and all("column_order_file" in e and f"'{asset}." in e for e in errors), errors

        override["changelog"] = [{"date": "2026-11-18", "change": "refused rather than warned"}]
        documented = cl.parse_file_check_metadata(_write(tmp_path / "own.yaml", [override]))
        assert cl.validate(old, documented) == []

    def test_the_move_reads_as_no_new_check(self, tmp_path):
        """Criterion 9: a ref with no shared default and the six in the
        asset's own file yields the same checks as the tree now."""
        before = _write(tmp_path / "former-asset-copy.yaml", _shared()["checks"])
        at_base = cl.parse_file_check_metadata(before, shared_text=None, at_ref=True)
        now = cl.parse_file_check_metadata(tmp_path / "none.yaml")
        assert {c.check_id for c in at_base} == {c.check_id for c in now}
        assert cl.validate(at_base, now) == []


#: The data asset this module's tests act for (C11, Keith 2026-11-02): the
#: shared default is every asset's, so either serves; quarterly's six datasets
#: make the derived-id assertions read more than one.
pytestmark = pytest.mark.asset("quarterly")
