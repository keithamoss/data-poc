"""QA over data for a dataset with no agreed schedule (REQ-PIPE-106).

THE HALF THAT RUNS. Its sibling tests/test_no_calendar.py covers the
CONFIGURATION half - a dataset declaring it has no calendar, and everything
that then declines to ask it for a supply. This module covers what happens
when data actually arrives for such a dataset and the real tools are run
over it: where the data lands, how the record is keyed, who can see it, and
who removes it.

THE SAME FIXTURE HIERARCHY as that module, for the same recorded reason:
criterion 12 asks the system to SUPPORT any number of calendar-less
datasets, not to ship one, and shipping one would drag a contract, its
checks and generated data behind it for no additional coverage here.
"""
from __future__ import annotations

import yaml

import pytest

from qa_tools.common import qa_store, sample_data, schedule, supply_db
from qa_tools.common.qa_results_writer import write_qa_result


def _clear():
    """Every lru_cache that holds a parsed data-asset.yaml - see
    tests/test_no_calendar.py's identical helper for why there are three."""
    from qa_tools.common import hierarchy as hierarchy_mod

    schedule._load.cache_clear()
    schedule._dataset_schedules.cache_clear()
    hierarchy_mod._load.cache_clear()


@pytest.fixture(autouse=True)
def _clear_caches():
    _clear()
    yield
    _clear()


SAMPLE = {"id": "cp-referrals", "name": "Referrals", "table": "cp_referrals",
          "no_calendar": "not-yet-agreed", "arrival_pattern": r"cp_referrals\.csv"}
SECOND_SAMPLE = {"id": "cp-outcomes", "name": "Outcomes", "table": "cp_outcomes",
                 "no_calendar": "not-yet-agreed", "arrival_pattern": r"cp_outcomes\.csv"}
AGREED = {"id": "birth-registrations", "name": "Birth Registrations",
          "table": "birth_registrations", "calendar": "daily",
          "arrival_pattern": r"birth_registrations_[^/]+\.csv"}
GRADUATED = dict(AGREED, id="cp-referrals", name="Referrals", table="cp_referrals",
                 arrival_pattern=r"cp_referrals\.csv")


def _asset_with(datasets: list[dict], tmp_path, monkeypatch):
    """The real asset with its datasets replaced - see
    tests/test_no_calendar.py's identical helper."""
    doc = yaml.safe_load(schedule.DATA_ASSET_YAML.read_text())
    agency = doc["hierarchy"]["agencies"][0]
    agency["collections"] = [{
        "id": "civil-registration", "name": "Civil Registration",
        "contract": "bdm-birth-registrations-contract.yaml",
        "delivery_boundary": "directory",
        "datasets": datasets,
    }]
    doc["hierarchy"]["agencies"] = [agency]
    path = tmp_path / "data-asset.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False))
    monkeypatch.setattr(schedule, "DATA_ASSET_YAML", path)
    from qa_tools.common import hierarchy as hierarchy_mod
    monkeypatch.setattr(hierarchy_mod, "DATA_ASSET_YAML", path)
    _clear()
    return path


def _result(dataset_id: str, check_id: str, status: str = "fail", **extra) -> dict:
    """One `verified` record, in the shape every evaluator builds."""
    record = {
        "dataset_id": dataset_id, "check_id": check_id, "check_name": check_id,
        "column_name": "(table)", "dimension": "validity", "label": None,
        "status": status, "metric_value": 3.0, "unit": "rows",
        "warn_threshold": 0, "fail_threshold": 0, "row_count_total": 100,
        "row_count_invalid": 3, "on_fail_action": "warn", "engine": "dbt-core",
    }
    record.update(extra)
    return record


