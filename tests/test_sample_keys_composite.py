"""A failing-row sample may name a row by several columns (REQ-PIPE-341).

Each table's sample key is an ordered list of columns (criterion 1). A
one-column key records the bare value exactly as before; a several-column key
records each sample as an ordered list of that row's key values, each as text,
a null part kept as null - never the text 'None' and never dropped (criteria
2, 7 and 8 as amended 2026-11-01, Keith, post-build-review #294) - ordered by
its parts as text by code point, nulls last, the same in every tool. A sampler
that cannot record a sample as declared fails loudly (criterion 8), unless the
check declares that its failure names no row (`names_no_row`, decisions
2026-11-01). Several-column results record their key's column names
(criterion 9).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from qa_tools import collections
from qa_tools.common import datacontract_common, dbt_common, sample_keys, soda_common, supply_db

KEY = ["dataset", "id_1", "id_2"]


# ---- criterion 1: every adapter declares an ordered list ------------------

def test_every_adapter_declares_each_tables_key_as_a_list():
    adapters = [collections.adapter(c) for c in collections.all_collections()]
    assert adapters, "no collection registered - this would prove nothing"
    for a in adapters:
        assert a.sample_key, a.collection_id
        for table, cols in a.sample_key.items():
            assert isinstance(cols, list) and cols and all(isinstance(c, str) for c in cols), \
                (a.collection_id, table, cols)


def test_the_existing_one_column_keys_are_unchanged():
    keys = {c.id: collections.adapter(c).sample_key for c in collections.all_collections()}
    assert keys["civil-registration"] == {"birth_registrations": ["registration_number"]}
    assert keys["emergency-department"] == {"ed_presentations": ["presentation_id"]}
    assert keys["child-protection"]["cp_clients"] == ["cp_client_id"]


def test_linkage_keys_is_named_by_its_dataset_and_every_identifier():
    """Criterion 3: dataset and id_1 to id_N, N the contract's id columns."""
    import yaml

    contract = yaml.safe_load(open(collections.by_id("linkage-products").check_file("contract")))
    ids = [p["name"] for s in contract["schema"] for p in s["properties"]
           if p["name"].startswith("id_")]
    assert ids, "the contract declares no id columns - this would prove nothing"
    assert collections.adapter("linkage-products").sample_key == {"linkage_keys": ["dataset", *ids]}


# ---- the shared value, order and record rules ------------------------------

def test_a_one_column_sample_is_the_bare_text_value():
    assert sample_keys.value_of({"pk": 7, "x": 1}, ["pk"], check="c", table="t") == "7"
    assert sample_keys.value_of({"pk": None}, ["pk"], check="c", table="t") is None


def test_a_several_column_sample_keeps_a_null_part_as_null_never_the_text_none():
    got = sample_keys.value_of({"dataset": "ED", "id_1": 12, "id_2": None, "other": "x"},
                               KEY, check="c", table="t")
    assert got == ["ED", "12", None]


def test_a_key_given_as_a_bare_string_is_refused_not_read_as_letters():
    with pytest.raises(TypeError):
        sample_keys.value_of({"pk": 1}, "pk", check="c", table="t")


def test_a_missing_key_column_is_refused_naming_check_table_and_column():
    with pytest.raises(sample_keys.SampleNotRecordable) as exc:
        sample_keys.value_of({"dataset": "ED"}, KEY, check="Referential", table="linkage_keys")
    msg = str(exc.value)
    assert "Referential" in msg and "linkage_keys" in msg and "id_1" in msg and "id_2" in msg


def test_several_column_samples_order_by_parts_as_text_nulls_last_and_are_limited():
    samples = [["B", "1", None], ["A", "2", "x"], ["A", None, None], ["A", "10", None],
               ["A", "2", None], ["a", "1", None], ["Z", "9", "9"]]
    assert sample_keys.pick(samples) == [
        ["A", "10", None], ["A", "2", "x"], ["A", "2", None], ["A", None, None], ["B", "1", None]]


def test_one_column_samples_order_as_before_a_null_kept_last():
    """Post-build-review #294 D1 (Keith 2026-11-01): a null key is recorded as
    an empty key part, never dropped - one column included."""
    assert sample_keys.pick(["K-3", None, "K-1", "K-2"]) == ["K-1", "K-2", "K-3", None]


def test_a_several_column_result_records_its_columns_and_a_one_column_result_none():
    assert sample_keys.recorded(KEY, [["A", "1", None]]) == {
        "failing_sample_keys": [["A", "1", None]], "failing_sample_key_columns": KEY}
    assert sample_keys.recorded(KEY, []) == {
        "failing_sample_keys": [], "failing_sample_key_columns": KEY}
    assert sample_keys.recorded(["pk"], ["1"]) == {"failing_sample_keys": ["1"]}


# ---- Soda ------------------------------------------------------------------

