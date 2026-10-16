"""Where a generator writes, and how to send all of it somewhere else
(REQ-GEN-043; moved out of tests/ for REQ-TEST-160).

A generator writes several things, not one: the delivery tree, the
receipts beside it, the shared bookkeeping file, and the scenario
placements - the last hanging off scenario_injection rather than the
generator, which is how it was once missed (see redirect()). They default
to the real ones under data/.

THIS USED TO LIVE IN tests/generator_isolation.py, which still exists and
now re-exports it. It moved because a replay's resume regenerates the
deliveries to compare them with a checkpoint's (REQ-TEST-160 criterion 2),
which is product code and must never touch data/ to do it. One copy, so
the next output a generator gains has one obvious place to be added.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path


def redirect(module, root: Path):
    """Point every one of `module`'s outputs under `root`; returns a restore
    callable (usable from a module-scoped fixture, which cannot depend on
    pytest's function-scoped monkeypatch).

    THE SCENARIO PLACEMENTS ARE REDIRECTED TOO. Both generators call
    `scenario_injection.write_placements()` at the end of a run, and it
    defaults to the REAL data/scenario_placements.json - so a generator
    test once rewrote that file with only the collection it had just
    generated, and a CI half reading it failed with `KeyError: 'TS-4'`.
    """
    from generator import scenario_injection

    root = Path(root)
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


@contextmanager
def generated_into(root: Path):
    """Run BOTH generators, in the order `mothman pipeline bootstrap` does,
    with everything they write under `root`. Both, and in that order,
    because a delivery's NAME depends on what the other generator already
    has on disk (REQ-GEN-043's uniqueness) - generating one collection
    alone could name its deliveries differently from the real tree."""
    from generator import generate_cp_runs, generate_runs

    root = Path(root)
    for module in (generate_runs, generate_cp_runs):
        undo = redirect(module, root)
        try:
            module.main()
        finally:
            undo()
    yield root
