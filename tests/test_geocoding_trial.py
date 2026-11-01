"""REQ-GEN-298 criteria 10 to 15: the generation-time trial in its slot's period.

Three layers. THE OVERLAY'S TRIAL BRANCH (amendment A7; criterion 15's five
proofs), against this worker's own database with tables written directly, as
tests/test_period_overlay.py does: what is under test is what a trial's view
schema reads. THE TRIAL'S OWN RULE for its cross-table results
(target_agreement.trial_reads_agree, criterion 15). And TWO REAL-TOOL TRIALS
(criteria 10 and 11) through cli/target_trial.try_in_period, built from the
Linkage Products provider's own plan: one whose plan holds the source, one
whose plan promotes it.
"""
from __future__ import annotations

import json
import random
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from qa_tools.common import period_overlay, period_schema, qa_store, supply_db, trial

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

OWN, SOURCE = "geo_cp_clients", "cp_clients"
TABLES = [OWN, SOURCE]


def _key() -> str:
    return "".join(random.choice("0123456789") for _ in range(18))


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-geocoding-trial") as c:
        supply_db.ensure_schemas(c)
        qa_store.ensure_schema(c)
        yield c


@pytest.fixture
def world(conn):
    """A unique period whose REAL schema holds a promoted Client Register,
    and helpers to give a trial its own staged copies."""
    from qa_tools.common import period_tables

    period = f"2099-q{uuid.uuid4().hex[:6]}"
    made, trials = [], []
    real = f"{SOURCE}__{_key()}"
    conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{real}" (v int)')
    conn.execute(f'INSERT INTO "{supply_db.STAGING_SCHEMA}"."{real}" VALUES (99)')
    made.append(real)
    period_schema.ensure_period_schema(conn, period)
    period_tables.bring_in(conn, physical=real, source_schema=supply_db.STAGING_SCHEMA,
                           period=period)

    def staged_trial(own_value: int, source_value: int | None):
        run_id = trial.trial_run_id()
        trials.append(run_id)
        schema = supply_db.staging_schema_for(run_id)
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        key = _key()
        own = f"{OWN}__{key}"
        conn.execute(f'CREATE TABLE "{schema}"."{own}" (v int)')
        conn.execute(f'INSERT INTO "{schema}"."{own}" VALUES (?)', [own_value])
        source = None
        if source_value is not None:
            source = f"{SOURCE}__{_key()}"
            conn.execute(f'CREATE TABLE "{schema}"."{source}" (v int)')
            conn.execute(f'INSERT INTO "{schema}"."{source}" VALUES (?)', [source_value])
        return run_id, key, source

    def build(run_id, key, source, c=None):
        return period_overlay.build(c or conn, run_id, period=period, own_table=OWN,
                                    arrival_key=key, tables=TABLES, loaded=None,
                                    trial_supplied={SOURCE: source})

    def read(run_id, table, c=None):
        return (c or conn).execute(
            f'SELECT v FROM "{supply_db.run_schema(run_id)}"."{table}"').fetchone()[0]

    def reads_from(run_id) -> set[str]:
        return {r[0] for r in conn.execute(
            "SELECT DISTINCT table_schema FROM information_schema.view_table_usage "
            "WHERE view_schema = ?", [supply_db.run_schema(run_id)]).fetchall()}

    yield type("W", (), {"period": period, "staged_trial": staticmethod(staged_trial),
                         "build": staticmethod(build), "read": staticmethod(read),
                         "reads_from": staticmethod(reads_from)})
    for run_id in trials:
        trial.discard(conn, run_id)
    for physical in made:
        conn.execute(f'DROP TABLE IF EXISTS "{supply_db.STAGING_SCHEMA}"."{physical}" CASCADE')
    conn.execute(f'DROP SCHEMA IF EXISTS "{period_schema.period_schema(period)}" CASCADE')


