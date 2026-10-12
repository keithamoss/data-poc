"""What each QA tool is asked to evaluate on a run, the record of it, and
the refusal when a check in the run's scope goes missing (REQ-PIPE-188).

Written before the code. The comparison against real recorded history
that sized the guard is in the requirement's evidence: across every run
in a bootstrapped database whose tools ran, the scope rule and what the
run recorded agreed exactly, so the guard refuses nothing a run does
today.
"""
from __future__ import annotations

import pytest

from qa_tools.common import asked_for, check_id, qa_results_writer, qa_store, supply_db
from qa_tools.common import validate_check_lifecycle as vcl

CP = "child-protection"
BDM = "civil-registration"
P = "data-asset-1.child-protection-family-support.child-protection"
CLIENTS_UNIQUE = f"{P}.cp-clients.cp_client_id.unique_dbt"
CARERS_UNIQUE = f"{P}.cp-carers.carer_id.unique_dbt"


def _active(collection: str, tool: str) -> set[str]:
    out = set()
    for c in vcl.collect_checks(None):
        parsed = check_id.try_parse(c.check_id)
        if (parsed and parsed.collection == collection and parsed.tool == tool
                and not c.retired_as_of):
            out.add(c.check_id)
    return out


class TestWhatACollectionHolds:

    @pytest.mark.parametrize("collection", [CP, BDM])
    @pytest.mark.parametrize("tool", asked_for.TOOLS)
    def test_every_active_check_of_that_tool_and_collection(self, collection, tool):
        got = asked_for.collection_checks(collection, tool)
        assert got == sorted(_active(collection, tool))
        assert got, "a collection with no checks for a tool it runs"

    def test_a_retired_check_is_never_asked_for(self):
        retired = [c.check_id for c in vcl.collect_checks(None) if c.retired_as_of]
        assert retired, "precondition: the register holds a retired check"
        asked = {c for tool in asked_for.TOOLS for coll in (CP, BDM)
                 for c in asked_for.collection_checks(coll, tool)}
        assert asked.isdisjoint(retired)

    def test_file_checks_are_not_a_tool_run(self):
        assert "file" not in asked_for.TOOLS


class TestOneRule:
    """Criterion 1: the subset comes from scope_of_run, the results
    writer's own rule - never a second implementation."""

    def test_a_scoped_tool_is_asked_for_what_scope_of_run_keeps(self, monkeypatch):
        monkeypatch.setattr(asked_for, "SCOPED", frozenset({"dbt"}))
        monkeypatch.setattr(qa_results_writer, "scope_of_run",
                            lambda run_id: lambda c: c in {CLIENTS_UNIQUE})
        assert asked_for.for_run("cp_clients__x", CP, "dbt") == [CLIENTS_UNIQUE]

    def test_a_tool_not_yet_scoped_is_asked_for_the_whole_collection(self, monkeypatch):
        monkeypatch.setattr(asked_for, "SCOPED", frozenset())
        monkeypatch.setattr(qa_results_writer, "scope_of_run",
                            lambda run_id: lambda c: False)
        assert asked_for.for_run("cp_clients__x", CP, "evidently") == \
            asked_for.collection_checks(CP, "evidently")

    def test_evidently_is_never_scoped(self):
        """Out of scope by decision: about 0.2s a run."""
        assert "evidently" not in asked_for.SCOPED

    def test_a_run_naming_no_table_is_asked_for_everything(self, monkeypatch):
        """Criterion 4: a trial or a fixture's run."""
        monkeypatch.setattr(asked_for, "SCOPED", frozenset(asked_for.TOOLS))
        for tool in asked_for.TOOLS:
            assert asked_for.for_run("run_001", CP, tool) == \
                asked_for.collection_checks(CP, tool)


def _record(check: str) -> dict:
    return {"check_id": check, "dataset_id": check_id.parse(check).dataset}


