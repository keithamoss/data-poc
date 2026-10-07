"""A replay of one collection can keep a checkpoint and resume from it
(REQ-TEST-159, signed by Keith 2026-10-06)."""
from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from qa_tools.common import bootstrap, checkpoints, replay_inputs, supply_db


@dataclass(frozen=True)
class _A:
    received_at: datetime
    delivery_name: str = ""


def _at(*minutes, deliveries=None):
    base = datetime(2023, 2, 1, tzinfo=timezone.utc)
    names = deliveries or [f"d{i}" for i in range(len(minutes))]
    return [_A(base + timedelta(minutes=m), n) for m, n in zip(minutes, names)]


class TestWhereACheckpointCanBe:

    def test_between_two_instants_it_stays(self):
        assert checkpoints.snapped(_at(0, 1, 2, 3), 3) == 3

    def test_inside_a_zip_it_moves_back_to_where_the_zip_begins(self):
        """A zip's files are filed together, so a checkpoint between them
        would hold half a filing - earlier is the safe direction."""
        assert checkpoints.snapped(_at(0, 5, 5, 5, 9), 4) == 2

    def test_inside_a_delivery_landing_over_minutes_it_moves_back_too(self):
        """A delivery's files can land minutes apart and are staged together
        (REQ-PIPE-035 criterion 10), so a checkpoint must not split one."""
        arr = _at(0, 5, 7, 9, 12, deliveries=["a", "b", "b", "b", "c"])
        assert checkpoints.snapped(arr, 4) == 2
        assert checkpoints.snapped(arr, 5) == 5

    @pytest.mark.parametrize("before", [0, 1, 6])
    def test_outside_the_collection_is_refused(self, before):
        with pytest.raises(checkpoints.CheckpointRefused, match="choose 2 to 5"):
            checkpoints.snapped(_at(0, 1, 2, 3, 4), before)

    def test_a_zip_from_the_first_arrival_has_no_point_inside_it(self):
        with pytest.raises(checkpoints.CheckpointRefused, match="no point"):
            checkpoints.snapped(_at(0, 0, 0, 0), 3)


class TestOnlyASyntheticAsset:
    """Criterion 6."""

    @pytest.fixture
    def real_asset(self, tmp_path, monkeypatch):
        from qa_tools.common import hierarchy

        doc = hierarchy.DATA_ASSET_YAML.read_text().replace("synthetic: true", "synthetic: false")
        assert "synthetic: false" in doc
        (tmp_path / "data-asset.yaml").write_text(doc)
        monkeypatch.setattr(hierarchy, "DATA_ASSET_YAML", tmp_path / "data-asset.yaml")

    def test_a_checkpoint_is_refused(self, real_asset):
        with pytest.raises(checkpoints.CheckpointRefused, match="synthetic"):
            checkpoints.save("child-protection", 2, recorded=replay_inputs.Recorded("x"),
                             pending_scripts=[])

    def test_a_bootstrap_asking_for_one_is_refused_before_anything_runs(self, real_asset):
        got = bootstrap.bootstrap(collection="cp", checkpoint_before=3)
        assert got.refused and "synthetic" in got.reason and not got.populated

    def test_a_resume_is_refused(self, real_asset):
        got = bootstrap.resume("mothman_ckpt_cp_002_x")
        assert got.refused and not got.replayed and "synthetic" in got.reason


class TestOneCollectionAtATime:

    def test_both_at_once_is_refused(self):
        got = bootstrap.bootstrap(collection="all", checkpoint_before=3)
        assert got.refused and "one collection" in got.reason


