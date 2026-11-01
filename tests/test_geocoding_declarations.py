"""The geocoding datasets' declarations, and the generic gates they pass
(REQ-QAC-294). Each gate test copies the real contract folder, changes one
thing, and asks the gate the collections gate calls; the real files are
untouched. Nothing here reads supply rows or the database."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from qa_tools.common import linked_datasets

REAL = Path(__file__).resolve().parent.parent
LP_SODA = Path("contract/department-of-health/linkage-products-soda-checks.yml")
LP_CONTRACT = Path("contract/department-of-health/linkage-products-contract.yaml")
GEO = ("geo-cp-clients", "geo-ed-presentations")


@pytest.fixture
def repo(tmp_path):
    shutil.copytree(REAL / "contract", tmp_path / "contract")
    return tmp_path


def _asset(repo):
    return repo / "contract" / "data-asset.yaml"


def _dataset(doc, ds_id):
    for agency in doc["hierarchy"]["agencies"]:
        for coll in agency["collections"]:
            for ds in coll["datasets"]:
                if ds["id"] == ds_id:
                    return ds
    raise AssertionError(f"precondition: {ds_id} is in the hierarchy")


def _edit_asset(repo, change):
    doc = yaml.safe_load(_asset(repo).read_text())
    change(doc)
    _asset(repo).write_text(yaml.safe_dump(doc, sort_keys=False))
    return "\n".join(linked_datasets.problems(repo))


def _soda_doc(repo):
    return yaml.safe_load((repo / LP_SODA).read_text())


def _write_soda(repo, doc):
    (repo / LP_SODA).write_text(yaml.safe_dump(doc, sort_keys=False))


def _check(block, linked_check, did):
    return next(c for c in block if isinstance(c, dict) and any(
        isinstance(b, dict) and (b.get("attributes") or {}).get("linked_check") == linked_check
        and (b.get("attributes") or {}).get("linked_dataset") == did for b in c.values()))


def _geo_block(did, cols, table):
    """A geocoding table's own check block holding the referential-and-
    coverage pair for its one source - what REQ-QAC-340 declares."""
    src = {"cp-clients": "cp_clients", "ed-presentations": "ed_presentations"}[did]
    col = cols[0]
    attrs = {"linked_dataset": did, "id_columns": cols, "reads_tables": [src]}
    return [
        {"failed rows": {
            "name": "Rows matching no source record",
            "fail query": (f"SELECT g.id_1, g.id_2, g.census_year FROM {table} g LEFT JOIN {src} s "
                           f"ON CAST(s.{col} AS TEXT) = CAST(g.id_1 AS TEXT) WHERE s.{col} IS NULL"),
            "attributes": {**attrs, "check_id": f"x.{table}.referential", "linked_check": "referential"}}},
        {f"{table}_coverage_percent": {
            f"{table}_coverage_percent query": (
                f"SELECT 100.0 * COUNT(g.id_1) / NULLIF(COUNT(*), 0) FROM {src} s LEFT JOIN "
                f"(SELECT DISTINCT CAST(id_1 AS TEXT) AS id_1 FROM {table}) g "
                f"ON g.id_1 = CAST(s.{col} AS TEXT)"),
            "attributes": {**attrs, "check_id": f"x.{table}.coverage", "linked_check": "coverage"}}},
    ]


class TestTheDeclarations:
    """Criteria 1, 2, 6 to 10 and 12, read from the committed configuration."""

    def test_two_geocoding_datasets_each_linking_one_source_with_no_code(self):
        from qa_tools.common import hierarchy

        cp = hierarchy.dataset("geo-cp-clients")
        ed = hierarchy.dataset("geo-ed-presentations")
        assert (cp.collection_id, cp.dataset_name, cp.table) == (
            "linkage-products", "Client Register Geocodes", "geo_cp_clients")
        assert (ed.collection_id, ed.dataset_name, ed.table) == (
            "linkage-products", "ED Presentations Geocodes", "geo_ed_presentations")
        assert cp.linked == (("cp-clients", None, ("cp_client_id",)),)
        assert ed.linked == (("ed-presentations", None, ("presentation_id",)),)
        assert cp.arrival_pattern == r"geo_cp_clients\.csv"
        assert ed.arrival_pattern == r"geo_ed_presentations\.csv"

    def test_the_schema_accepts_an_entry_with_no_code(self):
        from qa_tools.common.schemas import LinkedDataset

        assert LinkedDataset(dataset="cp-clients", id_columns=["cp_client_id"]).code is None

    def _table(self, name):
        doc = yaml.safe_load((REAL / LP_CONTRACT).read_text())
        return next(t for t in doc["schema"] if t["name"] == name)

    @pytest.mark.parametrize("table", ["geo_cp_clients", "geo_ed_presentations"])
    def test_each_table_has_exactly_the_agreed_columns(self, table):
        props = {p["name"]: p for p in self._table(table)["properties"]}
        keys = {p["name"] for p in self._table("linkage_keys")["properties"] if p["name"].startswith("id_")}
        assert list(props) == [*sorted(keys), "census_year", "sa2_code", "lga_code", "match_level"]
        required = {n for n, p in props.items() if p.get("required")}
        assert required == {"id_1", "census_year", "match_level"}
        assert all(props[k]["logicalType"] == "string" for k in keys)

    @pytest.mark.parametrize("table", ["geo_cp_clients", "geo_ed_presentations"])
    def test_allowed_values_formats_and_key(self, table):
        props = {p["name"]: p for p in self._table(table)["properties"]}
        assert [e["value"] for e in props["match_level"]["enum"]] == [
            "address", "postcode", "suburb", "not geocoded"]
        assert props["sa2_code"]["logicalTypeOptions"]["pattern"] == "^[0-9]{9}$"
        assert props["lga_code"]["logicalTypeOptions"]["pattern"] == "^[0-9]{5}$"
        key = sorted((p["primaryKeyPosition"], n) for n, p in props.items() if p.get("primaryKey"))
        assert [n for _pos, n in key] == ["id_1", "census_year"]
        assert not any(p.get("unique") for p in props.values())

    @pytest.mark.parametrize("table", ["geo_cp_clients", "geo_ed_presentations"])
    def test_no_column_describes_a_person_or_a_place_finer_than_sa2(self, table):
        props = [p["name"] for p in self._table(table)["properties"]]
        for word in ("address", "lat", "lon", "coord", "mesh", "sa1", "name", "birth", "dob"):
            assert not any(word in p for p in props), (word, props)

    def test_descriptions_say_synthetic_and_cover_both_releases(self):
        doc = yaml.safe_load((REAL / LP_CONTRACT).read_text())
        for table in ("geo_cp_clients", "geo_ed_presentations"):
            text = self._table(table)["description"]
            assert "SYNTHETIC" in text and "geocoding product" in text and "no address" in text
        purpose = doc["description"]["purpose"]
        assert "linkage" in purpose and "geocoding release" in purpose
        pres = yaml.safe_load((REAL / "contract" / "presentation.yaml").read_text())
        provenance = next(v for k, v in _walk_presentation(pres) if k == "linkage-products")["provenance"]
        assert "linkage and geocoding releases" in provenance


def _walk_presentation(doc):
    for section in doc.values():
        if isinstance(section, dict):
            for k, v in section.items():
                if isinstance(v, dict):
                    yield k, v


class TestTheCalendar:
    """Criterion 11: owed exactly the source's periods, due 19:00, 8 hours."""

    @pytest.mark.parametrize("geo,src", [("geo-cp-clients", "cp-clients"),
                                         ("geo-ed-presentations", "ed-presentations")])
    def test_each_owes_exactly_its_sources_periods(self, geo, src):
        from qa_tools.common import schedule

        owed = [p.name for p in schedule.periods_for_dataset(geo) if p.expected]
        assert owed, "precondition: the geocoding dataset owes periods"
        assert owed == [p.name for p in schedule.periods_for_dataset(src) if p.expected]

    def test_the_ed_gap_is_mirrored_and_the_due_time_is_its_own(self):
        from datetime import timedelta

        from qa_tools.common import agreement, schedule

        assert "2015-Q4" not in {p.name for p in schedule.periods_for_dataset("geo-ed-presentations")}
        for ds in GEO:
            for v in agreement.current().dataset(ds).participation:
                assert (str(v.expected_time)[:5], v.grace) == ("19:00", timedelta(hours=8)), (ds, v)

    def test_a_participation_that_disagrees_with_its_source_fails_naming_the_first_period(self, repo):
        cal_path = repo / "contract" / "calendar.yaml"
        cal = yaml.safe_load(cal_path.read_text())
        entry = next(d for d in cal["datasets"] if d["id"] == "geo-cp-clients")
        entry["participation"]["versions"][0]["effective_from"] = "2015-07-01"
        cal_path.write_text(yaml.safe_dump(cal, sort_keys=False))
        text = "\n".join(linked_datasets.participation_problems(repo))
        assert text.startswith("geo-cp-clients does not owe 2015-Q2, which its source cp-clients does"), text

    def test_the_real_participation_agrees(self):
        assert linked_datasets.participation_problems(REAL) == []