class TestTheRecordSaysWhetherItIsRealQualityHistory:
    """Criteria 6, 7 and 10."""

    def test_a_result_about_a_calendar_less_dataset_is_in_development(
            self, tmp_path, monkeypatch, clean_qa_history, finish_runs):
        _asset_with([AGREED, SAMPLE], tmp_path, monkeypatch)
        write_qa_result("a", "b", "run_1", "2026-01-01T00:00:00+00:00", "dbt-core",
                        {"raw": True}, [_result("cp-referrals", "referrals_not_null")])
        finish_runs("run_1", agency="a", collection="b")

        rows = qa_store.results_for_run(clean_qa_history, "run_1",
                                        supply_state=qa_store.IN_DEVELOPMENT)
        assert [r["check_id"] for r in rows] == ["referrals_not_null"]

    def test_a_result_about_an_agreed_dataset_is_not(
            self, tmp_path, monkeypatch, clean_qa_history, finish_runs):
        _asset_with([AGREED, SAMPLE], tmp_path, monkeypatch)
        write_qa_result("a", "b", "run_1", "2026-01-01T00:00:00+00:00", "dbt-core",
                        {"raw": True}, [_result("birth-registrations", "births_not_null")])
        finish_runs("run_1", agency="a", collection="b")

        assert [r["check_id"] for r in qa_store.results_for_run(clean_qa_history, "run_1")] \
            == ["births_not_null"]
        assert qa_store.results_for_run(clean_qa_history, "run_1",
                                        supply_state=qa_store.IN_DEVELOPMENT) == []

    def test_one_write_splits_a_mixed_collection_between_the_two(
            self, tmp_path, monkeypatch, clean_qa_history, finish_runs):
        """The case a per-caller flag could not express: one tool invocation
        over a collection holding both kinds."""
        _asset_with([AGREED, SAMPLE], tmp_path, monkeypatch)
        write_qa_result("a", "b", "run_1", "2026-01-01T00:00:00+00:00", "dbt-core",
                        {"raw": True},
                        [_result("birth-registrations", "births_not_null"),
                         _result("cp-referrals", "referrals_not_null")])
        finish_runs("run_1", agency="a", collection="b")

        agreed = qa_store.results_for_run(clean_qa_history, "run_1")
        developing = qa_store.results_for_run(clean_qa_history, "run_1",
                                              supply_state=qa_store.IN_DEVELOPMENT)
        assert [r["check_id"] for r in agreed] == ["births_not_null"]
        assert [r["check_id"] for r in developing] == ["referrals_not_null"]

    def test_the_default_read_cannot_see_it_without_asking(
            self, tmp_path, monkeypatch, clean_qa_history, finish_runs):
        """Criterion 10 the way round that fails safe: a reader that has
        never heard of this requirement counts nothing it should not."""
        _asset_with([AGREED, SAMPLE], tmp_path, monkeypatch)
        write_qa_result("a", "b", "run_1", "2026-01-01T00:00:00+00:00", "dbt-core",
                        {"raw": True}, [_result("cp-referrals", "referrals_not_null")])
        finish_runs("run_1", agency="a", collection="b")

        assert qa_store.results_for_run(clean_qa_history, "run_1") == []
        assert qa_store.history_for_check(clean_qa_history, "referrals_not_null") == []

    def test_its_verdict_is_the_real_one(
            self, tmp_path, monkeypatch, clean_qa_history, finish_runs):
        """Criterion 7. Developing a check means seeing whether it passes,
        so nothing here suppresses or rewrites the status the tool found."""
        _asset_with([AGREED, SAMPLE], tmp_path, monkeypatch)
        write_qa_result("a", "b", "run_1", "2026-01-01T00:00:00+00:00", "dbt-core",
                        {"raw": True},
                        [_result("cp-referrals", "a", status="fail"),
                         _result("cp-referrals", "b", status="warn"),
                         _result("cp-referrals", "c", status="pass")])
        finish_runs("run_1", agency="a", collection="b")

        rows = qa_store.results_for_run(clean_qa_history, "run_1",
                                        supply_state=qa_store.IN_DEVELOPMENT)
        assert {r["check_id"]: r["status"] for r in rows} == {
            "a": "fail", "b": "warn", "c": "pass"}
        assert {r["row_count_invalid"] for r in rows} == {3}

    def test_the_caller_s_own_record_is_stamped_too(
            self, tmp_path, monkeypatch, clean_qa_history, finish_runs):
        """A LIVE run writes reports/results_*.json from the list it holds
        in memory while a rebuild reads the database, so a field on one and
        not the other makes the two paths build different dashboards."""
        _asset_with([AGREED, SAMPLE], tmp_path, monkeypatch)
        verified = [_result("cp-referrals", "referrals_not_null"),
                    _result("birth-registrations", "births_not_null")]
        write_qa_result("a", "b", "run_1", "2026-01-01T00:00:00+00:00", "dbt-core",
                        {"raw": True}, verified)

        assert verified[0]["supply_state"] == qa_store.IN_DEVELOPMENT
        assert "supply_state" not in verified[1]

    def test_a_rebuilt_record_says_the_same_thing(
            self, tmp_path, monkeypatch, clean_qa_history, finish_runs):
        """The other end of the same parity: what comes back out carries
        `supply_state` for an in-development record and not for an agreed
        one, so an agreed record keeps the exact keys it always had."""
        from qa_tools.common import qa_results_reader

        _asset_with([AGREED, SAMPLE], tmp_path, monkeypatch)
        write_qa_result("a", "b", "run_1", "2026-01-01T00:00:00+00:00", "dbt-core",
                        {"raw": True},
                        [_result("cp-referrals", "referrals_not_null"),
                         _result("birth-registrations", "births_not_null")])
        finish_runs("run_1", agency="a", collection="b")

        back = qa_results_reader.read_one("a", "b", "run_1", "dbt-core",
                                          supply_state=None)
        by_check = {r["check_id"]: r for r in back}
        assert by_check["referrals_not_null"]["supply_state"] == qa_store.IN_DEVELOPMENT
        assert "supply_state" not in by_check["births_not_null"]


