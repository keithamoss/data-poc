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