@pytest.fixture
def scratch_source(supply_dsn):
    """A small database of this test's own to take checkpoints of - never the
    worker's, which other tests are connected to."""
    admin = os.environ["MOTHMAN_TEST_DSN"]
    name = f"ckpt_src_{os.getpid()}"
    from conftest import mark_test_database

    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{name}"')
        mark_test_database(conn, name)
    info = psycopg.conninfo.conninfo_to_dict(admin)
    info["dbname"] = name
    dsn = psycopg.conninfo.make_conninfo(**info)
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("CREATE TABLE marker (x int)")
        conn.execute("INSERT INTO marker VALUES (42)")
    yield dsn
    for cp in checkpoints.listed(dsn):
        if cp.source == name:
            checkpoints.delete(cp.name, dsn)
    supply_db.release_connections()
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def _recorded():
    return replay_inputs.Recorded(
        collection_id="child-protection",
        arrivals=[replay_inputs.ArrivalPrint("cp_clients__1", "Extract A", "cp_clients.csv",
                                             "c" * 64, "r" * 64)],
        inputs={"contract/data-asset.yaml": "d" * 64})


class TestKeepingCheckpoints:
    """Criteria 1 and 7."""

    def test_a_checkpoint_is_a_copy_carrying_what_it_was_made_from(self, scratch_source):
        cp = checkpoints.save("child-protection", 5, recorded=_recorded(),
                              pending_scripts=[{"scenario": "TS-1"}], dsn=scratch_source)
        [found] = [c for c in checkpoints.listed(scratch_source) if c.name == cp.name]
        assert (found.collection_id, found.before, found.recorded, found.pending_scripts) == \
            ("child-protection", 5, _recorded(), [{"scenario": "TS-1"}])
        with psycopg.connect(checkpoints._with_dbname(scratch_source, cp.name)) as conn:
            assert conn.execute("SELECT x FROM marker").fetchone()[0] == 42

    def test_it_never_holds_the_source_open(self, scratch_source):
        """PostgreSQL refuses the copy while anything is connected: the
        process's own idle connections are let go first."""
        with supply_db.connect(dsn=scratch_source, label="held-idle"):
            pass
        checkpoints.save("child-protection", 2, recorded=_recorded(), pending_scripts=[],
                         dsn=scratch_source)

    def test_a_connection_still_open_is_named_in_the_refusal(self, scratch_source):
        with psycopg.connect(scratch_source, application_name="someone-else"):
            with pytest.raises(checkpoints.CheckpointRefused, match="someone-else"):
                checkpoints.save("child-protection", 2, recorded=_recorded(),
                                 pending_scripts=[], dsn=scratch_source)

    def test_no_more_than_the_configured_number_are_kept(self, scratch_source, monkeypatch):
        import time

        monkeypatch.setenv(checkpoints.KEEP_ENV, "2")
        names = []
        for before in (2, 3, 4):
            names.append(checkpoints.save("child-protection", before, recorded=_recorded(),
                                          pending_scripts=[], dsn=scratch_source).name)
            time.sleep(1.1)  # names and stamps are to the second
        source = psycopg.conninfo.conninfo_to_dict(scratch_source)["dbname"]
        left = [c.name for c in checkpoints.listed(scratch_source) if c.source == source]
        assert left == names[1:]

    def test_one_is_deleted_on_request(self, scratch_source):
        cp = checkpoints.save("child-protection", 2, recorded=_recorded(), pending_scripts=[],
                              dsn=scratch_source)
        checkpoints.delete(cp.name, scratch_source)
        assert cp.name not in [c.name for c in checkpoints.listed(scratch_source)]

    def test_nothing_but_a_checkpoint_or_a_resume_can_be_deleted(self, scratch_source):
        with pytest.raises(checkpoints.CheckpointRefused, match="nothing was deleted"):
            checkpoints.delete("supply", scratch_source)

    @pytest.mark.parametrize("raw", ["0", "two"])
    def test_a_nonsense_keep_is_refused(self, monkeypatch, raw):
        monkeypatch.setenv(checkpoints.KEEP_ENV, raw)
        with pytest.raises(checkpoints.CheckpointRefused, match=checkpoints.KEEP_ENV):
            checkpoints.keep()


