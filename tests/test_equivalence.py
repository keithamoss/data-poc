"""The before-and-after equivalence harness (REQ-TEST-239, the lean
version Keith signed 2026-10-16).

Everything here drives the real command or the real module. The one thing
this file does not do is a full capture - that is a from-empty bootstrap,
about half an hour - so the self-check (criterion 5) is the on-demand test
at the bottom."""
from __future__ import annotations

import json
import os
import re
import subprocess

import pytest
from click.testing import CliRunner

from cli.app import cli
from qa_tools.common import equivalence as eq

#: A real commit from before `mothman env mark` existed (cli/env.py arrived
#: in 0d071d6), so its "mark" stage fails for real.
BEFORE_ENV_MARK = "58791fc"

_runner = CliRunner()
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _words(result) -> str:
    """The output as plain words: CI's terminal adds colour codes and the
    error panel wraps, neither of which is what a test is about."""
    return " ".join(_ANSI.sub("", result.output).replace("│", " ").split())


def _baseline(label, *, commit="HEAD", harness=eq.HARNESS_VERSION, s1=None, s4=None,
              s5=None, s7=None, seconds=100.0, pinned_now=eq.PINNED_NOW):
    commit = subprocess.run(["git", "rev-parse", commit], capture_output=True, text=True,
                            check=True, cwd=eq.ROOT).stdout.strip()
    return {"harness": harness, "normaliser": eq.NORMALISER_VERSION, "label": label,
            "commit": commit, "bootstrap_seconds": seconds, "timings": {},
            "pinned_now": pinned_now,
            "surfaces": {"S1": s1 or {"qa.run": {"columns": ["run_key"],
                                                 "rows": [[["\"r1\""], 1]]}},
                         "S4": s4 or {"data/deliveries/x.csv": "aa"},
                         "S5": s5 or {"results.json": {"a": 1}},
                         "S7": s7 or {"help: mothman": "Usage: mothman"}}}


@pytest.fixture
def harness_free():
    """The capture tests share the harness's one worktree path, so they
    need no real capture to be running. FAILS rather than skips when one
    is (post-build-review #213): a skip here would be a green that proved
    nothing, and the leftover test's tidy-up would otherwise reach a live
    capture's tree."""
    try:
        eq._one_capture_at_a_time().close()
    except eq.Refused:
        pytest.fail("an equivalence capture is running - these tests use its worktree "
                    "path, so run them once it has finished")


@pytest.fixture
def baselines(tmp_path, monkeypatch):
    monkeypatch.setenv("MOTHMAN_EQUIV_DIR", str(tmp_path))

    def write(label, **kw):
        (tmp_path / f"{label}.json").write_text(json.dumps(_baseline(label, **kw)))
    return write


