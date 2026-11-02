"""The gates over the set-member checks and the list setting they read
(REQ-QAC-297 criteria 4, 13 and 15; REQ-QAC-300 criteria 5, 7 and 9). Each gate
test copies the real configuration, changes one thing and asks the gate; the
real files are untouched."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from qa_tools.common import list_setting_members, supply_db

REAL = Path(__file__).resolve().parent.parent


def _schema() -> Path:
    """Linkage Products' dbt schema, by repository path through the resolver."""
    from qa_tools.common import assets

    return Path(assets.dbt_rel()) / "models" / "linkage-products" / "schema.yml"


@pytest.fixture
def repo(tmp_path):
    from qa_tools import collections
    from qa_tools.common import assets

    # The asset's configuration where the gate reads it, by the resolver's
    # repository path (the asset split - it was contract/); its dbt project
    # is copied below, model by model.
    real = assets.selected()
    shutil.copytree(real.folder, tmp_path / assets.folder_rel(),
                    ignore=lambda d, names: [real.dbt_project.name] if Path(d) == real.folder else [])
    (tmp_path / _schema()).parent.mkdir(parents=True)
    shutil.copy(REAL / _schema(), tmp_path / _schema())
    # The asset's own collections' models, in its own dbt project (the split).

    for c in collections.all_collections():
        if c.id == "linkage-products":
            continue
        shutil.copytree(REAL / assets.dbt_rel() / "models" / c.id,
                        tmp_path / assets.dbt_rel() / "models" / c.id)
    return tmp_path


def _schema_doc(repo):
    return yaml.safe_load((repo / _schema()).read_text())


def _write(repo, doc):
    (repo / _schema()).write_text(yaml.safe_dump(doc, sort_keys=False))


def _tests(doc, model):
    m = next(x for x in doc["models"] if x["name"] == model)
    return next(c for c in m["columns"] if c["name"] == "census_year")["tests"]


def test_the_real_configuration_passes():
    assert list_setting_members.problems(REAL) == []
    assert len(list_setting_members.declared(REAL)) == 6


class TestCriterionThirteenThePresenceGate:
    def test_a_geocoding_dataset_lacking_a_year_check_fails_naming_it(self, repo):
        doc = _schema_doc(repo)
        tests = _tests(doc, "stg_geo_ed_presentations")
        tests[:] = [t for t in tests if "duplicated_set_members" not in t]
        _write(repo, doc)
        assert list_setting_members.problems(repo) == [
            "geo-ed-presentations is a geocoding dataset without duplicated_set_members "
            "(REQ-QAC-297 criterion 13)."]

    def test_a_year_check_without_key_columns_or_a_declared_setting(self, repo):
        doc = _schema_doc(repo)
        body = _tests(doc, "stg_geo_cp_clients")[0]["missing_set_members"]
        body["key_columns"] = []
        body["member_setting"] = "census_yrs"
        _write(repo, doc)
        text = "\n".join(list_setting_members.problems(repo))
        assert "geo-cp-clients: missing_set_members declares no key columns." in text
        assert "names the member_setting 'census_yrs', which is no declared list setting" in text

    def test_a_geocoding_dataset_lacking_its_share_check(self, repo):
        from qa_tools.common import assets

        path = repo / assets.folder_rel() / "department-of-health" / "linkage-products-soda-checks.yml"
        doc = yaml.safe_load(path.read_text())
        block = doc["checks for geo_cp_clients"]
        block[:] = [c for c in block if "geo_cp_clients_not_geocoded_percent" not in c]
        path.write_text(yaml.safe_dump(doc, sort_keys=False))
        assert list_setting_members.problems(repo) == [
            "geo-cp-clients is a geocoding dataset without value_share_soda "
            "(REQ-QAC-297 criterion 13)."]


class TestCriterionFiveOfRequirement300Coverage:
    def test_a_period_no_version_covers_is_refused_naming_dataset_and_period(self, repo):
        from qa_tools.common import assets

        path = repo / assets.folder_rel() / "data-asset.yaml"
        text = path.read_text()
        assert '- effective_from: "2013-01-01"\n                  value: [2011]' in text
        path.write_text(text.replace('- effective_from: "2013-01-01"\n                  value: [2011]',
                                     '- effective_from: "2016-01-01"\n                  value: [2011]'))
        problems = list_setting_members.problems(repo)
        assert ("geo-cp-clients owes 2015-Q2 (round 2015-05-01), which no version of "
                "census_years covers (REQ-QAC-300 criterion 5).") in problems, problems
        assert any(p.startswith("geo-ed-presentations owes 2013-Q1") for p in problems)


