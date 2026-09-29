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

    THE SCENARIO PLACEMENTS ARE REDIRECTED TOO, and they are the reason
    this docstring's promise about "one obvious place" had to be kept
    rather than admired. Both generators call
    `scenario_injection.write_placements()` at the end of a run, and it
    defaults to the REAL data/scenario_placements.json - so a generator
    test rewrote that file with only the collection it had just
    generated. Nothing noticed while the bootstrap ran before every
    test: it overwrote the partial file with a complete one. Splitting
    CI left the fast half reading whatever a test had last written, and
    `test_a_shared_placement_is_recorded_under_both_scenarios` failed
    with `KeyError: 'TS-4'` - a Child Protection scenario missing from a
    file a Birth Registrations test had just truncated.

    IT HANGS OFF A DIFFERENT MODULE from the other three, which is why
    it was missed: the others are attributes of the generator being
    redirected, and this one belongs to `scenario_injection`.
    """
    from generator import scenario_injection

    names = {"DELIVERIES_DIR": root / "deliveries",
             "RECEIPTS_DIR": root / "receipts",
             "BOOKKEEPING_PATH": root / "generator_bookkeeping.json"}
    original = {}
    for name, value in names.items():
        if not hasattr(module, name):
            continue
        original[name] = getattr(module, name)
        setattr(module, name, value)

    placements = scenario_injection.PLACEMENTS_PATH
    scenario_injection.PLACEMENTS_PATH = root / "scenario_placements.json"

    def restore():
        for name, value in original.items():
            setattr(module, name, value)
        scenario_injection.PLACEMENTS_PATH = placements

    return restore
