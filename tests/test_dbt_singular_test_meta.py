"""A singular dbt test's meta reaches dbt (post-build-review #305, item 2).

Every collection's singular tests (tests/<collection>/*.sql) are described
in its models/ schema.yml - check_id, names_no_row and the rest. dbt 1.12
applies that block to the test only under the `data_tests:` key; under the
older `tests:` key it reads none of it, so `names_no_row` never reached the
manifest node run_dbt reads, a failing recency check was sampled as rows,
and the run stopped (SampleNotRecordable) - found when the daily asset's
bootstrap stopped at its first stale supply. This parses each asset's REAL
project with dbt itself and compares the manifest against the YAML."""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest
import yaml

import asset_folders

pytestmark = pytest.mark.asset("quarterly")


def _declared(project) -> dict:
    out = {}
    for path in (project / "models").rglob("*.yml"):
        doc = yaml.safe_load(path.read_text()) or {}
        for entry in (doc.get("data_tests") or doc.get("tests") or []):
            meta = ((entry.get("config") or {}).get("meta")) or {}
            out[entry["name"]] = meta
    return out


def _parsed(project, target) -> dict:
    env = {**os.environ, "DBT_RUN_SCHEMA": "x", "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
           "DBT_PG_HOST": "localhost", "DBT_PG_PORT": "5432", "DBT_PG_USER": "x",
           "DBT_PG_PASSWORD": "x", "DBT_PG_DBNAME": "x", "DBT_PG_SCHEMA": "x",
           "DBT_TARGET_PATH": str(target)}
    root = project.parents[2]  # assets/<asset>/dbt -> the repository
    subprocess.run([sys.executable, "-m", "dbt.cli.main", "parse", "--no-partial-parse",
                    "--project-dir", str(project),
                    "--profiles-dir", str(root / "qa_tools" / "dbt_profiles")],
                   env=env, check=True, capture_output=True, text=True)
    manifest = json.loads((target / "manifest.json").read_text())
    return {n["name"]: (n["config"].get("meta") or {}) for n in manifest["nodes"].values()
            if n["resource_type"] == "test" and n.get("test_metadata") is None}


@pytest.mark.parametrize("asset", ["quarterly", "daily"])
def test_every_singular_tests_meta_is_on_its_manifest_node(asset, tmp_path):
    project = asset_folders.real_folder_of(asset) / "dbt"
    declared = _declared(project)
    assert declared, f"{asset} describes no singular test - the comparison would prove nothing"
    parsed = _parsed(project, tmp_path / "target")
    for name, meta in declared.items():
        assert name in parsed, f"{asset}: {name} is described but is not a singular test"
        for key in ("check_id", "names_no_row"):
            if key in meta:
                assert parsed[name].get(key) == meta[key], (asset, name, key, parsed[name].get(key))
