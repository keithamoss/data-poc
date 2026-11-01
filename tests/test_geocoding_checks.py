"""The geocoding checks, proven by experiment against the INSTALLED tools
(REQ-QAC-297 criteria 3, 5 to 8, 11 and 12; REQ-QAC-340 criteria 1, 2 and 4).

Each test builds a run's view schema by hand in this worker's own database -
never the real supply database - and runs the committed check definitions
through the real dbt, Soda and Evidently, so a check edited in its file is the
check tested."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml

from qa_tools.common import list_setting_members, supply_db

REPO = Path(__file__).resolve().parent.parent
SODA = REPO / "contract" / "department-of-health" / "linkage-products-soda-checks.yml"


def _schema(conn, run_id, tables: dict[str, tuple[str, list[tuple]]]):
    """A run's view schema holding each table, as staging gives one."""
    schema = supply_db.run_schema(run_id)
    conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    conn.execute(f'CREATE SCHEMA "{schema}"')
    for table, (columns, rows) in tables.items():
        conn.execute(f'CREATE TABLE "{schema}".{table} ({columns})')
        for row in rows:
            marks = ", ".join(["?"] * len(row))
            conn.execute(f'INSERT INTO "{schema}".{table} VALUES ({marks})', list(row))
    return schema


GEO_COLUMNS = ("id_1 text, id_2 text, census_year integer, sa2_code text, lga_code text, "
               "match_level text")


def _geo(rows):
    return (GEO_COLUMNS, rows)


def _row(i, year, level="postcode"):
    placed = level != "not geocoded"
    return (i, None, year, "501011001" if placed else None, "57080" if placed else None, level)


# ---- dbt: the three set-member tests over the declared set --------------------

def _dbt(run_id: str, tests: list[str]) -> dict[str, int]:
    """Build stg_geo_cp_clients and the named tests for one run; the failure
    count of each, recounted from its audit table as run_dbt does."""
    from qa_tools.common.dbt_common import run_dbt
    from qa_tools.tools import run_dbt as tool

    target = str(supply_db.dbt_target_path(run_id))
    run_dbt("build", ["stg_geo_cp_clients", *tests], target, tool.PROFILES_DIR,
            tool._project_dir(), tool.ROOT, run_schema=supply_db.run_schema(run_id),
            run_id=run_id, indirect_selection="empty")
    results = json.load(open(os.path.join(target, "run_results.json")))
    manifest = json.load(open(os.path.join(target, "manifest.json")))
    out = {}
    with supply_db.connect() as conn:
        for r in results["results"]:
            node = manifest["nodes"].get(r["unique_id"]) or {}
            if node.get("resource_type") != "test":
                continue
            assert r["status"] in ("pass", "fail"), r
            out[node["test_metadata"]["name"]] = conn.execute(
                f"SELECT COUNT(*) FROM {node['relation_name']}").fetchone()[0] \
                if r["status"] == "fail" else 0
    return out


def _names(kind: str) -> str:
    return f"{kind}_set_members_stg_geo_cp_clients_census_year__id_1__census_years"


ALL = [_names(k) for k in ("missing", "duplicated", "unexpected")]


def _year_run(run_id: str, period: str, rows: list[tuple]):
    with supply_db.connect() as conn:
        schema = _schema(conn, run_id, {"geo_cp_clients": _geo(rows)})
        list_setting_members.create(conn, schema,
                                    list_setting_members.rows_for(["geo_cp_clients"], period))