class TestNothingInScopeGoesMissing:
    """Criterion 6."""

    def test_every_in_scope_check_accounted_for_passes(self):
        asked_for.check_nothing_missing(
            "r", CP, [_record(CLIENTS_UNIQUE)],
            in_scope=lambda c: c == CLIENTS_UNIQUE, tools=("dbt",))

    def test_a_not_evaluated_record_accounts_for_a_check(self):
        """The held and unrunnable pseudo-tools' records carry the real
        tool's check id, so they count exactly as a verdict does."""
        asked_for.check_nothing_missing(
            "r", CP, [{"check_id": CLIENTS_UNIQUE, "dataset_id": "cp-clients"}],
            in_scope=lambda c: c == CLIENTS_UNIQUE, tools=("dbt",))

    def test_a_missing_check_refuses_the_run_naming_it_and_its_tool(self):
        with pytest.raises(asked_for.MissingCheck) as caught:
            asked_for.check_nothing_missing(
                "cp_clients__k", CP, [_record(CLIENTS_UNIQUE)],
                in_scope=lambda c: c in {CLIENTS_UNIQUE, CARERS_UNIQUE}, tools=("dbt",))
        message = str(caught.value)
        assert "cp_clients__k" in message and CARERS_UNIQUE in message and "dbt" in message

    def test_a_check_outside_the_scope_may_be_absent(self):
        asked_for.check_nothing_missing("r", CP, [], in_scope=lambda c: False,
                                        tools=asked_for.TOOLS)

    def test_every_tool_is_compared_by_default(self):
        with pytest.raises(asked_for.MissingCheck, match="evidently"):
            asked_for.check_nothing_missing(
                "r", CP, [_record(c) for t in ("dbt", "soda", "datacontract")
                          for c in asked_for.collection_checks(CP, t)],
                in_scope=lambda c: True)


@pytest.fixture
def db(supply_dsn):
    with supply_db.connect(label="test-asked-for") as conn:
        qa_store.ensure_schema(conn)
        conn.execute(f'TRUNCATE "{qa_store.SCHEMA}".run CASCADE')
        yield conn


def _run(conn, run_key="cp_clients__a"):
    qa_store.record_run(conn, run_key=run_key, agency_id="a", collection_id=CP,
                        run_timestamp="2026-10-12T08:00:00+08:00", run_by="t@example.com",
                        environment="local")
    return run_key


class TestTheRecord:
    """Criteria 8 and 9."""

    def test_a_new_schema_version(self):
        assert qa_store.SCHEMA_VERSION == 38

    def test_one_row_per_run_tool_and_check(self, db):
        run_key = _run(db)
        qa_store.record_asked(db, run_key, "dbt", [CLIENTS_UNIQUE, CARERS_UNIQUE])
        qa_store.record_asked(db, run_key, "evidently", [])
        assert qa_store.asked_for_run(db, run_key) == {
            "dbt": [CARERS_UNIQUE, CLIENTS_UNIQUE]}

    def test_recording_again_replaces_that_tools_rows_only(self, db):
        run_key = _run(db)
        qa_store.record_asked(db, run_key, "dbt", [CLIENTS_UNIQUE, CARERS_UNIQUE])
        qa_store.record_asked(db, run_key, "soda", ["s"])
        qa_store.record_asked(db, run_key, "dbt", [CLIENTS_UNIQUE])
        assert qa_store.asked_for_run(db, run_key) == {"dbt": [CLIENTS_UNIQUE],
                                                       "soda": ["s"]}

    def test_removed_with_its_run(self, db):
        run_key = _run(db)
        qa_store.record_asked(db, run_key, "dbt", [CLIENTS_UNIQUE])
        db.execute(f'DELETE FROM "{qa_store.SCHEMA}".run WHERE run_key = ?', [run_key])
        (n,) = db.execute(f'SELECT count(*) FROM "{qa_store.SCHEMA}".asked_check').fetchone()
        assert n == 0

    def test_which_runs_were_asked_for_a_check_is_one_query(self, db):
        """The reason it is a table rather than an array on tool_output."""
        _run(db, "cp_clients__a")
        _run(db, "cp_carers__b")
        qa_store.record_asked(db, "cp_clients__a", "dbt", [CLIENTS_UNIQUE])
        qa_store.record_asked(db, "cp_carers__b", "dbt", [CARERS_UNIQUE])
        rows = db.execute(f'SELECT run_key FROM "{qa_store.SCHEMA}".asked_check '
                          "WHERE check_id = ?", [CARERS_UNIQUE]).fetchall()
        assert rows == [("cp_carers__b",)]

    def test_ask_records_what_it_returns(self, db, monkeypatch):
        """`ask` is what a tool runner calls: the list it is handed and the
        list on record are one list."""
        run_key = _run(db, "run_001")
        got = asked_for.ask(run_key, "2026-10-12T08:00:00+08:00", "a", CP, "soda")
        assert got == asked_for.collection_checks(CP, "soda")
        assert qa_store.asked_for_run(db, run_key)["soda"] == got