class TestCriterionFour:
    """The generic shape rules for a linked-dataset declaration."""

    def test_the_real_configuration_passes(self):
        assert linked_datasets.problems(REAL) == []

    def test_no_code_while_the_table_has_a_dataset_column(self, repo):
        def change(doc):
            del _dataset(doc, "linkage-keys")["linked_datasets"][0]["code"]
        text = _edit_asset(repo, change)
        assert "linkage-keys links 'cp-clients' with no code" in text, text

    def test_a_code_while_the_table_has_none(self, repo):
        def change(doc):
            _dataset(doc, "geo-cp-clients")["linked_datasets"][0]["code"] = "DOC_CLIENTS"
        text = _edit_asset(repo, change)
        assert "geo-cp-clients links 'cp-clients' with the code 'DOC_CLIENTS'" in text, text

    def test_two_entries_without_a_code(self, repo):
        def change(doc):
            _dataset(doc, "geo-cp-clients")["linked_datasets"].append(
                {"dataset": "ed-presentations", "id_columns": ["presentation_id"]})
        text = _edit_asset(repo, change)
        assert "geo-cp-clients declares 2 linked datasets without a code" in text, text

    def test_two_datasets_geocoding_the_same_source(self, repo):
        def change(doc):
            _dataset(doc, "geo-ed-presentations")["linked_datasets"] = [
                {"dataset": "cp-clients", "id_columns": ["cp_client_id"]}]
        text = _edit_asset(repo, change)
        assert "each declare 'cp-clients' as their one linked dataset without a code" in text, text

    def test_a_source_column_its_contract_lacks(self, repo):
        def change(doc):
            _dataset(doc, "geo-ed-presentations")["linked_datasets"][0]["id_columns"] = ["nope"]
        text = _edit_asset(repo, change)
        assert "geo-ed-presentations links 'ed-presentations' by the column 'nope'" in text, text

    def test_more_identifier_columns_than_the_tables_id_n(self, repo):
        def change(doc):
            _dataset(doc, "geo-cp-clients")["linked_datasets"][0]["id_columns"] = [
                "cp_client_id", "suburb", "postcode"]
        text = _edit_asset(repo, change)
        assert "geo-cp-clients links 'cp-clients' by 3 identifier columns" in text, text

    def test_a_source_on_another_calendar(self, repo):
        def change(doc):
            _dataset(doc, "geo-cp-clients")["linked_datasets"][0].update(
                dataset="birth-registrations", id_columns=["registration_number"])
        text = _edit_asset(repo, change)
        assert "geo-cp-clients links 'birth-registrations'" in text and "calendar" in text, text


