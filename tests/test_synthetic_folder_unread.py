"""Staging, the checks, the gate, promotion and the dashboard build read
nothing under an asset's synthetic/ folder (REQ-GEN-370 criterion 3).

HOW IT IS SHOWN: a Python audit hook watches every file opened and every
folder listed while one real Birth Registrations delivery tree is put through
the pipeline's batch pass (`orchestrate.run_pipeline`: staged as it arrives,
the four real tools, the arrival gate and promotion) into an empty database
of its own, and the dashboard is then built from what was recorded
(rebuild-results, build-data, embed, as `mothman dashboard rebuild` runs
them). An audit hook sees an open however it is made - open(), Path.read_text,
io.open_code for a module loaded by path - so a reader cannot route around it
the way it could around a patched function.

TWICE: with the asset's synthetic/ folder present, holding a scripted
decisions file of its own and the real providers, and with it removed. The
second is the case a real deployment is in once it deletes the folder; it
overlaps REQ-PIPE-385 criterion 1, which owns the whole of that case (the
generator, scenarios/ and the bootstrap unimportable, every gate, and the
synthetic commands refused) - this test shows only what criterion 3 names.

ONE KNOWN READ, OWNED ELSEWHERE: the batch pass builds a scripted-decision
Player for every collection it runs (qa_tools/tools/orchestrate.py's _begin),
and the Player reads the asset's synthetic/scripted_decisions.yaml. REQ-GEN-381
criterion 1 moves the Player into bootstrap/ and criterion 4 forbids the
pipeline importing it, which ends the read. Until then that one read is
allowed here BY WHO MADE IT - the Player's own constructor on the stack - so
any other read of the folder, by any other code, still fails; and the test
stays green when the read goes, rather than going red because work succeeded.
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
PLAYER = (os.path.join("qa_tools", "common", "scripted_decisions.py"), "Player.__init__")

#: What the hook is watching for, or None when it is not watching. A hook
#: cannot be removed once added, so it is added once per process and does
#: nothing outside a `watching()` block.
_STATE: dict | None = None
_HOOKED = False


def _by_the_player() -> bool:
    frame = sys._getframe(2)
    while frame is not None:
        code = frame.f_code
        if code.co_filename.endswith(PLAYER[0]) and code.co_qualname == PLAYER[1]:
            return True
        frame = frame.f_back
    return False


def _hook(event: str, args) -> None:
    state = _STATE
    if state is None or event not in ("open", "os.listdir", "os.scandir", "glob.glob"):
        return
    target = args[0] if args else None
    if isinstance(target, bytes):
        target = os.fsdecode(target)
    if not isinstance(target, (str, os.PathLike)):
        return
    try:
        path = os.path.realpath(os.fspath(target))
    except (TypeError, ValueError):
        return
    for root in state["roots"]:
        if path == root or path.startswith(root + os.sep):
            if _by_the_player():
                state["allowed"].append((event, path))
            else:
                state["reads"].append((event, path, _who()))
            return
    if any(path.startswith(folder + os.sep) for folder in state["asset"]):
        state["asset_reads"] += 1


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
    folder while inside, in seen["reads"] (or seen["allowed"], made by the
    Player), and how many reads of the asset folder there were at all."""

    def __init__(self, asset_folder: Path):
        self.asset_folder = Path(asset_folder)

    def __enter__(self) -> dict:
        global _STATE, _HOOKED
        if not _HOOKED:
            sys.addaudithook(_hook)
            _HOOKED = True
        self.state = {
            # The folder and the real one its entries link to.
            "asset": (os.path.realpath(self.asset_folder),
                      os.path.realpath(asset_folders.real_folder())),
            "roots": (os.path.realpath(self.asset_folder / "synthetic"),) + REAL_SYNTHETIC,
            "reads": [], "allowed": [], "asset_reads": 0}
        _STATE = self.state
        return self.state

    def __exit__(self, *exc) -> None:
        global _STATE
        _STATE = None


def _asset_folder(tmp: Path, *, synthetic: bool) -> Path:
    """The daily asset's configuration completed from the real folder - with a
    synthetic/ folder of its own (a scripted decisions file declaring none,
    and the real providers), or with none at all."""
    folder = tmp / ("with-synthetic" if synthetic else "without-synthetic")
    folder.mkdir()
    if synthetic:
        own = folder / "synthetic"
        own.mkdir()
        (own / "scripted_decisions.yaml").write_text("decisions: []\n")
        (own / "collections").symlink_to(asset_folders.real_folder() / "synthetic" / "collections")
    else:
        # Not linked in by complete(): a placeholder it skips, removed after.
        (folder / "synthetic").mkdir()
    asset_folders.complete(folder)
    if not synthetic:
        (folder / "synthetic").rmdir()
    return folder


#: How many of the generated history's first deliveries are run: the first
#: fills its open slot and is promoted, the second is checked against it.
DELIVERIES = 2