class TestCriterionSevenOfRequirement300BreakingEntries:
    def test_a_missing_breaking_entry_fails_naming_the_check_and_the_version(self, repo):
        doc = _schema_doc(repo)
        body = _tests(doc, "stg_geo_cp_clients")[2]["unexpected_set_members"]
        body["meta"]["changelog"] = [e for e in body["meta"]["changelog"]
                                     if not e["date"].startswith("2022-08-01")]
        _write(repo, doc)
        assert list_setting_members.problems(repo) == [
            "check quarterly.department-of-health.linkage-products.geo-cp-clients.census_year."
            "unexpected_set_members_dbt has no breaking changelog entry dated 2022-08-01 for the "
            "version of census_years it changes to (REQ-QAC-300 criterion 7)."]

    def test_a_non_breaking_entry_does_not_count(self, repo):
        doc = _schema_doc(repo)
        body = _tests(doc, "stg_geo_cp_clients")[0]["missing_set_members"]
        body["meta"]["changelog"][0]["breaking"] = False
        _write(repo, doc)
        assert any("dated 2017-08-01" in p for p in list_setting_members.problems(repo))

    def test_three_entries_per_year_check_for_four_versions(self):
        for check in list_setting_members.declared(REAL):
            assert sorted(e["date"][:10] for e in check.changelog if e.get("breaking")) == [
                "2017-08-01", "2022-08-01", "2027-08-01"], check.check_id


class TestCriterionNineOfRequirement300TheSetIsRecorded:
    def test_a_result_carries_the_version_its_years_and_what_it_added(self):
        with supply_db.connect() as conn:
            schema = supply_db.run_schema("geo_probe_record")
            conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            conn.execute(f'CREATE SCHEMA "{schema}"')
            try:
                list_setting_members.create(conn, schema, list_setting_members.rows_for(
                    ["geo_ed_presentations", "geo_cp_clients"], "2022-Q3"))
                got = list_setting_members.read(conn, schema, "geo_ed_presentations",
                                                "census_years")
                assert got.as_record() == {
                    "member_setting": "census_years", "member_set_version": "2022-08-01",
                    "member_set": ["2011", "2016", "2021"], "member_set_added": ["2021"]}
                first = list_setting_members.in_force("geo-ed-presentations", "2013-Q1")
                assert [(s.members, s.added) for s in first] == [((2011,), ())]
            finally:
                conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')

    def test_no_relation_where_the_run_has_no_period(self):
        with supply_db.connect() as conn:
            schema = supply_db.run_schema("geo_probe_none")
            conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            conn.execute(f'CREATE SCHEMA "{schema}"')
            try:
                assert not list_setting_members.exists(conn, schema)
                list_setting_members.create(conn, schema, [])
                assert list_setting_members.exists(conn, schema)
                assert list_setting_members.read(conn, schema, "x", "census_years") is None
            finally:
                conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


class TestCriterionFourNotEvaluatedWithoutAPeriod:
    def test_each_set_member_check_is_recorded_not_evaluated_with_its_reason(self):
        from qa_tools import collections
        from qa_tools.tools import run_dbt

        coll = collections.by_id("linkage-products")
        records = run_dbt._not_evaluated_for_want_of_a_period(
            coll, collections.adapter(coll).dbt, "lp_probe", "2026-11-01T10:00:00+00:00", None)
        assert len(records) == 6
        assert {r["status"] for r in records} == {"fail"}
        assert {r["not_evaluated_code"] for r in records} == {list_setting_members.NO_PERIOD}
        assert all("could not be evaluated" in r["not_evaluated_reason"] for r in records)
        from qa_tools.common import carried

        assert all(carried.not_evaluated_reason(r) for r in records)

    def test_only_the_checks_asked_for(self):
        from qa_tools import collections
        from qa_tools.tools import run_dbt

        coll = collections.by_id("linkage-products")
        one = ("quarterly.department-of-health.linkage-products.geo-cp-clients.census_year."
               "missing_set_members_dbt")
        records = run_dbt._not_evaluated_for_want_of_a_period(
            coll, collections.adapter(coll).dbt, "lp_probe", "2026-11-01T10:00:00+00:00", [one])
        assert [r["check_id"] for r in records] == [one]


def test_criterion_fifteen_no_distribution_of_an_area_code_or_an_identifier():
    from qa_tools import collections

    stats = collections.adapter(collections.by_id("linkage-products")).stats
    assert {col for _t, col in stats.value_counts} == {"match_level"}
    assert not any(col in ("sa2_code", "lga_code") or col.startswith("id_")
                   for _t, col in stats.aggregates)


class TestATrialsYearChecksSayTrialNotNoPeriod:
    """post-build-review #299 item 3: a staged-only trial (`mothman lp qa`) is
    filed to no period by design, and decides nothing - its year checks are
    recorded no data with a trial's reason, never red 'filed to no period'."""

    def test_a_trial_records_no_data_with_a_trials_reason(self):
        from qa_tools import collections
        from qa_tools.common import trial
        from qa_tools.tools import run_dbt

        coll = collections.by_id("linkage-products")
        records = run_dbt._not_evaluated_for_want_of_a_period(
            coll, collections.adapter(coll).dbt, trial.trial_run_id(),
            "2026-11-01T10:00:00+00:00", None)
        assert len(records) == 6
        assert {r["status"] for r in records} == {"nodata"}
        assert {r["not_evaluated_code"] for r in records} == {list_setting_members.TRIAL_NO_PERIOD}
        assert all("trial" in r["not_evaluated_reason"] and "filed to no period" not in
                   r["not_evaluated_reason"] for r in records)


#: The data asset this module's tests act for, unless a test says otherwise
#: (C11, Keith 2026-11-02: every test module names its asset).
pytestmark = pytest.mark.asset("quarterly")
