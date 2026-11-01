"""The asset resolver (REQ-PIPE-342 criteria 5 to 7, REQ-PIPE-363 criterion 1,
REQ-PIPE-343 criteria 5 and 6, REQ-PIPE-369 criteria 2 and 4): which data
asset a process acts for, where its configuration and state live, and the
adapters and providers loaded from its folder by path.

ON TODAY'S LAYOUT (REQ-TEST-357 criterion 6): contract/ is the one asset,
named data-asset-1 until REQ-QAC-344 renames it, and every path resolves to
where it is today. The assets/<asset>/ layout is exercised against a folder
of the test's own.

READS ONLY ITS OWN REPORTS - none at all: it compares the paths the resolver
names under reports/ and opens nothing there (tests/test_publish.py's marker).
"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from pathlib import Path

import pytest

from qa_tools.common import assets, config_yaml

ROOT = Path(__file__).resolve().parent.parent


def _two_assets(tmp_path: Path) -> Path:
    """An assets/ folder with two asset folders and the one shared file."""
    root = tmp_path / "assets"
    for name in ("quarterly", "daily"):
        (root / name / "collections").mkdir(parents=True)
        (root / name / "data-asset.yaml").write_text(f"data_asset_id: {name}\n")
        (root / name / "collections" / "same_name.py").write_text(f"WHO = {name!r}\n")
    (root / "environments.yaml").write_text("environments: []\n")
    return root


class TestTodaysLayout:
    """contract/ is the one asset, and everything resolves where it is today."""

    def test_the_one_asset_is_named_as_its_file_declares(self):
        declared = config_yaml.parse((ROOT / "contract" / "data-asset.yaml").read_text())
        assert assets.names() == [declared["data_asset_id"]] == ["data-asset-1"]

    def test_every_path_is_where_it_is_today(self, monkeypatch):
        monkeypatch.setenv(assets.ASSET_ENV, "data-asset-1")
        a = assets.selected()
        assert (a.name, a.folder) == ("data-asset-1", ROOT / "contract")
        assert a.file("data-asset.yaml") == ROOT / "contract" / "data-asset.yaml"
        assert a.adapters == ROOT / "qa_tools" / "collections"
        assert a.providers == ROOT / "generator" / "collections"
        assert a.dbt_project == ROOT / "dbt_project"
        assert a.dbt_packages == ROOT / "dbt_project" / "dbt_packages"
        assert assets.data_dir() == ROOT / "data"
        assert assets.reports_dir() == ROOT / "reports"
        assert assets.data_path("deliveries") == ROOT / "data" / "deliveries"
        assert assets.reports_path("x.json") == ROOT / "reports" / "x.json"
        assert assets.deliveries_dir() == ROOT / "data" / "deliveries"
        assert assets.receipts_dir() == ROOT / "data" / "receipts"


class TestSelection:
    """MOTHMAN_ASSET, with no default (REQ-PIPE-363 criteria 1 and 6)."""

    def test_unset_is_refused_naming_the_variable_and_every_folder(self, monkeypatch):
        monkeypatch.delenv(assets.ASSET_ENV, raising=False)
        with pytest.raises(assets.AssetNotSelected) as exc:
            assets.selected()
        message = str(exc.value)
        assert "MOTHMAN_ASSET is not set" in message
        assert "Set it to one of: data-asset-1" in message
        assert "deliberately no default" in message

    def test_a_name_with_no_folder_is_refused_the_same_way(self, monkeypatch):
        monkeypatch.setenv(assets.ASSET_ENV, "data-asset-2")
        with pytest.raises(assets.AssetNotSelected) as exc:
            assets.selected()
        assert "MOTHMAN_ASSET is 'data-asset-2', which names no asset folder" in str(exc.value)
        assert "Set it to one of: data-asset-1" in str(exc.value)

    def test_the_only_asset_present_is_never_chosen_for_you(self, monkeypatch):
        monkeypatch.delenv(assets.ASSET_ENV, raising=False)
        assert len(assets.names()) == 1
        assert assets.selected_or_none() is None

    def test_resolved_at_call_time_not_import_time(self, monkeypatch, tmp_path):
        assets.use_root(_two_assets(tmp_path))
        monkeypatch.setenv(assets.ASSET_ENV, "quarterly")
        assert assets.selected().name == "quarterly"
        monkeypatch.setenv(assets.ASSET_ENV, "daily")
        assert assets.selected().name == "daily"

    def test_select_states_it_for_this_process_and_its_children(self, monkeypatch):
        monkeypatch.delenv(assets.ASSET_ENV, raising=False)
        assert assets.select("data-asset-1").name == "data-asset-1"
        assert os.environ[assets.ASSET_ENV] == "data-asset-1"
        with pytest.raises(assets.AssetNotSelected):
            assets.select("nowhere")


class TestTheAssetsLayout:
    """assets/<asset>/, found from the folder itself (REQ-PIPE-342 criterion 5)."""

    def test_folders_are_discovered_and_files_are_not_assets(self, tmp_path):
        assets.use_root(_two_assets(tmp_path))
        assert assets.names() == ["daily", "quarterly"]

    def test_each_assets_paths_are_its_own(self, monkeypatch, tmp_path):
        root = _two_assets(tmp_path)
        assets.use_root(root)
        monkeypatch.setenv(assets.ASSET_ENV, "daily")
        a = assets.selected()
        assert a.folder == root / "daily"
        assert a.adapters == root / "daily" / "collections"
        assert a.providers == root / "daily" / "synthetic" / "collections"
        assert a.dbt_project == root / "daily" / "dbt"
        assert assets.data_dir() == ROOT / "data" / "daily"
        assert assets.reports_dir() == ROOT / "reports" / "daily"


class TestTheFixture:
    """One fixture points the resolver at an asset folder (REQ-PIPE-342
    criterion 7) - a copy of the selected one with the files a test names."""

    def test_a_named_file_replaces_the_real_one_and_the_rest_stay(self, asset_folder):
        folder = asset_folder({"calendar.yaml": "calendars: []\n"})
        a = assets.selected()
        assert a.folder == folder
        assert a.file("calendar.yaml").read_text() == "calendars: []\n"
        assert a.file("data-asset.yaml").read_text() == \
            (ROOT / "contract" / "data-asset.yaml").read_text()

    def test_the_hierarchy_reads_through_it(self, asset_folder):
        from qa_tools.common import hierarchy

        text = (ROOT / "contract" / "data-asset.yaml").read_text()
        asset_folder({"data-asset.yaml": text.replace("data_asset_id: data-asset-1",
                                                      "data_asset_id: elsewhere")})
        assert hierarchy.data_asset_id() == "elsewhere"


class TestLoadingByPath:
    """REQ-PIPE-369 criterion 2 and REQ-GEN-370 criterion 2."""

    def test_an_adapter_is_loaded_from_its_assets_folder(self):
        from qa_tools import collections

        module = collections.adapter_module("civil-registration")
        assert Path(module.__file__) == ROOT / "qa_tools" / "collections" / "civil_registration.py"
        assert module.__name__ == "mothman_adapter_data_asset_1_civil_registration"
        assert module.__name__ not in {"qa_tools.collections.civil_registration"}
        assert collections.adapter("civil-registration") is module.ADAPTER

    def test_a_provider_is_loaded_from_its_assets_folder(self):
        from generator import collections as providers

        module = providers.provider_module("child-protection")
        assert Path(module.__file__) == ROOT / "generator" / "collections" / "child_protection.py"
        assert module.__name__ == "mothman_provider_data_asset_1_child_protection"
        assert providers.provider("child-protection") is module.PROVIDER

    def test_no_asset_folder_goes_on_sys_path(self):
        from qa_tools import collections

        before = list(sys.path)
        collections.adapter_module("child-protection")
        assert sys.path == before

    def test_an_id_failing_the_pattern_is_refused_before_any_path(self, monkeypatch):
        from qa_tools import collections

        built = []
        monkeypatch.setattr(assets, "load", lambda *a, **k: built.append(a))
        bad = collections.Collection(id="../../etc", name="x", agency_id="a", agency_name="a",
                                     short="x", run_prefix="x", contract="x", datasets=())
        with pytest.raises(collections.UnknownCollectionError):
            collections.adapter_module(bad)
        assert built == []

    def test_two_assets_same_module_name_load_as_two_modules(self, monkeypatch, tmp_path):
        assets.use_root(_two_assets(tmp_path))
        monkeypatch.setenv(assets.ASSET_ENV, "quarterly")
        quarterly = assets.load("adapter", "same_name")
        monkeypatch.setenv(assets.ASSET_ENV, "daily")
        daily = assets.load("adapter", "same_name")
        assert quarterly is not daily
        assert (quarterly.WHO, daily.WHO) == ("quarterly", "daily")
        assert quarterly.__name__ == "mothman_adapter_quarterly_same_name"
        assert daily.__name__ == "mothman_adapter_daily_same_name"

    @pytest.mark.parametrize("bad", ["a_b", "Daily", "a.b", "-a", "a--b"])
    def test_a_folder_name_outside_the_pattern_is_refused(self, tmp_path, bad):
        """Lowercase letters, digits and single hyphens only (groundwork
        critic, post-build-review): 'a-b' and 'a_b' would register one module
        name, and a dot is a module-path separator."""
        root = _two_assets(tmp_path)
        (root / bad).mkdir()
        assets.use_root(root)
        with pytest.raises(assets.BadAssetName) as exc:
            assets.names()
        assert repr(bad) in str(exc.value)

    def test_two_assets_claiming_one_module_name_are_refused(self, monkeypatch, tmp_path):
        """Asset 'x' module 'y_z' and asset 'x-y' module 'z' both make
        mothman_adapter_x_y_z: the second is refused, the first kept."""
        root = tmp_path / "assets"
        (root / "x" / "collections").mkdir(parents=True)
        (root / "x-y" / "collections").mkdir(parents=True)
        (root / "x" / "collections" / "y_z.py").write_text("WHO = 'x'\n")
        (root / "x-y" / "collections" / "z.py").write_text("WHO = 'x-y'\n")
        assets.use_root(root)
        monkeypatch.setenv(assets.ASSET_ENV, "x")
        first = assets.load("adapter", "y_z")
        monkeypatch.setenv(assets.ASSET_ENV, "x-y")
        with pytest.raises(assets.ModuleNameClash) as exc:
            assets.load("adapter", "z")
        assert "mothman_adapter_x_y_z" in str(exc.value)
        assert sys.modules["mothman_adapter_x_y_z"] is first and first.WHO == "x"

    def test_the_same_module_pointed_at_another_file_is_reloaded(self, monkeypatch, tmp_path):
        """Re-pointing one asset's adapter folder (the suite's fixture) is not
        a clash: the same asset, kind and module, from its new file."""
        root = _two_assets(tmp_path)
        assets.use_root(root)
        monkeypatch.setenv(assets.ASSET_ENV, "daily")
        assert assets.load("adapter", "same_name").WHO == "daily"
        other = tmp_path / "other"
        other.mkdir()
        (other / "same_name.py").write_text("WHO = 'moved'\n")
        assets.use_folder(root / "daily", adapters=other)
        assert assets.load("adapter", "same_name").WHO == "moved"

    def test_a_missing_module_says_which_file(self, monkeypatch, tmp_path):
        assets.use_root(_two_assets(tmp_path))
        monkeypatch.setenv(assets.ASSET_ENV, "daily")
        with pytest.raises(assets.NoModule) as exc:
            assets.load("adapter", "absent")
        assert str(tmp_path / "assets" / "daily" / "collections" / "absent.py") in str(exc.value)

    def test_a_spawned_process_loads_from_the_asset_it_is_handed(self, monkeypatch):
        # The parent's own selection is not what the child goes by: it is
        # unset here, and the child is handed the asset and the id.
        monkeypatch.delenv(assets.ASSET_ENV, raising=False)
        with ProcessPoolExecutor(max_workers=1, mp_context=get_context("spawn"),
                                 initializer=assets.select, initargs=("data-asset-1",)) as pool:
            got = pool.submit(assets.adapter_file, "civil-registration").result()
        assert Path(got) == ROOT / "qa_tools" / "collections" / "civil_registration.py"


class TestOneAssetPerProcess:
    """REQ-PIPE-343 criteria 5 and 6."""

    def test_a_second_asset_in_one_test_is_refused(self, monkeypatch, tmp_path):
        assets.use_root(_two_assets(tmp_path))
        assets.claim_for_connection("quarterly")
        assets.claim_for_connection("quarterly")
        with pytest.raises(assets.OneAssetPerProcess) as exc:
            assets.claim_for_connection("daily")
        assert "'quarterly'" in str(exc.value) and "'daily'" in str(exc.value)

    def test_the_suite_starts_each_test_with_no_claim(self):
        # The exemption (criterion 6): a new test may open another asset's
        # database, which the autouse fixture makes so by releasing the
        # claim between tests - never by turning the rule off.
        assert assets.claimed() is None

    def test_a_process_a_test_spawns_does_not_inherit_the_exemption(self):
        """ABLE TO FAIL (groundwork critic): the child must refuse a second
        asset AND accept it once the claim is released - so a rule that never
        refuses fails the first half, and one that always refuses (or a child
        that cannot claim at all) fails the second. The parent holds the
        suite's exemption while it spawns."""
        assets.release_claim()
        with ProcessPoolExecutor(max_workers=1, mp_context=get_context("spawn")) as pool:
            refused, after_release = pool.submit(_claim_two, "data-asset-1",
                                                 "data-asset-2").result()
        assert (refused, after_release) == (True, True)


