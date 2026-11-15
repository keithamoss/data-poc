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
    scenario map."""
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
