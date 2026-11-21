"""An asset's configuration pinned for one synthetic run (REQ-PIPE-397), and
a generation run under it (REQ-GEN-398), both signed by Keith 2026-11-14 as
speed-anchor v2.

Each test drives the real reading code - config_yaml, the agreement, the
hierarchy, the generator's driver - against files it edits, and asserts what
a reader is answered, never how the pin stores it.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import asset_folders
from asset_model import agreement, asset_time, config_pin, config_yaml, hierarchy

pytestmark = pytest.mark.asset("quarterly")

ROOT = Path(__file__).resolve().parent.parent

#: Same-length substitutions, so an edit keeps the file's size.
EXPECTED = ('expected_time: "09:00"', 'expected_time: "10:00"')
DATASET_NAME = ("Client Register", "Client RegisteR")


def edit_in_place(path: Path, old: str, new: str) -> None:
    """Replace `old` with `new` (same length), modification time put back."""
    assert len(old) == len(new)
    before = os.stat(path)
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} is not in {path}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))


def _first_expected_time() -> str:
    return agreement.current().resolved_versions("cp-clients")[0].expected_time


def _client_name() -> str:
    return hierarchy.dataset("cp-clients").dataset_name


@pytest.fixture
def folder(tmp_path) -> Path:
    """A copy of the selected asset's folder whose calendar.yaml and
    data-asset.yaml are real files of the test's own, the rest linked."""
    pointed = tmp_path / "pointed"
    pointed.mkdir()
    real = asset_folders.real_folder()
    for name in ("calendar.yaml", "data-asset.yaml"):
        (pointed / name).write_text((real / name).read_text(encoding="utf-8"),
                                    encoding="utf-8")
    asset_folders.point(pointed)
    return pointed


@pytest.fixture(autouse=True)
def _no_pin_left():
    yield
    held = config_pin.installed()
    if held is not None:
        held.release()
        pytest.fail("a test left a configuration pin installed")


class TestAPinHoldsTheConfigurationStill:
    """Criteria 1, 6 and 2."""

    def test_a_value_read_inside_a_pin_is_unchanged_after_its_file_is_edited(self, folder):
        assert _first_expected_time() == "09:00"
        with config_pin.ConfigSnapshot.take():
            edit_in_place(folder / "calendar.yaml", *EXPECTED)
            assert _first_expected_time() == "09:00"
            edit_in_place(folder / "data-asset.yaml", *DATASET_NAME)
            assert _client_name() == DATASET_NAME[0]

    def test_the_edit_is_seen_after_release(self, folder):
        with config_pin.ConfigSnapshot.take():
            edit_in_place(folder / "calendar.yaml", *EXPECTED)
        assert _first_expected_time() == "10:00"

    def test_a_read_outside_any_pin_sees_an_edit_keeping_size_and_time(self, folder):
        """REQ-PIPE-254 criterion 2 still holds once a pin is released."""
        with config_pin.ConfigSnapshot.take():
            pass
        before = os.stat(folder / "data-asset.yaml")
        edit_in_place(folder / "data-asset.yaml", *DATASET_NAME)
        after = os.stat(folder / "data-asset.yaml")
        assert (after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns)
        assert _client_name() == DATASET_NAME[1]

    def test_a_file_reached_by_another_spelling_is_the_same_entry(self, folder):
        """Keyed on the resolved path: a linked file read through the link."""
        linked = next(p for p in folder.iterdir() if p.is_symlink() and p.is_dir())
        file = next(p for p in linked.rglob("*.yaml"))
        with config_pin.ConfigSnapshot.take() as snapshot:
            assert config_yaml.read(file) == snapshot.texts[os.path.realpath(file)]
            assert config_yaml.read(file.resolve()) == config_yaml.read(file)

    def test_load_hands_each_caller_its_own_copy_inside_a_pin(self, folder):
        """Criterion 10."""
        with config_pin.ConfigSnapshot.take():
            first = config_yaml.load(folder / "calendar.yaml")
            first["mutated"] = True
            assert "mutated" not in config_yaml.load(folder / "calendar.yaml")

    def test_pinned_reads_are_reentrant_and_released_however_the_block_ends(self, folder):
        with pytest.raises(RuntimeError, match="boom"):
            with config_pin.pinned() as outer:
                with config_pin.pinned() as inner:
                    assert inner is outer
                raise RuntimeError("boom")
        assert config_pin.installed() is None

    def test_the_digest_names_the_contents_taken(self, folder):
        """Criterion 13."""
        one = config_pin.ConfigSnapshot.take()
        assert one == config_pin.ConfigSnapshot.take()
        edit_in_place(folder / "calendar.yaml", *EXPECTED)
        assert one != config_pin.ConfigSnapshot.take()
        assert len(one.short) == 12