ROWS = [{"dataset": "ED", "id_1": "P-2", "id_2": None},
        {"dataset": "CP", "id_1": None, "id_2": None},
        {"dataset": "CP", "id_1": "C-1", "id_2": None}]


def test_soda_records_every_key_column_null_parts_kept():
    captured = {("linkage_keys", "c"): ROWS}
    assert soda_common.failing_sample_keys(captured, "c", KEY, "linkage_keys") == [
        ["CP", "C-1", None], ["CP", None, None], ["ED", "P-2", None]]


def test_soda_one_column_key_is_the_bare_value_a_null_kept():
    captured = {("t", "c"): [{"pk": "K-2", "o": 1}, {"pk": None}, {"pk": "K-1"}]}
    assert soda_common.failing_sample_keys(captured, "c", ["pk"], "t") == ["K-1", "K-2", None]


def test_soda_refuses_a_captured_row_without_a_key_column():
    captured = {("linkage_keys", "Expected identifiers present"):
                [{"dataset": "CP", "linkage_key": "k"}]}
    with pytest.raises(sample_keys.SampleNotRecordable, match="id_1"):
        soda_common.failing_sample_keys(captured, "Expected identifiers present", KEY,
                                        "linkage_keys")


def test_soda_records_nothing_for_a_check_declaring_it_names_no_row():
    captured = {("t", "fresh"): [{"?column?": 1}]}
    assert soda_common.failing_sample_keys(captured, "fresh", ["pk"], "t",
                                           names_no_row=True) == []


# ---- dbt (real PostgreSQL, the test worker's own database) ----------------

@pytest.fixture
def audit(supply_dsn):
    with supply_db.connect(label="test-composite-samples") as conn:
        conn.execute("DROP TABLE IF EXISTS public.composite_probe")
        conn.execute("CREATE TABLE public.composite_probe (dataset text, id_1 bigint, id_2 text, v text)")
        for row in [("ED", 10, None, "x"), ("ED", 9, None, "x"), ("CP", None, None, "x"),
                    ("CP", 3, "b", "y"), ("a", 1, None, "x"), ("B", 2, None, "x")]:
            conn.execute("INSERT INTO public.composite_probe VALUES (?, ?, ?, ?)", list(row))
        try:
            yield conn
        finally:
            conn.execute("DROP TABLE public.composite_probe")


def test_dbt_direct_samples_every_key_column_as_text_in_c_order_nulls_last(audit):
    assert dbt_common.failing_sample_keys_direct(audit, "public.composite_probe", KEY) == [
        ["B", "2", None], ["CP", "3", "b"], ["CP", None, None], ["ED", "10", None],
        ["ED", "9", None]]


def test_dbt_via_values_samples_every_key_column(audit):
    conn = audit
    conn.execute("DROP TABLE IF EXISTS public.composite_values")
    conn.execute("CREATE TABLE public.composite_values (value_field text)")
    conn.execute("INSERT INTO public.composite_values VALUES ('y')")
    try:
        assert dbt_common.failing_sample_keys_via_values(
            conn, "public.composite_values", "value_field", "public.composite_probe", "v",
            KEY) == [["CP", "3", "b"]]
    finally:
        conn.execute("DROP TABLE public.composite_values")


def test_dbt_one_column_samples_in_their_own_order_a_null_kept_last(audit):
    assert dbt_common.failing_sample_keys_direct(audit, "public.composite_probe", ["id_1"],
                                                 limit=10) == ["1", "2", "3", "9", "10", None]


def test_dbt_a_sample_query_that_raises_fails_the_recording(audit):
    with pytest.raises(sample_keys.SampleNotRecordable, match="no_such_column"):
        dbt_common.failing_sample_keys_direct(audit, "public.composite_probe",
                                              ["dataset", "no_such_column"])
    with pytest.raises(sample_keys.SampleNotRecordable):
        dbt_common.failing_sample_keys_via_values(audit, "public.no_such_audit", "v",
                                                  "public.composite_probe", "v", ["id_1"])


# ---- datacontract-cli ------------------------------------------------------

def test_datacontract_records_every_key_column():
    check = SimpleNamespace(name="n", failedSamples=[
        {"dataset": "ED", "id_1": "P-1", "id_2": None, "field": "x"},
        {"dataset": "CP", "id_1": None, "id_2": None, "field": "x"}])
    assert datacontract_common.failing_sample_keys(check, KEY) == [
        ["CP", None, None], ["ED", "P-1", None]]


def test_datacontract_one_column_null_key_is_null_never_the_text_none():
    """It was str(None), the text 'None' (post-build-review #294 D1)."""
    check = SimpleNamespace(name="n", failedSamples=[{"pk": "K-2"}, {"pk": None}, {"pk": "K-1"}])
    assert datacontract_common.failing_sample_keys(check, ["pk"]) == ["K-1", "K-2", None]