class TestTheOverlaysTrialBranch:
    """Criterion 15 (1), (2), (4) and (5); amendment A7."""

    def test_1_a_trial_reads_only_its_own_copy_though_the_period_holds_one(self, world):
        run_id, key, source = world.staged_trial(own_value=1, source_value=5)
        out = world.build(run_id, key, source)
        assert world.read(run_id, SOURCE) == 5, "its own copy, never the period's 99"
        assert world.read(run_id, OWN) == 1
        assert world.reads_from(run_id) == {supply_db.staging_schema_for(run_id)}, \
            "its view schema names no relation outside its trial scope"
        assert out.resolution.absent == []

    def test_2_a_trial_whose_plan_holds_the_source_stages_nothing_and_reads_none(self, world):
        run_id, key, _source = world.staged_trial(own_value=1, source_value=None)
        out = world.build(run_id, key, None)
        assert SOURCE in out.resolution.absent, "absent, though the period holds one"
        assert world.reads_from(run_id) == {supply_db.staging_schema_for(run_id)}

    def test_4_two_trials_at_once_each_read_and_discard_their_own(self, world, conn):
        a = world.staged_trial(own_value=1, source_value=11)
        b = world.staged_trial(own_value=2, source_value=22)

        def build_and_read(args):
            run_id, key, source = args
            with supply_db.connect(label="test-geocoding-trial-parallel") as c:
                world.build(run_id, key, source, c)
                return world.read(run_id, SOURCE, c)
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert list(pool.map(build_and_read, [a, b])) == [11, 22]
        dropped = trial.discard(conn, a[0])
        assert supply_db.staging_schema_for(a[0]) in dropped
        assert not set(dropped) & set(trial.schemas_of(conn, b[0])), "b's schemas untouched"
        assert world.read(b[0], SOURCE) == 22, "b still reads its own copy"

    def test_5_a_run_that_is_not_a_trial_is_refused_trial_supplied_tables(self, conn, world):
        with pytest.raises(period_overlay.TrialSuppliedRefused,
                           match=r"'geo_cp_clients__1' is not a trial.*cp_clients"):
            period_overlay.build(conn, "geo_cp_clients__1", period=world.period,
                                 own_table=OWN, arrival_key="1", tables=TABLES, loaded=None,
                                 trial_supplied={SOURCE: "cp_clients__2"})

    def test_with_no_mapping_the_ordinary_branch_reads_the_period(self, world, conn):
        """The ordinary branch is untouched: a run with no trial mapping reads
        another collection's table from the period, as before."""
        key = _key()
        run_id = f"{OWN}__{key}"
        conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{run_id}" (v int)')
        try:
            out = period_overlay.build(conn, run_id, period=world.period, own_table=OWN,
                                       arrival_key=key, tables=TABLES, loaded=None)
            assert out.source[SOURCE] == period_schema.FROM_PERIOD
            assert world.read(run_id, SOURCE) == 99
        finally:
            conn.execute(f'DROP SCHEMA IF EXISTS "{supply_db.run_schema(run_id)}" CASCADE')
            conn.execute(f'DROP TABLE IF EXISTS "{supply_db.STAGING_SCHEMA}"."{run_id}"')


class TestTheDeclaredSetIsTheTrialsPeriods:
    """Criterion 10: the trial's year checks are evaluated, the set in force
    for its slot's period beside its views."""

    def test_rebuild_for_trial_writes_the_set_for_the_period(self, conn, world):
        from qa_tools.common import list_setting_members

        run_id, key, source = world.staged_trial(own_value=1, source_value=5)
        period_overlay.rebuild_for_trial(run_id, period="2023-Q2", own_table=OWN,
                                         arrival_key=key, tables=TABLES,
                                         trial_supplied={SOURCE: source})
        schema = supply_db.run_schema(run_id)
        assert list_setting_members.exists(conn, schema)
        found = list_setting_members.read(conn, schema, OWN, "census_years")
        assert found is not None and found.members == ("2011", "2016", "2021")


def _record(check_id, **kw):
    return {"check_id": check_id, "status": kw.pop("status", "pass"), **kw}