class TestAResumeIsRefusedBeforeItCopiesAnything:
    """Criterion 3 and REQ-TEST-160 criteria 3 and 4."""

    @pytest.fixture
    def taken(self, scratch_source, monkeypatch):
        cp = checkpoints.save("child-protection", 5, recorded=_recorded(), pending_scripts=[],
                              dsn=scratch_source)
        monkeypatch.setenv(supply_db.SUPPLY_DSN_ENV, scratch_source)
        return cp

    def _resumes(self, dsn):
        return [c.name for c in checkpoints.listed(dsn, checkpoints.RESUME_PREFIX)]

    def test_a_change_before_the_checkpoint_is_refused_naming_the_arrival(
            self, taken, scratch_source, monkeypatch):
        monkeypatch.setattr(replay_inputs, "first_affected", lambda rec: replay_inputs.FirstAffected(
            3, "delivery 'Extract C' (cp_clients.csv) was changed - from arrival 3"))
        before = self._resumes(scratch_source)
        got = bootstrap.resume(taken.name)
        assert got.refused and got.first_affected == 3 and "arrival 3" in got.reason
        assert self._resumes(scratch_source) == before

    def test_an_input_change_restarts_the_collection_and_is_refused(
            self, taken, scratch_source, monkeypatch):
        monkeypatch.setattr(replay_inputs, "input_files",
                            lambda patterns=replay_inputs.INPUTS: {"contract/data-asset.yaml": "e"})
        got = bootstrap.resume(taken.name)
        assert got.refused and got.first_affected == 1 and "contract/data-asset.yaml" in got.reason

    def test_nothing_differs_replays_nothing(self, taken, scratch_source, monkeypatch):
        monkeypatch.setattr(replay_inputs, "first_affected", lambda rec: replay_inputs.FirstAffected(
            None, "nothing differs from the checkpoint - nothing to replay"))
        before = self._resumes(scratch_source)
        got = bootstrap.resume(taken.name)
        assert not got.replayed and not got.refused and "nothing" in got.reason.lower()
        assert self._resumes(scratch_source) == before


class TestARefusalChangesNothing:
    """post-build-review #133 B2, B3, B5 and B7: each refusal is a sentence,
    never a traceback, and comes before anything is generated, copied or
    dropped."""

    @pytest.fixture
    def no_generating(self, monkeypatch):
        from cli import bdm, cp

        def refuse():
            raise AssertionError("the synthetic data was regenerated before the refusal")
        monkeypatch.setattr(bdm, "generate_synthetic_data", refuse)
        monkeypatch.setattr(cp, "generate_synthetic_data", refuse)

    @pytest.mark.parametrize("before", [0, 1, 999])
    def test_an_impossible_arrival_is_refused_before_data_is_generated(
            self, scratch_source, monkeypatch, no_generating, before):
        monkeypatch.setenv(supply_db.SUPPLY_DSN_ENV, scratch_source)
        got = bootstrap.bootstrap(collection="cp", checkpoint_before=before)
        assert got.refused and "choose 2 to" in got.reason, got.reason

    def test_a_populated_database_is_refused_a_checkpoint_with_the_steps(
            self, scratch_source, monkeypatch, no_generating):
        monkeypatch.setenv(supply_db.SUPPLY_DSN_ENV, scratch_source)
        monkeypatch.setattr(bootstrap, "staged_table_count", lambda conn: 33)
        got = bootstrap.bootstrap(collection="cp", checkpoint_before=60)
        assert got.refused and "empty database" in got.reason and "env mark" in got.reason

    def test_an_unreadable_checkpoint_is_refused_not_crashed(self, scratch_source, monkeypatch):
        cp = checkpoints.save("child-protection", 5, recorded=_recorded(), pending_scripts=[],
                              dsn=scratch_source)
        with checkpoints._admin(scratch_source) as admin:
            admin.execute(f'COMMENT ON DATABASE "{cp.name}" IS \'not json\'')
        monkeypatch.setenv(supply_db.SUPPLY_DSN_ENV, scratch_source)
        before = [c.name for c in checkpoints.listed(scratch_source, checkpoints.RESUME_PREFIX)]
        try:
            got = bootstrap.resume(cp.name)
            assert got.refused and "cannot be read" in got.reason
            assert [c.name for c in checkpoints.listed(scratch_source,
                                                       checkpoints.RESUME_PREFIX)] == before
        finally:
            # ITS DESCRIPTION NO LONGER NAMES ITS SOURCE, so the fixture's
            # tidy-up cannot find it - this test removes its own.
            checkpoints.delete(cp.name, scratch_source)

    def test_deleting_a_name_that_does_not_exist_is_refused(self, scratch_source):
        with pytest.raises(checkpoints.CheckpointRefused, match="checkpoint list"):
            checkpoints.delete("mothman_ckpt_doesnotexist", scratch_source)

    def test_a_resume_database_is_listed(self, scratch_source):
        cp = checkpoints.save("child-protection", 5, recorded=_recorded(), pending_scripts=[],
                              dsn=scratch_source)
        dsn = checkpoints.copy_for_resume(cp, scratch_source)
        name = psycopg.conninfo.conninfo_to_dict(dsn)["dbname"]
        try:
            assert name in [r.name for r in checkpoints.resumes(scratch_source)]
        finally:
            checkpoints.delete(name, scratch_source)

    def test_only_a_declared_true_counts_as_synthetic(self, tmp_path, monkeypatch):
        """#131 D9: a string "false" is truthy."""
        from qa_tools.common import hierarchy

        doc = hierarchy.DATA_ASSET_YAML.read_text().replace("synthetic: true", 'synthetic: "false"')
        (tmp_path / "data-asset.yaml").write_text(doc)
        monkeypatch.setattr(hierarchy, "DATA_ASSET_YAML", tmp_path / "data-asset.yaml")
        with pytest.raises(checkpoints.CheckpointRefused, match="synthetic"):
            checkpoints.require_synthetic()


