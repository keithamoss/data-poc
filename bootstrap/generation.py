"""Generating one collection's synthetic history for a replay (REQ-GEN-381
criterion 3): the generator's own run, then its target trial, then the scenario
map - what cli/pipeline.py's generate_collection did, moved here so the
bootstrap reaches the generator through its one public module
(generator/public.py) and never through cli/.

THE TRIAL RUNS WHERE THE PROVIDER DECLARES ONE, and is REFUSED BY NAME where
it does not (REQ-GEN-246 criterion 6) - never silently skipped. It runs the
four real tools over every supply the generator just wrote to a target, which
is the collection command's try_targets (cli/collection_cli.py), so the caller
hands it in as `try_targets` (PROVISIONAL, step 3 of #134): the bootstrap may
not import cli/, and the generator may not import the pipeline.

THE TRIAL FIRST, THE MAP ONCE IT AGREES (post-build-review #157 finding 7):
the map is committed, and a history the trial refused to emit should not leave
it rewritten. A map regenerated separately from the history is a map that
disagrees with it (REQ-GEN-045 criterion 3).
"""
from __future__ import annotations

from collections.abc import Callable

from generator import public
from generator.public import NoGenerator  # noqa: F401 - re-exported for callers


class TargetTrialUnavailable(LookupError):
    """A target trial asked of a collection whose provider declares none
    (REQ-GEN-246 criterion 6), or with no trial runner to run it."""


SKIPPED = ("Target trial skipped: no injected target was tried against the real tools. "
           "The comparison after a replay still runs.")


def generate_collection(collection_id: str, *, trial: bool,
                        try_targets: Callable[[str], object] | None = None,
                        say: Callable[[str], None] = print) -> None:
    """One collection's synthetic history, its trial where `trial`, then the
    scenario map - ALL UNDER ONE CONFIGURATION PIN (REQ-GEN-398 criterion 1):
    the bootstrap's own where it installed one around every collection's
    generation (criterion 2), else one taken here, so the generator, the
    target trial's processes (handed it through assets.handoff) and the map
    writer all read the configuration as it stood when this began.

    PROVISIONAL (2026-11-16): the scenario map writer (qa_tools/common/
    scenario_map.write_map) is pinned by this caller rather than installing a
    pin itself - it is a pipeline module, and only the synthetic side installs
    one (REQ-PIPE-397 criterion 4)."""
    from asset_model import config_pin

    with config_pin.pinned():
        _generate_collection(collection_id, trial=trial, try_targets=try_targets, say=say)


def _generate_collection(collection_id: str, *, trial: bool, try_targets, say) -> None:
    from qa_tools.common import scenario_map

    public.require_generator(collection_id)
    declared = public.has_target_trial(collection_id)
    if trial and not declared:
        raise TargetTrialUnavailable(
            f"{collection_id} has no target trial: its generator provider declares none, so "
            f"there is nothing to try against the real tools")
    if trial and try_targets is None:
        raise TargetTrialUnavailable(
            f"a target trial of {collection_id} was asked for with nothing to run it - "
            f"pass try_targets, or ask for no trial")
    # A COLLECTION OF SEVERAL DATASETS HAS ITS TRIAL TOO (REQ-GEN-298 criterion
    # 10): each supply is tried against its own dataset's table.
    public.generate(collection_id)
    if trial:
        try_targets(collection_id)
    elif declared:
        say(SKIPPED)
    scenario_map.write_map(naming_mine=public.this_assets_scenarios())


def took_line(seconds: float) -> str:
    """What `mothman <collection> generate-synthetic-data` prints when it ends
    on its own (REQ-GEN-398 criterion 3): one line naming how long generation
    took, in the 'Took ...' line's own form."""
    return f"Took generation {seconds:.0f}s."
