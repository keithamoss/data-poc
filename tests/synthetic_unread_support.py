"""The harness behind REQ-GEN-370 criterion 3's tests
(tests/test_synthetic_folder_unread*.py): staging, the checks, the gate,
promotion and the dashboard build read nothing under an asset's synthetic/
folder.

HOW IT IS SHOWN: a Python audit hook watches while a real generated delivery
tree is put through the pipeline's batch pass (`orchestrate.run_pipeline`:
staged as it arrives, the four real tools, the arrival gate and promotion)
into an empty database of its own, and the dashboard is then built from what
was recorded (rebuild-results, build-data, embed, as `mothman dashboard
rebuild` runs them).

WHAT THE HOOK SEES, and what it does not (a decision on REQ-GEN-370):
- it sees every file this process opens through Python - open(),
  Path.read_text, os.open, io.open_code for a module loaded by path - every
  folder listed through os.listdir, os.scandir and glob, a listing by file
  descriptor resolved through /proc/self/fd, and every child process started
  through subprocess, whose executable, arguments and working directory are
  checked for a path under synthetic/;
- it does NOT see an os.stat, exists() or is_file() check (no audit event is
  raised for them), a file opened by a C extension's own code (libpq, DuckDB),
  or what a child process reads by itself without being handed the path (dbt
  runs as one, qa_tools/common/dbt_worker.py). A relative path opened against
  a directory descriptor cannot be resolved; one naming a `synthetic`
  component is counted as a read, so the gap fails safe.

ONE KNOWN READ, OWNED ELSEWHERE: the batch pass builds a scripted-decision
Player for every collection it runs (qa_tools/tools/orchestrate.py's
_begin), and the Player reads the asset's synthetic/scripted_decisions.yaml.
REQ-GEN-381 criteria 1 and 4 end it (Keith, 2026-11-15: c3 waits for it). It
is excused only when the Player's constructor was called from _begin - any
other read, by any other code or any other Player, fails - and the test stays
green once the read goes.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

import asset_folders
import equiv_support

ROOT = Path(__file__).resolve().parent.parent
REAL_SYNTHETIC = tuple(str((ROOT / "assets" / name / "synthetic").resolve())
                       for name in ("daily", "quarterly"))
PLAYER_FILE = os.path.join("qa_tools", "common", "scripted_decisions.py")
BEGIN_FILE = os.path.join("qa_tools", "tools", "orchestrate.py")
EVENTS = ("open", "os.listdir", "os.scandir", "glob.glob", "subprocess.Popen")

#: What the hook is watching for, or None when it is not watching. A hook
#: cannot be removed once added, so it is added once per process and does
#: nothing outside a `watching()` block.
_STATE: dict | None = None
_HOOKED = False


def excused_player_frame(frame) -> bool:
    """Whether `frame`'s stack holds the Player's constructor called from
    orchestrate._begin - the one read REQ-GEN-381 ends."""
    while frame is not None:
        code = frame.f_code
        if code.co_filename.endswith(PLAYER_FILE) and code.co_qualname == "Player.__init__":
            caller = frame.f_back
            return (caller is not None and caller.f_code.co_filename.endswith(BEGIN_FILE)
                    and caller.f_code.co_name == "_begin")
        frame = frame.f_back
    return False


#: How a path an event names is held against the synthetic/ roots.
RESOLVED, RELATIVE, ARGUMENT = "resolved", "relative", "argument"


def _text(value) -> str | None:
    if isinstance(value, bytes):
        value = os.fsdecode(value)
    if isinstance(value, os.PathLike):
        value = os.fspath(value)
        if isinstance(value, bytes):
            value = os.fsdecode(value)
    return value if isinstance(value, str) and value else None


def _paths(event: str, args) -> list[tuple[str, str]]:
    """(path, how to hold it) for each path an event names."""
    if event == "subprocess.Popen":
        executable, argv, cwd = (list(args) + [None] * 3)[:3]
        names = [executable, cwd] + (list(argv) if isinstance(argv, (list, tuple))
                                     else [argv])
        out = []
        for name in filter(None, map(_text, names)):
            out += _paths("open", (name,))
            # An argument may carry a path inside it (--project-dir=...).
            out.append((name, ARGUMENT))
        return out
    target = args[0] if args else None
    if isinstance(target, int):
        # A listing by descriptor (os.scandir(fd), os.fwalk).
        try:
            return [(os.readlink(f"/proc/self/fd/{target}"), RESOLVED)]
        except OSError:
            return []
    text = _text(target)
    if text is None:
        return []
    try:
        resolved = os.path.realpath(text)
    except (TypeError, ValueError):
        return []
    # A relative path may have been opened against a directory descriptor,
    # which the event does not carry - so it is held both ways.
    return [(resolved, RESOLVED)] + ([(text, RELATIVE)] if not os.path.isabs(text) else [])


def _under(path: str, how: str, roots) -> bool:
    if how == RELATIVE:
        # Fails safe: a `synthetic` component is enough.
        return "synthetic" in Path(path).parts
    if how == ARGUMENT:
        return any(root in path for root in roots)
    return any(path == root or path.startswith(root + os.sep) for root in roots)


def _hook(event: str, args) -> None:
    global _STATE
    state = _STATE
    if state is None or event not in EVENTS:
        return
    _STATE = None  # no re-entry while this event is looked at
    try:
        for path, how in _paths(event, args):
            if _under(path, how, state["roots"]):
                if event == "open" and excused_player_frame(sys._getframe(1)):
                    state["allowed"].append((event, path))
                else:
                    state["reads"].append((event, path, _who()))
                return
        if event != "subprocess.Popen" and any(
                path.startswith(folder + os.sep) for path, _ in _paths(event, args)
                for folder in state["asset"]):
            state["asset_reads"] += 1
    finally:
        _STATE = state


def _who() -> str:
    """The innermost product-code frame that made the read, for the message."""
    frame = sys._getframe(2)
    while frame is not None:
        name = frame.f_code.co_filename
        if name.startswith(str(ROOT)) and f"{os.sep}tests{os.sep}" not in name \
                and f"{os.sep}.venv{os.sep}" not in name:
            return f"{os.path.relpath(name, ROOT)}:{frame.f_lineno} in {frame.f_code.co_name}"
        frame = frame.f_back
    return "?"


class watching:
    """`with watching(asset_folder) as seen:` - every read under a synthetic/
    folder while inside, in seen["reads"] (or seen["allowed"], the excused
    Player read), and how many reads of the asset folder there were at all."""

    def __init__(self, asset_folder: Path):
        self.asset_folder = Path(asset_folder)

    def __enter__(self) -> dict:
        global _STATE, _HOOKED
        if not _HOOKED:
            sys.addaudithook(_hook)
            _HOOKED = True
        own = self.asset_folder / "synthetic"
        self.state = {
            # The folder and the real one its entries link to.
            "asset": (os.path.realpath(self.asset_folder),
                      os.path.realpath(asset_folders.real_folder())),
            "roots": tuple(dict.fromkeys((os.path.realpath(own), os.path.abspath(own))
                                         + REAL_SYNTHETIC)),
            "reads": [], "allowed": [], "asset_reads": 0}
        _STATE = self.state
        return self.state

    def __exit__(self, *exc) -> None:
        global _STATE
        _STATE = None


def scripted(dataset_id: str, period: str) -> str:
    """A scripted decisions file holding one real decision the cut-down
    corpus can play: reject the first supply filed to `period`, an hour after
    it arrived."""
    return ("decisions:\n"
            f"  - operation: reject\n    dataset: {dataset_id}\n    period: '{period}'\n"
            "    supply: 0\n    after_hours: 1\n"
            "    reason: \"REQ-GEN-370 c3's test: a played decision under watch.\"\n")


def asset_folder(tmp: Path, *, synthetic: str | None) -> Path:
    """The selected asset's configuration completed from the real folder -
    with a synthetic/ folder of its own (`synthetic` as its
    scripted_decisions.yaml, and the real providers), or with none at all."""
    folder = tmp / ("with-synthetic" if synthetic is not None else "without-synthetic")
    folder.mkdir()
    (folder / "synthetic").mkdir()
    if synthetic is not None:
        (folder / "synthetic" / "scripted_decisions.yaml").write_text(synthetic)
        (folder / "synthetic" / "collections").symlink_to(
            asset_folders.real_folder() / "synthetic" / "collections")
    asset_folders.complete(folder)  # skips the synthetic/ written above
    if synthetic is None:
        (folder / "synthetic").rmdir()
    return folder


def corpus(root: Path, collection_id: str, dataset_id: str, deliveries: int) -> list[dict]:
    """The real generator's output for `collection_id`, written under `root`
    and cut to its first `deliveries` of `dataset_id` - generated before
    anything is watched, since the generator is an allowed reader. Their
    bookkeeping entries, in run order."""
    import generator_isolation
    from generator import driver

    undo = generator_isolation.redirect(root)
    try:
        driver.generate(collection_id)
    finally:
        undo()
    book = json.loads((root / "generator_bookkeeping.json").read_text())
    entries = sorted(book[dataset_id], key=lambda e: e["run_index"])[:deliveries]
    keep = {e["delivery"] for e in entries}
    assert len(keep) == deliveries, "precondition: the generator wrote enough deliveries"
    for tree in ("deliveries", "receipts"):
        for d in (root / tree).iterdir():
            if d.name not in keep:
                shutil.rmtree(d)
    return entries


def tree_copy(tmp: Path, corpus_root: Path) -> Path:
    """A copy of the corpus, so each run writes beside a tree of its own."""
    tree = tmp / "tree"
    for part in ("deliveries", "receipts"):
        shutil.copytree(corpus_root / part, tree / part)
    return tree


def run_and_build(collection_id: str, tree: Path, folder: Path, out: Path,
                  db_name: str) -> dict:
    """The batch pass and the dashboard build, under watch, into a fresh
    database; the snapshot of what it recorded, with what was seen."""
    from cli import dashboard as dash
    from asset_model import assets
    from qa_tools.common import build_output, scripted_decisions

    the_scripts = scripted_decisions.script_path
    seen: dict = {}

    def run():
        from qa_tools.tools import orchestrate

        # THE REAL SCRIPT PATH, NOT THE CORPUS REDIRECT: the read under test
        # is the one the resolver points the Player at.
        scripted_decisions.script_path = the_scripts
        before = assets.use_folder(folder)
        mp = pytest.MonkeyPatch()
        mp.setenv(build_output.OUT_DIR_ENV, str(out))
        try:
            with watching(folder) as state:
                orchestrate.run_pipeline(collection_id, sequential=True)
                dash._rebuild_results()
                dash._build_data()
                dash._embed()
            seen.update(state)
        finally:
            mp.undo()
            assets.restore(before)

    snap = equiv_support.run_into_fresh_database(tree, db_name, run)
    snap["seen"] = seen
    snap["out"] = out
    return snap


def runs(collection_id: str, dataset_id: str, tmp_path_factory, worker_id,
         deliveries: int = 2) -> dict:
    """Both variants: "present" (a synthetic/ folder holding one real scripted
    decision) and "removed" (no synthetic/ folder)."""
    corpus_root = tmp_path_factory.mktemp(f"synthetic_unread_corpus_{dataset_id}")
    entries = corpus(corpus_root, collection_id, dataset_id, deliveries)
    out = {}
    for key, synthetic in (("present", scripted(dataset_id, entries[0]["period"])),
                           ("removed", None)):
        tmp = tmp_path_factory.mktemp(f"synthetic_unread_{key}")
        out[key] = run_and_build(collection_id, tree_copy(tmp, corpus_root),
                                 asset_folder(tmp, synthetic=synthetic), tmp / "out",
                                 f"synthetic_unread_{dataset_id.replace('-', '_')}_{key}_{worker_id}")
    return out


def column(snap: dict, table: str, name: str) -> list:
    """Every value of one column of a snapshot table (each held as JSON text)."""
    names, rows = snap[table]
    return [json.loads(row[names.index(name)]) for row in rows]


class Checks:
    """The tests both asset modules run, on their own `runs` fixture."""

    @pytest.mark.parametrize("variant", ["present", "removed"])
    def test_there_was_a_real_run_to_watch(self, runs, variant):
        """Rule 3: a test that can be empty must show it is not - the delivery
        was filed, all four tools checked it and it was promoted, the page was
        built, and the hook saw the asset folder being read at all."""
        snap = runs[variant]
        assert sum(snap["qa.filing"][1].values()) >= 1
        assert {"dbt", "soda", "datacontract", "evidently"} <= set(
            column(snap, "qa.check_result", "tool"))
        assert "promote" in column(snap, "qa.decision", "action")
        assert (snap["out"] / "qa-reporting-dashboard.html").is_file()
        assert snap["seen"]["asset_reads"] > 0

    def test_the_scripted_decision_was_played_under_watch(self, runs):
        """The Player's non-empty path ran: its one decision is recorded,
        and nothing of the kind without the folder."""
        assert "reject" in column(runs["present"], "qa.decision", "action")
        assert "reject" not in column(runs["removed"], "qa.decision", "action")

    @pytest.mark.parametrize("variant", ["present", "removed"])
    def test_nothing_under_synthetic_was_read(self, runs, variant):
        assert sorted(set(runs[variant]["seen"]["reads"])) == []

    def test_only_the_excused_player_read_the_scripted_decisions_file(self, runs):
        """REQ-GEN-381 criteria 1 and 4 end it - an empty list once it goes."""
        allowed = runs["present"]["seen"]["allowed"]
        assert all(path.endswith(os.path.join("synthetic", "scripted_decisions.yaml"))
                   for _, path in allowed), allowed
        assert runs["removed"]["seen"]["allowed"] == []