# --------------------------------------------------------------------------
# Criterion 5, on the reduced corpus REQ-TEST-116 criterion 4 uses.
# --------------------------------------------------------------------------

from test_bootstrap_equivalence import corpus  # noqa: E402,F401 - the shared fixture

import equiv_support  # noqa: E402


@pytest.mark.on_demand
class TestAResumeRecordsWhatAFullReplayDoes:

    @pytest.mark.parametrize("short,before", [("bdm", 3), ("cp", 7)])
    def test_identical(self, corpus, worker_id, short, before):  # noqa: F811
        collection_id = checkpoints.COLLECTIONS[short]
        taken = []

        def full():
            bootstrap._run_collection(
                short, True, record_deliveries=True,
                after_each=checkpoints.taking_checkpoint(
                    collection_id, before, contextlib.nullcontext, on_taken=taken.append))

        tag = f"{short}_{worker_id}"
        full_snap = equiv_support.run_into_fresh_database(corpus, f"ckpt_full_{tag}", full)
        [cp] = taken
        try:
            dsn = checkpoints.copy_for_resume(cp, os.environ["MOTHMAN_TEST_DSN"])
            from qa_tools.common import scripted_decisions

            def resumed():
                player = scripted_decisions.Player(
                    collection_id,
                    scripts=[scripted_decisions.Script(**s) for s in cp.pending_scripts])
                bootstrap._run_collection(short, True, record_deliveries=True,
                                          start_at=cp.before, player=player)

            resumed_snap = equiv_support.run_into_database(corpus, dsn, resumed)
        finally:
            checkpoints.delete(cp.name, os.environ["MOTHMAN_TEST_DSN"])
            for name in [c.name for c in checkpoints.listed(os.environ["MOTHMAN_TEST_DSN"],
                                                            checkpoints.RESUME_PREFIX)
                         if c.name.startswith(f"{checkpoints.RESUME_PREFIX}{short}_{before:03d}")]:
                checkpoints.delete(name, os.environ["MOTHMAN_TEST_DSN"])
        assert sum(equiv_support.summary(full_snap).values()) > 0
        diffs = equiv_support.differences(full_snap, resumed_snap)
        assert not diffs, "a resume differs from the full replay:\n" + "\n".join(diffs)
