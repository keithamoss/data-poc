#!/usr/bin/env bash
# End-to-end: generate synthetic runs -> load into DuckDB -> run the four
# real tools (dbt-core, Soda Core, datacontract-cli, Evidently) -> reshape
# for the dashboard -> re-embed real data into the dashboard HTML -> (opt-
# in) archive a "time travel" snapshot of the fully-rendered dashboard.
#
# Run this from the repo root. Every step is deterministic (seeded), so
# re-running regenerates byte-for-byte the same runs/results. Requires the
# real tool packages already installed - run `uv sync --dev` first (see
# pyproject.toml/README.md).
#
# Every step below runs through `uv run` rather than a bare `python3` -
# this script doesn't assume you've activated .venv yourself, or that
# whatever `python3` happens to be first on PATH is the right one. That
# matters here specifically: this repo gets handed to other people to run
# on their own machines (see README's "Development" section) - `uv sync
# --dev` + `./run_pipeline.sh` should be the entire setup, with nothing
# implicit about shell state in between.
set -euo pipefail
cd "$(dirname "$0")"

echo "== 1/4: generate + load the combined warehouse (pipeline/orchestrate.py) =="
uv run python3 -m pipeline.orchestrate

echo
echo "== 2/4: run the real tools (qa_tools/bdm/orchestrate_bdm.py) =="
uv run python3 -m qa_tools.bdm.orchestrate_bdm

echo
echo "== 3/4: reshape results_bdm.json for the dashboard =="
uv run python3 -m pipeline.build_dashboard_data

echo
echo "== 4/5: re-embed real data into the dashboard HTML =="
uv run python3 dashboard/embed_dashboard_data.py

echo
echo "== 5/5: archive a dashboard snapshot ('time travel' - plans/wider.md) =="
# Off by default (SNAPSHOT_DASHBOARD unset) - this script doubles as both
# "a real scheduled data refresh" and "a developer iterating on code", and
# only the former should ever get archived. Pass SNAPSHOT_DASHBOARD=1 to
# take one: SNAPSHOT_DASHBOARD=1 ./run_pipeline.sh
uv run python3 dashboard/snapshot_dashboard.py

echo
echo "Done. Open dashboard/qa-reporting-dashboard.html in a browser to view it,"
echo "or inspect reports/results_bdm.json for the raw check-result records."
