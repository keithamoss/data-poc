"""A bootstrap snapshots the delivery tree it is about to replay (REQ-PIPE-430,
signed by Keith 2026-11-14 as speed-anchor v2).

The tree is a real one: Birth Registrations generated once for the module
into a folder of its own, copied for each test that changes it. The bootstrap
is driven through its real entry point with the real tools stubbed out - what
is under test is what the replay's callers of arrivals_for are answered, and
when the tree is recognised from disk.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from asset_model import arrivals, delivery
from bootstrap import bootstrap as boot

pytestmark = pytest.mark.asset("daily")

COLLECTION = "civil-registration"


@pytest.fixture(scope="module")
def generated(daily_history) -> Path:
    """Birth Registrations' history: the suite's shared one (REQ-TEST-402),
    generated once per run, never under data/ - read-only, copied by `tree`."""
    return daily_history.root


@pytest.fixture
def tree(generated, tmp_path, monkeypatch) -> Path:
    """A copy of the generated tree the pipeline's readers default to."""
    root = tmp_path / "tree"
    shutil.copytree(generated / "deliveries", root / "deliveries")
    shutil.copytree(generated / "receipts", root / "receipts")
    monkeypatch.setattr(delivery, "default_deliveries_dir", lambda: root / "deliveries")
    monkeypatch.setattr(delivery, "default_receipts_dir", lambda: root / "receipts")
    return root


@pytest.fixture
def recognitions(monkeypatch) -> list:
    """Every recognition of the tree from disk, by collection."""
    seen = []
    real = arrivals.recognise_arrivals

    def counted(collection_id, *args, **kwargs):
        seen.append(collection_id)
        return real(collection_id, *args, **kwargs)
    monkeypatch.setattr(arrivals, "recognise_arrivals", counted)
    return seen


@pytest.fixture(autouse=True)
def _no_tree_left():
    yield
    held = arrivals.installed_tree()
    if held is not None:
        held.release(check=False)
        pytest.fail("a test left a delivery-tree snapshot installed")


def _remove_one(root: Path) -> str:
    """Take the newest delivery out of the tree; its name."""
    name = sorted(p.name for p in (root / "deliveries").iterdir())[-1]
    shutil.rmtree(root / "deliveries" / name)
    receipt = root / "receipts" / name
    if receipt.is_dir():
        shutil.rmtree(receipt)
    return name


class TestOutsideASnapshotTheTreeIsReadAsItIs:
    """Criterion 4."""

    def test_an_unpinned_call_sees_a_delivery_added_since_the_last(self, tree):
        whole = arrivals.arrivals_for(COLLECTION, "")
        aside = tree / "aside"
        aside.mkdir()
        name = sorted(p.name for p in (tree / "deliveries").iterdir())[-1]
        shutil.move(tree / "deliveries" / name, aside / "d")
        shutil.move(tree / "receipts" / name, aside / "r")
        fewer = arrivals.arrivals_for(COLLECTION, "")
        assert len(fewer) < len(whole)
        shutil.move(aside / "d", tree / "deliveries" / name)
        shutil.move(aside / "r", tree / "receipts" / name)
        assert len(arrivals.arrivals_for(COLLECTION, "")) == len(whole)


class TestInsideASnapshotTheTreeIsRecognisedOnce:
    """Criteria 1 and 5."""

    def test_every_call_is_answered_from_the_snapshot(self, tree, recognitions):
        snapshot = arrivals.TreeSnapshot([COLLECTION]).install()
        try:
            first = arrivals.arrivals_for(COLLECTION, "")
            for _ in range(5):
                assert arrivals.arrivals_for(COLLECTION, "run") == first
            assert arrivals.arrivals_for(COLLECTION, "", tree / "deliveries",
                                         tree / "receipts") == first
        finally:
            assert snapshot.release() == []
        assert recognitions.count(COLLECTION) == 2  # once at install, once to check at release

    def test_other_folders_are_recognised_as_they_are(self, tree, generated, recognitions):
        """A generation reading another collection's tree it has just written
        names its own folders: never answered from a snapshot of others."""
        snapshot = arrivals.TreeSnapshot([COLLECTION]).install()
        try:
            arrivals.arrivals_for(COLLECTION, "", generated / "deliveries",
                                  generated / "receipts")
        finally:
            snapshot.release(check=False)
        assert recognitions.count(COLLECTION) == 2

    def test_a_callers_change_does_not_reach_another_caller(self, tree):
        snapshot = arrivals.TreeSnapshot([COLLECTION]).install()
        try:
            mine = arrivals.arrivals_for(COLLECTION, "")
            dataset = next(iter(mine[0].files_by_dataset))
            mine[0].files_by_dataset[dataset] = ("tampered.csv",)
            mine[0].files_by_dataset["another"] = ("x.csv",)
            theirs = arrivals.arrivals_for(COLLECTION, "")
            assert theirs[0].files_by_dataset[dataset] != ("tampered.csv",)
            assert "another" not in theirs[0].files_by_dataset
        finally:
            snapshot.release(check=False)

    def test_a_change_mid_snapshot_is_found_at_release(self, tree):
        snapshot = arrivals.TreeSnapshot([COLLECTION]).install()
        _remove_one(tree)
        assert snapshot.release() == [COLLECTION]


