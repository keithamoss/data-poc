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


def redirect(root: Path):
    """Point every generator output under `root`; returns a restore callable
    (usable from a module-scoped fixture, which cannot depend on pytest's
    function-scoped monkeypatch).

    ONE PLACE SINCE REQ-GEN-246: every collection writes through the shared
    driver, so redirecting generator/driver.py's three paths redirects every
    provider's at once - there is no per-collection module left to miss.

    THE SCENARIO PLACEMENTS ARE REDIRECTED TOO. The driver calls
    `scenario_injection.write_placements()` at the end of a run, and it
    defaults to the REAL data/scenario_placements.json - so a generator
    test once rewrote that file with only the collection it had just
    generated, and a CI half reading it failed with `KeyError: 'TS-4'`.
    """
    from generator import driver, scenario_injection

    root = Path(root)
    names = {"DELIVERIES_DIR": root / "deliveries",
             "RECEIPTS_DIR": root / "receipts",
             "BOOKKEEPING_PATH": root / "generator_bookkeeping.json"}
    original = {name: getattr(driver, name) for name in names}
    for name, value in names.items():
        setattr(driver, name, value)

    placements = scenario_injection.PLACEMENTS_PATH
    scenario_injection.PLACEMENTS_PATH = root / "scenario_placements.json"

    def restore():
        for name, value in original.items():
            setattr(driver, name, value)
        scenario_injection.PLACEMENTS_PATH = placements

    return restore


@contextmanager
def generated_into(root: Path):
    """Run EVERY collection's generator, in hierarchy order - the order
    `mothman pipeline bootstrap` generates them in - with everything they
    write under `root`. Every one, and in that order, because a delivery's
    NAME depends on what the other collections already have on disk
    (REQ-GEN-043's uniqueness) - generating one collection alone could name
    its deliveries differently from the real tree.

    THROUGH THE REGISTRY (REQ-GEN-246 criterion 8): the collections are the
    ones with a provider, never a list written here."""
    from generator import collections, driver

    root = Path(root)
    undo = redirect(root)
    try:
        for provider in collections.providers():
            driver.generate(provider.collection_id)
    finally:
        undo()
    yield root