CHECK = "data-asset-1.department-of-health.linkage-products.geo-cp-clients.cp-clients.coverage_soda"
ORPHAN = ("data-asset-1.department-of-health.linkage-products.geo-cp-clients.cp-clients."
          "referential_soda")
READS = {CHECK: ["cp_clients"], ORPHAN: ["cp_clients", "geo_cp_clients"]}


class TestTheTrialsOwnRule:
    """Criterion 15: trial_reads_agree, beside compare over own_results."""

    def _agree(self, results, staged=(), unstaged=()):
        from qa_tools.common import target_agreement

        return target_agreement.trial_reads_agree("geo-cp-clients", results, staged=staged,
                                                  unstaged=unstaged, label="TS-x", reads=READS)

    def test_staged_and_evaluated_agrees(self):
        assert self._agree([_record(CHECK), _record(ORPHAN)], staged=["cp_clients"]) is None

    def test_3_staged_and_recorded_not_evaluated_is_a_disagreement(self):
        found = self._agree([_record(CHECK, status="nodata", unrunnable_reason="x",
                                     unrunnable_tables=["cp_clients"]), _record(ORPHAN)],
                            staged=["cp_clients"])
        assert found is not None
        text = str(found)
        assert "TS-x" in text and "cp-clients.coverage_soda" in text and "cp_clients" in text

    def test_nothing_staged_and_not_evaluated_naming_it_agrees(self):
        held = dict(status="nodata", unrunnable_reason="x", unrunnable_tables=["cp_clients"])
        assert self._agree([_record(CHECK, **held), _record(ORPHAN, **held)],
                           unstaged=["cp_clients"]) is None

    def test_nothing_staged_and_evaluated_is_a_disagreement(self):
        found = self._agree([_record(CHECK)], unstaged=["cp_clients"])
        assert found is not None and "was evaluated though the trial staged no cp_clients" in \
            str(found)

    def test_nothing_staged_and_not_evaluated_for_another_table_is_a_disagreement(self):
        found = self._agree([_record(CHECK, status="nodata", unrunnable_reason="x",
                                     unrunnable_tables=["ed_presentations"])],
                            unstaged=["cp_clients"])
        assert found is not None and "for want of ed_presentations" in str(found)

    def test_own_results_is_unchanged(self):
        """Criterion 15: own_results still drops a not-evaluated cross-table
        result - the comparison after replay relies on it."""
        from qa_tools.common import target_agreement

        held = _record(CHECK, status="nodata", unrunnable_reason="x",
                       unrunnable_table="cp_clients")
        assert target_agreement.own_results([held], reads=READS) == []