class TestGraduationLeavesTheRecordReadable:
    """Criteria 16 and 19."""

    def test_an_in_development_record_survives_the_dataset_growing_up(
            self, tmp_path, monkeypatch, clean_qa_history, finish_runs):
        """Developing a check is real work whose record should survive."""
        _asset_with([SAMPLE], tmp_path, monkeypatch)
        write_qa_result("a", "b", "run_1", "2026-01-01T00:00:00+00:00", "dbt-core",
                        {"raw": True}, [_result("cp-referrals", "referrals_not_null")])
        finish_runs("run_1", agency="a", collection="b")

        # It graduates: the configuration names a calendar.
        _asset_with([GRADUATED], tmp_path, monkeypatch)
        assert schedule.no_calendar("cp-referrals") is None

        rows = qa_store.results_for_run(clean_qa_history, "run_1",
                                        supply_state=qa_store.IN_DEVELOPMENT)
        assert [r["check_id"] for r in rows] == ["referrals_not_null"]

    def test_and_its_next_run_records_the_real_thing(
            self, tmp_path, monkeypatch, clean_qa_history, finish_runs):
        """From graduation on it is rolled up like any other, so its NEW
        results are agreed - the old ones are not retrospectively promoted."""
        _asset_with([SAMPLE], tmp_path, monkeypatch)
        write_qa_result("a", "b", "run_1", "2026-01-01T00:00:00+00:00", "dbt-core",
                        {"raw": True}, [_result("cp-referrals", "referrals_not_null")])
        _asset_with([GRADUATED], tmp_path, monkeypatch)
        write_qa_result("a", "b", "run_2", "2026-01-02T00:00:00+00:00", "dbt-core",
                        {"raw": True}, [_result("cp-referrals", "referrals_not_null")])
        finish_runs("run_1", "run_2", agency="a", collection="b")

        assert qa_store.results_for_run(clean_qa_history, "run_2") != []
        assert qa_store.results_for_run(clean_qa_history, "run_1") == []

    def test_a_re_run_after_graduation_clears_the_stale_in_development_row(
            self, tmp_path, monkeypatch, clean_qa_history, finish_runs):
        """The empty bucket earning its place. Re-running the SAME run id
        after graduation must not leave the in-development verdict standing
        beside the agreed one - two verdicts for one check in one run."""
        _asset_with([SAMPLE], tmp_path, monkeypatch)
        write_qa_result("a", "b", "run_1", "2026-01-01T00:00:00+00:00", "dbt-core",
                        {"raw": True}, [_result("cp-referrals", "referrals_not_null")])
        _asset_with([GRADUATED], tmp_path, monkeypatch)
        write_qa_result("a", "b", "run_1", "2026-01-01T00:00:00+00:00", "dbt-core",
                        {"raw": True}, [_result("cp-referrals", "referrals_not_null")])
        finish_runs("run_1", agency="a", collection="b")

        assert len(qa_store.results_for_run(clean_qa_history, "run_1")) == 1
        assert qa_store.results_for_run(clean_qa_history, "run_1",
                                        supply_state=qa_store.IN_DEVELOPMENT) == []


