"""
Regenerates the `const REAL_BIRTH_REG_DATA = {...};` line inside
qa-reporting-dashboard.html from reports/birth_registrations_dashboard.json
- the step that turns pipeline/build_dashboard_data.py's output into what
the dashboard actually renders. Run this last, after orchestrate.py and
build_dashboard_data.py, whenever the pipeline is regenerated (see
run_pipeline.sh at the repo root, which chains all four).

This only replaces that one line - the rest of the dashboard (its CSS, the
rendering code, and the other 14 illustrative datasets) is untouched.
"""
from __future__ import annotations
import json
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..")
DASHBOARD_HTML = os.path.join(os.path.dirname(__file__), "qa-reporting-dashboard.html")
DATA_JSON = os.path.join(ROOT, "reports", "birth_registrations_dashboard.json")

PATTERN = re.compile(r"const REAL_BIRTH_REG_DATA = .*?;\n")


def embed() -> None:
    with open(DATA_JSON) as f:
        data = json.load(f)
    real_json = json.dumps(data, separators=(",", ":"))
    new_line = f"const REAL_BIRTH_REG_DATA = {real_json};\n"

    with open(DASHBOARD_HTML) as f:
        html = f.read()

    # a lambda replacement (not a plain string) so backslash sequences
    # already inside the JSON (e.g. "—") are never reinterpreted as
    # regex backreferences by re.sub
    new_html, n = PATTERN.subn(lambda _m: new_line, html, count=1)
    if n != 1:
        raise RuntimeError(
            "Could not find exactly one 'const REAL_BIRTH_REG_DATA = ...;' line to replace "
            f"(found {n}) - has the dashboard's structure changed?"
        )

    with open(DASHBOARD_HTML, "w") as f:
        f.write(new_html)
    print(f"Re-embedded {len(real_json)} bytes of real data into {DASHBOARD_HTML}")


if __name__ == "__main__":
    embed()
