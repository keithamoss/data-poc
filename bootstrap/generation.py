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

    The scenario map's writer is the generator's (REQ-GEN-386 criterion 5),
    reached through generator.public and pinned by this caller; its path is
    the pipeline's scenario_map.map_path(), passed in."""
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
    public.write_map(map_path=scenario_map.map_path())


def generate_on_its_own(collection_id: str, *, trial: bool,
                        try_targets: Callable[[str], object] | None = None,
                        say: Callable[[str], None] = print, anchor=None) -> None:
    """`mothman <collection> generate-synthetic-data`: one collection generated
    at the anchor its caller asked for - `anchor`, else the fixed test anchor
    (REQ-GEN-405 criterion 4) - installed for the generation and handed to every
    process it starts (REQ-GEN-404 criterion 10).

    REFUSED BEFORE ANYTHING IS WRITTEN (REQ-GEN-404 criteria 7, 8 and 9): the
    retired GENERATOR_ANCHOR_DATE; an anchor that is not a date, is in the
    future or is before the fixed one; another anchor than the fixed one under
    test or CI; and an anchor other than the one recorded for the asset's
    current history (SR3), naming reset then bootstrap."""
    from asset_model import history_anchor
    from bootstrap import anchoring, bootstrap

    public.refuse_the_retired_variable()
    # INSTALLED BEFORE THE FIRST CONFIGURATION READ, the validation's own
    # included (REQ-GEN-404 criterion 12).
    with history_anchor.anchored(bootstrap._provisional(anchor)):
        anchoring.requested(anchor, False)
        chosen = anchoring.chosen_without_roll(anchor)
        problem = anchoring.mismatch(chosen.anchor, history_anchor.recorded())
        if problem:
            raise anchoring.AnchorRefused(problem)
        with history_anchor.anchored(chosen.anchor):
            generate_collection(collection_id, trial=trial, try_targets=try_targets, say=say)


def took_line(seconds: float) -> str:
    """What `mothman <collection> generate-synthetic-data` prints when it ends
    on its own (REQ-GEN-398 criterion 3): one line naming how long generation
    took, in the 'Took ...' line's own form."""
    from qa_tools.common.display_time import format_elapsed

    return f"Took generation {format_elapsed(seconds)}."
