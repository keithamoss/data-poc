"""Redirecting a generator's output, all of it (REQ-GEN-043).

A generator writes several things, not one: the delivery tree, the
receipts beside it, and the shared bookkeeping file. These used to
default to the real ones under data/, so redirecting a generator's
flat CSV output alone - which is what both generator test modules
did, back when there was one - left a test run deleting and rewriting
the real delivery tree as a side effect.
Deterministic, so the bytes came back identical and nothing noticed; a
run interrupted mid-write would have left it half-deleted.

NEITHER GENERATOR WRITES A FLAT COPY ANY MORE (REQ-PIPE-102):
Child Protection stopped first, Birth Registrations followed, and
with them went the raw directories the copies lived in. What is left
to redirect is the delivery tree, the receipts beside it, and the
shared bookkeeping file. The hasattr() guard below stays, so a
generator legitimately lacking one of these is not an error.

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
    names = {"DELIVERIES_DIR": root / "deliveries",
             "RECEIPTS_DIR": root / "receipts",
             "BOOKKEEPING_PATH": root / "generator_bookkeeping.json"}
    original = {}
    for name, value in names.items():
        if not hasattr(module, name):
            continue
        original[name] = getattr(module, name)
        setattr(module, name, value)

    def restore():
        for name, value in original.items():
            setattr(module, name, value)

    return restore
