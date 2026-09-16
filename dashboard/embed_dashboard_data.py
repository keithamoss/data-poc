"""
Builds dashboard/qa-reporting-dashboard.html from dashboard/qa-reporting-
dashboard.template.html (2026-09-16, Keith's call - plans/publishing-
and-history.md): reads the committed, hand-edited template, regenerates
the `const REAL_BIRTH_REG_DATA = {...};` and `const REAL_CP_DATA =
{...};` lines from reports/birth_registrations_dashboard.json and
reports/child_protection_dashboard.json (pipeline/build_dashboard_
data.py's/build_cp_dashboard_data.py's output), and writes the result
to the real, viewable HTML - gitignored, never committed, rebuilt fresh
by CI on every push and locally by ./run_pipeline.sh. Run this last,
after orchestrate.py/orchestrate_cp.py and the two build_*_dashboard_
data.py scripts, whenever the pipeline is regenerated.

This only replaces those two lines - the rest of the dashboard (its
CSS, the rendering code, the other 14 illustrative datasets, and the
separate SNAPSHOT_MANIFEST const dashboard/snapshot_dashboard.py owns)
is copied through unchanged from the template.
"""
from __future__ import annotations
import json
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..")
TEMPLATE_HTML = os.path.join(os.path.dirname(__file__), "qa-reporting-dashboard.template.html")
DASHBOARD_HTML = os.path.join(os.path.dirname(__file__), "qa-reporting-dashboard.html")

TARGETS = [
    ("REAL_BIRTH_REG_DATA", os.path.join(ROOT, "reports", "birth_registrations_dashboard.json")),
    ("REAL_CP_DATA", os.path.join(ROOT, "reports", "child_protection_dashboard.json")),
]


def embed() -> None:
    with open(TEMPLATE_HTML) as f:
        html = f.read()

    for const_name, data_json_path in TARGETS:
        with open(data_json_path) as f:
            data = json.load(f)
        real_json = json.dumps(data, separators=(",", ":"))
        new_line = f"const {const_name} = {real_json};\n"

        pattern = re.compile(rf"const {const_name} = .*?;\n")
        # a lambda replacement (not a plain string) so backslash sequences
        # already inside the JSON (e.g. "—") are never reinterpreted as
        # regex backreferences by re.sub
        html, n = pattern.subn(lambda _m: new_line, html, count=1)
        if n != 1:
            raise RuntimeError(
                f"Could not find exactly one 'const {const_name} = ...;' line to replace "
                f"(found {n}) - has the dashboard's structure changed?"
            )
        print(f"Re-embedded {len(real_json)} bytes of real data into {const_name}")

    with open(DASHBOARD_HTML, "w") as f:
        f.write(html)


if __name__ == "__main__":
    embed()