def _claim_two(first: str, second: str) -> tuple[bool, bool]:
    """(was a second asset refused, was it accepted after an explicit release)."""
    assert assets.claimed() is None
    assets.claim_for_connection(first)
    try:
        assets.claim_for_connection(second)
        refused = False
    except assets.OneAssetPerProcess:
        refused = True
    assets.release_claim()
    assets.claim_for_connection(second)
    return refused, assets.claimed() == second


class TestTheConnectionGuard:
    """Every connection says which asset it is for, before it opens
    (REQ-PIPE-363 criterion 6, REQ-PIPE-343 criterion 5)."""

    def test_no_asset_is_refused_before_any_connection_opens(self, supply_dsn, monkeypatch):
        import psycopg

        from qa_tools.common import supply_db

        monkeypatch.delenv(assets.ASSET_ENV, raising=False)
        opened = []
        monkeypatch.setattr(psycopg, "connect", lambda *a, **k: opened.append(a))
        with pytest.raises(assets.AssetNotSelected):
            supply_db.connect(read_only=True, reuse=False)
        assert opened == []

    def test_a_second_assets_connection_in_one_test_is_refused(self, supply_dsn, monkeypatch,
                                                              tmp_path):
        import psycopg

        from qa_tools.common import supply_db

        supply_db.connect(read_only=True, reuse=False).close()
        assert assets.claimed() == "data-asset-1"
        assets.use_root(_two_assets(tmp_path))
        monkeypatch.setenv(assets.ASSET_ENV, "quarterly")
        opened = []
        monkeypatch.setattr(psycopg, "connect", lambda *a, **k: opened.append(a))
        with pytest.raises(assets.OneAssetPerProcess):
            supply_db.connect(read_only=True, reuse=False)
        assert opened == []