class TestThePinAnswersTheReadersBuiltOnConfigYaml:
    """Criterion 7, and REQ-PIPE-401's deferred half: a reader that reads
    through config_yaml - here the Linkage Products set-member checks, which
    parse three dbt schema files on every call - reads no file inside a pin."""

    def test_the_set_member_checks_read_no_schema_file_inside_a_pin(self, monkeypatch):
        from asset_model import set_member_checks

        outside = set_member_checks.declared()
        assert outside, "precondition - the quarterly asset declares set-member checks"
        read = []
        real = config_yaml.read_from_disk
        monkeypatch.setattr(config_yaml, "read_from_disk",
                            lambda p: read.append(str(p)) or real(p))
        with config_pin.ConfigSnapshot.take():
            read.clear()
            inside = set_member_checks.declared()
        assert inside == outside
        assert not [p for p in read if p.endswith((".yml", ".yaml"))], read


class TestAFileThatCannotBeReadIsNotRemembered:
    """Criterion 9."""

    def test_an_unreadable_file_raises_on_every_read_and_reads_once_fixed(self, folder):
        broken = folder / "people.yaml"
        if broken.exists() or broken.is_symlink():
            broken.unlink()
        broken.mkdir()  # a directory where a file should be: open succeeds, read fails
        with config_pin.ConfigSnapshot.take():
            for _ in range(2):
                with pytest.raises(OSError):
                    config_yaml.read(broken)
            broken.rmdir()
            broken.write_text("people: []\n")
            assert config_yaml.read(broken) == "people: []\n"


class TestAStagedCorrectionSitsOnThePin:
    """Criterion 5: inside a pin, a staged correction's agreement and zones
    answer for the span of its context, the pin everything else."""

    def test_the_staged_agreement_answers_within_its_context_only(self, folder):
        from qa_tools.common import correction_trial

        cal_doc = config_yaml.load(folder / "calendar.yaml")
        asset_doc = config_yaml.load(folder / "data-asset.yaml")
        staged_text = config_yaml.read(folder / "calendar.yaml").replace(*EXPECTED, 1)
        staged_cal = config_yaml.parse(staged_text)
        assert cal_doc != staged_cal
        staged_zone = json.loads(json.dumps(asset_doc))
        staged_zone["timezone"]["versions"][0]["zone"] = "Australia/Eucla"
        with config_pin.ConfigSnapshot.take():
            edit_in_place(folder / "data-asset.yaml", *DATASET_NAME)
            with correction_trial.configured(staged_cal, staged_zone):
                assert _first_expected_time() == "10:00"
                assert asset_time.timezone_versions()[0].zone.key == "Australia/Eucla"
                # Everything else from the pin: the hierarchy as pinned.
                assert _client_name() == DATASET_NAME[0]
            assert _first_expected_time() == "09:00"
            assert asset_time.timezone_versions()[0].zone.key == "Australia/Perth"


