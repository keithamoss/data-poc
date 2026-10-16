"""Real Soda Core integration test for qa_tools/cp/run_soda_cp.py's
evaluate_soda_cp() - the CP counterpart to tests/test_run_soda_bdm.py."""
from __future__ import annotations

import qa_tools.tools.run_soda as run_soda
from qa_tools import collections

from fixture_ids import CP_DIRTY_RUN_ID as _DIRTY_RUN_ID, CP_REF_RUN_ID as _REF_RUN_ID


def _run(monkeypatch, cp_duckdb_dir, run_id, run_timestamp):
    # THE WHOLE COLLECTION, said outright: these are about the tool's own checks,
    # and a fixture run is scoped to one table since REQ-PIPE-188 to 191.
    from qa_tools.common import asked_for
    monkeypatch.setattr(asked_for, "SCOPED", frozenset())
    # The environment already points at this worker's database
    # (conftest's supply_dsn); cp_duckdb_dir is what staged the data into it.
    monkeypatch.setattr(run_soda, "write_qa_result", lambda *a, **k: None)
    return run_soda.evaluate("child-protection", run_id, run_timestamp)


def test_clean_run_resolves_every_check_id_across_all_6_tables(monkeypatch, cp_duckdb_dir):
    results = _run(monkeypatch, cp_duckdb_dir, _REF_RUN_ID, "2026-01-01T09:00:00Z")

    assert results, "the real Soda scan produced no CP check results at all"
    assert all(r["check_id"] for r in results), "every result must resolve a real check_id (evaluate_soda_cp raises if not)"
    tables_seen = {r["dataset_id"] for r in results}
    assert len(tables_seen) > 1, "results should span more than one of the 6 real CP tables"
    failing = [r for r in results if r["status"] == "fail"]
    assert not failing, f"clean reference run had real Soda failures: {failing}"


def test_dirty_run_produces_a_real_failure(monkeypatch, cp_duckdb_dir):
    results = _run(monkeypatch, cp_duckdb_dir, _DIRTY_RUN_ID, "2026-04-01T09:00:00Z")

    assert results
    assert all(r["check_id"] for r in results)
    failing = [r for r in results if r["status"] == "fail"]
    assert failing, "a real red-severity dirty CP run produced no Soda failures at all"


class TestAnUnreadableTableDoesNotTakeTheScanDown:
    """The Soda counterpart of test_run_dbt_cp.py's identically named
    class, and the same latent defect one tool over - found 2026-10-02
    when REQ-PIPE-105 made an absent table ORDINARY rather than
    hypothetical.

    One file is one arrival, so a run reads its siblings from its
    period, and a sibling filed to a DIFFERENT period - Case Workers,
    delivered only in February and August - is legitimately absent. The
    scan counted every table's rows up front and handed Soda checks for
    all six, so one absent table raised UndefinedTable and the run lost
    its QA for all five readable ones.
    """

    def test_the_other_tables_are_still_checked(self, monkeypatch, cp_duckdb_dir):
        import uuid

        from conftest import clone_run_views
        from qa_tools.common import supply_db

        mine = f"cp_held_{uuid.uuid4().hex[:8]}"
        with supply_db.connect(label="test-held-soda") as conn:
            clone_run_views(conn, _REF_RUN_ID, mine, held={"cp_clients"})
        try:
            results = _run(monkeypatch, cp_duckdb_dir, mine, "2026-01-01T09:00:00Z")
            seen = {r["dataset_id"] for r in results}
            assert len(seen) > 1, f"expected several tables still checked, got {seen}"
            assert "cp-clients" not in seen, \
                "nothing may be recorded against the table that could not be read"
            assert not [r for r in results if r["status"] == "error"], \
                "a check reading the absent table must be left out, not errored"
        finally:
            with supply_db.connect(label="test-held-soda") as conn:
                conn.execute(
                    f'DROP SCHEMA IF EXISTS "{supply_db.run_schema(mine)}" CASCADE')


class TestAPartitionedCheckIsNotDropped:
    """post-build-review #131 D6: `checks for t [recent]` is Soda's partition
    syntax (BDM uses it today). Its table is `t`; read raw it was
    "t [recent]", which the CP runner's table filter then dropped - a check
    that could not run vanishing, the false green 15edf01 exists to stop."""

    def test_its_table_is_the_bare_name(self):
        from types import SimpleNamespace

        from qa_tools.common import soda_common

        yaml_text = ("checks for cp_clients [recent]:\n"
                     "  - missing_count(given_name) = 0:\n"
                     "      attributes:\n"
                     "        check_id: x.cp-clients.given_name.missing_count_soda\n")
        [missing] = soda_common.unreported_checks(
            yaml_text, {"checks": []}, SimpleNamespace(get_error_logs=lambda: []))
        assert missing["table"] == "cp_clients"
        assert missing["column"] == "given_name"


class TestSamplesAreNotLostToANameAnotherTableShares:
    """A failing check's sample keys come from its OWN table's sample.

    Soda's samples were captured by check NAME alone, and Child Protection
    has seven names on more than one table - `missing_count(cp_client_id)`
    on four. In one scan the last table sampled overwrote the others, and a
    check whose sample had been overwritten looked its key column up in
    another table's rows, found none, and recorded no samples at all.
    Found 2026-10-12 scoping Soda (REQ-PIPE-191), where a narrower scan
    stopped colliding and the samples reappeared.
    """

    def test_notifications_missing_client_id_records_its_own_samples(self, monkeypatch,
                                                                       cp_duckdb_dir):
        results = _run(monkeypatch, cp_duckdb_dir, _DIRTY_RUN_ID, "2026-04-01T09:00:00Z")
        check = ("data-asset-1.child-protection-family-support.child-protection."
                 "cp-notifications.cp_client_id.missing_count_soda")
        (record,) = [r for r in results if r["check_id"] == check]
        assert record["status"] != "pass", "the dirty fixture should fail this check"
        assert record["failing_sample_keys"], "its samples were lost to a shared name"
        assert all(k.startswith("NOTIF-") for k in record["failing_sample_keys"])

    def test_every_sampled_failure_names_rows_of_its_own_table(self, monkeypatch,
                                                                cp_duckdb_dir):
        from qa_tools.common import hierarchy, supply_db

        results = _run(monkeypatch, cp_duckdb_dir, _DIRTY_RUN_ID, "2026-04-01T09:00:00Z")
        sampled = [r for r in results if r["failing_sample_keys"]]
        assert sampled
        with supply_db.connect(read_only=True, label="test-soda-samples") as conn:
            schema = supply_db.run_schema(_DIRTY_RUN_ID)
            for r in sampled:
                table = hierarchy.dataset(r["dataset_id"]).table
                pk = collections.adapter("child-protection").sample_key[table]
                keys = {str(row[0]) for row in conn.execute(
                    f'SELECT {pk} FROM "{schema}".{table}').fetchall()}
                assert set(r["failing_sample_keys"]) <= keys, \
                    (r["check_id"], r["failing_sample_keys"])
