"""REQ-TEST-339: thirty linked datasets, one linkage product, end to end.

A COPY of the tracked working tree gains five fake quarterly collections
holding thirty linked datasets between them - one identified by two columns,
one by three - and a fake linkage product reading all thirty, its referential
and coverage checks generated from its `linked_datasets`
(tests/thirty_linked_datasets.py). One period is then taken from generation
to recorded results through the function `mothman pipeline run` calls for
collections sharing a calendar (tests/thirty_linked_run.py), against a
scratch database of its own: the thirty arrive, are staged, filed and
promoted, the product arrives and is checked, and one linked supply is sent
again and promoted over the first by a scripted person.

ON DEMAND (the requirement's TEST COST NFR offers the fast half or a
deliberate mark): it generates and replays a stream, so it runs in CI's
on-demand job beside REQ-TEST-249's copy, never in the fast half, and needs
no deployment bootstrap. The repository's own contract/, data/ and reports/
are never touched.
"""

# READS ONLY ITS OWN REPORTS: every reports/ file here is one this module
# wrote under its own copied tree, never the real one (tests/test_publish.py's
# guard).

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import psycopg
import pytest

import thirty_linked_datasets as fx
import tree_copy
from conftest import mark_test_database

pytestmark = pytest.mark.on_demand

ROOT = tree_copy.ROOT
ADMIN_DSN_ENV = "MOTHMAN_TEST_DSN"
SCRATCH_DB = "thirty_linked_datasets"
RUNNER = Path(__file__).resolve().parent / "thirty_linked_run.py"


