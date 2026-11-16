"""Each asset's synthetic history, generated once and shared by the suite
(REQ-TEST-402, signed by Keith 2026-11-14).

WHY. Twenty-odd test modules each ran the real generator into a directory of
their own - the same seeded history, byte for byte, ten to forty seconds a
time, several times per run. A history is a pure function of the generator's
inputs and its anchor, so it is generated ONCE and every test that only reads
it reads the one copy: the `daily_history` and `quarterly_history` session
fixtures in tests/conftest.py.

ONCE PER RUN, NOT PER WORKER (criterion 3). Under xdist each worker is its own
pytest session, so a per-session fixture alone would generate once per worker.
The first worker to need an asset builds it under an exclusive fcntl.flock -
the standard library, not the filelock package - and the others wait, then
read under a shared lock that each holds until its session ends. A history
already built by an earlier run with the same key is restored rather than
regenerated.

THE KEY (criterion 3) is replay_inputs.cache_key(asset, anchor=the fixed test
anchor): the digest of every input a bootstrap reads - the generator, the
asset's providers and configuration, the shared code - with its KEY_PREFIX,
so a change to any of them misses, and the fixed anchor (REQ-GEN-404
criterion 11), so the key does not move with the calendar or with the
checkout's own data/<asset>/history_anchor. The build itself installs the
fixed anchor, whatever that file says (REQ-GEN-405 criterion 2). A digest of
this file is folded in beside it, since the build script, its environment and
an entry's layout live here (post-build-review #465).

A WAITING WORKER WAITS A BOUNDED TIME (BUILD_WAIT_SECONDS), and a build that
failed is recorded beside the entry so the run's other workers fail at once
with its message rather than each rebuilding (post-build-review #467).

WHERE (criterion 8): `.test-history/` at the repository root - gitignored,
never under data/ (everything that recognises arrivals reads data/, the
2026-09-28 incident), and outside /tmp's pytest session folders, which
pytest prunes and which filled the disk (plans/running-thoughts.md #139).

READ-ONLY, BY GUARDING THE WRITERS (criterion 5): the sandbox runs as root,
which ignores permissions, so a read-only bit would prove nothing. Every
writer of a history refuses a path under the shared root, naming the file
(guard_writers below), and each session compares a digest of every file it
read against the one recorded at build (verify below) as a backstop for a
write that went round the writers. A test that must change a history takes
its own copy (History.copy_to, criterion 6) - a plain copy, about a second,
never a regeneration.
"""
from __future__ import annotations

import fcntl
import functools
import hashlib
import inspect
import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Where every shared history and its cache live (criterion 8).
CACHE_DIR = ROOT / ".test-history"

#: Inside an entry: what it was built for, and a digest of every file.
ASSET_FILE = "ASSET"
DIGEST_FILE = "DIGEST.json"
#: The files of an entry that are bookkeeping of the cache, not the history.
_CACHE_FILES = frozenset({ASSET_FILE, DIGEST_FILE})


class SharedHistoryWritten(AssertionError):
    """A test wrote into a shared history (criterion 5)."""


