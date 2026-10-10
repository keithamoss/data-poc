"""
Parses the repo's own hand-maintained requirements.yaml (item 75,
plans/qa-pipeline.md) - real user stories tracked with MoSCoW priority,
implementation status, and real linked tests.

This module does almost no interpretation of its own. requirements.yaml's
own shape already IS the shape the dashboard renders, so this loads it,
validates it against the declared schema in qa_tools/common/schemas.py,
and hands back a plain list of dicts in the file's own top-to-bottom
order (never re-sorted here - that order is the intended reading order).

**It raises on a file that does not match the schema** (2026-09-20,
Keith's own call - "I don't mind if the parsers would choke and throw an
error"). Until then it carried its own `_DEFAULTS` dict and filled in
whatever was missing, so a half-written file still rendered. Two reasons
that changed:

  - A requirement missing its `story` rendered as a requirement whose
    story is the empty string, which a reader cannot tell apart from a
    requirement that genuinely has nothing to say. Failing the build is
    the more honest of the two.
  - `_DEFAULTS` was a second, hand-maintained statement of the file's
    shape sitting next to the real one. The schema now says it once.

The schema/linkage CI gate (qa_tools/common/validate_requirements.py)
still exists and still does the heavier work - AST-verifying every
`linked_tests`/`implemented_by` symbol, resolving `dependencies`. It
reads the raw YAML itself rather than going through this module, so it
can report EVERY problem in one run instead of stopping at the first.

See requirements.yaml's own top-of-file comment for the full schema.
"""
from __future__ import annotations
from pathlib import Path

import yaml

from qa_tools.common.schemas import Requirement


def parse_requirements(path: str | Path) -> list[dict]:
    """Returns a list of requirement dicts, each carrying every field
    the schema declares (defaulted where the file legitimately omits an
    optional one), in the file's own order.

    Raises pydantic's ValidationError if the file does not match the
    schema - see this module's own docstring for why that is preferred
    to rendering something half-formed."""
    with open(path) as f:
        doc = yaml.safe_load(f) or {}
    return [Requirement(**(r or {})).model_dump()
            for r in (doc.get("requirements") or [])]
