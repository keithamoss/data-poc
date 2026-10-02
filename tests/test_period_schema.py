"""One period's schema, with the staged delivery overlaid
(REQ-PIPE-035).

Every test here uses its OWN DuckDB file under tmp_path rather than the
shared per-worker one. These create and drop schemas, which is a write,
and DuckDB gives a writer an exclusive lock over the whole database -
so sharing would serialise the module against everything else and make
a failure surface as somebody else's crash.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import duckdb
import pytest

from qa_tools.common import period_schema as ps
from qa_tools.common import supply_db


@pytest.fixture
def conn(tmp_path):
    connection = duckdb.connect(str(tmp_path / "period.duckdb"))
    connection.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')
    try:
        yield connection
    finally:
        connection.close()


def _stage(conn, physical, rows):
    values = ", ".join(f"({v})" for v in rows)
    conn.execute(
        f'CREATE OR REPLACE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" AS '
        f"SELECT * FROM (VALUES {values}) AS t(n)")


def _promote(conn, period, physical, rows):
    ps.ensure_period_schema(conn, period)
    values = ", ".join(f"({v})" for v in rows)
    conn.execute(
        f'CREATE OR REPLACE TABLE "{ps.period_schema(period)}"."{physical}" AS '
        f"SELECT * FROM (VALUES {values}) AS t(n)")


class TestAPeriodNameIsNotAnIdentifier:
    """A period name is AUTHORED by whoever agreed the calendar -
    "2026-Q3", "Nov-Jan window" - so it is not a SQL identifier and must
    never be pasted into one."""

    @pytest.mark.parametrize("name,schema", [
        ("2026-Q3", "period_2026_q3"),
        ("2026-08-24", "period_2026_08_24"),
        ("Nov-Jan window", "period_nov_jan_window"),
        ("FY26/27", "period_fy26_27"),
    ])
    def test_the_schema_is_the_name_normalised_and_readable(self, name, schema):
        """Asserted as literal strings rather than a round trip, because
        being READABLE is the property that matters and a round trip
        cannot see it. These same names used to produce
        `period_2026_2d_51_33`, which satisfied a round-trip assertion
        perfectly."""
        assert ps.period_schema(name) == schema

    def test_it_is_lowercase_whatever_the_name_was(self):
        """The load-bearing half. PostgreSQL folds an unquoted identifier
        to lower case and both dbt and Soda write these names unquoted,
        so a surviving capital is a schema those tools cannot see - which
        surfaces as every check in the run failing on a missing
        relation."""
        assert ps.period_schema("FY26/27").islower()

    def test_the_period_is_recoverable_enough_to_name(self):
        """NOT an exact inverse any more, deliberately - see
        period_of()'s own docstring. It identifies the period to a
        person, which is all any caller here needed; the authored name
        lives in contract/data-asset.yaml."""
        assert ps.period_of(ps.period_schema("2026-Q3")) == "2026_q3"

    def test_two_names_that_would_share_a_schema_are_reported(self):
        """THE GUARD THAT REPLACED THE HEX ENCODING. The failure worth
        preventing is not an error, it is a MERGE: two periods sharing
        one schema silently combines their promoted data and nothing
        downstream could notice. Normalising cannot keep them apart, so
        the collision is refused where the calendar is authored instead."""
        assert ps.collisions_in(["2026-Q3", "2026_Q3"]) == {
            "period_2026_q3": ["2026-Q3", "2026_Q3"]}

    def test_names_that_differ_by_more_than_punctuation_are_fine(self):
        assert ps.collisions_in(["2026-Q3", "2026-Q4", "FY26/27"]) == {}

    def test_the_same_name_twice_is_not_a_collision(self):
        """A duplicate is a different config error, caught by the
        schedule validator's own repeated-period check. Reporting it here
        too would send a reader looking for a second period that does not
        exist."""
        assert ps.collisions_in(["2026-Q3", "2026-Q3"]) == {}

    def test_the_empty_name_is_refused(self):
        """The only one refused. A stricter rule would be this module
        inventing a naming policy for calendars it does not own; an
        empty name is different in kind, because it identifies no
        period at all and would give every nameless caller one schema."""
        with pytest.raises(ps.PeriodSchemaError):
            ps.period_schema("")

    def test_a_name_that_normalises_to_nothing_is_refused(self):
        """`---` has no usable characters at all. It used to round-trip
        as `period__2d__2d__2d_`; now there is nothing left to build a
        name from, which is a real config error rather than a schema
        nobody can read."""
        with pytest.raises(ValueError):
            ps.period_schema("---")

    def test_a_schema_that_is_not_a_period_schema_reads_as_none(self):
        assert ps.period_of(supply_db.STAGING_SCHEMA) is None
        assert ps.period_of("qa_run_run_01") is None


class TestTheNewestVersionWithinAPeriod:
    """Criterion 4: where a period's schema holds more than one version
    of a table - a supply and its resupplies - read the newest."""

    def test_the_latest_arrival_wins(self):
        assert ps.newest(["t__20260824010000", "t__20260826010000",
                           "t__20260825010000"]) == "t__20260826010000"

    def test_an_ordinal_breaks_a_tie_within_one_arrival(self):
        assert ps.newest(["t__20260824010000", "t__20260824010000__2"]) \
            == "t__20260824010000__2"

    def test_a_name_this_project_did_not_mint_never_wins(self):
        """It cannot be ordered against the others, and being wrong
        about WHICH version was read is the one outcome worth
        avoiding."""
        assert ps.newest(["t__20260824010000", "some_hand_made_table"]) \
            == "t__20260824010000"

    def test_no_candidates_is_absence_rather_than_an_error(self):
        assert ps.newest([]) is None

    def test_the_newest_promoted_version_is_what_a_run_reads(self, conn):
        _promote(conn, "2026-Q3", "carers__20260801010000", [1])
        _promote(conn, "2026-Q3", "carers__20260815010000", [2, 3])

        res = ps.create_overlay_views(
            conn, "run_1", "2026-Q3", staged={},
            promoted=ps.promoted_in(conn, "2026-Q3", ["carers"]))

        assert res.resolution.resolved["carers"] == "carers__20260815010000"
        rows = conn.execute(f'SELECT COUNT(*) FROM "{res.resolution.schema}"."carers"').fetchone()
        assert rows[0] == 2


class TestTheStagedDeliveryIsOverlaid:
    """Criterion 3: the candidate under test, alongside the tables
    already promoted into that period."""

    def test_a_staged_table_shadows_the_promoted_one_of_the_same_name(self, conn):
        _promote(conn, "2026-Q3", "clients__20260801010000", [1, 2, 3])
        _stage(conn, "clients__20260901010000", [9])

        res = ps.create_overlay_views(
            conn, "run_1", "2026-Q3",
            staged={"clients": ["clients__20260901010000"]},
            promoted=ps.promoted_in(conn, "2026-Q3", ["clients"]))

        assert res.source["clients"] == ps.FROM_STAGING
        assert conn.execute(
            f'SELECT n FROM "{res.resolution.schema}"."clients"').fetchall() == [(9,)]

    def test_a_table_only_the_period_has_is_read_from_the_period(self, conn):
        """This is the whole reason the overlay exists: a check
        comparing placements to carers reads the delivery's placements
        against the carers already promoted for that period."""
        _promote(conn, "2026-Q3", "carers__20260801010000", [1, 2])
        _stage(conn, "placements__20260901010000", [7])

        res = ps.create_overlay_views(
            conn, "run_1", "2026-Q3",
            staged={"placements": ["placements__20260901010000"]},
            promoted=ps.promoted_in(conn, "2026-Q3", ["carers", "placements"]))

        assert res.source == {"placements": ps.FROM_STAGING, "carers": ps.FROM_PERIOD}
        joined = conn.execute(
            f'SELECT COUNT(*) FROM "{res.resolution.schema}"."placements" p '
            f'CROSS JOIN "{res.resolution.schema}"."carers" c').fetchone()
        assert joined[0] == 2

    def test_an_ambiguous_staged_name_offers_nothing_of_its_own(self, conn):
        """Staging offers nothing where two files claim one name - and
        THAT is what this test still holds.

        IT USED TO ASSERT MORE THAN THAT, and the extra part was
        superseded: it required that the view not resolve at all, so
        that no check could read the table by any route. REQ-PIPE-079
        criteria 12 and 13 (signed 2026-09-26) and REQ-PIPE-105
        criterion 8 (signed 2026-09-28) draw a line the flat rule did
        not - the contested table's OWN checks must not run, and a
        check that merely READS it resolves against the period's
        promoted version like any table the delivery did not bring.
        tests/test_contested_staging.py holds that split; what remains
        here is the half that did not change.
        """
        _promote(conn, "2026-Q3", "clients__20260801010000", [1, 2, 3])
        _stage(conn, "clients__20260901010000__1", [8])
        _stage(conn, "clients__20260901010000__2", [9])

        res = ps.create_overlay_views(
            conn, "run_1", "2026-Q3",
            staged={"clients": ["clients__20260901010000__1",
                                 "clients__20260901010000__2"]},
            promoted=ps.promoted_in(conn, "2026-Q3", ["clients"]))

        assert "clients" in res.resolution.ambiguous
        assert res.source["clients"] == ps.FROM_PERIOD
        assert res.resolution.resolved["clients"] == "clients__20260801010000"

    def test_a_name_neither_staged_nor_promoted_is_absent(self, conn):
        res = ps.create_overlay_views(
            conn, "run_1", "2026-Q3", staged={"clients": []},
            promoted={"clients": []})
        assert res.resolution.absent == ["clients"]


class TestOneSchemaHoldsTheWholeDataAsset:
    """Criterion 5: across agencies and collections, so a cross-agency
    check is an ordinary same-schema query rather than an assembly
    step."""

    def test_two_agencies_tables_join_without_an_assembly_step(self, conn):
        _promote(conn, "2026-Q3", "birth_registrations__20260801010000", [1, 2])
        _promote(conn, "2026-Q3", "cp_clients__20260801010000", [1])

        res = ps.create_overlay_views(
            conn, "run_1", "2026-Q3", staged={},
            promoted=ps.promoted_in(conn, "2026-Q3",
                                     ["birth_registrations", "cp_clients"]))

        assert sorted(res.readable) == ["birth_registrations", "cp_clients"]
        joined = conn.execute(
            f'SELECT COUNT(*) FROM "{res.resolution.schema}"."birth_registrations" b '
            f'JOIN "{res.resolution.schema}"."cp_clients" c ON b.n = c.n').fetchone()
        assert joined[0] == 1


class TestRedForUnrun:
    """Criteria 6, 7 and 8. A check that COULD NOT RUN is not a check
    with nothing to say."""

    def _resolution(self, resolved=(), ambiguous=None, absent=()):
        res = supply_db.Resolution(run_id="run_1", schema="qa_run_run_1",
                                    resolved={n: f"{n}__x" for n in resolved},
                                    ambiguous=dict(ambiguous or {}),
                                    absent=list(absent))
        return ps.PeriodResolution(period="2026-Q3", resolution=res)

    def test_a_missing_dependency_reads_RED_and_names_the_table(self):
        verdict = ps.check_readiness(
            ["placements", "carers"],
            self._resolution(resolved=["placements"], absent=["carers"]))
        assert verdict.status == ps.RED
        assert verdict.names == ("carers",)
        assert "carers" in verdict.describe()

    def test_a_missing_dependency_is_never_reported_as_no_data(self):
        """Nodata is reserved for "nothing was owed". A check that could
        not run against an absent table HAS something to say."""
        verdict = ps.check_readiness(
            ["carers"], self._resolution(absent=["carers"]))
        assert verdict.status != ps.NODATA

    def test_an_AMBIGUOUS_dependency_counts_as_missing_not_present(self):
        """The hole an earlier wording left: two files ARE present, so
        read literally "not present in the staged delivery" would not
        fire and an implementer could conclude the table was
        available (REQ-PIPE-068 criterion 4)."""
        verdict = ps.check_readiness(
            ["clients"],
            self._resolution(ambiguous={"clients": ["a__1", "a__2"]}))
        assert verdict is not None
        assert verdict.status == ps.RED
        assert verdict.names == ("clients",)

    def test_a_check_whose_tables_all_resolve_simply_runs(self):
        assert ps.check_readiness(
            ["placements", "carers"],
            self._resolution(resolved=["placements", "carers"])) is None

    def test_an_owed_but_unfilled_reference_period_reads_RED_and_names_it(self):
        verdict = ps.check_readiness(
            ["clients"], self._resolution(resolved=["clients"]),
            reference_period="2026-Q2", reference_filled=False,
            any_prior_period_owed=True)
        assert verdict.status == ps.RED
        assert verdict.names == ("2026-Q2",)
        assert "2026-Q2" in verdict.describe()

    def test_a_brand_new_dataset_reads_NO_DATA_rather_than_red(self):
        """The carve-out, and the reason it exists: without it every new
        dataset starts life red on all its drift checks, which is how
        people learn to ignore a signal."""
        verdict = ps.check_readiness(
            ["clients"], self._resolution(resolved=["clients"]),
            reference_period="2026-Q2", reference_filled=False,
            any_prior_period_owed=False)
        assert verdict.status == ps.NODATA
        assert verdict.reason == ps.NO_PRIOR_PERIOD

    def test_a_filled_reference_period_simply_runs(self):
        assert ps.check_readiness(
            ["clients"], self._resolution(resolved=["clients"]),
            reference_period="2026-Q2", reference_filled=True) is None

    def test_a_check_with_no_temporal_reference_is_unaffected_by_the_reference_rules(self):
        assert ps.check_readiness(
            ["clients"], self._resolution(resolved=["clients"]),
            any_prior_period_owed=False) is None

    def test_a_missing_TABLE_outranks_a_missing_reference_period(self):
        """Both are true at once for a brand-new dataset whose table did
        not arrive, and the table is the one a person can act on."""
        verdict = ps.check_readiness(
            ["clients"], self._resolution(absent=["clients"]),
            reference_period="2026-Q2", any_prior_period_owed=False)
        assert verdict.reason == ps.MISSING_TABLE


class TestAMixedPeriodDeliveryFansOut:
    """Criteria 1 and 2: one QA run per period, never a warehouse
    spanning more than one."""

    TABLES = {"cp-clients": "cp_clients", "cp-carers": "cp_carers",
               "cp-placements": "cp_placements",
               "birth-registrations": "birth_registrations"}

    def test_two_periods_produce_two_runs_each_reading_its_own(self):
        runs = ps.fan_out("run_07",
                           {"cp-clients": "2026-Q3", "cp-carers": "2026-Q2"},
                           self.TABLES)
        assert [r.period for r in runs] == ["2026-Q2", "2026-Q3"]
        assert [r.tables for r in runs] == [("cp_carers",), ("cp_clients",)]

    def test_an_ordinary_multi_table_delivery_in_ONE_period_is_ONE_run(self):
        """Thread H's TS-33b trap, one layer up: per-table slots mean an
        ordinary six-table delivery already spans six SLOTS in one
        period, so anything keyed on slots rather than periods splits
        every healthy delivery."""
        runs = ps.fan_out("run_07",
                           {"cp-clients": "2026-Q3", "cp-carers": "2026-Q3",
                            "cp-placements": "2026-Q3"},
                           self.TABLES)
        assert len(runs) == 1
        assert runs[0].tables == ("cp_carers", "cp_clients", "cp_placements")

    def test_a_dataset_with_no_period_is_in_no_run_at_all(self):
        """A held or unfiled supply. Folding it into the commonest
        period is the forward cascade wearing a different hat."""
        runs = ps.fan_out("run_07",
                           {"cp-clients": "2026-Q3", "cp-carers": None},
                           self.TABLES)
        assert len(runs) == 1
        assert runs[0].datasets == ("cp-clients",)

    def test_nothing_filed_produces_no_runs(self):
        assert ps.fan_out("run_07", {}, self.TABLES) == []

    def test_a_runs_identity_comes_from_its_PERIOD_not_its_position(self):
        """A positional number is what REQ-PIPE-057 criterion 18 forbids
        for a run's identity, and the same argument applies here: adding
        a dataset would otherwise renumber the other periods' runs."""
        one = ps.fan_out("run_07", {"cp-clients": "2026-Q3"}, self.TABLES)
        two = ps.fan_out("run_07",
                          {"cp-carers": "2026-Q1", "cp-clients": "2026-Q3"},
                          self.TABLES)
        by_period = {r.period: r.run_id for r in two}
        assert one[0].run_id == by_period["2026-Q3"]

    def test_every_fanned_out_run_id_is_a_usable_schema_name(self):
        for run in ps.fan_out("run_07",
                               {"cp-clients": "Nov-Jan window",
                                "cp-carers": "FY26/27"}, self.TABLES):
            assert supply_db.run_schema(run.run_id)


