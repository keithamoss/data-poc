"""CI reuses the bootstrapped database when nothing that shapes it changed
(REQ-TEST-117) - asserted against the real workflow, since the cache only
ever runs on a GitHub runner."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"

#: Criterion 1, as amended 2026-10-06 (cli/pipeline.py and nothing else
#: under cli/).
INPUTS = ("generator/**", "synthetic_data_generator/**", "pipeline/**", "qa_tools/**",
          "contract/**", "dbt_project/**", "cli/pipeline.py", "pyproject.toml", "uv.lock",
          ".github/workflows/test.yml")
#: What the cache must carry beside the dump - the generated inputs the
#: tests and the dashboard build read (Keith's 2026-10-06 decision). The
#: placements file is the fifth; it is not named here because this module
#: reads none of them, and test_publish's guard rightly flags any test
#: module that names a generated artefact.
CARRIED = {"ci-cache", "data/deliveries", "data/receipts", "data/generator_bookkeeping.json"}


def _steps() -> list[dict]:
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    return jobs["test-deployment"]["steps"]


def _named(fragment: str) -> dict:
    [step] = [s for s in _steps() if fragment in s.get("name", "")]
    return step


def _index(fragment: str) -> int:
    return next(i for i, s in enumerate(_steps()) if fragment in s.get("name", ""))


class TestTheKey:
    """Criterion 1. The list is held once, in replay_inputs (REQ-TEST-160's
    NFR), and the workflow asks mothman for the key rather than copying the
    list into hashFiles()."""

    def test_it_hashes_every_input_criterion_1_names(self):
        from qa_tools.common import replay_inputs

        assert set(replay_inputs.INPUTS) == set(INPUTS)

    def test_the_workflow_takes_the_key_from_that_list(self):
        run = _named("Key the bootstrap cache")["run"]
        assert "mothman pipeline cache-key" in run and "hashFiles" not in run

    def test_no_other_cli_file_is_in_it(self):
        from qa_tools.common import replay_inputs

        assert not [p for p in replay_inputs.input_files()
                    if p.startswith("cli/") and p != "cli/pipeline.py"]

    def test_it_is_computed_before_the_restore_and_after_mothman_exists(self):
        assert _index("Sync dependencies") < _index("Key the bootstrap cache")
        assert _index("Key the bootstrap cache") < _index("Restore the bootstrapped database")


class TestOnlyAnExactMatchRestores:
    """Criterion 3."""

    def test_there_is_no_partial_key_fallback(self):
        restore = _named("Restore the bootstrapped database")
        assert restore["uses"].startswith("actions/cache/restore@")
        assert "restore-keys" not in restore["with"]


class TestAHitRestoresAndAMissRebuilds:
    """Criteria 2 and 5."""

    def test_a_hit_restores_the_dump_before_anything_reads_the_database(self):
        step = _named("Restore the cached database")
        assert step["if"] == "steps.cache.outputs.cache-hit == 'true'"
        assert "pg_restore" in step["run"]
        assert _index("Restore the cached database") < _index("Mark the warehouse")

    def test_a_miss_bootstraps_dumps_and_saves(self):
        miss = "steps.cache.outputs.cache-hit != 'true'"
        for name in ("Generate the QA history", "Dump the bootstrapped database",
                     "Save the bootstrapped database"):
            assert _named(name)["if"] == miss, name
        assert _named("Save the bootstrapped database")["uses"].startswith("actions/cache/save@")

    def test_restore_and_save_hold_the_same_things(self):
        def paths(name):
            return set(_named(name)["with"]["path"].split())
        restored = paths("Restore the bootstrapped database")
        assert restored == paths("Save the bootstrapped database")
        assert CARRIED <= restored and len(restored) == len(CARRIED) + 1
        assert all(p == "ci-cache" or p.startswith("data/") for p in restored), (
            "the cache holds generated data only (criterion 5)")

    def test_it_never_lives_in_the_repository(self):
        assert "ci-cache/" in (ROOT / ".gitignore").read_text().split()


class TestTheLogSaysWhichItWas:
    """Criterion 4."""

    def test_restored_or_rebuilt_and_the_key(self):
        run = _named("Say whether the database was restored or rebuilt")["run"]
        assert "RESTORED" in run and "REBUILT" in run
        assert "steps.key.outputs.key" in run
