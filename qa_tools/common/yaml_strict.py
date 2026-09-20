"""
Finds duplicate mapping keys in a hand-authored YAML file.

PyYAML's `safe_load` accepts a duplicate key silently and keeps the LAST
one. Every other value under that key is discarded with no warning, no
error, and no way to tell from the parsed result that anything was lost.

That is not hypothetical here. On 2026-09-20 `requirements.yaml`'s
REQ-QAC-023 ended up with two `decisions:` blocks - one written when
reasoning was migrated out of `non_functional_requirements`, another
written when the requirement was marked built. Python kept the second
and dropped the first, so five real decisions vanished, including a
rejected design alternative that had been deliberately moved there
BEFORE the plans prose describing it was deleted. The deletion was
justified by the requirement carrying that reasoning. It wasn't.

Nothing in the stack caught it:

  - `yaml.safe_load` accepted it, so both validators passed.
  - The `check-yaml` pre-commit hook uses `safe_load` too, so it passed.
  - The whole Python test suite passed.

It was caught by the JavaScript `yaml` package, which refuses duplicate
keys outright, failing `tests-js/implemented-by.test.js` in CI while
everything local stayed green. A second parser noticing what the first
one silently swallowed is luck, not a strategy - hence this module.

The rule this encodes: a file a human hand-edits, whose whole purpose is
to be the durable record, must not be able to lose content silently. A
duplicate key is always an authoring mistake here - there is no case in
this repo where writing the same key twice is intentional.
"""
from __future__ import annotations

from pathlib import Path

import yaml


def find_duplicate_keys(path: str | Path) -> list[str]:
    """Every duplicated mapping key in `path`, as error strings naming
    the key and the line it was repeated on.

    Walks PyYAML's own node graph rather than the loaded dict, because by
    the time it is a dict the duplicate is already gone - which is the
    entire problem."""
    with open(path) as f:
        root = yaml.compose(f)
    errors: list[str] = []

    def walk(node) -> None:
        if isinstance(node, yaml.MappingNode):
            seen: dict[str, int] = {}
            for key_node, value_node in node.value:
                key = getattr(key_node, "value", None)
                if isinstance(key, str):
                    if key in seen:
                        errors.append(
                            f"{path}: duplicate key {key!r} at line "
                            f"{key_node.start_mark.line + 1} (first seen at line "
                            f"{seen[key]}) - PyYAML keeps only the last one and "
                            f"silently discards everything under the first")
                    else:
                        seen[key] = key_node.start_mark.line + 1
                walk(value_node)
        elif isinstance(node, yaml.SequenceNode):
            for child in node.value:
                walk(child)

    if root is not None:
        walk(root)
    return errors
