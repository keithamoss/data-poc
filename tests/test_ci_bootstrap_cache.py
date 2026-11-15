"""CI reuses the bootstrapped database when nothing that shapes it changed
(REQ-TEST-117) - asserted against the real workflow, since the cache only
ever runs on a GitHub runner."""
from __future__ import annotations

import pytest

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"

#: Criterion 1, as amended 2026-10-06 (cli/pipeline.py and nothing else
#: under cli/).
#: The shared inputs; each asset's key adds that asset's own folder
#: (REQ-PIPE-365 criterion 3).
INPUTS = ("generator/**", "synthetic_data_generator/**", "pipeline/**", "qa_tools/**",
          "dbt_shared/**", "cli/pipeline.py", "pyproject.toml", "uv.lock",
          ".github/workflows/test.yml", "assets/environments.yaml")
#: What each asset's cache must carry beside its dump - the generated inputs
#: the tests and the dashboard build read (Keith's 2026-10-06 decision). The
#: placements file is the fifth; it is not named here because this module
#: reads none of them, and test_publish's guard rightly flags any test
#: module that names a generated artefact.
#: Each asset's own, under data/<asset>/ since the asset split, and its own
#: cache since REQ-TEST-353 criterion 1.
CARRIED = ("ci-cache/supply_{a}.dump", "data/{a}/deliveries", "data/{a}/receipts",
           "data/{a}/generator_bookkeeping.json")


def _assets() -> list[str]:
    """Every asset folder, as the workflow's own loops find them."""
    found = sorted(p.name for p in (ROOT / "assets").iterdir()
                   if p.is_dir() and not p.name.startswith((".", "_")))
    assert len(found) >= 2, f"fewer than two asset folders - this checks nothing: {found}"
    return found


def _steps() -> list[dict]:
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    return jobs["test-deployment"]["steps"]


def _named(fragment: str) -> dict:
    [step] = [s for s in _steps() if fragment in s.get("name", "")]
    return step


def _index(fragment: str) -> int:
    return next(i for i, s in enumerate(_steps()) if fragment in s.get("name", ""))


def _restore(asset: str) -> dict:
    return _named(f"Restore the {asset} bootstrap")


def _save(asset: str) -> dict:
    return _named(f"Save the {asset} bootstrap")


class TestTheKey:
    """Criterion 1. The list is held once, in replay_inputs (REQ-TEST-160's
    NFR), and the workflow asks mothman for the key rather than copying the
    list into hashFiles()."""

    def test_it_hashes_every_input_criterion_1_names(self):
        from qa_tools.common import replay_inputs

        assert set(replay_inputs.INPUTS) == set(INPUTS)

    def test_the_workflow_takes_each_assets_key_from_that_list(self):
        """REQ-TEST-353 criterion 1: one key per asset, each from `mothman
        pipeline cache-key` run with that asset selected."""
        run = _named("Key each asset's bootstrap cache")["run"]
        assert "mothman pipeline cache-key" in run and "hashFiles" not in run
        assert 'for asset in $(cd assets && ls -d */ | tr -d /)' in run
        assert 'MOTHMAN_ASSET="$asset" uv run mothman pipeline cache-key' in run
        assert '"${asset}=' in run and "GITHUB_OUTPUT" in run

    def test_no_other_cli_file_is_in_it(self):
        from qa_tools.common import replay_inputs

        assert not [p for p in replay_inputs.input_files()
                    if p.startswith("cli/") and p != "cli/pipeline.py"]

    def test_it_is_computed_before_the_restores_and_after_mothman_exists(self):
        assert _index("Sync dependencies") < _index("Key each asset's bootstrap cache")
        for asset in _assets():
            assert _index("Key each asset's bootstrap cache") < _index(
                f"Restore the {asset} bootstrap"), asset