class TestCriterionFiveEachRuleReadsItsOwnBlock:
    """Criterion 5, seen failing first against the whole-file rule: a
    geocoding check naming cp-clients counted toward linkage's pair."""

    def test_a_deleted_linkage_referential_check_still_fails_with_geocoding_blocks_present(self, repo):
        doc = _soda_doc(repo)
        doc["checks for geo_cp_clients"] = _geo_block("cp-clients", ["cp_client_id"], "geo_cp_clients")
        doc["checks for geo_ed_presentations"] = _geo_block(
            "ed-presentations", ["presentation_id"], "geo_ed_presentations")
        block = doc["checks for linkage_keys"]
        block.remove(_check(block, "referential", "cp-clients"))
        _write_soda(repo, doc)
        problems = linked_datasets.problems(repo)
        assert ("linkage-keys links 'cp-clients' without its referential check "
                "(REQ-QAC-333 criterion 8).") in problems, problems

    def test_a_geocoding_block_missing_its_coverage_check_fails_naming_it(self, repo):
        doc = _soda_doc(repo)
        doc["checks for geo_cp_clients"] = _geo_block("cp-clients", ["cp_client_id"], "geo_cp_clients")[:1]
        doc["checks for geo_ed_presentations"] = _geo_block(
            "ed-presentations", ["presentation_id"], "geo_ed_presentations")
        _write_soda(repo, doc)
        problems = linked_datasets.problems(repo)
        assert ("geo-cp-clients links 'cp-clients' without its coverage check "
                "(REQ-QAC-333 criterion 8).") in problems, problems

    def test_id_counts_are_keyed_by_the_source_dataset_where_there_is_no_code(self, repo):
        doc = _soda_doc(repo)
        geo = _geo_block("cp-clients", ["cp_client_id"], "geo_cp_clients")
        geo.append({"failed rows": {"name": "Expected identifiers present",
                                    "fail query": "SELECT id_1 FROM geo_cp_clients WHERE id_1 IS NULL",
                                    "attributes": {"check_id": "x.geo.expected",
                                                   "id_counts": {"cp-clients": 2}}}})
        doc["checks for geo_cp_clients"] = geo
        doc["checks for geo_ed_presentations"] = _geo_block(
            "ed-presentations", ["presentation_id"], "geo_ed_presentations")
        _write_soda(repo, doc)
        problems = "\n".join(linked_datasets.problems(repo))
        assert "check x.geo.expected states 2 identifier(s) for cp-clients" in problems, problems