_REFUSAL_PROBE = textwrap.dedent("""
    import sys
    sys.modules["bootstrap"] = None   # the bootstrap package cannot be imported
    from pathlib import Path
    from asset_model import assets, config_pin
    assets.use_folder(Path(sys.argv[1]))
    try:
        config_pin.ConfigSnapshot.take().install()
    except config_pin.PinRefused as exc:
        print("REFUSED", exc)
    else:
        print("INSTALLED")
    try:
        import bootstrap.bootstrap  # noqa: F401
        print("BOOTSTRAP-IMPORTED")
    except ImportError:
        print("NO-BOOTSTRAP")
""")


class TestARealAssetIsNeverPinned:
    """Criterion 3: refused on an asset that does not declare itself
    synthetic, with the bootstrap package absent."""

    def test_refused_naming_the_asset_and_its_file(self, folder):
        path = folder / "data-asset.yaml"
        path.write_text(path.read_text(encoding="utf-8").replace("synthetic: true",
                                                                 "synthetic: false"))
        done = subprocess.run([sys.executable, "-c", _REFUSAL_PROBE, str(folder)],
                              cwd=ROOT, capture_output=True, text=True,
                              env={**os.environ, "MOTHMAN_ASSET": "quarterly"})
        out = done.stdout
        assert "NO-BOOTSTRAP" in out, done.stderr
        assert "REFUSED" in out, out + done.stderr
        assert "'quarterly'" in out and "data-asset.yaml" in out
        assert "INSTALLED" not in out

    def test_a_synthetic_asset_is_pinned(self, folder):
        done = subprocess.run([sys.executable, "-c", _REFUSAL_PROBE, str(folder)],
                              cwd=ROOT, capture_output=True, text=True,
                              env={**os.environ, "MOTHMAN_ASSET": "quarterly"})
        assert "INSTALLED" in done.stdout, done.stdout + done.stderr


def _handed(_ignored=None):
    """What a spawned process holds after the one hand-off."""
    held = config_pin.installed()
    return None if held is None else held.digest


class TestEveryProcessIsHandedTheSnapshot:
    """Criterion 12."""

    def test_a_spawned_process_holds_the_parents_snapshot(self, folder):
        import multiprocessing
        from concurrent.futures import ProcessPoolExecutor

        from asset_model import assets

        with config_pin.ConfigSnapshot.take() as snapshot:
            # An edit after the pin is taken never reaches a started process.
            edit_in_place(folder / "calendar.yaml", *EXPECTED)
            with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context(
                    "spawn"), initializer=assets.adopt, initargs=assets.handoff()) as pool:
                assert pool.submit(_handed).result() == snapshot.digest

    def test_a_snapshot_whose_contents_do_not_match_its_digest_is_refused(self, folder):
        snapshot = config_pin.ConfigSnapshot.take()
        forged = config_pin.ConfigSnapshot(snapshot.asset, {**snapshot.texts, "/x.yaml": ""},
                                           digest=snapshot.digest)
        with pytest.raises(config_pin.PinMismatch, match="hand-off"):
            config_pin.adopt(forged)
        assert config_pin.installed() is None

    def test_the_target_trial_pool_uses_the_one_hand_off(self):
        """No pool carries an initializer of its own (criterion 12): the
        target trial's pool once handed the asset's name alone. READS SOURCE:
        an architecture rule (one hand-off for every pool) with no behaviour a
        test can observe short of running a trial's real tools in a pool."""
        source = (ROOT / "cli" / "target_trial.py").read_text()
        assert "initializer=assets.adopt" in source
        assert "initializer=assets.select" not in source


# ---- the QA tools read their own files (criterion 11) ---------------------------

