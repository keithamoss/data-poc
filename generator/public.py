"""The generator's one public module (REQ-GEN-386 criterion 3; REQ-GEN-381
criterion 3): everything the bootstrap reads of the generator, and the only
module of it the bootstrap imports.

WHY ONE MODULE. The bootstrap used to reach the generator by way of
cli/pipeline.py (generate_collection, has_target_trial, target_datasets,
generated_collections, generated_targets, generated_gate_outcomes and
generated_into), because nothing in qa_tools/ could import the generator. It
is a package of its own now, which may import the generator (REQ-TEST-384) but
not cli/, so what cli/pipeline.py offered it is offered here instead, and cli/
reads the same functions.

PROVISIONAL, step 3 of #134 (2026-11-15): built ahead of REQ-GEN-386's own
build, because REQ-GEN-381 criterion 3 needs it. A TARGET TRIAL IS NOT HERE: it
runs the real QA tools, which the generator may not import, so the bootstrap's
generate step (bootstrap/generation.py) runs it after generate() here.
"""
from __future__ import annotations


class NoGenerator(LookupError):
    """A collection with no synthetic data generator (no provider)."""


def require_generator(collection_id: str) -> None:
    """Refuse by name a collection with no provider - a real deployment's
    collections have none (post-build-review #229)."""
    from generator import collections as providers

    try:
        providers.provider(collection_id)
    except providers.NoProviderError as exc:
        raise NoGenerator(
            f"{collection_id} has no synthetic data generator, so there is nothing to "
            f"generate ({exc})") from None


def generate(collection_id: str) -> None:
    """One collection's synthetic history, through the shared driver
    (REQ-GEN-246), refused by name where it has no provider."""
    from generator import driver

    require_generator(collection_id)
    driver.generate(collection_id)


def has_target_trial(collection_id: str) -> bool:
    """Whether the collection's generator provider declares a target trial
    (REQ-GEN-246 criterion 5); refused by name where it has no provider."""
    from generator import collections as providers

    require_generator(collection_id)
    return providers.provider(collection_id).target_trial


def target_datasets(collection_id: str) -> tuple[str, ...]:
    """The datasets whose built targets the replay's comparison reads for
    this collection, as its provider declares them (criterion 5)."""
    from generator import collections as providers

    return providers.provider(collection_id).target_datasets


def generated_collections() -> list[str]:
    """Every collection with a generator provider, in hierarchy order."""
    from generator import collections as providers

    return [p.collection_id for p in providers.providers()]


def generated_targets():
    """What the last generation built each targeted supply to - for the
    comparison after a replay (REQ-GEN-186 criterion 3)."""
    from generator import targets

    return targets.written()


def generated_gate_outcomes():
    """The gate outcomes the scripted scenarios declare (REQ-GEN-273
    criterion 3), from the generator's placements."""
    from generator import targets

    return targets.gate_outcomes()


def generated_into(root):
    """Every generator writing under `root` - for a resume's comparison
    (REQ-TEST-160)."""
    from generator.output import generated_into as _generated_into

    return _generated_into(root)


def this_assets_scenarios() -> set[str]:
    """The scenarios whose injections name a dataset the selected asset
    declares - what the scenario map is written naming (REQ-PIPE-352
    criterion 3)."""
    from generator import scenario_injection

    return scenario_injection.this_assets_scenarios()


def anchor_statement():
    """(the date the generated history runs up to, 'fixed' or 'rolled') - the
    anchor installed for this run, as a bootstrap's closing line says it
    (REQ-GEN-399 criterion 4)."""
    from asset_model import history_anchor
    from generator import anchor_date

    up_to = anchor_date.get_anchor_date()
    return up_to.isoformat(), history_anchor.kind(up_to)


# THE ANCHOR, AS THE BOOTSTRAP SEES IT (REQ-GEN-404, REQ-GEN-405) - through
# this one module, as everything else of the generator's.
from generator.anchor_date import (  # noqa: E402,F401 - re-exported for the bootstrap
    FIXED_TEST_ANCHOR, AnchorRefused, refuse_the_retired_variable, validate as validate_anchor,
    zone_name)


def recorded_anchor():
    """The anchor the generator's bookkeeping records for the history on disk
    (REQ-GEN-404 criterion 3), or None."""
    from generator import driver

    return driver.recorded_anchor()


def written_delivery_names(bookkeeping) -> set[str]:
    """Every delivery folder the generator's bookkeeping at `bookkeeping` says
    it wrote - what a reset may delete and regenerate (REQ-GEN-408 criterion
    4). Empty where there is no bookkeeping."""
    import json
    from pathlib import Path

    from generator import driver

    path = Path(bookkeeping)
    if not path.exists():
        return set()
    book = json.loads(path.read_text(encoding="utf-8"))
    return {e["delivery"] for k in driver.dataset_keys(book) for e in book[k]
            if isinstance(e, dict) and e.get("delivery")}


# ---- the scenario map and the delivery tree (REQ-GEN-386 criteria 5 and 7) ----

#: The generator's bookkeeping file's name, which a reset deletes and keeps
#: (bootstrap/synthetic_reset.py).
from generator.delivery_writer import BOOKKEEPING_FILE  # noqa: E402,F401 - re-exported


def remove_deliveries(names, deliveries_dir=None, receipts_dir=None) -> int:
    """Clear the named deliveries the generator wrote, and their receipts -
    the generator's own writer's, looked up at call time."""
    from generator import delivery_writer

    return delivery_writer.remove_deliveries(names, deliveries_dir, receipts_dir)


def write_map(*, map_path):
    """Rebuild the selected asset's committed scenario map at `map_path` -
    the pipeline's scenario_map.map_path(), which the caller passes - naming
    this asset's scenarios (REQ-PIPE-352 criterion 3). Returns the path."""
    from generator import scenario_map_writer

    return scenario_map_writer.write_map(naming_mine=this_assets_scenarios(), map_path=map_path)


def build_map_for_selected() -> str:
    """The selected asset's scenario map as it would be written now."""
    from generator import scenario_map_writer

    return scenario_map_writer.build_for_selected(naming_mine=this_assets_scenarios())

