"""Reading YAML so that a duplicate key is LOUD.

THIS BUG HAS HAPPENED TWICE, which is why it gets a module rather than
a convention. PyYAML's safe_load accepts a repeated mapping key
silently and keeps only the LAST one:

    >>> yaml.safe_load("a: 1\\na: 2")
    {'a': 2}

On 2026-09-20 requirements.yaml's REQ-QAC-023 had two `decisions:`
blocks and five real decisions were discarded with no error, including
a rejected design alternative deliberately moved there before the prose
describing it was deleted. On 2026-09-25 REQ-PIPE-053 gained a second
`unmet_criteria:` block and its original five entries vanished from
every parsed view of the file.

THE SECOND TIME IS THE INSTRUCTIVE ONE. A read-back check ran straight
after the edit - the discipline CLAUDE.md asks for, precisely so an
edit is confirmed rather than assumed - and it printed a healthy
"unmet: 1", because safe_load had already thrown the original away. The
check was not skipped. It was performed, and it lied, because it was
built on the same silent primitive as the bug.

WHY NOT JUST THE LINTER. `.yamllint` enables key-duplicates for exactly
this and it works - it caught both. But a linter catches it at
pre-commit or at the next gate, which is minutes to hours after the
mistake and after whatever was built on top of the wrong value.
Reading is where the loss happens, so reading is where it should fail.

WHY NOT A SCHEMA, verified rather than assumed when this was first hit:
schema validation runs on the already-parsed object, by which point the
duplicate is gone. A required-key rule sees the key present with a
valid, truncated value and passes.

PyYAML HAS NO FLAG FOR THIS - safe_load takes a stream and nothing
else - so a loader subclass is the only in-library route. ruamel.yaml
is strict by default and was rejected as a new dependency plus a
different API for 29 call sites, to fix one behaviour.
"""
from __future__ import annotations

from pathlib import Path

import yaml


class DuplicateKeyError(yaml.YAMLError):
    """A mapping with the same key twice.

    Always names the key and both lines, because the useful question is
    never "is there a duplicate" but "which one did I mean to keep".
    """


class StrictLoader(yaml.SafeLoader):
    """SafeLoader, except that a repeated mapping key is an error.

    Subclasses SafeLoader rather than replacing it: everything else
    about the parse - no arbitrary object construction, no code
    execution - is the behaviour this repo already relies on, and only
    the silent-overwrite is being changed.
    """


def _no_duplicate_keys(loader: StrictLoader, node: yaml.MappingNode, deep: bool = False):
    seen: dict = {}
    for key_node, _value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise DuplicateKeyError(
                f"duplicate key {key!r} in a mapping: first at line "
                f"{seen[key].start_mark.line + 1}, again at line "
                f"{key_node.start_mark.line + 1} of {key_node.start_mark.name}. "
                f"PyYAML would keep only the SECOND and discard the first silently, "
                f"which is how five real decisions were lost once and five unmet "
                f"criteria another time. Merge them into one block.")
        seen[key] = key_node
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


StrictLoader.construct_mapping = _no_duplicate_keys


def load(source: str | Path):
    """Parse YAML from a path or a string, refusing a duplicate key.

    A `Path` is read as text; anything else is treated as YAML source,
    which matches how `yaml.safe_load` is called across this repo and
    keeps this a drop-in replacement.
    """
    text = source.read_text() if isinstance(source, Path) else source
    return yaml.load(text, Loader=StrictLoader)


def load_all(source: str | Path):
    """Every document in a multi-document stream, same strictness."""
    text = source.read_text() if isinstance(source, Path) else source
    return list(yaml.load_all(text, Loader=StrictLoader))