class TestTheSetReachesDbtWithThePeriodsViews:
    """Criterion 3: two runs of different periods read different sets, one
    parse serving both - the set is a relation, not a --vars value."""

    def test_two_periods_two_sets_one_parse(self):
        rows = [_row("A", 2011), _row("B", 2011)]
        _year_run("geo_probe_2017q2", "2017-Q2", rows)
        _year_run("geo_probe_2017q3", "2017-Q3", rows)
        before = _dbt("geo_probe_2017q2", ALL)
        after = _dbt("geo_probe_2017q3", ALL)
        assert before == {"missing_set_members": 0, "duplicated_set_members": 0,
                          "unexpected_set_members": 0}
        # 2016 joins from 2017-Q3: each record now lacks one year.
        assert after == {"missing_set_members": 2, "duplicated_set_members": 0,
                         "unexpected_set_members": 0}
        m1, m2 = (json.load(open(supply_db.dbt_target_path(r) / "manifest.json"))
                  for r in ("geo_probe_2017q2", "geo_probe_2017q3"))
        checksum = {uid: n["checksum"] for uid, n in m1["nodes"].items()}
        assert checksum == {uid: n["checksum"] for uid, n in m2["nodes"].items()}, \
            "the project parsed the same for both periods - nothing about the set is in it"
        assert not m1["metadata"].get("env", {}).get("DBT_VARS")


class TestEachYearCheckCountsItsOwnViolation:
    """Criteria 5 to 7, one violation per record and year, or per row."""

    def test_missing_duplicated_and_unexpected(self):
        rows = [_row("A", 2011), _row("A", 2016),            # complete
                _row("B", 2011),                               # 2016 missing
                _row("C", 2011), _row("C", 2016), _row("C", 2016),  # 2016 twice
                _row("D", 2011), _row("D", 2016), _row("D", 2021),  # 2021 unexpected
                ("E", None, None, None, None, "not geocoded")]       # no year at all
        _year_run("geo_probe_counts", "2018-Q1", rows)
        got = _dbt("geo_probe_counts", ALL)
        # E has no year in force: two missing (2011, 2016) plus B's one.
        assert got == {"missing_set_members": 3, "duplicated_set_members": 1,
                       "unexpected_set_members": 2}

    def test_an_empty_supply_passes_all_three(self):
        _year_run("geo_probe_empty", "2018-Q1", [])
        assert _dbt("geo_probe_empty", ALL) == {
            "missing_set_members": 0, "duplicated_set_members": 0, "unexpected_set_members": 0}


class TestARunWithNoPeriodLeavesTheYearChecksOut:
    """Criterion 4 against the installed dbt: with no declared-set relation -
    a supply filed to no period - the relation's dependents are excluded by
    run_dbt's own selector, and the build runs without error."""

    def test_the_relations_dependents_are_left_out_and_nothing_errors(self):
        from qa_tools.common.dbt_common import parsed_test_nodes, run_dbt
        from qa_tools.tools import run_dbt as tool

        nodes = parsed_test_nodes(tool.PROFILES_DIR, tool._project_dir())
        assert {n["name"] for n in nodes.values() if tool._reads_declared_set(n)} >= set(ALL)
        run_id = "geo_probe_no_period"
        with supply_db.connect() as conn:
            schema = _schema(conn, run_id, {"geo_cp_clients": _geo([_row("A", 2011)])})
            assert not list_setting_members.exists(conn, schema)
        target = str(supply_db.dbt_target_path(run_id))
        run_dbt("build", ["stg_geo_cp_clients", *ALL], target, tool.PROFILES_DIR,
                tool._project_dir(), tool.ROOT, run_schema=supply_db.run_schema(run_id),
                run_id=run_id, indirect_selection="empty",
                exclude=[f"source:raw.{list_setting_members.RELATION}+"])
        results = json.load(open(os.path.join(target, "run_results.json")))["results"]
        ran = {r["unique_id"].split(".")[2] for r in results}
        assert "stg_geo_cp_clients" in ran
        assert not ran & set(ALL)
        assert {r["status"] for r in results} <= {"success", "pass"}


# ---- Soda: the share, and the orphan and coverage pair ------------------------

def _soda(run_id: str, table: str) -> dict[str, tuple]:
    """Run the committed check block for `table` through the real Soda;
    (outcome, value) by check id tail."""
    from soda.scan import Scan

    from qa_tools.common.soda_common import execute_scan, resource_attribute

    doc = yaml.safe_load(SODA.read_text())
    block = {f"checks for {table}": doc[f"checks for {table}"]}
    scan = Scan()
    scan.set_data_source_name("probe")
    scan.add_configuration_yaml_str(supply_db.soda_config_yaml("probe", supply_db.run_schema(run_id)))
    scan.add_sodacl_yaml_str(yaml.safe_dump(block))
    scan.disable_telemetry()
    results = execute_scan(scan)
    return {resource_attribute(c, "check_id").split(".", 4)[-1]: (
        c["outcome"], c["diagnostics"].get("value")) for c in results["checks"]}


