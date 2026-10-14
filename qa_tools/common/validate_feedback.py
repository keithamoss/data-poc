"""
Gate for the road-testing feedback cards (REQ-DOCS-219).

Every numbered entry of plans/road-testing.md carries a card - what was
raised, what we heard, what we built, where to see it - and the dashboard's
Feedback tab (REQ-DASH-220) shows them. The card's SHAPE is checked by the
one parser the build uses too (dashboard/plans_md.parse_feedback_cards);
this adds what only committed configuration can answer: that a cited
requirement exists and is not retired, that a cited sprint is on the list,
and that a dashboard link names a route and a dataset the page has.

It reads plans/road-testing.md, requirements.yaml and contract/data-asset.yaml
and nothing else - no database, no data/, no reports/ (NFR 2). What it cannot
check is the authoring rule that matters most on a public page: a card never
names or describes the reviewer (criterion 18). Review holds that.

Run as `mothman dashboard validate-feedback`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

import yaml

from dashboard.plans_md import FEEDBACK_FILE, parse_feedback_cards, road_testing_sprints

ROOT = Path(__file__).resolve().parents[2]
PLANS_DIR = ROOT / "plans"
REQUIREMENTS = ROOT / "requirements.yaml"
DATA_ASSET = ROOT / "contract" / "data-asset.yaml"

_TOP_ROUTES = {"", "plans", "demo", "scenarios", "feedback"}


def _hierarchy(path: Path) -> dict:
    doc = yaml.safe_load(path.read_text()) or {}
    tree = {}
    for ag in (doc.get("hierarchy") or {}).get("agencies") or []:
        tree[ag["id"]] = {col["id"]: {d["id"] for d in col.get("datasets") or []}
                          for col in ag.get("collections") or []}
    return tree


def route_problem(path: str, tree: dict) -> str | None:
    """Why a link's #/... route is not one the dashboard has, or None."""
    parts = [unquote(p) for p in path.split("/") if p]
    if not parts or (len(parts) == 1 and parts[0] in _TOP_ROUTES):
        return None
    if parts[0] != "agency" or len(parts) < 2:
        return f"route '#{path}' is not one the dashboard has"
    agency = parts[1]
    if agency not in tree:
        return f"route '#{path}' names agency {agency!r}, which the hierarchy does not hold"
    if len(parts) == 2:
        return None
    if len(parts) < 6 or parts[2] != "collection" or parts[4] != "dataset":
        return f"route '#{path}' is not one the dashboard has"
    collection, dataset = parts[3], parts[5]
    if collection not in tree[agency]:
        return f"route '#{path}' names collection {collection!r}, which the hierarchy does not hold"
    if dataset not in tree[agency][collection]:
        return f"route '#{path}' names dataset {dataset!r}, which the hierarchy does not hold"
    rest = parts[6:]
    if rest and not (rest[0] == "column" and len(rest) in (2, 4) and (len(rest) == 2 or rest[2] == "check")):
        return f"route '#{path}' is not one the dashboard has"
    return None


def problems(plans_dir: Path = PLANS_DIR, requirements: Path = REQUIREMENTS,
             data_asset: Path = DATA_ASSET) -> tuple[list[dict], list[str]]:
    path = Path(plans_dir) / FEEDBACK_FILE
    cards, errors = parse_feedback_cards(path)
    if not path.is_file():
        return cards, errors
    reqs = {r["id"]: r for r in (yaml.safe_load(Path(requirements).read_text()) or {}).get("requirements", [])}
    sprints = road_testing_sprints(path.read_text())
    tree = _hierarchy(Path(data_asset))
    for card in cards:
        where = f"entry #{card['number']}"
        for item in card["evidence"]:
            if item["kind"] == "req":
                r = reqs.get(item["id"])
                if r is None:
                    errors.append(f"{where}: {item['id']} is not in requirements.yaml")
                elif r.get("status") == "retired":
                    by = ", ".join((r.get("retired") or {}).get("replaced_by") or []) or "its replacement"
                    errors.append(f"{where}: {item['id']} is retired - cite {by} instead")
            elif item["kind"] == "sprint":
                if item["n"] not in sprints:
                    errors.append(f"{where}: sprint {item['n']} is not in the introduction's list of proposed sprints")
            elif item["kind"] == "link" and item["path"]:
                why = route_problem(item["path"], tree)
                if why:
                    errors.append(f"{where}: link {item['label']!r}: {why}")
    return cards, errors


def main() -> int:
    cards, errors = problems()
    if errors:
        print(f"feedback validation FAILED - {len(errors)} problem(s) in plans/{FEEDBACK_FILE}:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(f"feedback validation OK - {len(cards)} card(s), zero errors.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
