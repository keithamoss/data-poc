"""
Compares reports/results.json (the four Python equivalents in engines/)
against reports/results_real.json (the four real tools in real_tools/),
run_id by run_id, and writes a plain-text summary to reports/comparison.txt
- HANDOFF.md step 4: "Compare real-tool output against the existing
equivalents' results... Where they don't agree, investigate before
assuming either one is wrong."

Pairs records on (run_id, column_name, a normalized check family - sex
validity / facility nulls / row count / drift PSI), not on exact
check_name text, since each real tool's own naming doesn't match its
equivalent's by design (they're independently-built tools, not the same
code twice).
"""
from __future__ import annotations
import json
import os

ROOT = os.path.join(os.path.dirname(__file__), "..")
EQUIV_PATH = os.path.join(ROOT, "reports", "results.json")
REAL_PATH = os.path.join(ROOT, "reports", "results_real.json")
OUT_PATH = os.path.join(ROOT, "reports", "comparison.txt")


def _family(r: dict) -> str | None:
    engine, check = r["engine"], r["check_name"]
    if r["column_name"] == "sex" and "recent" not in check.replace("_", "") and "[recent]" not in check and "24h" not in check:
        if any(k in check for k in ("invalid_percent", "invalid_count", "accepted_values", "validValues")):
            return "sex_unscoped"
    if r["column_name"] == "sex" and ("[recent]" in check or "24h" in check):
        return "sex_recent_scoped"
    if r["column_name"] == "sex" and check.startswith("drift:"):
        return "sex_drift_psi"
    if r["column_name"] == "place_of_birth_facility" and any(
        k in check for k in ("missing_percent", "missing_count", "not_null")
    ):
        return "facility_nulls"
    if r["column_name"] == "(table)" and "row_count" in check.lower().replace("rowcount", "row_count"):
        return "row_count"
    return None


def _engine_family(engine: str) -> str:
    if "dbt" in engine.lower():
        return "dbt"
    if "soda" in engine.lower():
        return "soda"
    if "datacontract" in engine.lower() or "contract_engine" in engine.lower():
        return "datacontract"
    if "evidently" in engine.lower() or "drift" in engine.lower():
        return "evidently"
    return "?"


def build_comparison() -> str:
    with open(EQUIV_PATH) as f:
        equiv = json.load(f)["results"]
    with open(REAL_PATH) as f:
        real = json.load(f)["results"]

    lines = []
    lines.append("Real tool vs. equivalent engine - per-run comparison")
    lines.append("=" * 60)
    lines.append("")

    manifest = {m["run_id"]: m for m in json.load(open(EQUIV_PATH))["runs"]}
    for run_id in sorted(manifest, key=lambda r: manifest[r]["run_date"]):
        severity = manifest[run_id]["dirty_severity"] or "clean"
        lines.append(f"{run_id}  [{severity}]")

        by_key_equiv: dict[tuple, list] = {}
        by_key_real: dict[tuple, list] = {}
        for r in equiv:
            if r["run_id"] != run_id:
                continue
            fam = _family(r)
            if fam:
                by_key_equiv.setdefault((fam, _engine_family(r["engine"])), []).append(r)
        for r in real:
            if r["run_id"] != run_id:
                continue
            fam = _family(r)
            if fam:
                by_key_real.setdefault((fam, _engine_family(r["engine"])), []).append(r)

        keys = sorted(set(by_key_equiv) | set(by_key_real))
        for fam, eng in keys:
            e = by_key_equiv.get((fam, eng), [])
            rr = by_key_real.get((fam, eng), [])
            e_desc = ", ".join(f"{x['status']}({x['metric_value']}{x['unit']})" for x in e) or "-"
            r_desc = ", ".join(f"{x['status']}({x['metric_value']}{x['unit']})" for x in rr) or "-"
            flag = "" if e_desc == r_desc else "  <-- differs"
            lines.append(f"  {fam:20s} [{eng:12s}] equiv: {e_desc:22s} real: {r_desc}{flag}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    text = build_comparison()
    with open(OUT_PATH, "w") as f:
        f.write(text)
    print(text)