@pytest.fixture(scope="module")
def corpus(tmp_path_factory) -> Path:
    """The real Birth Registrations generator's output, cut to its first
    DELIVERIES deliveries (tests/test_kept_routes_agree.py's corpus) -
    generated before anything is watched, since the generator is an allowed
    reader."""

    import generator_isolation
    from generator import driver

    root = tmp_path_factory.mktemp("synthetic_unread_corpus")
    undo = generator_isolation.redirect(root)
    try:
        driver.generate("civil-registration")
    finally:
        undo()
    book = json.loads((root / "generator_bookkeeping.json").read_text())
    entries = sorted(book["birth-registrations"], key=lambda e: e["run_id"])
    keep = {e["delivery"] for e in entries[:DELIVERIES]}
    assert len(keep) == DELIVERIES, "precondition: the generator wrote enough deliveries"
    for tree in ("deliveries", "receipts"):
        for d in (root / tree).iterdir():
            if d.name not in keep:
                shutil.rmtree(d)
    return root


def _tree(tmp: Path, corpus: Path) -> Path:
    """A copy of the corpus, so each run writes its reports and observations
    beside a tree of its own."""
    tree = tmp / "tree"
    for part in ("deliveries", "receipts"):
        shutil.copytree(corpus / part, tree / part)
    return tree


def _run_and_build(tree: Path, asset_folder: Path, out: Path, db_name: str) -> dict:
    """The batch pass and the dashboard build, under watch, into a fresh
    database; the snapshot of what it recorded, with what was seen."""
    from cli import dashboard as dash
    from qa_tools.common import assets, build_output, scripted_decisions

    the_scripts = scripted_decisions.script_path
    seen: dict = {}

    def run():
        from qa_tools.tools import orchestrate

        # THE REAL SCRIPT PATH, NOT THE CORPUS REDIRECT: the read under test
        # is the one the resolver points the Player at.
        scripted_decisions.script_path = the_scripts
        before = assets.use_folder(asset_folder)
        mp = pytest.MonkeyPatch()
        mp.setenv(build_output.OUT_DIR_ENV, str(out))
        try:
            with watching(asset_folder) as state:
                orchestrate.run_pipeline("civil-registration", sequential=True)
                dash._rebuild_results()
                dash._build_data()
                dash._embed()
            seen.update(state)
        finally:
            mp.undo()
            assets.restore(before)

    snap = equiv_support.run_into_fresh_database(tree, db_name, run)
    snap["seen"] = seen
    return snap


@pytest.fixture(scope="module")
def runs(corpus, tmp_path_factory, worker_id):
    out = {}
    for synthetic in (True, False):
        tmp = tmp_path_factory.mktemp("synthetic_unread")
        key = "present" if synthetic else "removed"
        out[key] = _run_and_build(_tree(tmp, corpus), _asset_folder(tmp, synthetic=synthetic),
                                  tmp / "out", f"synthetic_unread_{key}_{worker_id}")
        out[key]["out"] = tmp / "out"
    return out


def _decisions(snap: dict) -> list:
    names, rows = snap["qa.decision"]
    return [dict(zip(names, row)) for row in rows]


@pytest.mark.parametrize("variant", ["present", "removed"])
class TestTheRealPipelineReadsNothingThere:

    def test_there_was_a_real_run_to_watch(self, runs, variant):
        """Rule 3: a test that can be empty must show it is not - the delivery
        was filed, checked and decided on, the page was built, and the hook
        saw the asset folder being read at all."""
        snap = runs[variant]
        assert sum(snap["qa.filing"][1].values()) >= 1
        assert sum(snap["qa.check_result"][1].values()) > 10
        names, rows = snap["qa.check_result"]
        # The snapshot holds each value as its JSON text.
        tools = {json.loads(row[names.index("tool")]) for row in rows}
        assert {"dbt", "soda", "datacontract", "evidently"} <= tools, tools
        actions = {json.loads(d["action"]) for d in _decisions(snap)}
        assert "promote" in actions, actions
        assert (runs[variant]["out"] / "qa-reporting-dashboard.html").is_file()
        assert snap["seen"]["asset_reads"] > 0

    def test_nothing_under_synthetic_was_read(self, runs, variant):
        assert sorted(set(runs[variant]["seen"]["reads"])) == []


class TestTheOneReadOwnedElsewhere:

    def test_only_the_player_reads_the_scripted_decisions_file_and_only_that(self, runs):
        """REQ-GEN-381 criteria 1 and 4 end it. Allowed only as that file,
        only from the Player's constructor - an empty list once it goes."""
        allowed = runs["present"]["seen"]["allowed"]
        assert all(path.endswith(os.path.join("synthetic", "scripted_decisions.yaml"))
                   for _, path in allowed), allowed
        assert runs["removed"]["seen"]["allowed"] == []


#: The data asset this module's tests act for (C11, Keith 2026-11-02).
pytestmark = pytest.mark.asset("daily")
