"""The suite's shared synthetic history (REQ-TEST-402): built once per run or
restored by its inputs' key, at the fixed test anchor, read-only to every test,
copied for a test that must change it - tests/shared_history.py.

The locking and pruning tests drive the real acquire() in real separate
processes, with the generation itself replaced by a small stand-in that counts
its calls, so that "once across every worker" is observed rather than assumed
and costs seconds rather than a generation per process."""
from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import textwrap
from datetime import date
from pathlib import Path

import pytest

import shared_history
from asset_model import history_anchor
from bootstrap import replay_inputs
from generator import driver, scenario_injection
from qa_tools.common import delivery
from generator import delivery_writer

pytestmark = pytest.mark.asset("daily")

TESTS = Path(__file__).resolve().parent
FIXED = history_anchor.FIXED_TEST_ANCHOR


class TestTheSharedHistoryIsTheGeneratorsOwn:
    """Criterion 2: one session fixture per asset, yielding the generated
    delivery and receipt trees."""

    def test_the_daily_history_holds_deliveries_receipts_and_bookkeeping(self, daily_history):
        book = daily_history.book()
        assert book["birth-registrations"], "the bookkeeping names no birth registration"
        named = {e["delivery"] for e in book["birth-registrations"]}
        on_disk = {p.name for p in daily_history.deliveries.iterdir()}
        assert named and named <= on_disk
        assert {p.name for p in daily_history.receipts.iterdir()} == on_disk

    @pytest.mark.asset("quarterly")
    def test_the_quarterly_history_holds_every_collection_in_hierarchy_order(
            self, quarterly_history):
        from generator import collections

        book = quarterly_history.book()
        providers = collections.providers()
        assert [p.collection_id for p in providers] == [
            "child-protection", "emergency-department", "linkage-products"]
        for p in providers:
            ids = [d for st in p.streams() for d in st.dataset_ids]
            assert any(book.get(d) for d in ids), p.collection_id

    def test_it_is_recorded_at_the_fixed_test_anchor(self, daily_history):
        assert daily_history.book()[driver.ANCHOR_KEY] == FIXED.isoformat()
        assert history_anchor.recorded(daily_history.anchor_file) == FIXED

    def test_it_is_kept_in_the_gitignored_folder_never_under_data(self, daily_history):
        """Criterion 8."""
        root = daily_history.root.resolve()
        assert shared_history.CACHE_DIR.resolve() in root.parents
        assert (shared_history.ROOT / "data").resolve() not in root.parents
        assert "pytest-of-" not in str(root)
        ignored = subprocess.run(["git", "check-ignore", "-q", str(root / "x")],
                                 cwd=shared_history.ROOT)
        assert ignored.returncode == 0, f"{root} is not gitignored"


class TestTheKey:
    """Criterion 3: replay_inputs' digest of the generator's inputs, and the
    fixed test anchor."""

    def test_it_is_the_bootstrap_cache_key_at_the_fixed_anchor(self):
        assert shared_history.key("daily").startswith(
            replay_inputs.cache_key("daily", anchor=FIXED) + "-")
        assert shared_history.key("daily").startswith(replay_inputs.KEY_PREFIX + "daily-")

    def test_a_change_to_the_build_script_itself_misses(self, tmp_path, monkeypatch):
        """post-build-review #465: the build (_BUILD, its environment, the
        entry layout) lives in tests/shared_history.py, which replay_inputs'
        digest does not cover - so a change there restored the history the
        OLD build made. Two copies of the module, one with the build script
        edited, must key differently; two identical copies must not."""
        import importlib.util

        source = Path(shared_history.__file__).read_text()
        edited = source.replace("warnings.simplefilter(\"ignore\")",
                                "warnings.simplefilter(\"ignore\")  # edited")
        assert edited != source, "precondition: the build script was edited"

        def key_of(text, name):
            path = tmp_path / name / "tests" / "shared_history.py"
            path.parent.mkdir(parents=True)
            path.write_text(text)
            spec = importlib.util.spec_from_file_location(f"sh_{name}", path)
            module = importlib.util.module_from_spec(spec)
            monkeypatch.setitem(sys.modules, spec.name, module)  # a dataclass needs it
            spec.loader.exec_module(module)
            return module.key("daily")

        same = key_of(source, "same")
        assert key_of(source, "again") == same
        assert key_of(edited, "edited") != same

    def test_another_installed_anchor_does_not_move_it(self):
        before = shared_history.key("daily")
        with history_anchor.anchored(date(2026, 11, 2)):
            assert shared_history.key("daily") == before

    def test_a_generator_change_misses(self, monkeypatch):
        real = replay_inputs.input_files(replay_inputs.inputs("daily"))
        provider = "assets/daily/synthetic/collections/civil_registration.py"
        shared = "generator/driver.py"
        assert provider in real and shared in real
        before = shared_history.key("daily")
        for changed in (provider, shared):
            edited = dict(real, **{changed: "0" * 64})
            monkeypatch.setattr(replay_inputs, "input_files", lambda patterns=None, e=edited: e)
            assert shared_history.key("daily") != before, changed