class TestCriterionFourteenValidValuesAreTheCodeColumns:
    """Seen failing first against the rule that compared EVERY valid-values
    list in the collection's file with the mapping's codes."""

    def _with_match_level_values(self, repo):
        doc = _soda_doc(repo)
        for did, cols, table in (("cp-clients", ["cp_client_id"], "geo_cp_clients"),
                                 ("ed-presentations", ["presentation_id"], "geo_ed_presentations")):
            doc[f"checks for {table}"] = [*_geo_block(did, cols, table), {"invalid_count(match_level)": {
                "valid values": ["address", "postcode", "suburb", "not geocoded"],
                "fail": "when > 0", "attributes": {"check_id": f"x.{table}.match_level"}}}]
        return doc

    def test_match_level_values_in_a_geocoding_block_pass(self, repo):
        _write_soda(repo, self._with_match_level_values(repo))
        assert linked_datasets.problems(repo) == []

    def test_a_linkage_dataset_column_check_stating_a_code_its_mapping_lacks_still_fails(self, repo):
        doc = self._with_match_level_values(repo)
        block = doc["checks for linkage_keys"]
        check = next(c for c in block if "invalid_count(dataset)" in c)
        check["invalid_count(dataset)"]["valid values"] = ["DOC_CLIENTS", "EDDC_PRESENTATION", "X"]
        _write_soda(repo, doc)
        text = "\n".join(linked_datasets.problems(repo))
        assert "dataset.invalid_count_soda states the valid values" in text and "'X'" in text, text


class TestCriterionThreeThePlacingConfiguration:
    """contract/synthetic_inputs.yaml: generator-only, generic, gated."""

    def _edit(self, repo, change):
        path = repo / "contract" / "synthetic_inputs.yaml"
        doc = yaml.safe_load(path.read_text())
        change({d["dataset"]: d for d in doc["datasets"]})
        path.write_text(yaml.safe_dump(doc, sort_keys=False))
        from generator import synthetic_inputs

        return "\n".join(synthetic_inputs.problems(repo))

    def test_the_declared_placings_finest_first(self):
        from generator import synthetic_inputs

        p = synthetic_inputs.placings()
        assert p["geo-cp-clients"].place_by == (("suburb", "suburb"), ("postcode", "postcode"))
        assert p["geo-ed-presentations"].place_by == (("postcode", "postcode"),)
        assert {x.placed_column for x in p.values()} == {"match_level"}
        assert {x.unplaced_value for x in p.values()} == {"not geocoded"}
        assert synthetic_inputs.problems() == []

    def test_a_record_is_placed_by_its_finest_present_column(self):
        from generator import synthetic_inputs

        cp = synthetic_inputs.placings()["geo-cp-clients"]
        assert cp.value_for({"suburb": "Ascot", "postcode": "6104"}) == "suburb"
        assert cp.value_for({"suburb": " ", "postcode": "6104"}) == "postcode"
        assert cp.value_for({"suburb": None, "postcode": ""}) == "not geocoded"

    def test_a_column_the_source_contract_lacks_fails_naming_it(self, repo):
        text = self._edit(repo, lambda d: d["geo-ed-presentations"]["place_by"].append(
            {"column": "suburb", "value": "suburb"}))
        assert "geo-ed-presentations places by the column 'suburb'" in text, text

    def test_a_value_outside_the_allowed_values_fails_naming_it(self, repo):
        def change(d):
            d["geo-cp-clients"]["place_by"][0]["value"] = "locality"
        text = self._edit(repo, change)
        assert "geo-cp-clients declares the value 'locality'" in text, text

    def test_an_unplaced_value_outside_the_allowed_values_fails(self, repo):
        def change(d):
            d["geo-cp-clients"]["unplaced_value"] = "ungeocoded"
        assert "'ungeocoded'" in self._edit(repo, change)

    def test_it_is_an_asset_wide_file(self):
        from qa_tools.common import validate_collections

        assert "synthetic_inputs.yaml" in validate_collections.ASSET_WIDE

    def test_no_shared_module_carries_a_placing_word(self):
        """Architecture rule with no behaviour to observe (criterion 3): the
        placing keys live in generator-only configuration, never on the
        shared schema or the hierarchy's linked tuple."""
        for module in ("qa_tools/common/schemas.py", "qa_tools/common/hierarchy.py"):
            text = (REAL / module).read_text()
            for word in ("place_by", "placed_column", "unplaced_value", "match_level"):
                assert word not in text, (module, word)
