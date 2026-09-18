"""
Parses the repo's own hand-maintained requirements.yaml (item 75,
plans/qa-pipeline.md) - real user stories tracked with MoSCoW priority,
implementation status, and (enforced by qa_tools/common/
validate_requirements.py, not this module) real linked tests. Keith's
own scoping call: structured YAML with typed fields, not hand-prose
like CHANGELOG.md - so unlike dashboard/changelog_md.py, this module
does almost no interpretation of its own; requirements.yaml's own shape
already IS the shape the dashboard renders, this just loads it and
normalizes it into a stable, predictable list (never raising on a
missing optional field - that's validate_requirements.py's job, run as
its own separate CI gate, not this module's).

See requirements.yaml's own top-of-file comment for the full schema.
"""
from __future__ import annotations
from pathlib import Path

import yaml

# Fields every requirement is expected to carry - missing ones default
# rather than error here, since THIS module's job is "render whatever
# is really there," not enforce the schema (that's validate_
# requirements.py, run as its own CI gate against the same file).
_DEFAULTS = {
    "id": "",
    "title": "",
    "story": "",
    "moscow": "could",
    "status": "not_started",
    "acceptance_criteria": [],
    "linked_tests": [],
}


def parse_requirements(path: str | Path) -> list[dict]:
    """Returns a list of requirement dicts, each with every _DEFAULTS
    key present (defaulted if the file didn't set it), in the file's
    own top-to-bottom order (never re-sorted here - the file's own
    order is the intended reading/display order)."""
    with open(path) as f:
        doc = yaml.safe_load(f) or {}
    raw = doc.get("requirements") or []
    out = []
    for r in raw:
        entry = dict(_DEFAULTS)
        entry.update(r or {})
        # requirements.yaml's own `story` uses YAML's `>` folded-scalar
        # style for readability in the source file - collapses to one
        # line with a single trailing newline; strip it so the
        # rendered/embedded text doesn't carry that trailing newline
        # through into the dashboard.
        if isinstance(entry["story"], str):
            entry["story"] = entry["story"].strip()
        out.append(entry)
    return out
