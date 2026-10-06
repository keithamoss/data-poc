"""Redirecting a generator's output, all of it (REQ-GEN-043) - now
generator/output.py's, re-exported here so every test keeps its import.

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

from generator.output import redirect  # noqa: F401 - the one copy, re-exported