class TestEachAssetHasACacheOfItsOwn:
    """REQ-TEST-353 criterion 1: each asset's dump and data/<asset>/ paths
    under that asset's own key, so a change to one asset's configuration
    restores the other's cache - and nothing of the other's is in it."""

    def test_every_asset_folder_has_a_restore_and_a_save(self):
        for asset in _assets():
            assert _restore(asset)["uses"].startswith("actions/cache/restore@"), asset
            assert _save(asset)["uses"].startswith("actions/cache/save@"), asset

    def test_each_is_keyed_on_its_own_assets_key(self):
        for asset in _assets():
            for step in (_restore(asset), _save(asset)):
                assert step["with"]["key"] == f"${{{{ steps.key.outputs.{asset} }}}}", asset

    def test_each_holds_its_own_assets_paths_and_no_others(self):
        for asset in _assets():
            def paths(step):
                return set(step["with"]["path"].split())
            restored = paths(_restore(asset))
            assert restored == paths(_save(asset)), asset
            assert {c.format(a=asset) for c in CARRIED} <= restored, asset
            assert len(restored) == len(CARRIED) + 1, asset
            assert all(p == f"ci-cache/supply_{asset}.dump" or p.startswith(f"data/{asset}/")
                       for p in restored), (asset, restored)
            assert not any("*" in p for p in restored), "a wildcard reaches another asset"

    def test_a_save_runs_only_when_its_own_asset_missed(self):
        for asset in _assets():
            assert _save(asset)["if"] == f"steps.cache-{asset}.outputs.cache-hit != 'true'"
            assert _restore(asset)["id"] == f"cache-{asset}"


class TestOnlyAnExactMatchRestores:
    """Criterion 3."""

    def test_there_is_no_partial_key_fallback(self):
        for asset in _assets():
            restore = _restore(asset)
            assert restore["uses"].startswith("actions/cache/restore@")
            assert "restore-keys" not in restore["with"]


class TestAHitRestoresAndAMissRebuilds:
    """Criteria 2 and 5, per asset."""

    RESTORE = "Restore each cached database"

    def test_a_hit_restores_that_assets_dump_before_anything_reads_the_database(self):
        step = _named(self.RESTORE)
        run = step["run"]
        assert "pg_restore" in run and '"ci-cache/supply_${asset}.dump"' in run
        assert '--dbname "supply_${asset}"' in run
        for asset in _assets():
            assert f"{asset}=${{{{ steps.cache-{asset}.outputs.cache-hit }}}}" in step["env"]["HITS"]
        assert _index(self.RESTORE) < _index("Mark each asset's warehouse")
        for asset in _assets():
            assert _index(f"Restore the {asset} bootstrap") < _index(self.RESTORE)

    def test_an_asset_with_no_cache_steps_fails_the_run(self):
        assert "has no cache steps of its own" in _named(self.RESTORE)["run"]

    def test_a_miss_bootstraps_dumps_and_saves_only_the_assets_that_missed(self):
        for name in ("Generate the QA history", "Dump each rebuilt database"):
            assert _named(name)["if"] == "env.REBUILT_ASSETS != ''", name
            assert "for asset in $REBUILT_ASSETS" in _named(name)["run"], name
        assert "REBUILT_ASSETS=" in _named(self.RESTORE)["run"]

    def test_it_never_lives_in_the_repository(self):
        assert "ci-cache/" in (ROOT / ".gitignore").read_text().split()