class TestEveryTargetCarriesItsDayFileAndPeriod:
    """Criteria 12 and 23's targets half."""

    def _book(self, tmp_path, entries, cp=()):
        path = tmp_path / "book.json"
        path.write_text(json.dumps({"geo-cp-clients": entries, "cp-clients": list(cp)}))
        return path

    def test_a_geocoding_supply_carries_its_day_file_period_and_source(self, tmp_path):
        from generator import targets

        cp = [{"run_id": "cp_run_001", "period": "2023-Q2", "delivery": "cpd",
               "received_at": "2023-02-01T01:00:00+00:00", "dirty_severity": None}]
        geo = [{"run_id": "lp_run_geocoding_001", "period": "2023-Q1", "delivery": "g1",
                "received_at": "2023-02-01T18:30:00+08:00",
                "planned": {"geo-cp-clients": "green"}},
               {"run_id": "lp_run_geocoding_002", "period": "2023-Q2", "delivery": "g2",
                "received_at": "2023-05-01T18:30:00+08:00",
                "planned": {"geo-cp-clients": "red"}, "tried": ["geo-cp-clients"],
                "sources": {"geo-cp-clients": {"dataset": "cp-clients", "table": "cp_clients",
                                               "received_at": "2023-02-01T01:00:00+00:00"}}}]
        placed = tmp_path / "placed.json"
        placed.write_text(json.dumps({"placements": [
            {"scenario_id": "TS-102", "dataset": "geo-cp-clients", "period": "2023-Q2"}]}))
        built = {b.delivery: b for b in targets.written(self._book(tmp_path, geo, cp), placed)
                 if b.dataset_id == "geo-cp-clients"}
        two = built["g2"]
        assert (two.day, two.filename, two.period) == ("2023-05-01", "geo_cp_clients.csv",
                                                       "2023-Q2")
        assert two.tried and not built["g1"].tried
        assert two.reference == "g1", "the dataset's last supply before it planned green"
        assert two.sources == (("cp_clients", "cp-clients", "cpd", "2023-02-01T01:00:00+00:00"),)
        assert two.label.startswith("TS-102's 2023-Q2")

    def test_a_held_source_is_staged_as_nothing(self, tmp_path):
        from generator import targets

        geo = [{"run_id": "g", "period": "2019-Q3", "delivery": "g3",
                "received_at": "2019-08-01T18:17:00+08:00",
                "planned": {"geo-cp-clients": "green"}, "tried": ["geo-cp-clients"],
                "sources": {"geo-cp-clients": {"dataset": "cp-clients", "table": "cp_clients",
                                               "received_at": None}}}]
        [b] = [b for b in targets.written(self._book(tmp_path, geo), tmp_path / "none.json")
               if b.dataset_id == "geo-cp-clients"]
        assert b.sources == (("cp_clients", "cp-clients", None, None),)

    def test_a_record_lacking_its_day_is_refused_by_name(self, tmp_path):
        from generator import targets

        geo = [{"run_id": "g", "period": "2019-Q3", "delivery": "g4",
                "planned": {"geo-cp-clients": "green"}}]
        with pytest.raises(ValueError, match="delivery g4.*gives no day"):
            targets.written(self._book(tmp_path, geo), tmp_path / "none.json")

    def test_a_two_csv_deliverys_reference_no_longer_raises(self, tmp_path):
        """Criterion 12, seen failing first: a geocoding delivery holds two
        CSVs, and the trial's reference was resolved with no file name, so it
        raised 'holds 2 CSV files, not one' (targets.py:180-182)."""
        from generator import targets

        folder = tmp_path / "geo-delivery"
        folder.mkdir()
        (folder / "geo_cp_clients.csv").write_text("id_1\n1\n")
        (folder / "geo_ed_presentations.csv").write_text("id_1\n2\n")
        got = targets.csv_of("geo-delivery", tmp_path, dataset_id="geo-cp-clients")
        assert got.name == "geo_cp_clients.csv"
        with pytest.raises(ValueError, match="holds 0 files for cp-clients"):
            targets.csv_of("geo-delivery", tmp_path, dataset_id="cp-clients")


# ---- the real tools, in a slot's period (criteria 10 and 11) ----------------

@pytest.fixture(scope="module")
def plan():
    from collection_modules import provider_module

    return provider_module("linkage-products").PROVIDER.plan()