CP_CLIENTS = ("cp_client_id integer, suburb text, postcode text", [(1, "Ascot", "6104"),
                                                                   (2, "Bayswater", "6053")])


class TestTheShareAndThePairOnRealSoda:
    def test_an_empty_geocoding_supply_shares_zero_of_zero_and_covers_nothing(self):
        """Criterion 12 (the share's zero-of-zero passes) and REQ-QAC-340
        criterion 4 (coverage 0 percent against a source holding rows)."""
        with supply_db.connect() as conn:
            _schema(conn, "geo_probe_soda_empty", {"geo_cp_clients": _geo([]),
                                                    "cp_clients": CP_CLIENTS})
        got = _soda("geo_probe_soda_empty", "geo_cp_clients")
        assert got["match_level.value_share_soda"] == ("pass", 0.0)
        assert got["cp-clients.coverage_soda"] == ("fail", 0.0)
        assert got["cp-clients.referential_soda"][0] == "pass"

    def test_bands_and_casts(self):
        """The source's integer identifiers match the text ids (both cast);
        one of two records missing is 50 percent coverage, red; one row in
        three not geocoded is amber-or-worse; a row naming no source record
        is an orphan."""
        rows = [_row("1", 2011), _row("1", 2016), _row("9", 2011, "not geocoded")]
        with supply_db.connect() as conn:
            _schema(conn, "geo_probe_soda_rows", {"geo_cp_clients": _geo(rows),
                                                   "cp_clients": CP_CLIENTS})
        got = _soda("geo_probe_soda_rows", "geo_cp_clients")
        assert got["cp-clients.coverage_soda"] == ("fail", 50.0)
        assert got["cp-clients.referential_soda"][0] == "fail"
        assert got["match_level.value_share_soda"][0] == "fail"
        assert got["sa2_code.invalid_count_soda"][0] == "pass"
        assert got["match_level.invalid_count_soda"][0] == "pass"

    def test_coverage_amber_below_100_red_below_98(self):
        clients = ("cp_client_id integer", [(i,) for i in range(1, 101)])
        for missing, outcome in ((1, "warn"), (3, "fail")):
            rows = [_row(str(i), 2011) for i in range(1 + missing, 101)]
            run = f"geo_probe_band_{missing}"
            with supply_db.connect() as conn:
                _schema(conn, run, {"geo_cp_clients": _geo(rows), "cp_clients": clients})
            assert _soda(run, "geo_cp_clients")["cp-clients.coverage_soda"][0] == outcome


# ---- Evidently: drift over placed rows only ------------------------------------

def test_drift_excludes_the_declared_value_from_both_sides():
    """Criterion 11, against the installed Evidently: a rise in unplaced rows
    alone moves no drift, while the same frames unexcluded would drift."""
    import pandas as pd

    from qa_tools.common.evidently_common import compute_psi
    from qa_tools.tools.run_evidently import _excluding

    entry = {"column": "match_level", "exclude_values": ["not geocoded"]}
    reference = pd.DataFrame({"match_level": ["suburb"] * 60 + ["postcode"] * 38
                              + ["not geocoded"] * 2})
    current = pd.DataFrame({"match_level": ["suburb"] * 30 + ["postcode"] * 19
                            + ["not geocoded"] * 51})
    raw, _ = compute_psi(current, reference, "match_level")
    excluded, _ = compute_psi(_excluding(current, entry), _excluding(reference, entry),
                              "match_level")
    assert raw > 0.25 > 0.10 > excluded


@pytest.fixture(autouse=True)
def _tidy():
    yield
    with supply_db.connect() as conn:
        for (schema,) in conn.execute(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name LIKE ?", [supply_db.run_schema("geo_probe") + "%"]).fetchall():
            conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
