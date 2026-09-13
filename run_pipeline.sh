#!/usr/bin/env bash
# End-to-end: generate synthetic runs -> load into DuckDB -> run all four
# equivalent check engines -> aggregate results.json -> reshape for the
# dashboard -> re-embed real data into the dashboard HTML.
#
# Run this from the repo root. Every step is deterministic (seeded), so
# re-running regenerates byte-for-byte the same runs/results.
set -euo pipefail
cd "$(dirname "$0")"

echo "== 1/3: generate + load + run engines (pipeline/orchestrate.py) =="
python3 pipeline/orchestrate.py

echo
echo "== 2/3: reshape results.json for the dashboard =="
python3 pipeline/build_dashboard_data.py

echo
echo "== 3/3: re-embed real data into the dashboard HTML =="
python3 dashboard/embed_dashboard_data.py

echo
echo "Done. Open dashboard/qa-reporting-dashboard.html in a browser to view it,"
echo "or inspect reports/results.json for the raw check-result records."