class TestAnyNumberOfThem:
    """Criterion 12, at the recording layer."""

    def test_two_in_one_collection_are_both_in_development(
            self, tmp_path, monkeypatch, clean_qa_history, finish_runs):
        _asset_with([AGREED, SAMPLE, SECOND_SAMPLE], tmp_path, monkeypatch)
        assert sample_data.sample_dataset_ids() == frozenset({"cp-referrals", "cp-outcomes"})
        write_qa_result("a", "b", "run_1", "2026-01-01T00:00:00+00:00", "dbt-core",
                        {"raw": True},
                        [_result("cp-referrals", "x"), _result("cp-outcomes", "y")])
        finish_runs("run_1", agency="a", collection="b")

        rows = qa_store.results_for_run(clean_qa_history, "run_1",
                                        supply_state=qa_store.IN_DEVELOPMENT)
        assert sorted(r["check_id"] for r in rows) == ["x", "y"]


class TestWhereTheDataItself_Lands:
    """Criteria 4 and 5."""

    def test_a_calendar_less_dataset_stages_into_the_sample_schema(
            self, tmp_path, monkeypatch):
        _asset_with([AGREED, SAMPLE], tmp_path, monkeypatch)
        assert sample_data.schema_for("run_001", "cp-referrals") == supply_db.SAMPLE_SCHEMA

    def test_an_agreed_dataset_stages_into_shared_staging(self, tmp_path, monkeypatch):
        _asset_with([AGREED, SAMPLE], tmp_path, monkeypatch)
        assert sample_data.schema_for("run_001", "birth-registrations") \
            == supply_db.STAGING_SCHEMA

    def test_the_sample_schema_is_none_of_the_others(self):
        """Criterion 4 names three things it must not be, so this asserts
        all three rather than trusting the constant to stay distinct."""
        assert supply_db.SAMPLE_SCHEMA not in (
            supply_db.STAGING_SCHEMA, supply_db.REJECTED_SCHEMA)
        from qa_tools.common import period_schema
        assert not supply_db.SAMPLE_SCHEMA.startswith(period_schema.PERIOD_SCHEMA_PREFIX)

    def test_nothing_that_computes_a_period_reads_it(self):
        """Criterion 5's by-construction claim, asserted as the absence it
        is: the modules that do period, slot, lateness and promotion
        arithmetic never name the sample schema, so there is no filter for
        one of them to forget."""
        import pathlib

        for name in ("assignment", "slots", "period_schema", "backlog", "outstanding",
                     "runway", "landed_on_accepted"):
            source = pathlib.Path("qa_tools/common", f"{name}.py").read_text()
            assert "SAMPLE_SCHEMA" not in source, name
            assert "sample_data" not in source, name