class TestTheBootstrapsRunSideBySide:
    """REQ-TEST-353 criterion 2: in the one deployment job, each asset its
    own process with its own MOTHMAN_ASSET and DSN, started together rather
    than one after the other - and no second deployment job."""

    def test_each_starts_in_the_background_and_every_one_is_waited_for(self):
        run = _named("Generate the QA history")["run"]
        assert 'MOTHMAN_ASSET="$asset" MOTHMAN_SUPPLY_DSN="${MOTHMAN_PG}/supply_${asset}"' in run
        assert "uv run mothman pipeline bootstrap" in run
        assert ") &" in run and 'pids+=("$!")' in run
        assert 'wait "${pids[$i]}"' in run
        # A failure in either is the step's failure, naming it.
        assert "exit 1" in run and "the bootstrap failed for" in run

    def test_its_output_is_told_apart_by_asset(self):
        assert 'sed -u "s/^/[${asset}] /"' in _named("Generate the QA history")["run"]

    def test_the_side_by_side_bootstrap_runs_as_the_step_would(self, tmp_path):
        """The step's own shell, with `uv run mothman` stood in for: both
        start before either finishes, and a failure in one fails the step
        naming that asset only."""
        import subprocess

        run = _named("Generate the QA history")["run"]
        stub = tmp_path / "uv"
        stub.write_text(
            "#!/usr/bin/env bash\n"
            "echo started \"$MOTHMAN_ASSET\" >> \"$LOG\"\n"
            # Each waits for the other to have started: run one after the
            # other, the first would never see the second and time out.
            "for _ in $(seq 50); do [ \"$(wc -l < \"$LOG\")\" -ge 2 ] && break; sleep 0.1; done\n"
            "[ \"$(wc -l < \"$LOG\")\" -ge 2 ] || { echo alone; exit 3; }\n"
            "[ \"$MOTHMAN_ASSET\" = \"$FAIL\" ] && exit 4\n"
            "echo done\n")
        stub.chmod(0o755)

        def step(fail: str):
            log = tmp_path / f"log-{fail or 'none'}"
            log.write_text("")
            return subprocess.run(
                ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", run],
                env={"PATH": f"{tmp_path}:/usr/bin:/bin", "REBUILT_ASSETS": "quarterly daily",
                     "MOTHMAN_PG": "postgresql://x", "LOG": str(log), "FAIL": fail},
                capture_output=True, text=True, timeout=60)
        ok = step("")
        assert ok.returncode == 0, ok.stdout + ok.stderr
        assert "[quarterly] done" in ok.stdout and "[daily] done" in ok.stdout
        bad = step("daily")
        assert bad.returncode == 1
        assert "the bootstrap failed for: daily" in bad.stdout
        assert "quarterly" not in bad.stdout.split("failed for:", 1)[1]

    def test_there_is_one_deployment_job(self):
        jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
        bootstrapping = [n for n, j in jobs.items()
                         if any("mothman pipeline bootstrap" in s.get("run", "")
                                for s in j.get("steps", []))]
        assert bootstrapping == ["test-deployment"]
        assert "strategy" not in jobs["test-deployment"], "a matrix is a runner per asset"


class TestTheLogSaysWhichItWas:
    """Criterion 4; REQ-TEST-353 criterion 5: per asset."""

    def test_restored_or_rebuilt_and_the_key_for_each_asset(self):
        step = _named("Restore each cached database")
        run = step["run"]
        assert 'echo "${asset}: bootstrap RESTORED from cache key ${key}"' in run
        assert 'echo "${asset}: bootstrap REBUILT - no cache for key ${key}"' in run
        assert step["env"]["KEYS"] == "${{ toJSON(steps.key.outputs) }}"
        assert "for asset in $(cd assets && ls -d */ | tr -d /)" in run

    def test_the_lines_come_out_as_the_step_would_print_them(self, tmp_path):
        """The step's own shell, with pg_restore stood in for: one line per
        asset, restored or rebuilt, each with its own key."""
        import json
        import shutil
        import subprocess

        if shutil.which("jq") is None:
            pytest.fail("jq is not installed - the runner has it; install it here")
        step = _named("Restore each cached database")
        (tmp_path / "pg_restore").write_text("#!/usr/bin/env bash\necho restoring \"$@\" >&2\n")
        (tmp_path / "pg_restore").chmod(0o755)
        env_file = tmp_path / "github-env"
        env_file.write_text("")
        got = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
            env={"PATH": f"{tmp_path}:/usr/bin:/bin", "GITHUB_ENV": str(env_file),
                 "KEYS": json.dumps({a: f"key-of-{a}" for a in _assets()}),
                 "HITS": " ".join(f"{a}={'true' if a == 'quarterly' else ''}"
                                  for a in _assets())})
        assert got.returncode == 0, got.stdout + got.stderr
        lines = got.stdout.splitlines()
        assert "quarterly: bootstrap RESTORED from cache key key-of-quarterly" in lines
        for asset in _assets():
            if asset != "quarterly":
                assert f"{asset}: bootstrap REBUILT - no cache for key key-of-{asset}" in lines
        assert len(lines) == len(_assets())
        rebuilt = env_file.read_text().strip()
        assert rebuilt == "REBUILT_ASSETS=" + " ".join(a for a in _assets() if a != "quarterly")


#: The data asset this module's tests act for, unless a test says otherwise
#: (C11, Keith 2026-11-02: every test module names its asset).
pytestmark = pytest.mark.asset("quarterly")
