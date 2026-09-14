#!/usr/bin/env bash
# End-to-end: generate synthetic runs -> load into DuckDB -> run the four
# real tools (dbt-core, Soda Core, datacontract-cli, Evidently) -> reshape
# for the dashboard -> re-embed real data into the dashboard HTML.
#
# Run this from the repo root. Every step is deterministic (seeded), so
# re-running regenerates byte-for-byte the same runs/results. Requires the
# real tool packages already installed - see requirements-real.txt's own
# two-step install note before running this for the first time.
set -euo pipefail
cd "$(dirname "$0")"

echo "== 1/4: generate + load the combined warehouse (pipeline/orchestrate.py) =="
python3 pipeline/orchestrate.py

echo
echo "== 2/4: run the real tools (real_tools/orchestrate_real.py) =="
python3 real_tools/orchestrate_real.py

echo
echo "== 3/4: reshape results_real.json for the dashboard =="
python3 pipeline/build_dashboard_data.py

echo
echo "== 4/4: re-embed real data into the dashboard HTML =="
python3 dashboard/embed_dashboard_data.py

echo
echo "Done. Open dashboard/qa-reporting-dashboard.html in a browser to view it,"
echo "or inspect reports/results_real.json for the raw check-result records."