class TestDiscardingIsSomethingAPersonDoes:
    """Criteria 17 and 18."""

    def test_discard_removes_the_dataset_s_tables_from_the_sample_schema(
            self, tmp_path, monkeypatch, supply_dsn):
        _asset_with([AGREED, SAMPLE], tmp_path, monkeypatch)
        with supply_db.connect(label="test-discard") as conn:
            supply_db.ensure_schemas(conn)
            mine = supply_db.staged_table("cp_referrals", "2026-01-01T00:00:00+00:00")
            other = supply_db.staged_table("birth_registrations", "2026-01-01T00:00:00+00:00")
            for physical in (mine, other):
                conn.execute(
                    f'CREATE TABLE "{supply_db.SAMPLE_SCHEMA}"."{physical}" (x int)')
            try:
                assert sample_data.staged_tables(conn, "cp-referrals") == [mine]
                assert sample_data.discard(conn, "cp-referrals") == [mine]
                assert sample_data.staged_tables(conn, "cp-referrals") == []
                # AND ONLY THAT DATASET'S. A discard is per dataset, so a
                # neighbour's sample data in the same schema is untouched.
                assert sample_data.staged_tables(conn, "birth-registrations") == [other]
            finally:
                for physical in (mine, other):
                    conn.execute(
                        f'DROP TABLE IF EXISTS "{supply_db.SAMPLE_SCHEMA}"."{physical}" CASCADE')

    def test_discarding_twice_is_not_an_error(self, tmp_path, monkeypatch, supply_dsn):
        _asset_with([AGREED, SAMPLE], tmp_path, monkeypatch)
        with supply_db.connect(label="test-discard-twice") as conn:
            supply_db.ensure_schemas(conn)
            assert sample_data.discard(conn, "cp-referrals") == []

    def test_only_the_terminal_calls_discard(self):
        """Criterion 18, as a real constraint rather than a docstring.

        NOT AT GRADUATION, NOT ON A SCHEDULE, AND NOT AS A SIDE EFFECT OF
        ANY OTHER OPERATION - Keith's own condition when he settled the
        fork. The one caller is the command a person types, so this asserts
        the call graph rather than the intent: anything else calling it
        would make the discard automatic somewhere, which is the thing
        forbidden.
        """
        import pathlib
        import subprocess

        out = subprocess.run(
            ["grep", "-rn", r"sample_data\.discard\|from qa_tools.common.sample_data import",
             "--include=*.py", "qa_tools", "pipeline", "cli", "generator", "dashboard",
             "aws", "scripts"],
            capture_output=True, text=True).stdout
        callers = {line.split(":")[0] for line in out.splitlines() if line.strip()}
        assert callers == {"cli/supply.py"}, out
        # AND THE COMMAND ASKS FIRST, like `mothman supply tidy` - the two
        # destructive commands in this group behave the same way.
        source = pathlib.Path("cli/supply.py").read_text()
        assert "click.confirm" in source.split("def discard_sample_command")[1]