class TestCompare:
    """Criteria 2 and 3."""

    def test_reports_renamed_by_req_pipe_248_compare_under_their_new_names(self, baselines):
        """REQ-PIPE-248 criterion 8: its S5 comparison maps each old report
        name to its new one, and the mapping is available to that requirement
        only - any other name is refused."""
        baselines("a", s5={"results_bdm.json": {"a": 1}, "results_cp.json": {"b": 2}})
        baselines("b", s5={"results_rs_civil-registration.json": {"a": 1},
                           "results_cpfs_child-protection.json": {"b": 2}})
        plain = _runner.invoke(cli, ["debug", "equivalence", "compare", "a", "b",
                                     "--surfaces", "S5"])
        assert plain.exit_code == 1
        mapped = _runner.invoke(cli, ["debug", "equivalence", "compare", "a", "b",
                                      "--surfaces", "S5", "--renamed-by", "REQ-PIPE-248"])
        assert mapped.exit_code == 0, mapped.output
        other = _runner.invoke(cli, ["debug", "equivalence", "compare", "a", "b",
                                     "--renamed-by", "REQ-PIPE-249"])
        assert other.exit_code != 0 and "REQ-PIPE-248" in _words(other)

    def test_equal_baselines_compare_equal_and_exit_zero(self, baselines):
        baselines("a")
        baselines("b")
        result = _runner.invoke(cli, ["debug", "equivalence", "compare", "a", "b"])
        assert result.exit_code == 0, result.output
        assert _words(result).count("same") == 4

    def test_a_difference_is_named_by_surface_and_exits_non_zero(self, baselines):
        baselines("a")
        baselines("b", s4={"data/deliveries/x.csv": "bb"}, seconds=130.0)
        result = _runner.invoke(cli, ["debug", "equivalence", "compare", "a", "b"])
        assert result.exit_code == 1
        assert "S4 generated-files: DIFFERS" in _words(result)
        assert "differs: data/deliveries/x.csv" in _words(result)
        assert "S1 recorded-results: same" in _words(result)
        assert "difference +30s" in _words(result)

    def test_it_prints_both_commits_and_the_commits_between(self, baselines):
        baselines("a", commit="HEAD~2")
        baselines("b")
        result = _runner.invoke(cli, ["debug", "equivalence", "compare", "a", "b"])
        assert "commits between: 2" in _words(result)

    def test_s1_rows_only_on_one_side_are_shown(self, baselines):
        baselines("a")
        baselines("b", s1={"qa.run": {"columns": ["run_key"], "rows": [[["\"r2\""], 1]]}})
        result = _runner.invoke(cli, ["debug", "equivalence", "compare", "a", "b"])
        assert result.exit_code == 1
        assert "only in A: run_key=\"r1\"" in _words(result)
        assert "only in B: run_key=\"r2\"" in _words(result)

    def test_surfaces_by_name_or_code(self, baselines):
        baselines("a")
        baselines("b", s4={"data/deliveries/x.csv": "bb"})
        for sel in (["--surfaces", "S1", "--surfaces", "help-and-menus"],
                    ["--surfaces", "recorded-results"]):
            result = _runner.invoke(cli, ["debug", "equivalence", "compare", "a", "b", *sel])
            assert result.exit_code == 0, result.output
            assert "S4" not in _words(result)

    def test_an_unknown_surface_is_refused_naming_the_four(self, baselines):
        baselines("a")
        baselines("b")
        result = _runner.invoke(cli, ["debug", "equivalence", "compare", "a", "b",
                                      "--surfaces", "S6"])
        assert result.exit_code != 0
        assert "S7 (help-and-menus)" in _words(result)

    def test_different_harness_versions_are_refused_naming_both(self, baselines):
        baselines("a")
        baselines("b", harness=eq.HARNESS_VERSION + 1)
        result = _runner.invoke(cli, ["debug", "equivalence", "compare", "a", "b"])
        assert result.exit_code != 0
        assert f"a: {eq.HARNESS_VERSION}" in _words(result)
        assert f"b: {eq.HARNESS_VERSION + 1}" in _words(result)

    def test_baselines_pinned_to_different_instants_are_refused(self, baselines):
        """Criterion 17."""
        baselines("a")
        baselines("b", pinned_now="2001-01-01T00:00:00+08:00")
        result = _runner.invoke(cli, ["debug", "equivalence", "compare", "a", "b"])
        assert result.exit_code != 0
        assert f"a: {eq.PINNED_NOW}" in _words(result)
        assert "b: 2001-01-01T00:00:00+08:00" in _words(result)

    def test_a_report_difference_names_its_json_path(self, baselines):
        baselines("a", s5={"r.json": {"rows": [{"n": 1}, {"n": 2}]}})
        baselines("b", s5={"r.json": {"rows": [{"n": 1}, {"n": 3}]}})
        result = _runner.invoke(cli, ["debug", "equivalence", "compare", "a", "b"])
        assert result.exit_code == 1
        assert ".rows[1].n: 2 vs 3" in _words(result)

    def test_help_lists_all_four_surfaces_by_name_and_code(self):
        result = _runner.invoke(cli, ["debug", "equivalence", "--help"])
        for code, name, _ in eq.SURFACES:
            assert code in _words(result) and name in _words(result)


class TestCaptureRefuses:
    """Criteria 10, 11, 13 and 14 - every refusal before any work."""

    def test_the_real_database(self, baselines, monkeypatch):
        import psycopg

        info = psycopg.conninfo.conninfo_to_dict(os.environ["MOTHMAN_SUPPLY_DSN"])
        dsn = psycopg.conninfo.make_conninfo(**{**info, "dbname": "equiv_same"})
        monkeypatch.setenv("MOTHMAN_SUPPLY_DSN", dsn)
        result = _runner.invoke(cli, ["debug", "equivalence", "capture", "--ref", "HEAD",
                                      "--label", "same"])
        assert result.exit_code != 0
        assert "never writes to the real database" in _words(result)

    def test_a_real_asset(self, baselines, monkeypatch):
        monkeypatch.setattr("qa_tools.common.asset_time.declared_synthetic", lambda: False)
        result = _runner.invoke(cli, ["debug", "equivalence", "capture", "--ref", "HEAD",
                                      "--label", "x"])
        assert result.exit_code != 0
        assert "not declared synthetic" in _words(result)

    def test_an_existing_label_without_yes(self, baselines):
        baselines("taken")
        result = _runner.invoke(cli, ["debug", "equivalence", "capture", "--ref", "HEAD",
                                      "--label", "taken"])
        assert result.exit_code != 0
        assert "--yes" in _words(result)

    def test_a_ref_that_is_not_a_commit(self, baselines):
        result = _runner.invoke(cli, ["debug", "equivalence", "capture", "--ref",
                                      "no-such-ref", "--label", "x"])
        assert result.exit_code != 0
        assert "no commit 'no-such-ref'" in _words(result)


