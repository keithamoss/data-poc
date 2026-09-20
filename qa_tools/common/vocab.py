"""
The closed vocabularies this project's own hand-authored files use.

Extracted 2026-09-20 (REQ-DOCS-029) so that `qa_tools/common/schemas.py`
can declare them and the validators can enforce cross-references against
them, without the two importing each other in a circle.

Before this they lived wherever they were first needed - the component
codes in `validate_requirements.py`, the changelog categories in
`dashboard/changelog_yaml.py` - which worked only while nothing else
wanted them. One home means adding a component or a category is one
edit, and `tests/test_component_taxonomy_consistency.py` still checks
that this agrees with the dashboard's own consts and
`docs/components.md`.
"""
from __future__ import annotations

# The 7-part component taxonomy: short CODE used in requirement ids ->
# full name used in changelog tags, the dashboard's consts and
# docs/components.md's section headers. docs/components.md has the full
# write-up of what each one covers; this is the bare mapping.
COMPONENT_CODES: dict[str, str] = {
    "GEN": "Data generation",
    "QAC": "QA checks & contract",
    "PIPE": "Pipeline & publishing",
    "DASH": "Dashboard UI",
    "GHUB": "GitHub workflow & people",
    "TEST": "Testing & dev tooling",
    "DOCS": "Docs & process",
}

MOSCOW: tuple[str, ...] = ("must", "should", "could", "wont")

REQUIREMENT_STATUSES: tuple[str, ...] = ("not_started", "in_progress", "built")

# Plain words rather than Keep a Changelog's Added/Changed/Fixed, which
# read as a spec for a maintainer; these read as a sentence for a
# reader. Closed, because an open vocabulary drifts into six
# near-synonyms within a month.
CHANGELOG_CATEGORIES: tuple[str, ...] = ("New", "Improved", "Fixed")