class TestTheBootstrapHandsItsStreamsTheAsset:
    """REQ-PIPE-369 criterion 4: a stream's spawned process is handed the
    asset beside the collection, and selects it itself."""

    def test_each_stream_process_selects_the_asset_it_was_handed(self, monkeypatch):
        from qa_tools.common import bootstrap

        # The parent knows its asset; its environment no longer says so, so
        # a child that merely inherited the environment would know none.
        here = assets.selected()
        monkeypatch.delenv(assets.ASSET_ENV)
        monkeypatch.setattr(assets, "selected", lambda: here)
        monkeypatch.setattr(bootstrap, "_run_stream", _which_asset_and_adapter)
        got = bootstrap._run_concurrently(["civil-registration"], sequential=True)
        assert got == {"civil-registration": (
            "data-asset-1", str(ROOT / "qa_tools" / "collections" / "civil_registration.py"))}


    def test_a_stream_process_is_handed_the_layout_too(self, monkeypatch, tmp_path):
        """The groundwork critic: handed the name alone, a child of a
        use_root deployment (#55) looks for the asset in today's tree."""
        from qa_tools.common import bootstrap

        root = _two_assets(tmp_path)
        assets.use_root(root)
        monkeypatch.setenv(assets.ASSET_ENV, "daily")
        monkeypatch.setattr(bootstrap, "_run_stream", _which_adapter_file)
        got = bootstrap._run_concurrently(["same_name"], sequential=True)
        assert got == {"same_name": str(root / "daily" / "collections" / "same_name.py")}

    def test_a_manifest_worker_is_handed_the_asset_and_layout(self, monkeypatch, tmp_path):
        """parallel_orchestrate's pool hands both explicitly rather than
        relying on fork: forced onto a spawn context, its worker still sees
        the asset and the folder this process points at."""
        import concurrent.futures

        from qa_tools.common import parallel_orchestrate

        folder = tmp_path / "pointed"
        folder.mkdir()
        assets.use_folder(folder)
        real = concurrent.futures.ProcessPoolExecutor
        monkeypatch.setattr(parallel_orchestrate, "ProcessPoolExecutor",
                            lambda **kw: real(mp_context=get_context("spawn"), **kw))
        got = parallel_orchestrate.run_manifest([{"n": 1}, {"n": 2}], _asset_folder_of,
                                                max_workers=1)
        assert got == [("data-asset-1", str(folder))] * 2