def test_a_failed_capture_names_its_stage_and_leaves_nothing(baselines, tmp_path,
                                                             harness_free):
    """Criteria 12 and 14, for real: a commit from before `env mark` fails at
    the mark stage, and then no baseline, no worktree and no database remain."""
    import psycopg

    result = _runner.invoke(cli, ["debug", "equivalence", "capture", "--ref",
                                  BEFORE_ENV_MARK, "--label", "pytest-fails"])
    assert result.exit_code != 0
    assert "stage 'mark'" in _words(result)
    assert not list(tmp_path.glob("pytest-fails*"))
    worktrees = subprocess.run(["git", "worktree", "list"], capture_output=True, text=True,
                               cwd=eq.ROOT).stdout
    assert str(eq.work_dir()) not in worktrees
    assert not eq.work_dir().exists()
    admin, _scratch, name = eq._scratch_dsn("pytest-fails")
    with psycopg.connect(admin) as conn:
        assert not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s",
                                [name]).fetchall()


def test_a_killed_captures_leftovers_go_with_the_next_capture(baselines, harness_free):
    """post-build-review #210: a capture that is KILLED - a container restart,
    as on 2026-10-16 - never reaches its own cleanup, so its worktree stays
    registered and its directory stays on disk. The next capture clears
    both before it starts."""
    left = eq.work_dir()
    subprocess.run(["git", "worktree", "add", "--detach", "-q", str(left / "tree"),
                    BEFORE_ENV_MARK], cwd=eq.ROOT, check=True, capture_output=True)
    try:
        result = _runner.invoke(cli, ["debug", "equivalence", "capture", "--ref",
                                      BEFORE_ENV_MARK, "--label", "pytest-killed"])
        assert "stage 'mark'" in _words(result)
        worktrees = subprocess.run(["git", "worktree", "list"], capture_output=True,
                                   text=True, cwd=eq.ROOT).stdout
        assert str(left) not in worktrees
        assert not left.exists()
    finally:
        lock = eq._one_capture_at_a_time()  # never tidy a live capture's tree
        try:
            subprocess.run(["git", "worktree", "remove", "--force", str(left / "tree")],
                           cwd=eq.ROOT, capture_output=True)
        finally:
            lock.close()


def test_a_second_capture_while_one_runs_is_refused(baselines, harness_free):
    """One fixed worktree, so one capture at a time - and a live capture's
    tree is never cleared from under it."""
    held = eq._one_capture_at_a_time()
    try:
        result = _runner.invoke(cli, ["debug", "equivalence", "capture", "--ref",
                                      BEFORE_ENV_MARK, "--label", "pytest-second"])
        assert result.exit_code != 0
        assert "another equivalence capture is running" in _words(result)
    finally:
        held.close()