def test_datacontract_refuses_a_sample_lacking_a_key_column():
    """It was dropped by `if pk_column in s` (datacontract_common.py:271)."""
    check = SimpleNamespace(name="dupes", failedSamples=[{"other_id": "X", "duplicate_count": 2}])
    with pytest.raises(sample_keys.SampleNotRecordable, match="pk"):
        datacontract_common.failing_sample_keys(check, ["pk"], table="t")


def test_datacontract_records_nothing_for_a_rule_declaring_it_names_no_row():
    check = SimpleNamespace(name="dupes", failedSamples=[{"other_id": "X", "duplicate_count": 2}])
    assert datacontract_common.failing_sample_keys(check, ["pk"], names_no_row=True) == []


def test_names_no_row_is_read_from_a_rules_custom_properties():
    q = ("metric: duplicateValues\ncustomProperties:\n- property: check_id\n  value: a.b\n"
         "- property: names_no_row\n  value: true\n")
    assert datacontract_common.names_no_row_from_quality_definition(q) is True
    assert datacontract_common.names_no_row_from_quality_definition("metric: nullValues\n") is False
    assert datacontract_common.names_no_row_from_quality_definition(None) is False


def test_datacontract_cli_samples_every_primary_key_column_by_experiment(tmp_path):
    """Criterion 2's proof against the INSTALLED datacontract-cli: a model whose
    key is two primaryKey columns returns both in each failed sample, beside
    the failing field - so a several-column key is sampleable there at all."""
    import duckdb
    import yaml
    from datacontract.data_contract import DataContract

    db = tmp_path / "probe.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE probe (site_code VARCHAR, episode_no INTEGER, v VARCHAR, other VARCHAR)")
    con.execute("INSERT INTO probe VALUES ('S1', 1, NULL, 'o'), ('S1', 2, 'ok', 'o'), ('S2', 1, NULL, 'o')")
    con.close()
    contract = {
        "apiVersion": "v3.0.2", "kind": "DataContract", "id": "probe", "name": "probe",
        "version": "1.0.0", "status": "active",
        "servers": [{"server": "local", "type": "duckdb", "database": str(db), "schema": "main"}],
        "schema": [{"name": "probe", "physicalName": "probe", "logicalType": "object", "properties": [
            {"name": "site_code", "logicalType": "string", "primaryKey": True, "primaryKeyPosition": 1},
            {"name": "episode_no", "logicalType": "integer", "primaryKey": True, "primaryKeyPosition": 2},
            {"name": "v", "logicalType": "string",
             "quality": [{"type": "library", "metric": "nullValues", "mustBe": 0}]},
            {"name": "other", "logicalType": "string"}]}]}
    path = tmp_path / "probe-contract.yaml"
    path.write_text(yaml.safe_dump(contract, sort_keys=False))
    run = DataContract(data_contract_file=str(path), include_failed_samples=True).test()
    sampled = [c for c in run.checks if getattr(c, "failedSamples", None)]
    assert sampled, [(c.name, c.result) for c in run.checks]
    for c in sampled:
        for s in c.failedSamples:
            assert {"site_code", "episode_no"} <= set(s) and "other" not in s, s
    [c] = sampled
    assert datacontract_common.failing_sample_keys(c, ["site_code", "episode_no"]) == [
        ["S1", "1"], ["S2", "1"]]


def test_every_sampled_contract_rule_can_record_its_tables_key():
    """What criterion 8 would otherwise find at run time: datacontract-cli's
    samples carry only primaryKey or unique columns, never a sensitive one, and
    a duplicate rule's samples are the duplicated VALUE - so a sampled rule's
    key columns must be such columns, and a duplicate rule on a column outside
    the key must declare names_no_row."""
    import yaml

    sensitive = {"pii", "personal", "personal_data", "confidential", "restricted",
                 "sensitive", "secret"}
    seen = 0
    for c in collections.all_collections():
        key_by_table = collections.adapter(c).sample_key
        doc = yaml.safe_load(open(c.check_file("contract")))
        for schema in doc.get("schema") or []:
            table = schema.get("physicalName") or schema["name"]
            props = {p["name"]: p for p in schema.get("properties") or []}
            for col, prop in props.items():
                for rule in prop.get("quality") or []:
                    if rule.get("metric") not in ("nullValues", "invalidValues", "duplicateValues"):
                        continue
                    seen += 1
                    custom = {p["property"]: p.get("value") for p in rule.get("customProperties") or []}
                    if sample_keys.names_no_row(custom.get("names_no_row")):
                        continue
                    key = key_by_table[table]
                    if rule["metric"] == "duplicateValues":
                        assert key == [col], (c.id, table, col, "declare names_no_row")
                        continue
                    for k in key:
                        p = props[k]
                        assert p.get("primaryKey") or p.get("unique"), (c.id, table, k)
                        assert (p.get("classification") or "").lower() not in sensitive, (c.id, k)
    assert seen, "no sampled contract rule found - this would prove nothing"