def _snapshot(path: Path) -> dict:
    if not path.exists():
        return {}
    return {str(p.relative_to(path)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in path.rglob("*") if p.is_file()}


def _fresh_database() -> str:
    admin = os.environ[ADMIN_DSN_ENV]
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{SCRATCH_DB}"')
        mark_test_database(conn, SCRATCH_DB)
    info = psycopg.conninfo.conninfo_to_dict(admin)
    info["dbname"] = SCRATCH_DB
    return psycopg.conninfo.make_conninfo(**info)


class Copy:
    pass


@pytest.fixture(scope="module")
def copy(tmp_path_factory):
    """The whole journey, once: copy, add, generate and replay one period.
    Each test asserts one part of what was recorded."""
    c = Copy()
    c.before = {name: _snapshot(ROOT / name) for name in ("data", "reports")}
    c.tree = fx.build(tmp_path_factory.mktemp("thirty_linked") / "tree")
    c.changed_before_run = fx.changed_product_files(c.tree)
    out = tmp_path_factory.mktemp("evidence") / "evidence.json"
    env = {**os.environ, "MOTHMAN_SUPPLY_DSN": _fresh_database(), "MOTHMAN_ENVIRONMENT": "test",
           "NO_COLOR": "1", "COLUMNS": "200"}
    start = time.perf_counter()
    done = subprocess.run([sys.executable, str(RUNNER), str(out)], cwd=c.tree, env=env,
                          capture_output=True, text=True, timeout=1800)
    c.wall_seconds = round(time.perf_counter() - start, 1)
    assert done.returncode == 0, f"the replay failed:\n{done.stdout[-6000:]}\n{done.stderr[-6000:]}"
    c.log = done.stdout
    c.evidence = json.loads(out.read_text())
    doc = json.loads((c.tree / "reports" / "results_lkunit_lk-linkage.json").read_text())
    c.results = doc["results"]
    c.changed_after_run = fx.changed_product_files(c.tree)
    runs = [r for r in c.evidence["recorded_runs"] if r["collection"] == fx.PRODUCT["collection"]]
    c.linkage_run = next(r["run_key"] for r in runs if r["scope"] == "arrival")
    c.readers_runs = [r["run_key"] for r in runs if r["scope"] == "readers"]
    yield c
    with psycopg.connect(os.environ[ADMIN_DSN_ENV], autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)')


def _cross(results, run_key, kind=None):
    return [r for r in results if r["run_id"] == run_key and r.get("tables_read")
            and (kind is None or r["check_id"].endswith(f".{kind}_soda"))]


def _check_id(dataset_id: str, kind: str) -> str:
    return fx.check_id(f"{dataset_id}.{kind}_soda")


class TestThirtyLinkedDatasetsGoFromGenerationToRecordedResults:
    """Criterion 1."""

    def test_the_fixture_holds_thirty_across_several_collections(self):
        linked = fx.linked()
        assert len(linked) == 30
        assert len({d["id"] for d in linked}) == 30
        assert len(fx.sources()) >= 2
        widths = sorted(len(d["id_columns"]) for d in linked)
        assert 2 in widths and 3 in widths

    def test_every_linked_dataset_arrived_and_was_promoted_into_the_period(self, copy):
        held = copy.evidence["held_at_linkage"]
        assert sorted(held) == sorted(d["id"] for d in fx.linked())
        assert all(held.values()), {d: s for d, s in held.items() if not s}

    def test_the_product_was_checked_once_on_arrival(self, copy):
        assert copy.linkage_run.startswith(f"{fx.PRODUCT['table']}__")
        own = [r for r in copy.results if r["run_id"] == copy.linkage_run]
        assert own, "the linkage run recorded no results"

    def test_every_linked_dataset_has_its_referential_and_coverage_result(self, copy):
        got = {r["check_id"] for r in copy.results if r["run_id"] == copy.linkage_run}
        for d in fx.linked():
            for kind in ("referential", "coverage"):
                assert _check_id(d["id"], kind) in got, (d["id"], kind)
        assert len(_cross(copy.results, copy.linkage_run)) == 60


class TestTheLinkageRunReadsAllThirtyFromTheWarehouse:
    """Criterion 2, first half: the view schema resolves all thirty from the
    period's warehouse, and every cross-table result names its one table."""

    def test_its_view_schema_resolved_all_thirty_from_the_period(self, copy):
        read = {x["logical"]: x for x in copy.evidence["tables_read"][copy.linkage_run]}
        held = copy.evidence["held_at_linkage"]
        assert read[fx.PRODUCT["table"]]["source"] == "staging"
        linked = [d for d in fx.linked()]
        assert linked
        for d in linked:
            x = read.get(d["table"])
            assert x is not None, f"{d['table']} was not in the run's view schema"
            assert x["source"] == "period", x
            assert x["supply"] == held[d["id"]], (x, held[d["id"]])
        assert set(read) == {fx.PRODUCT["table"], *(d["table"] for d in linked)}

    def test_each_referential_and_coverage_result_names_its_one_table(self, copy):
        cross = _cross(copy.results, copy.linkage_run)
        assert len(cross) == 60
        by_id = {r["check_id"]: r for r in cross}
        for d in fx.linked():
            for kind in ("referential", "coverage"):
                r = by_id[_check_id(d["id"], kind)]
                assert list(r["tables_read"]) == [d["table"]], r["tables_read"]
                assert set(r["reads"]) == {fx.PRODUCT["table"], d["table"]}, r["reads"]
                assert r["reads"][d["table"]]["state"] == "READ"
                assert r["reads"][d["table"]]["supply_id"] == copy.evidence["held_at_linkage"][d["id"]]

    def test_every_linkage_check_passes_on_correctly_linked_rows(self, copy):
        cross = _cross(copy.results, copy.linkage_run)
        assert cross
        assert {r["check_id"]: r["status"] for r in cross if r["status"] != "pass"} == {}
        coverage = [r for r in cross if r["check_id"].endswith(".coverage_soda")]
        assert len(coverage) == 30 and all(r["metric_value"] == 100.0 for r in coverage)


class TestTheIdentifierShapeChecksPassOnCorrectlyShapedRows:
    """Criterion 2: the expected-ids and nothing-after-id_k checks pass on
    rows of every dataset - one, two and three identifiers - and the rows are
    genuinely of all three shapes, so a pass is not one shape checked thirty
    times."""

    def _release(self, copy) -> list[dict]:
        found = sorted((copy.tree / "data" / "deliveries").glob(f"*/{fx.PRODUCT['table']}.csv"))
        assert len(found) == 1, found
        with found[0].open() as f:
            return list(csv.DictReader(f))

    def test_the_release_carries_rows_of_each_shape(self, copy):
        rows = self._release(copy)
        by_code = {}
        for row in rows:
            by_code.setdefault(row["dataset"], []).append(row)
        assert sorted(by_code) == sorted(d["code"] for d in fx.linked())
        for d in fx.linked():
            k = len(d["id_columns"])
            for row in by_code[d["code"]]:
                filled = [j for j in range(1, fx.N_ID + 1) if row[f"id_{j}"].strip()]
                assert filled == list(range(1, k + 1)), (d["id"], row)

    @pytest.mark.parametrize("tail", ["id_1.expected_ids_soda", "id_1.no_surplus_ids_soda"])
    def test_it_passes(self, copy, tail):
        [r] = [r for r in copy.results if r["run_id"] == copy.linkage_run
               and r["check_id"] == fx.check_id(tail)]
        assert r["status"] == "pass" and r["row_count_invalid"] == 0, r
        assert r["row_count_total"] == len(self._release(copy)) > 0


class TestAMoveInOneCollectionReRunsOnlyItsTwoChecks:
    """Criterion 2, last half: a supply moved in one fake collection re-runs
    only the two linkage checks reading it."""

    def test_one_re_evaluation_followed_the_move(self, copy):
        caused = [r for r in copy.evidence["recorded_runs"] if r["caused_by_decision"]]
        assert [r["run_key"] for r in caused] == copy.readers_runs
        [run] = caused
        assert run["collection"] == fx.PRODUCT["collection"]
        assert run["reads_table"] == fx.MOVED.replace("-", "_")

    def test_it_asked_for_exactly_the_two_checks_reading_the_moved_table(self, copy):
        [run] = copy.readers_runs
        assert copy.evidence["asked"][run] == {
            "soda": sorted([_check_id(fx.MOVED, "coverage"), _check_id(fx.MOVED, "referential")]),
            "dbt": [], "datacontract": []}

    def test_it_recorded_exactly_those_two_and_they_read_the_new_supply(self, copy):
        [run] = copy.readers_runs
        got = [r for r in copy.results if r["run_id"] == run]
        assert sorted(r["check_id"] for r in got) == sorted(
            [_check_id(fx.MOVED, "coverage"), _check_id(fx.MOVED, "referential")])
        now = copy.evidence["held_now"][fx.MOVED]
        assert now != copy.evidence["held_at_linkage"][fx.MOVED], "nothing moved"
        table = fx.MOVED.replace("-", "_")
        for r in got:
            assert r["status"] == "pass"
            assert r["reads"][table]["supply_id"] == now

    def test_nothing_else_was_re_run(self, copy):
        recorded = copy.evidence["recorded_runs"]
        moved = [i for i, r in enumerate(recorded) if r["scope"] == "arrival"
                 and r["run_key"].startswith(fx.MOVED.replace("-", "_") + "__")]
        assert len(moved) == 2, "the moved dataset should have two arrivals"
        after = [r["run_key"] for r in recorded[moved[-1] + 1:]]
        assert after == copy.readers_runs


class TestNoProductFileChanged:
    """Criterion 3: only configuration, check files, adapters and providers
    were added or changed - before the run and after it."""

    def test_before_the_run(self, copy):
        assert copy.changed_before_run == []

    def test_after_the_run_only_the_generated_scenario_map_differs(self, copy):
        """The replay itself writes nothing into product code. The one tracked
        file it rewrites is SCENARIOS.md, which every generation rebuilds from
        the recorded placements (cli/pipeline.generate_collection) - and this
        copy places none of the real scenarios. That is the run's output, not
        a file the fixture had to change."""
        assert copy.changed_after_run == ["SCENARIOS.md changed (M)"]

    def test_the_check_would_catch_an_edit_to_product_code(self, tmp_path):
        tree = fx.build(tmp_path / "tree")
        (tree / "qa_tools" / "common" / "run_reads.py").write_text("# edited\n")
        (tree / "qa_tools" / "tools" / "stray.py").write_text("")
        hierarchy = tree / "contract" / "data-asset.yaml"
        hierarchy.write_text(hierarchy.read_text().replace("short: cp ", "short: cpx", 1))
        said = fx.changed_product_files(tree)
        assert any("qa_tools/common/run_reads.py" in p for p in said), said
        assert any("qa_tools/tools/stray.py" in p for p in said), said
        assert any("data-asset.yaml" in p and "replaced" in p for p in said), said

    @pytest.mark.parametrize("name", ["data", "reports"])
    def test_nothing_is_written_under_the_real_tree(self, copy, name):
        assert _snapshot(ROOT / name) == copy.before[name]

    def test_the_real_hierarchy_never_names_them(self, copy):
        assert fx.PRODUCT["collection"] not in (ROOT / "contract" / "data-asset.yaml").read_text()
        assert copy.tree != ROOT


def test_how_long_the_linkage_run_took(copy):
    """Criterion 4: the linkage run's own duration at thirty linked datasets,
    for the requirement's evidence - the QA run of the product's arrival, and
    the knock-on's re-run of two checks."""
    runs = {r["run_id"]: r["seconds"] for r in copy.evidence["runs"]}
    linkage = runs[copy.linkage_run]
    [readers] = copy.readers_runs
    print(f"\nREQ-TEST-339: linkage run {linkage}s at {len(fx.linked())} linked datasets; "
          f"knock-on re-run {runs[readers]}s; {len(runs)} QA runs in a {copy.evidence['stream_seconds']}s "
          f"stream; {copy.wall_seconds}s end to end including generation")
    assert linkage > 0
