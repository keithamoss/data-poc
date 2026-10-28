"""A cache built from a configuration file always answers for what the file
says now (REQ-PIPE-254, signed by Keith 2026-10-24).

Every test here drives one of the nine real functions against a file it
edits or swaps, and clears no cache: the point of the requirement is that
nothing has to be cleared.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
from pathlib import Path

import pytest
import yaml

from pipeline import build_dashboard_data
from qa_tools import collections
from qa_tools.common import (agreement, arrival_patterns, asset_time, config_yaml, hierarchy,
                             presentation)
from qa_tools.tools import run_datacontract, run_dbt

REAL = Path(__file__).resolve().parent.parent
CONTRACT = REAL / "contract"
CP_CONTRACT = CONTRACT / "child-protection-family-support" / "child-protection-contract.yaml"
CP_SCHEMA = REAL / "dbt_project" / "models" / "child-protection" / "schema.yml"

#: Same-length substitutions, so an edit keeps the file's size.
DATASET_NAME = ("Client Register", "Client RegisteR")
ZONE = ("Australia/Perth", "Australia/Eucla")
PATTERN = (r"'cp_notifications\.csv'", r"'cp_notificationz\.csv'")
EXPECTED = ('expected_time: "09:00"', 'expected_time: "10:00"')
DBT_ID = ("cp_client_id.unique_dbt", "cp_client_id.uniquE_dbt")
DC_NAME = ("Date of birth in a plausible range", "Date of birth in a plausible rangE")
BLURB = ("Civil registration of life events", "Civil registration of life eventS")


def _copy(src: Path, tmp_path: Path) -> Path:
    dest = tmp_path / src.name
    shutil.copyfile(src, dest)
    return dest


def edit_in_place(path: Path, old: str, new: str) -> None:
    """Replace `old` with `new` (same length) and put the modification time
    back, so neither size nor mtime says the file changed."""
    assert len(old) == len(new)
    before = os.stat(path)
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} is not in {path}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    after = os.stat(path)
    assert (after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns)


@pytest.fixture
def asset(tmp_path, monkeypatch) -> Path:
    """A copy of data-asset.yaml every reader of it is pointed at."""
    path = _copy(CONTRACT / "data-asset.yaml", tmp_path)
    monkeypatch.setattr(hierarchy, "DATA_ASSET_YAML", path)
    monkeypatch.setattr(asset_time, "DATA_ASSET_YAML", path)
    return path


@pytest.fixture
def calendar(tmp_path, monkeypatch) -> Path:
    path = _copy(CONTRACT / "calendar.yaml", tmp_path)
    monkeypatch.setattr(agreement, "CALENDAR_YAML", path)
    return path


def _client_name() -> str:
    return hierarchy.dataset("cp-clients").dataset_name


def _registry_client_name() -> str:
    [d] = [d for d in collections.by_id("child-protection").datasets
           if d.dataset_id == "cp-clients"]
    return d.dataset_name


def _zone() -> str:
    return asset_time.timezone_versions()[0].zone.key


def _has_notifications_pattern() -> bool:
    return arrival_patterns.compiled_patterns()["cp-notifications"].fullmatch(
        "cp_notifications.csv") is not None


def _first_expected_time() -> str:
    """Child Protection's earliest due time, stated once for the collection
    and resolved onto each of its datasets."""
    return agreement.current().resolved_versions("cp-clients")[0].expected_time


# ---- criterion 2: an in-place edit, same size and mtime ---------------------

class TestAnEditInPlaceIsSeenOnTheNextCall:

    def test_the_hierarchy(self, asset):
        assert _client_name() == DATASET_NAME[0]
        edit_in_place(asset, *DATASET_NAME)
        assert _client_name() == DATASET_NAME[1]

    def test_the_collection_registry(self, asset):
        assert _registry_client_name() == DATASET_NAME[0]
        edit_in_place(asset, *DATASET_NAME)
        assert _registry_client_name() == DATASET_NAME[1]

    def test_the_timezone_versions(self, asset):
        assert _zone() == ZONE[0]
        edit_in_place(asset, *ZONE)
        assert _zone() == ZONE[1]

    def test_the_arrival_patterns(self, asset):
        assert _has_notifications_pattern()
        edit_in_place(asset, *PATTERN)
        assert not _has_notifications_pattern()

    def test_the_agreement(self, calendar):
        assert _first_expected_time() == "09:00"
        edit_in_place(calendar, *EXPECTED)
        assert _first_expected_time() == "10:00"

    def test_the_dbt_check_ids(self, tmp_path):
        path = str(_copy(CP_SCHEMA, tmp_path))
        key = ("stg_cp_clients", "cp_client_id", "unique")
        assert run_dbt._check_ids(path)[key].endswith(DBT_ID[0])
        edit_in_place(Path(path), *DBT_ID)
        assert run_dbt._check_ids(path)[key].endswith(DBT_ID[1])

    def test_the_datacontract_names(self, tmp_path):
        path = str(_copy(CP_CONTRACT, tmp_path))
        assert DC_NAME[0] in run_datacontract._authored_names(path).values()
        edit_in_place(Path(path), *DC_NAME)
        assert DC_NAME[1] in run_datacontract._authored_names(path).values()

    def test_the_presentation(self, tmp_path):
        path = _copy(CONTRACT / "presentation.yaml", tmp_path)
        assert presentation.agency_blurbs(path)["registry-services"].startswith(BLURB[0])
        edit_in_place(path, *BLURB)
        assert presentation.agency_blurbs(path)["registry-services"].startswith(BLURB[1])

    def test_the_dashboard_builds_contract(self, tmp_path):
        path = str(_copy(CP_CONTRACT, tmp_path))
        assert DC_NAME[0] in json.dumps(build_dashboard_data._contract_at(path))
        edit_in_place(Path(path), *DC_NAME)
        assert DC_NAME[1] in json.dumps(build_dashboard_data._contract_at(path))


# ---- criterion 3: a patched path, and back -----------------------------------

class TestAPatchedPathIsReadAndUndoneWithNothingCleared:

    def test_the_hierarchy_and_what_is_built_from_it(self, tmp_path, monkeypatch):
        assert _client_name() == DATASET_NAME[0]
        assert _registry_client_name() == DATASET_NAME[0]
        assert _has_notifications_pattern()
        other = _copy(CONTRACT / "data-asset.yaml", tmp_path)
        edit_in_place(other, *DATASET_NAME)
        edit_in_place(other, *PATTERN)
        with monkeypatch.context() as m:
            m.setattr(hierarchy, "DATA_ASSET_YAML", other)
            assert _client_name() == DATASET_NAME[1]
            assert _registry_client_name() == DATASET_NAME[1]
            assert not _has_notifications_pattern()
        assert _client_name() == DATASET_NAME[0]
        assert _registry_client_name() == DATASET_NAME[0]
        assert _has_notifications_pattern()

    def test_the_timezone_versions(self, tmp_path, monkeypatch):
        assert _zone() == ZONE[0]
        other = _copy(CONTRACT / "data-asset.yaml", tmp_path)
        edit_in_place(other, *ZONE)
        with monkeypatch.context() as m:
            m.setattr(asset_time, "DATA_ASSET_YAML", other)
            assert _zone() == ZONE[1]
        assert _zone() == ZONE[0]

    def test_the_agreement(self, tmp_path, monkeypatch):
        assert _first_expected_time() == "09:00"
        other = _copy(CONTRACT / "calendar.yaml", tmp_path)
        edit_in_place(other, *EXPECTED)
        with monkeypatch.context() as m:
            m.setattr(agreement, "CALENDAR_YAML", other)
            assert _first_expected_time() == "10:00"
        assert _first_expected_time() == "09:00"


# ---- criterion 4: unchanged content is neither parsed nor built again --------

class TestAnUnchangedFileIsNotParsedOrBuiltAgain:

    @pytest.fixture
    def parses(self, monkeypatch):
        calls = []
        real = config_yaml.parse

        def counted(*a, **k):
            calls.append(a)
            return real(*a, **k)
        monkeypatch.setattr(config_yaml, "parse", counted)
        return calls

    @pytest.mark.parametrize("call", [
        hierarchy._load, collections._load, arrival_patterns.compiled_patterns,
        asset_time.timezone_versions, agreement.current,
        lambda: run_dbt._check_ids(str(CP_SCHEMA)),
        lambda: run_datacontract._authored_names(str(CP_CONTRACT)),
    ], ids=["hierarchy", "collections", "patterns", "timezone", "agreement", "dbt",
            "datacontract"])
    def test_a_built_value_is_the_same_value_with_no_parse(self, parses, call):
        first = call()
        parses.clear()
        assert call() is first
        assert parses == []

    @pytest.mark.parametrize("call", [
        lambda: presentation.load(CONTRACT / "presentation.yaml"),
        lambda: build_dashboard_data._contract_at(str(CP_CONTRACT)),
    ], ids=["presentation", "contract"])
    def test_a_plain_document_is_not_parsed_again(self, monkeypatch, call):
        first = call()
        raw = []
        real = config_yaml._parse_raw
        monkeypatch.setattr(config_yaml, "_parse_raw", lambda t: raw.append(t) or real(t))
        assert call() == first
        assert raw == []


# ---- criterion 6: one read per built value -----------------------------------

class TestOneValueIsBuiltFromOneRead:
    """The registry is built from the collections AND the hierarchy's
    datasets. A file replaced between those two halves must not give a
    registry whose collection names one version and whose datasets the
    other."""

    def test_the_registry_never_combines_two_versions(self, asset, monkeypatch):
        text = asset.read_text()
        new = text.replace("name: Child Protection\n", "name: Child ProtectioN\n", 1)
        assert new != text
        real = config_yaml.parse
        swapped = []

        def parse_then_replace(*a, **k):
            out = real(*a, **k)
            if not swapped:
                swapped.append(True)
                asset.write_text(new)
            return out
        monkeypatch.setattr(config_yaml, "parse", parse_then_replace)
        coll = collections.by_id("child-protection")
        assert coll.datasets, "the collection has datasets to compare"
        assert {d.collection_name for d in coll.datasets} == {coll.name}
        assert swapped, "the file was replaced between reads"
        assert collections.by_id("child-protection").name == "Child ProtectioN"


# ---- criterion 7: no caller's change reaches another -------------------------

class TestNoCallersChangeReachesAnother:

    def test_the_hierarchy_tree_cannot_be_changed(self):
        with pytest.raises(TypeError):
            hierarchy._load()[1]["invented"] = None
        datasets = hierarchy.all_datasets()
        datasets.clear()
        assert hierarchy.all_datasets()

    def test_the_registry_and_patterns_cannot_be_changed(self):
        assert isinstance(collections._load(), tuple)
        with pytest.raises(TypeError):
            arrival_patterns.compiled_patterns()["invented"] = None

    def test_the_dbt_lookup_cannot_be_changed(self):
        with pytest.raises(TypeError):
            run_dbt._check_ids(str(CP_SCHEMA))[("x", None, "y")] = "invented"
        assert ("x", None, "y") not in run_dbt._check_ids(str(CP_SCHEMA))

    def test_the_datacontract_names_cannot_be_changed(self):
        with pytest.raises(TypeError):
            run_datacontract._authored_names(str(CP_CONTRACT))["invented"] = "x"
        assert "invented" not in run_datacontract._authored_names(str(CP_CONTRACT))

    def test_the_presentation_is_each_callers_own(self):
        path = CONTRACT / "presentation.yaml"
        mine = presentation.load(path)
        mine["agencies"]["registry-services"]["blurb"] = "changed by one caller"
        mine["invented"] = True
        theirs = presentation.load(path)
        assert "invented" not in theirs
        assert theirs["agencies"]["registry-services"]["blurb"].startswith(BLURB[0])

    def test_the_dashboard_contract_is_each_callers_own(self):
        mine = build_dashboard_data._contract_at(str(CP_CONTRACT))
        mine["schema"].clear()
        assert build_dashboard_data._contract_at(str(CP_CONTRACT))["schema"]


# ---- criterion 8: threads, while the file is replaced ------------------------

class TestThreadsDuringAReplacement:

    def test_every_value_is_wholly_one_version(self, asset):
        text = asset.read_text()
        versions = [text.replace("name: Child Protection\n", f"name: Child Protection {n}\n", 1)
                    .replace("name: Client Register\n", f"name: Client Register {n}\n", 1)
                    for n in "AB"]
        assert all(v != text for v in versions)
        stop = threading.Event()
        bad, seen = [], set()

        def writer():
            i = 0
            while not stop.is_set():
                tmp = asset.with_suffix(".tmp")
                tmp.write_text(versions[i % 2])
                os.replace(tmp, asset)
                i += 1

        def reader():
            for _ in range(150):
                coll = next(c for c in collections._load() if c.id == "child-protection")
                tag = coll.name[-1]
                seen.add(tag)
                names = {d.collection_name for d in coll.datasets}
                client = next(d for d in coll.datasets if d.dataset_id == "cp-clients")
                if names != {coll.name} or not client.dataset_name.endswith(tag):
                    bad.append((coll.name, names, client.dataset_name))

        asset.write_text(versions[0])
        w = threading.Thread(target=writer)
        readers = [threading.Thread(target=reader) for _ in range(6)]
        w.start()
        for t in readers:
            t.start()
        for t in readers:
            t.join()
        stop.set()
        w.join()
        assert not bad, bad[:3]
        assert seen <= {"A", "B"} and seen


# ---- criterion 9: a failure is raised every time and never remembered --------

BROKEN = "hierarchy: [unclosed\n"


class TestAFailureIsNeverRemembered:

    def _broken_then_fixed(self, path: Path, good: str, call):
        path.write_text(BROKEN)
        for _ in range(2):
            with pytest.raises(yaml.YAMLError) as exc:
                call()
            assert path.name in str(exc.value)
        path.write_text(good)
        return call()

    def test_the_hierarchy_and_registry(self, asset):
        good = asset.read_text()
        assert self._broken_then_fixed(asset, good, hierarchy.all_datasets)
        assert self._broken_then_fixed(asset, good, collections.all_collections)
        assert self._broken_then_fixed(asset, good, arrival_patterns.compiled_patterns)
        assert self._broken_then_fixed(asset, good, asset_time.timezone_versions)

    def test_the_agreement(self, calendar):
        good = calendar.read_text()
        assert self._broken_then_fixed(calendar, good, agreement.current).datasets

    def test_a_missing_file_raises_every_call(self, tmp_path, monkeypatch):
        missing = tmp_path / "nowhere.yaml"
        monkeypatch.setattr(hierarchy, "DATA_ASSET_YAML", missing)
        monkeypatch.setattr(asset_time, "DATA_ASSET_YAML", missing)
        monkeypatch.setattr(agreement, "CALENDAR_YAML", missing)
        for call in (hierarchy.all_datasets, collections.all_collections,
                     asset_time.timezone_versions, agreement.current,
                     lambda: run_dbt._check_ids(str(missing)),
                     lambda: run_datacontract._authored_names(str(missing)),
                     lambda: presentation.load(missing),
                     lambda: build_dashboard_data._contract_at(str(missing))):
            for _ in range(2):
                with pytest.raises(FileNotFoundError):
                    call()

    def test_the_path_keyed_ones(self, tmp_path):
        for src, call in ((CP_SCHEMA, run_dbt._check_ids),
                          (CP_CONTRACT, run_datacontract._authored_names),
                          (CONTRACT / "presentation.yaml", presentation.load),
                          (CP_CONTRACT, build_dashboard_data._contract_at)):
            path = tmp_path / f"{len(list(tmp_path.iterdir()))}-{src.name}"
            good = src.read_text()
            assert self._broken_then_fixed(path, good, lambda p=path, c=call: c(str(p)))


# ---- criterion 15: content is read on every call -----------------------------

class TestTheContentIsReadOnEveryCall:

    def test_a_cached_value_still_reads_the_file(self, asset, monkeypatch):
        hierarchy.all_datasets()
        reads = []
        real = config_yaml.read
        monkeypatch.setattr(config_yaml, "read", lambda p: reads.append(p) or real(p))
        hierarchy.all_datasets()
        agreement.current()
        assert asset in reads and agreement.CALENDAR_YAML in reads


# ---- the store's own bound (NFR MEMORY) --------------------------------------

class TestTheStoreIsBounded:

    def test_it_keeps_the_newest_versions_per_file(self):
        store = config_yaml.Built(versions=2)
        builds = []
        for text in ("a", "b", "c"):
            store.get("f", text, lambda t=text: builds.append(t) or t.upper())
        assert store.get("f", "c", lambda: "rebuilt") == "C"
        assert store.get("f", "b", lambda: "rebuilt") == "B"
        assert store.get("f", "a", lambda: "rebuilt") == "rebuilt"
        assert builds == ["a", "b", "c"]


# ---- criterion 19: a value taken once and passed down ------------------------

class TestAValuePassedDownAnswersForTheReadItCameFrom:
    """The hot call sites take the hierarchy's table index or the zone
    versions once and pass them down, rather than reading the file for each
    of tens of thousands of lookups. A value passed down answers for the
    read it was taken from; without one, the file is read now."""

    def test_the_table_index(self, asset):
        from qa_tools.common import supply_status

        taken = hierarchy.by_table()
        assert taken["cp_clients"].dataset_name == DATASET_NAME[0]
        edit_in_place(asset, *DATASET_NAME)
        assert hierarchy.dataset_for_table("cp_clients", taken).dataset_name == DATASET_NAME[0]
        assert hierarchy.dataset_for_table("cp_clients").dataset_name == DATASET_NAME[1]
        assert supply_status.dataset_of("cp_clients", taken) == "cp-clients"
        assert supply_status.dataset_of("no_such_table", taken) is None
        with pytest.raises(hierarchy.UnknownDatasetError, match="no_such_table"):
            hierarchy.dataset_for_table("no_such_table", taken)

    def test_the_zone_versions(self, asset):
        from datetime import UTC, date, datetime

        taken = asset_time.timezone_versions()
        edit_in_place(asset, *ZONE)
        day, instant = date(2026, 1, 1), datetime(2026, 1, 1, 12, tzinfo=UTC)
        assert asset_time.zone_on(day, taken).key == ZONE[0]
        assert asset_time.zone_at(instant, taken).key == ZONE[0]
        assert asset_time.zone_on(day).key == ZONE[1]
        assert asset_time.localise(instant, taken).tzinfo.key == ZONE[0]
        assert asset_time.end_of_day(day, taken).tzinfo.key == ZONE[0]

    def test_a_holdings_reads_the_hierarchy_once(self, monkeypatch):
        from qa_tools.common import supply_status

        holdings = supply_status.Holdings({("cp-clients", "2024-Q1"): "s1"})
        reads = []
        real = config_yaml.read
        monkeypatch.setattr(config_yaml, "read", lambda p: reads.append(p) or real(p))
        from qa_tools.common import qa_store

        record = {"reads": {"cp_clients": {"state": qa_store.READ, "supply_id": "s1"}}}
        for _ in range(5):
            assert supply_status._matches(holdings, record["reads"], "2024-Q1")
        assert len(reads) == 1