class TestACrossTableCheckMaySpanThem:
    """Criteria 13, 14 and 15's recording half.

    THE DECLARATION IS MONKEYPATCHED rather than authored into a real
    contract, and deliberately so: `_declared_reads_tables()` parses every
    real check source, and adding a cross-table check over a dataset that
    does not exist would need a contract, a model and a Soda file for it.
    What is under test is the RULE - which state a spanning record is
    recorded under, given who participates - and the rule takes the
    declaration as input.
    """

    @staticmethod
    def _declaring(monkeypatch, mapping: dict[str, list[str]]):
        from qa_tools.common import qa_results_writer

        monkeypatch.setattr(qa_results_writer, "_declared_reads_tables", lambda: mapping)

    def test_a_check_among_two_calendar_less_datasets_is_in_development(
            self, tmp_path, monkeypatch, clean_qa_history, finish_runs):
        """Criterion 13: authored and run exactly as for datasets that have
        a calendar - so it lands in the reserved cross-table scope, not on
        either participant."""
        _asset_with([AGREED, SAMPLE, SECOND_SAMPLE], tmp_path, monkeypatch)
        self._declaring(monkeypatch, {"referrals_match_outcomes": ["cp_referrals", "cp_outcomes"]})
        write_qa_result("a", "b", "run_1", "2026-01-01T00:00:00+00:00", "dbt-core",
                        {"raw": True},
                        [_result("cp-referrals", "referrals_match_outcomes")])
        finish_runs("run_1", agency="a", collection="b")

        spanning = qa_store.cross_table_results(clean_qa_history, "run_1",
                                               supply_state=qa_store.IN_DEVELOPMENT)
        assert [r["check_id"] for r in spanning] == ["referrals_match_outcomes"]
        assert qa_store.results_for_run(clean_qa_history, "run_1",
                                        supply_state=None) == []

    def test_a_mixed_check_is_allowed_and_recorded_as_in_development(
            self, tmp_path, monkeypatch, clean_qa_history, finish_runs):
        """Criteria 14 and 15. Keith, 2026-09-27: "allow it, but don't let
        it affect the agreed data set". ANY unagreed participant makes the
        whole verdict in-development, which is what stops it reaching the
        agreed dataset - not a second filter somewhere downstream."""
        _asset_with([AGREED, SAMPLE], tmp_path, monkeypatch)
        self._declaring(monkeypatch,
                        {"births_match_referrals": ["birth_registrations", "cp_referrals"]})
        write_qa_result("a", "b", "run_1", "2026-01-01T00:00:00+00:00", "dbt-core",
                        {"raw": True},
                        [_result("birth-registrations", "births_match_referrals")])
        finish_runs("run_1", agency="a", collection="b")

        assert qa_store.cross_table_results(clean_qa_history, "run_1") == []
        spanning = qa_store.cross_table_results(clean_qa_history, "run_1",
                                                supply_state=qa_store.IN_DEVELOPMENT)
        assert [r["check_id"] for r in spanning] == ["births_match_referrals"]

    def test_a_check_among_agreed_datasets_only_is_unaffected(
            self, tmp_path, monkeypatch, clean_qa_history, finish_runs):
        """The regression this could most easily cause: every existing
        cross-table check stays agreed."""
        _asset_with([AGREED, SAMPLE], tmp_path, monkeypatch)
        self._declaring(monkeypatch, {"births_self": ["birth_registrations"]})
        write_qa_result("a", "b", "run_1", "2026-01-01T00:00:00+00:00", "dbt-core",
                        {"raw": True}, [_result("birth-registrations", "births_self")])
        finish_runs("run_1", agency="a", collection="b")

        assert [r["check_id"] for r in
                qa_store.cross_table_results(clean_qa_history, "run_1")] == ["births_self"]

    def test_a_declared_table_no_dataset_maps_cannot_make_it_in_development(
            self, tmp_path, monkeypatch, clean_qa_history, finish_runs):
        """An unresolvable table name is the hierarchy gate's to report, and
        must not be read here as an unagreed participant - that would flip a
        real cross-table verdict out of history over a typo."""
        _asset_with([AGREED, SAMPLE], tmp_path, monkeypatch)
        self._declaring(monkeypatch,
                        {"births_self": ["birth_registrations", "no_such_table"]})
        write_qa_result("a", "b", "run_1", "2026-01-01T00:00:00+00:00", "dbt-core",
                        {"raw": True}, [_result("birth-registrations", "births_self")])
        finish_runs("run_1", agency="a", collection="b")

        assert [r["check_id"] for r in
                qa_store.cross_table_results(clean_qa_history, "run_1")] == ["births_self"]