def test_real_soda_over_the_real_linkage_checks_names_each_failing_row(supply_dsn):
    """Post-build-review #291 at unit scale: real Soda, the committed Linkage
    Keys checks file, a fixture with one fault of each kind. Every captured
    sample records dataset and id_1 to id_2 - the referential ones included,
    which were recorded empty - and no captured row lacks a key column, so no
    sampler refuses (criterion 8)."""
    from soda.scan import Scan

    from qa_tools import collections as registry

    key = registry.adapter("linkage-products").sample_key["linkage_keys"]
    path = registry.by_id("linkage-products").check_file("soda")
    schema = "sample_probe_linkage"
    with supply_db.connect(label="test-linkage-samples") as conn:
        conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        conn.execute(f"CREATE SCHEMA {schema}")
        conn.execute(f"CREATE TABLE {schema}.linkage_keys "
                     "(linkage_key text, dataset text, id_1 text, id_2 text)")
        conn.execute(f"CREATE TABLE {schema}.cp_clients (cp_client_id text)")
        conn.execute(f"CREATE TABLE {schema}.ed_presentations (presentation_id text)")
        for row in [("k1", "DOC_CLIENTS", "C-1", None), ("k2", "DOC_CLIENTS", "C-404", None),
                    ("k3", "EDDC_PRESENTATION", "P-1", None),
                    ("k4", "EDDC_PRESENTATION", "P-404", None),
                    ("k5", "DOC_CLIENTS", None, None), ("k6", "DOC_CLIENTS", "C-1", "extra")]:
            conn.execute(f"INSERT INTO {schema}.linkage_keys VALUES (?, ?, ?, ?)", list(row))
        conn.execute(f"INSERT INTO {schema}.cp_clients VALUES ('C-1')")
        conn.execute(f"INSERT INTO {schema}.ed_presentations VALUES ('P-1')")
    try:
        scan = Scan()
        scan.set_data_source_name("probe")
        scan.add_configuration_yaml_str(supply_db.soda_config_yaml("probe", schema))
        scan.add_sodacl_yaml_file(path)
        sampler = soda_common.CaptureSampler()
        scan.sampler = sampler
        scan.disable_telemetry()
        soda_common.execute_scan(scan)
        got = {name: soda_common.failing_sample_keys(sampler.captured, name, key, table)
               for (table, name) in sampler.captured}
    finally:
        with supply_db.connect(label="test-linkage-samples") as conn:
            conn.execute(f"DROP SCHEMA {schema} CASCADE")
    assert got["Client Register links match a client"] == [
        ["DOC_CLIENTS", "C-404", None], ["DOC_CLIENTS", None, None]]
    assert got["ED Presentations links match a presentation"] == [
        ["EDDC_PRESENTATION", "P-404", None]]
    assert got["Expected identifiers present"] == [["DOC_CLIENTS", None, None]]
    assert got["No surplus identifiers"] == [["DOC_CLIENTS", "C-1", "extra"]]


# ---- dbt honours the same names_no_row declaration (post-build-review) ----

class _NoQueries:
    def execute(self, sql, *a):
        raise AssertionError(f"queried for a check that names no row: {sql}")


def _singular(meta):
    return {"relation_name": '"x"."audit"', "test_metadata": None,
            "config": {"meta": meta}}


def test_dbt_records_nothing_for_a_test_declaring_it_names_no_row():
    from qa_tools.tools import run_dbt

    adapter = collections.adapter("civil-registration")
    got = run_dbt._failing_sample_keys(_NoQueries(), adapter, "recency", "date_of_birth",
                                       "birth_registrations", _singular({"names_no_row": True}),
                                       "fail", frozenset())
    assert got == []


def test_dbt_samples_a_singular_test_without_the_declaration():
    from qa_tools.tools import run_dbt

    adapter = collections.adapter("civil-registration")
    with pytest.raises(sample_keys.SampleNotRecordable, match="queried"):
        run_dbt._failing_sample_keys(_NoQueries(), adapter, "recency", "date_of_birth",
                                     "birth_registrations", _singular({}), "fail", frozenset())


def test_birth_registrations_recency_test_declares_it_names_no_row():
    """The one declaration, not an adapter list (singular_unsampled is gone)."""
    import yaml

    from qa_tools.collections.base import DbtSpec

    doc = yaml.safe_load(open("dbt_project/models/civil-registration/schema.yml"))
    [recency] = [t for t in doc.get("data_tests") or doc.get("tests") or []
                 if t.get("name") == "recency"]
    assert recency["config"]["meta"]["names_no_row"] is True
    assert not hasattr(DbtSpec(), "singular_unsampled")