class TestNoTestCanWriteIt:
    """Criterion 5: every writer refuses a path under the shared root, naming
    it, and the history is unchanged after."""

    @pytest.fixture
    def shared(self, daily_history):
        yield daily_history
        assert shared_history.changed_files(daily_history.root) == []

    def test_write_delivery_refuses(self, shared):
        with pytest.raises(shared_history.SharedHistoryWritten, match="write_delivery.*shared"):
            delivery.write_delivery("intruder", {"birth_registrations_2026-01-01.csv": "a\n"},
                                    deliveries_dir=shared.deliveries,
                                    receipts_dir=shared.receipts)
        assert not (shared.deliveries / "intruder").exists()

    def test_write_receipts_refuses(self, shared):
        with pytest.raises(shared_history.SharedHistoryWritten, match="write_receipts"):
            delivery.write_receipts("intruder", "2026-01-01T00:00:00+08:00", shared.receipts,
                                    files=["x.csv"])

    def test_remove_deliveries_refuses(self, shared):
        some = next(shared.deliveries.iterdir()).name
        with pytest.raises(shared_history.SharedHistoryWritten, match=f"remove_deliveries.*{some}"):
            delivery_writer.remove_deliveries([some], shared.deliveries, shared.receipts)
        assert (shared.deliveries / some).is_dir()

    def test_the_bookkeeping_and_anchor_writers_refuse(self, shared):
        with shared.as_generator_output():
            with pytest.raises(shared_history.SharedHistoryWritten, match="write_bookkeeping"):
                driver.write_bookkeeping("birth-registrations", [])
            with pytest.raises(shared_history.SharedHistoryWritten, match="record_anchor"):
                driver.record_anchor(date(2026, 11, 1))
        with pytest.raises(shared_history.SharedHistoryWritten, match="history_anchor.write"):
            history_anchor.write(date(2026, 11, 1), shared.anchor_file)

    def test_write_placements_refuses(self, shared):
        with pytest.raises(shared_history.SharedHistoryWritten, match="write_placements"):
            scenario_injection.write_placements([], shared.placements)

    def test_a_generation_pointed_at_it_refuses_before_anything_changes(self, shared):
        with shared.as_generator_output():
            with pytest.raises(shared_history.SharedHistoryWritten):
                driver.generate("civil-registration")

    def test_a_write_round_the_writers_is_found_by_the_digest(self, daily_history, tmp_path):
        """The backstop, on a copy: the shared one is never written to prove it."""
        copy = daily_history.copy_to(tmp_path / "copy")
        (copy.root / shared_history.DIGEST_FILE).write_text(
            (daily_history.root / shared_history.DIGEST_FILE).read_text())
        assert shared_history.changed_files(copy.root) == []
        target = next(copy.deliveries.iterdir())
        victim = next(target.iterdir())
        with open(victim, "a") as f:
            f.write("tampered\n")
        assert shared_history.changed_files(copy.root) == [
            victim.relative_to(copy.root).as_posix()]


class TestATestThatMustChangeItTakesACopy:
    """Criterion 6."""

    def test_the_copy_is_the_history_and_is_writable(self, daily_history, tmp_path):
        copy = daily_history.copy_to(tmp_path / "mine")
        assert shared_history.digest(copy.root) == shared_history.digest(daily_history.root)
        some = next(copy.deliveries.iterdir()).name
        delivery_writer.remove_deliveries([some], copy.deliveries, copy.receipts)
        assert not (copy.deliveries / some).exists()
        assert (daily_history.deliveries / some).is_dir()