def _which_adapter_file(key: str, sequential: bool):
    return str(assets.module_file("adapter", key))


def _asset_folder_of(entry: dict) -> list:
    return [(assets.selected().name, str(assets.selected().folder))]


def _which_asset_and_adapter(key: str, sequential: bool):
    """What a stream process would load - run in the spawned child."""
    return os.environ.get(assets.ASSET_ENV), assets.adapter_file(key)


class TestLoadingIsSafeAcrossThreads:
    """A run's dbt thread and its foreground load the same adapter at once
    (parallel_orchestrate.beside): neither may be handed a module still
    running its own body."""

    def test_a_second_thread_waits_for_the_first_to_finish_loading(self, monkeypatch, tmp_path):
        import threading

        root = _two_assets(tmp_path)
        (root / "daily" / "collections" / "slow.py").write_text(
            "import time\ntime.sleep(0.5)\nDONE = True\n")
        assets.use_root(root)
        monkeypatch.setenv(assets.ASSET_ENV, "daily")
        got = []

        def load():
            got.append(getattr(assets.load("adapter", "slow"), "DONE", False))

        threads = [threading.Thread(target=load) for _ in range(2)]
        threads[0].start()
        import time
        time.sleep(0.1)
        threads[1].start()
        for t in threads:
            t.join()
        assert got == [True, True]