@dataclass(frozen=True)
class History:
    """One asset's generated history: everything generator/output.py's
    redirect() points a generation at, under `root`."""

    asset: str
    root: Path
    key: str

    @property
    def deliveries(self) -> Path:
        return self.root / "deliveries"

    @property
    def receipts(self) -> Path:
        return self.root / "receipts"

    @property
    def bookkeeping(self) -> Path:
        return self.root / "generator_bookkeeping.json"

    @property
    def placements(self) -> Path:
        return self.root / "scenario_placements.json"

    @property
    def anchor_file(self) -> Path:
        return self.root / "history_anchor"

    def book(self) -> dict:
        """The generator's bookkeeping, as written."""
        return json.loads(self.bookkeeping.read_text())

    @contextmanager
    def as_generator_output(self):
        """The generator's call-time paths (driver.deliveries_dir() and the
        rest) answering this history for the with-block - for a test reading
        through them. On the shared history any write through them is refused."""
        from generator.output import redirect

        undo = redirect(self.root)
        try:
            yield self
        finally:
            undo()

    def copy_to(self, dest: Path, only=None) -> "History":
        """A copy of this history at `dest`, the test's own to change
        (criterion 6) - never a regeneration. `only`, a collection of delivery
        names, copies just those deliveries and their receipts, with the
        bookkeeping, placements and anchor file whole - for a test that reads
        the first arrival or two."""
        dest = Path(dest)
        if only is None:
            shutil.copytree(self.root, dest, ignore=shutil.ignore_patterns(*_CACHE_FILES))
            return History(self.asset, dest, self.key)
        only = set(only)
        missing = only - {p.name for p in self.deliveries.iterdir()}
        if missing:
            raise KeyError(f"no such delivery in the shared {self.asset} history: {sorted(missing)}")
        dest.mkdir(parents=True)
        for path in self.root.iterdir():
            if path.is_file() and path.name not in _CACHE_FILES:
                shutil.copy2(path, dest / path.name)
        for tree in ("deliveries", "receipts"):
            (dest / tree).mkdir()
            for name in sorted(only):
                if (self.root / tree / name).exists():
                    shutil.copytree(self.root / tree / name, dest / tree / name)
        return History(self.asset, dest, self.key)


def key(asset: str) -> str:
    """The cache key of `asset`'s shared history: replay_inputs' key for its
    inputs at the fixed test anchor (criterion 3), and a digest of THIS FILE.

    THIS FILE IS A BUILD INPUT TOO (post-build-review #465): the build script
    (_BUILD), the environment it runs in and an entry's layout are all here,
    and replay_inputs' digest covers none of tests/ - so without it a change
    to how a history is built restored the one the old build made."""
    from asset_model import history_anchor
    from bootstrap import replay_inputs

    build = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]
    return (replay_inputs.cache_key(asset, anchor=history_anchor.FIXED_TEST_ANCHOR)
            + f"-build-{build}")


