"""Replace a generated file whole or not at all.

A report other processes read - reports/results_*.json, the dashboard JSON -
used to be written by truncating it and streaming into it, so a reader in
another process could parse half a file. That is exactly what CI on d6dce26
did (2026-10-11): one xdist worker read reports/results_cpfs_child-protection.json while
another worker's dashboard build was rewriting it. Writing to a temporary
file beside it and renaming it into place gives every reader the old file
or the new one, because a rename within one directory is atomic.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def write_json(path, obj, **dump_kwargs) -> None:
    """Write `obj` as JSON to `path`, replacing it in one step. Leaves the
    previous file untouched, and no temporary file behind, if anything
    fails part-way."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_kwargs.setdefault("indent", 2)
    dump_kwargs.setdefault("default", str)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, **dump_kwargs)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
