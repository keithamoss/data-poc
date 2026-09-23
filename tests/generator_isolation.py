"""Redirecting a generator's output, all of it (REQ-GEN-043).

A generator writes FOUR things now, not one: its extracted CSVs, the
delivery tree, the receipts beside it, and the shared bookkeeping file.
Three of those defaulted to the real ones under data/, so redirecting
OUT_DIR alone - which is what both generator test modules did - left a
test run deleting and rewriting the real delivery tree as a side
effect. Deterministic, so the bytes came back identical and nothing
noticed; a run interrupted mid-write would have left it half-deleted.

Kept in one place so the next output added has one obvious place to be
added to, and so the two generator modules cannot drift apart on it.
"""
from __future__ import annotations

from pathlib import Path


def redirect(module, root: Path):
    """Point every one of `module`'s outputs under `root`.

    Returns a restore callable. Used from a module-scoped fixture,
    which cannot depend on pytest's function-scoped monkeypatch - hence
    the manual save/restore rather than setattr.
    """
    names = {"OUT_DIR": str(root / "raw"),
             "DELIVERIES_DIR": root / "deliveries",
             "RECEIPTS_DIR": root / "receipts",
             "BOOKKEEPING_PATH": root / "generator_bookkeeping.json"}
    original = {}
    for name, value in names.items():
        original[name] = getattr(module, name)
        setattr(module, name, value)

    def restore():
        for name, value in original.items():
            setattr(module, name, value)

    return restore