# ---- through the bootstrap ------------------------------------------------------

@pytest.fixture
def stubbed(tree, monkeypatch):
    """A bootstrap of the daily asset with the real tools out of it: its
    generation and replay replaced by `on_generate` and `on_replay`."""
    import dbsupport
    import one_collection

    # One collection, so the stream pool never spawns: its child processes
    # would not see these stubs and would replay for real (post-build-review #485).
    one_collection.only(monkeypatch, "civil-registration")
    dbsupport.use_empty_supply_db(monkeypatch)
    from qa_tools.common import supply_db

    with supply_db.connect(label="test") as conn:
        supply_db.ensure_schemas(conn)
    calls = {"generate": [], "replay": []}

    def generate(cid, **_k):
        calls["generate"].append(arrivals.installed_tree())
        hook = calls.get("on_generate")
        if hook:
            hook()

    def run_pipeline(collection_id, **_k):
        calls["replay"].append(arrivals.installed_tree())
        hook = calls.get("on_replay")
        if hook:
            hook(collection_id)

    monkeypatch.setattr("bootstrap.generation.generate_collection", generate)
    monkeypatch.setattr("qa_tools.tools.orchestrate.run_pipeline", run_pipeline)
    monkeypatch.setattr(boot, "targets_agree", lambda names: ())
    monkeypatch.setattr("bootstrap.correction_replay.confirm_due", lambda **k: [])
    return calls


class TestABootstrapReplaysFromOneRecognition:

    def test_a_replay_recognises_each_collection_once(self, stubbed, recognitions):
        """Criterion 1: however often the replay asks."""
        def replay(collection_id):
            for _ in range(20):
                arrivals.arrivals_for(collection_id, "")
            before_release = recognitions.count(collection_id)
            stubbed["seen"] = before_release
        stubbed["on_replay"] = replay
        result = boot.bootstrap(collection="all")
        assert result.populated and not result.tree_changes
        assert stubbed["seen"] == 1, "recognised more than once during the replay"

    def test_no_snapshot_is_installed_during_a_generation(self, stubbed):
        """Criterion 1 and REQ-GEN-398 criterion 4."""
        seen_new = []

        def generate():
            # A generation reading back the tree it has just written sees it.
            seen_new.append(len(arrivals.arrivals_for(COLLECTION, "")))
        stubbed["on_generate"] = generate
        boot.bootstrap(collection="all")
        assert stubbed["generate"] == [None]
        assert stubbed["replay"] and all(t is not None for t in stubbed["replay"])
        assert seen_new and seen_new[0] > 0

    def test_a_tree_changed_mid_replay_fails_the_bootstrap(self, stubbed, tree):
        """Criterion 3."""
        stubbed["on_replay"] = lambda _cid: _remove_one(tree)
        result = boot.bootstrap(collection="all")
        assert result.tree_changes
        message = boot.tree_changed_message(result.tree_changes)
        assert "Birth Registrations" in message
        assert str(Path("tree") / "deliveries") in message or "deliveries" in message
        assert "hand filing" in message and "another terminal" in message
        assert "kept but is not to be trusted" in message
        assert "`mothman env reset-synthetic` then `mothman pipeline bootstrap`" in message

    def test_the_cli_exits_non_zero_and_the_tui_does_not_say_ready(self, stubbed, tree,
                                                                    monkeypatch):
        from click.testing import CliRunner

        from cli import app, common, pipeline

        stubbed["on_replay"] = lambda _cid: _remove_one(tree)
        done = CliRunner().invoke(pipeline.bootstrap_command, [])
        assert done.exit_code != 0
        assert "delivery tree changed" in done.output

        # The TUI's menu, on a fresh empty database.
        import dbsupport

        dbsupport.use_empty_supply_db(monkeypatch)
        from qa_tools.common import supply_db

        with supply_db.connect(label="test") as conn:
            supply_db.ensure_schemas(conn)
        stubbed["on_replay"] = lambda _cid: _remove_one(tree)
        monkeypatch.setattr(common, "confirm", lambda *a, **k: True)
        said = []
        monkeypatch.setattr(app.console, "print",
                            lambda text="", *a, style=None, **k: said.append(str(text)))
        app._bootstrap_menu()
        assert any("delivery tree changed" in s for s in said)
        assert not any(s.startswith("Ready") for s in said)