class TestTheSurfacesReadTheTree:
    def test_generated_files_hash_every_generated_file(self, tmp_path):
        (tmp_path / "data" / "deliveries" / "d1").mkdir(parents=True)
        (tmp_path / "data" / "deliveries" / "d1" / "a.csv").write_text("x")
        (tmp_path / "data" / "receipts").mkdir()
        (tmp_path / "data" / "receipts" / "r.json").write_text("{}")
        (tmp_path / "data" / "generator_bookkeeping.json").write_text("{}")
        (tmp_path / "data" / "dbt_scratch" / "run").mkdir(parents=True)
        (tmp_path / "data" / "dbt_scratch" / "run" / "manifest.json").write_text("{}")
        got = eq.generated_files(tmp_path)
        assert set(got) == {"data/deliveries/d1/a.csv", "data/receipts/r.json",
                            "data/generator_bookkeeping.json"}

    def test_reports_drop_the_named_clock_keys(self, tmp_path):
        built = tmp_path / "reports"
        built.mkdir()
        (built / "x.json").write_text(json.dumps(
            {"generated_at": "now", "datasets": [{"generated_at": "now", "id": "a",
                                                  "run_timestamp": "t", "recordedAt": "t"}]}))
        assert eq.reports(tmp_path) == {"x.json": {"datasets": [{"id": "a"}]}}

    def test_reports_name_ids_and_noisy_instants_by_what_they_are(self, tmp_path):
        """Normaliser 2: a decision or load id becomes what it names; an
        instant from a clock or a rule decision's running clock becomes its
        kind; a wait measured to a rule's time goes with it; every other
        value is untouched."""
        from datetime import datetime

        rule_at = datetime.fromisoformat("2026-08-18T03:00:02.719734+00:00")
        ctx = {"decisions": {"155": "civil-registration#66"},
               "loads": {"47": "birth-registrations#12"},
               "instants": {rule_at: "<rule-made decision's time>"}}
        built = tmp_path / "reports"
        built.mkdir()
        (built / "x.json").write_text(json.dumps({
            "slots": [{"decision_id": 155, "at": "2026-08-18T11:00:02.719734+08:00",
                       "kept": "2026-08-18T03:00:00+00:00"}],
            "points": [{"decisions": [{"id": 155}]}],
            "history": [{"attempt": 47}],
            "arrivals": [{"filledAt": "2026-08-18T03:00:02.719734+00:00", "waitedSeconds": 9.5},
                         {"filledAt": None, "waitedSeconds": 4.0}]}))
        got = eq.reports(tmp_path, ctx)["x.json"]
        assert got["slots"] == [{"decision_id": "civil-registration#66",
                                 "at": "<rule-made decision's time>",
                                 "kept": "2026-08-18T03:00:00+00:00"}]
        assert got["points"] == [{"decisions": [{"id": "civil-registration#66"}]}]
        assert got["history"] == [{"attempt": "birth-registrations#12"}]
        assert got["arrivals"] == [{"filledAt": "<rule-made decision's time>"},
                                   {"filledAt": None, "waitedSeconds": 4.0}]

    def test_the_bootstraps_own_timings_line_is_read(self):
        out = "x\nTook Birth Registrations 593s, Child Protection 1642s\n"
        assert eq._timings(out) == {"Birth Registrations": 593.0, "Child Protection": 1642.0}


@pytest.mark.full_capture
def test_two_captures_of_one_commit_compare_equal(baselines):
    """Criterion 5, THE SELF-CHECK: the normaliser is quiet. Two full
    bootstraps - about an hour - so it runs only with --run-full-capture,
    and never in CI (Keith, 2026-10-16: only when absolutely essential)."""
    for label in ("self-check-a", "self-check-b"):
        result = _runner.invoke(cli, ["debug", "equivalence", "capture", "--ref", "HEAD",
                                      "--label", label, "--yes"])
        assert result.exit_code == 0, result.output
    result = _runner.invoke(cli, ["debug", "equivalence", "compare", "self-check-a",
                                  "self-check-b"])
    assert result.exit_code == 0, result.output


def test_a_refiling_is_compared_as_the_decision_that_made_it(supply_dsn):
    """post-build-review #211: filing.refiled_by names the DECISION that
    re-filed a supply. The rule inherited from tests/equiv_support.py joined
    it to qa.filing.id, comparing whatever filing happened to share the
    number. Against a real database: re-file a supply, then the snapshot
    must name that re-filing decision by its place in its collection's log."""
    import test_refile_decision as rf

    period, target = f"2099-S{os.urandom(3).hex()}", f"2099-R{os.urandom(3).hex()}"
    with rf.supply_db.connect(label="test-equivalence") as conn:
        rf._base.qa_store.ensure_schema(conn)
        supply, _table = rf._filed(conn, period, "2026-05-01T01:00:00+00:00")
        rf._refile(conn, supply, period, target)
        raw, ref = conn.execute(
            "SELECT f.refiled_by, (SELECT d.collection_id || '#' || d.n FROM "
            "(SELECT id, collection_id, row_number() OVER (PARTITION BY collection_id "
            "ORDER BY id) AS n FROM qa.decision) d WHERE d.id = f.refiled_by) "
            "FROM qa.filing f WHERE f.supply_id = ? AND f.refiled_by IS NOT NULL",
            [supply]).fetchall()[0]
        assert raw is not None and ref.startswith(rf.COL + "#")
    cols, rows = eq.snapshot(os.environ["MOTHMAN_SUPPLY_DSN"])["qa.filing"]
    i, s = cols.index("refiled_by*"), cols.index("supply_id")
    got = [json.loads(r[i]) for r in rows if json.loads(r[s]) == supply and r[i] != "null"]
    assert got == [ref]