class TestLoadingCompletesBeforeQARuns:
    """Criterion 10, asserted structurally rather than by timing.

    Both orchestrators stage the WHOLE delivery set before the QA
    fan-out starts, which is what REQ-PIPE-060's own decision
    established - "the staging pass lifted OUT of the
    ProcessPoolExecutor fan-out and run once before it". A test that
    merely ran the pipeline would pass whatever the order was.
    """

    @pytest.mark.parametrize("module,function,builder", [
        ("qa_tools.bdm.orchestrate_bdm", "run_pipeline", "build_all"),
        ("qa_tools.cp.orchestrate_cp", "run_pipeline_cp", "build_all"),
    ])
    def test_the_staging_pass_precedes_the_fan_out(self, module, function, builder):
        import importlib

        mod = importlib.import_module(module)
        source = inspect.getsource(getattr(mod, function))
        tree = ast.parse(source.lstrip())

        def line_of(name):
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                        and node.func.attr == name:
                    return node.lineno
            return None

        staged_at = line_of(builder)
        fanned_at = line_of("run_manifest")
        assert staged_at is not None, f"{function} no longer stages before anything"
        assert fanned_at is not None, f"{function} no longer fans out"
        assert staged_at < fanned_at, (
            "the staging pass has moved after the QA fan-out - a check can now be "
            "evaluated against a table still mid-load")


class TestACheckIsEvaluatedOnce:
    """Criterion 11: against the state current at that moment, never
    recomputed for a historical arrival.

    The cost of this was accepted deliberately - a rebuild from
    committed history can REPLAY recorded results but cannot re-derive
    them - so the thing to hold is that the replay path does not try.
    """

    @pytest.mark.parametrize("path", [
        "qa_tools/bdm/build_results_from_history.py",
        "qa_tools/cp/build_results_from_history.py",
    ])
    def test_the_replay_path_re_runs_no_tool_and_opens_no_warehouse(self, path):
        source = Path(path).read_text()
        for forbidden in ("import duckdb", "supply_db.connect", "evaluate_dbt",
                           "evaluate_soda", "evaluate_datacontract", "evaluate_evidently"):
            assert forbidden not in source, (
                f"{path} would re-derive a historical verdict via {forbidden!r} "
                f"instead of replaying the one that was recorded")