def digest(root: Path) -> dict[str, str]:
    """{relative path: sha256} of every file of the history under `root`."""
    root = Path(root)
    out = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name not in _CACHE_FILES:
            out[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def changed_files(root: Path) -> list[str]:
    """The files of the entry at `root` that differ from its recorded digest -
    changed, added or removed - empty when it is as built."""
    root = Path(root)
    recorded = json.loads((root / DIGEST_FILE).read_text())
    now = digest(root)
    return sorted(p for p in set(recorded) | set(now) if recorded.get(p) != now.get(p))


#: The generation run in a process of its own: the asset selected, the fixed
#: anchor installed, everything written under the folder named. A process of
#: its own so that nothing a test has installed in a worker - a pin, a
#: monkeypatch, another asset's selection - reaches the shared history.
_BUILD = """
import contextlib, io, sys, warnings
from pathlib import Path
from asset_model import history_anchor
from generator.output import generated_into
with history_anchor.anchored(history_anchor.FIXED_TEST_ANCHOR), \\
        contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
    warnings.simplefilter("ignore")
    with generated_into(Path(sys.argv[1])):
        pass
"""


def _build(asset: str, dest: Path) -> None:
    from asset_model import assets

    env = dict(os.environ, **{assets.ASSET_ENV: asset, "MOTHMAN_ENVIRONMENT": "test"})
    done = subprocess.run([sys.executable, "-c", _BUILD, str(dest)], cwd=ROOT, env=env,
                          capture_output=True, text=True)
    if done.returncode:
        raise RuntimeError(f"generating the shared {asset} history failed:\n"
                           f"{done.stderr[-4000:]}")


def _lock_file(entry_key: str) -> Path:
    return CACHE_DIR / f"{entry_key}.lock"


#: How long a worker waits for another to finish building a history before
#: giving up, naming what it waited on (post-build-review #467). A cold build
#: of the quarterly asset is about a minute on the 4-core sandbox; this is
#: generous on purpose, a bound rather than an estimate.
BUILD_WAIT_SECONDS = 30 * 60


class SharedHistoryBuildFailed(RuntimeError):
    """Building a shared history failed, in this process or in another
    worker of the same run (post-build-review #467)."""


def _open_locked(path: Path, how: int, *, wait: float | None = None) -> int:
    """`path` opened and flocked `how`, retried until the lock is on the file
    that is still at `path` - a pruner may unlink a lock file between the
    open and the lock. With `wait`, the lock is waited for that many seconds
    at most and TimeoutError names the file; with `how` carrying LOCK_NB,
    BlockingIOError is raised at once, as flock raises it."""
    deadline = None if wait is None else time.monotonic() + wait
    while True:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            if deadline is None:
                fcntl.flock(fd, how)
            else:
                while True:
                    try:
                        fcntl.flock(fd, how | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise TimeoutError(
                                f"waited {wait:.0f}s for the lock on {path}, which another "
                                f"process still holds") from None
                        time.sleep(0.2)
        except BaseException:
            os.close(fd)
            raise
        try:
            same = os.stat(path).st_ino == os.fstat(fd).st_ino
        except FileNotFoundError:
            same = False
        if same:
            return fd
        os.close(fd)


#: The lock each process holds on the entries it reads, until it exits.
_HELD: dict[str, tuple[int, History]] = {}


def acquire(asset: str) -> History:
    """`asset`'s shared history, held under a shared lock until this process
    ends: restored where an entry with its key exists, built under an
    exclusive lock where it does not (criterion 3)."""
    if asset in _HELD:
        return _HELD[asset][1]
    CACHE_DIR.mkdir(exist_ok=True)
    entry_key = key(asset)
    entry = CACHE_DIR / entry_key
    # TWO LOCKS PER ENTRY. The READ lock is held shared for the whole session,
    # so no pruner can remove an entry somebody is reading; the BUILD lock is
    # taken exclusively, and only while building, so the workers that find no
    # entry wait for the first to build it rather than for every reader to
    # finish (one lock for both would deadlock a second builder behind the
    # first one's shared hold).
    fd = _open_locked(_lock_file(entry_key), fcntl.LOCK_SH)
    try:
        if not entry.is_dir():
            build_lock = CACHE_DIR / f"{entry_key}.build"
            try:
                build = _open_locked(build_lock, fcntl.LOCK_EX, wait=BUILD_WAIT_SECONDS)
            except TimeoutError as waited:
                raise SharedHistoryBuildFailed(
                    f"gave up on the shared {asset} history: {waited}. Another worker is "
                    f"building it or has hung doing so; if nothing is running, delete "
                    f"{build_lock} and run again.") from None
            try:
                if not entry.is_dir():
                    _build_once_per_run(asset, entry_key)
                    _prune(asset, entry_key)
            finally:
                os.close(build)
        # RESTORED ONLY AS BUILT: an entry an earlier session changed (and was
        # failed for, see conftest) is never read again as though it were whole.
        changed = changed_files(entry)
        if changed:
            raise SharedHistoryWritten(
                f"the cached {asset} history {entry} differs from what was built - "
                f"{len(changed)} file(s), first {changed[:5]}. Delete {CACHE_DIR} and run again.")
    except BaseException:
        os.close(fd)
        raise
    history = History(asset, entry, entry_key)
    _HELD[asset] = (fd, history)
    return history


def _failed_file(entry_key: str) -> Path:
    return CACHE_DIR / f"{entry_key}.failed"


def _run_id() -> str | None:
    """This test run's id, shared by every xdist worker of it - None outside
    xdist, where no other worker of the run is waiting."""
    return os.environ.get("PYTEST_XDIST_TESTRUNUID") or None


def _build_once_per_run(asset: str, entry_key: str) -> None:
    """Build the entry, called under its build lock - unless a worker of THIS
    run already tried and failed, in which case fail at once with that
    worker's message rather than spend another build finding the same thing
    (post-build-review #467). A failure recorded by an EARLIER run is
    cleared and the build tried again."""
    failed = _failed_file(entry_key)
    run = _run_id()
    if failed.exists():
        recorded = json.loads(failed.read_text())
        if run is not None and recorded.get("run") == run:
            raise SharedHistoryBuildFailed(
                f"the shared {asset} history was not built - another worker of this run "
                f"(pid {recorded.get('pid')}) already failed to build it:\n{recorded['error']}")
        failed.unlink()
    try:
        _build_entry(asset, entry_key)
    except Exception as error:
        failed.write_text(json.dumps({"run": run, "pid": os.getpid(), "error": str(error)}))
        raise


def _build_entry(asset: str, entry_key: str) -> None:
    """Build `asset`'s history beside the entry and rename it into place, so
    an entry that exists is always whole."""
    for stale in CACHE_DIR.glob(f".building-{entry_key}-*"):
        shutil.rmtree(stale, ignore_errors=True)
    building = CACHE_DIR / f".building-{entry_key}-{os.getpid()}"
    _build(asset, building)
    (building / ASSET_FILE).write_text(asset + "\n")
    (building / DIGEST_FILE).write_text(json.dumps(digest(building), indent=1, sort_keys=True))
    os.rename(building, CACHE_DIR / entry_key)


def _prune(asset: str, keep: str) -> list[str]:
    """Remove `asset`'s other cached histories - each only under an
    exclusive lock taken without waiting, so one another session still reads
    under a shared lock is skipped (criterion 4). Returns the keys removed."""
    removed = []
    for other in sorted(CACHE_DIR.iterdir()):
        if not other.is_dir() or other.name == keep or other.name.startswith("."):
            continue
        # ONLY WHAT IS PROVABLY THIS ASSET'S (post-build-review #469): a folder
        # with no ASSET file was not made by _build_entry, so it is left alone.
        try:
            owner = (other / ASSET_FILE).read_text().strip()
        except FileNotFoundError:
            continue
        if owner != asset:
            continue
        lock = _lock_file(other.name)
        # THE SAME INODE RE-CHECK AS acquire()'s (post-build-review #466): a
        # second pruner may unlink the lock file between the open and the lock.
        try:
            fd = _open_locked(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            continue
        try:
            shutil.rmtree(other, ignore_errors=True)
            lock.unlink(missing_ok=True)
            (CACHE_DIR / f"{other.name}.build").unlink(missing_ok=True)
            _failed_file(other.name).unlink(missing_ok=True)
            removed.append(other.name)
        finally:
            os.close(fd)
    return removed


def release(asset: str) -> None:
    """Give up this process's shared lock on `asset`'s history."""
    held = _HELD.pop(asset, None)
    if held is not None:
        os.close(held[0])


def guard_writers():
    """Every writer of a generated history refusing a path under CACHE_DIR,
    naming the file (criterion 5); returns the callable that puts them back.

    The five the criterion names - write_delivery, write_receipts,
    remove_deliveries, write_bookkeeping and write_placements - and the two
    that write the anchor beside them, record_anchor and history_anchor.write,
    which a generation calls between them."""
    from asset_model import delivery as delivery_tree
    from asset_model import history_anchor
    from generator import driver, scenario_injection
    from qa_tools.common import delivery

    shared = CACHE_DIR.resolve()

    def refuse_under(writer: str, *paths) -> None:
        for p in paths:
            if p is None:
                continue
            resolved = Path(p).resolve()
            if resolved == shared or shared in resolved.parents:
                raise SharedHistoryWritten(
                    f"{writer} tried to write {resolved}, which is in a shared, read-only "
                    f"history (tests/shared_history.py) - take the test's own copy with "
                    f"History.copy_to(tmp_path) and write there")

    def wrap(module, name, targets):
        real = getattr(module, name)
        signature = inspect.signature(real)

        @functools.wraps(real)
        def guarded(*args, **kwargs):
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            refuse_under(f"{module.__name__}.{name}", *targets(bound.arguments))
            return real(*args, **kwargs)

        setattr(module, name, guarded)
        return module, name, real

    def named_delivery(a):
        deliveries = Path(a.get("deliveries_dir") or delivery_tree.default_deliveries_dir())
        receipts = Path(a.get("receipts_dir") or delivery_tree.default_receipts_dir())
        names = [a["name"]] if "name" in a else list(a.get("names") or [])
        return [*(deliveries / n for n in names), deliveries, receipts]

    def receipts(a):
        r = Path(a.get("receipts_dir") or delivery_tree.default_receipts_dir())
        return [r / a["name"], r]

    originals = [
        wrap(delivery, "write_delivery", named_delivery),
        wrap(delivery, "write_receipts", receipts),
        wrap(delivery, "remove_deliveries", named_delivery),
        wrap(driver, "write_bookkeeping", lambda a: [driver.bookkeeping_path()]),
        wrap(driver, "record_anchor", lambda a: [driver.bookkeeping_path(), driver.anchor_path()]),
        wrap(scenario_injection, "write_placements",
             lambda a: [a.get("path") or scenario_injection.placements_path()]),
        wrap(history_anchor, "write", lambda a: [a.get("at") or history_anchor.path()]),
    ]

    def restore():
        for module, name, real in reversed(originals):
            setattr(module, name, real)

    return restore


def session(asset: str, fail):
    """A session's hold on `asset`'s shared history: acquired, yielded, and at
    the end checked against its digest - the backstop (criterion 5) for a
    write that went round the guarded writers (an open() of its own, a process
    a test started), reported through `fail` naming every file it changed."""
    history = acquire(asset)
    try:
        yield history
    finally:
        changed = changed_files(history.root)
        release(asset)
    if changed:
        fail(f"the shared {asset} history at {history.root} was changed during this session - "
             f"{len(changed)} file(s), first {changed[:5]}. Delete {CACHE_DIR} and find the "
             f"test that wrote there.")


def answer_regenerations(history: History, monkeypatch) -> None:
    """Product code that REGENERATES a history only to read it - a checkpoint's
    arrival numbering (bootstrap.checkpoints.arrivals_of) and a resume's
    comparison print (bootstrap.replay_inputs.regenerated_print) - answered
    from `history` for one test, for a test whose subject is not that
    regeneration (REQ-TEST-402 criterion 7). Each generates every collection
    at the installed anchor into a folder of its own and reads it, so at the
    fixed anchor its answer IS the shared history's; at any other anchor
    installed, the real regeneration runs."""
    from asset_model import arrivals as arrival_tree
    from asset_model import history_anchor
    from bootstrap import checkpoints, replay_inputs

    real_arrivals, real_print = checkpoints.arrivals_of, replay_inputs.regenerated_print

    def at_the_fixed_anchor() -> bool:
        return history_anchor.installed() in (None, history_anchor.FIXED_TEST_ANCHOR)

    def arrivals_of(collection_id):
        if not at_the_fixed_anchor():
            return real_arrivals(collection_id)
        return arrival_tree.arrivals_for(collection_id, "", history.deliveries, history.receipts)

    def regenerated_print(collection_id):
        if not at_the_fixed_anchor():
            return real_print(collection_id)
        return replay_inputs.deliveries_print(collection_id, history.deliveries, history.receipts)

    monkeypatch.setattr(checkpoints, "arrivals_of", arrivals_of)
    monkeypatch.setattr(replay_inputs, "regenerated_print", regenerated_print)
