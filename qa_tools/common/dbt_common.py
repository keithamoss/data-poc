"""
Tool-generic dbt-core invocation and manifest-parsing helpers, shared by
qa_tools/bdm/run_dbt_bdm.py and qa_tools/cp/run_dbt_cp.py.
The actual test-to-dashboard-field mapping (which tests exist, what
dimension/label each one gets, any tool-reliability workarounds a
dataset needed) is genuinely different per dataset and stays in each
dataset's own file - only the subprocess invocation and
manifest.json/run_results.json parsing plumbing that's identical across
datasets lives here. Split out once a second dataset (Child Protection)
confirmed the same ~30-40 lines really were identical, rather than
guessed in advance - see plans/wider.md #20.
"""
from __future__ import annotations
import os
import re
import subprocess

ENGINE_TAG = "dbt-core 1.12 + dbt-duckdb"

_NUM_RE = re.compile(r"([\d.]+)")


def parse_threshold(spec: str | None) -> float | None:
    if spec is None or spec.strip() == "!= 0":
        return None
    m = _NUM_RE.search(spec)
    return float(m.group(1)) if m else None


def run_dbt(db_path: str, command: str, select: list[str], target_path: str,
            profiles_dir: str, project_dir: str, root: str) -> None:
    env = dict(os.environ)
    env["DBT_DB_PATH"] = db_path
    env["DBT_SEND_ANONYMOUS_USAGE_STATS"] = "False"
    subprocess.run(
        # --target-path gives each run its OWN target/ subdirectory rather
        # than dbt's shared default - required for cross-run
        # parallelization (plans/performance.md #4): without this,
        # concurrent `dbt build` calls for different runs clobber each
        # other's manifest.json/run_results.json mid-write. Always applied
        # (not just under parallel execution) since it's strictly safer
        # and free even sequentially - one run's target/ never lingers to
        # confuse the next.
        ["dbt", command, "--profiles-dir", profiles_dir, "--project-dir", project_dir, "--quiet",
         "--target-path", target_path, "--select", *select],
        env=env, cwd=root, check=False, capture_output=True, text=True,
    )


def test_nodes(manifest: dict) -> dict[str, dict]:
    return {
        uid: node for uid, node in manifest["nodes"].items()
        if node.get("resource_type") == "test"
    }