class TestARunCanReadBothSchemasAtOnce:
    """Criteria 13 and 14's run half - the views a check actually reads
    through."""

    def test_a_run_gets_views_over_staging_and_sample_together(
            self, tmp_path, monkeypatch, supply_dsn):
        """dbt and Soda read across schemas but only within one search
        path, so a cross-table check spanning both kinds needs its views
        side by side in the run's own schema."""
        _asset_with([AGREED, SAMPLE], tmp_path, monkeypatch)
        arrival = "2026-01-01T00:00:00+00:00"
        agreed = supply_db.staged_table("birth_registrations", arrival)
        sample = supply_db.staged_table("cp_referrals", arrival)
        with supply_db.connect(label="test-two-source-views") as conn:
            supply_db.ensure_schemas(conn)
            conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{agreed}" (x int)')
            conn.execute(f'CREATE TABLE "{supply_db.SAMPLE_SCHEMA}"."{sample}" (y int)')
            try:
                res = supply_db.create_run_views(conn, "run_two_source", {
                    "birth_registrations": [agreed]},
                    source_schema=supply_db.STAGING_SCHEMA)
                res = supply_db.add_run_views(conn, "run_two_source", {
                    "cp_referrals": [sample]}, supply_db.SAMPLE_SCHEMA, res)

                assert res.resolved == {"birth_registrations": agreed,
                                        "cp_referrals": sample}
                schema = supply_db.run_schema("run_two_source")
                views = {row[0] for row in conn.execute(
                    "SELECT table_name FROM information_schema.views "
                    "WHERE table_schema = ?", [schema]).fetchall()}
                assert views == {"birth_registrations", "cp_referrals"}
            finally:
                supply_db.drop_run_schema(conn, "run_two_source")
                conn.execute(f'DROP TABLE IF EXISTS "{supply_db.STAGING_SCHEMA}"."{agreed}" CASCADE')
                conn.execute(f'DROP TABLE IF EXISTS "{supply_db.SAMPLE_SCHEMA}"."{sample}" CASCADE')

    def test_adding_views_does_not_throw_away_the_first_source(
            self, tmp_path, monkeypatch, supply_dsn):
        """Why add_run_views exists rather than a flag on create_run_views:
        that function OWNS the schema and drops it, which is what makes a
        re-run idempotent."""
        with supply_db.connect(label="test-add-keeps") as conn:
            supply_db.ensure_schemas(conn)
            physical = supply_db.staged_table("birth_registrations", "2026-01-01T00:00:00+00:00")
            conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" (x int)')
            try:
                first = supply_db.create_run_views(
                    conn, "run_keeps", {"birth_registrations": [physical]},
                    source_schema=supply_db.STAGING_SCHEMA)
                after = supply_db.add_run_views(conn, "run_keeps", {}, supply_db.SAMPLE_SCHEMA,
                                                first)
                assert after.resolved == {"birth_registrations": physical}
            finally:
                supply_db.drop_run_schema(conn, "run_keeps")
                conn.execute(
                    f'DROP TABLE IF EXISTS "{supply_db.STAGING_SCHEMA}"."{physical}" CASCADE')

    def test_the_cp_builder_splits_its_tables_by_what_is_agreed(
            self, tmp_path, monkeypatch):
        """Read from configuration on every call rather than at import,
        because graduation IS a configuration change."""
        from qa_tools.cp import build_cp_warehouses

        monkeypatch.setattr(build_cp_warehouses, "TABLES",
                            ["birth_registrations", "cp_referrals"])
        _asset_with([AGREED, SAMPLE], tmp_path, monkeypatch)
        assert build_cp_warehouses._sample_and_agreed_tables() == (
            ["cp_referrals"], ["birth_registrations"])

        _asset_with([AGREED, GRADUATED], tmp_path, monkeypatch)
        assert build_cp_warehouses._sample_and_agreed_tables() == (
            [], ["birth_registrations", "cp_referrals"])


