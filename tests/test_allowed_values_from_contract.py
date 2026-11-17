"""REQ-QAC-389: each QA adapter's statistics read a column's allowed values
from the collection's ODCS contract at run time, through one reader in
asset_model/, and Emergency Department's age_group gains a real contract rule
that datacontract-cli checks.

Driven through the real entry points: compute_dataset_stats (what a run
records), the orchestrator's run_one (what refuses before any tool runs), the
collections gate's main() and datacontract-cli itself against a real schema.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
import yaml

from asset_model import collections as declared_collections
from asset_model import contract_values
from qa_tools.tools import dataset_stats

BDM, ED, LP = "civil-registration", "emergency-department", "linkage-products"
AGE_GROUP_ID = ("quarterly:department-of-health:emergency-department:ed-presentations:"
                "age_group:invalidValues_datacontract")
TEN_BANDS = ["0-4", "5-14", "15-24", "25-34", "35-44", "45-54", "55-64", "65-74", "75-84", "85+"]


def _contract(collection_id: str) -> dict:
    return yaml.safe_load(Path(declared_collections.by_id(collection_id).check_file("contract"))
                          .read_text())


def _column(doc: dict, table: str, column: str) -> dict:
    model = next(m for m in doc["schema"] if m["name"] == table)
    return next(p for p in model["properties"] if p["name"] == column)


def _use_contract(monkeypatch, tmp_path, collection_id: str, doc: dict) -> Path:
    """Point the collection's contract at an edited copy - what an edit to the
    committed contract does, without touching it."""
    path = tmp_path / "edited-contract.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False))
    real = declared_collections.Collection.check_file

    def check_file(self, kind, *, retired=False):
        if self.id == collection_id and kind == "contract" and not retired:
            return str(path)
        return real(self, kind, retired=retired)

    monkeypatch.setattr(declared_collections.Collection, "check_file", check_file)
    return path


def _sex_rule(doc: dict) -> dict:
    return next(r for r in _column(doc, "birth_registrations", "sex")["quality"]
                if r["metric"] == "invalidValues")


def _births(*sexes: str):
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE birth_registrations (sex VARCHAR, place_of_birth_suburb VARCHAR, "
                 "date_of_birth DATE, date_registered DATE, extract_timestamp TIMESTAMP)")
    for sex in sexes:
        conn.execute("INSERT INTO birth_registrations VALUES (?, 'Fremantle', '2020-01-01', "
                     "'2020-01-05', '2020-01-05 10:00:00')", [sex])
    return conn


_ARRIVAL = {"run_id": "run_01", "run_index": 1, "delivery": "d",
            "received_at": "2020-01-05T06:00:00+00:00"}


@pytest.mark.asset("daily")
class TestTheStatisticsCountAgainstTheContract:
    def test_a_value_added_to_the_contract_is_counted_by_the_next_run(self, monkeypatch, tmp_path):
        """Criteria 1 and 3: 'U' is invalid until the contract lists it, then
        counted in the order the contract declares it."""
        before = dataset_stats.compute_dataset_stats(BDM, _births("M", "U"), _ARRIVAL)
        assert before["value_counts"]["sex"] == [["M", 1], ["F", 0], ["X", 0],
                                                 ["(invalid code)", 1]]
        assert before["check_aggregates"]["birth_registrations.sex"]["total_invalid"] == 1

        doc = _contract(BDM)
        _sex_rule(doc)["arguments"]["validValues"] = ["U", "M", "F", "X"]
        _use_contract(monkeypatch, tmp_path, BDM, doc)

        after = dataset_stats.compute_dataset_stats(BDM, _births("M", "U"), _ARRIVAL)
        assert after["value_counts"]["sex"] == [["U", 1], ["M", 1], ["F", 0], ["X", 0]]
        assert after["check_aggregates"]["birth_registrations.sex"]["total_invalid"] == 0

    def test_a_column_with_no_list_is_refused_before_any_tool_runs(self, monkeypatch, tmp_path):
        """Criterion 4 and NFR RELIABILITY: never an empty list that would
        count every value invalid - a named refusal, and no tool is asked."""
        from qa_tools.tools import orchestrate

        doc = _contract(BDM)
        prop = _column(doc, "birth_registrations", "sex")
        prop["quality"] = [r for r in prop["quality"] if r["metric"] != "invalidValues"]
        path = _use_contract(monkeypatch, tmp_path, BDM, doc)

        asked = []
        for name in ("run_dbt", "run_soda", "run_datacontract", "run_evidently"):
            module = getattr(orchestrate, name)
            monkeypatch.setattr(module, "evaluate", lambda *a, _n=name, **k: asked.append(_n))
        monkeypatch.setattr(orchestrate, "open_run", lambda *a, **k: asked.append("open_run"))

        with pytest.raises(contract_values.AllowedValuesError) as refused:
            orchestrate.run_one(BDM, dict(_ARRIVAL, run_id="run_refused"),
                                "2020-01-05T06:00:00Z", "t@example.com")
        message = str(refused.value)
        assert str(path) in message and "birth_registrations.sex" in message
        assert "add an invalidValues rule or `enum:` to sex in" in message
        assert asked == []

    def test_the_collections_gate_fails_on_the_same_condition(self, monkeypatch, tmp_path, capsys):
        """Criterion 4: the gate, without a database."""
        from qa_tools.common import validate_collections

        doc = _contract(BDM)
        prop = _column(doc, "birth_registrations", "sex")
        prop["quality"] = [r for r in prop["quality"] if r["metric"] != "invalidValues"]
        _use_contract(monkeypatch, tmp_path, BDM, doc)

        assert validate_collections.main() == 1
        assert "birth_registrations.sex declares no allowed-value list" in capsys.readouterr().out


def test_two_declarations_that_disagree_are_refused(tmp_path):
    """Criterion 4: a column declaring an `enum:` and an invalidValues rule
    that differ is refused rather than one picked."""
    doc = {"schema": [{"name": "t", "properties": [{
        "name": "c", "enum": [{"value": "a"}, {"value": "b"}],
        "quality": [{"metric": "invalidValues", "arguments": {"validValues": ["a"]}}]}]}]}
    path = tmp_path / "c-contract.yaml"
    path.write_text(yaml.safe_dump(doc))
    with pytest.raises(contract_values.AllowedValuesError, match="two allowed-value lists"):
        contract_values.allowed_values(path, "t", "c")
    doc["schema"][0]["properties"][0]["quality"][0]["arguments"]["validValues"] = ["a", "b"]
    path.write_text(yaml.safe_dump(doc))
    assert contract_values.allowed_values(path, "t", "c") == ["a", "b"]


@pytest.mark.asset("quarterly")
class TestEmergencyDepartmentsAgeGroup:
    def test_the_contract_declares_the_ten_bands_as_a_real_rule(self):
        """Criteria 5 to 8: the rule its siblings' shape, read by the stats."""
        rule = next(r for r in _column(_contract(ED), "ed_presentations", "age_group")["quality"]
                    if r["metric"] == "invalidValues")
        assert rule["id"] == AGE_GROUP_ID
        assert rule["arguments"]["validValues"] == TEN_BANDS
        assert (rule["mustBe"], rule["severity"], rule["dimension"]) == (0, "error", "conformity")
        props = {p["property"]: p["value"] for p in rule["customProperties"]}
        assert props["check_id"] == AGE_GROUP_ID.replace(":", ".")
        assert props["introduced_date"] == "2013-01-01" and props["changelog"] == "[]"
        assert "technical_note" not in props
        coll = declared_collections.by_id(ED)
        assert contract_values.allowed_values(coll.check_file("contract"), "ed_presentations",
                                              "age_group") == TEN_BANDS

    def test_an_age_group_outside_the_ten_bands_fails_the_new_check(self):
        """Criterion 12: datacontract-cli itself, against a real schema."""
        from qa_tools.common import datacontract_common, supply_db

        schema = "test_389_age_group"
        with supply_db.connect(label="test-389") as conn:
            conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            conn.execute(f'CREATE SCHEMA "{schema}"')
            conn.execute(f'''CREATE TABLE "{schema}".ed_presentations (
                presentation_id varchar(20), arrival_datetime timestamp, triage_category integer,
                age_group varchar(10), sex varchar(1), postcode varchar(4),
                departure_status varchar(30), length_of_stay_minutes integer)''')
            conn.execute(f'''INSERT INTO "{schema}".ed_presentations VALUES
                ('p1', '2020-01-01 10:00', 3, '25-34', 'F', '6000', 'Discharged', 60),
                ('p2', '2020-01-01 11:00', 2, '90+', 'M', '6000', 'Admitted', 90)''')
            conn.commit()
        try:
            coll = declared_collections.by_id(ED)
            run = datacontract_common.run_against_warehouse(
                coll.check_file("contract"), schema, quality_ids={AGE_GROUP_ID},
                schema_name="ed_presentations")
            ours = [c for c in run.checks if datacontract_common.check_id_from_quality_definition(
                getattr(c, "qualityDefinition", None)) == AGE_GROUP_ID.replace(":", ".")]
            assert ours, [c.name for c in run.checks]
            assert all(getattr(c.result, "value", c.result) == "failed" for c in ours), \
                [(c.name, c.result, c.reason) for c in ours]
        finally:
            with supply_db.connect(label="test-389") as conn:
                conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                conn.commit()

    def test_the_linkage_providers_known_values_read_the_contract(self, monkeypatch, tmp_path):
        """Criterion 9: the provider's drift planning reads the same reader,
        not the QA adapter."""
        from generator import collections as providers

        provider = providers.provider(LP)
        import sys
        module = sys.modules[type(provider).__module__]
        dataset = next(d for d in declared_collections.by_id(LP).datasets
                       if d.table == "geo_cp_clients").dataset_id
        assert module.known_values(dataset, "match_level") == [
            "address", "postcode", "suburb", "not geocoded"]

        doc = _contract(LP)
        _column(doc, "geo_cp_clients", "match_level")["enum"].append({"value": "mesh block"})
        _use_contract(monkeypatch, tmp_path, LP, doc)
        assert module.known_values(dataset, "match_level")[-1] == "mesh block"


#: The data asset this module's tests act for, unless a test says otherwise
#: (C11, Keith 2026-11-02: every test module names its asset).
pytestmark = pytest.mark.asset("daily")