# THE LOCKING, IN REAL PROCESSES. Each runs acquire() against a cache folder of
# the test's own, with the key and the generation stood in for.
_WORKER = textwrap.dedent("""
    import json, os, sys, time
    sys.path[:0] = [{tests!r}, {root!r}]
    from pathlib import Path
    import shared_history as sh
    cache, key, builds, hold = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]), float(sys.argv[4])
    mode, wait = sys.argv[5], sys.argv[6]
    sh.CACHE_DIR = cache
    sh.key = lambda asset: key
    if wait:
        sh.BUILD_WAIT_SECONDS = float(wait)
    def build(asset, dest):
        with open(builds, "a") as f:
            f.write(f"{{os.getpid()}}\\n")
        time.sleep(1.0)
        if mode == "fail":
            raise RuntimeError(f"stand-in build failed in {{os.getpid()}}")
        (dest / "deliveries" / "d1").mkdir(parents=True)
        (dest / "deliveries" / "d1" / "f.csv").write_text("x\\n")
    sh._build = build
    h = sh.acquire("daily")
    print(json.dumps({{"root": str(h.root), "files": sorted(sh.digest(h.root))}}), flush=True)
    time.sleep(hold)
""")


def _worker(tmp_path, cache, key, *, hold=0.0, mode="ok", wait="", run="run-1"):
    code = _WORKER.format(tests=str(TESTS), root=str(shared_history.ROOT))
    return subprocess.Popen(
        [sys.executable, "-c", code, str(cache), key, str(tmp_path / "builds"), str(hold),
         mode, str(wait)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=shared_history.ROOT,
        env=dict(os.environ, MOTHMAN_ASSET="daily", PYTEST_XDIST_TESTRUNUID=run))


def _builds(tmp_path) -> int:
    path = tmp_path / "builds"
    return len(path.read_text().split()) if path.exists() else 0


class TestOnceAcrossEveryWorker:
    """Criterion 3: the first process builds under an exclusive lock, the
    others wait and then read; a later run restores it."""

    def test_four_workers_at_once_build_it_once(self, tmp_path):
        cache = tmp_path / "cache"
        procs = [_worker(tmp_path, cache, "k-one") for _ in range(4)]
        outs = [p.communicate(timeout=120) for p in procs]
        assert all(p.returncode == 0 for p in procs), [e for _, e in outs]
        assert _builds(tmp_path) == 1
        seen = {o for o, _ in outs}
        assert len(seen) == 1 and json.loads(seen.pop())["files"] == ["deliveries/d1/f.csv"]

    def test_a_later_run_with_the_same_key_restores_it(self, tmp_path):
        cache = tmp_path / "cache"
        for _ in range(2):
            p = _worker(tmp_path, cache, "k-one")
            p.communicate(timeout=60)
            assert p.returncode == 0
        assert _builds(tmp_path) == 1


class TestAWaitingWorkerDoesNotWaitForever:
    """post-build-review #467: a worker waiting on another's build waits a
    bounded time and says what it waited on; a build that failed is not
    retried by every worker in turn - the rest of the run fails fast with
    the first failure's message, and a LATER run tries again."""

    def test_a_build_that_never_finishes_is_given_up_on_naming_it(self, tmp_path):
        cache = tmp_path / "cache"
        cache.mkdir()
        # ANOTHER WORKER BUILDING: the build lock held exclusively, as acquire()
        # holds it while it builds.
        fd = os.open(cache / "k-one.build", os.O_RDWR | os.O_CREAT, 0o644)
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            p = _worker(tmp_path, cache, "k-one", wait=2)
            try:
                _, err = p.communicate(timeout=60)
            except subprocess.TimeoutExpired:
                p.kill()
                p.communicate()
                pytest.fail("the waiting worker was still waiting after 60s")
        finally:
            os.close(fd)
        assert p.returncode != 0
        assert "waited" in err and "k-one.build" in err, err[-2000:]
        assert _builds(tmp_path) == 0

    def test_a_failed_build_is_not_retried_by_each_waiting_worker(self, tmp_path):
        cache = tmp_path / "cache"
        procs = [_worker(tmp_path, cache, "k-one", mode="fail") for _ in range(3)]
        outs = [p.communicate(timeout=120) for p in procs]
        assert all(p.returncode != 0 for p in procs)
        assert _builds(tmp_path) == 1
        builder = (tmp_path / "builds").read_text().split()[0]
        for _, err in outs:
            assert f"stand-in build failed in {builder}" in err, err[-2000:]
        assert not (cache / "k-one").exists()

    def test_a_later_run_tries_the_build_again(self, tmp_path):
        cache = tmp_path / "cache"
        p = _worker(tmp_path, cache, "k-one", mode="fail", run="run-1")
        p.communicate(timeout=60)
        assert p.returncode != 0
        p = _worker(tmp_path, cache, "k-one", run="run-2")
        _, err = p.communicate(timeout=60)
        assert p.returncode == 0, err[-2000:]
        assert _builds(tmp_path) == 2
        assert sorted(q.name for q in cache.iterdir() if q.is_dir()) == ["k-one"]


class TestAnOlderHistoryIsRemovedOnlyWhenNobodyHoldsIt:
    """Criterion 4."""

    def test_a_new_key_removes_the_old_one(self, tmp_path):
        cache = tmp_path / "cache"
        for key in ("k-old", "k-new"):
            p = _worker(tmp_path, cache, key)
            p.communicate(timeout=60)
            assert p.returncode == 0
        assert sorted(p.name for p in cache.iterdir() if p.is_dir()) == ["k-new"]

    def test_one_another_session_still_reads_is_kept(self, tmp_path):
        cache = tmp_path / "cache"
        p = _worker(tmp_path, cache, "k-old")
        p.communicate(timeout=60)
        # ANOTHER SESSION READING k-old: a shared lock held, as acquire() holds it.
        fd = os.open(cache / "k-old.lock", os.O_RDWR)
        fcntl.flock(fd, fcntl.LOCK_SH)
        try:
            p = _worker(tmp_path, cache, "k-new")
            p.communicate(timeout=60)
            assert p.returncode == 0
            assert sorted(q.name for q in cache.iterdir() if q.is_dir()) == ["k-new", "k-old"]
        finally:
            os.close(fd)

    def test_a_folder_that_names_no_asset_is_left_alone(self, tmp_path):
        """post-build-review #469: pruning removes only what it can tell is
        this asset's - a folder in the cache without an ASSET file (put there
        by hand, or by something else) is not."""
        cache = tmp_path / "cache"
        stranger = cache / "k-stranger"
        (stranger / "deliveries").mkdir(parents=True)
        (stranger / "deliveries" / "keep.csv").write_text("x\n")
        p = _worker(tmp_path, cache, "k-new")
        _, err = p.communicate(timeout=60)
        assert p.returncode == 0, err[-2000:]
        assert (stranger / "deliveries" / "keep.csv").is_file()


class TestTheBuildUsesTheFixedAnchor:
    """REQ-GEN-405 criterion 2: whatever anchor the process or the checkout's
    anchor file would otherwise give."""

    def test_a_rolled_anchor_file_and_installed_anchor_do_not_reach_it(self, tmp_path):
        rolled = tmp_path / "rolled_anchor"
        rolled.write_text("2026-11-10\n")
        prelude = textwrap.dedent(f"""
            from datetime import date
            from pathlib import Path
            from asset_model import history_anchor
            history_anchor.path = lambda: Path({str(rolled)!r})
            history_anchor.install(date(2026, 11, 10))
        """)
        dest = tmp_path / "built"
        code = prelude + shared_history._BUILD
        done = subprocess.run([sys.executable, "-c", code, str(dest)], cwd=shared_history.ROOT,
                              env=dict(os.environ, MOTHMAN_ASSET="daily",
                                       MOTHMAN_ENVIRONMENT="test"),
                              capture_output=True, text=True)
        assert done.returncode == 0, done.stderr[-2000:]
        assert history_anchor.recorded(dest / "history_anchor") == FIXED
        assert json.loads((dest / "generator_bookkeeping.json").read_text())[
            driver.ANCHOR_KEY] == FIXED.isoformat()