class TestTheRecordOfREQPIPE279IsComparedByWhatItSays:
    """REQ-PIPE-279's three new records under the snapshot (CI run
    40012232945's on-demand failures). An attempt's start and end are wall
    clock, but whether it ended is not; a read belongs to a result, not to
    that result's surrogate id; and run_seq is opening order, compared
    within each collection, since collections replaying side by side
    interleave the raw numbers while each collection's own order does not
    (REQ-PIPE-279's rank NFR). Each test also shows the comparison still
    catches the real difference beside the one it now ignores."""

    @staticmethod
    def _run(conn, key, collection="c1", seq=None):
        conn.execute("INSERT INTO qa.run (run_key, agency_id, collection_id, run_timestamp, "
                     "run_instant, run_seq) VALUES (?, 'a', ?, '2026-01-01T00:00:00+00:00', "
                     "'2026-01-01T00:00:00+00:00', ?)", [key, collection, seq])

    @staticmethod
    def _snap(**kw):
        return eq.snapshot(os.environ["MOTHMAN_SUPPLY_DSN"], **kw)

    def test_an_attempts_clock_is_left_out_but_whether_it_ended_is_not(self, clean_qa_history):
        conn = clean_qa_history
        self._run(conn, "r1", seq=1)
        conn.execute("INSERT INTO qa.run_attempt (run_key, run_seq, began_at, ended_at, outcome) "
                     "VALUES ('r1', 1, '2026-01-01T00:00:00Z', '2026-01-01T00:01:00Z', "
                     "'COMPLETED')")
        before = self._snap()
        conn.execute("UPDATE qa.run_attempt SET began_at = '2027-05-05T05:00:00Z', "
                     "ended_at = '2027-05-05T05:09:00Z'")
        assert eq.differences(before, self._snap()) == []
        conn.execute("UPDATE qa.run_attempt SET outcome = 'INTERRUPTED', ended_at = NULL")
        assert any(d.startswith("qa.run_attempt") for d in eq.differences(before, self._snap()))

    def _result_reading(self, conn, supply):
        [(rid,)] = conn.execute(
            "INSERT INTO qa.check_result (run_key, agency_id, collection_id, dataset_id, tool, "
            "check_id, status) VALUES ('r1', 'a', 'c1', 'd1', 'soda', 'x_ref', 'fail') "
            "RETURNING id").fetchall()
        conn.execute("INSERT INTO qa.check_read (check_result_id, logical_table, state, "
                     "supply_id) VALUES (?, 'clients', 'READ', ?)", [rid, supply])

    def test_a_read_is_compared_by_the_result_it_belongs_to(self, clean_qa_history):
        conn = clean_qa_history
        self._run(conn, "r1", seq=1)
        self._result_reading(conn, "clients@1")
        before = self._snap()
        # The same result recorded again: a new surrogate id, the same read.
        conn.execute("DELETE FROM qa.check_result")
        self._result_reading(conn, "clients@1")
        assert eq.differences(before, self._snap()) == []
        conn.execute("UPDATE qa.check_read SET supply_id = 'clients@2'")
        assert any(d.startswith("qa.check_read") for d in eq.differences(before, self._snap()))

    def _two_collections(self, conn, order):
        conn.execute("TRUNCATE qa.run, qa.run_attempt CASCADE")
        for seq, key in enumerate(order, start=1):
            self._run(conn, key, collection=key[:2], seq=seq)
            conn.execute("INSERT INTO qa.run_attempt (run_key, run_seq, began_at) "
                         "VALUES (?, ?, '2026-01-01T00:00:00Z')", [key, seq])

    def test_opening_order_is_compared_within_each_collection(self, clean_qa_history):
        conn = clean_qa_history
        self._two_collections(conn, ["c1_a", "c2_a", "c1_b", "c2_b"])
        before = self._snap(run_seq_within_collection=True)
        # The two collections interleaved the other way: each one's own
        # order unchanged.
        self._two_collections(conn, ["c2_a", "c1_a", "c2_b", "c1_b"])
        assert eq.differences(before, self._snap(run_seq_within_collection=True)) == []
        # One collection's own order changed: a real difference, in both tables.
        self._two_collections(conn, ["c1_b", "c2_a", "c1_a", "c2_b"])
        diffs = eq.differences(before, self._snap(run_seq_within_collection=True))
        assert any(d.startswith("qa.run:") for d in diffs), diffs
        assert any(d.startswith("qa.run_attempt") for d in diffs), diffs

    def test_by_default_the_raw_numbers_are_compared(self, clean_qa_history):
        """A resume continues one collection from a copy of its own database,
        so there the raw sequence is deterministic and compared as it is."""
        conn = clean_qa_history
        self._two_collections(conn, ["c1_a", "c2_a", "c1_b", "c2_b"])
        before = self._snap()
        self._two_collections(conn, ["c2_a", "c1_a", "c2_b", "c1_b"])
        assert any(d.startswith("qa.run:") for d in eq.differences(before, self._snap()))