def _completed(run_id: str) -> bool:
    with supply_db.connect(read_only=True, label="test-asked-for") as conn:
        rows = conn.execute(f'SELECT completed_at FROM "{qa_store.SCHEMA}".run '
                            "WHERE run_key = ?", [run_id]).fetchall()
    return bool(rows) and rows[0][0] is not None


def _asked(run_id: str) -> dict[str, list[str]]:
    with supply_db.connect(read_only=True, label="test-asked-for") as conn:
        return qa_store.asked_for_run(conn, run_id)


def _bdm_run():
    import uuid

    from conftest import clone_run_views
    from fixture_ids import BDM_REF_RUN_ID

    mine = f"bdm_asked_{uuid.uuid4().hex[:8]}"
    with supply_db.connect(label="test-asked-for") as conn:
        clone_run_views(conn, BDM_REF_RUN_ID, mine)
    return mine, {"run_id": mine, "run_index": 1, "csv_path": "unused.csv",
                  "received_at": "2026-01-01T06:00:00+00:00", "delivery": "d"}


class TestThroughTheRealOrchestrator:
    """Criteria 6, 8 and 10 end to end: Birth Registrations through all
    four real tools, the same path Child Protection takes."""

    def test_every_tool_invoked_has_what_it_was_asked_for_on_record(self, bdm_duckdb_dir):
        from qa_tools.bdm import orchestrate_bdm

        run_id, entry = _bdm_run()
        orchestrate_bdm._run_one(entry, "2026-01-01T09:00:00Z", "t@example.com",
                                 reference_run_id=None)
        assert _completed(run_id)
        assert _asked(run_id) == {tool: asked_for.collection_checks(BDM, tool)
                                  for tool in asked_for.TOOLS}

    def test_a_check_gone_missing_refuses_the_run(self, bdm_duckdb_dir, monkeypatch):
        """A tool that comes back without one of its in-scope checks - the
        shape a wrong selection takes - refuses the run before it is
        finished, naming the check, and the batch stops (nothing catches
        it)."""
        from qa_tools.bdm import orchestrate_bdm, run_soda_bdm

        real = run_soda_bdm.evaluate_soda_bdm
        dropped = []

        def loses_one(run_id, run_timestamp):
            got = real(run_id, run_timestamp)
            dropped.append(got.pop()["check_id"])
            return got
        monkeypatch.setattr(run_soda_bdm, "evaluate_soda_bdm", loses_one)

        run_id, entry = _bdm_run()
        with pytest.raises(asked_for.MissingCheck) as caught:
            orchestrate_bdm._run_one(entry, "2026-01-01T09:00:00Z", "t@example.com",
                                     reference_run_id=None)
        assert dropped and dropped[0] in str(caught.value) and "soda" in str(caught.value)
        assert not _completed(run_id)

    def test_a_run_whose_tools_did_not_run_asks_nothing(self, bdm_duckdb_dir, monkeypatch):
        """Criterion 8 is WHEN a tool is invoked: a run that may not read
        its own table invokes none, and the guard does not demand verdicts
        nobody could produce."""
        import uuid

        from conftest import clone_run_views
        from fixture_ids import BDM_REF_RUN_ID
        from qa_tools.bdm import orchestrate_bdm

        mine = f"bdm_asked_held_{uuid.uuid4().hex[:8]}"
        with supply_db.connect(label="test-asked-for") as conn:
            clone_run_views(conn, BDM_REF_RUN_ID, mine, held={"birth_registrations"})
        entry = {"run_id": mine, "run_index": 1, "csv_path": "unused.csv",
                 "received_at": "2026-01-01T06:00:00+00:00", "delivery": "d"}
        orchestrate_bdm._run_one(entry, "2026-01-01T09:00:00Z", "t@example.com",
                                 reference_run_id=None)
        assert _completed(mine) and _asked(mine) == {}