class TestTheDashboardReportsItAgainstTheRightDataset:
    """Criterion 15's report half, at the layer a reader actually sees.

    BOTH ENDS OF THE SAME RULE, which this project has a scar for: item 74
    shipped a correct data layer and a dashboard whose own transform
    disagreed, rendering a check with 14 real violations green. The record
    is keyed in-development by the writer, and this is the transform that
    has to honour it.
    """

    @staticmethod
    def _sharing(monkeypatch, reads: dict[str, list[str]]):
        from qa_tools.common import tables_read

        monkeypatch.setattr(tables_read, "declared_by_check_id", lambda checks: reads)

    def test_a_mixed_result_reaches_the_calendar_less_table_only(
            self, tmp_path, monkeypatch):
        from pipeline import build_cp_dashboard_data as build_cp

        _asset_with([AGREED, SAMPLE], tmp_path, monkeypatch)
        self._sharing(monkeypatch,
                      {"births_match_referrals": ["birth_registrations", "cp_referrals"]})
        record = _result("cp-referrals", "births_match_referrals",
                         supply_state=qa_store.IN_DEVELOPMENT)
        by_table = {"birth_registrations": [], "cp_referrals": []}
        build_cp.share_cross_table_results([record], by_table)

        assert by_table["cp_referrals"] == [record]
        assert by_table["birth_registrations"] == []

    def test_an_agreed_cross_table_result_still_reaches_every_participant(
            self, tmp_path, monkeypatch):
        """REQ-QAC-037's own behaviour, unchanged - the regression this
        exclusion could most easily cause."""
        from pipeline import build_cp_dashboard_data as build_cp

        _asset_with([AGREED, SAMPLE], tmp_path, monkeypatch)
        self._sharing(monkeypatch,
                      {"births_and_more": ["birth_registrations", "cp_referrals"]})
        record = _result("birth-registrations", "births_and_more")
        by_table = {"birth_registrations": [], "cp_referrals": []}
        build_cp.share_cross_table_results([record], by_table)

        assert by_table["cp_referrals"] == [record]
        assert by_table["birth_registrations"] == [record]

    def test_the_two_are_the_same_record_shared_not_copied(
            self, tmp_path, monkeypatch):
        """Criterion 2 of REQ-QAC-037 forbids a second record, not a second
        reader - so the identity matters, not just the equality."""
        from pipeline import build_cp_dashboard_data as build_cp

        _asset_with([AGREED, SAMPLE, SECOND_SAMPLE], tmp_path, monkeypatch)
        self._sharing(monkeypatch,
                      {"referrals_match_outcomes": ["cp_referrals", "cp_outcomes"]})
        record = _result("cp-referrals", "referrals_match_outcomes",
                         supply_state=qa_store.IN_DEVELOPMENT)
        by_table = {"cp_referrals": [], "cp_outcomes": []}
        build_cp.share_cross_table_results([record], by_table)

        assert by_table["cp_referrals"][0] is record
        assert by_table["cp_outcomes"][0] is record


class TestATableNameIsNotADatasetId:
    """A real regression, found by CI on 2026-09-28 and fixed here.

    `build_cp_warehouses.add_table_to_run()` defaults `dataset_id` to the
    TABLE name when a caller does not pass one, so the first version of the
    staging change asked `is_sample("cp_clients")` and got
    UnknownDatasetError - six CLI tests down, every real Child Protection
    check refusing to run. The strings differ by one character per word and
    this project has shipped the same confusion before (tables_read.attach,
    where a check recorded its own table as something it read).
    """

    def test_asking_about_a_table_name_does_not_raise(self, tmp_path, monkeypatch):
        _asset_with([AGREED, SAMPLE], tmp_path, monkeypatch)
        assert sample_data.is_sample_table("cp_referrals") is True
        assert sample_data.is_sample_table("birth_registrations") is False

    def test_a_table_nothing_maps_is_not_sample(self, tmp_path, monkeypatch):
        """The safe direction: an unresolvable name is the hierarchy gate's
        to report, and reading it as calendar-less here would divert a real
        supply into the sample schema over a typo."""
        _asset_with([AGREED, SAMPLE], tmp_path, monkeypatch)
        assert sample_data.is_sample_table("no_such_table") is False

    def test_asking_about_a_dataset_id_as_though_it_were_a_table_is_false(
            self, tmp_path, monkeypatch):
        """The bug's own shape, stated as an assertion: the hyphenated id
        is not a table, so this must answer False rather than raise - which
        is what makes the two functions impossible to confuse silently."""
        _asset_with([AGREED, SAMPLE], tmp_path, monkeypatch)
        assert sample_data.is_sample_table("cp-referrals") is False

    def test_both_staging_paths_decide_from_the_table(self):
        """Structural, because the unit test above cannot catch a CALLER
        passing the wrong one - which is exactly how this got through.

        Neither builder may ask the dataset-id form: one of them has only a
        table name that is sometimes standing in for a dataset id, and the
        other would then be one edit away from the same fault.
        """
        import pathlib

        for path in ("qa_tools/cp/build_cp_warehouses.py",
                     "qa_tools/bdm/build_per_run_warehouses.py"):
            source = pathlib.Path(path).read_text()
            assert "ensure_schema_for_table(" in source, path
            assert "sample_data.ensure_schema_for(" not in source, path
