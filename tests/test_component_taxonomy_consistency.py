"""Real CI guard against the 7-part component taxonomy drifting between
its 3 independently hand-maintained representations - Keith's own
question, 2026-09-19 ("how will we ensure components.md is kept in
sync with the components present in the UI"): before this, nothing
cross-checked them, and `qa_tools/common/validate_requirements.py`'s
own `_COMPONENT_CODES` comment said as much ("keep this dict and those
two consts in sync by hand... nothing currently cross-checks them").

The 3 representations:
  1. `qa_tools/common/validate_requirements.py`'s `_COMPONENT_CODES` -
     the single source of truth for the short CODE used in real
     requirement ids (imported directly, real code, not a fixture).
  2. `dashboard/qa-reporting-dashboard.template.html`'s own
     `COMPONENT_ICON`/`PLANS_ALL_COMPONENTS` consts - what the Plans
     tab and Release Notes panel actually render (parsed from the real
     template file's source text via regex, not executed - this repo's
     own `tests-js/` already covers the template's runtime JS behaviour,
     this test only checks the literal taxonomy values agree, so a
     plain Python regex read is enough and keeps this in the same
     toolchain as the other 2 representations).
  3. `docs/components.md`'s own `## \\`CODE\\` — Full Name` section
     headers - the human/agent-facing write-up.

If any of the 3 ever disagree (a new component added to one but not
the others, a typo, a renamed component), this fails loudly rather than
silently drifting - the same "structurally impossible to drift, not
just remembered" treatment this project already gives other
multi-representation data (e.g. the dashboard build-output split)."""
from __future__ import annotations

import re
from pathlib import Path

from qa_tools.common.validate_requirements import _COMPONENT_CODES

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "dashboard" / "qa-reporting-dashboard.template.html"
COMPONENTS_MD = ROOT / "docs" / "components.md"


def _component_icon_names() -> set[str]:
    text = TEMPLATE.read_text()
    m = re.search(r"const COMPONENT_ICON = \{(.*?)\};", text, re.DOTALL)
    assert m, "COMPONENT_ICON const not found in the real template - has it been renamed/moved?"
    return set(re.findall(r'"([^"]+)":\s*"', m.group(1)))


def _plans_all_components_names() -> set[str]:
    text = TEMPLATE.read_text()
    m = re.search(r"const PLANS_ALL_COMPONENTS = \[(.*?)\];", text, re.DOTALL)
    assert m, "PLANS_ALL_COMPONENTS const not found in the real template - has it been renamed/moved?"
    return set(re.findall(r'"([^"]+)"', m.group(1)))


def _components_md_entries() -> dict[str, str]:
    """Returns {code: full_name} parsed from docs/components.md's own
    real `## \\`CODE\\` — Full Name` section headers."""
    text = COMPONENTS_MD.read_text()
    pairs = re.findall(r"^## `([A-Z]+)` — (.+)$", text, re.MULTILINE)
    assert pairs, "No `## `CODE` — Full Name` headers found in docs/components.md - has its format changed?"
    return dict(pairs)


def test_component_icon_names_match_the_real_component_codes():
    assert _component_icon_names() == set(_COMPONENT_CODES.values())


def test_plans_all_components_names_match_the_real_component_codes():
    assert _plans_all_components_names() == set(_COMPONENT_CODES.values())


def test_components_md_entries_match_the_real_component_codes_exactly():
    assert _components_md_entries() == _COMPONENT_CODES