def _spec_from_plan(plan, period, dataset_id, tmp_path, *, stage_source: bool):
    """A trial's spec built from the provider's own plan - the file as the
    driver writes it, and the source rows the warehouse holds then."""
    from collection_modules import provider_module
    from qa_tools.common import asset_time, hierarchy

    lp = provider_module("linkage-products")
    jobs = [j for j in plan.jobs if j.stream == lp.GEO_STREAM]
    k = next(i for i, j in enumerate(jobs) if j.period.name == period)
    table = hierarchy.dataset(dataset_id).table
    at, files = plan.state["geocoding"][jobs[k].slot_id]
    _d, rows, target = files[table]
    ref = next(plan.state["geocoding"][j.slot_id][1][table][1]
               for j in reversed(jobs[:k]) if plan.state["geocoding"][j.slot_id]
               and table in plan.state["geocoding"][j.slot_id][1]
               and plan.state["geocoding"][j.slot_id][1][table][2] == "green")
    (tmp_path / "own.csv").write_text(rows.to_csv(index=False))
    (tmp_path / "ref.csv").write_text(ref.to_csv(index=False))
    src = hierarchy.dataset(dataset_id).linked[0][0]
    held = lp.in_warehouse(src, period, at, plan.state["sources"][src])
    sources = [{"table": hierarchy.dataset(src).table, "dataset_id": src,
                "received_at": held.received_at if held is not None else None, "csv": None}]
    if stage_source:
        assert held is not None, f"the plan promotes {src} into {period}"
        (tmp_path / "src.csv").write_text(held.rows.to_csv(index=False))
        sources[0]["csv"] = str(tmp_path / "src.csv")
    else:
        assert held is None, f"the plan holds {src} in {period}"
    return {"label": f"a {period} trial", "dataset_id": dataset_id, "target": target,
            "rules": [], "period": period, "received_at": asset_time.isoformat(at),
            "table": table, "csv": str(tmp_path / "own.csv"),
            "reference_csv": str(tmp_path / "ref.csv"), "sources": sources}


class TestARealTrialInItsPeriod:
    """Criteria 10 and 11 through the real four tools - about thirty seconds
    each."""

    def test_2_a_held_source_is_not_staged_and_its_readers_are_not_evaluated(
            self, plan, tmp_path, supply_dsn, monkeypatch):
        """TS-100c's quarter: TS-100a's Client Register is held when the
        geocodes arrive, so the trial stages nothing for cp_clients and its
        two reading checks are recorded not evaluated, naming it; the year
        checks are evaluated in the period. The replay's half of (2) is the
        end-of-run bootstrap's."""
        from cli import target_trial

        from qa_tools.common import target_agreement

        captured = {}

        original = target_agreement.trial_reads_agree

        def spy(dataset_id, results, **kw):
            captured["results"] = results
            return original(dataset_id, results, **kw)
        monkeypatch.setattr(target_agreement, "trial_reads_agree", spy)
        spec = _spec_from_plan(plan, "2019-Q3", "geo-cp-clients", tmp_path, stage_source=False)
        assert target_trial.try_in_period("linkage-products", spec) == []
        mine = {r["check_id"].split(".", 4)[-1]: r for r in captured["results"]
                if ".geo-cp-clients." in r["check_id"]}
        for name in ("cp-clients.coverage_soda", "cp-clients.referential_soda"):
            assert mine[name].get("unrunnable_tables") == ["cp_clients"], mine[name]
        years = mine["census_year.missing_set_members_dbt"]
        assert years.get("not_evaluated_reason") is None and years["status"] == "pass", years

    def test_3_a_promoted_source_is_staged_and_both_reading_checks_evaluated(
            self, plan, tmp_path, supply_dsn, monkeypatch):
        """TS-102's quarter: the plan promotes the Client Register before the
        geocodes arrive, so the trial stages it and evaluates the orphan and
        coverage checks; the planted missing year reads red, as built."""
        from cli import target_trial
        from qa_tools.common import target_agreement

        captured = {}
        original = target_agreement.trial_reads_agree

        def spy(dataset_id, results, **kw):
            captured["results"] = results
            return original(dataset_id, results, **kw)
        monkeypatch.setattr(target_agreement, "trial_reads_agree", spy)
        spec = _spec_from_plan(plan, "2023-Q2", "geo-cp-clients", tmp_path, stage_source=True)
        assert spec["target"] == "red"
        assert target_trial.try_in_period("linkage-products", spec) == []
        mine = {r["check_id"].split(".", 4)[-1]: r for r in captured["results"]
                if ".geo-cp-clients." in r["check_id"]}
        for name in ("cp-clients.coverage_soda", "cp-clients.referential_soda"):
            assert not mine[name].get("unrunnable_reason"), mine[name]
            assert mine[name]["status"] == "pass", mine[name]
        assert mine["census_year.missing_set_members_dbt"]["status"] == "fail"