@pytest.mark.asset("daily")
class TestAToolsOwnFilesAreNotPinned:
    """A dbt schema file edited inside a pin reaches dbt, which reads its
    project itself."""

    def test_a_dbt_model_edited_inside_a_pin_reaches_dbt(self, tmp_path):
        import shutil

        from qa_tools.common import dbt_common
        from qa_tools.tools import run_dbt
        from asset_model import assets

        real = assets.selected().dbt_project
        # THE SAME DEPTH AS THE REAL PROJECT, so its relative macro and test
        # paths (../../../dbt_shared) still resolve.
        project = tmp_path / "a" / "b" / "dbt"
        shutil.copytree(real, project, ignore=shutil.ignore_patterns(
            "dbt_packages", "logs", "target"), symlinks=True)
        (project / "dbt_packages").symlink_to(real / "dbt_packages")
        (tmp_path / "a" / "dbt_shared").symlink_to(ROOT / "dbt_shared")
        schema = project / "models" / "civil-registration" / "schema.yml"
        old, new = "name: Multiple-birth sibling match", "name: Multiple-birth sibling matcH"

        def meta_names() -> set[str]:
            nodes = dbt_common.parsed_test_nodes(run_dbt.PROFILES_DIR, str(project))
            return {str((n.get("config") or {}).get("meta", {}).get("name"))
                    for n in nodes.values()}

        with config_pin.pinned():
            assert old.split(": ", 1)[1] in meta_names()
            # AN ORDINARY EDIT, its modification time moved: dbt's own partial
            # parse skips a file whose time has not moved, which is dbt's
            # behaviour and nothing of the pin's.
            schema.write_text(schema.read_text(encoding="utf-8").replace(old, new, 1),
                              encoding="utf-8")
            stat = schema.stat()
            os.utime(schema, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
            assert new.split(": ", 1)[1] in meta_names(), \
                "dbt did not read its own schema file as edited mid-pin"


# ---- a pinned generation (REQ-PIPE-397 criterion 15, REQ-GEN-398) ---------------

_AUDITED_GENERATION = textwrap.dedent("""
    import json, os, sys, tempfile, warnings
    warnings.simplefilter("ignore")
    from generator import driver, output
    from asset_model import config_pin

    root = tempfile.mkdtemp()
    output.redirect(root)
    snapshot = config_pin.ConfigSnapshot.take()
    watched = set(snapshot.texts)
    tools = ("/dbt/", "/soda/", "/datacontract/", "/evidently/")
    hits, active = [], [False]

    def hook(event, args):
        if not active[0] or event != "open":
            return
        path = args[0]
        if not isinstance(path, (str, bytes, os.PathLike)):
            return
        real = os.path.realpath(os.fsdecode(path))
        if real not in watched:
            return
        frames, frame = [], sys._getframe(1)
        while frame is not None:
            frames.append(frame.f_code.co_filename)
            frame = frame.f_back
        # A QA TOOL'S OWN READ IS ALLOWED (SA Q4): only mothman's frames count.
        if any(t in f and "site-packages" in f for f in frames for t in tools):
            return
        hits.append((real, frames[1:4]))

    sys.addaudithook(hook)
    import contextlib, io
    with snapshot, contextlib.redirect_stdout(io.StringIO()):
        active[0] = True
        driver.generate(sys.argv[1])
        active[0] = False
    print(json.dumps({"files": len(watched), "hits": hits[:20], "count": len(hits)}))
""")


@pytest.mark.asset("daily")
class TestAPinnedGenerationOpensNoConfigurationFile:
    """Criterion 15's audit-hook test: a pinned generation of a test asset
    opens no file of the snapshot set from a mothman frame. ITS SUBJECT IS
    GENERATION ITSELF, so it generates (REQ-TEST-402 criterion 7)."""

    def test_no_snapshot_file_is_opened(self):
        done = subprocess.run([sys.executable, "-c", _AUDITED_GENERATION,
                               "civil-registration"], cwd=ROOT, capture_output=True,
                              text=True, env={**os.environ, "MOTHMAN_ASSET": "daily"},
                              timeout=600)
        assert done.returncode == 0, done.stderr[-3000:]
        found = json.loads(done.stdout.strip().splitlines()[-1])
        assert found["files"] > 5
        assert found["count"] == 0, found["hits"]


@pytest.mark.asset("daily")
class TestAGenerationReadsItsConfigurationOnce:
    """REQ-GEN-398 criterion 5: a configuration file edited while a generation
    runs leaves that generation's output unchanged, and the next generation
    reads the edit. ITS SUBJECT IS GENERATION ITSELF, so it generates
    (REQ-TEST-402 criterion 7)."""

    def test_an_edit_mid_generation_waits_for_the_next(self, tmp_path):
        from generator import collections as providers
        from generator import driver, output

        provider = providers.provider("civil-registration")
        real = asset_folders.real_folder()
        pointed = tmp_path / "pointed"
        pointed.mkdir()
        (pointed / "calendar.yaml").write_text(
            (real / "calendar.yaml").read_text(encoding="utf-8"), encoding="utf-8")
        asset_folders.point(pointed)
        calendar = pointed / "calendar.yaml"
        when = ('expected_time: "22:00"', 'expected_time: "21:00"')

        def generated(into: Path) -> dict:
            undo = output.redirect(into)
            try:
                driver.generate("civil-registration")
            finally:
                undo()
            return {p.relative_to(into).as_posix(): p.read_bytes()
                    for p in (into / "receipts").rglob("*") if p.is_file()}

        clean = generated(tmp_path / "clean")
        # AN EDIT MADE PART-WAY, from inside the generation: once its provider
        # has planned the history, which reads the calendar.
        original_plan = provider.plan
        edited = []

        def plan_then_edit():
            out = original_plan()
            if not edited:
                edit_in_place(calendar, *when)
                edited.append(True)
            return out

        provider.plan = plan_then_edit
        try:
            during = generated(tmp_path / "during")
        finally:
            provider.plan = original_plan
        assert edited, "the edit was never made"
        assert during == clean, "an edit made mid-generation reached that generation"
        after = generated(tmp_path / "after")
        assert after != clean, "the next generation did not read the edit"


def test_a_bare_generate_command_says_how_long_it_took():
    """REQ-GEN-398 criterion 3: one line, its own."""
    from bootstrap import generation

    assert generation.took_line(12.4) == "Took generation 12s."


@pytest.fixture
def opened(monkeypatch):
    """Every file opened from here on, by any of the three ways Python opens
    one - for a test that a reader opens no snapshot file inside a pin."""
    import builtins
    import io

    seen: list[str] = []
    real_io, real_os = io.open, os.open

    def watching_io(file, *a, **k):
        seen.append(os.path.realpath(os.fsdecode(file)) if isinstance(
            file, (str, bytes, os.PathLike)) else repr(file))
        return real_io(file, *a, **k)

    def watching_os(file, *a, **k):
        seen.append(os.path.realpath(os.fsdecode(file)))
        return real_os(file, *a, **k)

    monkeypatch.setattr(io, "open", watching_io)
    monkeypatch.setattr(builtins, "open", watching_io)
    monkeypatch.setattr(os, "open", watching_os)
    return seen


class TestEveryReaderInsideARunIsPinned:
    """post-build-review #394: four readers reached during a pinned run read
    their file themselves - the scripted corrections, the check-lifecycle
    sources (through collect_checks, which tables_read and the re-checks
    call), Soda's check file as handed to Soda, and the synthetic reset's
    asset id - so a pin missed them in silence."""

    @pytest.mark.parametrize("reader", ["scripted corrections", "check sources",
                                        "soda checks", "synthetic reset"])
    def test_it_opens_no_snapshot_file(self, reader, opened):
        from asset_model import collections

        def read():
            if reader == "scripted corrections":
                from bootstrap import scripted_corrections
                return scripted_corrections.load()
            if reader == "check sources":
                from qa_tools.common import validate_check_lifecycle
                return validate_check_lifecycle._sources(None)
            if reader == "soda checks":
                from qa_tools.common import soda_common
                path = ROOT / collections.check_files("soda")[0]
                return soda_common.readable_checks_yaml(str(path), {"x"})
            from bootstrap import synthetic_reset
            return synthetic_reset.asset_id()

        with config_pin.ConfigSnapshot.take() as snapshot:
            opened.clear()
            read()
            read_in_pin = [p for p in opened if p in snapshot.texts]
        assert read_in_pin == [], read_in_pin
